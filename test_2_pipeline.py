"""STEP 2+3 TEST: WAV -> whisper.cpp -> cleanup, no mic and no injection.
Usage: python test_2_pipeline.py [path/to.wav]"""
import os, sys, time
import cleanup, transcribe

wav = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/whisper.cpp/samples/jfk.wav")
print(f"input: {wav}\n")

p = transcribe.preflight()
print("preflight:", p or "OK")
if p: sys.exit(1)

t0 = time.time()
raw = transcribe.transcribe(wav)
print(f"\n[transcribe] {time.time()-t0:.2f}s")
print(f"  RAW: {raw!r}")

t1 = time.time()
r = cleanup.clean(raw)
print(f"\n[cleanup] {time.time()-t1:.2f}s  source={r.source}  detail={r.detail}")
print(f"  OUT: {r.text!r}")
print("\nKEY SET:", bool(os.environ.get("OPENROUTER_API_KEY")))
