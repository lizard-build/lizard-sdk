"""sandbox.desktop: REST calls and xdotool/scrot argv, with the transport mocked."""
import base64
import json

import httpx
import pytest

from lizard import DesktopInfo, LizardError, Sandbox

CONFIG = {"api_key": "liz_test", "api_url": "https://test.invalid"}
INFO = {"running": True, "width": 1280, "height": 800,
        "url": "https://x/vnc.html?password=p", "viewOnlyUrl": "https://x/vnc.html?view_only=true"}


class Calls(list):
    """Recorded requests, plus what to answer the next one with."""
    reply: dict = {}
    state: dict = {}


@pytest.fixture
def execs(monkeypatch):
    """Record every exec request; answer with ``execs.reply``."""
    calls = Calls()
    calls.reply = {"stdout": "", "stderr": "", "exitCode": 0}

    def post(url, **kw):
        assert url == "https://test.invalid/api/sandboxes/sb1/exec"
        calls.append(kw["json"])
        return httpx.Response(200, json=calls.reply)

    monkeypatch.setattr(httpx, "post", post)
    return calls


def argv(calls):
    assert len(calls) == 1
    return calls[0]["cmd"]


@pytest.fixture
def rest(monkeypatch):
    calls = Calls()
    calls.state = state = {"status": 200, "body": INFO}

    def handler(request):
        calls.append((request.method, str(request.url), json.loads(request.content) if request.content else None))
        return httpx.Response(state["status"], json=state["body"])

    original = httpx.Client.__init__

    def init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        original(self, *a, **kw)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    return calls


def sandbox():
    return Sandbox("sb1", **CONFIG)


def test_start_info_stop(rest):
    info = sandbox().desktop.start(width=1920, height=1080)
    assert info == DesktopInfo(running=True, width=1280, height=800, url=INFO["url"], view_only_url=INFO["viewOnlyUrl"])
    sandbox().desktop.info()
    sandbox().desktop.stop()
    assert rest == [
        ("POST", "https://test.invalid/api/sandboxes/sb1/desktop", {"width": 1920, "height": 1080}),
        ("GET", "https://test.invalid/api/sandboxes/sb1/desktop", None),
        ("DELETE", "https://test.invalid/api/sandboxes/sb1/desktop", None),
    ]


def test_start_without_size_sends_empty_body(rest):
    sandbox().desktop.start()
    assert rest[0][2] == {}


def test_unsupported_template_keeps_code(rest):
    rest.state.update(status=400, body={"error": "The 'base' template has no desktop.", "code": "DESKTOP_NOT_SUPPORTED"})
    with pytest.raises(LizardError) as exc:
        sandbox().desktop.start()
    assert exc.value.code == "DESKTOP_NOT_SUPPORTED"
    assert exc.value.status_code == 400


def test_type_is_one_argv_element_never_shell(execs):
    text = "\"; rm -rf / #$(id) `id` 'quote' && echo pwned"
    sandbox().desktop.type(text)
    assert argv(execs) == ["xdotool", "type", "--delay", "12", "--", text]


def test_type_keeps_leading_dash_as_text(execs):
    sandbox().desktop.type("--help")
    assert argv(execs) == ["xdotool", "type", "--delay", "12", "--", "--help"]


def test_click(execs):
    sandbox().desktop.click(10, 20)
    sandbox().desktop.click(10.4, 20.6, button="right", double=True)
    assert [c["cmd"] for c in execs] == [
        ["xdotool", "mousemove", "10", "20", "click", "1"],
        ["xdotool", "mousemove", "10", "21", "click", "--repeat", "2", "--delay", "100", "3"],
    ]


@pytest.mark.parametrize("x", [float("nan"), -1, "10"])
def test_bad_coordinates_are_not_sent(execs, x):
    with pytest.raises(LizardError):
        sandbox().desktop.move_mouse(x, 1)
    assert execs == []


def test_press(execs):
    sandbox().desktop.press("ctrl+l")
    sandbox().desktop.press(["ctrl+a", "BackSpace; reboot"])
    assert [c["cmd"] for c in execs] == [
        ["xdotool", "key", "--", "ctrl+l"],
        ["xdotool", "key", "--", "ctrl+a", "BackSpace; reboot"],
    ]


def test_move_drag_scroll(execs):
    d = sandbox().desktop
    d.move_mouse(5, 6)
    d.drag(1, 2, 3, 4)
    d.scroll("down")
    d.scroll("left", 1)
    assert [c["cmd"] for c in execs] == [
        ["xdotool", "mousemove", "5", "6"],
        ["xdotool", "mousemove", "1", "2", "mousedown", "1", "sleep", "0.1", "mousemove", "3", "4", "sleep", "0.1", "mouseup", "1"],
        ["xdotool", "click", "--repeat", "3", "--delay", "30", "5"],
        ["xdotool", "click", "--repeat", "1", "--delay", "30", "6"],
    ]


def test_open_url_passes_url_as_positional_arg(execs):
    url = "https://example.com/?q=$(id)&x=`id`"
    sandbox().desktop.open_url(url)
    cmd = argv(execs)
    assert cmd == ["sh", "-c", 'setsid chromium --new-window "$1" >/dev/null 2>&1 < /dev/null &', "sh", url]
    assert url not in cmd[2]


def test_cursor_position(execs):
    execs.reply = {"stdout": "X=640\nY=400\nSCREEN=0\nWINDOW=123\n", "stderr": "", "exitCode": 0}
    assert sandbox().desktop.cursor_position() == (640, 400)
    assert argv(execs) == ["xdotool", "getmouselocation", "--shell"]


def test_screenshot_decodes_base64(execs):
    png = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 255])
    execs.reply = {"stdout": base64.b64encode(png).decode() + "\n", "stderr": "", "exitCode": 0}
    assert sandbox().desktop.screenshot() == png
    assert argv(execs) == ["lizard-desktop", "screenshot"]


def test_screenshot_refuses_truncated_output(execs):
    execs.reply = {"stdout": "iVBORw0KGgo", "stderr": "", "exitCode": 0, "truncated": True}
    with pytest.raises(LizardError, match="exec output limit"):
        sandbox().desktop.screenshot()


def test_failed_command_raises_with_stderr(execs):
    execs.reply = {"stdout": "", "stderr": "lizard-desktop: the desktop is not running", "exitCode": 1}
    with pytest.raises(LizardError, match="the desktop is not running"):
        sandbox().desktop.screenshot()


def test_missing_tool_is_desktop_not_supported(execs):
    execs.reply = {"stdout": "", "stderr": "sh: xdotool: not found", "exitCode": 127}
    with pytest.raises(LizardError) as exc:
        sandbox().desktop.click(1, 1)
    assert exc.value.code == "DESKTOP_NOT_SUPPORTED"
