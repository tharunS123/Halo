"""Spoken self-correction: "meet me Thursday -- actually Friday" -> "meet me Friday".

People correct themselves out loud all the time, and whisper faithfully types
both halves. Apple Dictation leaves them in; Wispr Flow calls resolving them
"backtrack". This is Halo's deterministic version.

It is not a replace table, because every cue word is also ordinary English:
"I actually like it", "no problem", "wait for me", "sorry for the delay",
"I mean it". Deleting words the speaker meant is the worst thing a dictation
tool can do, so a correction has to clear three tests before anything moves:

  1. The cue is DELIMITED -- whisper marks the pause with a comma, a dash or a
     full stop. "I actually like it" has no pause and never fires. A cue that
     opens the utterance ("No, I don't think so") has nothing to correct.
  2. The replacement is found: whatever follows the cue, up to the next pause.
  3. What it replaces is found by MEANING, not position, in this order:
       typed     the replacement is a number, a day, a month, a pronoun or a
                 name, and the nearest earlier word of the same kind is what
                 it replaces ("five ... make that six")
       restart   the replacement repeats the words it started from
                 ("send it to John, sorry, send it to Jake")
       clause    "scratch that" / "let me rephrase" drop the sentence so far
       position  last resort, only for cues that are never small talk
                 ("I mean", "make that", "correction", "or rather")

Anything that fails the third test is reported as ambiguous and left exactly as
spoken. The cleanup model (Normal and Polished modes) may resolve it later; if
there is no model, the speaker gets their words back rather than a guess.
"""
import re
from dataclasses import dataclass, field
from functools import lru_cache

# (phrase, kind). Longest first at compile time so "no wait" beats "no".
#   strong   -- a correction whenever it is delimited and something is found
#   weak     -- also everyday politeness, so only a typed or restart match
#               counts; never the positional fallback
#   restart  -- drops the clause (or, at a sentence start, the sentence before)
_CUES = {
    "scratch that": "restart",
    "let me rephrase": "restart",
    "let me rephrase that": "restart",
    "let me start over": "restart",
    "let me try that again": "restart",
    "make that": "strong",
    "or rather": "strong",
    "i mean": "strong",
    "correction": "strong",
    "actually": "strong",
    "actually no": "strong",
    "no actually": "strong",
    "rather": "strong",
    "no wait": "weak",
    "wait no": "weak",
    "no sorry": "weak",
    "sorry no": "weak",
    "sorry": "weak",
    "wait": "weak",
    "no": "weak",
}

# Only these may use the positional fallback. "actually" and "rather" are too
# often an aside: "it was, rather, unusual" must not become "it unusual".
_POSITIONAL_OK = {"make that", "or rather", "i mean", "correction"}

# What may follow a cue when it is NOT a correction. Checked against the first
# word after the cue (and its optional comma).
_NOT_AFTER = {
    "sorry": {"for", "about", "to", "that", "if", "but", "i'm", "im", "we",
              "guys", "everyone", "folks", "all", "again"},
    "no": {"problem", "problems", "worries", "thanks", "thank", "way", "idea",
           "doubt", "longer", "more", "matter", "need", "big", "rush",
           "pressure", "clue", "kidding", "offense", "offence", "comment",
           "one", "not", "i", "we", "you", "it", "that", "this"},
    "wait": {"for", "until", "till", "a", "and", "to", "up", "on", "here",
             "there", "outside", "what", "around", "in", "at"},
    "i mean": {"it", "that", "this", "what", "well", "seriously", "really",
               "business", "come"},
    "rather": {"than", "not", "be", "have", "go", "do", "just", "stay"},
    "actually": {"i", "we", "you", "it", "that", "this", "there", "the"},
}

# A pause whisper typed out. The cue must sit right after one of these.
_DELIM = r"(?:[,;:.!?…]|\s-{1,2}(?=\s)|[—–])"
_CUE_RE = re.compile(
    r"(?P<pre>" + _DELIM + r")\s*(?P<cue>"
    + "|".join(re.escape(c).replace(r"\ ", r"\s+")
               for c in sorted(_CUES, key=len, reverse=True))
    + r")(?![\w'’])",
    re.IGNORECASE,
)

# Where the replacement ends: the next pause, or the end of the utterance.
_R_END = re.compile(r"\s*(?:[,;:.!?…]+|\s-{1,2}(?=\s)|[—–])\s*|\s*$")

_WORD = re.compile(r"[$€£]?[\w][\w'’]*(?:[.:]\d+)?%?")

_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "million", "billion", "half", "dozen",
}
_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
         "sunday", "today", "tomorrow", "tonight", "yesterday", "weekend"}
_MONTHS = {"january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"}
_PRONOUNS = {"he", "she", "they", "we", "you", "him", "her", "them", "us",
             "me", "his", "hers", "their", "our", "my", "your"}
