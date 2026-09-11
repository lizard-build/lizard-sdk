class LizardError(Exception):
    pass

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

def handle_api_error(status_code: int, message: str) -> None:
    if status_code in (401, 403):
        raise AuthenticationError(message)
    if status_code == 404:
        raise NotFoundError(message)
    if status_code == 409:
        raise ConflictError(message)
    if status_code in (408, 504):
        raise TimeoutError(message)
    raise LizardError(f"API error {status_code}: {message}")
