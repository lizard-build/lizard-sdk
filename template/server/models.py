from typing import Optional
from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    code: str
    context_id: Optional[str] = None
    language: Optional[str] = None
    env_vars: Optional[dict[str, str]] = None


class CreateContextRequest(BaseModel):
    language: str = "python"
    cwd: str = "/home/user"


class ContextInfo(BaseModel):
    id: str
    language: str
    cwd: str
