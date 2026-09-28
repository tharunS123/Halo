"""Privacy Mode: private dictation, toggled by voice or the menu bar.

Since 0.4 nothing Halo does leaves this Mac in any mode (netguard.py enforces
that), so Privacy Mode no longer means "no network" -- that is simply how Halo
works. It now means nothing about a dictation is kept or read beyond the words
themselves:

  - no History entry, text or audio, whatever the History setting says
  - no text read around the cursor; only the app's kind, for formatting
  - no vocabulary learning (which re-reads what you typed afterwards)

The words are still cleaned up and typed exactly as usual. State is persisted
so the guarantee survives a restart -- a privacy switch that silently resets
itself at login would be worse than no switch at all.

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
