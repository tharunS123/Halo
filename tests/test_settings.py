"""Settings precedence, and the refusal to clobber a settings.json typo.

The clobber case is the one that matters: `halo config edit` opens the file in
an editor, and a trailing comma is the easiest mistake in JSON. load() then
returns False with _data empty, so a set() that ignored it would rewrite the
whole file as a single key and silently discard every other setting.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="halo-settings-"))
os.environ["HALO_CONFIG_DIR"] = str(TMP)
os.environ["HALO_DATA_DIR"] = str(TMP / "data")

from settings import DEFAULTS, Settings, SettingsFileError

ok = True


def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {name}")
    if not good:
        print(f"         want: {want!r}\n         got : {got!r}")


print("=== precedence: env > settings.json > default ===")
f = TMP / "settings.json"
f.write_text(json.dumps({"hotkey": "f12", "cleanup": {"enabled": False}}) + "\n")
s = Settings(f)
check("file beats default", s.get("hotkey"), "f12")
check("default when absent", s.get("language"), DEFAULTS["language"])
check("dotted key", s.get("cleanup.enabled"), False)
os.environ["HALO_HOTKEY"] = "f13"
check("env beats file", s.get("hotkey"), "f13")
check("source_of reports env", s.source_of("hotkey"), "env HALO_HOTKEY")
del os.environ["HALO_HOTKEY"]

print("\n=== set() round-trips and keeps the other keys ===")
s.set("whisper_threads", 4)
on_disk = json.loads(f.read_text())
check("new key written", on_disk.get("whisper_threads"), 4)
check("existing key kept", on_disk.get("hotkey"), "f12")
check("nested kept", on_disk.get("cleanup"), {"enabled": False})

print("\n=== set() refuses to overwrite a file it cannot parse ===")
bad = TMP / "broken.json"
original = '{\n  "hotkey": "f12",\n  "language": "en",\n  "model": "small.en",\n}\n'
bad.write_text(original)                       # trailing comma
b = Settings(bad)
raised = False
try:
    b.set("whisper_threads", 4)
except SettingsFileError:
    raised = True
check("raises SettingsFileError", raised, True)
check("file left byte-for-byte alone", bad.read_text(), original)

print("\n=== but a missing file is still created ===")
fresh = TMP / "fresh.json"
Settings(fresh).set("hotkey", "f9")
check("created", json.loads(fresh.read_text()), {"hotkey": "f9"})

print("\n=== config.reload() picks up every derived value ===")
# HOTKEY and PRIVACY_MODE_DEFAULT were declared global in reload() but never
# assigned, so `halo config set hotkey f12` left the running process on the old
# value. reload() documents itself as recomputing everything.
live = TMP / "settings.json"
live.write_text(json.dumps({"hotkey": "f9", "privacy_default": False}) + "\n")
import config
check("HOTKEY before", config.HOTKEY, "f9")
check("PRIVACY_MODE_DEFAULT before", config.PRIVACY_MODE_DEFAULT, False)
live.write_text(json.dumps({"hotkey": "f12", "privacy_default": True}) + "\n")
config.reload()
check("HOTKEY after reload", config.HOTKEY, "f12")
check("PRIVACY_MODE_DEFAULT after reload", config.PRIVACY_MODE_DEFAULT, True)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
