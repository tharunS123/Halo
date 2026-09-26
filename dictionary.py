"""Personal vocabulary correction for raw whisper.cpp transcripts.

Two jobs:
  1. Rewrite known mis-transcriptions before anything else sees the text.
  2. Hand the preferred spellings to the cleanup model as context, so it does
     not "helpfully" undo them.

An entry in dictionary.json:

    {"term": "Supabase",            the written form, exactly as you want it
     "variants": ["super base"],    what you say / what whisper types instead
     "type": "company",             word | name | company | acronym |
                                    technical | phrase  (for the manager UI)
     "hint": "soo-puh-base",        how it sounds; matched like a variant
     "match_case": true,            also fix the casing of a correct spelling
     "apps": ["com.tinyspeck..."],  only in these apps (empty: everywhere)
     "languages": ["en"]}           only in these languages (empty: all)

Every field but `term` is optional, so a 0.3 dictionary still loads as is.
"""
import csv
import difflib
import io
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
    return len(tokens) > 1 and all(t in words or len(t) <= 2 for t in tokens)


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
            self.terms = [t for t in data.get("terms", [])
                          if isinstance(t, dict) and t.get("term")]
            self.fuzzy = {**self.fuzzy, **data.get("fuzzy", {})}
            self._rules = self._compile(self.terms)
            self._mtime = mtime
        return True

    @staticmethod
    def spoken_forms(entry: dict) -> list[str]:
        """Everything that should turn into `term`: its variants, plus the
        pronunciation hint read as words ("soo-puh-base" -> "soo puh base")."""
        forms = [v.strip() for v in entry.get("variants", []) if isinstance(v, str)
                 and v.strip()]
        hint = entry.get("hint")
        if isinstance(hint, str) and hint.strip():
            forms.append(re.sub(r"[-_/]+", " ", hint).strip())
        return forms

    @staticmethod
    def _compile(terms) -> list[tuple[re.Pattern, str, dict]]:
        """Longest variants first, so 'senthil kumar' wins over 'kumar'."""
        pairs = []
        for entry in terms:
            correct = entry["term"]
            for variant in Dictionary.spoken_forms(entry):
                pairs.append((variant, correct, entry))
            # Also normalise casing when the word is already spelled right.
            if entry.get("match_case", True):
                pairs.append((correct, correct, entry))
        pairs.sort(key=lambda p: len(p[0]), reverse=True)

        rules = []
        for variant, correct, entry in pairs:
            # \b fails next to '.', so bound on non-word chars explicitly.
            pattern = re.compile(
                r"(?<![\w.])" + r"[\s.]*".join(map(re.escape, variant.split()))
                + r"(?![\w])",
                re.IGNORECASE,
            )
            rules.append((pattern, correct, entry))
        return rules

    @staticmethod
    def in_scope(entry: dict, app: str | None, language: str | None) -> bool:
        """An entry scoped to apps or languages applies only there. Unknown
        app or language (no context) means only global entries apply --
        a Slack-only nickname must not leak into an email because Halo
        could not tell where it was."""
        apps = [a for a in entry.get("apps", []) or [] if a]
        langs = [x for x in entry.get("languages", []) or [] if x]
        if apps and (not app or app not in apps):
            return False
        if langs and (not language or language.split("-")[0] not in
                      [x.split("-")[0] for x in langs]):
            return False
        return True

    # --- correction ----------------------------------------------------
    def apply(self, text: str, app: str | None = None,
              language: str | None = None) -> tuple[str, list[tuple[str, str]]]:
        """Correct `text`. Returns (corrected, [(before, after), ...]).

        `app` (a bundle id) and `language` select scoped entries; without
        them only global entries apply.
        """
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
            rules = [(p, c) for p, c, e in self._rules
                     if self.in_scope(e, app, language)]
            scoped_targets = [t["term"] for t in self.terms
                              if self.in_scope(t, app, language)]
        out = text
        for pattern, correct in rules:
            out = sub_one(pattern, correct, out)

        if self.fuzzy.get("enabled"):
            # Line by line, keeping each line's indent: the fuzzy pass works
            # on whitespace tokens and rejoins them with single spaces, which
            # used to flatten a list into one line once 0.4 started
            # re-applying the dictionary after the cleanup model.
            lines = []
            for line in out.split("\n"):
                indent = line[:len(line) - len(line.lstrip())]
                fixed, fuzzy_changes = self._apply_fuzzy(line.strip(), scoped_targets)
                changes.extend(fuzzy_changes)
                lines.append(indent + fixed if fixed else line)
            out = "\n".join(lines)
        return out, changes

    def _apply_fuzzy(self, text: str, targets: list[str] | None = None):
        """Catch near-misses the variant list does not cover.

        Deliberately conservative: only n-grams of at least `min_chars`, only
        above `threshold`, and never touching a token that already matches a
        known term exactly. Over-eager fuzzy matching corrupts good text, which
        is far worse than leaving one word mis-transcribed.
        """
        threshold = float(self.fuzzy.get("threshold", 0.90))
        max_words = int(self.fuzzy.get("max_words", 4))
        min_chars = int(self.fuzzy.get("min_chars", 6))
        if targets is None:
            targets = [t["term"] for t in self.terms]
        known = {t.lower() for t in targets}
        known |= {re.sub(r"[^\w]", "", t.lower()) for t in targets}

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
                # A "correction" identical to what was said is not a change.
                if best and score >= threshold and best.lower() != low:
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

    # --- decoder priming -------------------------------------------------
    def terms_list(self, app: str | None = None,
                   language: str | None = None) -> list[str]:
        """Your preferred spellings, for casing and the cleanup model's hints."""
        self.load()
        return [t["term"] for t in self.terms if self.in_scope(t, app, language)]

    # --- import / export ---------------------------------------------------
    CSV_FIELDS = ("term", "variants", "type", "hint", "apps", "languages", "match_case")

    def export(self, fmt: str = "json") -> str:
        """The whole vocabulary as JSON or CSV text. Lists in CSV cells are
        separated by '; ' -- commas are common inside the terms themselves."""
        self.load()
        if fmt == "json":
            return json.dumps({"terms": self.terms}, indent=2, ensure_ascii=False) + "\n"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(self.CSV_FIELDS)
        for t in self.terms:
            w.writerow([
                t.get("term", ""), "; ".join(t.get("variants", []) or []),
                t.get("type", ""), t.get("hint", ""),
                "; ".join(t.get("apps", []) or []),
                "; ".join(t.get("languages", []) or []),
                "" if t.get("match_case", True) else "false",
            ])
        return buf.getvalue()

    @staticmethod
    def parse_import(text: str) -> list[dict]:
        """Entries from JSON (a {"terms": [...]} object or a bare list) or CSV
        with a header row. Unknown columns are ignored; a row without a term
        is skipped."""
        text = text.lstrip("\ufeff")
        stripped = text.strip()
        if stripped.startswith(("{", "[")):
            data = json.loads(stripped)
            items = data.get("terms", []) if isinstance(data, dict) else data
            out = []
            for t in items:
                if isinstance(t, dict) and str(t.get("term", "")).strip():
                    out.append(Dictionary._clean_entry(t))
            return out
        out = []
        for row in csv.DictReader(io.StringIO(text)):
            if not (row.get("term") or "").strip():
                continue
            split = lambda v: [x.strip() for x in (v or "").split(";") if x.strip()]  # noqa: E731
            entry = {"term": row["term"].strip(), "variants": split(row.get("variants"))}
            for key in ("type", "hint"):
                if (row.get(key) or "").strip():
                    entry[key] = row[key].strip()
            for key in ("apps", "languages"):
                if split(row.get(key)):
                    entry[key] = split(row.get(key))
            if (row.get("match_case") or "").strip().lower() in ("false", "no", "0"):
                entry["match_case"] = False
            out.append(entry)
        return out

    @staticmethod
    def _clean_entry(t: dict) -> dict:
        entry = {"term": str(t["term"]).strip(),
                 "variants": [str(v).strip() for v in t.get("variants", []) or []
                              if str(v).strip()]}
        for key in ("type", "hint"):
            if isinstance(t.get(key), str) and t[key].strip():
                entry[key] = t[key].strip()
        for key in ("apps", "languages"):
            if isinstance(t.get(key), list) and t[key]:
                entry[key] = [str(x) for x in t[key] if str(x).strip()]
        if t.get("match_case") is False:
            entry["match_case"] = False
        return entry

    def merge(self, entries: list[dict]) -> tuple[int, int]:
        """Add or update entries by term (case-insensitive), writing the file
        atomically and keeping every other key in it. Returns (added,
        updated). Variants are unioned rather than replaced, so importing a
        colleague's list never loses what you taught Halo yourself."""
        self.load()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        terms = [t for t in data.get("terms", []) if isinstance(t, dict)]
        index = {str(t.get("term", "")).lower(): t for t in terms}
        added = updated = 0
        for e in entries:
            key = e["term"].lower()
            if key in index:
                cur = index[key]
                before = json.dumps(cur, sort_keys=True)
                seen = {v.lower() for v in cur.get("variants", [])}
                cur.setdefault("variants", []).extend(
                    v for v in e.get("variants", []) if v.lower() not in seen)
                for k, v in e.items():
                    if k not in ("term", "variants"):
                        cur[k] = v
                if json.dumps(cur, sort_keys=True) != before:
                    updated += 1
            else:
                terms.append(e)
                index[key] = e
                added += 1
        data["terms"] = terms
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(self.path)
        self._mtime = None
        self.load()
        return added, updated

    def whisper_prompt(self, limit: int = 48) -> str:
        """Terms as a bare comma-separated list, for whisper's --prompt.

        Deliberately not the sentence prompt_context() builds: whisper is not
        instruction-following, it is conditioning its next-token distribution
        on this text, so English scaffolding ("keep these exactly as written")
        only dilutes the terms with tokens it already predicts well.
        """
        self.load()
        names = [t["term"] for t in self.terms][:limit]
        return ", ".join(names) + "." if names else ""

    # --- prompt context -------------------------------------------------
    def prompt_context(self, limit: int = 60) -> str:
        """Preferred spellings for the cleanup model's system prompt."""
        self.load()
        names = [t["term"] for t in self.terms][:limit]
        if not names:
            return ""
        return ("Preferred spellings (keep these EXACTLY as written if they "
                "appear): " + ", ".join(names) + ".")
