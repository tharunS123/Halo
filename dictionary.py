"""Personal vocabulary correction for raw whisper.cpp transcripts.

Two jobs:
  1. Rewrite known mis-transcriptions before anything else sees the text.
  2. Hand the preferred spellings to the cleanup model as context, so it does
     not "helpfully" undo them.
"""
import difflib
import json
import re
import threading
from functools import lru_cache

import config


@lru_cache(maxsize=1)
def _english_words() -> frozenset:
    """macOS ships a 235k-word list. Used to veto fuzzy matches: if what the
    speaker said is already a real English word, it is almost certainly that
    word and not a garbled technical term. Without this guard 'launch' becomes
    'launchd' and 'jason' becomes 'JSON'."""
    try:
        with open("/usr/share/dict/words", encoding="utf-8", errors="ignore") as f:
            return frozenset(w.strip().lower() for w in f if w.strip())
    except OSError:
        return frozenset()


_SUFFIXES = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "y")


def _is_english(phrase: str) -> bool:
    """True if the phrase is ordinary English and must not be fuzzy-replaced.

    Three checks, because the system wordlist holds base forms only:
      1. the phrase itself      -> 'launch', 'jason'
      2. a de-inflected form    -> 'launched' -> 'launch'
      3. every word in a phrase -> 'a sync' = 'a' + 'sync'
    """
    words = _english_words()
    if not words:
        return False
    low = phrase.lower().strip()
    if not low:
        return False
    if low in words:
        return True
    for suf in _SUFFIXES:
        if low.endswith(suf) and len(low) - len(suf) >= 3:
            stem = low[: -len(suf)]
            if stem in words or (stem + "e") in words:
                return True
    tokens = low.split()
    if len(tokens) > 1 and all(
        t in words or len(t) <= 2 for t in tokens
    ):
        return True
    return False


class Dictionary:
    def __init__(self, path=None):
        self.path = path or config.DICTIONARY_FILE
        self._lock = threading.Lock()
        self._mtime = None
        self.terms: list[dict] = []
        self.fuzzy = {"enabled": False, "threshold": 0.90,
                      "max_words": 4, "min_chars": 6}
        self._rules: list[tuple[re.Pattern, str]] = []
        self.load()

    # --- loading -------------------------------------------------------
    def load(self) -> bool:
        """(Re)load from disk. Returns True if anything was loaded."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            if self._mtime == mtime and self._rules:
                return True
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[dictionary] could not parse {self.path}: {e}")
                return False
            self.terms = [t for t in data.get("terms", []) if t.get("term")]
            self.fuzzy = {**self.fuzzy, **data.get("fuzzy", {})}
            self._rules = self._compile(self.terms)
            self._mtime = mtime
        return True

    @staticmethod
    def _compile(terms) -> list[tuple[re.Pattern, str]]:
        """Longest variants first, so 'senthil kumar' wins over 'kumar'."""
        pairs = []
        for entry in terms:
            correct = entry["term"]
            for variant in entry.get("variants", []):
                if variant.strip():
                    pairs.append((variant.strip(), correct))
            # Also normalise casing when the word is already spelled right.
            pairs.append((correct, correct))
        pairs.sort(key=lambda p: len(p[0]), reverse=True)

        rules = []
        for variant, correct in pairs:
            # \b fails next to '.', so bound on non-word chars explicitly.
            pattern = re.compile(
                r"(?<![\w.])" + r"[\s.]*".join(map(re.escape, variant.split()))
                + r"(?![\w])",
                re.IGNORECASE,
            )
            rules.append((pattern, correct))
        return rules

    # --- correction ----------------------------------------------------
    def apply(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Correct `text`. Returns (corrected, [(before, after), ...])."""
        if not text:
            return text, []
        self.load()                      # pick up edits without a restart
        changes: list[tuple[str, str]] = []

        def sub_one(pattern, correct, s):
            def repl(m):
                if m.group(0) != correct:
                    changes.append((m.group(0), correct))
                return correct
            return pattern.sub(repl, s)

        with self._lock:
            rules = list(self._rules)
        out = text
        for pattern, correct in rules:
            out = sub_one(pattern, correct, out)

        if self.fuzzy.get("enabled"):
            out, fuzzy_changes = self._apply_fuzzy(out)
            changes.extend(fuzzy_changes)
        return out, changes

    def _apply_fuzzy(self, text: str):
        """Catch near-misses the variant list does not cover.

        Deliberately conservative: only n-grams of at least `min_chars`, only
        above `threshold`, and never touching a token that already matches a
        known term exactly. Over-eager fuzzy matching corrupts good text, which
        is far worse than leaving one word mis-transcribed.
        """
        threshold = float(self.fuzzy.get("threshold", 0.90))
        max_words = int(self.fuzzy.get("max_words", 4))
        min_chars = int(self.fuzzy.get("min_chars", 6))
        targets = [t["term"] for t in self.terms]
        known = {t.lower() for t in targets}

        tokens = text.split()
        changes = []
        i = 0
        out: list[str] = []
        while i < len(tokens):
            matched = False
            # Longest n-gram first.
            for n in range(min(max_words, len(tokens) - i), 0, -1):
                phrase = " ".join(tokens[i:i + n])
                core = re.sub(r"[^\w\s]", "", phrase)
                low = core.lower()
                if len(core) < min_chars or low in known:
                    continue
                # Veto: ordinary English is what the speaker meant.
                if _is_english(core):
                    continue
                # Veto: plain plural of a term ("repos" is not a typo of "repo").
                if low.endswith("s") and low[:-1] in known:
                    continue
                best, score = None, 0.0
                for term in targets:
                    if abs(len(term) - len(core)) > max(4, len(term) * 0.4):
                        continue
                    r = difflib.SequenceMatcher(
                        None, core.lower(), term.lower()).ratio()
                    if r > score:
                        best, score = term, r
                if best and score >= threshold:
                    trailing = re.search(r"[^\w]+$", phrase)
                    out.append(best + (trailing.group(0) if trailing else ""))
                    changes.append((phrase, best))
                    i += n
                    matched = True
                    break
            if not matched:
                out.append(tokens[i])
                i += 1
        return " ".join(out), changes

    # --- prompt context -------------------------------------------------
    def prompt_context(self, limit: int = 60) -> str:
        """Preferred spellings for the cleanup model's system prompt."""
        self.load()
        names = [t["term"] for t in self.terms][:limit]
        if not names:
            return ""
        return ("Preferred spellings (keep these EXACTLY as written if they "
                "appear): " + ", ".join(names) + ".")
