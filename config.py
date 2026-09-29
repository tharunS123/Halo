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
# The downloaded app ships whisper-cli in Contents/Helpers; Homebrew ships a
# prebuilt one. An existing ~/whisper.cpp build still works and is checked last.
WHISPER_DIR = paths.LEGACY_WHISPER_DIR


def find_whisper_bin() -> Path:
    """Locate whisper-cli. Returns the best candidate even when missing, so
    preflight can name the path it looked for."""
    configured = settings.get("whisper_bin")
    bundled = paths.HELPERS_DIR / "whisper-cli" if paths.HELPERS_DIR else None
    if configured:
        # A path `halo setup` saved for a Homebrew install that has since been
        # removed must not strand the downloaded app, which has its own.
        if bundled and bundled.exists() and not Path(configured).expanduser().exists():
            return bundled
        return Path(configured).expanduser()
    if bundled and bundled.exists():
        return bundled

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


def _num(key: str, default, cast, low=None, high=None):
    """Read a numeric setting without ever letting it kill the engine.

    reload() runs at module import, so an unparseable value here is not a bad
    setting -- it is an engine that exits before it can report why, and a
    supervisor that restart-loops on it. settings.json is hand-editable and
    the Settings window is not the only writer, so "many" in a number field
    has to degrade to the default rather than raise.
    """
    raw = settings.get(key)
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        print(f"[config] {key}={raw!r} is not a number; using {default}")
        return default
    if (low is not None and value < low) or (high is not None and value > high):
        print(f"[config] {key}={value} is out of range; using {default}")
        return default
    return value


