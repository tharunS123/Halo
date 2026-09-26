"""Halo -- hold a key, speak, release, get cleaned text at the cursor.

Pipeline:  mic -> whisper.cpp (local) -> cleanup (rules, then a model on this
           Mac or OpenRouter) -> verified insertion into the app you started in
"""
import json
import os
import re
import shutil
import signal
import sys
import threading
import time
import traceback

from pynput import keyboard

import cleanup
import clipboard
import commands as commands_mod
import config
import context as context_mod
import control
import dictionary
import history as history_mod
import insertion
import languages
import learning as learning_mod
import local_llm
import logsafe
import pipeline
import privacy as privacy_mod
import snippets as snippets_mod
import overlay as overlay_mod
import paths
import permissions
import settings as settings_mod
import transcribe
import transforms as transforms_mod
from audio import Recorder

C_DIM, C_OK, C_WARN, C_ERR, C_RST = "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


HEADLESS = os.environ.get("HALO_OVERLAY_CHILD") == "1" or not sys.stdout.isatty()

# Exit code meaning "misconfigured, do not restart me" -- the supervisor honours
# this so a missing permission does not become a crash-restart loop.
EXIT_CONFIG = 78

# A clip left behind by a crash is offered back for this long.
RECOVERY_MAX_AGE = 30 * 60


def setup_logging():
    """In background mode there is no terminal, so send output to a log file."""
    if not HEADLESS:
        return
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Deliberately not a context manager: this handle has to outlive the
        # function, because it becomes stdout/stderr for the whole process.
        f = open(config.ENGINE_LOG, "a", buffering=1, encoding="utf-8")
        sys.stdout = f
        sys.stderr = f
        print(f"\n=== engine start {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    except OSError:
        pass  # keep running even if the log is unwritable


def log(stage: str, msg: str, color: str = ""):
    print(f"{C_DIM}[{time.strftime('%H:%M:%S')}]{C_RST} "
          f"{color}{stage:<12}{C_RST} {msg}", flush=True)


def resolve_hotkey(name: str):
    key = getattr(keyboard.Key, name.lower(), None)
    if key is None:
        sys.exit(f"Unknown hotkey {name!r}. Use e.g. f9, f13, f12.")
    return key


def friendly(e: BaseException) -> str:
    """A short message for the orb. Never a traceback, never dictated text."""
    text = str(e)
    if isinstance(e, transcribe.TranscriptionError):
        if "damaged" in text:
            return "Speech model damaged"
        if "timed out" in text:
            return "Transcription timed out"
        return "Transcription failed"
    if "PortAudio" in text or "device" in text.lower():
        return "Microphone unavailable"
    return "Something went wrong"


def log_exception(where: str, e: BaseException):
    """Diagnostics without content: the exception type and where it happened.
    Messages can quote the text being handled, so they appear only in debug
    mode."""
    frames = traceback.extract_tb(e.__traceback__)[-4:]
    trail = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}"
                        for f in reversed(frames))
    detail = f": {e}" if config.DEBUG_LOG_CONTENT else ""
    log("ERROR", f"{where}: {type(e).__name__}{detail} at {trail}", C_ERR)


_LANG_SWITCH = re.compile(
    r"^(?:(?:switch|change|set)\s+(?:the\s+)?(?:language\s+)?to|"
    r"(?:dictate|speak|type|language)\s+in|language)\s+([a-z ]{2,24}?)[.!]?$",
    re.IGNORECASE)


