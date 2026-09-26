"""Structure and house style: lists, email layout, typography, casing, and
fitting the text to where the cursor is.

The same sentence should not arrive the same way everywhere. "sounds good"
in Messages wants no full stop; an email wants its greeting on its own line; a
terminal wants straight quotes and nothing "helpful". A Profile captures those
differences per kind of app, and context.py decides which kind you are in.
Without context (Context Awareness off, or an app Halo cannot read) everything
falls back to the "unknown" profile, which is exactly Halo's 0.3 behaviour.

Everything here is deterministic and runs in well under a millisecond. It
keys on explicit cues rather than guessing structure: "number one ... number
two" is a list, a run of short sentences is not. The cleanup model can do the
guessing in Polished mode; rules that guess wrong in Normal mode are worse
than rules that do nothing.
"""
import re
from dataclasses import dataclass

from backtrack import is_common


@dataclass(frozen=True)
class Profile:
    name: str
    # always | multi_sentence (chat: skip the full stop on one short line)
    # | keep (never add or remove one -- terminals)
    terminal: str = "always"
    lists: str = "cues"            # off | cues | all (ordinal lists too)
    email_layout: bool = False     # greeting and sign-off on their own lines
    smart_typography: bool = False # curly quotes, em dashes
    dev_terms: str = "safe"        # off | safe | all
    insertion: bool = True         # adapt to the text around the cursor


PROFILES = {
    "chat": Profile("chat", terminal="multi_sentence"),
    "email": Profile("email", email_layout=True, smart_typography=True),
    "document": Profile("document", lists="all", smart_typography=True),
    # A terminal may be a shell or an AI CLI taking prose, and Halo cannot
    # tell which. So: add nothing, remove nothing, straight ASCII throughout.
    "terminal": Profile("terminal", terminal="keep", lists="off",
                        dev_terms="off"),
    "ide": Profile("ide", dev_terms="all"),
    "browser": Profile("browser"),
    "unknown": Profile("unknown"),
}

# Hosts where developer vocabulary is the likelier reading of "python".
DEV_HOSTS = ("github.com", "gitlab.com", "stackoverflow.com", "bitbucket.org",
             "developer.apple.com", "docs.python.org", "npmjs.com", "vercel.com")


def profile_for(ctx) -> Profile:
    """The profile for a captured Context, or the neutral one without it."""
    if ctx is None:
        return PROFILES["unknown"]
    base = PROFILES.get(getattr(ctx, "category", "unknown"), PROFILES["unknown"])
    host = getattr(ctx, "host", "") or ""
    if host and any(host == h or host.endswith("." + h) for h in DEV_HOSTS):
        return Profile(base.name, base.terminal, base.lists, base.email_layout,
                       base.smart_typography, "all", base.insertion)
    return base


# --- repeats and stutters (Light and up) ------------------------------------

# Words people stumble on and repeat without meaning to. A closed list on
# purpose: "that that" ("I know that that is true"), "had had", "very very",
# "no no no" and "bye bye" are all things people mean.
_STUTTER_PRONE = {
    "i", "we", "you", "he", "she", "they", "it", "the", "a", "an", "to", "of",
    "in", "on", "at", "for", "with", "and", "but", "or", "my", "our", "your",
    "this", "is", "was", "if", "so", "be", "can", "will", "i'm", "it's",
    "we're", "there", "what",
}
_STUTTER = re.compile(r"(?<![\w'])(\w{1,6})-\s*(?=(\w+))", re.IGNORECASE)


