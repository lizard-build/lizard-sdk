from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Sequence

from ..errors import LizardError

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from .fs import Fs
    from .process import Process, ProcessResult


MouseButton = Literal["left", "right", "middle"]
ScrollDirection = Literal["up", "down", "left", "right"]

_BUTTONS = {"left": "1", "middle": "2", "right": "3"}
_SCROLL_BUTTONS = {"up": "4", "down": "5", "left": "6", "right": "7"}
#: Milliseconds between typed characters; xdotool's own default.
_TYPE_DELAY_MS = 12
#: Where ``lizard-desktop screenshot --path`` writes its file (mktemp suffix).
_SCREENSHOT_PATH = re.compile(r"/tmp/lizard-screenshot-[A-Za-z0-9_-]+\.png")
_OPEN_URL_SCRIPT = 'setsid chromium --new-window "$1" >/dev/null 2>&1 < /dev/null &'


@dataclass
class DesktopInfo:
    """State of a sandbox's desktop, and the URLs that stream it.

    **Both URLs are credentials.** The port is published on a public hostname and
    each URL carries the stream token and a VNC password: anyone holding ``url`` can
    see and control the desktop, anyone holding ``view_only_url`` can watch it. Do
    not log them or put them anywhere you would not put an API key.
    """

    running: bool
    #: Screen size in pixels, or ``None`` when the desktop has never been started.
    width: int | None
    height: int | None
    #: noVNC page with full control (mouse and keyboard). Treat like a credential.
    url: str
    #: noVNC page that can only watch; enforced by the VNC server, not the page.
    view_only_url: str


def _to_info(d: dict) -> DesktopInfo:
    return DesktopInfo(
        running=bool(d.get("running")),
        width=d.get("width"),
        height=d.get("height"),
        url=d.get("url", ""),
        view_only_url=d.get("viewOnlyUrl", ""),
    )


def _coord(n: float) -> str:
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n < 0:
        raise LizardError(f"Invalid screen coordinate: {n!r}")
    return str(int(round(n)))


