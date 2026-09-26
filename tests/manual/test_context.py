"""Context Awareness probe. Click into any text field within 5 seconds.

Prints what Halo would capture there: the app, its category, whether the
field counts as secure, and how much text was read around the cursor. The
text itself is only shown with --show, because this is exactly the kind of
output that ends up pasted into an issue.

Try it in a password field: it must say "secure" and read nothing.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import context
import formatting
import permissions

show = "--show" in sys.argv

print("Accessibility:", "GRANTED" if permissions.accessibility_ok() else "NOT GRANTED")
t0 = time.time()
context.warm_up()
print(f"PyObjC warm-up: {time.time() - t0:.2f}s (paid once, at engine start)")
print("\nClick into a text field NOW.")
for s in range(5, 0, -1):
    print(f"  reading in {s}...", flush=True)
    time.sleep(1)

t0 = time.time()
ctx = context.capture(context._backend())
took = time.time() - t0
print(f"\ncaptured in {took * 1000:.0f}ms")
print(f"  app       : {ctx.app_name} ({ctx.bundle_id})")
print(f"  category  : {ctx.category}" + (f"  host {ctx.host}" if ctx.host else ""))
print(f"  profile   : {formatting.profile_for(ctx)}")
print(f"  secure    : {ctx.secure}")
print(f"  summary   : {ctx.summary()}")
print(f"  repr      : {ctx!r}")
if show:
    print(f"  before    : {ctx.before!r}")
    print(f"  after     : {ctx.after!r}")
    print(f"  selected  : {ctx.selected!r}")
    print(f"  terms     : {ctx.terms}")
else:
    print("  (run with --show to print the text itself)")
ctx.clear()
