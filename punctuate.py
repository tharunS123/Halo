"""Local, offline punctuation and capitalization -- the Apple Dictation part.

Apple's dictation punctuates without a network round trip, and it obeys spoken
punctuation ("comma", "new line", "question mark"). Halo's equivalent used to
be the OpenRouter cleanup pass, which meant Privacy Mode -- and anyone without
an API key -- got raw whisper output: no spoken punctuation, `i` lowercase, and
often no terminal period.

This module closes that gap with pure text rules, so it runs in ~0.1ms, needs
no key, and never leaves the machine. It runs on EVERY utterance, before
cleanup, so the LLM pass (when enabled) starts from already-correct text rather
than being the only thing standing between you and unpunctuated prose.

It deliberately does NOT try to split sentences heuristically. whisper already
places most sentence boundaries, and a wrong split ("Dr. Smith" -> two
sentences) reads worse than a missing one.
"""
import re

# --- spoken punctuation ---------------------------------------------------
#
# Apple substitutes these unconditionally. We cannot: "period" and "dash" are
# ordinary nouns ("the Jurassic period", "a dash of salt"), and silently eating
# a real word is worse than leaving a spoken command untranslated.
#
# So multi-word phrases -- which are never ordinary speech -- substitute
# freely, while the ambiguous single words below must clear two tests: nothing
# may follow them but the end of the utterance (or another mark), and a
# determiner may not sit in front. "The Jurassic period was long" fails the
# first test, "add a dash of salt" fails both, and "I am done period" passes.

# A double quote is the one mark whose spacing depends on which one you
# meant: an opening quote binds to the word AFTER it, a closing quote to the
# word BEFORE. The character itself cannot tell us apart, so the two spoken
# phrases substitute to sentinels and the direction is resolved at the end.
_OPEN_Q, _CLOSE_Q = "\x01", "\x02"

# phrase -> replacement. Longest first at compile time so "question mark" wins
# over "mark" and "exclamation point" over "point".
_PUNCTUATION = {
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
    "semi colon": ";",
    "ellipsis": "...",
    "dot dot dot": "...",
    "hyphen": "-",
    "dash": " - ",
    "em dash": " -- ",
    "open paren": "(",
    "open parenthesis": "(",
    "close paren": ")",
    "close parenthesis": ")",
    "open quote": _OPEN_Q,
    "close quote": _CLOSE_Q,
    # No bare "quote"/"unquote": "a quote from the article" is ordinary
    # speech, and the clause-end test that rescues "period" cannot help here
    # because a quotation mark is rarely the last thing you say.
    "open bracket": "[",
    "close bracket": "]",
    "ampersand": "&",
    "percent sign": "%",
    "dollar sign": "$",
    "at sign": "@",
    "asterisk": "*",
    "slash": "/",
    "forward slash": "/",
    "backslash": "\\",
}

# Line breaks are substitutions too, but they are whitespace rather than
# punctuation, so capitalization after them follows a different rule.
_BREAKS = {
    "new line": "\n",
    "newline": "\n",
    "new paragraph": "\n\n",
}

# Single words above that are also ordinary English. Substituted only when NOT
# preceded by one of _DETERMINERS.
_AMBIGUOUS = {"period", "full stop", "dash", "colon", "slash", "hyphen"}

# Marks that must stay available mid-clause -- "hello comma world" has to
# work -- but are still ordinary nouns after a determiner. The clause-end
# test would break the useful case, so these get the determiner veto alone:
# "add a comma after this word" survives, "hello comma world" does not.
_DETERMINER_GUARDED = {"comma", "semicolon", "ellipsis", "ampersand",
                       "asterisk", "backslash"}

_DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those", "my", "your", "his",
    "her", "its", "our", "their", "one", "some", "any", "each", "every",
    "no", "another",
}

# Filler words whisper faithfully transcribes and nobody wants typed. Only
# removed when they stand alone as a token -- "um" inside "umbrella" is safe
# because we match whole words, and "like" is left alone entirely because it
# is far too often meant ("I like this", "looks like rain").
_FILLERS = re.compile(
    r"(?<![\w'])(?:u[hm]+|e[rh]+|a+h+|mhm+|hmm+)(?![\w'])[\s,]*",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"[.!?]['\")\]]*\s+$")


def _compiled_substitutions():
    """(pattern, replacement, ambiguous, is_punct, guarded), longest first."""
    pairs = sorted(
        [(p, r, False) for p, r in _BREAKS.items()]
        + [(p, r, True) for p, r in _PUNCTUATION.items()],
        key=lambda t: -len(t[0]),
    )
    out = []
    for phrase, repl, is_punct in pairs:
        ambiguous = phrase in _AMBIGUOUS
        pattern = re.compile(
            r"(?<![\w'])" + r"\s+".join(map(re.escape, phrase.split()))
            + r"(?![\w'])",
            re.IGNORECASE,
        )
        out.append((pattern, repl, ambiguous, is_punct,
                    phrase in _DETERMINER_GUARDED))
    return out


_SUBS = _compiled_substitutions()


def _preceded_by_determiner(text: str, start: int) -> bool:
    """True if the word immediately before `start` is a determiner.

    This is the whole veto: it is what keeps "a dash of salt" and "the grace
    period" from turning into "a - of salt" and "the grace."
    """
    before = text[:start].rstrip()
    if not before:
        return False
    last = re.search(r"[\w']+$", before)
    return bool(last) and last.group(0).lower() in _DETERMINERS