class Desktop:
    """
    A graphical desktop in the sandbox, for computer-use agents and for people to watch.

    Only the ``desktop`` template has one (Xvfb + XFCE + Chromium on ``DISPLAY=:1``);
    on any other template the calls raise with ``code == "DESKTOP_NOT_SUPPORTED"``.

    Input and screenshots run inside the sandbox with ``xdotool`` and ``scrot``. Every
    argument goes to the sandbox as an argv list and is never parsed by a shell, so
    text typed on behalf of a model or a user cannot run commands.

    Access via ``sandbox.desktop``.

    Example::

        sandbox = Sandbox.create("desktop", project="my-project")
        info = sandbox.desktop.start()        # open info.url in a browser
        sandbox.desktop.open_url("https://example.com")
        sandbox.desktop.click(640, 400)
        sandbox.desktop.type("hello")
        sandbox.desktop.press("Return")
        png = sandbox.desktop.screenshot()
    """

    def __init__(self, sandbox_id: str, config: "ConnectionConfig", process: "Process", fs: "Fs"):
        self._sandbox_id = sandbox_id
        self._config = config
        self._process = process
        self._fs = fs

    def _path(self) -> str:
        from ..platform.client import segment
        return f"/api/sandboxes/{segment(self._sandbox_id)}/desktop"

    def _client(self):
        from ..platform.client import PlatformClient
        return PlatformClient(self._config)

    def start(self, *, width: int | None = None, height: int | None = None) -> DesktopInfo:
        """Start the desktop, publish its stream and return the URLs.

        Idempotent: on a running desktop it returns the same URLs (the size of a
        running desktop is not changed). ``width`` 640-3840 and ``height`` 480-2160
        go together; the default is 1280x800.
        """
        body: dict = {}
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height
        return _to_info(self._client().post(self._path(), body))

    def info(self) -> DesktopInfo:
        """The desktop's state and URLs, without starting it."""
        return _to_info(self._client().get(self._path()))

    def stop(self) -> None:
        """Stop the desktop and unpublish its stream. Its URLs stay the same for the next start."""
        self._client().delete(self._path())

    def screenshot(self) -> bytes:
        """A PNG of the whole screen. The desktop must be running.

        Example::

            Path("screen.png").write_bytes(sandbox.desktop.screenshot())
        """
        # The PNG goes through a file, not stdout: exec output is streamed in 64 KiB
        # lines and capped at 512 KiB, and a real page is a ~250 KB PNG.
        r = self._run(["lizard-desktop", "screenshot", "--path"])
        lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
        path = lines[-1] if lines else ""
        if not _SCREENSHOT_PATH.fullmatch(path):
            raise LizardError(f"Screenshot returned an unexpected path: {path[:200]}")
        try:
            return self._fs.read_bytes(path)
        finally:
            try:
                self._fs.remove(path)
            except Exception:
                pass  # best effort: a leftover file in /tmp is harmless

    def click(self, x: float, y: float, *, button: MouseButton = "left", double: bool = False) -> None:
        """Click at (x, y)."""
        b = _BUTTONS.get(button)
        if b is None:
            raise LizardError(f"Unknown mouse button: {button!r}")
        repeat = ["--repeat", "2", "--delay", "100"] if double else []
        self._run(["xdotool", "mousemove", _coord(x), _coord(y), "click", *repeat, b])

    def move_mouse(self, x: float, y: float) -> None:
        """Move the pointer to (x, y) without clicking."""
        self._run(["xdotool", "mousemove", _coord(x), _coord(y)])

    def drag(self, from_x: float, from_y: float, to_x: float, to_y: float) -> None:
        """Press the left button at (from_x, from_y), move to (to_x, to_y) and release."""
        self._run([
            "xdotool",
            "mousemove", _coord(from_x), _coord(from_y), "mousedown", "1", "sleep", "0.1",
            "mousemove", _coord(to_x), _coord(to_y), "sleep", "0.1", "mouseup", "1",
        ])

    def type(self, text: str) -> None:
        """Type text into the focused window, as keystrokes.

        The text is passed as a single argument after ``--``, never through a shell.
        """
        if not text:
            return
        timeout_ms = min(600_000, max(60_000, len(text) * _TYPE_DELAY_MS * 3))
        self._run(["xdotool", "type", "--delay", str(_TYPE_DELAY_MS), "--", text], timeout_ms=timeout_ms)

    def press(self, keys: "str | Sequence[str]") -> None:
        """Press a key or a chord in xdotool keysym syntax: ``"Return"``, ``"ctrl+l"``,
        ``"alt+Tab"``. A list presses them one after another."""
        seq = [keys] if isinstance(keys, str) else list(keys)
        if not seq or any(not isinstance(k, str) or not k for k in seq):
            raise LizardError("press() needs at least one non-empty key")
        self._run(["xdotool", "key", "--", *seq])

    def scroll(self, direction: ScrollDirection, amount: int = 3) -> None:
        """Scroll with the mouse wheel at the pointer's current position. ``amount`` is wheel clicks."""
        b = _SCROLL_BUTTONS.get(direction)
        if b is None:
            raise LizardError(f"Unknown scroll direction: {direction!r}")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise LizardError("scroll amount must be a positive integer")
        self._run(["xdotool", "click", "--repeat", str(amount), "--delay", "30", b])

    def cursor_position(self) -> tuple[int, int]:
        """Where the pointer is now, as ``(x, y)``."""
        r = self._run(["xdotool", "getmouselocation", "--shell"])
        x = re.search(r"^X=(\d+)$", r.stdout, re.M)
        y = re.search(r"^Y=(\d+)$", r.stdout, re.M)
        if not x or not y:
            raise LizardError(f"Unexpected xdotool output: {r.stdout.strip()}")
        return int(x.group(1)), int(y.group(1))

    def open_url(self, url: str) -> None:
        """Open a URL in a new Chromium window on the desktop.

        Returns once Chromium has been launched, not when the page has loaded -- take
        a screenshot to see it.
        """
        # The URL is "$1" of the script, never part of the script text.
        self._run(["sh", "-c", _OPEN_URL_SCRIPT, "sh", url])

    def _run(self, argv: list[str], *, timeout_ms: int | None = None) -> "ProcessResult":
        r = self._process.exec_(argv, timeout_ms=timeout_ms)
        if r.exit_code != 0:
            err = LizardError(f"{argv[0]} {argv[1]} failed (exit {r.exit_code}): {(r.stderr or r.stdout).strip()}")
            if r.exit_code == 127:
                err.code = "DESKTOP_NOT_SUPPORTED"
            raise err
        return r
