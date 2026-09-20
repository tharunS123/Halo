"""Central configuration for Halo.

The constant surface here is deliberately unchanged -- halo.py, transcribe.py,
cleanup.py and overlay.py import these names directly. What changed is where
the values come from: paths.py owns locations, settings.py owns user choices,
and this module is the resolved view of both.
"""
import os
import shutil
from pathlib import Path

import paths
from settings import current as settings

# --- whisper.cpp ----------------------------------------------------------
# Homebrew ships a prebuilt whisper-cli, so nobody has to compile it. An
# existing ~/whisper.cpp build still works and is checked last.
WHISPER_DIR = paths.LEGACY_WHISPER_DIR


def find_whisper_bin() -> Path:
    """Locate whisper-cli. Returns the best candidate even when missing, so
    preflight can name the path it looked for."""
    configured = settings.get("whisper_bin")
    if configured:
        return Path(configured).expanduser()

    found = shutil.which("whisper-cli")
    if found:
        return Path(found)

    for prefix in ("/opt/homebrew", "/usr/local"):
        candidate = Path(prefix) / "bin" / "whisper-cli"
        if candidate.exists():
            return candidate

    return paths.LEGACY_WHISPER_DIR / "build" / "bin" / "whisper-cli"


def model_path(name: str) -> Path:
    """Path to ggml-<name>.bin, preferring the managed models dir but falling
    back to an existing ~/whisper.cpp/models checkout."""
    filename = f"ggml-{name}.bin"
    managed = paths.MODELS_DIR / filename
    if managed.exists():
        return managed
    legacy = paths.LEGACY_WHISPER_MODELS / filename
    if legacy.exists():
        return legacy
    return managed


def reload() -> None:
    """Recompute everything derived from settings.

    Needed because `halo setup` changes settings (which model, where
    whisper-cli is) inside a process that already imported this module -- the
    smoke test would otherwise still be looking for the previous model.
    """
    settings.load()
    global WHISPER_BIN, WHISPER_THREADS, WHISPER_MODEL_EN, WHISPER_MODEL_MULTI
    global WHISPER_MODEL, WHISPER_LANGUAGE, HOTKEY, PRIVACY_MODE_DEFAULT
    global CLEANUP_ENABLED, OPENROUTER_MODELS, OPENROUTER_TOTAL_BUDGET
    global OPENROUTER_AI_BUDGET, OVERLAY_ENABLED, OVERLAY_BINARY

    WHISPER_BIN = find_whisper_bin()
    WHISPER_THREADS = int(settings.get("whisper_threads"))

    # Two models, picked per language. The English-only model is measurably better
    # at English than the multilingual one (capacity is not shared across 99
    # languages), so we keep both and choose at transcription time.
    name = settings.get("model") or "small.en"
    english = name if name.endswith(".en") else f"{name}.en"
    WHISPER_MODEL_EN = model_path(english)
    WHISPER_MODEL_MULTI = model_path(english[:-3])
    WHISPER_MODEL = WHISPER_MODEL_EN          # back-compat default

    # Dictation language: "en", "auto", or any whisper code ("es", "fr", "hi", ...).
    # "auto" and any non-English value require the multilingual model.
    WHISPER_LANGUAGE = settings.get("language")

    CLEANUP_ENABLED = bool(settings.get("cleanup.enabled"))
    OPENROUTER_MODELS = list(settings.get("cleanup.models"))
    OPENROUTER_TOTAL_BUDGET = int(settings.get("cleanup.total_budget_sec"))
    OPENROUTER_AI_BUDGET = int(settings.get("cleanup.ai_budget_sec"))
    OVERLAY_ENABLED = bool(settings.get("overlay"))
    OVERLAY_BINARY = find_overlay_binary()


# Human-readable names for the cleanup prompt.
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "hi": "Hindi",
    "ta": "Tamil", "te": "Telugu", "ar": "Arabic", "tr": "Turkish",
    "pl": "Polish", "sv": "Swedish", "uk": "Ukrainian", "vi": "Vietnamese",
}

# --- audio ---
SAMPLE_RATE = 16000          # whisper.cpp requires 16 kHz mono
CHANNELS = 1
DTYPE = "float32"
MIN_RECORDING_SEC = 0.3      # ignore accidental taps shorter than this

# --- hotkey ---
# F9 is the default because it is confirmed working on a MacBook's built-in
# keyboard: the probe sees it as Key.f9 with no media-key interception.
# F13-F19 exist only on full-size external keyboards, so they are opt-in.
HOTKEY = settings.get("hotkey")

