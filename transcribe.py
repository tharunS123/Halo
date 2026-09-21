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


# whisper's initial prompt is capped at n_text_ctx/2 tokens (224 for these
# models). Well under that in characters, because a prompt that overflows is
# silently truncated mid-word and then primes on a fragment.
PROMPT_MAX_CHARS = 700


def build_prompt(vocabulary: str = "", previous: str = "") -> str:
    """Prime the decoder the way Apple Dictation primes on your contacts.

    whisper conditions the first decode window on this text, so a name or
    product it has never heard (a surname, "whisper.cpp", "launchd") becomes far
    more likely than the ordinary English word it otherwise collapses to. This
    is the single largest accuracy win available without a bigger model,
    because the failure it fixes -- proper nouns and jargon -- is exactly what
    a 487MB model is worst at.

    Two sources, in priority order:
      1. your dictionary terms, as a comma-separated list
      2. the tail of the previous utterance, which carries topic and style
         across a pause the way a single long recording would

    `previous` goes last so that if the cap bites, it is the disposable half
    that gets cut.
    """
    parts = []
    vocabulary = (vocabulary or "").strip()
    previous = " ".join((previous or "").split())
    if vocabulary:
        parts.append(vocabulary)
    if previous:
        parts.append(previous)
    prompt = " ".join(parts).strip()
    if len(prompt) <= PROMPT_MAX_CHARS:
        return prompt
    # Cut on a word boundary: half a token primes on nonsense.
    cut = prompt[:PROMPT_MAX_CHARS]
    space = cut.rfind(" ")
    return cut[:space] if space > 0 else cut


def transcribe(wav_path: str, language: str | None = None,
               vocabulary: str = "", previous: str = "") -> TranscriptResult:
    """Run whisper-cli on a 16 kHz WAV.

    `language` is a whisper code or "auto"; defaults to config.WHISPER_LANGUAGE.
    `vocabulary` and `previous` prime the decoder -- see build_prompt().
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
        # Pinned rather than inherited. These happen to match whisper.cpp's
        # current defaults, but they are the knobs that decide accuracy, and an
        # upstream default change should not silently retune dictation.
        "--beam-size", str(config.WHISPER_BEAM_SIZE),
        "--best-of", str(config.WHISPER_BEST_OF),
        "--entropy-thold", str(config.WHISPER_ENTROPY_THOLD),
        "--no-speech-thold", str(config.WHISPER_NO_SPEECH_THOLD),
        "--output-txt", "--output-file", wav_path,  # -> <wav_path>.txt
    ]
    if config.WHISPER_SUPPRESS_NST:
        # Stops the decoder emitting [BLANK_AUDIO], (music), (typing) and the
        # rest. _clean() already drops those, but suppressing them at decode
        # time means the beam spends its probability mass on words instead.
        cmd.append("--suppress-nst")

    prompt = build_prompt(vocabulary, previous) if config.WHISPER_PROMPT else ""
    if prompt:
        cmd += ["--prompt", prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as e:
        raise TranscriptionError("whisper-cli timed out after 120s") from e

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

    text = _clean(raw)
    if prompt and _is_prompt_echo(text, prompt):
        # Priming has one failure mode: on a clip with no usable speech the
        # decoder can fall back to regurgitating its own initial prompt, which
        # would paste your entire vocabulary list at the cursor. Treat it as
        # silence, which is what it actually was.
        print("[transcribe] discarded a prompt echo")
        text = ""

    return TranscriptResult(text, detected, model.name, confidence)


def _is_prompt_echo(text: str, prompt: str) -> bool:
    """True if the transcript is just the initial prompt coming back."""
    if not text:
        return False
    norm = lambda s: re.sub(r"[^\w\s]", "", s.lower()).split()
    out, primed = norm(text), set(norm(prompt))
    if not out or not primed:
        return False
    return sum(w in primed for w in out) / len(out) > 0.9


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
