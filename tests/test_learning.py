"""Vocabulary learning: real fixes become suggestions; rewrites, content
changes and grammar edits never do; nothing is added without acceptance."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(TMP)
os.environ["HALO_DATA_DIR"] = str(TMP)
(TMP / "dictionary.json").write_text(json.dumps({"terms": [{"term": "GitHub", "variants": []}]}))

import dictionary  # noqa: E402
import insertion  # noqa: E402
import learning  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


F = learning.find_corrections

print("=== fixes that ARE vocabulary ===")
r = F("We moved the backend to Super Base last week.", "We moved the backend to Supabase last week.")
check("Super Base -> Supabase", [(h, c, k) for h, c, s, k in r] == [("Super Base", "Supabase", "spelling")], r)
check("...confidently", r and r[0][2] >= learning.THRESHOLD, r)
r = F("It runs on post grass.", "It runs on Postgres.")
check("post grass -> Postgres", r and r[0][1] == "Postgres", r)
r = F("Ask tarun about it.", "Ask Tharun about it.")
check("a name", r and r[0][:2] == ("tarun", "Tharun"), r)
r = F("Open the swift ui preview.", "Open the SwiftUI preview.")
check("swift ui -> SwiftUI", r and r[0][1] == "SwiftUI", r)
r = F("Push it to github today.", "Push it to GitHub today.")
check("a case-only fix is a capitalisation suggestion", r and r[0][3] == "case", r)
r = F("Ship the kubernetes change.", "Ship the Kubernetes change. Then lunch.")
check("words you added after it are not edits of it", r and r[0][1] == "Kubernetes", r)

print("\n=== edits that are NOT ===")
check("changing your mind (John -> Jake)", F("Send it to John.", "Send it to Jake.") == [])
check("grammar (there -> their)", F("I saw there car.", "I saw their car.") == [])
check("a rewrite", F("Can we meet on Friday to talk about the launch plan?",
                     "Let's skip Friday; I'll email the launch plan instead.") == [])
check("a big replacement", F("the old approach was fine really",
                             "the brand new streaming architecture was fine really") == [])
check("unchanged text", F("All good here.", "All good here.") == [])
check("nothing readable", F("text", None) == [])

print("\n=== suggestions: stored, strengthened, never auto-added ===")
d = dictionary.Dictionary(TMP / "dictionary.json")
seen = []
L = learning.Learner(TMP / "suggestions.json", d, notify=seen.append)
s = L.record("Super Base", "Supabase", 0.85, "spelling", "com.apple.Notes")
check("a confident fix becomes a pending suggestion", s is not None and s.status == "pending")
check("...and the dictionary is untouched", [t["term"] for t in d.terms] == ["GitHub"])
check("a known term is not suggested again", L.record("github", "GitHub", 0.9, "case") is None)
weak = L.record("fooo", "Foo", 0.62, "spelling")
check("a weak one is kept quietly", weak is None and any(x.correct == "Foo" for x in L.suggestions()))
again = L.record("fooo", "Foo", 0.62, "spelling")
check("seeing it again crosses the threshold", again is not None and again.count == 2)

L.accept("Super Base", "Supabase")
d.load()
entry = next(t for t in d.terms if t["term"] == "Supabase")
check("accept adds the term with what was heard as a variant", entry["variants"] == ["Super Base"])
check("...and marks it accepted", all(x.correct != "Supabase" for x in L.suggestions()))
check("an accepted fix is not suggested again", L.record("Super Base", "Supabase", 0.9, "spelling") is None)
L.set_status("fooo", "Foo", "dismissed")
check("a dismissed one stays dismissed", L.record("fooo", "Foo", 0.95, "spelling") is None)

print("\n=== watching a real insertion ===")


class AX:
    def __init__(self, value):
        self.value = value

    def string_for_range(self, elem, loc, length):
        return self.value[loc:loc + length]

    def attr(self, elem, name):
        return None


L2 = learning.Learner(TMP / "s2.json", d, notify=seen.append)
rec = insertion.Record("Deploy to cloud flare now.", "ax", 1, "com.apple.Notes", "el", "w",
                       (6, 26), at=time.time() - 11)
L2.watch(rec)
fresh = L2.check_due(AX("Todo: Deploy to Cloudflare now. More."))
check("10s later the fix is noticed", [s.correct for s in fresh] == ["Cloudflare"], fresh)
secure = insertion.Record("secret", "paste", 1, "x", "el", "w", (0, 6), secure=True)
L2.watch(secure)
check("a secure field is never watched", secure not in L2._pending)
norange = insertion.Record("abc", "paste", 1, "x", "el", "w", None)
L2.watch(norange)
check("no known range, nothing to re-read", norange not in L2._pending)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