# Never on the replaced side of a positional guess: swapping "the" for a noun
# is never what anyone meant.
_FUNCTION = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "with",
             "and", "or", "but", "is", "are", "was", "were", "be", "it",
             "that", "this", "i", "we", "you", "he", "she", "they", "me",
             "my", "our", "your", "do", "did", "does", "have", "has", "had",
             "will", "would", "can", "could", "should", "so", "not"}
# A comma before these survives a mid-sentence correction; any other pause
# was only there to set off the correction and goes with it.
_KEEP_COMMA_BEFORE = {"and", "but", "or", "so", "then", "because", "which",
                      "who", "although", "though"}


@lru_cache(maxsize=1)
def _common_words() -> frozenset:
    """Lower-case entries of the system word list. Names appear there only
    capitalised, which is what tells "John" from "The" at a sentence start."""
    try:
        with open("/usr/share/dict/words", encoding="utf-8", errors="ignore") as f:
            return frozenset(w.strip() for w in f if w[:1].islower())
    except OSError:
        return frozenset()


_SUFFIXES = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "ies", "ied")


def is_common(word: str) -> bool:
    """True if `word` is ordinary lower-case English, inflections included.

    The word list holds base forms only, so "sounds" and "invalidated" need
    stemming -- the same trick dictionary.py uses to protect "launched".
    Names are absent from the lower-case entries, which is the point.
    """
    words = _common_words()
    w = word.lower().strip(".,;:!?\"'()")
    if not w or w in words:
        return bool(w)
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[: -len(suf)]
            if stem in words or stem + "e" in words or \
                    (suf in ("ies", "ied") and stem + "y" in words) or \
                    (len(stem) > 3 and stem[-1] == stem[-2] and stem[:-1] in words):
                return True
    return False


@dataclass
class Repair:
    cue: str
    removed: str
    inserted: str
    method: str          # typed | restart | clause | positional


@dataclass
class BacktrackResult:
    text: str
    repairs: list[Repair] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)   # the cue words left alone

    @property
    def changed(self) -> bool:
        return bool(self.repairs)


def _is_number(word: str) -> bool:
    w = word.lower().strip("$€£%,")
    if re.fullmatch(r"\d+(?:[.:]\d+)?(?:st|nd|rd|th)?", w):
        return True
    parts = w.split("-")
    return all(p in _NUMBER_WORDS for p in parts) and bool(parts[0])


def _kind(word: str, sentence_initial: bool = False) -> str | None:
    """The semantic class a typed match keys on, or None."""
    w = word.lower().strip("$€£%.,")
    if _is_number(word):
        return "number"
    if w in _DAYS:
        return "day"
    if w in _MONTHS and (w not in ("may", "march") or word[:1].isupper()):
        return "month"
    if w in _PRONOUNS:
        return "pronoun"
    if word[:1].isupper() and w != "i":
        # A capital at a sentence start proves nothing, unless the word is not
        # an ordinary lower-case English word.
        if not sentence_initial or not is_common(w):
            return "name"
    return None


def _words(text: str) -> list[tuple[str, int, int, bool]]:
    """(word, start, end, sentence_initial) for every word in `text`."""
    out = []
    for m in _WORD.finditer(text):
        before = text[:m.start()].rstrip()
        initial = not before or before[-1] in ".!?\n"
        out.append((m.group(0), m.start(), m.end(), initial))
    return out


def _find_typed(pre: str, kind: str) -> tuple[int, int] | None:
    """Span of the nearest earlier run of `kind` words in `pre`."""
    words = _words(pre)
    for i in range(len(words) - 1, -1, -1):
        w, s, e, initial = words[i]
        if _kind(w, initial) != kind:
            continue
        # Extend left over a multi-word run: "twenty five", "John Smith".
        j = i
        while j > 0:
            pw, ps, pe, pinit = words[j - 1]
            gap = pre[pe:words[j][1]]
            if _kind(pw, pinit) == kind and gap.strip() in ("", "-"):
                j -= 1
            else:
                break
        return words[j][1], e
    return None


def _find_restart(pre: str, r_words: list[str]) -> int | None:
    """Offset in `pre` where the replacement's opening words were first said."""
    if len(r_words) < 2:
        return None
    words = _words(pre)
    first = r_words[0].lower()
    for i in range(len(words) - 1, -1, -1):
        if words[i][0].lower() != first:
            continue
        rest = words[i + 1:]
        same_second = bool(rest) and rest[0][0].lower() == r_words[1].lower()
        # "the red one, I mean the blue one": only the article repeats, but
        # the span it opens is the same size as the replacement.
        if same_second or len(rest) + 1 <= len(r_words) + 1:
            return words[i][1]
    return None


