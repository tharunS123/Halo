"""Client for the SwiftUI overlay.

Design rule: the overlay is decoration, dictation is the product. Every method
here swallows its errors. If the overlay is missing, crashed, wedged, or slow,
this class degrades to a no-op and dictation continues untouched.
"""
import os
import socket
import subprocess
import time

import config


class Overlay:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and config.OVERLAY_ENABLED
        self.path = config.OVERLAY_SOCKET
        # When the overlay app is our PARENT (headless/background mode) we must
        # only connect -- never spawn it, and never kill it on exit.
        self.connect_only = os.environ.get("FLOW_OVERLAY_CHILD") == "1"
        self._sock: socket.socket | None = None
        self._spawned: subprocess.Popen | None = None
        self._last_level_at = 0.0
        self._warned = False

    # --- plumbing -------------------------------------------------------
    def _warn_once(self, msg: str):
        if not self._warned:
            print(f"[overlay] disabled: {msg}")
            self._warned = True

    def _connect(self) -> bool:
        if self._sock is not None:
            return True
        if not os.path.exists(self.path):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            # Short timeout: a wedged overlay must never stall the pipeline.
            s.settimeout(0.15)
            s.connect(self.path)
            self._sock = s
            return True
        except OSError:
            self._sock = None
            return False

    def _send(self, line: str) -> bool:
        if not self.enabled:
            return False
        if not self._connect():
            return False
        try:
            self._sock.sendall((line + "\n").encode())
            return True
        except OSError:
            # Drop the connection; the next call will try to reconnect.
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            return False

    # --- lifecycle ------------------------------------------------------
    def start_app(self, wait: float = 2.5) -> bool:
        """Launch the overlay app if it isn't already listening."""
        if not self.enabled:
            return False
        if self._connect():
            return True

        if self.connect_only:
            # Parent owns the overlay; it may still be binding its socket.
            deadline = time.time() + wait
            while time.time() < deadline:
                if self._connect():
                    return True
                time.sleep(0.08)
            self._warn_once("overlay parent never accepted a connection")
            return False

        binary = config.OVERLAY_BINARY
        if not os.path.exists(binary):
            self._warn_once(f"overlay app not built at {binary}\n"
                            f"           build it with: overlay/build_app.sh")
            self.enabled = False
            return False
        try:
            self._spawned = subprocess.Popen(
                [binary],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            self._warn_once(f"could not launch overlay ({e})")
            self.enabled = False
            return False

        deadline = time.time() + wait
        while time.time() < deadline:
            if self._connect():
                return True
            time.sleep(0.08)
        self._warn_once("overlay launched but never accepted a connection")
        return False

    def close(self):
        """Hide, then shut down the overlay if we were the one who started it."""
        self.hide()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._spawned is not None and not self.connect_only:
            try:
                self._spawned.terminate()
                self._spawned.wait(timeout=1.5)
            except Exception:
                try:
                    self._spawned.kill()
                except Exception:
                    pass
            self._spawned = None

    # --- states ---------------------------------------------------------
    def listening(self):  self._send("listening")
    def processing(self): self._send("processing")
    def done(self):       self._send("done")
    def hide(self):       self._send("hide")

    def privacy(self, on: bool):
        """Persistent lock indicator while Privacy Mode is on."""
        self._send(f"privacy {1 if on else 0}")

    def flash(self, message: str):
        """Brief neutral message (not an error)."""
        safe = message.replace("\n", " ")[:40]
        self._send(f"flash {safe}")

    def error(self, message: str):
        """Show a short failure message in the pill -- the only way the user
        finds out about a problem when there is no terminal."""
        safe = message.replace("\n", " ")[:40]
        self._send(f"error {safe}")

    def level(self, value: float):
        """Push a mic level (0..1). Throttled -- called from the audio thread."""
        now = time.time()
        if now - self._last_level_at < config.OVERLAY_LEVEL_INTERVAL:
            return
        self._last_level_at = now
        self._send(f"level {value:.3f}")


class NullOverlay:
    """Stand-in when the overlay is disabled: every call is a no-op."""
    enabled = False

    def start_app(self, wait: float = 0) -> bool: return False
    def close(self): pass
    def listening(self): pass
    def processing(self): pass
    def done(self): pass
    def hide(self): pass
    def privacy(self, on: bool):
        """Persistent lock indicator while Privacy Mode is on."""
        self._send(f"privacy {1 if on else 0}")

    def flash(self, message: str):
        """Brief neutral message (not an error)."""
        safe = message.replace("\n", " ")[:40]
        self._send(f"flash {safe}")

    def error(self, message: str): pass
    def privacy(self, on: bool): pass
    def flash(self, message: str): pass
    def level(self, value: float): pass
