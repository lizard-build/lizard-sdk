class LizardError(Exception):
    pass

class AuthenticationError(LizardError):
    pass

class NotFoundError(LizardError):
    pass

class TimeoutError(LizardError):
    pass

def handle_api_error(status_code: int, message: str) -> None:
    if status_code in (401, 403):
        raise AuthenticationError(message)
    if status_code == 404:
        raise NotFoundError(message)
    if status_code in (408, 504):
        raise TimeoutError(message)
    raise LizardError(f"API error {status_code}: {message}")
