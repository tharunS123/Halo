"""Dictation history: off by default, retention enforced, audio separate,
secure fields never kept, files private."""
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = str(TMP)

import config  # noqa: E402
import history  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


h = history.History(TMP / "h.sqlite3", TMP / "audio")
wav = TMP / "clip.wav"
wav.write_bytes(b"RIFF....fake")


def add(**kw):
    base = dict(raw="send it to john no jake", cleaned="Send it to Jake.", mode="normal",
                status="inserted", duration=2.1, app_name="Slack",
                bundle_id="com.tinyspeck.slackmacgap", language="en", wav=str(wav))
    base.update(kw)
    return h.add(**base)


print("=== off by default ===")
check("the default setting is off", config.HISTORY_ENABLED is False)
check("nothing is kept while off", add() is None and not (TMP / "h.sqlite3").exists())

config.HISTORY_ENABLED = True
config.HISTORY_RETENTION = "7d"
print("\n=== on ===")
i1 = add()
check("an item is kept", i1 is not None)
item = h.get(i1)
check("with every field", item.raw == "send it to john no jake" and item.cleaned == "Send it to Jake."
      and item.app_name == "Slack" and item.status == "inserted" and item.language == "en")
check("the database is private (0600)",
      stat.S_IMODE((TMP / "h.sqlite3").stat().st_mode) == 0o600)
check("audio is NOT kept unless separately enabled", item.audio is None and not (TMP / "audio").exists())
check("repr never shows the words", "jake" not in repr(item).lower())

check("a secure field is never kept", add(secure=True) is None)

config.HISTORY_KEEP_AUDIO = True
config.HISTORY_AUDIO_RETENTION = "24h"
i2 = add(raw="with audio")
a = h.get(i2).audio
check("audio kept when enabled", a is not None and Path(a).exists())
check("...privately", a and stat.S_IMODE(Path(a).stat().st_mode) == 0o600)

print("\n=== search, update, delete ===")
add(raw="quarterly numbers", cleaned="Quarterly numbers.", app_name="Mail")
check("search finds by text", [x.raw for x in h.search("quarterly")] == ["quarterly numbers"])
check("search finds by app", len(h.search("Mail")) == 1)
check("newest first", h.search()[0].raw == "quarterly numbers")
h.update(i1, cleaned="Send it to Jake!", status="retried")
check("update", h.get(i1).cleaned == "Send it to Jake!" and h.get(i1).status == "retried")
h.delete(i2)
check("delete removes the row and its audio", h.get(i2) is None and not Path(a).exists())

print("\n=== retention ===")
now = time.time()
old = add(raw="old one")
import sqlite3  # noqa: E402
conn = sqlite3.connect(TMP / "h.sqlite3")
conn.execute("UPDATE dictations SET created=? WHERE id=?", (now - 8 * 86400, old))
conn.commit()
conn.close()
removed = h.prune(now)
check("older than 7 days is pruned", h.get(old) is None and removed >= 1)
i3 = add(raw="audio ages first")
conn = sqlite3.connect(TMP / "h.sqlite3")
conn.execute("UPDATE dictations SET created=? WHERE id=?", (now - 2 * 86400, i3))
conn.commit()
conn.close()
a3 = h.get(i3).audio
h.prune(now)
check("audio past its own retention goes, the text stays",
      h.get(i3) is not None and h.get(i3).audio is None and not Path(a3).exists())

config.HISTORY_RETENTION = "forever"
i4 = add(raw="kept forever")
conn = sqlite3.connect(TMP / "h.sqlite3")
conn.execute("UPDATE dictations SET created=0 WHERE id=?", (i4,))
conn.commit()
conn.close()
h.prune(now)
check("forever keeps it", h.get(i4) is not None)

print("\n=== turning it off deletes it ===")
config.HISTORY_ENABLED = False
h.prune(now)
check("off means nothing stays on disk", not (TMP / "h.sqlite3").exists() and not (TMP / "audio").exists())
config.HISTORY_ENABLED = True
config.HISTORY_RETENTION = "never"
check("'never' keeps nothing", add() is None)
config.HISTORY_RETENTION = "7d"
add()
h.clear()
check("clear() removes everything", not (TMP / "h.sqlite3").exists() and h.search() == [])

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
