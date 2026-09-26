"""Vocabulary learning: notice when you fix a word Halo typed, and offer to
remember it.

Halo types "Super Base". You change it to "Supabase". Next time it should
just type Supabase -- but only if you say so. So this module never edits the
dictionary; it SUGGESTS, and Settings > Dictionary has Accept and Dismiss.

How a correction is noticed: shortly after an insertion (10s and 40s later,
and when you start the next dictation), Halo re-reads the same field --
only the inserted stretch plus a few dozen characters, only if Context
Awareness and learning are on, never in a secure field -- and compares it
with what it typed. The comparison is word by word, and most edits are not
vocabulary corrections at all, so most are thrown away:

  - a rewrite: over half the words changed, or under half survived
  - a content change: "John" -> "Jake" sounds nothing alike (similarity of
    the letters < 0.6); that is you changing your mind, not whisper
    mishearing
  - grammar: "there" -> "their" swaps one ordinary word for another
  - anything bigger than three words on either side

What survives gets a confidence from how alike the two sound in letters, how
term-like the new form is (capitals, digits, not in the word list), and how
often you have made the same fix. At 0.7 it becomes a suggestion; the orb
mentions it once.

Nothing here is written to the log, and the re-read text is discarded as
soon as it has been compared.
"""
import difflib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass

import paths
from backtrack import is_common

THRESHOLD = 0.7
WINDOW_EXTRA = 40
CHECK_AFTER = (10.0, 40.0)
MAX_AGE = 120.0


@dataclass
class Suggestion:
    heard: str             # what Halo typed
    correct: str           # what you changed it to
    confidence: float
    count: int = 1
    kind: str = "spelling"  # spelling | case
    app: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0
    status: str = "pending"  # pending | accepted | dismissed

    @property
    def key(self) -> str:
        return f"{self.heard.lower()}→{self.correct}"


_WORD = re.compile(r"[\w][\w'’.+#-]*[\w+#]|[\w]")


def _letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _termish(s: str) -> bool:
    return (any(c.isupper() for c in s[1:]) or any(c.isdigit() for c in s)
            or any(not is_common(w) for w in s.split())
            or (s[:1].isupper() and len(s.split()) > 1))


def find_corrections(inserted: str, current: str) -> list[tuple[str, str, float, str]]:
    """(heard, correct, score, kind) for each likely vocabulary fix of
    `inserted` found in `current` (the field's text from the insertion point
    on). Empty for rewrites, content changes and grammar edits."""
    if not inserted or current is None:
        return []
    a = _WORD.findall(inserted)
    # Only as much of the field as could be the inserted stretch.
    b_all = _WORD.findall(current)
    b = b_all[:len(a) + 3]
    if not a or not b:
        return []
    sm = difflib.SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b],
                                 autojunk=False)
    blocks = sm.get_opcodes()
    kept = sum(i2 - i1 for tag, i1, i2, _, _ in blocks if tag == "equal")
    # Trailing words you added after the insertion are not edits of it.
    while blocks and blocks[-1][0] == "insert":
        blocks.pop()
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in blocks if tag != "equal")
    case_only = [(a[i1:i2], b[j1:j2]) for tag, i1, i2, j1, j2 in blocks
                 if tag == "equal" and a[i1:i2] != b[j1:j2]]

    out = []
    # Case-only differences hide inside "equal" blocks (matching ignored case).
    for olds, news in case_only:
        for o, n in zip(olds, news, strict=True):
            if o != n and o.lower() == n.lower() and _termish(n):
                out.append((o, n, 0.8, "case"))
    # Half the words kept, half at most changed. Tighter than that and a
    # two-word fix in a five-word sentence ("post grass" -> "Postgres") reads
    # as a rewrite; the letter-similarity test below is what stops content
    # changes getting through.
    if len(a) >= 3 and (changed / len(a) > 0.5 or kept / len(a) < 0.5):
        return out                                  # a rewrite, not a fix
    for tag, i1, i2, j1, j2 in blocks:
        if tag != "replace":
            continue
        old, new = a[i1:i2], b[j1:j2]
        if not (1 <= len(old) <= 3 and 1 <= len(new) <= 3):
            continue
        heard, correct = " ".join(old), " ".join(new)
        sim = difflib.SequenceMatcher(None, _letters(heard), _letters(correct)).ratio()
        if sim < 0.6:
            continue                                # changed your mind, not a mishearing
        if not _termish(correct) and all(is_common(w) for w in old):
            continue                                # grammar: word for word
        score = sim + (0.15 if _termish(correct) else 0.0)
        out.append((heard, correct, min(score, 0.95), "spelling"))
    return out


