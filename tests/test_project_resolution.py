"""
A sandbox is billed per project, so the SDK must never send a create request
without one. These cover the resolution itself — no network, httpx is stubbed.

Run with:
    PYTHONPATH=packages/python venv/bin/pytest tests/test_project_resolution.py -v
"""
from __future__ import annotations

import itertools

import httpx
import pytest

from lizard import Lizard
from lizard.config import ConnectionConfig
from lizard.errors import LizardError
from lizard.project import resolve_project_id, resolve_required_project_id

PROJECTS = [
    {"id": "p_abc", "name": "My Project", "slug": "my-project-x1"},
    {"id": "p_def", "name": "Other", "slug": "other-y2"},
]

_counter = itertools.count()


@pytest.fixture
def config(monkeypatch):
    """A config whose /api/projects returns PROJECTS, counting the calls.

    Each config gets its own api_url so the module-level cache — keyed on
    (api_url, ref) — cannot leak a resolved id between tests.
    """
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json=PROJECTS, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    cfg = ConnectionConfig(
        api_key="liz_test", api_url=f"https://api.test-{next(_counter)}.invalid"
    )
    cfg.calls = calls  # type: ignore[attr-defined]
    return cfg


class TestResolveProjectId:
    def test_matches_id_slug_and_name_ignoring_case(self, config):
        assert resolve_project_id("p_abc", config) == "p_abc"
        assert resolve_project_id("my-project-x1", config) == "p_abc"
        assert resolve_project_id("My Project", config) == "p_abc"
        assert resolve_project_id("MY PROJECT", config) == "p_abc"

    def test_unknown_project_raises_and_lists_available(self, config):
        with pytest.raises(LizardError, match="not found"):
            resolve_project_id("nope", config)

    def test_caches_so_repeated_creates_do_not_relist(self, config):
        resolve_project_id("other-y2", config)
        resolve_project_id("other-y2", config)
        assert len(config.calls) == 1


class TestResolveRequiredProjectId:
    def test_exact_project_id_skips_the_network(self, config):
        assert resolve_required_project_id(config, project_id="p_zzz") == "p_zzz"
        assert config.calls == []

    def test_resolves_a_project_reference(self, config):
        assert resolve_required_project_id(config, project="other-y2") == "p_def"

    def test_refuses_without_a_project(self, config):
        with pytest.raises(LizardError, match="project is required"):
            resolve_required_project_id(config)


class TestLizardClient:
    def test_requires_a_project_up_front(self):
        with pytest.raises(TypeError):
            Lizard()  # type: ignore[call-arg]
        with pytest.raises(LizardError, match="project is required"):
            Lizard(project="")

    def test_resolves_its_project_reference(self, config):
        lizard = Lizard(project="my-project-x1", api_key="liz_test", api_url=config.api_url)
        assert lizard.project_id() == "p_abc"
