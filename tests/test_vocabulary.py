"""The dictionary as a product: scopes, pronunciation hints, capitalisation,
import/export; plus the language registry and the engine's control socket."""
import json
import os
import stat
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(TMP)
os.environ["HALO_DATA_DIR"] = str(TMP)

import config  # noqa: E402
import control  # noqa: E402
import dictionary  # noqa: E402
import languages  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


path = TMP / "dictionary.json"
path.write_text(json.dumps({"fuzzy": {"enabled": False}, "terms": [
    {"term": "Supabase", "variants": ["super base"], "type": "company"},
    {"term": "Postgres", "variants": [], "hint": "post-grass"},
    {"term": "Jonno", "variants": ["jono"], "type": "name", "apps": ["com.tinyspeck.slackmacgap"]},
    {"term": "tortilla", "variants": ["tortiya"], "languages": ["es"]},
    {"term": "iOS", "variants": [], "match_case": False},
    {"term": "GitHub", "variants": []},
]}))
d = dictionary.Dictionary(path)
A = lambda text, app=None, lang=None: d.apply(text, app, lang)[0]  # noqa: E731

print("=== spoken form -> written form ===")
check("a variant", A("we use super base"), "we use Supabase")
check("a pronunciation hint works like a variant", A("it runs on post grass"), "it runs on Postgres")
check("preferred capitalisation", A("push to github"), "push to GitHub")
check("...unless switched off for that entry", A("the ios app"), "the ios app")

print("\n=== scope ===")
check("an app-scoped entry applies in that app", A("ask jono", "com.tinyspeck.slackmacgap"), "ask Jonno")
check("...and nowhere else", A("ask jono", "com.apple.mail"), "ask jono")
check("...not even when the app is unknown", A("ask jono"), "ask jono")
check("a language-scoped entry in its language", A("una tortiya", None, "es"), "una tortilla")
check("...not in English", A("una tortiya", None, "en"), "una tortiya")
check("regional codes match their language", A("una tortiya", None, "es-MX"), "una tortilla")
check("scoped terms list", d.terms_list("com.apple.mail", "en"), ["Supabase", "Postgres", "iOS", "GitHub"])

print("\n=== import / export ===")
csv_text = d.export("csv")
check("CSV has a header", csv_text.splitlines()[0], "term,variants,type,hint,apps,languages,match_case")
round_trip = dictionary.Dictionary.parse_import(csv_text)
check("CSV round-trips every entry", [e["term"] for e in round_trip],
      ["Supabase", "Postgres", "Jonno", "tortilla", "iOS", "GitHub"])
check("...with its fields", round_trip[2].get("apps"), ["com.tinyspeck.slackmacgap"])
check("...and match_case", round_trip[4].get("match_case"), False)
added, updated = d.merge([{"term": "Supabase", "variants": ["soup a base"]},
                          {"term": "Cloudflare", "variants": ["cloud flare"]}])
check("merge adds new and updates existing", (added, updated), (1, 1))
d.load()
check("variants are unioned, never replaced",
      next(t for t in d.terms if t["term"] == "Supabase")["variants"], ["super base", "soup a base"])
check("unknown top-level keys survive a merge", json.loads(path.read_text())["fuzzy"], {"enabled": False})
check("a JSON list imports", [e["term"] for e in dictionary.Dictionary.parse_import(
    '[{"term": "Halo"}, {"nope": 1}]')], ["Halo"])

print("\n=== languages ===")
check("names", languages.name("es"), "Spanish")
check("English rules for en-GB", languages.english_rules("en-GB"), True)
check("...not Spanish", languages.english_rules("es"), False)
check("spoken names", languages.from_spoken("Spanish"), "es")
check("auto", languages.from_spoken("auto detect"), "auto")
check("unknown", languages.from_spoken("klingon"), None)
config.LANGUAGE_REGIONS = {"en": "en-GB"}
check("a regional variant", languages.region("en"), "en-GB")
check("...means day-first dates", languages.day_first("en"), True)
config.LANGUAGE_REGIONS = {"en": "xx-YY"}
check("an unknown variant is ignored", languages.region("en"), "")
languages.remember("es")
languages.remember("fr")
languages.remember("es")
check("recent languages, newest first, no repeats", languages.recent(), ["es", "fr"])

print("\n=== the control socket ===")
sock = TMP / "e.sock"
srv = control.ControlServer({"health": lambda req: {"state": "idle"},
                             "boom": lambda req: 1 / 0}, path=sock)
check("starts", srv.start(), True)
check("is private (0600)", stat.S_IMODE(os.stat(sock).st_mode), 0o600)
check("answers", control.request({"op": "health"}, sock), {"ok": True, "state": "idle"})
check("an unknown op is an error, not a crash", control.request({"op": "rm -rf"}, sock)["ok"], False)
check("a failing handler is contained", control.request({"op": "boom"}, sock),
      {"ok": False, "error": "ZeroDivisionError"})
results = []
threads = [threading.Thread(target=lambda: results.append(control.request({"op": "health"}, sock)))
           for _ in range(5)]
[t.start() for t in threads]
[t.join() for t in threads]
check("several clients at once", len(results), 5)
srv.stop()
check("stop removes the socket", sock.exists(), False)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
