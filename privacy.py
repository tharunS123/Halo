"""Privacy Mode: a hard local-only guarantee, toggled by voice.

When enabled, the pipeline never calls OpenRouter. The transcript is still
corrected and punctuated locally, but no text leaves the machine. State is
persisted so the guarantee survives a restart -- a privacy switch that silently
resets itself at login would be worse than no switch at all.

The state file re-reads on mtime, the same way dictionary.json and
settings.json do. That is what lets the menu bar item flip Privacy Mode: the
overlay is a separate process and cannot reach into the engine, so it writes
the file and the engine notices. Without the reload the two would disagree,
and a privacy indicator that lies is worse than no indicator.
"""
import json
import threading

import config


class Privacy:
    def __init__(self, path=None):
        self.path = path or config.STATE_FILE
        self._lock = threading.Lock()
        self._enabled = config.PRIVACY_MODE_DEFAULT
        self._mtime = None
        self._load()

    def _load(self):
        try:
            self._mtime = self.path.stat().st_mtime
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._enabled = bool(data.get("privacy_mode",
                                          config.PRIVACY_MODE_DEFAULT))
        except (OSError, ValueError):
            pass   # no state file yet, or unreadable: fall back to the default

    def _reload_if_changed(self):
        """Pick up a write from another process (the menu bar item)."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return
        if mtime != self._mtime:
            self._load()

    def _save(self):
        try:
            data = {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            data["privacy_mode"] = self._enabled
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            # Adopt our own write, so the reload check does not immediately
            # re-read a file we just authored.
            self._mtime = self.path.stat().st_mtime
        except OSError as e:
            print(f"[privacy] could not persist state: {e}")

    @property
    def enabled(self) -> bool:
        with self._lock:
            self._reload_if_changed()
            return self._enabled

    def set(self, on: bool) -> bool:
        with self._lock:
            self._enabled = bool(on)
            self._save()
            return self._enabled

    def toggle(self) -> bool:
        return self.set(not self.enabled)