def _find_positional(pre: str, r_words: list[str]) -> int | None:
    n = len(r_words)
    words = _words(pre)
    if n > 3 or len(words) < n + 1:
        return None
    if r_words[0].lower() in _FUNCTION or r_words[0].lower() in _PRONOUNS:
        return None
    tail = words[-n:]
    if any(w.lower() in _FUNCTION for w, *_ in tail):
        return None
    return tail[0][1]


def _sentence_start(text: str, end: int) -> int:
    """Offset just after the last sentence break before `end`."""
    cut = max(text.rfind(ch, 0, end) for ch in ".!?\n")
    return cut + 1 if cut >= 0 else 0


def _join(left: str, right: str) -> str:
    left, right = left.rstrip(), right.lstrip()
    if not left:
        return right
    if not right:
        return left
    return left + ("" if right[0] in ",.;:!?)" else " ") + right


def _resolve_one(text: str, m: re.Match) -> tuple[str, Repair] | str:
    """Apply the correction at `m`. Returns (new text, repair), or a reason."""
    cue = " ".join(m.group("cue").lower().split())
    kind = _CUES[cue]
    pre = text[:m.start("pre")]
    delim = m.group("pre").strip()
    after = text[m.end("cue"):]

    if not pre.strip():
        return "cue opens the utterance"

    if kind == "restart":
        start = _sentence_start(pre, len(pre))
        if not pre[start:].strip() and delim in ".!?":
            # "...we should go. Scratch that." -- the sentence before goes.
            start = _sentence_start(pre, len(pre.rstrip()) - 1)
        removed = pre[start:].strip()
        rest = after.lstrip(" ,;:.!?-—–…")
        new = _join(pre[:start], rest)
        return new, Repair(cue, removed, "", "clause")

    # The replacement runs from the cue to the next pause.
    body = after.lstrip(" ,;:")
    end = _R_END.search(body)
    r_text = body[:end.start()].strip()
    r_delim = end.group(0).strip()
    rest = body[end.end():]
    if not r_text:
        return "nothing after the cue"
    r_words = [w for w, *_ in _words(r_text)]
    if not r_words:
        return "nothing after the cue"
    blocked = _NOT_AFTER.get(cue, set())
    if r_words[0].lower() in blocked:
        return f"'{cue} {r_words[0]}' is ordinary speech"

    head_kind = _kind(r_words[0])
    method, span = None, None
    if head_kind:
        found = _find_typed(pre, head_kind)
        if found:
            method, span = "typed", found
    if span is None:
        start = _find_restart(pre, r_words)
        if start is not None:
            method, span = "restart", (start, len(pre.rstrip()))
    if span is None and cue in _POSITIONAL_OK:
        start = _find_positional(pre, r_words)
        if start is not None:
            method, span = "positional", (start, len(pre.rstrip()))
    if span is None:
        return "no match for the replacement"

    s, e = span
    removed = pre[s:e]
    if method == "typed" and len(r_words) == 1:
        # "Meet me Thursday at noon, actually Friday": only the day changes.
        new_pre = pre[:s] + r_text + pre[e:]
    else:
        new_pre = pre[:s] + r_text
    new_pre = new_pre.rstrip()

    rest_words = rest.split()
    if not rest.strip():
        tail = r_delim if r_delim[:1] in (".", "!", "?", "…") else ""
        new = new_pre + tail
    elif r_delim[:1] in (".", "!", "?"):
        new = new_pre + r_delim + " " + rest.lstrip()
    elif r_delim == "," and rest_words[0].lower().strip(",") in _KEEP_COMMA_BEFORE:
        new = new_pre + ", " + rest.lstrip()
    else:
        # A dash or comma that only fenced off the correction goes with it:
        # "we need five -- make that six -- copies".
        new = _join(new_pre, rest)
    return new, Repair(cue, removed.strip(), r_text, method)


def resolve(text: str, max_repairs: int = 6) -> BacktrackResult:
    """Resolve every spoken self-correction in `text` that is unambiguous."""
    result = BacktrackResult(text)
    if not text or not text.strip():
        return result
    pos = 0
    for _ in range(max_repairs * 3):
        m = _CUE_RE.search(result.text, pos)
        if m is None:
            break
        outcome = _resolve_one(result.text, m)
        if isinstance(outcome, str):
            cue = " ".join(m.group("cue").lower().split())
            # Only report what a model could plausibly fix; an opening cue or
            # "no problem" is not a correction at all.
            if outcome in ("no match for the replacement",):
                result.ambiguous.append(cue)
            pos = m.end("cue")
            continue
        result.text, repair = outcome
        result.repairs.append(repair)
        if len(result.repairs) >= max_repairs:
            break
        pos = 0
    return result
