"""The engine's control socket, for the Settings window and the menu bar.

Files remain the contract for configuration: settings, vocabulary, styles
and transforms are JSON the window edits and the engine re-reads. This socket
is only for things that need the engine itself -- to type text, to run
whisper or the model, or to say how it is:

    {"op": "health"}
    {"op": "history.reinsert",            "id": "..."}
    {"op": "history.retry_cleanup",       "id": "..."}
    {"op": "history.retry_transcription", "id": "..."}
    {"op": "transform", "id": "shorten"}   (on the current selection)

One JSON object per line in, one per line out. The socket is created 0600 in
Halo's own data directory, so only processes running as you can reach it.
Replies never contain dictated text except where the op is asked to return
it (a retry returns its result so the window can show it).
"""
import json
import os
import socket
import threading

import paths


class ControlServer:
    def __init__(self, handlers: dict, path=None):
        self.handlers = handlers
        self.path = str(path or paths.ENGINE_SOCKET)
        self._sock: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        try:
            paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old = os.umask(0o177)          # the socket is born 0600
            try:
                s.bind(self.path)
            finally:
                os.umask(old)
            os.chmod(self.path, 0o600)
            s.listen(4)
            self._sock = s
        except OSError as e:
            print(f"[control] socket unavailable: {type(e).__name__}")
            return False
        threading.Thread(target=self._accept, daemon=True, name="control").start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(120)
            buf = b""
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except OSError:
                    return
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    reply = self.handle(line)
                    try:
                        conn.sendall((json.dumps(reply) + "\n").encode())
                    except OSError:
                        return

    def handle(self, line: bytes) -> dict:
        try:
            req = json.loads(line.decode("utf-8"))
            op = req.get("op", "")
        except (ValueError, UnicodeDecodeError, AttributeError):
            return {"ok": False, "error": "bad request"}
        fn = self.handlers.get(op)
        if fn is None:
            return {"ok": False, "error": f"unknown op {op!r}"}
        try:
            out = fn(req) or {}
            return {"ok": True, **out} if "ok" not in out else out
        except Exception as e:                  # never let a request kill the engine
            return {"ok": False, "error": type(e).__name__}


def request(req: dict, path=None, timeout: float = 60) -> dict:
    """Client side, for tests and `halo` subcommands."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    with s:
        s.connect(str(path or paths.ENGINE_SOCKET))
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.split(b"\n", 1)[0] or b"{}")
