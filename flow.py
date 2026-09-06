"""WisprFlowClone -- hold a key, speak, release, get cleaned text at the cursor.

Pipeline:  mic -> whisper.cpp (local) -> OpenRouter cleanup -> Cmd+V paste
"""
import os
import sys
import threading
import time

from pynput import keyboard

import cleanup
import config
import dictionary
import inject
import overlay as overlay_mod
import permissions
import transcribe
from audio import Recorder

C_DIM, C_OK, C_WARN, C_ERR, C_RST = "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


HEADLESS = os.environ.get("FLOW_OVERLAY_CHILD") == "1" or not sys.stdout.isatty()

# Exit code meaning "misconfigured, do not restart me" -- the supervisor honours
# this so a missing permission does not become a crash-restart loop.
EXIT_CONFIG = 78


def setup_logging():
    """In background mode there is no terminal, so send output to a log file."""
    if not HEADLESS:
        return
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
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


class Flow:
    def __init__(self, ui=None):
        self.recorder = Recorder()
        self.dictionary = dictionary.Dictionary()
        self.hotkey = resolve_hotkey(config.HOTKEY)
        self.held = False
        self.busy = threading.Lock()
        self.ui = ui or overlay_mod.NullOverlay()
        self._pump_stop = threading.Event()
        self._pump: threading.Thread | None = None

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
    def on_press(self, key):
        if key == self.hotkey and not self.held:
            self.held = True
            self.start_recording()
        elif key == keyboard.Key.esc and not self.held:
            pass

    def on_release(self, key):
        if key == self.hotkey and self.held:
            self.held = False
            threading.Thread(target=self.finish, daemon=True).start()

    def start_recording(self):
        if self.busy.locked():
            log("BUSY", "still processing the last clip -- ignoring", C_WARN)
            return
        try:
            self.recorder.start()
            self.ui.listening()
            self._start_level_pump()
            log("RECORDING", f"listening... (release {config.HOTKEY.upper()} to stop)", C_OK)
        except Exception as e:
            self.ui.hide()
            log("ERROR", f"could not open microphone: {e}", C_ERR)

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
                    "audio is pure silence. Grant Microphone to WisprFlow: "
                    "System Settings > Privacy & Security > Microphone",
                    C_WARN)
                return

            self.ui.processing()
            t0 = time.time()
            log("TRANSCRIBE", "running whisper.cpp locally...")
            try:
                raw = transcribe.transcribe(wav)
            except transcribe.TranscriptionError as e:
                self.ui.hide()
                log("ERROR", f"transcription failed: {e}", C_ERR)
                return
            if not raw:
                self.ui.hide()
                log("SKIPPED", "no speech detected", C_WARN)
                return
            log("TRANSCRIBE", f"{time.time()-t0:.2f}s -> {raw!r}", C_OK)

            # Personal vocabulary, before anything else sees the text.
            corrected, changes = self.dictionary.apply(raw)
            if changes:
                pretty = ", ".join(f"{b!r}->{a!r}" for b, a in changes[:6])
                log("DICTIONARY", f"{len(changes)} fix(es): {pretty}", C_OK)
                raw = corrected

            t1 = time.time()
            log("CLEANUP", "sending to OpenRouter...")
            result = cleanup.clean(raw, vocabulary=self.dictionary.prompt_context())
            if result.source == "llm":
                log("CLEANUP", f"{time.time()-t1:.2f}s via {result.detail}", C_OK)
            else:
                log("CLEANUP", f"fell back to RAW ({result.detail})", C_WARN)
            log("TEXT", repr(result.text))

            log("INJECT", "pasting into the focused app...")
            try:
                inject.inject(result.text)
                self.ui.done()
                log("DONE", "text injected.", C_OK)
            except inject.InjectionError as e:
                self.ui.hide()
                inject.copy_only(result.text)
                log("ERROR", f"{e}", C_ERR)
                log("FALLBACK", "text left on your clipboard -- press Cmd+V yourself", C_WARN)
        finally:
            self._stop_level_pump()
            if wav and os.path.exists(wav):
                os.unlink(wav)
            self.busy.release()

    def run(self):
        with keyboard.Listener(on_press=self.on_press,
                               on_release=self.on_release) as ln:
            ln.join()


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

    if not config.get_api_key():
        print(f"{C_WARN}No OpenRouter API key found.{C_RST}")
        print("  The app will still work, but text is injected UNCLEANED.")
        print("  Fix (background-safe):")
        print(f"    security add-generic-password -s {config.KEYCHAIN_SERVICE} "
              "-a \"$USER\" -w 'sk-or-...' -T /usr/bin/security -U\n")
    return ok


def main():
    setup_logging()
    print(f"\n{C_OK}WisprFlowClone{C_RST}  --  local dictation\n")

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
    print(f"  hotkey   : {config.HOTKEY.upper()}  (hold to talk, release to send)")
    print(f"  cleanup  : {config.OPENROUTER_MODELS[0]}")
    print(f"  overlay  : {'on' if getattr(ui, 'enabled', False) else 'off'}")
    print(f"\n{C_OK}Ready.{C_RST} Hold {config.HOTKEY.upper()} anywhere and speak. Ctrl+C to quit.\n")

    try:
        Flow(ui=ui).run()
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        ui.close()


if __name__ == "__main__":
    main()
