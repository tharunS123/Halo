"""ACCEPTANCE: the whole workflow with the network switched off.

    Record -> Transcribe -> Clean -> Contextualize -> Format -> Insert
           -> Undo -> Transform

On macOS this test re-runs itself under `sandbox-exec` with every outbound
connection denied except to this machine -- DNS included -- so whisper-cli
and llama-server, separate binaries that Python cannot police, are held to it
as well. Inside, the engine's own netguard is on too, and must count zero
attempts.

With whisper.cpp and the models installed (a developer's Mac) the transcribe
and model steps use the real binaries and real models. Where they are not
(CI), those two steps get stand-ins and the test says so. Everything else is
the real engine -- context capture, the cleanup pipeline, verified insertion,
safe undo, Command Mode, failed-dictation recovery -- against a fake
Accessibility layer playing Notes and Messages.

It also carries the critical integration case: start dictating into Notes,
switch to Messages while Halo is still processing, and the Notes transcript
must NOT land in Messages.
"""
import contextlib
import io
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

# --- 1. no network, for this process and every child it starts --------------

PROFILE = (
    '(version 1)(allow default)'
    '(deny network-outbound)'
    '(allow network-outbound (remote ip "localhost:*"))'
    '(allow network-outbound (remote unix-socket))'
    # mDNSResponder is a Unix socket, but talking to it is a DNS lookup.
    '(deny network-outbound (remote unix-socket (path-literal "/private/var/run/mDNSResponder")))'
)


