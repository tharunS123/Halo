#!/usr/bin/env python3
"""halo -- set up and control the background dictation agent.

Day to day you only hold F9. This is for the handful of things a single key
cannot express: first-time setup, checking why something is not working, and
getting rid of it again.

Replaces the old `haloctl` shell script. Written in Python because it needs
the same config, settings and model code the engine uses.
"""
import argparse
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import config
import models
import paths
import signing
from settings import SettingsFileError, current as settings

LABEL = "io.github.tharuns123.halo"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DOMAIN = f"gui/{os.getuid()}"
APP_BIN = paths.INSTALLED_APP / "Contents" / "MacOS" / "Halo"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks"
              "/LaunchServices.framework/Support/lsregister")

DIM, OK, WARN, ERR, RST = "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
if not sys.stdout.isatty():
    DIM = OK = WARN = ERR = RST = ""


def say(msg=""):
    print(msg, flush=True)


def good(msg):
    say(f"  {OK}OK{RST}    {msg}")


def warn(msg):
    say(f"  {WARN}warn{RST}  {msg}")


def bad(msg):
    say(f"  {ERR}FAIL{RST}  {msg}")


def step(n, total, title):
    say(f"\n{DIM}[{n}/{total}]{RST} {title}")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(f"  {prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        say()
        return default
    return answer or default


def confirm(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = ask(f"{prompt} [{hint}]").lower()
    return default if not answer else answer.startswith("y")


# --- the pieces setup and doctor share ------------------------------------

def version_stable(p: Path) -> Path:
    """Rewrite a Homebrew Cellar path to its stable opt/ equivalent.

    Cellar paths carry the version, so a LaunchAgent pointing at
    /opt/homebrew/Cellar/halo/0.2.0/... stops resolving the moment
    `brew upgrade` removes that directory, and the agent then fails to launch
    with nothing in the log to explain it. $(brew --prefix)/opt/halo is the
    symlink Homebrew moves forward on every upgrade, so bake that in instead.

    This matters even though the `halo` shim already uses the opt path: Python
    resolves symlinks when it sets sys.executable, so the Cellar path comes
    back in anyway.
    """
    parts = p.parts
    if "Cellar" not in parts:
        return p
    i = parts.index("Cellar")
    if len(parts) < i + 4:           # need Cellar/<formula>/<version>/<rest>
        return p
    return Path(*parts[:i], "opt", parts[i + 1], *parts[i + 3:])


def engine_script() -> Path:
    return version_stable(Path(__file__).resolve().parent / "halo.py")


def python_exe() -> Path:
    # NOT .resolve(): a venv's bin/python is a symlink to the base interpreter,
    # and resolving it would point at a Python with none of our packages.
    return version_stable(Path(sys.executable))


def bundled_app() -> Path | None:
    """The freshly built app that ships with this install."""
    return paths.BUNDLED_APP


def app_identity(app: Path) -> str | None:
    """What macOS actually keys this app's permissions on.

    Signed ad-hoc that is the code hash, and it moves on every build -- a
    version bump alone is enough, because CFBundleVersion lives inside the
    bundle. Signed with a certificate it is the certificate, and it does not
    move. Comparing the designated requirement covers both cases, so the rest
    of the CLI never has to ask which mode is in use.
    """
    return signing.requirement(app)


def cdhash(app: Path) -> str | None:
    """A bundle's code directory hash. Still used to decide whether a freshly
    built bundle differs from the installed one, which is a question about
    bytes rather than about identity -- see app_identity() for the latter."""
    if not app.exists():
        return None
    r = run(["codesign", "-d", "--verbose=4", str(app)])
    for line in (r.stderr + r.stdout).splitlines():
        if line.lower().startswith("cdhash="):
            return line.split("=", 1)[1].strip()
    return None


def read_state() -> dict:
    try:
        return json.loads(paths.STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(**changes) -> None:
    data = read_state()
    data.update(changes)
    paths.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.STATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def socket_ask(message: str, timeout: float = 2.0) -> str | None:
    """Ask the RUNNING app something. Permissions belong to that process, so
    asking from this one would report the terminal's grants instead."""
    path = config.OVERLAY_SOCKET
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(path)
        s.sendall((message + "\n").encode())
        chunks = []
        while True:
            try:
                data = s.recv(4096)
            except TimeoutError:
                break
            if not data:
                break
            chunks.append(data)
        s.close()
        return b"".join(chunks).decode(errors="replace")
    except OSError:
        return None


def permissions_from_app() -> dict:
    """{'accessibility': 'OK', ...} as reported by the running app."""
    reply = socket_ask("status")
    out = {}
    for line in (reply or "").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip().lower()
            if k in ("accessibility", "input monitoring", "microphone"):
                out[k] = v.strip()
    return out


def agent_running() -> bool:
    r = run(["launchctl", "print", f"{DOMAIN}/{LABEL}"])
    return r.returncode == 0 and "state = running" in r.stdout


def engine_running() -> bool:
    """Is the Python engine alive, as opposed to just the app supervising it?

    These come apart in one specific and very confusing way: the engine exits
    when Accessibility is missing, and the app deliberately does not respawn it
    on a config error. So the agent looks healthy, the grant is in place, and
    the hotkey still does nothing until something restarts the engine.
    """
    return run(["pgrep", "-f", "halo.py"]).returncode == 0


def sign_step(offer: bool) -> None:
    """Re-sign the installed app with a certificate kept on this Mac.

    Ad-hoc signing makes the code hash the app's identity, so every upgrade
    looks like a new app and macOS voids the permissions -- including upgrades
    that change nothing but Python, because the version string lives inside the
    bundle. A certificate moves the identity off the hash, and grants survive.
    """
    if not signing.available():
        return
    have = signing.identity_sha1()
    if not have:
        if offer:
            say("\n        Halo can sign itself with a certificate kept on this")
            say("        Mac. Without one, every upgrade looks like a brand new")
            say("        app to macOS and you re-grant Accessibility each time.")
            say("        The certificate never leaves this machine and needs no")
            say("        password or admin rights.")
            if not confirm("Set that up?", default=True):
                return
        have = signing.create_identity()
        if not have:
            warn("could not create a signing certificate; staying ad-hoc")
            say("        Upgrades will keep asking you to re-grant permissions.")
            return
        good(f"created a signing certificate ({have[:8]})")
    if signing.sign(paths.INSTALLED_APP):
        good("signed the app with it -- upgrades keep your permissions")
    else:
        warn("could not sign the app; staying ad-hoc")


def reset_stale_grants() -> bool:
    """Drop TCC rows that no longer match the installed bundle.

    macOS keys an ad-hoc-signed app's grants to its code hash, but System
    Settings goes on showing the old row with its switch ON. So after the
    bundle changes the user sees Halo apparently granted while the app is
    refused, and there is nothing obvious to toggle -- worse, setup then waits
    for a switch that already looks flipped. Clearing the row first means the
    switch they see is the switch that matters.

    tccutil resolves the identifier through LaunchServices, so this only works
    while the bundle is on disk: reset before removing it, never after.
    """
    run([LSREGISTER, "-f", str(paths.INSTALLED_APP)])
    time.sleep(1)
    failed = [s for s in ("Accessibility", "ListenEvent", "Microphone")
              if run(["tccutil", "reset", s, LABEL]).returncode != 0]
    return not failed


def wait_for_permission(name: str, timeout: int = 300) -> bool:
    """Block until the running app reports `name` granted. Ctrl+C to skip.

    Setup used to ask you to press Return and then check once. Flip the switch
    a moment later -- which is the normal case, System Settings asks for Touch
    ID -- and setup had already recorded a failure and moved on, leaving a
    correctly configured Mac with nothing running. Polling means the moment the
    switch goes on, setup notices and continues.
    """
    deadline = time.time() + timeout
    spinner, i = "|/-\\", 0
    tty = sys.stdout.isatty()
    try:
        while time.time() < deadline:
            value = permissions_from_app().get(name, "")
            if value.upper().startswith("OK"):
                if tty:
                    sys.stdout.write("\r" + " " * 72 + "\r")
                    sys.stdout.flush()
                return True
            if tty:
                left = int(deadline - time.time())
                sys.stdout.write(
                    f"\r  {DIM}waiting for you to switch Halo on "
                    f"{spinner[i % 4]}  ({left}s, Ctrl+C to skip){RST}   ")
                sys.stdout.flush()
            i += 1
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    if tty:
        sys.stdout.write("\r" + " " * 72 + "\r")
        sys.stdout.flush()
    return False


def render_plist() -> None:
    template = paths.LAUNCHD_TEMPLATE
    if not template or not template.is_file():
        raise SystemExit(f"error: LaunchAgent template not found ({template})")
    brew_bin = str(Path(config.WHISPER_BIN).parent) if config.WHISPER_BIN.exists() else "/opt/homebrew/bin"
    text = (template.read_text(encoding="utf-8")
            .replace("__APP_BINARY__", str(APP_BIN))
            .replace("__PYTHON__", str(python_exe()))
            .replace("__ENGINE__", str(engine_script()))
            .replace("__PATH__", f"{brew_bin}:/usr/bin:/bin:/usr/sbin:/sbin")
            .replace("__LOG_DIR__", str(paths.LOG_DIR)))
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(text, encoding="utf-8")


def local_llm_installed() -> bool:
    return models.llm_path(config.LOCAL_MODEL) is not None


def write_engine_pointer() -> None:
    """So a Finder launch of Halo.app can find the engine with no env."""
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.ENGINE_POINTER.write_text(json.dumps(
        {"python": str(python_exe()), "script": str(engine_script())},
        indent=2) + "\n", encoding="utf-8")


def bootstrap_agent() -> None:
    run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"])
    # A manually-launched instance still holds the LaunchServices registration
    # for this bundle id, and bootstrap then fails with "5: Input/output
    # error". bootout does not clear it, so kill any stray instance.
    run(["pkill", "-f", "Halo.app/Contents/MacOS/Halo"])
    run(["pkill", "-f", "halo.py"])
    time.sleep(1)
    r = run(["launchctl", "bootstrap", DOMAIN, str(PLIST)])
    if r.returncode != 0:
        bad(f"launchctl bootstrap failed: {(r.stderr or r.stdout).strip()}")


def install_app_bundle() -> str:
    """Copy the built bundle to ~/Applications, but only when it actually
    differs. An unchanged bundle keeps its TCC grants, so most upgrades cost
    the user nothing."""
    src = bundled_app()
    if not src or not src.exists():
        return "missing"
    src_hash = cdhash(src)
    # Compare against the hash the SOURCE had when we installed it, not against
    # the installed bundle's own hash: once setup re-signs the copy with the
    # local certificate its hash necessarily differs from the shipped one, and
    # comparing the two would report a pending upgrade forever.
    if paths.INSTALLED_APP.exists() and read_state().get("installed_from") == src_hash:
        return "unchanged"
    replaced = paths.INSTALLED_APP.exists()
    paths.INSTALLED_APP.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(paths.INSTALLED_APP, ignore_errors=True)
    shutil.copytree(src, paths.INSTALLED_APP, symlinks=True)
    write_state(installed_from=src_hash)
    return "replaced" if replaced else "installed"


# --- setup ----------------------------------------------------------------

def cmd_setup(args) -> int:
    total = 9
    say(f"\n{OK}Halo setup{RST}  --  local dictation for macOS")

    # Seed before anything writes a setting: seeding is copy-if-absent, so a
    # settings.json created by the whisper_bin write below would block the
    # documented default file from ever landing.
    paths.ensure_dirs()
    migrated = paths.migrate_legacy_state()
    seeded = paths.seed_user_config()

    step(1, total, "Checking this Mac")
    if sys.platform != "darwin":
        bad("Halo is macOS only.")
        return 1
    mac_ver = run(["sw_vers", "-productVersion"]).stdout.strip()
    arch = run(["uname", "-m"]).stdout.strip()
    good(f"macOS {mac_ver} on {arch}")
    if int(mac_ver.split(".")[0]) < 14:
        bad("macOS 14 (Sonoma) or newer is required.")
        return 1

    whisper = config.find_whisper_bin()
    if not whisper.exists():
        bad(f"whisper-cli not found (looked at {whisper})")
        say("        Install it with:  brew install whisper.cpp")
        return 1
    settings.set("whisper_bin", str(whisper))
    config.reload()
    good(f"whisper-cli at {whisper}")

    step(2, total, "Setting up your config")
    if migrated:
        good(f"moved {paths.LEGACY_STATE_FILE.name} into {paths.DATA_DIR}")
    for path in seeded:
        good(f"created {path}")
    if not seeded:
        good(f"already set up in {paths.CONFIG_DIR}")
    say("        Edit these any time with: halo config edit")

    # The graphical guide (in Halo.app) does the model, the microphone, the
    # permissions and a test dictation, with a picture for each. This
    # command does what only a command can: install the app and its login
    # agent. `--cli` keeps the old all-in-Terminal walkthrough.
    gui = not args.cli and not args.no_agent
    step(3, total, "Speech model")
    if gui and not models.installed():
        good("the Halo window will download it (it recommends one for this Mac)")
    elif args.no_model:
        good("skipped (--no-model)")
    else:
        have = models.installed()
        if have and not args.force_model:
            for name, path in have.items():
                good(f"{name} already installed ({path})")
        else:
            choice = args.model
            if not choice:
                say("        Which model? Bigger is more accurate, not slower to a human.")
                say(f"        1. small.en  {models.human(models.CATALOG['small.en']['size'])}  English only (recommended)")
                say(f"        2. base.en   {models.human(models.CATALOG['base.en']['size'])}  English only, faster, rougher")
                say(f"        3. small     {models.human(models.CATALOG['small']['size'])}  99 languages")
                choice = {"1": "small.en", "2": "base.en", "3": "small",
                          "": "small.en"}.get(ask("Choose [1]:"), "small.en")
            try:
                models.download(choice)
            except models.ModelError as e:
                bad(str(e))
                return 1
            settings.set("model", choice)
            config.reload()      # the smoke test below must use the new model
            good(f"{choice} ready")

    step(4, total, "Testing transcription")
    sample = find_sample_wav()
    if gui:
        good("the Halo window ends with a real test dictation")
    elif not models.installed():
        warn("no speech model yet; skipping the test")
    elif not sample:
        warn("no sample audio found; skipping the test")
    else:
        say("        The first run compiles Metal shaders and takes ~25s.")
        say("        Every run after that is under a second.")
        t0 = time.time()
        try:
            import transcribe
            result = transcribe.transcribe(str(sample), "en")
            say(f'        heard: "{result.text[:70]}"')
            good(f"transcribed in {time.time()-t0:.1f}s using {result.model}")
        except Exception as e:                      # noqa: BLE001 - report anything
            bad(f"transcription failed: {e}")
            return 1

    step(5, total, "Cleanup (optional)")
    if gui:
        good("optional -- add a local model later in Halo's Settings > Models")
        args.local_model, args.no_key = False, True
    say("        Halo works fully offline. Punctuation, capitals, spoken")
    say('        marks ("comma", "new line"), fillers, self-corrections')
    say('        ("Thursday -- actually Friday"), lists, numbers and dates')
    say("        all happen on this Mac with no model and no key.")
    say("        A language model adds grammar repair on top. It can run on")
    say(f"        this Mac ({models.human(models.LLM_CATALOG['qwen2.5-1.5b']['size'])} download, nothing leaves the machine),")
    say("        or through OpenRouter (only the TEXT of a transcript is sent).")
    local_ready = local_llm_installed()
    if local_ready:
        good(f"local cleanup model {config.LOCAL_MODEL} is installed")
    elif args.local_model is False:
        good("local model skipped (--no-local-model)")
    elif args.local_model or confirm("Download the local cleanup model now?", default=False):
        if not shutil.which("llama-server") and not Path("/opt/homebrew/bin/llama-server").exists():
            warn("llama-server not found; install it with: brew install llama.cpp")
        try:
            models.download_llm(config.LOCAL_MODEL)
            good(f"{config.LOCAL_MODEL} ready -- Halo starts it when you dictate")
            local_ready = True
        except models.ModelError as e:
            warn(str(e))
    if local_ready:
        good("OpenRouter not needed; add a key later if you want it as a fallback")
    elif config.get_api_key():
        good("an OpenRouter key is already stored in your Keychain")
    elif args.no_key or not confirm("Add an OpenRouter key now?", default=False):
        good("skipped -- Halo cleans up with local rules. Add a model later with "
             "halo model local install, or a key in halo settings > Privacy")
    else:
        setup_key()

    step(6, total, "Installing the app")
    outcome = install_app_bundle()
    if outcome == "missing":
        bad("no built Halo.app found. From a checkout, run overlay/build_app.sh")
        return 1
    good({"installed": f"installed {paths.INSTALLED_APP}",
          "replaced": f"updated {paths.INSTALLED_APP} (permissions need re-granting)",
          "unchanged": f"{paths.INSTALLED_APP} is already current (permissions kept)",
          }[outcome])
    write_engine_pointer()

    if args.stable_identity is not False:
        sign_step(offer=args.stable_identity is None)

    # A changed identity leaves TCC rows bound to the previous one. They still
    # render switched ON in System Settings while the app is refused, so clear
    # them here -- otherwise the permission step below waits for a switch that
    # already looks flipped, and the user has nothing useful to do.
    #
    # Compared by designated requirement, not code hash: once the app is signed
    # with a certificate, a new build keeps the same identity and there is
    # nothing stale to clear.
    current = app_identity(paths.INSTALLED_APP)
    st = read_state()
    granted = st.get("granted_identity")
    if granted is None and st.get("granted_cdhash"):
        # Installed before identities were tracked by requirement. The old
        # value is a bare code hash; it is only comparable to a code hash, and
        # only meaningful while the app is still ad-hoc. Translate rather than
        # compare across kinds, or the first upgrade resets a perfectly good
        # grant for no reason.
        granted = (f'cdhash H"{st["granted_cdhash"]}"'
                   if signing.is_adhoc(paths.INSTALLED_APP) else current)
    if granted and current and granted != current:
        if reset_stale_grants():
            good("cleared the stale permission entries")
        else:
            warn("could not clear the old permission entries")
            say("        If Halo shows as already on below, switch it off and"
                " on again.")

    if args.no_agent:
        say(f"\n{DIM}skipping the login agent and permissions (--no-agent){RST}")
        return 0

    step(7, total, "Starting at login")
    render_plist()
    bootstrap_agent()
    good(f"LaunchAgent installed at {PLIST}")

    if gui:
        step(8, total, "Continuing in the Halo window")
        run(["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL}"])
        for _ in range(20):
            time.sleep(0.5)
            if socket_ask("onboarding 1") is not None:
                break
        else:
            warn("Halo did not open its window; run: halo setup --cli")
            return 1
        good("the setup guide is open: permissions, microphone, model, language, a test")
        say("        It picks up where you left off if you close it.")
        say("        Prefer Terminal? halo setup --cli")
        return 0

    step(8, total, "macOS permissions")
    grant_permissions(skip_if_ok=not args.repair)

    step(9, total, "Verifying")
    run(["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL}"])
    time.sleep(2.5)
    perms = permissions_from_app()
    for name in ("accessibility", "input monitoring", "microphone"):
        value = perms.get(name)
        if value is None:
            warn(f"{name:<17}: app not answering yet")
        elif value.upper().startswith("OK"):
            good(f"{name:<17}: OK")
        else:
            bad(f"{name:<17}: {value}")
    current = app_identity(paths.INSTALLED_APP)
    if current:
        write_state(granted_identity=current)

    say(f"\n{OK}Done.{RST} Hold F9 in any app and speak.")
    say("  Something wrong? Run: halo doctor")
    return 0


def find_sample_wav() -> Path | None:
    """whisper.cpp's own jfk.wav, wherever this install put it."""
    candidates = []
    prefix = run(["brew", "--prefix", "whisper.cpp"]).stdout.strip()
    if prefix:
        candidates.append(Path(prefix) / "share" / "whisper.cpp" / "jfk.wav")
    candidates += [
        Path(config.WHISPER_BIN).parent.parent / "share" / "whisper.cpp" / "jfk.wav",
        paths.LEGACY_WHISPER_DIR / "samples" / "jfk.wav",
    ]
    return next((c for c in candidates if c.exists()), None)


def setup_key() -> None:
    say("        Get one at https://openrouter.ai/keys (free tier is enough).")
    say("        Then at https://openrouter.ai/settings/privacy set")
    say("          Zero Data Retention > Non-frontier : OFF")
    say('          "Allow free endpoints that train on request data" : ON')
    say("        Free models 404 without both -- it is the most common setup error.")
    try:
        key = getpass.getpass("  Paste your key (hidden, Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        good("skipped")
        return
    r = run(["security", "add-generic-password", "-s", config.KEYCHAIN_SERVICE,
             "-a", os.environ.get("USER", ""), "-T", "/usr/bin/security",
             "-U", "-w", key])
    if r.returncode != 0:
        bad(f"could not save to the Keychain: {(r.stderr or r.stdout).strip()}")
        return
    good("saved to your Keychain")
    say("        checking it...")
    try:
        import cleanup
        result = cleanup.clean("um so this is a test of the cleanup")
        if result.source == "llm":
            good(f'cleanup works: "{result.text}"')
        else:
            warn(f"the key was saved but cleanup fell back to raw ({result.detail})")
            warn("check the two OpenRouter privacy settings above")
    except Exception as e:                          # noqa: BLE001
        warn(f"could not verify the key: {e}")


def grant_permissions(skip_if_ok: bool = True) -> None:
    perms = permissions_from_app()
    if skip_if_ok and perms and all(
            v.upper().startswith("OK") for v in perms.values()):
        good("already granted")
        return

    app_path = str(paths.INSTALLED_APP)
    say("        Halo needs three permissions. Grant them to Halo itself --")
    say("        not to your terminal, and not to python.")

    say(f"\n        {DIM}1. Microphone{RST}")
    say("        A prompt appears on its own the first time Halo runs.")
    say("        Click Allow. (This pane has no + button, so it cannot be")
    say("        added by hand -- and a missed prompt records pure silence.)")
    ask("Press Return when you have clicked Allow (or if you already did).")

    import permissions as perms_mod

    say(f"\n        {DIM}2. Accessibility{RST}")
    say("        In the window that opens, switch Halo on.")
    say("        If Halo is not listed: click +, press Cmd+Shift+G, paste")
    say(f"          {app_path}")
    perms_mod.open_settings("Accessibility")
    if wait_for_permission("accessibility"):
        good("accessibility granted")
        # macOS only re-reads this grant when the process starts, and the
        # engine exited earlier precisely because it was missing. Restart it
        # here or the user flips the switch and nothing happens.
        run(["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL}"])
        time.sleep(2)
    else:
        warn("accessibility still off -- the hotkey will not work")
        say("        Grant it later, then run: halo restart")

    # Input Monitoring registers itself once pynput builds its event tap, so
    # with the engine now running it is usually already on. Only send someone
    # to System Settings if it genuinely is not.
    say(f"\n        {DIM}3. Input Monitoring{RST}")
    if permissions_from_app().get("input monitoring", "").upper().startswith("OK"):
        good("input monitoring granted automatically")
    else:
        say("        In the window that opens, switch Halo on.")
        say(f"        If Halo is not listed: + , Cmd+Shift+G, {app_path}")
        perms_mod.open_settings("ListenEvent")
        if wait_for_permission("input monitoring", timeout=120):
            good("input monitoring granted")
        else:
            warn("input monitoring still off (advisory -- dictation may still work)")

    say("\n        With that, you can revoke Accessibility from your terminal")
    say("        and editor if you had granted it: the permission now belongs")
    say("        to a small purpose-built app instead of something that can")
    say("        run arbitrary code.")


# --- everyday commands ----------------------------------------------------

def cmd_start(args) -> int:
    if not PLIST.exists():
        bad("not installed yet. Run: halo setup")
        return 1
    r = run(["launchctl", "bootstrap", DOMAIN, str(PLIST)])
    if r.returncode != 0 and "already" not in (r.stderr or ""):
        bad((r.stderr or r.stdout).strip())
        return 1
    good("started")
    return 0


def cmd_stop(args) -> int:
    run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"])
    run(["pkill", "-f", "halo.py"])
    good("stopped (it will start again at login unless you uninstall)")
    return 0


def cmd_restart(args) -> int:
    if not PLIST.exists():
        bad("not installed yet. Run: halo setup")
        return 1
    r = run(["launchctl", "kickstart", "-k", f"{DOMAIN}/{LABEL}"])
    if r.returncode != 0:
        bootstrap_agent()
    good("restarted")
    return 0


def cmd_status(args) -> int:
    say(f"\n{DIM}launchd{RST}")
    r = run(["launchctl", "print", f"{DOMAIN}/{LABEL}"])
    if r.returncode != 0:
        bad("not loaded. Run: halo setup")
    else:
        for line in r.stdout.splitlines():
            s = line.strip()
            if s.startswith(("state =", "pid =", "last exit code =")):
                say(f"  {s}")

    say(f"\n{DIM}processes{RST}")
    for label, pattern in (("app   ", "Halo.app/Contents/MacOS/Halo"),
                           ("engine", "halo.py")):
        r = run(["pgrep", "-fl", pattern])
        say(f"  {label} {r.stdout.strip() or '-- not running'}")

    say(f"\n{DIM}permissions (as the running app){RST}")
    perms = permissions_from_app()
    if not perms:
        warn("the app is not answering on its socket")
    for name, value in perms.items():
        (good if value.upper().startswith("OK") else bad)(f"{name:<17}: {value}")

    say(f"\n{DIM}config{RST}")
    say(f"  settings : {paths.SETTINGS_FILE}")
    say(f"  model    : {config.WHISPER_MODEL_EN if config.WHISPER_MODEL_EN.exists() else 'MISSING'}")
    say(f"  whisper  : {config.WHISPER_BIN}")
    say(f"  api key  : {'found' if config.get_api_key() else 'none (raw transcripts)'}")
    return 0


def cmd_logs(args) -> int:
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    files = [str(paths.ENGINE_LOG), str(paths.OVERLAY_LOG)]
    cmd = ["tail", "-n", str(args.lines)] + (["-f"] if args.follow else []) + files
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_settings(args) -> int:
    """Open the Settings window in the running app.

    The window lives in Halo.app because that is the process that already has
    an event loop and a screen; this command is just the doorbell. It exists so
    the menu bar icon can stay off by default -- without it, a user who never
    enables the icon would have no way to reach the window at all.
    """
    tab = getattr(args, "tab", None)
    reply = socket_ask(f"settings {tab}" if tab else "settings")
    if reply is not None:
        good("opened Settings")
        return 0

    # Nothing is listening. Either Halo is not running, or the overlay is
    # turned off -- and the second case is the confusing one, because the
    # hotkey still works, so nothing looks broken.
    if not settings.get("overlay"):
        bad("the overlay is disabled, so there is no window to open.")
        say("  Turn it back on:  halo config set overlay true")
        return 1
    bad("Halo is not running.")
    say("  Start it:  halo start        (or `halo setup` if this is a new Mac)")
    say(f"  Meanwhile, the same settings are plain JSON in {paths.SETTINGS_FILE}")
    return 1


def cmd_config(args) -> int:
    if args.action == "path":
        say(str(paths.SETTINGS_FILE))
        return 0
    if args.action == "edit":
        paths.seed_user_config()
        editor = os.environ.get("EDITOR", "open -t").split()
        subprocess.run(editor + [str(paths.SETTINGS_FILE)])
        say("  Run `halo restart` to apply.")
        return 0
    if args.action == "set":
        if not args.key or args.value is None:
            bad("usage: halo config set <key> <value>")
            return 1
        value: object = args.value
        if args.value.lower() in ("true", "false"):
            value = args.value.lower() == "true"
        elif args.value.isdigit():
            value = int(args.value)
        if args.key == "hotkey":
            from pynput import keyboard
            if getattr(keyboard.Key, str(value).lower(), None) is None:
                bad(f"{value!r} is not a key name. Try f9, f12, f13.")
                return 1
        if args.key == "activation" and str(value).lower() not in ("hold", "toggle"):
            bad(f"{value!r} is not an activation mode. Use hold or toggle.")
            return 1
        if args.key == "cleanup.mode" and str(value).lower() not in config.CLEANUP_MODES:
            bad(f"{value!r} is not a cleanup mode. Use {', '.join(config.CLEANUP_MODES)}.")
            return 1
        if args.key == "cleanup.provider" and str(value).lower() not in config.CLEANUP_PROVIDERS:
            bad(f"{value!r} is not a provider. Use {', '.join(config.CLEANUP_PROVIDERS)}.")
            return 1
        if args.key == "cleanup.local.model" and value not in models.LLM_CATALOG:
            bad(f"{value!r} is not a local model. Use {', '.join(models.LLM_CATALOG)}.")
            return 1
        settings.set(args.key, value)
        config.reload()
        good(f"{args.key} = {value}  ({paths.SETTINGS_FILE})")
        if confirm("Restart Halo to apply?", default=True):
            return cmd_restart(args)
        return 0

    keys = ["hotkey", "activation", "max_recording_sec", "language", "model",
            "whisper_bin", "whisper_threads",
            "overlay", "menu_bar", "orb.scale", "orb.position", "orb.inset",
            "dictation.spoken_punctuation", "dictation.strip_fillers",
            "dictation.terminal_punctuation", "dictation.self_correction",
            "dictation.smart_formatting", "dictation.chat_period",
            "whisper.prompt", "whisper.suppress_nst",
            "privacy_default", "context.enabled",
            "cleanup.mode", "cleanup.provider", "cleanup.enabled",
            "cleanup.local.backend", "cleanup.local.model",
            "cleanup.local.endpoint", "cleanup.local.budget_ms",
            "cleanup.local.polished_budget_ms", "cleanup.local.idle_unload_min",
            "cleanup.total_budget_sec", "cleanup.ai_budget_sec"]
    say(f"\n{DIM}{paths.SETTINGS_FILE}{RST}")
    for key in keys:
        say(f"  {key:<34} {str(settings.get(key)):<20} {DIM}{settings.source_of(key)}{RST}")
    say(f"\n  everything in {paths.CONFIG_DIR} reloads while Halo runs.")
    say("  a hotkey change rebinds as soon as Halo is idle; no restart needed.")
    say("  `halo settings` opens the same options in a window.")
    return 0


def cmd_model(args) -> int:
    if args.action == "local":
        return cmd_model_local(args)
    if args.action == "catalog":
        data = models.catalog_json(settings.get("model") or "small.en", config.LOCAL_MODEL)
        if args.json:
            print(json.dumps(data))
        else:
            models.print_catalog()
            say()
            models.print_llm_catalog(config.LOCAL_MODEL)
        return 0
    if args.action == "remove":
        if not args.name:
            bad("usage: halo model remove <name>")
            return 1
        good("removed" if models.remove(args.name) else f"{args.name} was not in {paths.MODELS_DIR}")
        return 0
    if args.action == "list":
        models.print_catalog()
        return 0
    if args.action == "path":
        path = models.installed_path(args.name) if args.name else config.WHISPER_MODEL_EN
        say(str(path) if path else "not installed")
        return 0
    if args.action == "verify":
        return 0 if models.verify(args.name or "small.en") else 1
    try:
        models.download(args.name or "small.en", force=args.force)
    except models.ModelError as e:
        bad(str(e))
        return 1
    return 0


def cmd_model_local(args) -> int:
    """halo model local [list|install|verify|remove|status] [name]"""
    import local_llm
    sub, name = (args.name or "list"), (args.extra or config.LOCAL_MODEL)
    if sub == "list":
        models.print_llm_catalog(config.LOCAL_MODEL)
        say(f"\n  * is the one Halo uses (cleanup.local.model). Mode: {config.CLEANUP_MODE}")
        return 0
    if sub == "install":
        try:
            models.download_llm(name, force=args.force)
        except models.ModelError as e:
            bad(str(e))
            return 1
        if name != config.LOCAL_MODEL:
            settings.set("cleanup.local.model", name)
            good(f"cleanup.local.model = {name}")
        if not local_llm.find_server_binary():
            warn("llama-server not found. Install it with: brew install llama.cpp")
        say("  Halo picks it up on your next dictation; no restart needed.")
        return 0
    if sub == "verify":
        return 0 if models.verify_llm(name) else 1
    if sub == "remove":
        good("removed" if models.remove_llm(name) else f"{name} was not installed")
        return 0
    if sub == "status":
        st = local_llm.read_status()
        say(f"  model   : {config.LOCAL_MODEL} "
            f"({'installed' if models.llm_path(config.LOCAL_MODEL) else 'not installed'})")
        say(f"  server  : {local_llm.find_server_binary() or 'llama-server not found'}")
        if st:
            say(f"  state   : {st.get('state')}" + (f" -- {st['detail']}" if st.get("detail") else ""))
        else:
            say("  state   : not started yet")
        return 0
    bad(f"unknown action {sub!r}: use list, install, verify, remove or status")
    return 1


def cmd_dictionary(args) -> int:
    """halo dictionary export [--format csv] [file] | import <file>"""
    import dictionary
    d = dictionary.Dictionary()
    if args.action == "export":
        text = d.export(args.format)
        if args.file:
            Path(args.file).write_text(text, encoding="utf-8")
            good(f"wrote {len(d.terms)} entries to {args.file}")
        else:
            sys.stdout.write(text)
        return 0
    if args.action == "import":
        if not args.file:
            bad("usage: halo dictionary import <file.json|file.csv>")
            return 1
        try:
            entries = d.parse_import(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            bad(f"could not read {args.file}: {e}")
            return 1
        added, updated = d.merge(entries)
        good(f"{added} added, {updated} updated")
        return 0
    return 1


def cmd_key(args) -> int:
    if args.action == "status":
        key = config.get_api_key()
        if key:
            good(f"a key is stored (…{key[-4:]})")
        else:
            say("  no key. Halo injects raw transcripts; everything stays local.")
        return 0
    if args.action == "clear":
        r = run(["security", "delete-generic-password", "-s", config.KEYCHAIN_SERVICE])
        good("removed" if r.returncode == 0 else "no key was stored")
        return 0
    setup_key()
    return 0


def cmd_doctor(args) -> int:
    problems = 0
    say(f"\n{DIM}system{RST}")
    mac_ver = run(["sw_vers", "-productVersion"]).stdout.strip()
    good(f"macOS {mac_ver} on {run(['uname', '-m']).stdout.strip()}")

    say(f"\n{DIM}speech{RST}")
    if config.WHISPER_BIN.exists() and os.access(config.WHISPER_BIN, os.X_OK):
        good(f"whisper-cli  {config.WHISPER_BIN}")
    else:
        problems += 1
        bad(f"whisper-cli missing ({config.WHISPER_BIN})")
        say("        fix: brew install whisper.cpp && halo setup")
    if config.WHISPER_MODEL_EN.exists() or config.WHISPER_MODEL_MULTI.exists():
        good(f"model        {config.WHISPER_MODEL_EN if config.WHISPER_MODEL_EN.exists() else config.WHISPER_MODEL_MULTI}")
    else:
        problems += 1
        bad("no speech model installed")
        say("        fix: halo model download small.en")

    say(f"\n{DIM}engine{RST}")
    missing = []
    for mod in ("numpy", "sounddevice", "pynput", "requests"):
        r = run([str(python_exe()), "-c", f"import {mod}"])
        if r.returncode != 0:
            missing.append(mod)
    if missing:
        problems += 1
        bad(f"python packages missing: {', '.join(missing)}")
        say("        fix: brew reinstall halo")
    else:
        good(f"python deps  {python_exe()}")

    say(f"\n{DIM}app{RST}")
    src, installed = bundled_app(), paths.INSTALLED_APP
    if not installed.exists():
        problems += 1
        bad(f"{installed} is missing")
        say("        fix: halo setup")
    else:
        good(f"installed at {installed}")
        stable = not signing.is_adhoc(installed)
        if stable:
            good("signed with a certificate -- upgrades keep your permissions")
        else:
            warn("signed ad-hoc -- every upgrade voids your permissions")
            say("        fix (optional): halo setup --stable-identity")

        # Against the source hash recorded at install time: the installed copy
        # gets re-signed locally, so its own hash never matches the shipped one.
        there = cdhash(src) if src else None
        installed_from = read_state().get("installed_from")
        if there and installed_from and there != installed_from:
            problems += 1
            bad("a newer build is available and differs from the installed app")
            if not stable:
                say("        Updating it voids Accessibility and Input Monitoring,")
                say("        because Halo is signed ad-hoc.")
            say("        fix: halo setup --repair")

        # By designated requirement, not code hash: under a certificate a new
        # build keeps the same identity, and reporting it as voided would send
        # people to re-grant something that never lapsed.
        st = read_state()
        granted = st.get("granted_identity") or st.get("granted_cdhash")
        here_id = app_identity(installed)
        if granted and here_id and granted != here_id:
            problems += 1
            bad("the app changed since you granted permissions -- macOS has voided them")
            say("        fix: halo setup --repair")

    say(f"\n{DIM}agent{RST}")
    if not PLIST.exists():
        problems += 1
        bad("no LaunchAgent installed")
        say("        fix: halo setup")
    elif agent_running():
        good("running, and starts at login")
        # The app can be up with the engine dead: the engine exits when
        # Accessibility is missing and the app will not respawn it on a config
        # error. Grant the permission afterwards and everything reads healthy
        # while the hotkey stays dead, which is exactly the state that looks
        # like a Halo bug and is actually one restart away.
        if not engine_running():
            problems += 1
            bad("the app is running but the engine is not")
            say("        Usually means a permission was granted after the engine")
            say("        gave up. macOS only re-reads grants on start.")
            say("        fix: halo restart")
    else:
        problems += 1
        bad("installed but not running")
        say("        fix: halo restart")

    if not args.offline:
        say(f"\n{DIM}permissions (as the running app){RST}")
        perms = permissions_from_app()
        if not perms:
            problems += 1
            bad("the app is not answering; cannot read its permissions")
            say("        fix: halo restart")
        for name, value in perms.items():
            if value.upper().startswith("OK"):
                good(f"{name:<17}: OK")
            else:
                problems += 1
                bad(f"{name:<17}: {value}")
                say("        fix: halo setup --repair")

    say(f"\n{DIM}cleanup{RST}")
    import local_llm
    good(f"mode {config.CLEANUP_MODE}, provider {config.CLEANUP_PROVIDER}, "
         f"context awareness {'on' if config.CONTEXT_ENABLED else 'off'}")
    if config.LOCAL_BACKEND == "endpoint":
        say(f"  local model: your server at {config.LOCAL_ENDPOINT or '(not set)'}")
    elif models.llm_path(config.LOCAL_MODEL):
        good(f"local model  {config.LOCAL_MODEL}")
        server = local_llm.find_server_binary()
        if server:
            good(f"llama-server {server}")
        else:
            problems += 1
            bad("llama-server not found, so the local model cannot run")
            say("        fix: brew install llama.cpp")
        st = local_llm.read_status()
        if st.get("state") == "failed":
            problems += 1
            bad(f"local model failed: {st.get('detail', '')}")
            say("        fix: halo model local verify, then halo restart")
        elif st:
            say(f"  local model state: {st.get('state')}"
                + (f" ({st['detail']})" if st.get("detail") else ""))
    else:
        say("  no local model -- rules only unless OpenRouter is set up. Not a problem.")
        say("  add one: halo model local install")
    if config.get_api_key():
        good("OpenRouter key found" + ("" if config.CLEANUP_ENABLED
                                       else " (but cleanup.enabled is off)"))
    if config.CLEANUP_PROVIDER == "openrouter" and read_privacy_default():
        warn("provider is openrouter but Privacy Mode starts on: cleanup will be rules only")

    say(f"\n{DIM}config{RST}")
    for path in (paths.SETTINGS_FILE, paths.DICTIONARY_FILE,
                 paths.SNIPPETS_FILE, paths.COMMANDS_FILE):
        if not path.exists():
            warn(f"{path.name} missing (halo setup re-creates it)")
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
                good(f"{path.name}")
            except ValueError as e:
                problems += 1
                bad(f"{path.name} is not valid JSON: {e}")

    last_error = None
    if paths.ENGINE_LOG.exists():
        for line in paths.ENGINE_LOG.read_text(errors="replace").splitlines()[-400:]:
            if "ERROR" in line:
                last_error = line.strip()
    if last_error:
        say(f"\n{DIM}last error in the log{RST}\n  {last_error}")

    say()
    if problems:
        bad(f"{problems} problem(s) found.")
    else:
        good("everything checks out. Hold F9 and speak.")
    return 1 if problems else 0


def read_privacy_default() -> bool:
    try:
        return bool(json.loads(paths.STATE_FILE.read_text(encoding="utf-8"))
                    .get("privacy_mode", config.PRIVACY_MODE_DEFAULT))
    except (OSError, ValueError):
        return config.PRIVACY_MODE_DEFAULT


def cmd_uninstall(args) -> int:
    say("\nThis removes the background agent, the app, and its permissions.")
    if not args.yes and not confirm("Continue?", default=False):
        say("  cancelled")
        return 0

    run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"])
    run(["pkill", "-f", "Halo.app/Contents/MacOS/Halo"])
    run(["pkill", "-f", "halo.py"])
    # The local cleanup server runs in its own session so it survives an
    # engine crash; its "-a halo-cleanup" alias is how to find only ours.
    run(["pkill", "-f", "halo-cleanup"])
    PLIST.unlink(missing_ok=True)
    good("login agent removed")

    # Reset the grants BEFORE deleting the bundle. tccutil resolves a bundle
    # identifier through LaunchServices, so once Halo.app is gone every reset
    # fails with -10814 ("No such bundle identifier") and the stale rows are
    # left behind -- which is what makes a later reinstall look granted in
    # System Settings while the app still gets refused.
    stale = [s for s in ("Accessibility", "ListenEvent", "Microphone")
             if run(["tccutil", "reset", s, LABEL]).returncode != 0]
    if stale:
        warn(f"could not reset: {', '.join(stale)}")
        say("        System Settings > Privacy & Security -- remove Halo by hand")
    else:
        good("permission grants reset")

    shutil.rmtree(paths.INSTALLED_APP, ignore_errors=True)
    good(f"{paths.INSTALLED_APP} removed")

    r = run(["security", "delete-generic-password", "-s", config.KEYCHAIN_SERVICE])
    good("API key removed from the Keychain" if r.returncode == 0
         else "no API key was stored")

    if signing.identity_sha1() or signing.KEYCHAIN.exists():
        signing.remove()
        good("signing certificate and its keychain removed")

    if args.purge:
        size = sum(p.stat().st_size for pat in ("*.bin", "*.gguf")
                   for p in paths.MODELS_DIR.glob(pat)) \
            if paths.MODELS_DIR.exists() else 0
        if size and not args.yes:
            say(f"\n  This also deletes {models.human(size)} of models,")
            say("  which have to be downloaded again if you reinstall.")
            if not confirm("Delete them?", default=False):
                args.purge = False
        if args.purge:
            for d in (paths.CONFIG_DIR, paths.DATA_DIR, paths.LOG_DIR):
                shutil.rmtree(d, ignore_errors=True)
            paths.LEGACY_STATE_FILE.unlink(missing_ok=True)
            good("settings, models and logs removed")
    else:
        say("\n  Kept your settings and models:")
        say(f"    {paths.CONFIG_DIR}")
        say(f"    {paths.DATA_DIR}")
        say("  Remove them too with: halo uninstall --purge")

    say("\n  Finally, to remove the program itself:  brew uninstall halo")
    return 0


def version() -> str:
    for candidate in (Path(__file__).resolve().parent / "VERSION",
                      Path(__file__).resolve().parent.parent / "VERSION"):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return "dev"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="halo",
        description="Local push-to-talk dictation for macOS. Hold F9 and speak.")
    p.add_argument("--version", action="version", version=f"halo {version()}")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("setup", help="first-time setup (safe to re-run)")
    s.add_argument("--repair", action="store_true",
                   help="re-do the permission steps")
    s.add_argument("--model", help="model to install, e.g. small.en")
    s.add_argument("--force-model", action="store_true",
                   help="download even if a model is present")
    s.add_argument("--no-model", action="store_true", help="skip the model step")
    s.add_argument("--no-key", action="store_true", help="skip the API key step")
    s.add_argument("--local-model", dest="local_model", action="store_true", default=None,
                   help="download the local cleanup model without asking")
    s.add_argument("--no-local-model", dest="local_model", action="store_false",
                   help="skip the local cleanup model")
    s.add_argument("--cli", action="store_true",
                   help="do everything in Terminal instead of the Halo window")
    s.add_argument("--no-agent", action="store_true",
                   help="set up files only: no login agent, no permissions")
    # Tri-state on purpose: None means ask, True means yes without asking,
    # False means stay ad-hoc. Setup has to be runnable unattended.
    s.add_argument("--stable-identity", dest="stable_identity",
                   action="store_true", default=None,
                   help="sign with a certificate so upgrades keep permissions")
    s.add_argument("--no-stable-identity", dest="stable_identity",
                   action="store_false",
                   help="stay ad-hoc; every upgrade needs re-granting")
    s.set_defaults(func=cmd_setup)

    for name, fn, help_text in (
            ("start", cmd_start, "start the background agent"),
            ("stop", cmd_stop, "stop it until the next login"),
            ("restart", cmd_restart, "restart it (after changing settings)"),
            ("status", cmd_status, "what is running, and its permissions"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(func=fn)

    d = sub.add_parser("doctor", help="diagnose a Halo that is not working")
    d.add_argument("--offline", action="store_true",
                   help="skip checks that need the running app")
    d.set_defaults(func=cmd_doctor)

    lg = sub.add_parser("logs", help="show recent log output")
    lg.add_argument("-n", "--lines", type=int, default=60)
    lg.add_argument("-f", "--follow", action="store_true")
    lg.set_defaults(func=cmd_logs)

    st = sub.add_parser("settings", help="open the Settings window")
    st.add_argument("tab", nargs="?",
                    choices=["general", "dictation", "microphone", "intelligence", "styles",
                             "dictionary", "commands", "models", "history", "privacy",
                             "permissions", "advanced"],
                    help="open straight to this section")
    st.set_defaults(func=cmd_settings)

    c = sub.add_parser("config", help="show or change settings")
    c.add_argument("action", nargs="?", default="show",
                   choices=["show", "edit", "set", "path"])
    c.add_argument("key", nargs="?")
    c.add_argument("value", nargs="?")
    c.set_defaults(func=cmd_config)

    m = sub.add_parser("model", help="manage speech models and the local cleanup model",
                       epilog="halo model local [list|install|verify|remove|status] [name]")
    m.add_argument("action", nargs="?", default="list",
                   choices=["list", "download", "path", "verify", "local", "catalog",
                            "remove"])
    m.add_argument("--json", action="store_true", help="machine-readable catalog")
    m.add_argument("name", nargs="?")
    m.add_argument("extra", nargs="?", help=argparse.SUPPRESS)
    m.add_argument("--force", action="store_true")
    m.set_defaults(func=cmd_model)

    dc = sub.add_parser("dictionary", help="import or export your vocabulary")
    dc.add_argument("action", choices=["export", "import"])
    dc.add_argument("file", nargs="?")
    dc.add_argument("--format", choices=["json", "csv"], default="json")
    dc.set_defaults(func=cmd_dictionary)

    k = sub.add_parser("key", help="manage the optional OpenRouter key")
    k.add_argument("action", nargs="?", default="status",
                   choices=["status", "set", "clear"])
    k.set_defaults(func=cmd_key)

    u = sub.add_parser("uninstall", help="remove Halo from this Mac")
    u.add_argument("--purge", action="store_true",
                   help="also delete settings, models and logs")
    u.add_argument("-y", "--yes", action="store_true", help="do not ask")
    u.set_defaults(func=cmd_uninstall)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        say("\n  cancelled")
        return 130
    except SettingsFileError as e:
        bad(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
