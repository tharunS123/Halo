"""Privacy Mode: a hard local-only guarantee, toggled by voice.

When enabled, the pipeline never calls OpenRouter. The transcript is still
corrected by the local dictionary, but no text leaves the machine. State is
persisted so the guarantee survives a restart -- a privacy switch that silently
resets itself at login would be worse than no switch at all.
"""
import json
import threading

import config


class Privacy:
    def __init__(self, path=None):
        self.path = path or config.STATE_FILE
        self._lock = threading.Lock()
        self._enabled = config.PRIVACY_MODE_DEFAULT
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._enabled = bool(data.get("privacy_mode",
                                          config.PRIVACY_MODE_DEFAULT))
        except (OSError, ValueError):
            pass   # no state file yet, or unreadable: fall back to the default

    def _save(self):
        try:
            data = {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            data["privacy_mode"] = self._enabled
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"[privacy] could not persist state: {e}")

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set(self, on: bool) -> bool:
        with self._lock:
            self._enabled = bool(on)
            self._save()
            return self._enabled

    def toggle(self) -> bool:
        return self.set(not self.enabled)
