"""Halo -- hold a key, speak, release, get cleaned text at the cursor.

Pipeline:  mic -> whisper.cpp (local) -> cleanup (rules, then a model on this
           Mac or OpenRouter) -> Cmd+V paste
"""
import os
import signal
import sys
import threading
import time

from pynput import keyboard

import cleanup
import commands as commands_mod
import config
import context as context_mod
import dictionary
import inject
import local_llm
import pipeline
import privacy as privacy_mod
import snippets as snippets_mod
import overlay as overlay_mod
import paths
import permissions
import settings as settings_mod
import transcribe
from audio import Recorder

C_DIM, C_OK, C_WARN, C_ERR, C_RST = "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


HEADLESS = os.environ.get("HALO_OVERLAY_CHILD") == "1" or not sys.stdout.isatty()

# Exit code meaning "misconfigured, do not restart me" -- the supervisor honours
# this so a missing permission does not become a crash-restart loop.
EXIT_CONFIG = 78


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


class Halo:
    def __init__(self, ui=None):
        self.recorder = Recorder()
        self.dictionary = dictionary.Dictionary()
        self.snippets = snippets_mod.Snippets()
        self.commands = commands_mod.Commands()
        self.privacy = privacy_mod.Privacy()
        # Last text WE injected. Used as context for AI commands and to decide
        # whether an undo is ours to perform.
        self.last_injected: str | None = None
        self.hotkey = resolve_hotkey(config.HOTKEY)
        self.held = False
        self.busy = threading.Lock()
        self.ui = ui or overlay_mod.NullOverlay()
        self._pump_stop = threading.Event()
        self._pump: threading.Thread | None = None
        # Toggle mode: True between the press that starts and the press that
        # sends. Separate from `held`, which tracks the physical key.
        self.toggled_on = False
        self._auto_stop: threading.Timer | None = None
        self._listener: keyboard.Listener | None = None
        self._watch_stop = threading.Event()
        # Context Awareness, for exactly one dictation: captured at key-down,
        # cleared in finish()'s finally or on cancel. Never logged, never
        # written anywhere -- see context.py.
        self._pending: context_mod.Pending | None = None
        self._context: context_mod.Context | None = None

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

    # --- hotkey callbacks (must return fast; work happens on a thread) ---
    #
    # Two activation styles share one key. In "hold" the press starts and the
    # release sends, which is the original behaviour and cannot leave the mic
    # open. In "toggle" the release is ignored and the NEXT press sends, which
    # is what makes long dictation and one-handed use bearable -- at the cost
    # of needing `max_recording_sec` as a backstop, because a toggle you walk
    # away from would otherwise record until the disk filled.
    def on_press(self, key):
        if key != self.hotkey:
            # Escape abandons a toggled recording without typing anything.
            if (key == keyboard.Key.esc and self.toggled_on
                    and config.ACTIVATION == "toggle"):
                self.cancel_recording()
            return

        if config.ACTIVATION == "toggle":
            if self.toggled_on:
                self.toggled_on = False
                self._cancel_auto_stop()
                threading.Thread(target=self.finish, daemon=True).start()
            elif not self.busy.locked():
                # Commit only on success -- see start_recording().
                if self.start_recording():
                    self.toggled_on = True
                    self._arm_auto_stop()
            return

        if not self.held:
            self.held = True
            self.start_recording()

    def on_release(self, key):
        if config.ACTIVATION != "hold":
            return
        if key == self.hotkey and self.held:
            self.held = False
            threading.Thread(target=self.finish, daemon=True).start()

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

    def _begin_context(self):
        """Read the focused app at key-down, on a thread: the app you are
        dictating into is the one focused NOW, and nothing here may delay
        the microphone."""
        self._clear_context()
        if config.CONTEXT_ENABLED:
            self._pending = context_mod.capture_async(config.CONTEXT_APP_OVERRIDES)

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

    def cancel_recording(self):
        """Throw the clip away. Nothing is transcribed and nothing is typed."""
        self.toggled_on = False
        self._cancel_auto_stop()
        self._stop_level_pump()
        self._clear_context()
        try:
            wav, _ = self.recorder.stop()
        except Exception:
            wav = None
        if wav and os.path.exists(wav):
            os.unlink(wav)
        self.ui.flash("Cancelled")
        log("CANCELLED", "recording discarded", C_WARN)

    def start_recording(self) -> bool:
        """Returns True only if the microphone actually opened.

        Toggle mode needs the answer: committing `toggled_on` on a failed
        start would arm the auto-stop timer and leave the next key press
        trying to finish a recording that never began, which surfaces as a
        baffling "clip too short (0.00s)".
        """
        if self.busy.locked():
            log("BUSY", "still processing the last clip -- ignoring", C_WARN)
            return False
        try:
            self.recorder.start()
            self._begin_context()
            # Load the cleanup model while you talk, if it is not loaded.
            local_llm.prewarm(config.CLEANUP_MODE)
            self.ui.listening()
            self._start_level_pump()
            verb = ("press again" if config.ACTIVATION == "toggle"
                    else f"release {config.HOTKEY.upper()}")
            log("RECORDING", f"listening... ({verb} to stop)", C_OK)
            return True
        except Exception as e:
            self.ui.hide()
            log("ERROR", f"could not open microphone: {e}", C_ERR)
            return False

    def finish(self):
        if not self.busy.acquire(blocking=False):
            return
        wav = None
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
                self.ui.error("No microphone access")
                log("SKIPPED",
                    "audio is pure silence. Grant Microphone to Halo: "
                    "System Settings > Privacy & Security > Microphone",
                    C_WARN)
                return

            self.ui.processing()
            ctx = self._take_context()
            t0 = time.time()
            log("TRANSCRIBE", "running whisper.cpp locally...")
            try:
                result = transcribe.transcribe(
                    wav, config.WHISPER_LANGUAGE,
                    vocabulary=self.dictionary.whisper_prompt(),
                    previous=self.last_injected or "",
                    context_terms=ctx.terms if ctx is not None else ())
                raw = result.text
            except transcribe.TranscriptionError as e:
                self.ui.hide()
                log("ERROR", f"transcription failed: {e}", C_ERR)
                return
            if not raw:
                self.ui.hide()
                log("SKIPPED", "no speech detected", C_WARN)
                return
            log("TRANSCRIBE",
                f"{time.time()-t0:.2f}s [{result.language}] -> {raw!r}", C_OK)
            if result.confidence is not None and result.confidence < 0.7:
                log("LANGUAGE",
                    f"low confidence ({result.confidence:.2f}) on "
                    f"{result.language!r}; set HALO_LANGUAGE to be sure", C_WARN)

            self.dispatch(raw, result.language, ctx)

        finally:
            self._stop_level_pump()
            self._clear_context()
            if wav and os.path.exists(wav):
                os.unlink(wav)
            self.busy.release()

    # ------------------------------------------------------------------
    # Post-transcription pipeline.
    #
    # Order matters and is deliberate:
    #   1. dictionary  -- fix vocabulary first, so everything below matches
    #                     against corrected text
    #   2. commands    -- before cleanup, which would rewrite "scratch that"
    #                     into prose
    #   3. snippets    -- whole-utterance triggers, fully local
    #   4. dictation   -- pipeline.py: the cleanup mode's rules, then a
    #                     model if one is ready (never OpenRouter in Privacy
    #                     Mode), then fitting the text to the cursor
    #
    # To add a stage, insert it here and give it a handler. To add a command,
    # edit commands.json and add a branch in run_command().
    # ------------------------------------------------------------------
    def dispatch(self, raw: str, language: str = "en", ctx=None):
        corrected, changes = self.dictionary.apply(raw)
        if changes:
            pretty = ", ".join(f"{b!r}->{a!r}" for b, a in changes[:6])
            log("DICTIONARY", f"{len(changes)} fix(es): {pretty}", C_OK)

        cmd = self.commands.detect(corrected)
        if cmd is not None:
            log("COMMAND", f"{cmd}", C_OK)
            return self.run_command(cmd, language)

        hit = self.snippets.match(corrected)
        if hit is not None:
            snip, score = hit
            log("SNIPPET", f"{snip.trigger!r} @{score:.2f} "
                           f"({len(snip.text)} chars, local only)", C_OK)
            return self.deliver(snip.text)

        return self.dictate(corrected, language, ctx)

    def dictate(self, text: str, language: str, ctx=None):
        # The category and flags only -- never the text context.py read.
        if ctx is not None:
            log("CONTEXT", ctx.summary())
        elif config.CONTEXT_ENABLED:
            log("CONTEXT", "not available for this app")
        mode = config.CLEANUP_MODE
        result = pipeline.process(
            text, mode=mode, ctx=ctx, language=language,
            dictionary=self.dictionary, privacy=self.privacy.enabled)
        stages = ", ".join(result.stages) or "no changes"
        if result.source in ("local", "openrouter"):
            log("CLEANUP", f"{mode}: {stages} -- {result.model_seconds:.2f}s via "
                           f"{result.detail}", C_OK)
        elif mode != "off":
            log("CLEANUP", f"{stages} -- {result.detail}",
                C_WARN if result.fell_back else C_OK)
        if not result.text.strip():
            # "...scratch that" with nothing after it: you took it all back.
            self.ui.hide()
            log("SKIPPED", "nothing left to type after the correction", C_WARN)
            return None
        return self.deliver(result.text)

    def run_command(self, cmd, language: str):
        action = cmd.action

        if action == "undo":
            # Only undo what WE injected. Cmd+Z into an app we have not typed
            # into would eat the user's own last edit, which is worse than
            # doing nothing.
            if not self.last_injected:
                self.ui.error("Nothing to undo")
                log("COMMAND", "undo with nothing injected -- ignored", C_WARN)
                return
            try:
                inject.undo()
                self.last_injected = None
                self.ui.done()
                log("DONE", "sent Cmd+Z", C_OK)
            except inject.InjectionError as e:
                self.ui.error("Undo failed")
                log("ERROR", str(e), C_ERR)
            return

        if action in ("newline", "paragraph"):
            return self.deliver("\n" if action == "newline" else "\n\n",
                                remember=False)

        if action in ("privacy_on", "privacy_off"):
            on = action == "privacy_on"
            self.privacy.set(on)
            self.ui.privacy(on)
            self.ui.flash("Privacy ON" if on else "Privacy OFF")
            log("PRIVACY", f"turned {'ON' if on else 'OFF'} by voice", C_OK)
            return

        if action == "ai":
            if self.privacy.enabled:
                self.ui.error("Blocked: Privacy Mode")
                log("PRIVACY",
                    "AI command needs OpenRouter; refused in Privacy Mode",
                    C_WARN)
                return
            context = self.last_injected or ""
            if not context:
                self.ui.error("Nothing to edit yet")
                log("COMMAND", "AI command with no prior dictation", C_WARN)
                return
            log("COMMAND", f"AI: {cmd.argument!r} on {len(context)} chars")
            t = time.time()
            res = cleanup.ai_command(cmd.argument, context, language)
            if res.source != "llm" or not res.text:
                self.ui.error("AI command failed")
                log("ERROR", f"AI command: {res.detail}", C_ERR)
                return
            log("COMMAND", f"{time.time()-t:.2f}s via {res.detail}", C_OK)
            # Replace rather than append: "make that more formal" means the
            # previous text should go away.
            try:
                inject.undo()
                time.sleep(0.12)
            except inject.InjectionError as e:
                log("WARN", f"could not undo before rewrite: {e}", C_WARN)
            return self.deliver(res.text)

        log("COMMAND", f"unhandled action {action!r}", C_WARN)

    def deliver(self, text: str, remember: bool = True):
        """Inject text, with the clipboard fallback if Accessibility is gone."""
        log("TEXT", repr(text[:120]))
        log("INJECT", "pasting into the focused app...")
        try:
            inject.inject(text)
            if remember:
                self.last_injected = text
            self.ui.done()
            log("DONE", "text injected.", C_OK)
        except inject.InjectionError as e:
            self.ui.error("Accessibility off")
            inject.copy_only(text)
            log("ERROR", f"{e}", C_ERR)
            log("FALLBACK", "text left on your clipboard -- press Cmd+V yourself",
                C_WARN)

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
                config.reload()
            except Exception as e:
                log("SETTINGS", f"reload failed, keeping old values: {e}", C_WARN)
                continue
            log("SETTINGS", f"reloaded {path.name}", C_OK)
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
        watcher = threading.Thread(target=self._watch_settings, daemon=True)
        watcher.start()
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


def startup_checks(ui=None) -> bool:
    """Returns True if we can run. In headless mode nothing interactive may
    happen: no System Settings pop-up, and failures go to the pill + log."""
    ok = True
    problems = transcribe.preflight()
    if problems:
        print(f"{C_ERR}whisper.cpp is not usable:{C_RST}")
        for p in problems:
            print("  -", p)
        ok = False

    if not permissions.report(require=not HEADLESS):
        ok = False
        if ui is not None:
            ui.error("Accessibility off")

    if config.CLEANUP_PROVIDER in ("auto", "openrouter") and \
            not local_llm.local_installed() and not config.get_api_key():
        print(f"{C_DIM}No local cleanup model and no OpenRouter key: Halo uses its "
              f"local rules only.{C_RST}")
        print(f"{C_DIM}  For grammar cleanup on this Mac: halo model local install{C_RST}\n")
    return ok


def main():
    setup_logging()
    print(f"\n{C_OK}Halo{C_RST}  --  local dictation\n")

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
