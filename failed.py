"""The last dictation that did not make it -- kept so it can be tried again.

Before 0.4 a failed transcription deleted its recording on the spot, and a
failed insertion left the text on the clipboard and nowhere else unless
History happened to be on. Either way the only copy of what you said could
be gone before you had read the error.

Now the most recent failure is kept, whatever the History setting:

  - its audio, in the recovery folder (0700 folder, 0600 file), so whisper
    can be run again -- unless Privacy Mode was on, which keeps no audio
  - its transcript and cleaned text, in memory only
  - where it failed and why, in words for the orb and Settings

and the Settings window and the menu bar can Retry Transcription, Retry
Cleanup, Retry Insertion, Copy or Discard it over the control socket.

It lasts until it is retried successfully, discarded, replaced by the next
failure, or 30 minutes pass. A small metadata file beside the audio (stage,
reason, language, app name -- never text) lets an engine that crashed and
restarted offer the audio back.
"""
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field

import paths

MAX_AGE = 30 * 60

STAGES = ("transcription", "cleanup", "insertion", "recovered")


@dataclass
class Failed:
    stage: str                  # transcription | cleanup | insertion | recovered
    reason: str                 # short, for people: "you switched apps"
    language: str = ""
    raw: str = ""               # what whisper heard, if it got that far
    text: str = ""              # the cleaned text, if it got that far
    audio: str | None = None    # path of the kept clip, if any
    duration: float | None = None
    app_name: str = ""
    bundle_id: str = ""
    at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __repr__(self) -> str:
        # Never the words: an accidental log(f"{failed}") must stay safe.
        return (f"<Failed {self.stage}: {self.reason!r}, raw={len(self.raw)} chars, "
                f"text={len(self.text)} chars, audio={'yes' if self.audio else 'no'}>")

    def summary(self, with_text: bool = False) -> dict:
        """For the control socket. Text only when the caller asks for it --
        the Settings window, which shows it to you -- never in health."""
        out = {"id": self.id, "stage": self.stage, "reason": self.reason,
               "at": self.at, "language": self.language, "app": self.app_name,
               "has_audio": bool(self.audio and os.path.exists(self.audio)),
               "has_raw": bool(self.raw), "has_text": bool(self.text or self.raw)}
        if with_text:
            out.update(raw=self.raw, text=self.text)
        return out


class Keeper:
    """Holds at most one Failed, and owns its audio file."""

    def __init__(self, folder=None, on_change=None):
        self.folder = folder or paths.RECOVERY_DIR
        self._lock = threading.Lock()
        self._item: Failed | None = None
        # Called with True when a failure is kept, False when it goes -- so
        # the menu bar can offer it. Outside the lock; must not raise.
        self.on_change = on_change

    def _notify(self, had: bool, has: bool) -> None:
        if had != has and self.on_change is not None:
            try:
                self.on_change(has)
            except Exception:
                pass

    @property
    def audio_path(self):
        return self.folder / "failed.wav"

    @property
    def meta_path(self):
        return self.folder / "failed.json"

    def current(self) -> Failed | None:
        with self._lock:
            had = self._item is not None
            if had and time.time() - self._item.at > MAX_AGE:
                self._drop_locked()
            item = self._item
        self._notify(had, item is not None)
        return item

    def keep(self, item: Failed, wav: str | None = None, keep_audio: bool = True) -> Failed:
        """Remember `item`, copying `wav` beside it when allowed. Replaces
        whatever was kept before. Never raises: failing to keep a failure
        must not become a second failure."""
        with self._lock:
            self._drop_locked()
            self._keep_locked(item, wav, keep_audio)
        self._notify(False, True)
        return item

    def _keep_locked(self, item: Failed, wav, keep_audio: bool) -> None:
        item.audio = None
        if wav and keep_audio and os.path.exists(wav):
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                os.chmod(self.folder, 0o700)
                shutil.copyfile(wav, self.audio_path)
                os.chmod(self.audio_path, 0o600)
                item.audio = str(self.audio_path)
            except OSError:
                item.audio = None
        self._item = item
        self._write_meta_locked()

    def update(self, **fields) -> Failed | None:
        with self._lock:
            if self._item is None:
                return None
            for k, v in fields.items():
                setattr(self._item, k, v)
            self._write_meta_locked()
            return self._item

    def discard(self) -> None:
        with self._lock:
            had = self._item is not None
            self._drop_locked()
        self._notify(had, False)

    def restore(self) -> Failed | None:
        """After a restart: offer back the audio a previous engine kept.
        The text was in that engine's memory and is gone; the audio is not."""
        with self._lock:
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = None
            if not meta or not self.audio_path.exists() or \
                    time.time() - float(meta.get("at", 0)) > MAX_AGE:
                self._drop_locked()
                return None
            self._item = Failed(
                stage=meta.get("stage") if meta.get("stage") in STAGES else "recovered",
                reason=str(meta.get("reason") or "Halo restarted"),
                language=str(meta.get("language") or ""),
                app_name=str(meta.get("app") or ""),
                duration=meta.get("duration"),
                at=float(meta.get("at", time.time())),
                audio=str(self.audio_path))
            item = self._item
        self._notify(False, True)
        return item

    def _write_meta_locked(self) -> None:
        item = self._item
        if item is None or not item.audio:
            try:
                self.meta_path.unlink()
            except OSError:
                pass
            return
        try:
            self.meta_path.write_text(json.dumps({
                "stage": item.stage, "reason": item.reason, "at": item.at,
                "language": item.language, "app": item.app_name,
                "duration": item.duration}), encoding="utf-8")
            os.chmod(self.meta_path, 0o600)
        except OSError:
            pass

    def _drop_locked(self) -> None:
        self._item = None
        for p in (self.audio_path, self.meta_path):
            try:
                p.unlink()
            except OSError:
                pass