def _sandbox_works() -> bool:
    try:
        return subprocess.run(["sandbox-exec", "-p", PROFILE, "/usr/bin/true"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


if (os.environ.get("HALO_E2E_SANDBOXED") != "1" and sys.platform == "darwin"
        and shutil.which("sandbox-exec") and _sandbox_works()):
    env = dict(os.environ, HALO_E2E_SANDBOXED="1")
    sys.exit(subprocess.run(["sandbox-exec", "-p", PROFILE, sys.executable, __file__],
                            env=env).returncode)
SANDBOXED = os.environ.get("HALO_E2E_SANDBOXED") == "1"

# --- 2. a private Halo: its own config, data and logs; the real models ------

TMP = Path(tempfile.mkdtemp(prefix="halo-e2e-"))
shutil.copytree(FIXTURES, TMP / "config")
os.environ["HALO_CONFIG_DIR"] = str(TMP / "config")
os.environ["HALO_DATA_DIR"] = str(TMP / "data")
os.environ["HALO_LOG_DIR"] = str(TMP / "logs")
os.environ["HALO_OVERLAY"] = "0"

REAL_MODELS = Path.home() / "Library" / "Application Support" / "Halo" / "models"
models_dir = TMP / "models"
models_dir.mkdir()
# Links, not copies (the models are GBs) -- and not the real folder itself,
# so nothing here can write into it.
for f in REAL_MODELS.glob("*") if REAL_MODELS.is_dir() else ():
    if f.suffix in (".bin", ".gguf"):
        (models_dir / f.name).symlink_to(f)
    elif f.name == "verified.json":
        shutil.copyfile(f, models_dir / f.name)
os.environ["HALO_MODELS_DIR"] = str(models_dir)
for name in ("small.en", "base.en", "tiny.en"):
    if (models_dir / f"ggml-{name}.bin").exists():
        os.environ["HALO_MODEL"] = name
        break

import numpy as np  # noqa: E402

import clipboard  # noqa: E402
import config  # noqa: E402
import context  # noqa: E402
import halo  # noqa: E402
import inject  # noqa: E402
import local_llm  # noqa: E402
import models  # noqa: E402
import netguard  # noqa: E402
import overlay  # noqa: E402
import transcribe  # noqa: E402
import transforms  # noqa: E402
from audio import Recorder  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


JFK = next((p for p in (
    Path(subprocess.run(["brew", "--prefix", "whisper.cpp"], capture_output=True, text=True)
         .stdout.strip() or "/nonexistent") / "share" / "whisper.cpp" / "jfk.wav",
    Path("/opt/homebrew/share/whisper.cpp/jfk.wav"),
) if p.exists()), None)
REAL_WHISPER = not transcribe.preflight() and JFK is not None
REAL_LLM = local_llm.find_server_binary() is not None and \
    models.llm_path(config.LOCAL_MODEL) is not None

print(f"sandbox (network denied for every process) : {'yes' if SANDBOXED else 'NOT AVAILABLE'}")
print(f"whisper.cpp                                : {'real, ' + config.WHISPER_MODEL_EN.name if REAL_WHISPER else 'stand-in (not installed)'}")
print(f"local language model                       : {'real, ' + config.LOCAL_MODEL if REAL_LLM else 'stand-in (not installed)'}")

print("\n=== 0. the network really is off ===")
if SANDBOXED:
    import socket
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(("1.1.1.1", 443))
        check("the sandbox refuses a connection off this Mac", False, "it connected")
    except OSError as e:
        check("the sandbox refuses a connection off this Mac", True, type(e).__name__)
    finally:
        s.close()
    try:
        socket.getaddrinfo("example.com", 443)
        check("...and a DNS lookup", False, "it resolved")
    except OSError:
        check("...and a DNS lookup", True)
netguard.install()
try:
    import socket
    socket.create_connection(("93.184.216.34", 80), timeout=2)
    check("netguard refuses a connection off this Mac", False)
except netguard.NetworkBlocked:
    check("netguard refuses a connection off this Mac", True)
try:
    socket.getaddrinfo("openrouter.ai", 443)
    check("netguard refuses a lookup", False)
except netguard.NetworkBlocked:
    check("netguard refuses a lookup", True)
netguard.clear()            # those two were ours; from here on, zero is the bar

# --- 3. Notes and Messages, as the Accessibility layer shows them -----------


class Field:
    def __init__(self, value=""):
        self.value = value
        self.sel = (len(value), 0)


class App:
    def __init__(self, pid, bundle, name, window, field):
        self.pid, self.bundle, self.name, self.window, self.field = pid, bundle, name, window, field


class FakeAX:
    """Everything context.capture() and insertion.py ask of the real one."""

    def __init__(self):
        self.fields = {"notes-body": Field(), "messages-input": Field()}
        self.apps = {101: App(101, "com.apple.Notes", "Notes", "notes-win", "notes-body"),
                     202: App(202, "com.apple.MobileSMS", "Messages", "messages-win",
                              "messages-input")}
        self.front = 101
        self.on_focus = None   # a hook to switch apps mid-dictation

    def focus(self, pid):
        self.front = pid

    def secure_input(self):
        return False

    def focused_app(self):
        return ("app", self.front), self.front

    def app_info(self, pid):
        a = self.apps[pid]
        return a.bundle, a.name

    def attr(self, elem, name):
        if isinstance(elem, tuple) and elem[0] == "app":
            a = self.apps[elem[1]]
            return {"AXFocusedWindow": a.window, "AXFocusedUIElement": a.field}.get(name)
        f = self.fields.get(elem)
        if f is None:
            return None
        loc, n = f.sel
        return {"AXValue": f.value, "AXSelectedText": f.value[loc:loc + n],
                "AXRole": "AXTextArea", "AXNumberOfCharacters": len(f.value)}.get(name)

    def selected_range(self, elem):
        return self.fields[elem].sel

    def string_for_range(self, elem, loc, n):
        return self.fields[elem].value[loc:loc + n]

    def settable(self, elem, name):
        return elem in self.fields

    def set_attr(self, elem, name, value):
        f = self.fields[elem]
        if name == "AXSelectedText":
            loc, n = f.sel
            f.value = f.value[:loc] + value + f.value[loc + n:]
            f.sel = (loc + len(value), 0)
        return True

    def set_selected_range(self, elem, loc, length):
        self.fields[elem].sel = (loc, length)
        return True

    def focused_element(self, app):
        return self.apps[app[1]].field

    @staticmethod
    def same(a, b):
        return a is not None and a == b

    def url_host(self, value):
        return ""


AX = FakeAX()
context._ax = AX
inject.accessibility_ok = lambda: True
PASTES = []
inject.paste_keystroke = lambda: PASTES.append(1)   # never expected: Notes takes AX
CLIPBOARD = []
clipboard.put_text_for_user = lambda text, pb=None: CLIPBOARD.append(text)


class UI(overlay.NullOverlay):
    def __init__(self):
        self.events = []

    def listening(self):       self.events.append("listening")
    def processing(self):      self.events.append("processing")
    def inserting(self):       self.events.append("inserting")
    def done(self):            self.events.append("done")
    def hide(self):            self.events.append("hide")
    def error(self, m):        self.events.append(f"error:{m}")
    def flash(self, m):        self.events.append(f"flash:{m}")
    def failed(self, on):      self.events.append(f"failed:{on}")


# --- 4. a local model endpoint on this Mac (loopback: allowed) ---------------

SEEN_BY_MODEL = []


class ModelHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"data": [{"id": "fake"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN_BY_MODEL.append(body["messages"])
        said = body["messages"][-1]["content"]
        if body["messages"][0]["content"].startswith(transforms.SYSTEM[:40]):
            # A transform: "make this shorter" -> its first line.
            text = said.split("TEXT:\n", 1)[1]
            said = text.splitlines()[0]
        self._send({"choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": said}}]})


class NoDNSServer(ThreadingHTTPServer):
    def server_bind(self):          # skip HTTPServer's reverse lookup
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


server = NoDNSServer(("127.0.0.1", 0), ModelHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()


def use_fake_model():
    config.LOCAL_BACKEND = "endpoint"
    config.LOCAL_ENDPOINT = f"http://127.0.0.1:{server.server_address[1]}/v1"
    config.LOCAL_ENDPOINT_MODEL = "fake"


# --- 5. driving one dictation ------------------------------------------------

f = halo.Halo(ui=UI())
f.privacy.set(False)
LOG = io.StringIO()


def sine_wav() -> str:
    t = np.arange(int(config.SAMPLE_RATE * 1.2)) / config.SAMPLE_RATE
    return Recorder._write_wav((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))


def dictate(heard=None, wav=None, during=None):
    """Key down in the focused app, speak, key up -- then the whole finish().
    `heard` stands in for whisper; None means the real whisper.cpp.
    `during` runs while whisper works: the moment someone switches apps."""
    f._begin_context()
    f.stage = "recording"
    clip = wav or sine_wav()
    real = transcribe.transcribe
    if heard is not None or during is not None:
        def fake(path, language=None, **kw):
            if during:
                during()
            if heard is None:
                return real(path, language, **kw)
            return transcribe.TranscriptResult(heard, "en", "stand-in")
        transcribe.transcribe = fake
    saved_stop = f.recorder.stop
    f.recorder.stop = lambda: (clip, 1.2)
    f.ui.events.clear()
    try:
        with contextlib.redirect_stdout(LOG):
            f.finish()
    finally:
        transcribe.transcribe = real
        f.recorder.stop = saved_stop


notes = AX.fields["notes-body"]
messages = AX.fields["messages-input"]

# --- A. Record -> Transcribe -> Clean -> Insert -> Undo, real binaries ------

print("\n=== A. Record -> Transcribe -> Clean -> Insert -> Undo ===")
if REAL_LLM:
    config.LOCAL_BACKEND = "llama.cpp"
    config.LOCAL_BUDGET = 15.0          # a cold first answer is allowed to be slow here
    local_llm.prewarm("normal")
    deadline = time.time() + 60
    lm = local_llm.local_model()
    while time.time() < deadline and not lm.usable():
        time.sleep(0.5)
    check("llama-server comes up and answers with the network off", lm.usable(),
          lm.status().detail)
else:
    use_fake_model()

AX.focus(101)
if REAL_WHISPER:
    clip = str(TMP / "jfk.wav")
    shutil.copyfile(JFK, clip)
    dictate(wav=clip)
    said = notes.value.lower()
    check("whisper.cpp transcribes with the network off",
          "ask not what your country can do for you" in said, notes.value)
else:
    dictate("and so my fellow americans ask not what your country can do for you")
    check("(stand-in whisper) the transcript is typed", "ask not" in notes.value.lower(),
          notes.value)
check("it went into Notes by Accessibility, no clipboard", notes.value and not PASTES)
check("the clip is gone afterwards", not any((TMP / "data").rglob("pending.wav")))
check("the model ran on this Mac, or the rules stood in",
      "via" in LOG.getvalue() or "rules" in LOG.getvalue())
f.undo_last()
check("scratch that removes exactly what Halo typed", notes.value == "", repr(notes.value))
if REAL_LLM:
    local_llm.shutdown()

# --- B. Clean -> Contextualize -> Format -> Insert -> Undo -> Transform ------

print("\n=== B. Context, formatting, undo and transform ===")
use_fake_model()
config.LOCAL_BUDGET = 5.0
config.HISTORY_ENABLED = True           # on, to prove context never reaches it
MARKER = "KIWI-CONTEXT-MARKER-3141"
notes.value = f"Launch notes {MARKER} with Priyanka and Supabase.\n"
notes.sel = (len(notes.value), 0)
SEEN_BY_MODEL.clear()
dictate("um so number one call priyanka about the launch number two send jake "
        "twenty five dollars on march third")
typed = notes.value[len(f"Launch notes {MARKER} with Priyanka and Supabase.\n"):]
check("fillers gone, a spoken list becomes a list, no 'So:' heading",
      typed.startswith("1. ") and "\n2. " in typed, repr(typed))
check("a name from the screen is spelled the way the screen spells it", "Priyanka" in typed,
      repr(typed))
check("money and dates are written the way you would type them",
      "$25" in typed and "March 3" in typed, repr(typed))
check("the local model was asked, over loopback", len(SEEN_BY_MODEL) == 1)
check("...and was never shown the text around the cursor", MARKER not in repr(SEEN_BY_MODEL))
check("context is cleared when the dictation ends", f._context is None and f._pending is None)

notes.value += "\n"
notes.sel = (len(notes.value), 0)
before = notes.value
dictate("please ask jake to review the budget. then ship it on friday")
check("a second dictation on a fresh line reads as a new sentence",
      notes.value.startswith(before) and notes.value[len(before):].startswith("Please ask")
      and notes.value.endswith("on Friday."), repr(notes.value))
f.undo_last()
check("undo removes only that second insertion", notes.value == before, repr(notes.value))

# Transform: select the list, then Command Mode.
start = notes.value.index("1. ")
AX.set_selected_range("notes-body", start, len(notes.value) - start)
target = context.capture(AX, read_text=False)
with contextlib.redirect_stdout(LOG):
    r = f.command_mode("replace Jake with Sarah", target)
check("a rule transform runs with no model", r["ok"] and "Sarah" in notes.value
      and "Jake" not in notes.value, repr(notes.value))
after_rule = notes.value
start = notes.value.index("1. ")
AX.set_selected_range("notes-body", start, len(notes.value) - start)
with contextlib.redirect_stdout(LOG):
    r = f.command_mode("make this shorter", context.capture(AX, read_text=False))
check("a model transform runs on this Mac", r["ok"] and len(notes.value) < len(after_rule),
      r)
f.undo_last()
check("...and undo puts the selection back", notes.value == after_rule, repr(notes.value))

# --- C. The critical case: Notes, then Messages while Halo is processing ----

print("\n=== C. switch to Messages while Halo is processing a Notes dictation ===")
notes.value, notes.sel = "Draft: ", (7, 0)
messages.value, messages.sel = "see you soon", (12, 0)
CLIPBOARD.clear()
AX.focus(101)                                    # key down in Notes
dictate("the quarterly numbers look strong", during=lambda: AX.focus(202))
check("nothing is typed into Messages", messages.value == "see you soon", repr(messages.value))
check("...nor into Notes behind your back", notes.value == "Draft: ", repr(notes.value))
check("the text waits on the clipboard", CLIPBOARD and "quarterly numbers" in CLIPBOARD[-1])
check("the orb says why", any("App changed" in e for e in f.ui.events), f.ui.events)
kept = f.failed.current()
check("the dictation is kept for a retry", kept is not None and kept.stage == "insertion"
      and kept.reason == "you switched apps", kept)
check("...with its audio", kept is not None and kept.audio and Path(kept.audio).exists())
check("...and the app is told, for the menu bar", "failed:True" in f.ui.events)

AX.focus(101)                                    # back to Notes
with contextlib.redirect_stdout(LOG):
    r = f._op_failed_retry_insertion({})
check("Retry Insertion types it where you are now", r["ok"] and
      notes.value.startswith("Draft: ") and "quarterly numbers" in notes.value, r)
check("...and lets it go, audio and all", f.failed.current() is None
      and not (TMP / "data" / "recovery" / "failed.wav").exists())

# --- D. what was left behind --------------------------------------------------

print("\n=== D. nothing left the machine, nothing was kept that should not be ===")
check("zero connection attempts off this Mac", netguard.attempts == [], netguard.attempts)
log_text = LOG.getvalue()
check("the log never holds what was said", "quarterly" not in log_text
      and "Priyanka" not in log_text and "fellow" not in log_text)
check("...nor what was on screen", MARKER not in log_text)
leaked = [str(p) for p in (TMP / "data").rglob("*") if p.is_file()
          and MARKER.encode() in p.read_bytes()]
check("the text around the cursor is in no file, History included", not leaked, leaked)
check("(History was on, and kept the dictation itself)",
      bool(f.history.search("quarterly")))

server.shutdown()
shutil.rmtree(TMP, ignore_errors=True)
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
