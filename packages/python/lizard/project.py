from __future__ import annotations

from hashlib import sha256

from .config import ConnectionConfig, HTTP_TIMEOUT_S
from .errors import LizardError, handle_api_error

# Resolved project IDs are cached per (api_url, credential hash, ref) so repeated sandbox creates
# on the same Lizard client don't re-list projects on every call.
_project_id_cache: dict[str, str] = {}


def resolve_project_id(ref: str, config: ConnectionConfig) -> str:
    """
    Resolve a project reference — its ID, slug, or name — to the stable project
    ID the API bills against. Raises :class:`LizardError` when nothing matches.
    """
    import httpx

    cache_key = f"{config.api_url} {sha256(config.api_key.encode()).hexdigest()} {ref}"
    cached = _project_id_cache.get(cache_key)
    if cached:
        return cached

    res = httpx.get(f"{config.api_url}/api/projects", headers=config.headers, timeout=HTTP_TIMEOUT_S)
    if not res.is_success:
        handle_api_error(res.status_code, res.text)

    projects = res.json()
    lower = ref.lower()
    matches = [p for p in projects if lower in (
        p.get("id", "").lower(), (p.get("slug") or "").lower(), (p.get("name") or "").lower()
    )]
    if len(matches) > 1:
        raise LizardError("Project reference is ambiguous; pass the project ID")
    if matches:
        _project_id_cache[cache_key] = matches[0]["id"]
        return matches[0]["id"]

    available = ", ".join(p.get("slug") or p["id"] for p in projects) or "(none)"
    raise LizardError(
        f'Project "{ref}" not found. Available: {available}. '
        "Pass the project's ID, slug, or name."
    )


def require_project_ref(
    *, project: str | None = None, project_id: str | None = None
) -> tuple[str | None, str | None]:
    """
    Every sandbox must belong to a project — billing is metered per project.
    Returns the reference the caller gave as ``(project_id, project)``, raising
    :class:`LizardError` when they gave none. Checked before the connection is
    built so a missing project is reported as such, not as a missing API key.
    """
    if project_id:
        return project_id, None
    if project:
        return None, project
    raise LizardError(
        "A project is required to create a sandbox. Pass project (its ID, slug, "
        "or name), or create sandboxes through a Lizard client: "
        'Lizard(project="my-project").'
    )


def resolve_required_project_id(
    config: ConnectionConfig,
    *,
    project: str | None = None,
    project_id: str | None = None,
) -> str:
    """
    Resolve the project a sandbox will be billed to: an exact ``project_id``
    skips the lookup, otherwise ``project`` (ID, slug, or name) is resolved.
    """
    resolved_id, ref = require_project_ref(project=project, project_id=project_id)
    return resolved_id or resolve_project_id(ref, config)  # type: ignore[arg-type]