def reload() -> None:
    """Recompute everything derived from settings.

    Needed because `halo setup` changes settings (which model, where
    whisper-cli is) inside a process that already imported this module -- the
    smoke test would otherwise still be looking for the previous model.
    """
    settings.load()
    global WHISPER_BIN, WHISPER_THREADS, WHISPER_MODEL_EN, WHISPER_MODEL_MULTI
    global WHISPER_MODEL, WHISPER_LANGUAGE, HOTKEY, PRIVACY_MODE_DEFAULT
    global OVERLAY_ENABLED, OVERLAY_BINARY
    global ACTIVATION, MAX_RECORDING_SEC, MENU_BAR
    global WHISPER_BEAM_SIZE, WHISPER_BEST_OF, WHISPER_ENTROPY_THOLD
    global WHISPER_NO_SPEECH_THOLD, WHISPER_SUPPRESS_NST, WHISPER_PROMPT
    global SPOKEN_PUNCTUATION, STRIP_FILLERS, TERMINAL_PUNCTUATION
    global SELF_CORRECTION, SMART_FORMATTING, CHAT_PERIOD
    global CLEANUP_MODE, CLEANUP_PROVIDER, LOCAL_BACKEND, LOCAL_MODEL
    global LOCAL_SERVER_BIN, LOCAL_ENDPOINT, LOCAL_ENDPOINT_MODEL
    global LOCAL_BUDGET, LOCAL_POLISHED_BUDGET, LOCAL_IDLE_UNLOAD_MIN
    global CONTEXT_ENABLED, CONTEXT_APP_OVERRIDES
    global MIC_DEVICE, SOUNDS, LANGUAGES_ENABLED, LANGUAGE_REGIONS, DEVELOPER_MODE
    global STYLES_ENABLED, COMMAND_MODE_ENABLED, COMMAND_TRIGGER, COMMAND_HOTKEY
    global HISTORY_ENABLED, HISTORY_RETENTION, HISTORY_KEEP_AUDIO
    global HISTORY_AUDIO_RETENTION, LEARNING_ENABLED, INSERTION_METHOD
    global INSERTION_APP_OVERRIDES, DEBUG_LOG_CONTENT

    WHISPER_BIN = find_whisper_bin()
    WHISPER_THREADS = _num("whisper_threads", 8, int, low=1, high=64)

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

    OVERLAY_ENABLED = bool(settings.get("overlay"))
    OVERLAY_BINARY = find_overlay_binary()

    # These two were declared global here but never assigned, so `halo config
    # set hotkey f12` left config.HOTKEY on the old value inside the running
    # process. Harmless today only because the CLI tells you to restart and
    # nothing reads it in between -- but reload() says it recomputes
    # everything, and a caller is entitled to believe that.
    HOTKEY = settings.get("hotkey")
    PRIVACY_MODE_DEFAULT = bool(settings.get("privacy_default"))

    # "hold" or "toggle". Anything else would leave the engine with no way to
    # start recording at all, so an unrecognised value falls back rather than
    # failing -- this string can arrive from a hand-edited JSON file.
    ACTIVATION = str(settings.get("activation") or "hold").lower()
    if ACTIVATION not in ("hold", "toggle"):
        print(f"[config] unknown activation {ACTIVATION!r}; using 'hold'")
        ACTIVATION = "hold"
    # Upper bound as well as lower: a toggle that "stops automatically" after
    # an hour has not stopped automatically.
    MAX_RECORDING_SEC = _num("max_recording_sec", 120, int, low=5, high=3600)
    MENU_BAR = bool(settings.get("menu_bar"))

    WHISPER_BEAM_SIZE = _num("whisper.beam_size", 5, int, low=1, high=16)
    WHISPER_BEST_OF = _num("whisper.best_of", 5, int, low=1, high=16)
    WHISPER_ENTROPY_THOLD = _num("whisper.entropy_thold", 2.4, float, low=0)
    WHISPER_NO_SPEECH_THOLD = _num("whisper.no_speech_thold", 0.6, float,
                                   low=0, high=1)
    WHISPER_SUPPRESS_NST = bool(settings.get("whisper.suppress_nst"))
    WHISPER_PROMPT = bool(settings.get("whisper.prompt"))

    SPOKEN_PUNCTUATION = bool(settings.get("dictation.spoken_punctuation"))
    STRIP_FILLERS = bool(settings.get("dictation.strip_fillers"))
    TERMINAL_PUNCTUATION = bool(settings.get("dictation.terminal_punctuation"))
    SELF_CORRECTION = bool(settings.get("dictation.self_correction"))
    SMART_FORMATTING = bool(settings.get("dictation.smart_formatting"))
    CHAT_PERIOD = bool(settings.get("dictation.chat_period"))

    # Same shape as activation: these strings arrive from a hand-editable
    # file, and an unknown value must degrade to the default rather than
    # leave dictation with no pipeline at all.
    CLEANUP_MODE = _choice("cleanup.mode", CLEANUP_MODES, "normal")
    CLEANUP_PROVIDER = _choice("cleanup.provider", CLEANUP_PROVIDERS, "auto",
                               legacy=_LEGACY_PROVIDERS)
    LOCAL_BACKEND = _choice("cleanup.local.backend", ("llama.cpp", "endpoint"),
                            "llama.cpp")
    LOCAL_MODEL = str(settings.get("cleanup.local.model") or "qwen2.5-1.5b")
    LOCAL_SERVER_BIN = str(settings.get("cleanup.local.server_bin") or "")
    LOCAL_ENDPOINT = str(settings.get("cleanup.local.endpoint") or "")
    LOCAL_ENDPOINT_MODEL = str(settings.get("cleanup.local.endpoint_model") or "")
    LOCAL_BUDGET = _num("cleanup.local.budget_ms", 1500, int,
                        low=100, high=30000) / 1000
    LOCAL_POLISHED_BUDGET = _num("cleanup.local.polished_budget_ms", 3500, int,
                                 low=100, high=60000) / 1000
    LOCAL_IDLE_UNLOAD_MIN = _num("cleanup.local.idle_unload_min", 30, int,
                                 low=0, high=24 * 60)

    MIC_DEVICE = str(settings.get("microphone.device") or "")
    SOUNDS = bool(settings.get("sounds"))
    enabled = settings.get("languages.enabled")
    LANGUAGES_ENABLED = [str(x) for x in enabled] if isinstance(enabled, list) and enabled \
        else ["en"]
    regions = settings.get("languages.region")
    LANGUAGE_REGIONS = {str(k): str(v) for k, v in regions.items()} \
        if isinstance(regions, dict) else {}
    DEVELOPER_MODE = _choice("developer_mode", ("auto", "on", "off"), "auto")
    STYLES_ENABLED = bool(settings.get("styles.enabled"))
    COMMAND_MODE_ENABLED = bool(settings.get("command_mode.enabled"))
    COMMAND_TRIGGER = str(settings.get("command_mode.trigger") or "shift").lower()
    COMMAND_HOTKEY = str(settings.get("command_mode.hotkey") or "").lower()
    HISTORY_ENABLED = bool(settings.get("history.enabled"))
    HISTORY_RETENTION = _choice("history.retention", RETENTIONS, "7d")
    HISTORY_KEEP_AUDIO = bool(settings.get("history.keep_audio"))
    HISTORY_AUDIO_RETENTION = _choice("history.audio_retention", RETENTIONS, "24h")
    LEARNING_ENABLED = bool(settings.get("learning.enabled"))
    INSERTION_METHOD = _choice("insertion.method", ("auto", "ax", "paste", "type"), "auto")
    ov = settings.get("insertion.app_overrides")
    INSERTION_APP_OVERRIDES = {str(k): str(v) for k, v in ov.items()} \
        if isinstance(ov, dict) else {}
    DEBUG_LOG_CONTENT = bool(settings.get("debug.log_content"))

    CONTEXT_ENABLED = bool(settings.get("context.enabled"))
    overrides = settings.get("context.app_overrides")
    CONTEXT_APP_OVERRIDES = ({str(k): str(v) for k, v in overrides.items()}
                             if isinstance(overrides, dict) else {})


