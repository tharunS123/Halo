"""The downloaded Halo.app: the engine recognises that it is running inside
the bundle (Contents/Resources/engine) and uses the whisper-cli and
llama-server shipped beside it, while a checkout or a Homebrew install is left
exactly as it was. Hermetic: the bundle is a fake laid out in a temp dir.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


def probe(engine_dir: Path, home: Path, code: str) -> str:
    """Run `code` with the engine imported from engine_dir, in a clean HOME."""
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    for k in ("HALO_CONFIG_DIR", "HALO_DATA_DIR", "HALO_MODELS_DIR", "HALO_LOG_DIR"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(engine_dir)!r})\n{code}"],
                       capture_output=True, text=True, env=env, cwd=engine_dir)
    if r.returncode != 0:
        return "ERROR " + r.stderr.strip().splitlines()[-1]
    return r.stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()
    home = tmp / "home"
    home.mkdir()

    app = tmp / "Applications" / "Halo.app"
    engine = app / "Contents" / "Resources" / "engine"
    helpers = app / "Contents" / "Helpers"
    engine.mkdir(parents=True)
    helpers.mkdir(parents=True)
    for py in ROOT.glob("*.py"):
        shutil.copy2(py, engine / py.name)
    shutil.copytree(ROOT / "defaults", app / "Contents" / "Resources" / "share" / "defaults")
    for tool in ("whisper-cli", "llama-server"):
        (helpers / tool).write_text("#!/bin/sh\n")
        (helpers / tool).chmod(0o755)

    print("\n=== inside the downloaded app ===")
    got = probe(engine, home, "import paths; print(paths.APP_BUNDLE); print(paths.INSTALLED_APP); "
                              "print(paths.DEFAULTS_DIR)")
    lines = got.splitlines()
    check("the bundle is recognised", lines[:1] == [str(app)], got)
    check("it is its own installed app (no copy to ~/Applications)",
          lines[1:2] == [str(app)], got)
    check("defaults come from Resources/share",
          lines[2:3] == [str(app / "Contents/Resources/share/defaults")], got)

    got = probe(engine, home, "import config; print(config.find_whisper_bin())")
    check("whisper-cli comes from Contents/Helpers", got == str(helpers / "whisper-cli"), got)

    got = probe(engine, home, "import local_llm; print(local_llm.find_server_binary())")
    check("llama-server comes from Contents/Helpers", got == str(helpers / "llama-server"), got)

    # A settings.json left by an earlier Homebrew install names a whisper-cli
    # that `brew uninstall` has since removed.
    cfg = home / ".config" / "halo"
    cfg.mkdir(parents=True)
    (cfg / "settings.json").write_text('{"whisper_bin": "/nonexistent/whisper-cli"}')
    got = probe(engine, home, "import config; print(config.find_whisper_bin())")
    check("a stale Homebrew whisper_bin does not strand the app",
          got == str(helpers / "whisper-cli"), got)

    real = tmp / "custom-whisper"
    real.write_text("#!/bin/sh\n")
    real.chmod(0o755)
    (cfg / "settings.json").write_text(f'{{"whisper_bin": "{real}"}}')
    got = probe(engine, home, "import config; print(config.find_whisper_bin())")
    check("a whisper_bin that exists is still honoured", got == str(real), got)

    got = probe(engine, home, "import cli; print(cli.DOWNLOADED)")
    check("the CLI knows it is the downloaded app", got == "True", got)

    print("\n=== a checkout is unchanged ===")
    got = probe(ROOT, home, "import paths, cli; print(paths.APP_BUNDLE, paths.HELPERS_DIR, cli.DOWNLOADED)")
    check("no bundle, no helpers, not downloaded", got == "None None False", got)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
