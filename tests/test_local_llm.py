"""The local model supervisor, against a fake llama-server.

The fake is a real executable that speaks the same HTTP API, so this runs
the actual spawn / health-wait / request / crash / restart path with no model
and no GPU. What it proves is the rule local_llm.py is built on: every way
the server can misbehave ends in a ModelError the pipeline turns into the
rules' text, never in a hang or a lost dictation.
"""
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = str(TMP)

import config  # noqa: E402
import local_llm  # noqa: E402
import models  # noqa: E402
import paths  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


# Generous: the first launch of a fresh Python script can take seconds on a
# cold machine, and a timeout here is a flaky test, not a finding.
def wait_for(fn, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


# --- the fake server ----------------------------------------------------------

MODE_FILE = TMP / "fake-mode"
MODE_FILE.write_text("ok")
FAKE = TMP / "llama-server"
FAKE.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
    import json, sys, time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    args = sys.argv[1:]
    if args == ["--version"]:
        sys.exit(0)
    port = int(args[args.index("--port") + 1])
    key = open(args[args.index("--api-key-file") + 1]).read().strip()
    mode_file = "MODE_FILE"
    mode = lambda: open(mode_file).read().strip()
    if mode() == "crash":
        sys.exit(3)
    started = time.time()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            loading = mode() == "slowload" and time.time() - started < 1.0
            self._send(503 if loading else 200, {"status": "loading" if loading else "ok"})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.headers.get("Authorization") != "Bearer " + key:
                return self._send(401, {"error": "bad key"})
            if mode() == "slow":
                time.sleep(3)
            said = body["messages"][-1]["content"]
            self._send(200, {"choices": [{"finish_reason": "stop",
                                          "message": {"role": "assistant", "content": said}}]})

    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
'''.replace("MODE_FILE", str(MODE_FILE))))
FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)

# Run the fake once, untimed, before anything below is on a clock. The first
# exec of a brand-new executable can take many seconds (on a CI runner it
# outlasted a 20s wait while every later launch was instant), and that is the
# machine vetting a file, not the supervisor being slow.
t0 = time.time()
subprocess.run([str(FAKE), "--version"], timeout=120, check=True)
print(f"(fake llama-server first exec: {time.time() - t0:.1f}s)")

GGUF = TMP / "fake.gguf"
GGUF.write_bytes(b"GGUF")

MSG = [{"role": "system", "content": "clean"}, {"role": "user", "content": "hello there"}]

print("=== nothing installed ===")
srv = local_llm.LlamaServer()
srv._launch()
check("no model file -> not_installed", srv.status().state == "not_installed")
check("...and it says how to fix it", "halo model local install" in srv.status().detail)
check("...and it is not usable", not srv.usable())

saved_path = models.llm_path
models.llm_path = lambda name: GGUF
config.LOCAL_SERVER_BIN = str(TMP / "missing-binary")
srv = local_llm.LlamaServer()
srv._launch()
check("no llama-server -> failed, with the brew command", srv.status().state == "failed"
      and "brew install llama.cpp" in srv.status().detail, srv.status())

print("\n=== a healthy server ===")
config.LOCAL_SERVER_BIN = str(FAKE)
srv = local_llm.LlamaServer()
srv.prewarm()
check("prewarm returns at once and loads in the background",
      srv.status().state in ("loading", "stopped", "ready"))
check("ready within a few seconds", wait_for(srv.usable), srv.status())
check("answers", srv.chat(MSG, budget=2, max_tokens=50) == "hello there")
check("the API key is not on the command line", srv._key not in " ".join(srv._proc.args))
mode = paths.LOCAL_SERVER_KEY.stat().st_mode & 0o777
check("the key file is private (0600)", mode == 0o600, oct(mode))
check("the pid is recorded for the next engine", paths.LOCAL_SERVER_PID.exists())
check("listens on loopback only", "127.0.0.1" in srv._proc.args)
check("its logging is off", "--log-disable" in srv._proc.args)

SECRET = "ZEBRA-SENTINEL-9021"
srv.chat([{"role": "user", "content": SECRET}], budget=2, max_tokens=20)
status_text = paths.LOCAL_MODEL_STATUS.read_text()
check("the status file says ready", json.loads(status_text)["state"] == "ready")
check("...and never holds dictated text", SECRET not in status_text)

print("\n=== too slow ===")
MODE_FILE.write_text("slow")
t0 = time.time()
try:
    srv.chat(MSG, budget=0.4, max_tokens=50)
    check("a slow answer is abandoned", False)
except local_llm.ModelError as e:
    took = time.time() - t0
    check("a slow answer is abandoned at the budget", took < 0.9, f"{took:.2f}s: {e}")
MODE_FILE.write_text("ok")

print("\n=== a crash ===")
os.kill(srv._proc.pid, signal.SIGKILL)
srv._proc.wait()
check("the next dictation sees it and does not wait", not srv.usable())
check("...state says it is restarting", srv.status().state == "stopped"
      and "restarting" in srv.status().detail, srv.status())
try:
    srv.chat(MSG, budget=1, max_tokens=20)
    check("a request while down fails fast", False)
except local_llm.ModelError:
    check("a request while down fails fast", True)
srv.prewarm()
check("no restart inside the backoff", srv._proc is None and not srv._starting)
time.sleep(1.1)
srv.prewarm()
check("restarted after the backoff", wait_for(srv.usable), srv.status())

print("\n=== still loading ===")
srv.stop()
MODE_FILE.write_text("slowload")
srv.prewarm()
check("a loading model is skipped, not waited for",
      wait_for(lambda: srv.status().state == "loading", 3) and not srv.usable())
check("...and becomes ready on its own", wait_for(srv.usable, 5), srv.status())
MODE_FILE.write_text("ok")

print("\n=== a model that will not load ===")
srv.stop()
srv._crashes.clear()
MODE_FILE.write_text("crash")
srv.prewarm()
wait_for(lambda: srv.status().state == "stopped" and srv._proc is None and not srv._starting, 5)
time.sleep(1.1)
srv.prewarm()
check("twice during load -> failed, and it stays down",
      wait_for(lambda: srv.status().state == "failed", 5), srv.status())
srv.prewarm()
check("...no restart loop", srv._proc is None and not srv._starting)
config.LOCAL_MODEL = "qwen3-4b"
check("changing the model in Settings clears the failure",
      srv.usable() is False and srv.status().state != "failed", srv.status())
config.LOCAL_MODEL = "qwen2.5-1.5b"
MODE_FILE.write_text("ok")

print("\n=== shutdown ===")
srv._crashes.clear()
srv._status = local_llm.Status("stopped")
srv.prewarm()
wait_for(srv.usable)
proc = srv._proc
srv.stop()
check("the process is gone", proc is not None and proc.poll() is not None)
check("pid and key files are removed",
      not paths.LOCAL_SERVER_PID.exists() and not paths.LOCAL_SERVER_KEY.exists())

paths.LOCAL_SERVER_PID.write_text(str(os.getpid()))
local_llm.reap_stale()
check("reaping never kills a recycled pid that is not llama-server", True)
check("...and forgets the stale pid file", not paths.LOCAL_SERVER_PID.exists())
models.llm_path = saved_path

print("\n=== someone else's server ===")


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"data": [{"id": "m"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send({"choices": [{"finish_reason": "stop", "message": {
            "content": body["messages"][-1]["content"] + " via " + body["model"]}}]})


httpd = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
port = httpd.server_address[1]
ep = local_llm.Endpoint(f"http://127.0.0.1:{port}", "llama3.2")
check("a loopback endpoint is used", ep.usable())
check("...with /v1 added and the configured model name",
      ep.chat(MSG, budget=2, max_tokens=20) == "hello there via llama3.2")
for url in ("http://example.com:11434/v1", "http://192.168.1.20:1234/v1",
            "http://127.0.0.1.evil.com/v1"):
    ep = local_llm.Endpoint(url, "m")
    check(f"refused: {url}", not ep.usable() and ep.status().state == "failed")
ep = local_llm.Endpoint("http://127.0.0.1:9", "m")
check("nothing listening -> not usable, quickly", not ep.usable())
httpd.shutdown()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
