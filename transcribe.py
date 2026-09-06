"""Local transcription via whisper.cpp (no network)."""
import os
import re
import subprocess

import config


class TranscriptionError(RuntimeError):
    pass


def preflight() -> list[str]:
    """Return a list of problems with the whisper.cpp install (empty == OK)."""
    problems = []
    if not config.WHISPER_BIN.exists():
        problems.append(f"whisper-cli not found at {config.WHISPER_BIN}")
    elif not os.access(config.WHISPER_BIN, os.X_OK):
        problems.append(f"whisper-cli is not executable: {config.WHISPER_BIN}")
    if not config.WHISPER_MODEL.exists():
        problems.append(f"model not found at {config.WHISPER_MODEL}")
    return problems


# whisper.cpp emits these for non-speech audio; they are not real transcripts.
_NOISE_ONLY = re.compile(
    r"^\s*[\[(](blank_audio|silence|music|inaudible|no speech|sound|"
    r"applause|laughter|noise)[^\])]*[\])]\s*$",
    re.IGNORECASE,
)


def transcribe(wav_path: str) -> str:
    """Run whisper-cli on a 16 kHz WAV and return plain text."""
    cmd = [
        str(config.WHISPER_BIN),
        "-m", str(config.WHISPER_MODEL),
        "-f", wav_path,
        "-t", str(config.WHISPER_THREADS),
        "--no-timestamps",
        "--no-prints",
        "--language", "en",
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

    txt_path = wav_path + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            raw = f.read()
        os.unlink(txt_path)
    else:
        raw = proc.stdout

    return _clean(raw)


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