CLEANUP_MODES = ("off", "verbatim", "light", "normal", "polished")
# auto and local mean the same since 0.4 -- the model on this Mac when one is
# ready, the rules otherwise -- and both stay valid so a settings file written
# by either spelling keeps working. none is rules only.
CLEANUP_PROVIDERS = ("auto", "local", "none")
# Values an older Halo wrote. "openrouter" sent text to a cloud model; there is
# no such provider any more, and the closest honest reading is the model on
# this Mac, or the rules without one.
_LEGACY_PROVIDERS = {"openrouter": "auto"}
RETENTIONS = ("never", "1h", "24h", "7d", "30d", "forever")


def _choice(key: str, allowed, default: str, legacy: dict | None = None) -> str:
    value = str(settings.get(key) or default).strip().lower()
    if legacy and value in legacy:
        return legacy[value]
    if value not in allowed:
        print(f"[config] unknown {key} {value!r}; using {default!r}")
        return default
    return value


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
# Private dictation: nothing about it is kept or read beyond the words
# themselves -- no History, no text around the cursor, no vocabulary
# learning. See privacy.py.
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

# --- the OpenRouter key an older Halo may have stored ---
# Halo 0.3 could send transcripts to OpenRouter and kept the key in the
# Keychain under this service. Nothing reads it any more; `halo doctor`
# mentions a leftover one and `halo key delete` / `halo uninstall` remove it.
KEYCHAIN_SERVICE = "halo"


def legacy_key_stored() -> bool:
    """Whether an old OpenRouter key is still in the Keychain. Never reads
    the secret itself (no -w)."""
    try:
        import subprocess
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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

# --- clip conditioning before whisper (see Recorder.condition) -----------
# Scale a quiet clip up to this peak. whisper is trained on normalised audio.
AUDIO_NORMALIZE_TARGET = 0.85
# ...but only when there is signal to scale. Below this a clip is room noise
# or a dead microphone, and amplifying it manufactures confident nonsense.
# Deliberately above halo.py's 0.005 silence check, so a missing Microphone
# grant is still reported as silence rather than normalised into hiss.
AUDIO_NORMALIZE_MIN_PEAK = 0.02
# Silence welded to each end. Push-to-talk puts the first phoneme in the very
# first mel frame, where whisper routinely clips it.
AUDIO_PAD_SEC = 0.25


reload()
