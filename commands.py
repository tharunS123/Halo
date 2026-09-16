"""Voice commands: speak an instruction and the app acts, instead of typing it.

Detection runs on the raw transcript BEFORE cleanup, because cleanup would
happily rewrite "scratch that" into prose.

Adding a command:
  1. add an entry to commands.json with an `action` and the phrases you say
  2. add a handler for that action in Commands.HANDLERS below
Nothing else needs to change.
"""
import difflib
import json
import re
import threading

import config
from snippets import normalize


class Command:
    """A detected command. `action` says what to do; `argument` carries any
    free text (used by the AI command)."""

    def __init__(self, action: str, argument: str = "", score: float = 1.0):
        self.action = action
        self.argument = argument
        self.score = score

    def __repr__(self):
        arg = f" {self.argument!r}" if self.argument else ""
        return f"<Command {self.action}{arg} @{self.score:.2f}>"


class Commands:
    # Actions this build understands. Anything else in commands.json is
    # reported as unknown rather than silently ignored.
    KNOWN = {"undo", "newline", "paragraph", "privacy_on", "privacy_off"}

    def __init__(self, path=None):
        self.path = path or config.COMMANDS_FILE
        self._lock = threading.Lock()
        self._mtime = None
        self.entries: list[tuple[str, list[str]]] = []
        self.ai_prefixes: list[str] = []
        self.threshold = 0.87
        self.max_words = 6
        self.load()

    def load(self) -> bool:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            if self._mtime == mtime and self.entries:
                return True
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[commands] could not parse {self.path}: {e}")
                return False
            m = data.get("match", {})
            self.threshold = float(m.get("threshold", 0.87))
            self.max_words = int(m.get("max_words", 6))
            self.entries = []
            for c in data.get("commands", []):
                action = c.get("action")
                phrases = [p for p in c.get("phrases", []) if p.strip()]
                if not action or not phrases:
                    continue
                if action not in self.KNOWN:
                    print(f"[commands] unknown action {action!r} in {self.path.name}")
                    continue
                self.entries.append((action, phrases))
            self.ai_prefixes = [normalize(p) for p in data.get("ai_prefixes", [])
                                if p.strip()]
            self._mtime = mtime
        return True

    def detect(self, transcript: str) -> Command | None:
        """Return a Command if the transcript IS one, else None."""
        self.load()
        text = normalize(transcript)
        if not text:
            return None

        # 1. "hey halo, <instruction>" -- checked first, because the
        #    instruction that follows may itself contain command-like words.
        ai = self._detect_ai(text)
        if ai:
            return ai

        # 2. Fixed commands. Whole-utterance only: "scratch that" inside a
        #    sentence is dictation, not an instruction.
        if len(text.split()) > self.max_words:
            return None
        best, best_action, best_score = None, None, 0.0
        for action, phrases in self.entries:
            for phrase in phrases:
                p = normalize(phrase)
                if text == p:
                    return Command(action, score=1.0)
                score = difflib.SequenceMatcher(None, text, p).ratio()
                if score > best_score:
                    best, best_action, best_score = phrase, action, score
        if best_action and best_score >= self.threshold:
            return Command(best_action, score=best_score)
        return None

    def _detect_ai(self, text: str) -> Command | None:
        """Match a wake prefix, tolerating whisper mishearing 'halo'."""
        for prefix in self.ai_prefixes:
            if not prefix:
                continue
            if text.startswith(prefix + " "):
                return Command("ai", text[len(prefix):].strip(), 1.0)
            # Fuzzy on just the opening words, so a mangled wake phrase still
            # lands but the instruction itself is preserved verbatim.
            n = len(prefix.split())
            head = " ".join(text.split()[:n])
            rest = " ".join(text.split()[n:])
            if rest and difflib.SequenceMatcher(None, head, prefix).ratio() >= 0.85:
                return Command("ai", rest.strip(), 0.9)
        return None