def collapse_repeats(text: str) -> str:
    """"the the" -> "the", "I, I think" -> "I think", "th- the" -> "the",
    and short repeated phrases: "we need to we need to" -> "we need to"."""
    if not text:
        return text

    def stutter(m: re.Match) -> str:
        frag, nxt = m.group(1).lower(), m.group(2).lower()
        # Only a fragment of the word that follows: "th- the", "I- I".
        # "e-mail", "re-do" and "x-ray" are words, not stumbles, and have no
        # space after the hyphen.
        if nxt.startswith(frag) and m.group(0) != m.group(1) + "-":
            return ""
        return m.group(0)
    text = _STUTTER.sub(stutter, text)

    # Repeated n-grams, longest first, where the repeated unit contains a
    # stutter-prone word and no digits ("Bora Bora" and "20 20" are safe).
    words = list(re.finditer(r"[\w']+", text))
    drop = []                        # (start, end) spans to delete
    i = 0
    while i < len(words):
        for n in (4, 3, 2, 1):
            if i + 2 * n > len(words):
                continue
            a = [w.group(0).lower() for w in words[i:i + n]]
            b = [w.group(0).lower() for w in words[i + n:i + 2 * n]]
            if a != b or any(ch.isdigit() for w in a for ch in w):
                continue
            if not any(w in _STUTTER_PRONE for w in a):
                continue
            # Only spaces and commas between the copies, and inside each.
            span = text[words[i].start():words[i + 2 * n - 1].end()]
            if re.search(r"[^\w'\s,]", span):
                continue
            drop.append((words[i].start(), words[i + n].start()))
            i += n - 1
            break
        i += 1
    for s_, e_ in reversed(drop):
        text = text[:s_] + text[e_:]
    return text


# --- days and months (Light and up) ------------------------------------------

# "may", "march" and "august" are also a verb, a verb and an adjective, so
# they are capitalised only where a date makes the month reading certain
# (itn.py). The rest are never anything but names.
_PROPER = re.compile(
    r"(?<![\w'./@-])(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|april|june|july|september|october|november|december)"
    r"(?![\w'@/-]|\.\w)")


def proper_days(text: str) -> str:
    return _PROPER.sub(lambda m: m.group(1).capitalize(), text)


# --- questions (Light and up) -----------------------------------------------

_AUX = ("is", "are", "am", "was", "were", "do", "does", "did", "can", "could",
        "would", "will", "should", "shall", "may", "might", "have", "has",
        "isn't", "aren't", "don't", "doesn't", "didn't", "won't", "wouldn't",
        "can't", "couldn't", "shouldn't", "haven't", "hasn't")
_SUBJECTS = {"i", "you", "we", "they", "he", "she", "it", "this", "that",
             "there", "anyone", "someone", "everyone", "anybody", "somebody",
             "the", "your", "my", "our", "their", "his", "her", "these", "those"}
_WH = ("what", "why", "how", "when", "where", "who", "which", "whose")


def _is_question(sentence: str) -> bool:
    words = re.findall(r"[\w']+", sentence.lower())
    if len(words) < 2 or len(words) > 25:
        return False
    w0, w1 = words[0], words[1]
    if w0 in _AUX:
        # "Do it now." is an order, "Have a nice day." a wish: the verb must
        # be followed by who is being asked about.
        if w0 in ("do", "have") and w1 not in ("you", "we", "they", "i"):
            return False
        return w1 in _SUBJECTS
    if re.fullmatch(r"(?:what|where|who|how|when)'s", w0):
        return True
    if w0 in _WH:
        # "When is it", "How about Friday" -- but not "When I get home I'll
        # call", where a subject follows the wh-word directly.
        return w1 in _AUX or w1 in ("about", "if", "else")
    return False


def fix_questions(text: str) -> str:
    """Swap a full stop for a question mark where the sentence is plainly one.

    whisper marks most questions itself; this catches the short ones it
    types with a period. Conservative: only sentences that open with an
    auxiliary and a subject, or a wh-word and an auxiliary.
    """
    def sub(m: re.Match) -> str:
        sentence, mark = m.group(1), m.group(2)
        if mark in (".", "") and _is_question(sentence):
            return sentence + "?"
        return m.group(0)
    return re.sub(r"([^.!?\n]+?)([.]|$)(?=\s|$)", sub, text)


# --- lists --------------------------------------------------------------------

