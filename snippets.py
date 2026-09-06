"""Voice-triggered text expansion.

If the whole transcript is (close to) a stored trigger, we inject the stored
text verbatim and skip cleanup entirely -- so a snippet is both instant and
fully local, regardless of Privacy Mode.
"""
import difflib
import json
import re
import threading

import config


def normalize(s: str) -> str:
    """Spoken triggers arrive with stray punctuation and casing from whisper."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Snippet:
    def __init__(self, trigger: str, text: str, aliases=None):
        self.trigger = trigger
        self.text = text
        self.aliases = aliases or []

    @property
    def phrases(self) -> list[str]:
        return [self.trigger] + list(self.aliases)

    def __repr__(self):
        return f"<Snippet {self.trigger!r}>"


class Snippets:
    def __init__(self, path=None):
        self.path = path or config.SNIPPETS_FILE
        self._lock = threading.Lock()
        self._mtime = None
        self.items: list[Snippet] = []
        self.threshold = 0.84
        self.max_trigger_words = 8
        self.load()

    def load(self) -> bool:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            if self._mtime == mtime and self.items:
                return True
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[snippets] could not parse {self.path}: {e}")
                return False
            m = data.get("match", {})
            self.threshold = float(m.get("threshold", 0.84))
            self.max_trigger_words = int(m.get("max_trigger_words", 8))
            self.items = [
                Snippet(s["trigger"], s["text"], s.get("aliases"))
                for s in data.get("snippets", [])
                if s.get("trigger") and s.get("text")
            ]
            self._mtime = mtime
        return True

    def match(self, transcript: str):
        """Return (Snippet, score) if the transcript IS a trigger, else None.

        Deliberately whole-utterance only: expanding on a trigger buried inside
        a sentence would make ordinary dictation unpredictable.
        """
        self.load()
        text = normalize(transcript)
        if not text:
            return None
        # A long utterance is dictation, not a trigger.
        if len(text.split()) > self.max_trigger_words:
            return None

        best, best_score = None, 0.0
        for snip in self.items:
            for phrase in snip.phrases:
                p = normalize(phrase)
                if not p:
                    continue
                if text == p:
                    return snip, 1.0
                score = difflib.SequenceMatcher(None, text, p).ratio()
                if score > best_score:
                    best, best_score = snip, score
        if best and best_score >= self.threshold:
            return best, best_score
        return None

    @property
    def triggers(self) -> list[str]:
        return [s.trigger for s in self.items]
