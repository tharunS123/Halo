"""User settings, read from ~/.config/halo/settings.json.

Why this file exists: settings used to be environment variables only, and
launchd never sources a shell profile. A background install therefore ignored
HALO_HOTKEY, HALO_LANGUAGE, HALO_OVERLAY and HALO_PRIVACY entirely -- changing
the hotkey meant hand-editing the installed LaunchAgent plist.

Precedence is env > settings.json > built-in default, defined once in
ENV_OVERRIDES so the three layers cannot drift apart.

Read once at engine start, not hot-reloaded: every value here is bound at
startup (pynput binds the hotkey, transcribe picks the model, the overlay
client reads its enabled flag), so a live change would mean tearing down the
key listener mid-utterance. `halo config set` writes the file and offers a
restart. The three vocabulary files DO hot-reload -- that is unchanged.
"""
import json
import os
import threading

import paths


class SettingsFileError(Exception):
    """settings.json is on disk but is not readable as JSON."""

DEFAULTS = {
    "hotkey": "f9",
    "language": "en",
    "model": "small.en",
    # Absolute path, resolved once by `halo setup`. launchd hands the agent
    # PATH=/usr/bin:/bin:/usr/sbin:/sbin, so searching PATH at runtime misses
    # Homebrew in exactly the mode that matters.
    "whisper_bin": "",
    "whisper_threads": 8,
    "overlay": True,
    "privacy_default": False,
    "cleanup": {
        "enabled": True,
        # Free OpenRouter models, fastest and most faithful first. Kept here
        # rather than in code so a retired endpoint is a config edit.
        "models": [
            "nvidia/nemotron-3.5-lightning:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
        ],
        "total_budget_sec": 8,
        "ai_budget_sec": 25,
    },
}

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() in _TRUE


def _as_int(raw: str) -> int:
    return int(raw)


# key -> (env var, parser)
ENV_OVERRIDES = {
    "hotkey": ("HALO_HOTKEY", str),
    "language": ("HALO_LANGUAGE", str),
    "model": ("HALO_MODEL", str),
    "whisper_bin": ("HALO_WHISPER_BIN", str),
    "whisper_threads": ("HALO_THREADS", _as_int),
    "overlay": ("HALO_OVERLAY", _as_bool),
    "privacy_default": ("HALO_PRIVACY", _as_bool),
}


class Settings:
    """Dotted-key access over the JSON file, with env overrides on top."""

    def __init__(self, path=None):
        self.path = path or paths.SETTINGS_FILE
        self._lock = threading.Lock()
        self._mtime = None
        self._data: dict = {}
        self.load()

    def load(self) -> bool:
        """Re-read if the file changed. Same mtime-guard shape as Commands."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            if self._mtime == mtime and self._data:
                return True
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[settings] could not parse {self.path}: {e}; using defaults")
                return False
            if not isinstance(data, dict):
                print(f"[settings] {self.path} is not an object; using defaults")
                return False
            self._data = data
            self._mtime = mtime
        return True

    def get(self, key: str):
        """`get("hotkey")` or `get("cleanup.models")`. Env wins, then the file,
        then the built-in default."""
        env = ENV_OVERRIDES.get(key)
        if env:
            raw = os.environ.get(env[0])
            if raw not in (None, ""):
                try:
                    return env[1](raw)
                except (TypeError, ValueError):
                    print(f"[settings] ignoring bad {env[0]}={raw!r}")

        for source in (self._data, DEFAULTS):
            node, found = source, True
            for part in key.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    found = False
                    break
            if found and node is not None:
                return node
        return None

    def source_of(self, key: str) -> str:
        """Where the effective value came from -- for `halo config`."""
        env = ENV_OVERRIDES.get(key)
        if env and os.environ.get(env[0]) not in (None, ""):
            return f"env {env[0]}"
        node, found = self._data, True
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                found = False
                break
        return str(self.path) if found else "default"

    def set(self, key: str, value) -> None:
        """Write one key back to settings.json, creating it if needed."""
        # Re-read first: this instance may have been created before the file
        # existed (seeding runs after import), and writing a stale in-memory
        # copy would wipe everything the user or the seed put there.
        #
        # If the file is there but will not parse, refuse. load() returns False
        # and leaves _data empty, so the write below would replace the whole
        # file with the single key being set: one trailing comma left behind by
        # `halo config edit` would otherwise cost the user every other setting,
        # with a printed warning as the only clue.
        if not self.load() and self.path.exists():
            raise SettingsFileError(
                f"{self.path} exists but could not be parsed.\n"
                "        Refusing to write it -- that would discard every "
                "other setting.\n"
                "        Fix the JSON, then run this again.")
        with self._lock:
            data = dict(self._data)
            node = data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            self._data = data
            self._mtime = self.path.stat().st_mtime


# One shared instance; config.py reads it at import.
current = Settings()
