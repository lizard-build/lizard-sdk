# The same source as packages/js/src/code-interpreter/runner.ts. The two copies must
# stay byte-identical (checked by packages/js/src/firecracker.test.ts).
SOURCE = r"""# Lizard code runner: executes code for CodeSandbox.run_code / runCode inside the sandbox.
# Python runs in a persistent Jupyter kernel per context when the template has one
# (the interpreter template does); everything else runs as a fresh process.
# Events are JSON lines on stdout; an event over 24000 chars is sent as "part" lines.
import base64, json, os, re, shutil, signal, subprocess, sys, threading, time
ROOT = "/tmp/.lizard-code"
LANGS = {"python": "python3", "javascript": "node", "bash": "bash"}
ALIASES = {"py": "python", "python3": "python", "js": "javascript", "node": "javascript", "sh": "bash"}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LOCK = threading.Lock()


def emit(ev):
    s = json.dumps(ev)
    with LOCK:
        if len(s) <= 24000:
            print(s, flush=True)
            return
        n = (len(s) + 23999) // 24000
        for i in range(n):
            print(json.dumps({"type": "part", "data": s[i * 24000:(i + 1) * 24000], "end": i == n - 1}), flush=True)


def fail(msg):
    emit({"type": "fatal", "message": msg})
    sys.exit(3)


def meta_path(ctx):
    return os.path.join(ROOT, ctx, "meta.json")


def load(ctx):
    try:
        with open(meta_path(ctx)) as f:
            return json.load(f)
    except OSError:
        return None


def save(m):
    os.makedirs(os.path.join(ROOT, m["id"]), exist_ok=True)
    with open(meta_path(m["id"]), "w") as f:
        json.dump(m, f)


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().split(") ")[-1][:1] != "Z"
    except OSError:
        return False


def kernel_pid(m):
    try:
        with open(os.path.join(ROOT, m["id"], "kernel.pid")) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def stop_kernel(m):
    pid = kernel_pid(m)
    if pid and alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    for name in ("kernel.pid", "kernel.json"):
        try:
            os.remove(os.path.join(ROOT, m["id"], name))
        except OSError:
            pass


def start_kernel(m):
    d = os.path.join(ROOT, m["id"])
    conn = os.path.join(d, "kernel.json")
    stop_kernel(m)
    os.makedirs(m["cwd"], exist_ok=True)
    log = open(os.path.join(d, "kernel.log"), "ab")
    p = subprocess.Popen([sys.executable, "-m", "ipykernel_launcher", "-f", conn], cwd=m["cwd"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                         env=dict(os.environ, PYTHONUNBUFFERED="1"))
    with open(os.path.join(d, "kernel.pid"), "w") as f:
        f.write(str(p.pid))
    end = time.time() + 30
    while time.time() < end:
        if os.path.exists(conn) and os.path.getsize(conn) > 0:
            return
        if p.poll() is not None:
            break
        time.sleep(0.05)
    with open(os.path.join(d, "kernel.log"), "rb") as f:
        tail = f.read()[-2000:].decode("utf-8", "replace")
    fail("python kernel failed to start: " + (tail or "no output"))


def has_kernel():
    try:
        import jupyter_client, ipykernel  # noqa: F401
        return True
    except ImportError:
        return False


def client(m):
    from jupyter_client import BlockingKernelClient
    if not (kernel_pid(m) and alive(kernel_pid(m))):
        start_kernel(m)
    kc = BlockingKernelClient()
    kc.load_connection_file(os.path.join(ROOT, m["id"], "kernel.json"))
    kc.start_channels()
    kc.wait_for_ready(timeout=30)
    return kc


def shell_reply(kc, msg_id, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = kc.get_shell_msg(timeout=max(0.01, end - time.time()))
        except Exception:
            return None
        if r["parent_header"].get("msg_id") == msg_id:
            return r
    return None


def silent(kc, code):
    shell_reply(kc, kc.execute(code, silent=True, store_history=False), 10)


BEST = ("image/png", "image/jpeg", "image/svg+xml", "text/html", "text/markdown", "application/json", "text/latex", "text/plain")


def run_python(m, code, envs, timeout):
    kc = client(m)
    if envs:
        silent(kc, "import os as _lz_os\n_lz_saved = {k: _lz_os.environ.get(k) for k in %r}\n_lz_os.environ.update(%r)" % (list(envs), envs))
    msg_id = kc.execute(code, store_history=True, allow_stdin=False)
    end = time.time() + timeout
    timed_out = False
    while True:
        left = end - time.time()
        if left <= 0:
            timed_out = True
            break
        try:
            msg = kc.get_iopub_msg(timeout=left)
        except Exception:
            continue
        if msg["parent_header"].get("msg_id") != msg_id:
            continue
        t, c = msg["msg_type"], msg["content"]
        if t == "stream":
            emit({"type": "stderr" if c.get("name") == "stderr" else "stdout", "data": c.get("text", "")})
        elif t in ("execute_result", "display_data"):
            data = c.get("data", {})
            mime = next((k for k in BEST if k in data), next(iter(data), None))
            if mime:
                v = data[mime]
                emit({"type": "result", "mime": mime, "data": v if isinstance(v, str) else json.dumps(v)})
        elif t == "error":
            emit({"type": "error", "name": c.get("ename", "Error"), "message": c.get("evalue", ""),
                  "traceback": ANSI.sub("", "\n".join(c.get("traceback", [])))})
        elif t == "status" and c.get("execution_state") == "idle":
            break
    count = 0
    if timed_out:
        pid = kernel_pid(m)
        if pid:
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                pass
        emit({"type": "error", "name": "TimeoutError", "message": "execution timed out after %gs; the kernel was interrupted" % timeout, "traceback": ""})
    else:
        r = shell_reply(kc, msg_id, 10)
        count = (r or {}).get("content", {}).get("execution_count") or 0
    if envs and not timed_out:
        silent(kc, "for _lz_k, _lz_v in _lz_saved.items():\n    _lz_os.environ.pop(_lz_k, None) if _lz_v is None else _lz_os.environ.__setitem__(_lz_k, _lz_v)")
    kc.stop_channels()
    emit({"type": "done", "execution_count": count})


def run_process(m, code, envs, timeout):
    interp = LANGS[m["language"]]
    if shutil.which(interp) is None:
        emit({"type": "error", "name": "LanguageUnavailable", "message": "%s is not installed in this sandbox" % interp, "traceback": ""})
        emit({"type": "done", "execution_count": 0})
        return
    d = os.path.join(ROOT, m["id"])
    src = os.path.join(d, "cell" + {"node": ".js", "bash": ".sh"}.get(interp, ".py"))
    with open(src, "w") as f:
        f.write(code)
    os.makedirs(m["cwd"], exist_ok=True)
    p = subprocess.Popen([interp, src], cwd=m["cwd"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=dict(os.environ, **(envs or {})), start_new_session=True)
    err_tail = []

    def pump(stream, kind):
        for line in iter(stream.readline, b""):
            text = line.decode("utf-8", "replace")
            if kind == "stderr":
                err_tail.append(text)
                del err_tail[:-50]
            emit({"type": kind, "data": text})

    ts = [threading.Thread(target=pump, args=(p.stdout, "stdout")), threading.Thread(target=pump, args=(p.stderr, "stderr"))]
    for t in ts:
        t.start()
    try:
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        rc = None
    for t in ts:
        t.join(5)
    m["count"] = m.get("count", 0) + 1
    save(m)
    if rc is None:
        emit({"type": "error", "name": "TimeoutError", "message": "execution timed out after %gs" % timeout, "traceback": ""})
    elif rc != 0:
        emit({"type": "error", "name": "ExitError", "message": "exited with code %d" % rc, "traceback": "".join(err_tail)})
    emit({"type": "done", "execution_count": m["count"]})


def ctx_for(a):
    lang = (a.get("language") or "python").lower()
    lang = ALIASES.get(lang, lang)
    if lang not in LANGS:
        fail("unsupported language %r; use python, javascript or bash" % lang)
    return lang


def main():
    a = json.loads(base64.b64decode(sys.argv[1]))
    act = a["action"]
    os.makedirs(ROOT, exist_ok=True)
    if act == "create" or (act == "run" and not a.get("context")):
        lang = ctx_for(a)
        cid = a.get("context") or ("default-" + lang)
        m = load(cid) if act == "run" else None
        if m is None:
            m = {"id": cid if act == "run" else a["id"], "language": lang, "cwd": a.get("cwd") or "/home/user"}
            save(m)
            if lang == "python" and act == "create" and has_kernel():
                client(m).stop_channels()
        if act == "create":
            emit({"type": "context", "id": m["id"], "language": m["language"], "cwd": m["cwd"]})
            return
    elif act == "list":
        out = []
        for name in sorted(os.listdir(ROOT)):
            m = load(name)
            if m and not name.startswith("default-"):
                out.append({"id": m["id"], "language": m["language"], "cwd": m["cwd"]})
        emit({"type": "contexts", "data": out})
        return
    else:
        m = load(a["context"])
        if m is None:
            fail("context %r not found" % a["context"])
        if act == "delete":
            stop_kernel(m)
            shutil.rmtree(os.path.join(ROOT, m["id"]), ignore_errors=True)
            emit({"type": "ok"})
            return
        if act == "restart":
            if m["language"] == "python" and has_kernel():
                start_kernel(m)
            m["count"] = 0
            save(m)
            emit({"type": "ok"})
            return
    code = a.get("code")
    if code is None:
        with open(a["codeFile"]) as f:
            code = f.read()
        os.remove(a["codeFile"])
    if m["language"] == "python" and has_kernel():
        run_python(m, code, a.get("envs") or {}, a.get("timeout") or 60)
    else:
        run_process(m, code, a.get("envs") or {}, a.get("timeout") or 60)


main()
"""
