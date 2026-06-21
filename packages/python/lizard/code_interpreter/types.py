from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass
class StdoutItem:
    type: Literal["stdout"] = "stdout"
    data: str = ""
    ts: int = 0


@dataclass
class StderrItem:
    type: Literal["stderr"] = "stderr"
    data: str = ""
    ts: int = 0


@dataclass
class ResultItem:
    type: Literal["result"] = "result"
    mime: str = "text/plain"
    data: str = ""


@dataclass
class ErrorItem:
    type: Literal["error"] = "error"
    name: str = ""
    message: str = ""
    traceback: str = ""


OutputItem = Union[StdoutItem, StderrItem, ResultItem, ErrorItem]


class ExecutionError(Exception):
    def __init__(self, name: str, message: str, traceback: str):
        super().__init__(message)
        self.name = name
        self.traceback = traceback


@dataclass
class Execution:
    stdout: str = ""
    stderr: str = ""
    results: list[ResultItem] = field(default_factory=list)
    error: ExecutionError | None = None
    execution_count: int = 0

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def text(self) -> str:
        return self.stdout


@dataclass
class CodeContext:
    id: str
    language: str
    cwd: str
