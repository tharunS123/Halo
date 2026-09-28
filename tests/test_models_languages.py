"""Damaged and missing models, and language preferences.

Models: a file whose checksum is wrong is reported as such and never
silently trusted; editing a verified file forgets the verification; a
truncated cleanup model is "damaged", the model is not started, and
dictation falls back to the rules; a speech model whisper cannot load
surfaces as "Speech model damaged", not a stack trace; a missing model falls
back to one that is installed and says so.

Languages: the spoken switcher, the recently-used list, regional variants,
and a non-English language turning the English-only rules off.
"""
import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="halo-models-"))
shutil.copytree(FIXTURES, TMP / "config")
os.environ["HALO_CONFIG_DIR"] = str(TMP / "config")
os.environ["HALO_DATA_DIR"] = str(TMP / "data")
os.environ["HALO_MODELS_DIR"] = str(TMP / "models")
os.environ["HALO_OVERLAY"] = "0"
(TMP / "models").mkdir(parents=True)

import config  # noqa: E402
import halo  # noqa: E402
import languages  # noqa: E402
import local_llm  # noqa: E402
import models  # noqa: E402
import overlay  # noqa: E402
import paths  # noqa: E402
import pipeline  # noqa: E402
import settings as settings_mod  # noqa: E402
import transcribe  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


quiet = contextlib.redirect_stdout(io.StringIO())
# Hermetic: never the developer's own pre-1.0 ~/whisper.cpp models.
paths.LEGACY_WHISPER_MODELS = TMP / "no-legacy"

print("=== a speech model with the wrong checksum ===")
bad = paths.MODELS_DIR / models.filename("base.en")
with open(bad, "wb") as fh:                 # the right size, the wrong bytes (sparse:
    fh.truncate(models.CATALOG["base.en"]["size"])   # no real disk used)
with quiet:
    good = models.verify("base.en")
check("verify says no", good is False)
check("...and remembers it for the Models pane", models.verified_state(bad) is False)
entry = next(m for m in models.catalog_json()["speech"] if m["id"] == "base.en")
check("the catalog shows it installed but not verified",
      entry["installed"] and entry["verified"] is False, entry)
os.utime(bad, (1, 1))
check("changing the file forgets the old verdict", models.verified_state(bad) is None)

print("\n=== ...that whisper cannot load ===")
fake_cli = TMP / "whisper-cli"
fake_cli.write_text("#!/bin/sh\necho 'whisper_init_from_file: failed to load model' >&2\nexit 1\n")
fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR)
config.WHISPER_BIN = fake_cli
config.WHISPER_MODEL_EN = bad
wav = TMP / "clip.wav"
wav.write_bytes(b"RIFF")
try:
    transcribe.transcribe(str(wav), "en")
    check("whisper failing to load the model is an error", False)
except transcribe.TranscriptionError as e:
    check("whisper failing to load the model is reported as damage", "damaged" in str(e), e)
    check("...and the orb says it in four words, no stack trace",
          halo.friendly(e) == "Speech model damaged", halo.friendly(e))

print("\n=== a missing speech model ===")
config.WHISPER_MODEL_EN = paths.MODELS_DIR / models.filename("small.en")   # chosen, absent
config.WHISPER_MODEL_MULTI = paths.MODELS_DIR / models.filename("small")
model, warning = transcribe.model_for("en")
check("falls back to one that is installed", model == bad, model)
check("...and says so", warning and "not installed" in warning and "base.en" in warning, warning)
bad.unlink()
problems = transcribe.preflight()
check("with none at all, startup says what to do",
      any("halo model download" in p for p in problems), problems)

print("\n=== a truncated cleanup model ===")
spec = models.LLM_CATALOG[config.LOCAL_MODEL]
gguf = paths.MODELS_DIR / spec["file"]
gguf.write_bytes(b"GGUF" + b"\0" * 1000)          # the download stopped early
check("it is not 'installed'", models.llm_path(config.LOCAL_MODEL) is None)
entry = next(m for m in models.catalog_json()["cleanup"] if m["id"] == config.LOCAL_MODEL)
check("the Models pane calls it damaged", entry["damaged"] is True, entry)
server = local_llm.LlamaServer()
with quiet:
    server._launch()
check("llama-server is not started on it", server._proc is None if hasattr(server, "_proc")
      else True)
check("...and the status says why", server.status().state == "failed"
      and "damaged" in server.status().detail, server.status())
config.CLEANUP_PROVIDER = "auto"
model, why = local_llm.select("normal")
check("cleanup does not wait for it", model is None and why == "no local model installed", why)
r = pipeline.process("so um the the launch is on friday", mode="normal")
check("...the rules do the job instead", r.text == "So the launch is on Friday."
      and r.source == "rules", (r.text, r.source))
gguf.unlink()

print("\n=== languages ===")
check("'Spanish' is es", languages.from_spoken("Spanish") == "es")
check("'auto detect' is auto", languages.from_spoken("auto detect") == "auto")
check("an unknown language is None", languages.from_spoken("Klingon") is None)

h = halo.Halo(ui=overlay.NullOverlay())
with quiet:
    h.dispatch("switch to spanish")
on_disk = json.loads(paths.SETTINGS_FILE.read_text())
check("'switch to Spanish' changes the language", config.WHISPER_LANGUAGE == "es")
check("...persists it in settings.json", on_disk.get("language") == "es", on_disk)
check("...and puts it first in the recent list", languages.recent()[:1] == ["es"])
with quiet:
    h.dispatch("dictate in french")
check("recent languages keep their order", languages.recent()[:2] == ["fr", "es"],
      languages.recent())
check("a model that cannot do Spanish is flagged", transcribe.model_for("es")[1] is not None)

r = pipeline.process("la la reunión es el viernes, no, el jueves", mode="normal", language="es")
check("non-English turns off the English-only rules",
      not {"backtrack", "repeats", "days", "questions", "numbers"} & set(r.stages), r.stages)
hints = pipeline._hints(None, [], "normal", None, "es")
check("...and the model is told the language, not to translate",
      "Spanish" in hints and "Do not translate" in hints, hints)

config.LANGUAGE_REGIONS = {"en": "en-GB"}
check("en-GB writes the day first", pipeline.process(
    "the launch is on march third", mode="normal", language="en").text
      == "The launch is on 3 March.")
config.LANGUAGE_REGIONS = {}
check("en-US writes the month first", pipeline.process(
    "the launch is on march third", mode="normal", language="en").text
      == "The launch is on March 3.")
settings_mod.current.set("language", "en")
config.reload()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
