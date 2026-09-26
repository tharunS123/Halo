"""Writing styles: how Halo should sound in each app.

A style has two halves:

  rules         deterministic, apply with or without a model: whether to end
                with a full stop, lowercase the opening word, swap the last
                full stop for "!", avoid em dashes
  instructions  plain English for the cleanup model (Normal and Polished),
                which is the only thing that can make text shorter or more
                formal

Every app falls into a category, every category has a style, and any app
can override its category:

    Messages     -> Personal Messaging -> Casual
    Slack        -> Work Messaging     -> Concise
    Mail         -> Email              -> Professional
    Google Docs  -> Documents          -> Neutral
    Cursor       -> Coding / AI Prompts-> Coding

All of it lives in ~/.config/halo/styles.json -- custom styles, category
defaults and per-app assignments -- and none of it leaves the Mac. Custom
style instructions go to the local model only: OpenRouter keeps receiving
exactly what it received before styles existed.

Custom instructions are also read for a few phrasings that rules can honour
on their own ("never use em dashes", "no periods on short messages",
"lowercase"), so the promise holds even with no model installed.
"""
import json
import re
import threading
from dataclasses import dataclass, field, replace

import config
import paths

CATEGORIES = {
    "personal_messaging": "Personal Messaging",
    "work_messaging": "Work Messaging",
    "email": "Email",
    "documents": "Documents",
    "coding": "Coding / AI Prompts",
    "other": "Other",
}

DEFAULT_ASSIGNMENTS = {
    "personal_messaging": "casual",
    "work_messaging": "concise",
    "email": "professional",
    "documents": "neutral",
    "coding": "coding",
    "other": "neutral",
}


@dataclass(frozen=True)
class Rules:
    terminal: str | None = None     # always | multi_sentence | never | None (profile's)
    lowercase_start: bool = False
    exclaim: bool = False
    no_em_dash: bool = False


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    instructions: str
    rules: Rules = field(default_factory=Rules)
    builtin: bool = True
    base: str = ""


BUILTIN = {s.id: s for s in (
    Style("neutral", "Neutral", "Keep the speaker's own tone. Clear, plain sentences."),
    Style("casual", "Casual",
          "Relaxed and friendly, like a message to a friend. Contractions are fine.",
          Rules(terminal="multi_sentence")),
    Style("very_casual", "Very Casual",
          "Very relaxed texting style: lowercase is fine, keep punctuation minimal, "
          "no closing full stop.",
          Rules(terminal="never", lowercase_start=True)),
    Style("professional", "Professional",
          "Clear, polite and professional. Complete sentences, no slang.",
          Rules(terminal="always")),
    Style("formal", "Formal",
          "Formal and precise. No contractions, no slang, complete sentences.",
          Rules(terminal="always")),
    Style("concise", "Concise",
          "As short as possible while keeping every point. Cut filler, hedging and "
          "repetition.",
          Rules(terminal="multi_sentence")),
    Style("excited", "Excited",
          "Upbeat and enthusiastic. An exclamation mark where it fits, never more "
          "than one in a row.",
          Rules(exclaim=True)),
    Style("coding", "Coding / AI Prompt",
          "Precise technical writing for code, a terminal or an AI prompt. Keep "
          "identifiers, file names, flags and commands exactly as given.",
          Rules()),
)}


# --- which category an app is in --------------------------------------------

_WORK_CHAT_BUNDLES = {"com.tinyspeck.slackmacgap", "com.microsoft.teams",
                      "com.microsoft.teams2", "us.zoom.xos", "com.webex.meetingmanager"}
_WORK_CHAT_HOSTS = ("slack.com", "teams.microsoft.com", "chat.google.com")
_AI_BUNDLES = {"com.openai.chat", "com.anthropic.claudefordesktop"}
_AI_HOSTS = ("chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com",
             "perplexity.ai")


def _host_is(host: str, suffixes) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)


def category_for(ctx) -> str:
    """The style category of the app a Context describes ("other" without one)."""
    if ctx is None:
        return "other"
    bundle = getattr(ctx, "bundle_id", "") or ""
    host = getattr(ctx, "host", "") or ""
    cat = getattr(ctx, "category", "unknown")
    if bundle in _AI_BUNDLES or _host_is(host, _AI_HOSTS):
        return "coding"
    if cat in ("ide", "terminal"):
        return "coding"
    if cat == "chat":
        if bundle in _WORK_CHAT_BUNDLES or _host_is(host, _WORK_CHAT_HOSTS):
            return "work_messaging"
        return "personal_messaging"
    return {"email": "email", "document": "documents"}.get(cat, "other")


# --- custom-instruction directives --------------------------------------------

_NEG = r"(?:never|don'?t|do\s+not|no|avoid|without)"