def _ends_the_clause(text: str, end: int) -> bool:
    """True if nothing but the end of the utterance -- or another mark --
    follows the match.

    This is the test that saves ordinary nouns. A spoken "period" is the last
    thing you say in a sentence; a Jurassic one has a verb after it.
    """
    rest = text[end:]
    if not rest.strip():
        return True
    return rest.lstrip(" \t")[:1] in (
        ".", ",", ";", ":", "!", "?", "\n", '"', ")", _OPEN_Q, _CLOSE_Q)


def apply_spoken_punctuation(text: str) -> tuple[str, int]:
    """Replace spoken punctuation names with the marks they stand for.

    Returns (text, number of substitutions made).
    """
    count = 0
    for pattern, repl, ambiguous, is_punct, guarded in _SUBS:
        def sub(m, repl=repl, ambiguous=ambiguous, is_punct=is_punct,
                guarded=guarded):
            nonlocal count
            determiner = _preceded_by_determiner(m.string, m.start())
            if ambiguous and (determiner
                              or not _ends_the_clause(m.string, m.end())):
                return m.group(0)
            if guarded and determiner:
                return m.group(0)
            count += 1
            # Punctuation binds to the word before it, so eat the space that
            # whisper put in front: "hello comma world" -> "hello, world".
            return repl
        new = pattern.sub(sub, text)
        if is_punct and new != text:
            # Tidy the space the spoken word used to occupy.
            new = re.sub(r"\s+([,.;:!?)\]])", r"\1", new)
            new = re.sub(r"([(\[])\s+", r"\1", new)
        text = new

    # Resolve the quote sentinels now that every substitution has landed.
    text = re.sub(_OPEN_Q + r"\s*", '"', text)
    text = re.sub(r"\s*" + _CLOSE_Q, '"', text)
    return text, count


def strip_fillers(text: str) -> str:
    """Drop standalone hesitation noises."""
    out = _FILLERS.sub("", text)
    # A filler at the start of a clause leaves a dangling comma behind.
    out = re.sub(r"^\s*,\s*", "", out)
    out = re.sub(r"([,;:])\s*,", r"\1", out)
    return out


def capitalize(text: str) -> str:
    """Sentence case, plus the pronoun I.

    whisper usually capitalizes, but not after a mark the speaker dictated,
    and never reliably for a lone `i`.
    """
    # The pronoun I, including contractions: i'm, i'll, i've, i'd.
    text = re.sub(r"(?<![\w'])i(?=(?:'[a-z]{1,2})?(?![\w']))", "I", text)

    # A sentence ends at .!? followed by WHITESPACE -- never by a letter.
    # "whisper.cpp" and "example.com" are one word with a dot in the middle,
    # and capitalizing after that dot ("whisper.Cpp") corrupts every term in
    # the user's own dictionary. The whitespace requirement is the whole
    # difference, and it cost a dictionary test to find.
    out = []
    capitalize_next = True
    for i, ch in enumerate(text):
        if capitalize_next and ch.isalpha():
            out.append(ch.upper())
            capitalize_next = False
            continue

        out.append(ch)
        if ch == "\n":
            capitalize_next = True
        elif ch in ".!?":
            rest = text[i + 1:]
            # Trailing quotes and brackets may sit between the mark and the
            # space: `he said "stop." Then...`
            rest = rest.lstrip("\"')]}")
            capitalize_next = (rest == "" or rest[0].isspace())
        elif not ch.isspace() and ch not in "\"'([":
            capitalize_next = False
    return "".join(out)


def tidy_spacing(text: str) -> str:
    """Collapse the whitespace damage the substitutions leave behind."""
    # Spaces before punctuation, none after.
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", text)
    # Deliberately NOT inserting a space after .!? that is followed by a
    # letter: whisper always spaces its own sentence breaks, so the only
    # things matching that shape are "whisper.cpp" and "example.com".
    # Never more than one space, and never a space around a newline.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    # Three or more newlines is never what anyone dictated.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" \t")


def ensure_terminal(text: str) -> str:
    """Give the utterance a final mark if it has none.

    Skipped when the text ends in a line break (the speaker asked to keep
    going) or already ends in punctuation.
    """
    stripped = text.rstrip()
    if not stripped or text.endswith("\n"):
        return text
    # Look past a closing quote or bracket: "(a test)" still wants a period,
    # but "(a test.)" does not.
    core = stripped.rstrip("\"')]}")
    if not core or core[-1] in ".!?,;:-":
        return text
    return stripped + "."


def polish(text: str, spoken: bool = True, fillers: bool = True,
           terminal: bool = True) -> tuple[str, int]:
    """The whole local pass. Returns (text, spoken-punctuation substitutions).

    Order matters: spoken punctuation first (it creates the sentence
    boundaries everything below keys on), then fillers, then spacing, then
    capitalization last so it sees the final boundaries.
    """
    if not text or not text.strip():
        return text, 0

    subs = 0
    if spoken:
        text, subs = apply_spoken_punctuation(text)
    if fillers:
        text = strip_fillers(text)
    text = tidy_spacing(text)
    if terminal:
        text = ensure_terminal(text)
    text = capitalize(text)
    return text, subs
