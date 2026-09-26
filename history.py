"""Dictation history: off unless you turn it on, and only on this Mac.

When `history.enabled` is on, each dictation is kept in
~/Library/Application Support/Halo/history.sqlite3 (0600) with: when, how
long, the app, the language, what whisper heard, what was typed, the cleanup
mode, whether it landed, and why not if it did not. That is what Settings >
History searches, copies, reinserts and retries.

Never kept, whatever the settings:
  - anything around the cursor (Context Awareness is in-memory only)
  - dictation into a password or other secure field
  - anything in the diagnostic log, which records lengths, not words

Audio is a separate switch (`history.keep_audio`) with its own retention,
because a recording of your voice is a different thing to keep than text.
It is what makes "retry transcription" possible after a model upgrade.

Retention is applied on every write and hourly: never | 1h | 24h | 7d |
30d | forever. "never" keeps nothing -- the same as off.
"""
import os
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass

import config
import paths

_SECONDS = {"never": 0, "1h": 3600, "24h": 86400, "7d": 7 * 86400,
            "30d": 30 * 86400, "forever": None}

SCHEMA = """
CREATE TABLE IF NOT EXISTS dictations (
    id          TEXT PRIMARY KEY,
    created     REAL NOT NULL,
    duration    REAL,
    app_name    TEXT,
    bundle_id   TEXT,
    language    TEXT,
    raw         TEXT,
    cleaned     TEXT,
    mode        TEXT,
    status      TEXT,
    reason      TEXT,
    audio       TEXT
);
CREATE INDEX IF NOT EXISTS dictations_created ON dictations(created);
"""


@dataclass
class Item:
    id: str
    created: float
    duration: float | None
    app_name: str
    bundle_id: str
    language: str
    raw: str
    cleaned: str
    mode: str
    status: str
    reason: str
    audio: str | None

    def __repr__(self):           # never print the words by accident
        return f"<history.Item {self.id} {self.status} {len(self.raw or '')}ch>"


class History:
    def __init__(self, db_path=None, audio_dir=None):
        self.db_path = db_path or paths.HISTORY_DB
        self.audio_dir = audio_dir or paths.HISTORY_AUDIO_DIR
        self._lock = threading.Lock()
        self._last_prune = 0.0

    # --- plumbing ------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.db_path.exists()
        conn = sqlite3.connect(self.db_path, timeout=5)
        if new:
            os.chmod(self.db_path, 0o600)
        conn.executescript(SCHEMA)
        return conn

    @staticmethod
    def enabled() -> bool:
        return config.HISTORY_ENABLED and config.HISTORY_RETENTION != "never"

    @staticmethod
    def audio_enabled() -> bool:
        return (History.enabled() and config.HISTORY_KEEP_AUDIO
                and config.HISTORY_AUDIO_RETENTION != "never")

    # --- writing ---------------------------------------------------------------
    def add(self, *, raw: str, cleaned: str, mode: str, status: str,
            reason: str = "", duration: float | None = None, app_name: str = "",
            bundle_id: str = "", language: str = "", wav: str | None = None,
            secure: bool = False) -> str | None:
        """Record one dictation. Returns its id, or None when nothing was
        kept (history off, or a secure field)."""
        if not self.enabled() or secure:
            return None
        item_id = uuid.uuid4().hex[:16]
        audio = None
        if wav and self.audio_enabled() and os.path.exists(wav):
            try:
                self.audio_dir.mkdir(parents=True, exist_ok=True)
                os.chmod(self.audio_dir, 0o700)
                dest = self.audio_dir / f"{item_id}.wav"
                shutil.copyfile(wav, dest)
                os.chmod(dest, 0o600)
                audio = str(dest)
            except OSError:
                audio = None
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO dictations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item_id, time.time(), duration, app_name, bundle_id, language,
                     raw, cleaned, mode, status, reason, audio))
                conn.commit()
            finally:
                conn.close()
        self.prune()
        return item_id

    def update(self, item_id: str, **fields) -> None:
        allowed = {"cleaned", "raw", "status", "reason", "mode", "language"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    f"UPDATE dictations SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                    (*sets.values(), item_id))
                conn.commit()
            finally:
                conn.close()

    # --- reading ---------------------------------------------------------------
    def get(self, item_id: str) -> Item | None:
        rows = self._query("SELECT * FROM dictations WHERE id=?", (item_id,))
        return rows[0] if rows else None

    def search(self, text: str = "", limit: int = 200) -> list[Item]:
        if text:
            like = f"%{text}%"
            return self._query(
                "SELECT * FROM dictations WHERE raw LIKE ? OR cleaned LIKE ? OR app_name LIKE ? "
                "ORDER BY created DESC LIMIT ?", (like, like, like, limit))
        return self._query("SELECT * FROM dictations ORDER BY created DESC LIMIT ?", (limit,))

    def _query(self, sql, args) -> list[Item]:
        if not self.db_path.exists():
            return []
        with self._lock:
            conn = self._connect()
            try:
                return [Item(*row) for row in conn.execute(sql, args).fetchall()]
            finally:
                conn.close()

    # --- deleting ----------------------------------------------------------------
    def delete(self, item_id: str) -> None:
        item = self.get(item_id)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM dictations WHERE id=?", (item_id,))
                conn.commit()
            finally:
                conn.close()
        if item and item.audio:
            _unlink(item.audio)

    def clear(self) -> None:
        """Everything: rows, audio, and the database file itself."""
        with self._lock:
            for suffix in ("", "-wal", "-shm", "-journal"):
                _unlink(str(self.db_path) + suffix)
            shutil.rmtree(self.audio_dir, ignore_errors=True)

    def prune(self, now: float | None = None) -> int:
        """Apply retention. Returns rows removed. Runs on every write and at
        most hourly otherwise."""
        now = now or time.time()
        if not self.db_path.exists():
            return 0
        if not self.enabled():
            # Turned off: keep nothing. Off means off.
            self.clear()
            return -1
        removed = 0
        text_age = _SECONDS[config.HISTORY_RETENTION]
        audio_age = _SECONDS[config.HISTORY_AUDIO_RETENTION] if config.HISTORY_KEEP_AUDIO else 0
        with self._lock:
            conn = self._connect()
            try:
                if text_age is not None:
                    for (audio,) in conn.execute(
                            "SELECT audio FROM dictations WHERE created < ?", (now - text_age,)):
                        if audio:
                            _unlink(audio)
                    removed = conn.execute("DELETE FROM dictations WHERE created < ?",
                                           (now - text_age,)).rowcount
                cutoff = now - audio_age if audio_age is not None else None
                if cutoff is not None:
                    for (item_id, audio) in conn.execute(
                            "SELECT id, audio FROM dictations WHERE audio IS NOT NULL AND created < ?",
                            (cutoff,)).fetchall():
                        _unlink(audio)
                        conn.execute("UPDATE dictations SET audio=NULL WHERE id=?", (item_id,))
                conn.commit()
            finally:
                conn.close()
        self._last_prune = now
        return removed

    def maybe_prune(self) -> None:
        if time.time() - self._last_prune > 3600:
            self.prune()


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