_NUMBER_NAMES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_LIST_NUM = re.compile(
    r"(?<![\w'])(?:number|item|step)\s+(one|two|three|four|five|six|seven|"
    r"eight|nine|ten|\d{1,2})(?![\w'])[\s]*[,.:;-]?\s*",
    re.IGNORECASE)
_ORDINAL_CUES = ("first", "second", "third", "fourth", "fifth", "sixth",
                 "seventh", "eighth", "ninth", "tenth")
_LIST_ORD = re.compile(
    r"(?:(?<=^)|(?<=[.!?;:]\s)|(?<=\n))(first|second|third|fourth|fifth|sixth|"
    r"seventh|eighth|ninth|tenth)(?:ly)?\s*[,:]\s*",
    re.IGNORECASE)
_LIST_BULLET = re.compile(
    r"(?<![\w'])(?P<sub>sub[\s-]?(?:bullet(?:\s+point)?|point|item))"
    r"|(?<![\w'])(?:(?:new|next)\s+bullet(?:\s+point)?|bullet\s+point)(?![\w'])",
    re.IGNORECASE)
_DETERMINER_BEFORE = re.compile(r"\b(?:a|an|the|this|that|another|each|every)\s*$",
                                re.IGNORECASE)


def _item(text: str) -> str:
    text = text.strip().strip(",;:").strip()
    text = re.sub(r"[.,;:]+$", "", text).strip()
    return text[:1].upper() + text[1:] if text else text


