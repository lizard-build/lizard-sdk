from __future__ import annotations

import json


class LizardError(Exception):
    """Base class for every SDK error.

    When the error came from an API call, ``status_code`` is its HTTP status and
    ``code`` is the server's machine-readable error code if it sent one (e.g.
    ``"volume_too_full_to_shrink"``). Branch on ``code`` rather than the message.
    """

    status_code: int | None = None
    code: str | None = None

class ConfigApplyError(LizardError):
    """Config was saved, but one or more deploy/restart actions failed."""
    def __init__(self, result):
        super().__init__("Config was saved, but one or more side effects failed; inspect result before retrying")
        self.result = result


class AuthenticationError(LizardError):
    pass

class NotFoundError(LizardError):
    pass

class ConflictError(LizardError):
    """The resource already exists.

    Most often a volume whose name is already taken in the project. Volume names are
    the key inside a project, so :meth:`Volume.create` refuses to make a second one;
    catch this, or call :meth:`Volume.get_or_create` instead.
    """


class TimeoutError(LizardError):
    pass

def handle_api_error(status_code: int, message: str, *, code: str | None = None) -> None:
    """Raise the error for a failed API call.

    ``message`` may be the raw response body: when it is a JSON ``{error, code?}``
    object, ``error`` becomes the message and ``code`` is kept on the exception.
    """
    try:
        body = json.loads(message)
    except (TypeError, ValueError):
        body = None
    if isinstance(body, dict):
        if isinstance(body.get("error"), str):
            message = body["error"]
        if code is None and isinstance(body.get("code"), str):
            code = body["code"]

    if status_code in (401, 403):
        err: LizardError = AuthenticationError(message)
    elif status_code == 404:
        err = NotFoundError(message)
    elif status_code == 409:
        err = ConflictError(message)
    elif status_code in (408, 504):
        err = TimeoutError(message)
    else:
        err = LizardError(f"API error {status_code}: {message}")
    err.status_code = status_code
    err.code = code
    raise err