class Halo:
    def __init__(self, ui=None):
        self.recorder = Recorder()
        self.dictionary = dictionary.Dictionary()
        self.snippets = snippets_mod.Snippets()
        self.commands = commands_mod.Commands()
        self.privacy = privacy_mod.Privacy()
        self.history = history_mod.History()
        self.transforms = transforms_mod.Store()
        self.learner = learning_mod.Learner(dictionary=self.dictionary,
                                            notify=self._suggestion_ready)
        # What Halo typed, newest last, in memory only: undo, the AI command,
        # whisper's "previous utterance" priming, and learning use it.
        self.records: list[insertion.Record] = []
        self.hotkey = resolve_hotkey(config.HOTKEY)
        self.held = False
        self.busy = threading.Lock()
        self.stage = "idle"      # idle | recording | transcribing | cleaning | inserting
        self.ui = ui or overlay_mod.NullOverlay()
        self._pump_stop = threading.Event()
        self._pump: threading.Thread | None = None
        # Toggle mode: True between the press that starts and the press that
        # sends. Separate from `held`, which tracks the physical key.
        self.toggled_on = False
        self._auto_stop: threading.Timer | None = None
        self._listener: keyboard.Listener | None = None
        self._watch_stop = threading.Event()
        # The target (and, if Context Awareness is on, the context) for exactly
        # one dictation: captured at key-down, cleared in finish()'s finally or
        # on cancel. Never logged, never written anywhere -- see context.py.
        self._pending: context_mod.Pending | None = None
        self._context: context_mod.Context | None = None
        # Escape sets this at any stage; every stage checks it.
        self._cancel = threading.Event()
        self._command_mode = False
        self._shift = False
        # Keys pressed while Halo itself is typing are not "you typed since".
        self._injecting_until = 0.0
        self._started = time.time()
        self.last_error = ""

    # ------------------------------------------------------------------
    # The level meter
    # ------------------------------------------------------------------
    def _start_level_pump(self):
        """Ship mic levels to the overlay at ~30fps from a NORMAL thread.

        Never from the audio callback: a socket write there could stall the
        audio thread and drop samples.
        """
        self._pump_stop.clear()

        def run():
            while not self._pump_stop.wait(config.OVERLAY_LEVEL_INTERVAL):
                if not self.recorder.recording:
                    break
                self.ui.level(self.recorder.last_level)

        self._pump = threading.Thread(target=run, daemon=True)
        self._pump.start()

    def _stop_level_pump(self):
        self._pump_stop.set()
        self._pump = None

    # ------------------------------------------------------------------
    # Keys (callbacks must return fast; work happens on a thread)
    #
    # Two activation styles share one key. In "hold" the press starts and the
    # release sends, which is the original behaviour and cannot leave the mic
    # open. In "toggle" the release is ignored and the NEXT press sends, which
    # is what makes long dictation and one-handed use bearable -- at the cost
    # of needing `max_recording_sec` as a backstop.
    #
    # Command Mode is the same key with Shift held (or its own key), and
    # Escape cancels whatever stage Halo is in. pynput cannot swallow keys, so
    # the app you are in sees that Escape too.
    # ------------------------------------------------------------------
    def _is_command_key(self, key) -> bool:
        if not config.COMMAND_MODE_ENABLED or not config.COMMAND_HOTKEY:
            return False
        return key == getattr(keyboard.Key, config.COMMAND_HOTKEY, None)

    def on_press(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            self._shift = True
            return
        is_hotkey = key == self.hotkey
        is_command = self._is_command_key(key)
        if not (is_hotkey or is_command):
            if key == keyboard.Key.esc:
                self.escape()
                return
            # Anything else you type makes Halo's last insertion no longer
            # the app's last undo step -- unless Halo is the one typing.
            if time.time() > self._injecting_until and self.records:
                self.records[-1].keys_since += 1
            return

        command = is_command or (config.COMMAND_MODE_ENABLED
                                 and config.COMMAND_TRIGGER == "shift" and self._shift)
        if config.ACTIVATION == "toggle":
            if self.toggled_on:
                self.toggled_on = False
                self._cancel_auto_stop()
                threading.Thread(target=self.finish, daemon=True).start()
            elif not self.busy.locked():
                # Commit only on success -- see start_recording().
                if self.start_recording(command=command):
                    self.toggled_on = True
                    self._arm_auto_stop()
            return

        if not self.held:
            self.held = True
            self.start_recording(command=command)

    def on_release(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            self._shift = False
            return
        if config.ACTIVATION != "hold":
            return
        if (key == self.hotkey or self._is_command_key(key)) and self.held:
            self.held = False
            threading.Thread(target=self.finish, daemon=True).start()

    def escape(self):
        """Cancel whatever is in flight. Safe at any moment: the only thing it
        does is set a flag every stage checks, and stop the microphone."""
        if self.stage == "recording" or self.recorder.recording:
            self.cancel_recording()
        elif self.stage in ("transcribing", "cleaning", "inserting"):
            self._cancel.set()
            log("CANCELLED", f"during {self.stage}", C_WARN)

    def _arm_auto_stop(self):
        """End a toggled recording that nobody came back to."""
        self._cancel_auto_stop()
        t = threading.Timer(config.MAX_RECORDING_SEC, self._auto_stop_fired)
        t.daemon = True
        self._auto_stop = t
        t.start()

    def _cancel_auto_stop(self):
        if self._auto_stop is not None:
            self._auto_stop.cancel()
            self._auto_stop = None

    def _auto_stop_fired(self):
        if not self.toggled_on:
            return
        self.toggled_on = False
        log("TIMEOUT",
            f"toggle hit the {config.MAX_RECORDING_SEC}s limit -- sending", C_WARN)
        threading.Thread(target=self.finish, daemon=True).start()

    # ------------------------------------------------------------------
    # Target and context
    # ------------------------------------------------------------------
    def _begin_context(self, command: bool = False):
        """Read the focused app at key-down, on a thread: the app you are
        dictating into is the one focused NOW, and nothing here may delay
        the microphone. The target is always recorded (safe insertion needs
        it); text only with Context Awareness on."""
        self._clear_context()
        self._pending = context_mod.capture_async(
            config.CONTEXT_APP_OVERRIDES, read_text=config.CONTEXT_ENABLED and not command)

    def _take_context(self) -> context_mod.Context | None:
        pending, self._pending = self._pending, None
        if pending is None:
            return None
        # The capture has had the whole recording (>=0.3s) to finish against
        # a 0.25s budget, so this wait is almost always zero.
        self._context = pending.get(timeout=0.05)
        return self._context

    def _clear_context(self):
        pending, self._pending = self._pending, None
        if pending is not None:
            pending.discard()
        ctx, self._context = self._context, None
        if ctx is not None:
            ctx.clear()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def cancel_recording(self):
        """Throw the clip away. Nothing is transcribed and nothing is typed."""
        self.toggled_on = False
        self.held = False
        self._cancel_auto_stop()
        self._stop_level_pump()
        self._clear_context()
        try:
            wav, _ = self.recorder.stop()
        except Exception:
            wav = None
        if wav and os.path.exists(wav):
            os.unlink(wav)
        self.stage = "idle"
        self.ui.flash("Cancelled")
        log("CANCELLED", "recording discarded", C_WARN)

    def start_recording(self, command: bool = False) -> bool:
        """Returns True only if the microphone actually opened.

        Toggle mode needs the answer: committing `toggled_on` on a failed
        start would arm the auto-stop timer and leave the next key press
        trying to finish a recording that never began, which surfaces as a
        baffling "clip too short (0.00s)".
        """
        if self.busy.locked():
            log("BUSY", "still processing the last clip -- ignoring", C_WARN)
            return False
        # Before the new target is captured: did you fix a word Halo typed?
        self._check_learning(force=True)
        try:
            self.recorder.start()
        except Exception as e:
            self.ui.error("Microphone unavailable")
            self.last_error = "Microphone unavailable"
            log_exception("microphone", e)
            return False
        self._cancel.clear()
        self._command_mode = command
        self.stage = "recording"
        self._begin_context(command)
        # Load the cleanup model while you talk, if it is not loaded.
        local_llm.prewarm("polished" if command else config.CLEANUP_MODE)
        if command:
            self.ui.command()
        else:
            self.ui.listening()
        self._badge_language()
        if self.recorder.device_warning:
            log("MIC", f"{self.recorder.device_warning}; using the system default", C_WARN)
            self.ui.flash("Mic missing: using default")
        self._start_level_pump()
        verb = ("press again" if config.ACTIVATION == "toggle"
                else f"release {config.HOTKEY.upper()}")
        log("RECORDING", f"{'command' if command else 'listening'}... ({verb} to stop)", C_OK)
        return True

    def _badge_language(self):
        """Show the language on the orb when there is more than one to be in."""
        lang = config.WHISPER_LANGUAGE
        if lang != "en" or len(config.LANGUAGES_ENABLED) > 1:
            self.ui.language("AUTO" if lang == "auto" else lang.upper())

    # ------------------------------------------------------------------
    # The whole dictation
    # ------------------------------------------------------------------
    def finish(self):
        if not self.busy.acquire(blocking=False):
            return
        wav = None
        command = self._command_mode
        try:
            self._stop_level_pump()
            wav, dur = self.recorder.stop()
            if wav is None:
                self.ui.hide()
                log("SKIPPED", f"clip too short ({dur:.2f}s)", C_WARN)
                return
            peak = Recorder.peak_level(wav)
            log("RECORDED", f"{dur:.2f}s, peak {peak:.3f}")
            if peak < 0.005:
                # All-zero samples almost always mean the Microphone grant is
                # missing: macOS hands out silence rather than an error.
                self.ui.error("No microphone input")
                log("SKIPPED",
                    "audio is pure silence. Check the microphone in Settings > "
                    "Microphone, and that Halo has Microphone access.", C_WARN)
                return
            self._keep_for_recovery(wav)

            self.stage = "transcribing"
            self.ui.processing()
            target = self._take_context()
            ctx = target if (target is not None and target.text_read) else None
            t0 = time.time()
            log("TRANSCRIBE", "running whisper.cpp locally...")
            previous = self.records[-1].text if self.records else ""
            result = transcribe.transcribe(
                wav, config.WHISPER_LANGUAGE,
                vocabulary=self.dictionary.whisper_prompt(),
                previous=previous,
                context_terms=ctx.terms if ctx is not None else (),
                cancel=self._cancel)
            raw = result.text
            if transcribe.last_warning:
                self.ui.flash(transcribe.last_warning[:40])
            if not raw:
                self.ui.hide()
                log("SKIPPED", "no speech detected", C_WARN)
                return
            log("TRANSCRIBE", f"{time.time()-t0:.2f}s [{result.language}] -> "
                              f"{logsafe.content(raw, 'transcript')}", C_OK)
            if result.confidence is not None and result.confidence < 0.7:
                log("LANGUAGE",
                    f"low confidence ({result.confidence:.2f}) on "
                    f"{result.language!r}; choose the language in Settings to be sure",
                    C_WARN)
            if self._cancel.is_set():
                raise transcribe.Cancelled()

            if command:
                self.command_mode(raw, target)
            else:
                self.dispatch(raw, result.language, ctx, target=target, wav=wav,
                              duration=dur)
            self._drop_recovery()
        except transcribe.Cancelled:
            self._drop_recovery()
            self.ui.flash("Cancelled")
            log("CANCELLED", "nothing was typed", C_WARN)
        except Exception as e:
            # Whatever broke, the next key press must work: log where, show a
            # short message, and fall through to the cleanup below.
            self.last_error = friendly(e)
            log_exception("dictation", e)
            self.ui.error(self.last_error)
            self._drop_recovery()
        finally:
            self._stop_level_pump()
            self._clear_context()
            self._command_mode = False
            self.stage = "idle"
            if wav and os.path.exists(wav):
                os.unlink(wav)
            self.busy.release()

    # ------------------------------------------------------------------
    # Post-transcription pipeline.
    #
    # Order matters and is deliberate:
    #   1. dictionary  -- fix vocabulary first, so everything below matches
    #                     against corrected text (scoped to the app/language)
    #   2. language    -- "switch to Spanish" is an instruction, not text
    #   3. commands    -- before cleanup, which would rewrite "scratch that"
    #                     into prose
    #   4. snippets    -- whole-utterance triggers, fully local
    #   5. dictation   -- pipeline.py: the cleanup mode's rules, then a
    #                     model if one is ready (never OpenRouter in Privacy
    #                     Mode), then fitting the text to the cursor
    #   6. insertion   -- insertion.py: only into the target captured at
    #                     key-down, by the safest method that app supports
    # ------------------------------------------------------------------
    def dispatch(self, raw: str, language: str = "en", ctx=None, target=None,
                 wav=None, duration=None):
        target = target if target is not None else ctx
        app = ctx.bundle_id if ctx is not None else None
        corrected, changes = self.dictionary.apply(raw, app, language)
        if changes:
            log("DICTIONARY", logsafe.count(changes, "fix(es)"), C_OK)

        if self._language_switch(corrected):
            return None

        cmd = self.commands.detect(corrected)
        if cmd is not None:
            log("COMMAND", cmd.action, C_OK)
            return self.run_command(cmd, language, target)

        hit = self.snippets.match(corrected)
        if hit is not None:
            snip, score = hit
            log("SNIPPET", f"@{score:.2f} ({len(snip.text)} chars, local only)", C_OK)
            return self.deliver(snip.text, target, raw=raw, language=language,
                                mode="snippet", wav=wav, duration=duration)

        return self.dictate(corrected, language, ctx, target=target, raw=raw, wav=wav,
                            duration=duration)

    def dictate(self, text: str, language: str, ctx=None, target=None, raw=None,
                wav=None, duration=None):
        # The category and flags only -- never the text context.py read.
        if ctx is not None:
            log("CONTEXT", ctx.summary())
        elif config.CONTEXT_ENABLED:
            log("CONTEXT", "not available for this app")
        mode = config.CLEANUP_MODE
        self.stage = "cleaning"
        result = pipeline.process(
            text, mode=mode, ctx=ctx, language=language,
            dictionary=self.dictionary, privacy=self.privacy.enabled)
        stages = ", ".join(result.stages) or "no changes"
        style = f" [{result.style}]" if result.style else ""
        if result.source in ("local", "openrouter"):
            log("CLEANUP", f"{mode}{style}: {stages} -- {result.model_seconds:.2f}s via "
                           f"{result.detail}", C_OK)
        elif mode != "off":
            log("CLEANUP", f"{stages}{style} -- {result.detail}",
                C_WARN if result.fell_back else C_OK)
        if self._cancel.is_set():
            raise transcribe.Cancelled()
        if not result.text.strip():
            # "...scratch that" with nothing after it: you took it all back.
            self.ui.hide()
            log("SKIPPED", "nothing left to type after the correction", C_WARN)
            return None
        return self.deliver(result.text, target, raw=raw or text, language=language,
                            mode=mode, wav=wav, duration=duration)

    def _language_switch(self, text: str) -> bool:
        """"switch to Spanish", "dictate in French", "language auto"."""
        if len(text.split()) > 6:
            return False
        m = _LANG_SWITCH.match(text.strip())
        if not m:
            return False
        code = languages.from_spoken(m.group(1).strip())
        if not code:
            return False
        self.set_language(code)
        return True

    def set_language(self, code: str):
        try:
            settings_mod.current.set("language", code)
            config.reload()
        except Exception as e:
            log_exception("language", e)
            self.ui.error("Could not switch language")
            return
        languages.remember(code)
        name = languages.name(code)
        log("LANGUAGE", f"now {code}", C_OK)
        warn = transcribe.model_for(code)[1] if code != "en" else None
        self.ui.flash(f"{name}: needs multilingual model" if warn and "multilingual" in warn
                      else f"Language: {name}")
        self._badge_language()

    def run_command(self, cmd, language: str, target=None):
        action = cmd.action

        if action == "undo":
            return self.undo_last()

        if action in ("newline", "paragraph"):
            return self.deliver("\n" if action == "newline" else "\n\n", target,
                                remember=False)

        if action in ("privacy_on", "privacy_off"):
            on = action == "privacy_on"
            self.privacy.set(on)
            self.ui.privacy(on)
            self.ui.flash("Privacy ON" if on else "Privacy OFF")
            log("PRIVACY", f"turned {'ON' if on else 'OFF'} by voice", C_OK)
            return

        if action == "ai":
            # The model on this Mac first, through Command Mode's safe
            # replace (it acts on Halo's last insertion when nothing is
            # selected). OpenRouter only with the same consent cleanup needs.
            if local_llm.local_installed() and target is not None:
                return self.command_mode(cmd.argument, target)
            if not config.CLEANUP_ENABLED:
                self.ui.error("Needs the local model")
                log("COMMAND", "AI command: no local model, and OpenRouter is off", C_WARN)
                return
            if self.privacy.enabled:
                self.ui.error("Blocked: Privacy Mode")
                log("PRIVACY",
                    "AI command needs OpenRouter; refused in Privacy Mode",
                    C_WARN)
                return
            last = self.records[-1] if self.records else None
            if last is None:
                self.ui.error("Nothing to edit yet")
                log("COMMAND", "AI command with no prior dictation", C_WARN)
                return
            log("COMMAND", f"AI: {logsafe.content(cmd.argument, 'instruction')} on "
                           f"{len(last.text)} chars")
            t = time.time()
            res = cleanup.ai_command(cmd.argument, last.text, language)
            if res.source != "llm" or not res.text:
                self.ui.error("AI command failed")
                log("ERROR", f"AI command: {res.detail}", C_ERR)
                return
            log("COMMAND", f"{time.time()-t:.2f}s via {res.detail}", C_OK)
            # Replace rather than append: "make that more formal" means the
            # previous text should go away -- but only if Halo can remove it
            # safely; otherwise say so rather than stacking a second version.
            undone = insertion.undo(last)
            if not undone.ok:
                self.ui.error(f"Can't replace: {undone.reason}"[:40])
                return
            self.records.pop()
            time.sleep(0.12)
            return self.deliver(res.text, target)

        log("COMMAND", f"unhandled action {action!r}", C_WARN)

    def undo_last(self):
        """"scratch that": remove Halo's own last insertion, or nothing."""
        last = self.records[-1] if self.records else None
        if last is None:
            self.ui.error("Nothing to undo")
            log("COMMAND", "undo with nothing inserted -- ignored", C_WARN)
            return
        self._injecting_until = time.time() + 0.5
        r = insertion.undo(last)
        if r.ok:
            self.records.pop()
            self.ui.done()
            log("DONE", f"removed Halo's last insertion ({r.method})", C_OK)
        else:
            self.ui.error(f"Can't undo: {r.reason}"[:40])
            log("COMMAND", f"undo refused: {r.reason}", C_WARN)

    # ------------------------------------------------------------------
    # Command Mode
    # ------------------------------------------------------------------
    def _selection(self, target) -> tuple[str, bool]:
        """(text to act on, whether it is a live selection). With nothing
        selected, Halo's own last insertion in the same field -- selected
        first, so the replacement lands on it."""
        if target is None or target.secure or target.element is None:
            return "", False
        ax = context_mod._backend()
        sel = ax.attr(target.element, "AXSelectedText")
        if sel is not None and str(sel).strip():
            return str(sel)[:20000], True
        last = self.records[-1] if self.records else None
        if last is not None and last.range and ax.same(last.element, target.element):
            value = ax.attr(target.element, "AXValue")
            loc, n = last.range
            if isinstance(value, str) and value[loc:loc + n] == last.text:
                ax.set_selected_range(target.element, loc, n)
                return last.text, False
        return "", False

    def command_mode(self, spoken: str, target, transform_id: str | None = None):
        """Speech (or a menu choice) -> an edit of the selected text."""
        store = self.transforms
        cmd = (transforms_mod.Command("transform", transform_id) if transform_id
               else transforms_mod.parse(spoken, store))
        if cmd is None:
            self.ui.hide()
            return {"ok": False, "reason": "no instruction"}
        if cmd.kind == "undo":
            self.undo_last()
            return {"ok": True}
        original, _ = self._selection(target)
        if not original:
            self.ui.error("Select some text first")
            return {"ok": False, "reason": "no selection"}
        self.stage = "cleaning"
        self.ui.processing()
        model = None
        if cmd.kind != "rule":
            lm = local_llm.local_model() if local_llm.local_installed() else None
            if lm is not None and lm.usable():
                model = lm
            elif lm is not None:
                lm.prewarm()
        log("COMMAND", f"{cmd.kind} {cmd.op or ''} on "
                       f"{logsafe.content(original, 'selection')}".strip())
        try:
            new = transforms_mod.run(cmd, original, model, store,
                                     budget=max(10.0, config.LOCAL_POLISHED_BUDGET * 4))
        except ValueError as e:
            msg = str(e)
            self.ui.error(("Needs the local model" if "local model" in msg else msg)[:40])
            log("COMMAND", f"not applied: {msg if config.DEBUG_LOG_CONTENT else type(e).__name__}",
                C_WARN)
            return {"ok": False, "reason": msg}
        if self._cancel.is_set():
            raise transcribe.Cancelled()
        self.stage = "inserting"
        self._injecting_until = time.time() + 1.0
        r = insertion.replace_selection(new, original, target)
        if not r.ok:
            self.ui.error(f"Not replaced: {r.reason}"[:40])
            log("COMMAND", f"not replaced: {r.reason}", C_WARN)
            return {"ok": False, "reason": r.reason}
        self._remember(new, r, target, original=original)
        self.ui.done()
        log("DONE", f"replaced the selection ({r.method}); say 'scratch that' to undo", C_OK)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------
    def deliver(self, text: str, target=None, remember: bool = True, raw: str = "",
                language: str = "", mode: str = "", wav=None, duration=None):
        """Insert into the target captured at key-down -- or explain why not,
        with the text left on the clipboard and in History."""
        if self._cancel.is_set():
            raise transcribe.Cancelled()
        self.stage = "inserting"
        log("TEXT", logsafe.content(text))
        self._injecting_until = time.time() + 1.0
        r = insertion.insert(text, target)
        secure = bool(getattr(target, "secure", False))
        if r.ok:
            if remember:
                self._remember(text, r, target)
            self.ui.done()
            log("DONE", f"inserted via {r.method}.", C_OK)
            status, reason = "inserted", ""
        else:
            clipboard.put_text_for_user(text)
            short = {"you switched apps": "App changed: ⌘V to paste",
                     "you switched windows": "Window changed: ⌘V to paste",
                     "the text field changed": "Field changed: ⌘V to paste",
                     "Accessibility is off": "Accessibility off"}.get(r.reason,
                                                                       "Not typed: ⌘V to paste")
            self.ui.error(short)
            self.last_error = short
            log("NOT TYPED", f"{r.reason} -- text left on the clipboard", C_WARN)
            status, reason = "not inserted", r.reason
        if raw and mode:
            try:
                self.history.add(raw=raw, cleaned=text, mode=mode, status=status,
                                 reason=reason, duration=duration,
                                 app_name=getattr(target, "app_name", "") or "",
                                 bundle_id=getattr(target, "bundle_id", "") or "",
                                 language=language, wav=wav, secure=secure)
            except Exception as e:
                log_exception("history", e)
        return r

    def _remember(self, text, r, target, original=None):
        rec = insertion.Record(
            text=text, method=r.method, pid=getattr(target, "pid", None),
            bundle_id=getattr(target, "bundle_id", "") or "",
            element=getattr(target, "element", None),
            window=getattr(target, "window", None), range=r.range,
            original=original, secure=bool(getattr(target, "secure", False)))
        self.records = (self.records + [rec])[-5:]
        if config.LEARNING_ENABLED and config.CONTEXT_ENABLED and original is None:
            self.learner.watch(rec)

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    def _suggestion_ready(self, s):
        self.ui.flash(f"Learn “{s.correct}”? See Settings"[:40])
        log("LEARNING", "new dictionary suggestion (see Settings > Dictionary)", C_OK)

    def _check_learning(self, force: bool = False):
        if not (config.LEARNING_ENABLED and config.CONTEXT_ENABLED):
            return
        try:
            self.learner.check_due(context_mod._backend(), force=force)
        except Exception as e:
            log_exception("learning", e)

    def _learning_loop(self):
        while not self._watch_stop.wait(5.0):
            if self.stage == "idle" and not self.busy.locked():
                self._check_learning()
            if history_mod.History.enabled():
                self.history.maybe_prune()

    # ------------------------------------------------------------------
    # Crash recovery
    #
    # The clip is copied aside before transcription and removed once its text
    # has landed (or failed cleanly). If the engine dies in between, the next
    # engine finds it, transcribes it, and puts the text on the clipboard.
    # ------------------------------------------------------------------
    @staticmethod
    def _keep_for_recovery(wav: str):
        try:
            paths.RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(paths.RECOVERY_DIR, 0o700)
            shutil.copyfile(wav, paths.RECOVERY_DIR / "pending.wav")
            (paths.RECOVERY_DIR / "pending.json").write_text(json.dumps(
                {"at": time.time(), "language": config.WHISPER_LANGUAGE}), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _drop_recovery():
        for name in ("pending.wav", "pending.json"):
            try:
                (paths.RECOVERY_DIR / name).unlink()
            except OSError:
                pass

    def recover(self):
        """Offer back a dictation an engine crash interrupted."""
        wav = paths.RECOVERY_DIR / "pending.wav"
        if not wav.exists():
            return
        try:
            meta = json.loads((paths.RECOVERY_DIR / "pending.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if time.time() - float(meta.get("at", 0)) > RECOVERY_MAX_AGE:
            self._drop_recovery()
            return
        with self.busy:
            try:
                result = transcribe.transcribe(str(wav), meta.get("language") or
                                               config.WHISPER_LANGUAGE)
                if result.text:
                    cleaned = pipeline.process(
                        self.dictionary.apply(result.text, None, result.language)[0],
                        ctx=None, language=result.language, dictionary=self.dictionary,
                        privacy=self.privacy.enabled).text
                    clipboard.put_text_for_user(cleaned)
                    self.ui.flash("Recovered dictation: ⌘V")
                    log("RECOVERED", f"{logsafe.content(cleaned)} left on the clipboard", C_OK)
                    self.history.add(raw=result.text, cleaned=cleaned, mode=config.CLEANUP_MODE,
                                     status="recovered", reason="the engine restarted",
                                     language=result.language, wav=str(wav))
            except Exception as e:
                log_exception("recovery", e)
            finally:
                self._drop_recovery()

    # ------------------------------------------------------------------
    # The control socket (Settings window, menu bar)
    # ------------------------------------------------------------------
    def control_handlers(self) -> dict:
        return {
            "health": self._op_health,
            "history.reinsert": self._op_reinsert,
            "history.retry_cleanup": self._op_retry_cleanup,
            "history.retry_transcription": self._op_retry_transcription,
            "transform": self._op_transform,
        }

    def _op_health(self, req):
        st = local_llm.read_status()
        return {
            "state": self.stage, "pid": os.getpid(),
            "uptime": int(time.time() - self._started),
            "language": config.WHISPER_LANGUAGE, "mode": config.CLEANUP_MODE,
            "local_model": st.get("state", "not started"),
            "local_model_detail": st.get("detail", ""),
            "mic": config.MIC_DEVICE or "System Default",
            "mic_warning": self.recorder.device_warning,
            "last_error": self.last_error, "accessibility": permissions.accessibility_ok(),
            "history": history_mod.History.enabled(), "context": config.CONTEXT_ENABLED,
            "debug_logging": config.DEBUG_LOG_CONTENT,
        }

    def _locked(self, fn):
        if not self.busy.acquire(timeout=5):
            return {"ok": False, "reason": "Halo is busy"}
        try:
            return fn()
        finally:
            self.busy.release()

    def _op_reinsert(self, req):
        item = self.history.get(req.get("id", ""))
        if item is None:
            return {"ok": False, "reason": "not found"}

        def go():
            # The window hid itself before asking; the app underneath has focus.
            time.sleep(0.35)
            target = context_mod.capture(context_mod._backend(), config.CONTEXT_APP_OVERRIDES,
                                         read_text=False)
            r = self.deliver(item.cleaned, target)
            return {"ok": r.ok, "reason": r.reason}
        return self._locked(go)

    def _op_retry_cleanup(self, req):
        item = self.history.get(req.get("id", ""))
        if item is None:
            return {"ok": False, "reason": "not found"}

        def go():
            corrected = self.dictionary.apply(item.raw, item.bundle_id or None,
                                              item.language)[0]
            res = pipeline.process(corrected, mode=req.get("mode") or config.CLEANUP_MODE,
                                   ctx=None, language=item.language or "en",
                                   dictionary=self.dictionary, privacy=self.privacy.enabled)
            self.history.update(item.id, cleaned=res.text, mode=config.CLEANUP_MODE,
                                status="cleanup retried")
            return {"ok": True, "text": res.text}
        return self._locked(go)

    def _op_retry_transcription(self, req):
        item = self.history.get(req.get("id", ""))
        if item is None or not item.audio or not os.path.exists(item.audio):
            return {"ok": False, "reason": "no audio kept for this one"}

        def go():
            result = transcribe.transcribe(item.audio, item.language or config.WHISPER_LANGUAGE)
            corrected = self.dictionary.apply(result.text, item.bundle_id or None,
                                              result.language)[0]
            res = pipeline.process(corrected, ctx=None, language=result.language,
                                   dictionary=self.dictionary, privacy=self.privacy.enabled)
            self.history.update(item.id, raw=result.text, cleaned=res.text,
                                language=result.language, status="transcription retried")
            return {"ok": True, "raw": result.text, "text": res.text}
        return self._locked(go)

    def _op_transform(self, req):
        tid = req.get("id", "")
        if self.transforms.get(tid) is None:
            return {"ok": False, "reason": "unknown transform"}

        def go():
            target = context_mod.capture(context_mod._backend(), config.CONTEXT_APP_OVERRIDES,
                                         read_text=False)
            self._cancel.clear()
            try:
                return self.command_mode("", target, transform_id=tid)
            finally:
                self.stage = "idle"
        return self._locked(go)

    # ------------------------------------------------------------------
    # Live settings.
    #
    # settings.json used to be read once, because pynput binds the hotkey at
    # startup and tearing the listener down mid-utterance would drop a keypress.
    # The Settings window makes that unacceptable: nobody expects to restart an
    # app after moving a slider.
    #
    # The compromise is to reload on mtime and rebind ONLY when it is safe --
    # idle, nothing held, nothing toggled on. Everything that is not the hotkey
    # (activation style, polish toggles, whisper knobs, cleanup budgets) is read
    # per utterance from config, so it takes effect on the next thing you say
    # with no rebinding at all.
    # ------------------------------------------------------------------
    def _watch_settings(self):
        path = settings_mod.current.path
        try:
            last = path.stat().st_mtime
        except OSError:
            last = None
        while not self._watch_stop.wait(1.0):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime == last:
                continue
            last = mtime
            if self.busy.locked() or self.held or self.toggled_on:
                # Come back to it: re-reading now could rebind the key the
                # user is holding down this instant.
                last = None
                continue
            previous_hotkey = config.HOTKEY
            try:
                if not settings_mod.current.load():
                    # A typo in settings.json: keep running on what we had,
                    # and say so once rather than dying or going silent.
                    self.ui.error("settings.json has an error")
                    continue
                config.reload()
            except Exception as e:
                log_exception("settings reload", e)
                continue
            log("SETTINGS", f"reloaded {path.name}", C_OK)
            if logsafe.banner():
                log("DEBUG", logsafe.banner(), C_WARN)
            if config.HOTKEY != previous_hotkey:
                self._rebind_hotkey()

    def _rebind_hotkey(self):
        """Swap the global key tap for a new one.

        pynput has no way to change a running listener's key set, so the tap is
        torn down and rebuilt. Safe only when idle, which _watch_settings has
        already checked.
        """
        try:
            new_key = getattr(keyboard.Key, str(config.HOTKEY).lower(), None)
        except Exception:
            new_key = None
        if new_key is None:
            log("SETTINGS", f"ignoring unknown hotkey {config.HOTKEY!r}", C_WARN)
            return
        self.hotkey = new_key
        if self._listener is not None:
            self._listener.stop()
        log("HOTKEY", f"now {str(config.HOTKEY).upper()}", C_OK)
        self.ui.flash(f"Hotkey: {str(config.HOTKEY).upper()}")

    def run(self):
        threading.Thread(target=self._watch_settings, daemon=True).start()
        threading.Thread(target=self._learning_loop, daemon=True).start()
        threading.Thread(target=self.recover, daemon=True).start()
        server = control.ControlServer(self.control_handlers())
        server.start()
        try:
            # Outer loop so _rebind_hotkey() can stop the listener and have a
            # fresh one take its place without unwinding the process.
            while not self._watch_stop.is_set():
                with keyboard.Listener(on_press=self.on_press,
                                       on_release=self.on_release) as ln:
                    self._listener = ln
                    ln.join()
                self._listener = None
        finally:
            self._watch_stop.set()
            server.stop()


def startup_checks(ui=None) -> bool:
    """Returns True if we can run. In headless mode nothing interactive may
    happen: no System Settings pop-up, and failures go to the pill + log."""
    ok = True
    quiet = os.environ.get("HALO_QUIET_START") == "1"
    problems = transcribe.preflight()
    if problems:
        print(f"{C_ERR}whisper.cpp is not usable:{C_RST}")
        for p in problems:
            print("  -", p)
        ok = False
        if ui is not None and not quiet:
            ui.error("No speech model: see Settings")

    if not permissions.report(require=not HEADLESS):
        ok = False
        if ui is not None and not quiet:
            ui.error("Accessibility off")

    if config.CLEANUP_PROVIDER in ("auto", "openrouter") and \
            not local_llm.local_installed() and not config.get_api_key():
        print(f"{C_DIM}No local cleanup model and no OpenRouter key: Halo uses its "
              f"local rules only.{C_RST}")
        print(f"{C_DIM}  For grammar cleanup on this Mac: Settings > Models{C_RST}\n")
    return ok


def main():
    setup_logging()
    print(f"\n{C_OK}Halo{C_RST}  --  local dictation\n")
    if logsafe.banner():
        print(f"{C_WARN}{logsafe.banner()}{C_RST}")

    # Seeding is idempotent and also runs in `halo setup`; doing it here too
    # means a first run from a checkout works with no setup step at all.
    paths.ensure_dirs()
    if paths.migrate_legacy_state():
        print(f"  migrated {paths.LEGACY_STATE_FILE.name} -> {paths.STATE_FILE}")
    for created in paths.seed_user_config():
        print(f"  created {created}")

    # Connect the overlay BEFORE the checks, so a failed check has somewhere
    # visible to report itself when there is no terminal.
    ui: object = overlay_mod.NullOverlay()
    if config.OVERLAY_ENABLED:
        real = overlay_mod.Overlay()
        ui = real if real.start_app() else overlay_mod.NullOverlay()

    if not startup_checks(ui):
        print(f"{C_ERR}Startup checks failed. Fix the above, then rerun.{C_RST}")
        if HEADLESS:
            time.sleep(3)      # let the error pill be seen before we exit
        ui.close()
        sys.exit(EXIT_CONFIG)

    print(f"  model    : {config.WHISPER_MODEL.name}")
    style = ("press to start, press again to send" if config.ACTIVATION == "toggle"
             else "hold to talk, release to send")
    print(f"  hotkey   : {config.HOTKEY.upper()}  ({style})")
    print(f"  cleanup  : {config.CLEANUP_MODE} ({config.CLEANUP_PROVIDER})")
    print(f"  context  : {'on' if config.CONTEXT_ENABLED else 'off'}")
    print(f"  language : {config.WHISPER_LANGUAGE}")
    print(f"  history  : {'on, ' + config.HISTORY_RETENTION if config.HISTORY_ENABLED else 'off'}")
    print(f"  overlay  : {'on' if getattr(ui, 'enabled', False) else 'off'}")
    verb = "Press" if config.ACTIVATION == "toggle" else "Hold"
    print(f"\n{C_OK}Ready.{C_RST} {verb} {config.HOTKEY.upper()} anywhere and speak. "
          "Ctrl+C to quit.\n")

    # launchd stops the agent with SIGTERM. Turning that into SystemExit is
    # what lets the finally below stop llama-server instead of orphaning it.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    # Both cost a second or so the first time; pay it now, not on the first
    # dictation.
    threading.Thread(target=context_mod.warm_up, daemon=True).start()
    local_llm.reap_stale()
    local_llm.prewarm(config.CLEANUP_MODE)

    try:
        Halo(ui=ui).run()
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        local_llm.shutdown()
        ui.close()


if __name__ == "__main__":
    main()