def _intro(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    text = re.sub(r"[.,;:-]+$", "", text).strip()
    return text + ":"


def format_lists(text: str, profile: Profile) -> tuple[str, bool]:
    """Turn spoken list cues into a list. Returns (text, made_a_list)."""
    if profile.lists == "off" or not text:
        return text, False

    # Numbered: "number one ... number two ..." counting up from one.
    cues = list(_LIST_NUM.finditer(text))
    values = []
    for m in cues:
        v = m.group(1).lower()
        values.append(int(v) if v.isdigit() else _NUMBER_NAMES[v])
    if len(cues) >= 2 and values == list(range(1, len(cues) + 1)):
        return _render(text, cues, numbered=True), True

    if profile.lists == "all":
        cues = list(_LIST_ORD.finditer(text))
        names = [m.group(1).lower() for m in cues]
        if len(cues) >= 3 and names == list(_ORDINAL_CUES[:len(cues)]):
            return _render(text, cues, numbered=True), True

    cues = [m for m in _LIST_BULLET.finditer(text)
            if not _DETERMINER_BEFORE.search(text[:m.start()])]
    if cues:
        return _render(text, cues, numbered=False), True
    return text, False


def _render(text: str, cues: list, numbered: bool) -> str:
    lines = []
    intro = _intro(text[:cues[0].start()])
    if intro:
        lines.append(intro)
    n = 0
    for i, m in enumerate(cues):
        end = cues[i + 1].start() if i + 1 < len(cues) else len(text)
        body = _item(text[m.end():end])
        if not body:
            continue
        sub = "sub" in m.groupdict() and m.group("sub")
        if sub:
            lines.append(("   - " if numbered else "  - ") + body)
        elif numbered:
            n += 1
            lines.append(f"{n}. {body}")
        else:
            lines.append(f"- {body}")
    return "\n".join(lines)


# --- email layout ------------------------------------------------------------

_GREETING = re.compile(
    r"^(?P<g>(?:hi|hello|hey|dear|good\s+(?:morning|afternoon|evening))"
    r"(?:\s+[A-Z][\w'-]*){0,3}),\s+(?=\S)",
    re.IGNORECASE)
_SIGNOFF = re.compile(
    r"(?<=[.!?])\s+(?P<s>thanks|thank\s+you|thanks\s+again|best|best\s+regards|"
    r"regards|kind\s+regards|warm\s+regards|cheers|sincerely|all\s+the\s+best)"
    r"[,.!]?(?:\s+(?P<name>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?))?[.!]?\s*$",
    re.IGNORECASE)


def email_layout(text: str) -> tuple[str, bool]:
    """"Hi Sam, ... Thanks, Alex" -> greeting and sign-off on their own lines.
    Only with enough in between to be a letter rather than a one-liner.

    Returns (text, signed): a sign-off must not then get a full stop after
    the name.
    """
    if len(text.split()) < 8:
        return text, False
    m = _GREETING.match(text)
    if m:
        text = m.group("g") + ",\n\n" + text[m.end():]
    m = _SIGNOFF.search(text)
    if not m:
        return text, False
    signoff = m.group("s")
    signoff = signoff[0].upper() + signoff[1:]
    name = m.group("name")
    text = text[:m.start()] + "\n\n" + signoff + "," + ("\n" + name if name else "")
    return text, True


# --- typography --------------------------------------------------------------

def typography(text: str, profile: Profile) -> str:
    """Em dashes and curly quotes where the target is prose, ASCII elsewhere."""
    if not profile.smart_typography:
        return text
    # A spaced hyphen or double hyphen between words is a dash. Not at a line
    # start, where it is a list bullet.
    text = re.sub(r"(?<=[\w,.!?\"')])[ \t]+-{1,2}[ \t]+(?=[\w\"'(])", "\u2014", text)
    text = re.sub(r"(?<=\d)\s*\u2013\s*(?=\d)", "\u2013", text)
    # Double quotes: opening after start/space/bracket, closing otherwise.
    text = re.sub(r'(^|[\s(\[\u2014])"', "\\1\u201c", text)
    text = text.replace('"', "\u201d")
    # Apostrophes inside or closing a word. Leading single quotes are too
    # often an abbreviation ('90s) to guess, so they stay straight.
    text = re.sub(r"(?<=\w)'(?=\w)", "\u2019", text)
    text = re.sub(r"(?<=s)'(?=\s|$|[.,;:!?])", "\u2019", text)
    return text


# --- developer vocabulary ----------------------------------------------------

# Never ordinary English, so safe anywhere.
_DEV_SAFE = {
    "github": "GitHub", "gitlab": "GitLab", "javascript": "JavaScript",
    "typescript": "TypeScript", "macos": "macOS", "ios": "iOS",
    "ipados": "iPadOS", "json": "JSON", "yaml": "YAML", "api": "API",
    "apis": "APIs", "url": "URL", "urls": "URLs", "http": "HTTP",
    "https": "HTTPS", "html": "HTML", "css": "CSS", "sql": "SQL",
    "oauth": "OAuth", "graphql": "GraphQL", "postgresql": "PostgreSQL",
    "mysql": "MySQL", "sqlite": "SQLite", "xcode": "Xcode",
    "iphone": "iPhone", "ipad": "iPad", "youtube": "YouTube",
    "linkedin": "LinkedIn", "cli": "CLI", "sdk": "SDK", "sdks": "SDKs",
    "llm": "LLM", "llms": "LLMs", "gpu": "GPU", "cpu": "CPU", "ui": "UI",
    "ux": "UX", "kubernetes": "Kubernetes", "openai": "OpenAI",
    "chatgpt": "ChatGPT", "vscode": "VS Code", "nodejs": "Node.js",
    "npm": "npm", "linux": "Linux", "ssh": "SSH", "dns": "DNS",
    "jwt": "JWT", "csv": "CSV", "pdf": "PDF", "uuid": "UUID",
    "wifi": "Wi-Fi", "swiftui": "SwiftUI", "appkit": "AppKit",
}
# Also ordinary English, so only where code is the likelier subject.
_DEV_CONTEXTUAL = {
    "python": "Python", "swift": "Swift", "rust": "Rust", "docker": "Docker",
    "java": "Java", "ruby": "Ruby", "react": "React", "django": "Django",
    "flask": "Flask", "rails": "Rails", "redis": "Redis", "kotlin": "Kotlin",
    "node": "Node", "postgres": "Postgres", "pytest": "pytest",
    "homebrew": "Homebrew", "github actions": "GitHub Actions",
}
# Not inside a path, domain, email or identifier: "github.com", "data.json".
_DEV_EDGE_L = r"(?<![\w./@#:$-])"
_DEV_EDGE_R = r"(?![\w/@-]|\.\w)"


def dev_terms(text: str, profile: Profile) -> str:
    if profile.dev_terms == "off":
        return text
    table = dict(_DEV_SAFE)
    if profile.dev_terms == "all":
        table.update(_DEV_CONTEXTUAL)
    for spoken in sorted(table, key=len, reverse=True):
        pattern = _DEV_EDGE_L + r"\s+".join(map(re.escape, spoken.split())) + _DEV_EDGE_R
        text = re.sub(pattern, table[spoken], text, flags=re.IGNORECASE)
    return text


# --- the final full stop -----------------------------------------------------

def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if s.strip()])


