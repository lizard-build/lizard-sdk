import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from executors import PythonExecutor, NodeExecutor, BashExecutor

LANGUAGE_ALIASES = {
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "sh": "bash",
    "shell": "bash",
    "py": "python",
    "python3": "python",
}


def normalize_language(lang: str) -> str:
    return LANGUAGE_ALIASES.get(lang.lower(), lang.lower())


@dataclass
class Context:
    id: str
    language: str
    cwd: str
    _executor: object = field(repr=False)

    async def execute(self, code: str, env_vars: dict | None = None) -> AsyncIterator[dict]:
        return self._executor.execute(code, env_vars)

    async def close(self):
        if hasattr(self._executor, "close"):
            await self._executor.close()


class ContextManager:
    def __init__(self):
        self._contexts: dict[str, Context] = {}
        self._defaults: dict[str, str] = {}  # language → context_id

    def create(self, language: str = "python", cwd: str = "/home/user") -> Context:
        language = normalize_language(language)
        ctx_id = str(uuid.uuid4())

        executor = _make_executor(language, cwd)
        ctx = Context(id=ctx_id, language=language, cwd=cwd, _executor=executor)
        self._contexts[ctx_id] = ctx
        return ctx

    def get(self, context_id: str) -> Context | None:
        return self._contexts.get(context_id)

    def get_or_create_default(self, language: str) -> Context:
        language = normalize_language(language)
        ctx_id = self._defaults.get(language)
        if ctx_id and ctx_id in self._contexts:
            return self._contexts[ctx_id]
        ctx = self.create(language)
        self._defaults[language] = ctx.id
        return ctx

    def list(self) -> list[Context]:
        return list(self._contexts.values())

    async def delete(self, context_id: str) -> bool:
        ctx = self._contexts.pop(context_id, None)
        if ctx is None:
            return False
        await ctx.close()
        # Remove from defaults if it was default
        for lang, cid in list(self._defaults.items()):
            if cid == context_id:
                del self._defaults[lang]
        return True

    def ensure_defaults(self):
        self.get_or_create_default("python")
        self.get_or_create_default("javascript")


def _make_executor(language: str, cwd: str):
    if language == "python":
        return PythonExecutor(cwd)
    if language == "javascript":
        return NodeExecutor(cwd)
    if language == "bash":
        return BashExecutor(cwd)
    raise ValueError(f"Unsupported language: {language}")
