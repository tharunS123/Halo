"""Central configuration for WisprFlowClone."""
import os
from pathlib import Path

# --- whisper.cpp ---
WHISPER_DIR = Path.home() / "whisper.cpp"
WHISPER_BIN = WHISPER_DIR / "build" / "bin" / "whisper-cli"
WHISPER_MODEL = WHISPER_DIR / "models" / "ggml-small.en.bin"
WHISPER_THREADS = 8

# --- audio ---
SAMPLE_RATE = 16000          # whisper.cpp requires 16 kHz mono
CHANNELS = 1
DTYPE = "float32"
MIN_RECORDING_SEC = 0.3      # ignore accidental taps shorter than this

# --- hotkey ---
# F13 avoids the "use F1-F12 as standard function keys" ambiguity entirely.
# Set to "f9" if you prefer, but see README notes.
HOTKEY = os.environ.get("FLOW_HOTKEY", "f9")

# --- logging (background mode has no terminal) ---
LOG_DIR = Path.home() / "Library" / "Logs" / "WisprFlowClone"
ENGINE_LOG = LOG_DIR / "engine.log"
OVERLAY_LOG = LOG_DIR / "overlay.log"

# --- API key ---
# Service name for the macOS Keychain item holding the OpenRouter key.
KEYCHAIN_SERVICE = "wisprflowclone"


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
# Verified present and $0/token on OpenRouter as of this build.
# Fallback chain: tried in order when one rate-limits or times out.
# Order matters: fastest + most faithful first. Measured with reasoning
# disabled -- these are all reasoning models, and leaving reasoning ON costs
# 50-80s per call AND truncates output (CoT eats the max_tokens budget).
OPENROUTER_MODELS = [
    "nvidia/nemotron-3.5-lightning:free",      # ~0.8s, preserves wording best
    "nvidia/nemotron-3-super-120b-a12b:free",  # ~0.5s, over-edits slightly
    "nvidia/nemotron-3-ultra-550b-a55b:free",  # slowest, last resort
]
OPENROUTER_TIMEOUT = 6       # per-request hint passed to requests; NOTE this
                             # is a between-bytes read timeout, NOT total
                             # elapsed -- a trickling response can run for
                             # minutes past it, so it is not sufficient alone.
OPENROUTER_TOTAL_BUDGET = 8  # HARD wall-clock ceiling, thread-enforced.
                             # Past this you get raw text instead of waiting.
OPENROUTER_MAX_RETRIES = 1   # per model, on 429/5xx

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
OVERLAY_ENABLED = os.environ.get("FLOW_OVERLAY", "1") not in ("0", "false", "no")
OVERLAY_SOCKET = os.environ.get(
    "FLOW_OVERLAY_SOCKET", str(Path.home() / ".wisprflowclone-overlay.sock"))
OVERLAY_BINARY = str(_here / "overlay" / "WisprFlow.app" / "Contents" / "MacOS" / "WisprFlow")
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