def directives(text: str) -> Rules:
    """Deterministic rules hidden in free-text instructions. Deliberately a
    short, literal list: guessing wrong here would change text the user never
    asked to change."""
    t = (text or "").lower()
    terminal = None
    if re.search(_NEG + r"[^.]{0,40}(?:period|full stop)s?[^.]{0,40}short", t) or \
            re.search(r"short[^.]{0,40}" + _NEG + r"[^.]{0,20}(?:period|full stop)", t):
        terminal = "multi_sentence"
    elif re.search(_NEG + r"[^.]{0,30}(?:period|full stop)", t):
        terminal = "never"
    return Rules(
        terminal=terminal,
        lowercase_start=bool(re.search(r"\b(?:all\s+)?lower\s*-?\s*case\b", t))
        and not re.search(_NEG + r"[^.]{0,20}lower\s*-?\s*case", t),
        exclaim=False,
        no_em_dash=bool(re.search(_NEG + r"[^.]{0,20}em[\s-]*dash", t)),
    )


def _merge(a: Rules, b: Rules) -> Rules:
    return Rules(terminal=b.terminal or a.terminal,
                 lowercase_start=a.lowercase_start or b.lowercase_start,
                 exclaim=a.exclaim or b.exclaim,
                 no_em_dash=a.no_em_dash or b.no_em_dash)


# --- the store ------------------------------------------------------------------

class Styles:
    """styles.json, reloaded on mtime like every other config file."""

    def __init__(self, path=None):
        self.path = path or paths.STYLES_FILE
        self._lock = threading.Lock()
        self._mtime = None
        self.custom: dict[str, Style] = {}
        self.categories: dict[str, str] = dict(DEFAULT_ASSIGNMENTS)
        self.apps: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return
        with self._lock:
            if mtime == self._mtime:
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[styles] could not parse {self.path.name}: {type(e).__name__}")
                return
            custom = {}
            for item in data.get("custom", []) or []:
                if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
                    continue
                base = BUILTIN.get(item.get("base", ""), BUILTIN["neutral"])
                text = str(item.get("instructions", ""))
                custom[str(item["id"])] = Style(
                    str(item["id"]), str(item["name"]), text,
                    _merge(base.rules, directives(text)), builtin=False, base=base.id)
            self.custom = custom
            cats = dict(DEFAULT_ASSIGNMENTS)
            cats.update({k: str(v) for k, v in (data.get("categories") or {}).items()
                         if k in CATEGORIES})
            self.categories = cats
            self.apps = {str(k): str(v) for k, v in (data.get("apps") or {}).items()}
            self._mtime = mtime

    def get(self, style_id: str) -> Style:
        return self.custom.get(style_id) or BUILTIN.get(style_id) or BUILTIN["neutral"]

    def all(self) -> list[Style]:
        return list(BUILTIN.values()) + list(self.custom.values())

    def for_context(self, ctx) -> tuple[Style, str]:
        """(style, why) for the app a Context describes. App assignments win
        over the category's, a website's over its browser's."""
        self.load()
        if ctx is not None:
            host = getattr(ctx, "host", "") or ""
            bundle = getattr(ctx, "bundle_id", "") or ""
            if host and f"host:{host}" in self.apps:
                return self.get(self.apps[f"host:{host}"]), f"assigned to {host}"
            if bundle and bundle in self.apps:
                return self.get(self.apps[bundle]), "assigned to this app"
        cat = category_for(ctx)
        return self.get(self.categories.get(cat, "neutral")), CATEGORIES[cat]


# --- applying a style ------------------------------------------------------------

def adjust_profile(profile, style: Style | None):
    """A formatting Profile with the style's closing-punctuation rule on top."""
    if style is None or style.rules.terminal is None or profile.terminal == "keep":
        return profile
    return replace(profile, terminal=style.rules.terminal)


def finish(text: str, style: Style | None, structured: bool = False) -> str:
    """The style's rules that act on finished text."""
    if style is None or not text:
        return text
    r = style.rules
    if r.no_em_dash:
        # A dash between words becomes a comma; around a number range, a hyphen.
        text = re.sub(r"(?<=\d)\s*[—–]\s*(?=\d)", "-", text)
        text = re.sub(r"\s*—\s*", ", ", text)
        text = re.sub(r"\s+--\s+", ", ", text)
        text = re.sub(r",\s*,", ",", text)
    if r.exclaim and not structured:
        stripped = text.rstrip()
        if stripped.endswith(".") and not stripped.endswith(".."):
            text = stripped[:-1] + "!" + text[len(stripped):]
    if r.lowercase_start:
        m = re.match(r"(\s*)([A-Z])([a-z'’]*)\b", text)
        if m and m.group(2) + m.group(3) not in ("I", "I'm", "I'll", "I've", "I'd"):
            word = m.group(2) + m.group(3)
            from backtrack import is_common
            if is_common(word):
                text = m.group(1) + m.group(2).lower() + text[m.end(2):]
    if r.terminal == "never" and not structured:
        stripped = text.rstrip()
        if stripped.endswith(".") and not stripped.endswith(".."):
            text = stripped[:-1] + text[len(stripped):]
    return text


def instructions(style: Style | None, mode: str) -> str:
    """The model's share of the style. In Normal mode the model may not
    reword, so the style is framed as a tie-breaker, not a licence."""
    if style is None or not config.STYLES_ENABLED:
        return ""
    if mode == "polished":
        return f"Write it in this style: {style.instructions}"
    return ("Where it needs no rewording, lean toward this style: "
            f"{style.instructions}")
