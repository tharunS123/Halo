"""Text models for cleanup: the one on this Mac, and OpenRouter.

pipeline.py asks `select()` for a model and gets one back only if it can
answer RIGHT NOW. Everything else -- not installed, still loading, crashed,
too slow -- means "no model", and the rule-based text is typed instead. The
rule that shapes this whole file: a dictation is never lost to, or held up
by, a language model.

Why llama.cpp's llama-server, run as a child process:

  - Same shape as whisper.cpp: a Homebrew bottle with Metal on Apple Silicon,
    and no Python build dependency. MLX and llama-cpp-python both need wheels
    for whatever Python Homebrew ships this month.
  - Isolation. A corrupt model, a Metal fault or an out-of-memory kill takes
    down the child, not the engine holding your hotkey. The engine notices on
    the next dictation, types the rule-based text, and restarts it.
  - It speaks the OpenAI chat API, and so do mlx_lm.server, Ollama and LM
    Studio. The `endpoint` backend is that same client pointed at a server
    you run yourself, which is how MLX is supported without Halo depending on
    it. Core ML is not offered: there is no maintained LLM runtime for it that
    builds with the Command Line Tools alone.

The server listens on 127.0.0.1 only, on a fresh port each launch, behind a
random API key read from a 0600 file (never argv, so never `ps`). Its own
logging is off: a server that logs requests would write your dictation to
disk, which Halo promises not to do.
"""
import collections
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

import cleanup
import config
import models
import paths


class ModelError(Exception):
    """The model could not produce an answer in time. Never fatal."""


@dataclass
class Status:
    state: str          # not_installed | stopped | loading | ready | failed
    detail: str = ""