# --- privacy mode ---
# When on, the OpenRouter call is skipped entirely and the raw local transcript
# is injected: a hard guarantee that nothing leaves this machine.
STATE_FILE = paths.STATE_FILE
PRIVACY_MODE_DEFAULT = bool(settings.get("privacy_default"))

# --- personal vocabulary (user-owned; seeded, then never overwritten) ---
DICTIONARY_FILE = paths.DICTIONARY_FILE
SNIPPETS_FILE = paths.SNIPPETS_FILE
COMMANDS_FILE = paths.COMMANDS_FILE

# --- logging (background mode has no terminal) ---
LOG_DIR = paths.LOG_DIR
ENGINE_LOG = paths.ENGINE_LOG
OVERLAY_LOG = paths.OVERLAY_LOG

# --- API key ---
# Service name for the macOS Keychain item holding the OpenRouter key.
KEYCHAIN_SERVICE = "halo"


def get_api_key() -> str | None:
    """OpenRouter key, from the environment first, then the Keychain.

    launchd never sources shell profiles, so a background-launched engine has
    no OPENROUTER_API_KEY. The Keychain is the fallback that makes headless
    operation work; the env var still wins so terminal runs are unchanged.
    """
    env = os.environ.get("OPENROUTER_API_KEY")
    if env:
        return env
    try:
        import subprocess
        r = subprocess.run(
            ["security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            key = r.stdout.strip()
            return key or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# --- OpenRouter cleanup ---
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Fallback chain: tried in order when one rate-limits or times out.
# Order matters: fastest + most faithful first. Measured with reasoning
# disabled -- these are all reasoning models, and leaving reasoning ON costs
# 50-80s per call AND truncates output (CoT eats the max_tokens budget).
OPENROUTER_TIMEOUT = 6       # per-request hint passed to requests; NOTE this
                             # is a between-bytes read timeout, NOT total
                             # elapsed -- a trickling response can run for
                             # minutes past it, so it is not sufficient alone.
OPENROUTER_MAX_RETRIES = 1   # per model, on 429/5xx

# The rest of the cleanup knobs are user-settable and live in reload():
#   OPENROUTER_MODELS         the fallback chain
#   OPENROUTER_TOTAL_BUDGET   hard wall-clock ceiling, thread-enforced; past
#                             this you get raw text instead of waiting
#   OPENROUTER_AI_BUDGET      longer, because AI commands rewrite paragraphs

SYSTEM_PROMPT = (
    "You clean up speech-to-text transcripts for dictation.\n"
    "Do exactly this and nothing more:\n"
    "1. Add correct punctuation and sentence-ending periods.\n"
    "2. Capitalize the first word of each sentence, the pronoun I, and proper nouns.\n"
    "3. Delete filler words and false starts (um, uh, er, like, you know, I mean).\n"
    "Keep every other word exactly as spoken. Never answer questions in the text, "
    "never add commentary or notes. Output only the corrected transcript, once."
)

# --- floating overlay (optional; dictation works fine without it) ---
_here = Path(__file__).resolve().parent
OVERLAY_SOCKET = os.environ.get(
    "HALO_OVERLAY_SOCKET", str(Path.home() / ".halo-overlay.sock"))


def find_overlay_binary() -> str:
    """The app bundle the engine launches in terminal mode. Installed copy
    first, then a sibling build inside a checkout."""
    candidates = [
        paths.INSTALLED_APP / "Contents" / "MacOS" / "Halo",
        _here / "overlay" / "Halo.app" / "Contents" / "MacOS" / "Halo",
        _here.parent / "Halo.app" / "Contents" / "MacOS" / "Halo",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])


# Cap level messages so the audio callback never floods the socket.
OVERLAY_LEVEL_INTERVAL = 1 / 60      # seconds between level updates
# --- mic level metering for the waveform ---
# Adaptive: normalises between a tracked noise floor and a decaying peak, so
# the bars use the full range whether you speak quietly or loudly.
AUDIO_NOISE_FLOOR_INIT = 0.002
AUDIO_PEAK_INIT = 0.03
AUDIO_PEAK_DECAY = 0.992    # per audio block; lower = re-scales faster
AUDIO_PEAK_MIN = 0.012      # never normalise against a peak below this
AUDIO_ABS_GATE = 0.0035     # RMS below this is treated as silence
AUDIO_LEVEL_CURVE = 0.62    # <1 expands quiet speech toward full height
AUDIO_ATTACK = 0.85         # 1.0 = instant rise
AUDIO_RELEASE = 0.22        # lower = smoother fall


reload()