class Learner:
    """Holds pending checks (in memory) and suggestions (suggestions.json)."""

    def __init__(self, path=None, dictionary=None, notify=None):
        self.path = path or paths.SUGGESTIONS_FILE
        self.dictionary = dictionary
        self.notify = notify or (lambda s: None)
        self._lock = threading.Lock()
        self._pending: list = []      # insertion.Records awaiting a re-read

    # --- storage -----------------------------------------------------------
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def suggestions(self, status: str | None = "pending") -> list[Suggestion]:
        items = []
        for raw in self._read().get("suggestions", []):
            try:
                s = Suggestion(**raw)
            except TypeError:
                continue
            if status is None or s.status == status:
                items.append(s)
        return items

    def _known(self, heard: str, correct: str) -> bool:
        if self.dictionary is None:
            return False
        self.dictionary.load()
        for t in self.dictionary.terms:
            if t["term"] == correct and (heard.lower() in [v.lower() for v in
                                                           self.dictionary.spoken_forms(t)]
                                         or heard.lower() == correct.lower()):
                return True
        return False

    def record(self, heard: str, correct: str, score: float, kind: str,
               app: str = "") -> Suggestion | None:
        """Add or strengthen a suggestion. Returns it when it newly crosses
        the threshold (so the orb can mention it once)."""
        if self._known(heard, correct):
            return None
        with self._lock:
            data = self._read()
            items = data.get("suggestions", [])
            now = time.time()
            key = f"{heard.lower()}→{correct}"
            for raw in items:
                s = Suggestion(**raw)
                if s.key == key:
                    if s.status != "pending":
                        return None                 # dismissed or accepted: stay quiet
                    was = s.confidence
                    s.count += 1
                    s.last_seen = now
                    s.confidence = min(0.99, max(s.confidence, score) + 0.1)
                    raw.update(asdict(s))
                    self._write(data)
                    return s if was < THRESHOLD <= s.confidence else None
            s = Suggestion(heard, correct, round(score, 2), 1, kind, app, now, now)
            items.append(asdict(s))
            data["suggestions"] = items[-200:]
            self._write(data)
            return s if s.confidence >= THRESHOLD else None

    def set_status(self, heard: str, correct: str, status: str) -> None:
        with self._lock:
            data = self._read()
            key = f"{heard.lower()}→{correct}"
            for raw in data.get("suggestions", []):
                if Suggestion(**raw).key == key:
                    raw["status"] = status
            self._write(data)

    def accept(self, heard: str, correct: str) -> None:
        """Add to the dictionary: `correct` as the term, `heard` as a variant."""
        if self.dictionary is not None:
            entry = {"term": correct, "variants": [] if heard.lower() == correct.lower()
                     else [heard]}
            self.dictionary.merge([entry])
        self.set_status(heard, correct, "accepted")

    # --- watching insertions -------------------------------------------------
    def watch(self, rec) -> None:
        if rec is None or rec.secure or rec.element is None or rec.range is None:
            return
        with self._lock:
            self._pending = [r for r in self._pending if time.time() - r.at < MAX_AGE][-4:]
            self._pending.append(rec)

    def check_due(self, ax, force: bool = False) -> list[Suggestion]:
        """Re-read the fields of recent insertions that are due a look.
        `force` is used at key-down: look now, whatever the schedule."""
        now = time.time()
        with self._lock:
            due = []
            for r in self._pending:
                age = now - r.at
                checks = getattr(r, "_checks", 0)
                if age > MAX_AGE:
                    continue
                if force or (checks < len(CHECK_AFTER) and age >= CHECK_AFTER[checks]):
                    r._checks = checks + 1
                    due.append(r)
            self._pending = [r for r in self._pending if now - r.at <= MAX_AGE
                             and getattr(r, "_checks", 0) < len(CHECK_AFTER)]
        fresh = []
        for r in due:
            try:
                text = self._read_region(ax, r)
            except Exception:
                text = None
            if text is None:
                continue
            for heard, correct, score, kind in find_corrections(r.text, text):
                s = self.record(heard, correct, score, kind, r.bundle_id)
                if s is not None:
                    fresh.append(s)
                    self.notify(s)
            del text
        return fresh

    @staticmethod
    def _read_region(ax, r) -> str | None:
        loc = r.range[0]
        length = len(r.text) + WINDOW_EXTRA
        text = ax.string_for_range(r.element, loc, length)
        if text is None:
            value = ax.attr(r.element, "AXValue")
            if isinstance(value, str) and len(value) <= 5000:
                text = value[loc:loc + length]
        return text