def apply_terminal(text: str, profile: Profile, *, enabled: bool,
                   chat_period: bool = False) -> str:
    """Add or leave off the closing full stop, per profile."""
    import punctuate
    if not text.strip():
        return text
    if profile.terminal == "keep":
        return text
    if profile.terminal == "multi_sentence" and not chat_period:
        stripped = text.rstrip()
        if _sentences(stripped) == 1 and len(stripped.split()) <= 15 \
                and stripped.endswith(".") and not stripped.endswith(".."):
            return stripped[:-1]
        if _sentences(stripped) == 1 and len(stripped.split()) <= 15:
            return text
    return punctuate.ensure_terminal(text) if enabled else text


# --- fitting into the text around the cursor --------------------------------

_OPENERS = "([{\"'\u201c\u2018/\n\t "
_SENTENCE_ENDS = ".!?\n"


def _keeps_capital(word: str, terms: set[str]) -> bool:
    m = re.search(r"[\w'\u2019-]+", word)
    if not m:
        return True
    core = m.group(0)
    if core in ("I", "I'm", "I'll", "I've", "I'd") or core in terms:
        return True
    if not (core[0].isupper() and core[1:].islower()):
        return True          # iPhone, JSON, McDonald -- not ours to touch
    return not is_common(core)                   # a name


def adapt_to_cursor(text: str, before: str | None, after: str | None,
                    profile: Profile, terms: set[str] | None = None,
                    spacing_only: bool = False) -> str:
    """Make the dictation fit where it lands.

    Only with context. `before`/`after` are the few characters either side
    of the cursor that context.py read; None means "unknown", which leaves
    the text exactly as it was -- the 0.3 behaviour.
    """
    if not text or not profile.insertion:
        return text
    terms = terms or set()

    if before:
        last = before[-1]
        tail = before.rstrip(" \t")
        # Continuing a sentence: no capital unless the word always has one.
        if not spacing_only and tail and tail[-1] not in _SENTENCE_ENDS \
                and tail[-1] not in ":" \
                and not re.search(r"(?:^|\n)\s*(?:[-*\u2022]|\d+[.)])\s*$", tail):
            first = re.match(r"\S+", text)
            if first and not _keeps_capital(first.group(0), terms):
                text = text[:1].lower() + text[1:]
        # A word glued to the one before it: "hello" + "world" -> "hello world".
        if last not in _OPENERS and text[:1] not in ",.;:!?)]}\n'\u2019":
            text = " " + text

    if after and after.strip(" \t"):
        # Look past spaces: " tomorrow." still continues the sentence. A
        # newline does not -- the cursor is at the end of its line.
        nxt = after.lstrip(" \t")[0]
        glued = not after[0].isspace()
        if nxt.isalnum() or nxt in "([{\"'\u201c":
            # The sentence carries on after the cursor: no full stop here, and
            # a space so the next word does not fuse to ours.
            if not spacing_only and text.endswith(".") and not text.endswith(".."):
                text = text[:-1]
            if glued and not text.endswith((" ", "\n")):
                text += " "
        elif nxt in ",.;:!?)]}" and not spacing_only:
            if text.endswith(".") and not text.endswith(".."):
                text = text[:-1]
    return text