def _write_status(backend: str, model: str, status: Status) -> None:
    """For the Settings window and `halo doctor`. Never contains user text."""
    try:
        paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = paths.LOCAL_MODEL_STATUS.with_name(".local_model.json.tmp")
        tmp.write_text(json.dumps({
            "backend": backend, "model": model, "state": status.state,
            "detail": status.detail, "updated": int(time.time()),
        }, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, paths.LOCAL_MODEL_STATUS)
    except OSError:
        pass


def read_status() -> dict:
    try:
        return json.loads(paths.LOCAL_MODEL_STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class TextModel:
    """Anything that can clean text inside a deadline."""
    kind = "local"          # local | openrouter
    remote = False

    @property
    def name(self) -> str:
        return self.kind

    def status(self) -> Status:
        return Status("ready")

    def usable(self) -> bool:
        return True

    def prewarm(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def chat(self, messages: list[dict], budget: float, max_tokens: int) -> str:
        raise NotImplementedError


class _ChatServer(TextModel):
    """An OpenAI-compatible /chat/completions endpoint on this machine."""

    def _base(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _extra(self) -> dict:
        return {}

    def _model_name(self) -> str:
        return "halo-cleanup"

    def _on_connection_error(self) -> None:
        pass

    def chat(self, messages, budget, max_tokens):
        body = {"model": self._model_name(), "messages": messages,
                "temperature": 0, "max_tokens": max_tokens, "stream": False,
                **self._extra()}
        try:
            resp = cleanup._post_bounded(
                self._headers(), body, budget,
                url=self._base() + "/chat/completions", read_timeout=budget)
        except cleanup._HardTimeout as e:
            raise ModelError(f"no answer within {budget:.1f}s") from e
        except requests.ConnectionError as e:
            self._on_connection_error()
            raise ModelError("server not reachable") from e
        except requests.RequestException as e:
            raise ModelError(type(e).__name__) from e
        if resp.status_code == 503:
            raise ModelError("model still loading")
        if resp.status_code != 200:
            raise ModelError(f"HTTP {resp.status_code}")
        try:
            choice = resp.json()["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ModelError("malformed response") from e
        if finish == "length":
            # Cut off mid-sentence: typing it would silently drop your words.
            raise ModelError("answer truncated")
        if not content or not content.strip():
            raise ModelError("empty answer")
        return content


# --- llama.cpp -------------------------------------------------------------

def find_server_binary() -> Path | None:
    configured = config.LOCAL_SERVER_BIN
    if configured:
        p = Path(configured).expanduser()
        return p if p.exists() else None
    found = shutil.which("llama-server")
    if found:
        return Path(found)
    # launchd hands the agent a bare PATH, so look where Homebrew puts it.
    for prefix in ("/opt/homebrew", "/usr/local"):
        p = Path(prefix) / "bin" / "llama-server"
        if p.exists():
            return p
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# Restart backoff after a crash, then give up until something changes.
_BACKOFF = (1.0, 2.0, 4.0)
_CRASH_WINDOW = 600
_LOAD_TIMEOUT = 120


class LlamaServer(_ChatServer):
    """Runs and supervises llama-server for the configured GGUF model."""
    kind = "local"

    def __init__(self):
        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None
        self._key: str | None = None
        self._model: str | None = None
        self._status = Status("stopped")
        self._crashes: collections.deque = collections.deque()
        self._retry_at = 0.0
        self._starting = False
        self._last_used = time.time()
        self._idle_thread: threading.Thread | None = None

    @property
    def name(self) -> str:
        return f"llama.cpp {self._model or config.LOCAL_MODEL}"

    # --- state -----------------------------------------------------------
    def _set(self, state: str, detail: str = "") -> None:
        self._status = Status(state, detail)
        _write_status("llama.cpp", self._model or config.LOCAL_MODEL, self._status)

    def status(self) -> Status:
        with self._lock:
            self._check_alive()
            return self._status

    def _check_alive(self) -> None:
        """Notice a server that died since we last looked."""
        if self._proc is None or self._proc.poll() is None:
            return
        code = self._proc.returncode
        was = self._status.state
        self._forget_process()
        now = time.time()
        self._crashes.append(now)
        while self._crashes and now - self._crashes[0] > _CRASH_WINDOW:
            self._crashes.popleft()
        n = len(self._crashes)
        what = "failed to load the model" if was == "loading" else "stopped unexpectedly"
        if n >= 3 or (was == "loading" and n >= 2):
            # A model that will not load will not load on the fourth try
            # either. Stay down until the model or binary changes.
            self._set("failed", f"llama-server {what} (exit {code}), {n} times "
                                "in 10 minutes. Try `halo model local verify`.")
        else:
            self._retry_at = now + _BACKOFF[min(n, len(_BACKOFF)) - 1]
            self._set("stopped", f"llama-server {what} (exit {code}); restarting")

    def _forget_process(self) -> None:
        self._proc = None
        self._port = None
        self._key = None
        for p in (paths.LOCAL_SERVER_PID, paths.LOCAL_SERVER_KEY):
            try:
                p.unlink()
            except OSError:
                pass

    def usable(self) -> bool:
        with self._lock:
            self._check_alive()
            self._maybe_restart_for_settings()
            if self._status.state == "loading" and self._proc is not None:
                # The load may have finished since the loader last polled.
                if self._healthy(0.15):
                    self._set("ready")
            return self._status.state == "ready"

    def _maybe_restart_for_settings(self) -> None:
        if self._proc is not None and self._model != config.LOCAL_MODEL:
            self._stop_locked("model changed in Settings")
            self._crashes.clear()
        if self._status.state == "failed" and self._model != config.LOCAL_MODEL:
            self._crashes.clear()
            self._set("stopped")

    # --- lifecycle -------------------------------------------------------
    def prewarm(self) -> None:
        """Start loading if it is not running. Returns at once."""
        with self._lock:
            self._last_used = time.time()
            self._check_alive()
            self._maybe_restart_for_settings()
            if self._proc is not None or self._starting:
                return
            if self._status.state == "failed":
                return
            if time.time() < self._retry_at:
                return
            self._starting = True
        threading.Thread(target=self._start, daemon=True,
                         name="llama-server-start").start()

    def _start(self) -> None:
        try:
            self._launch()
        finally:
            with self._lock:
                self._starting = False

    def _launch(self) -> None:
        with self._lock:
            self._model = config.LOCAL_MODEL
            model = models.llm_path(self._model)
            if model is None:
                spec = models.LLM_CATALOG.get(self._model)
                if spec and (paths.MODELS_DIR / spec["file"]).exists():
                    self._set("failed", "the model file is incomplete or damaged; "
                                        "run `halo model local install --force`")
                else:
                    self._set("not_installed",
                              f"run `halo model local install {self._model}`")
                return
            binary = find_server_binary()
            if binary is None:
                self._set("failed", "llama-server not found; brew install llama.cpp")
                return
            reap_stale()
            port = _free_port()
            key = secrets.token_urlsafe(24)
            try:
                paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
                fd = os.open(paths.LOCAL_SERVER_KEY,
                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(key + "\n")
            except OSError as e:
                self._set("failed", f"could not write the server key: {e}")
                return
            args = [
                str(binary), "-m", str(model),
                "--host", "127.0.0.1", "--port", str(port),
                "--api-key-file", str(paths.LOCAL_SERVER_KEY),
                "-a", "halo-cleanup",
                "-ngl", "99",          # every layer on the GPU (Metal)
                "-c", "4096",          # a long dictation plus the prompt
                "-np", "1",            # one dictation at a time
                "--no-webui",
                # Logging off. Measured with llama.cpp 0.4.1: at default
                # verbosity a request logs only slot timings, never the
                # prompt. But that is a default, not a promise, and a debug
                # setting must never be able to put dictation in a file.
                "--log-disable",
            ]
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as e:
                self._set("failed", f"could not start llama-server: {e}")
                return
            self._proc, self._port, self._key = proc, port, key
            # From here the process is what prewarm() checks. Leaving
            # _starting set through the health wait below meant a stop()
            # followed at once by prewarm() was silently ignored.
            self._starting = False
            try:
                paths.LOCAL_SERVER_PID.write_text(str(proc.pid), encoding="utf-8")
            except OSError:
                pass
            self._set("loading")
            self._ensure_idle_watch()

        # Wait for the load outside the lock, so a dictation that arrives
        # meanwhile can ask usable(), hear "no", and carry on without it.
        deadline = time.time() + _LOAD_TIMEOUT
        while time.time() < deadline:
            with self._lock:
                if self._proc is not proc:
                    return                      # stopped or replaced meanwhile
                if proc.poll() is not None:
                    self._check_alive()
                    return
                if self._status.state == "ready":
                    return
                if self._healthy(1.0):
                    self._set("ready")
                    return
            time.sleep(0.25)
        with self._lock:
            if self._proc is proc:
                self._stop_locked("")
                self._set("failed", f"model did not load within {_LOAD_TIMEOUT}s")

    def _healthy(self, timeout: float) -> bool:
        if self._port is None:
            return False
        try:
            r = requests.get(f"http://127.0.0.1:{self._port}/health", timeout=timeout)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def _ensure_idle_watch(self) -> None:
        if self._idle_thread is not None:
            return

        def watch():
            while True:
                time.sleep(30)
                limit = config.LOCAL_IDLE_UNLOAD_MIN * 60
                with self._lock:
                    if limit and self._proc is not None and \
                            time.time() - self._last_used > limit:
                        self._stop_locked(
                            f"unloaded after {config.LOCAL_IDLE_UNLOAD_MIN} idle minutes; "
                            "it reloads when you next dictate")

        self._idle_thread = threading.Thread(target=watch, daemon=True,
                                             name="llama-server-idle")
        self._idle_thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked("")

    def _stop_locked(self, detail: str) -> None:
        proc = self._proc
        self._forget_process()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._status.state != "not_installed":
            self._set("stopped", detail)

    # --- requests --------------------------------------------------------
    def _base(self) -> str:
        return f"http://127.0.0.1:{self._port}/v1"

    def _headers(self) -> dict:
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {self._key}"}

    def _extra(self) -> dict:
        # Reuse the processed system prompt across dictations: most of the
        # prompt is identical every time, and re-reading it is most of the
        # latency on a short utterance.
        return {"cache_prompt": True}

    def _on_connection_error(self) -> None:
        with self._lock:
            self._check_alive()

    def chat(self, messages, budget, max_tokens):
        with self._lock:
            if self._status.state != "ready" or self._port is None:
                raise ModelError(f"local model {self._status.state}")
            self._last_used = time.time()
        return super().chat(messages, budget, max_tokens)


def reap_stale() -> None:
    """Kill a llama-server left behind by an engine that died hard.

    It runs in its own session so a crash of ours does not take it down, which
    also means nothing else will. The pid file is how the next engine finds
    it; the command-name check is what stops a recycled pid from costing some
    unrelated process its life.
    """
    try:
        pid = int(paths.LOCAL_SERVER_PID.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    if "llama-server" in out:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        paths.LOCAL_SERVER_PID.unlink()
    except OSError:
        pass


# --- someone else's server on this Mac --------------------------------------

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Endpoint(_ChatServer):
    """Ollama, LM Studio, mlx_lm.server -- anything OpenAI-compatible that is
    already running on this machine. Addresses off this machine are refused:
    'local' has to mean local, or Privacy Mode would be a lie."""
    kind = "local"

    def __init__(self, url: str, model: str):
        self.url = url
        self.model = model
        self._checked_at = 0.0
        self._ok = False
        self._status = Status("stopped")

    @property
    def name(self) -> str:
        return f"endpoint {self.model or '(default model)'}"

    def _base(self) -> str:
        u = self.url.rstrip("/")
        return u if urlparse(u).path not in ("", "/") else u + "/v1"

    def _model_name(self) -> str:
        return self.model or "default"

    def _set(self, status: Status) -> None:
        if status != self._status:
            self._status = status
            _write_status("endpoint", self.model, status)

    def status(self) -> Status:
        return self._status

    def usable(self) -> bool:
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in _LOOPBACK:
            self._set(Status("failed", "endpoint is not on this Mac; refused"))
            return False
        now = time.time()
        if now - self._checked_at > 15:
            self._checked_at = now
            try:
                r = requests.get(self._base() + "/models", timeout=0.3)
                self._ok = r.status_code < 500
            except requests.RequestException:
                self._ok = False
            self._set(Status("ready") if self._ok else
                      Status("stopped", "no server answering at " + self._base()))
        return self._ok

    def _on_connection_error(self) -> None:
        self._ok = False
        self._checked_at = 0.0


class OpenRouter(TextModel):
    """Marker for the remote provider. pipeline.py calls cleanup.clean() for
    it, which carries its own fallback chain, budget and output checks."""
    kind = "openrouter"
    remote = True

    @property
    def name(self) -> str:
        return "OpenRouter"


# --- selection ---------------------------------------------------------------

_server: LlamaServer | None = None
_endpoint: Endpoint | None = None
_openrouter = OpenRouter()


def local_model() -> TextModel | None:
    """The configured local model object, whether or not it is running."""
    global _server, _endpoint
    if config.LOCAL_BACKEND == "endpoint":
        if not config.LOCAL_ENDPOINT:
            return None
        if _endpoint is None or (_endpoint.url, _endpoint.model) != (
                config.LOCAL_ENDPOINT, config.LOCAL_ENDPOINT_MODEL):
            _endpoint = Endpoint(config.LOCAL_ENDPOINT, config.LOCAL_ENDPOINT_MODEL)
        return _endpoint
    if _server is None:
        _server = LlamaServer()
    return _server


def local_installed() -> bool:
    if config.LOCAL_BACKEND == "endpoint":
        return bool(config.LOCAL_ENDPOINT)
    return models.llm_path(config.LOCAL_MODEL) is not None


def wants_model(mode: str) -> bool:
    return mode in ("normal", "polished") and config.CLEANUP_PROVIDER != "none"


def select(mode: str, *, privacy: bool) -> tuple[TextModel | None, str]:
    """The model to use for this utterance, or (None, why not).

    Auto prefers this Mac. When a local model is installed but not ready,
    auto does NOT quietly fall through to OpenRouter: someone who installed
    a local model chose to keep text here, and a model that is still loading
    is not a reason to overrule that.
    """
    if not wants_model(mode):
        return None, "rules only"
    provider = config.CLEANUP_PROVIDER
    if provider in ("auto", "local") and local_installed():
        model = local_model()
        if model is not None and model.usable():
            return model, ""
        if model is not None:
            model.prewarm()
            st = model.status()
            return None, f"local model {st.state}" + (f": {st.detail}" if st.detail else "")
    if provider == "local":
        return None, "no local model installed"
    if privacy:
        return None, "Privacy Mode is on"
    if not config.CLEANUP_ENABLED:
        return None, "OpenRouter is off in Settings"
    if not config.get_api_key():
        return None, "no OpenRouter key"
    return _openrouter, ""


def prewarm(mode: str) -> None:
    """Called at key-down: load the model while you are still talking."""
    if wants_model(mode) and config.CLEANUP_PROVIDER in ("auto", "local") \
            and local_installed():
        model = local_model()
        if model is not None:
            model.prewarm()


def shutdown() -> None:
    if _server is not None:
        _server.stop()
