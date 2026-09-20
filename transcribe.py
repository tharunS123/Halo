"""Local transcription via whisper.cpp (no network)."""
import os
import re
import subprocess

import config


class TranscriptionError(RuntimeError):
    pass


class TranscriptResult:
    def __init__(self, text: str, language: str, model: str,
                 confidence: float | None = None):
        self.text = text
        self.language = language      # whisper code actually used/detected
        self.model = model
        self.confidence = confidence  # only set when auto-detecting

    def __repr__(self):
        return f"<Transcript {self.language} {self.text[:40]!r}>"


def model_for(language: str):
    """Pick the model that fits the language.

    English-only models ignore the -l flag entirely, so asking one for Spanish
    silently produces English-ish nonsense. Route anything but plain English to
    the multilingual model, and fall back with a clear message if it is absent.
    """
    if language == "en" and config.WHISPER_MODEL_EN.exists():
        return config.WHISPER_MODEL_EN, None
    if config.WHISPER_MODEL_MULTI.exists():
        return config.WHISPER_MODEL_MULTI, None
    if config.WHISPER_MODEL_EN.exists():
        return config.WHISPER_MODEL_EN, (
            f"language {language!r} needs a multilingual model; "
            f"{config.WHISPER_MODEL_MULTI.name} is missing, falling back to "
            f"English-only. Download it with:\n"
            f"  halo model download small")
    return config.WHISPER_MODEL_EN, "no whisper model found"


def preflight() -> list[str]:
    """Return a list of problems with the whisper.cpp install (empty == OK)."""
    problems = []
    if not config.WHISPER_BIN.exists():
        problems.append(
            f"whisper-cli not found at {config.WHISPER_BIN}\n"
            f"    fix: brew install whisper.cpp && halo setup")
    elif not os.access(config.WHISPER_BIN, os.X_OK):
        problems.append(f"whisper-cli is not executable: {config.WHISPER_BIN}")
    if not (config.WHISPER_MODEL_EN.exists() or config.WHISPER_MODEL_MULTI.exists()):
        problems.append(
            f"no model found (looked for {config.WHISPER_MODEL_EN.name} and "
            f"{config.WHISPER_MODEL_MULTI.name} in {config.WHISPER_MODEL_EN.parent})\n"
            f"    fix: halo model download small.en")
    lang = config.WHISPER_LANGUAGE
    if lang != "en" and not config.WHISPER_MODEL_MULTI.exists():
        problems.append(
            f"language {lang!r} needs {config.WHISPER_MODEL_MULTI.name}\n"
            f"    fix: halo model download small")
    return problems


# whisper.cpp emits these for non-speech audio; they are not real transcripts.
_NOISE_ONLY = re.compile(
    r"^\s*[\[(](blank_audio|silence|music|inaudible|no speech|sound|"
    r"applause|laughter|noise)[^\])]*[\])]\s*$",
    re.IGNORECASE,
)


_DETECTED = re.compile(
    r"auto-detected language:\s*([a-z]{2,3})(?:\s*\(p\s*=\s*([\d.]+)\))?",
    re.IGNORECASE)


def transcribe(wav_path: str, language: str | None = None) -> TranscriptResult:
    """Run whisper-cli on a 16 kHz WAV.

    `language` is a whisper code or "auto"; defaults to config.WHISPER_LANGUAGE.
    """
    language = language or config.WHISPER_LANGUAGE
    model, warning = model_for(language)
    if warning:
        print(f"[transcribe] {warning}")
    # An English-only model cannot honour any other language.
    effective = "en" if model.name.endswith(".en.bin") else language

    cmd = [
        str(config.WHISPER_BIN),
        "-m", str(model),
        "-f", wav_path,
        "-t", str(config.WHISPER_THREADS),
        "--no-timestamps",
        "--language", effective,
        "--output-txt", "--output-file", wav_path,  # -> <wav_path>.txt
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise TranscriptionError("whisper-cli timed out after 120s")

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        raise TranscriptionError(
            f"whisper-cli exited {proc.returncode}: " + " | ".join(tail)
        )

    # whisper prints the detected language to stderr when -l auto is used.
    detected = effective
    confidence = None
    if effective == "auto":
        # whisper.cpp has printed this to stdout in some builds and stderr in
        # others; search both rather than depend on which.
        blob = (proc.stderr or "") + "\n" + (proc.stdout or "")
        m = _DETECTED.search(blob)
        detected = m.group(1).lower() if m else "en"
        if m and m.group(2):
            confidence = float(m.group(2))

    txt_path = wav_path + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            raw = f.read()
        os.unlink(txt_path)
    else:
        raw = proc.stdout

    return TranscriptResult(_clean(raw), detected, model.name, confidence)


def _clean(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or _NOISE_ONLY.match(line):
            continue
        # strip any residual [00:00:00.000 --> ...] prefix
        line = re.sub(r"^\[[\d:.\s\->]+\]\s*", "", line)
        if line:
            lines.append(line)
    return " ".join(lines).strip()
