"""Languages Halo knows about, and what each one supports.

One table, so adding a language is a data change: whisper already speaks 99,
and the rest of Halo asks this module what applies rather than hard-coding
"is it English". Today the English-only stages -- self-correction cues, number
and date writing, list cues, question marks -- say english_rules=True; every
other language gets punctuation, casing, the dictionary and the model pass.
A later ruleset for Spanish would add a flag here and a module beside itn.py,
and nothing that calls rules_for() would change.

Regional variants change formatting, not recognition: en-GB writes dates
day-first ("5 January 2027") where en-US writes "January 5, 2027".

The recently-used list is state, not a setting: it lives in state.json next
to Privacy Mode, and the quick switcher and menu bar read it.
"""
import json
import threading

import config
import paths

LANGUAGES = {
    "en": {"name": "English", "regions": ["en-US", "en-GB", "en-AU", "en-CA", "en-IN"],
           "english_rules": True},
    "es": {"name": "Spanish", "regions": ["es-ES", "es-MX", "es-US"]},
    "fr": {"name": "French", "regions": ["fr-FR", "fr-CA"]},
    "de": {"name": "German", "regions": ["de-DE", "de-AT", "de-CH"]},
    "it": {"name": "Italian", "regions": []},
    "pt": {"name": "Portuguese", "regions": ["pt-BR", "pt-PT"]},
    "nl": {"name": "Dutch", "regions": []},
    "ru": {"name": "Russian", "regions": []},
    "ja": {"name": "Japanese", "regions": []},
    "ko": {"name": "Korean", "regions": []},
    "zh": {"name": "Chinese", "regions": ["zh-CN", "zh-TW"]},
    "hi": {"name": "Hindi", "regions": []},
    "ta": {"name": "Tamil", "regions": []},
    "te": {"name": "Telugu", "regions": []},
    "ar": {"name": "Arabic", "regions": []},
    "tr": {"name": "Turkish", "regions": []},
    "pl": {"name": "Polish", "regions": []},
    "sv": {"name": "Swedish", "regions": []},
    "uk": {"name": "Ukrainian", "regions": []},
    "vi": {"name": "Vietnamese", "regions": []},
}

# Spoken names for the voice switcher, including a few whisper spellings.
_SPOKEN = {info["name"].lower(): code for code, info in LANGUAGES.items()}
_SPOKEN.update({"auto": "auto", "automatic": "auto", "auto detect": "auto",
                "detect": "auto", "mandarin": "zh", "castilian": "es",
                "portugese": "pt", "farsi": None})


def name(code: str) -> str:
    if code == "auto":
        return "Detect automatically"
    return LANGUAGES.get(base(code), {}).get("name", code)


def base(code: str) -> str:
    """"en-GB" -> "en"."""
    return (code or "en").split("-")[0].lower()


def english_rules(code: str) -> bool:
    return bool(LANGUAGES.get(base(code), {}).get("english_rules"))


def region(code: str) -> str:
    """The regional variant in effect for `code`, e.g. "en-GB"."""
    b = base(code)
    chosen = config.LANGUAGE_REGIONS.get(b, "")
    return chosen if chosen in LANGUAGES.get(b, {}).get("regions", []) else ""


def day_first(code: str) -> bool:
    """Dates as "5 January" rather than "January 5"."""
    return region(code) in ("en-GB", "en-AU", "en-IN")


def from_spoken(phrase: str) -> str | None:
    """"Spanish" -> "es"; "auto detect" -> "auto"; unknown -> None."""
    p = " ".join(phrase.lower().replace("-", " ").split())
    return _SPOKEN.get(p)


# --- recently used ------------------------------------------------------------

_lock = threading.Lock()


def recent() -> list[str]:
    try:
        data = json.loads(paths.STATE_FILE.read_text(encoding="utf-8"))
        return [c for c in data.get("languages_recent", []) if isinstance(c, str)][:5]
    except (OSError, ValueError):
        return []


def remember(code: str) -> None:
    """Move `code` to the front of the recently-used list in state.json."""
    if not code or code == "auto":
        return
    with _lock:
        try:
            data = json.loads(paths.STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        items = [c for c in data.get("languages_recent", []) if c != code]
        data["languages_recent"] = [code] + items[:4]
        try:
            paths.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = paths.STATE_FILE.with_name(".state.json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(paths.STATE_FILE)
        except OSError:
            pass
