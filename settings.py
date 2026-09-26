"""User settings, read from ~/.config/halo/settings.json.

Why this file exists: settings used to be environment variables only, and
launchd never sources a shell profile. A background install therefore ignored
HALO_HOTKEY, HALO_LANGUAGE, HALO_OVERLAY and HALO_PRIVACY entirely -- changing
the hotkey meant hand-editing the installed LaunchAgent plist.

Precedence is env > settings.json > built-in default, defined once in
ENV_OVERRIDES so the three layers cannot drift apart.

Reloaded on mtime while Halo runs, because the Settings window made a restart
after every slider unacceptable. The one value that cannot simply be re-read
is the hotkey -- pynput binds it at startup -- so `Halo._watch_settings`
rebinds only when dictation is idle, never mid-utterance. Everything else is
read from config per utterance and applies to the next thing you say.
"""
import json
import os
import threading

import paths


class SettingsFileError(Exception):
    """settings.json is on disk but is not readable as JSON."""

DEFAULTS = {
    "hotkey": "f9",
    # "hold"   -- press and hold to talk, release to send (the original)
    # "toggle" -- one press starts, the next press sends
    #
    # Hold is the default because it cannot strand a hot microphone: let go of
    # the key and recording is over. Toggle exists for long dictation and for
    # anyone for whom holding a key is uncomfortable, and pairs with
    # `max_recording_sec` so a forgotten toggle still ends by itself.
    "activation": "hold",
    "max_recording_sec": 120,
    "language": "en",
    "model": "small.en",
    # Absolute path, resolved once by `halo setup`. launchd hands the agent
    # PATH=/usr/bin:/bin:/usr/sbin:/sbin, so searching PATH at runtime misses
    # Homebrew in exactly the mode that matters.
    "whisper_bin": "",
    "whisper_threads": 8,
    "overlay": True,
    # Opt-in menu bar item. Off by default: the whole point of Halo is that
    # the key is the interface, and `halo settings` reaches the window without
    # spending a slot in the user's menu bar.
    "menu_bar": False,
    "orb": {
        # 0.6 .. 1.6 -- multiplies the 84pt bubble. Stored as a number rather
        # than small/medium/large so the slider is continuous.
        "scale": 1.0,
        # bottom | top | bottom-left | bottom-right | top-left | top-right
        "position": "bottom",
        # Distance from that edge, in points.
        "inset": 140,
        # Hide the orb while it is only thinking, so the screen is quiet
        # unless you are actually speaking.
        "show_while_processing": True,
    },
    "privacy_default": False,
    # Everything here is local-only and runs with no key and no network.
    "dictation": {
        # Spoken punctuation: "comma", "new line", "question mark".
        "spoken_punctuation": True,
        # Drop standalone um/uh/er.
        "strip_fillers": True,
        # Add a final period when the utterance ends without one.
        "terminal_punctuation": True,
        # "Thursday -- actually Friday" types "Friday". Normal and Polished
        # modes only; see backtrack.py for why it is not a replace table.
        "self_correction": True,
        # Numbers, dates, times, money, phone numbers, emails, URLs and
        # spoken lists. Normal and Polished modes only.
        "smart_formatting": True,
        # Chat apps get no final period on a single short sentence, because
        # that is how people actually write there. True keeps the period.
        "chat_period": False,
    },
    "whisper": {
        # Pinned copies of whisper.cpp's decode defaults -- see transcribe.py.
        "beam_size": 5,
        "best_of": 5,
        "entropy_thold": 2.4,
        "no_speech_thold": 0.6,
        "suppress_nst": True,
        # Prime the decoder with your vocabulary and the previous utterance.
        "prompt": True,
    },
    "cleanup": {
        # Consent to send transcript text to OpenRouter. Before 0.4.0 this was
        # read and then ignored; the provider choice below now enforces it.
        "enabled": True,
        # off | verbatim | light | normal | polished -- see pipeline.py.
        "mode": "normal",
        # auto | local | openrouter | none. Auto prefers the model on this
        # Mac, then OpenRouter (key + enabled + Privacy Mode off), then rules.
        "provider": "auto",
        "local": {
            # llama.cpp (Halo runs llama-server itself) or endpoint (any
            # OpenAI-compatible server on this Mac: Ollama, LM Studio,
            # mlx_lm.server). Endpoints off the loopback interface are refused.
            "backend": "llama.cpp",
            "model": "qwen2.5-1.5b",
            "server_bin": "",
            "endpoint": "",
            "endpoint_model": "",
            # Hard wall-clock ceilings. Past them you get the rule-based text.
            "budget_ms": 1500,
            "polished_budget_ms": 3500,
            # Stop llama-server after this long without dictation, to give
            # back its ~1.5GB. 0 keeps it loaded.
            "idle_unload_min": 30,
        },
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
    "context": {
        # Read the focused app and a little text around the cursor, in
        # memory only, to pick names, casing and formatting. Never reads a
        # password or secure field, never logs, never persists. See context.py.
        "enabled": True,
        # bundle id -> chat | email | document | terminal | ide | browser
        "app_overrides": {},
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
    "activation": ("HALO_ACTIVATION", str),
    "cleanup.mode": ("HALO_CLEANUP_MODE", str),
    "context.enabled": ("HALO_CONTEXT", _as_bool),
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
            # Write-then-rename. write_text() truncates in place, and this file
            # now has readers in two processes -- the engine polls it on mtime
            # and the Settings window reads it on open -- either of which could
            # otherwise catch it empty or half-written. os.replace is atomic
            # within a filesystem, and the temp file is in the same directory
            # to guarantee that.
            tmp = self.path.with_name(f".{self.path.name}.tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
            self._data = data
            self._mtime = self.path.stat().st_mtime


# One shared instance; config.py reads it at import.
current = Settings()
