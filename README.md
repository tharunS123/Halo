# WisprFlowClone

Local push-to-talk dictation for macOS. Audio and transcription stay on your
machine; only the raw transcript text leaves, for one LLM cleanup call.

```
mic -> whisper.cpp (local, Metal) -> OpenRouter cleanup -> Cmd+V into focused app
```

## Status

| Piece | State |
|---|---|
| whisper.cpp | Built at `~/whisper.cpp`, Metal enabled, `small.en` (465MB) |
| Transcription | Verified: 11s clip in **0.73s** (~15x realtime) |
| Cleanup + dedup | Live-tested. Median **0.88s**, max 3.7s, 8/8 cleaned |
| Permissions | Checker implemented, detects the real responsible app |
| Mic capture | Verified: 4.01s captured, peak 0.072 |
| Hotkey (F9) | Verified as `Key.f9`; needs Accessibility to go global |
| Injection | Verified working |

## Setup

### 1. API key

```bash
export OPENROUTER_API_KEY='sk-or-...'
```

Put it in `~/.zshrc` to persist. Without it the app still runs and injects the
**raw** transcript, printing a warning.

### 2. Grant Accessibility

**Accessibility is the one permission that matters.** pynput's global key
listener calls `AXIsProcessTrusted()` before creating its event tap
(`pynput/_util/darwin.py:216`), so without it you get *both* failures at once:

- the hotkey only fires while your terminal is focused
- Cmd+V is silently swallowed — no error, no text

Input Monitoring is worth granting too if macOS offers it, but it is **not**
what gates pynput. Do not stop at Input Monitoring and assume you are done.

**Which app do I grant?** Not `python`. macOS attributes this to the app that
owns your terminal session. Run this to be told exactly which:

```bash
cd ~/WisprFlowClone && ./.venv/bin/python -c "import permissions; permissions.report(require=False)"
```

Then `System Settings > Privacy & Security > Accessibility` → enable that app.
If it isn't listed, click `+`, press `Cmd+Shift+G`, and paste the printed path.

> **Then fully quit that app with Cmd+Q and reopen it.** Closing the window is
> not enough — macOS only re-reads this grant when the process restarts. This
> is the single most common reason this setup "doesn't work".

Microphone access prompts normally on first run; just click Allow.

## Test in order

```bash
cd ~/WisprFlowClone

./.venv/bin/python test_1_audio.py       # 1. mic capture
./.venv/bin/python test_2_pipeline.py    # 2. transcribe + cleanup (no mic)
./.venv/bin/python test_3_dedup.py       # 3. echo dedup, offline
./.venv/bin/python hotkey_probe.py       # 4. what your F-keys actually emit
./.venv/bin/python test_4_inject.py      # 5. injection into another app
./.venv/bin/python flow.py               # 6. the real thing
```

## Hotkey notes

**F9 is confirmed working** on the built-in MacBook Pro keyboard — the probe
sees it as `Key.f9` with no media-key interception, so the "use F1–F12 as
standard function keys" setting is not a problem here.

**F13 does not exist on a MacBook Pro's built-in keyboard.** The function row
is Esc + F1–F12 only. F13–F19 exist only on full-size external keyboards, so
`FLOW_HOTKEY=f13` is only an option if you plug one in. Any F-key works:

```bash
FLOW_HOTKEY=f12 ./.venv/bin/python flow.py
```

One cosmetic note: while the terminal itself is focused, pressing F9 also emits
its escape sequence (`^[[20~`) into the shell. Harmless, and it does not happen
when another app has focus — which is the only case that matters.

## Background mode (no terminal)

Once installed, F9 works from login with no terminal open. F9 is the entire
control surface -- there is no menu bar icon by design.

### Setup, in order

```bash
# 1. Build the app bundle
overlay/build_app.sh

# 2. Store the API key where launchd can reach it.
#    launchd never sources ~/.zshrc, so the env var alone is not enough.
security add-generic-password -s wisprflowclone -a "$USER" \
    -w 'sk-or-v1-...' -T /usr/bin/security -U

# 3. Install and start the login agent
./flowctl install
```

Then grant these to **WisprFlow** -- not your terminal, not `python`:

- `System Settings > Privacy & Security > Accessibility` -> WisprFlow
- `System Settings > Privacy & Security > Input Monitoring` -> WisprFlow
- **Microphone** -- granted by a prompt the app raises on first launch.

**The Microphone pane has no "+" button**, so an app cannot be added by hand:
it appears only once it has *asked*. `WisprFlow.app` therefore calls
`AVCaptureDevice.requestAccess` at startup, and its Info.plist carries
`NSMicrophoneUsageDescription` (without that key macOS denies the mic outright).
The engine records as our child, so this one grant covers it.

Symptom if the mic grant is missing: recording "succeeds" with the right
duration but **`peak 0.000`** -- macOS hands out a stream of zeros rather than
an error, so it looks exactly like a silent room.

App path: `overlay/WisprFlow.app`. Finish with `./flowctl restart`.

Once this works you can **revoke Accessibility from Cursor/Terminal** -- the
grant now belongs to a small purpose-built app instead of an editor that can
already run arbitrary code.

### Why the app supervises Python, not the other way round

In background mode `WisprFlow.app` is what launchd starts, and it spawns
`flow.py` as a child. That inversion is deliberate: a process inherits its
nearest `.app` ancestor as the TCC *responsible process* -- the same mechanism
that made Python inherit `Cursor.app` when run from Cursor's terminal. With the
app as parent, the engine's key tap and synthetic Cmd+V are attributed to
`WisprFlow.app`, so permissions are granted once to one stable identity.

Terminal mode is unchanged: `python flow.py` still spawns the overlay itself.
The app only supervises when `FLOW_SUPERVISE=1`, which only the LaunchAgent sets.

### Managing it

```bash
./flowctl status      # launchd state, processes, permissions, api key
./flowctl stop        # disable without uninstalling
./flowctl restart
./flowctl logs        # tail engine.log + overlay.log
./flowctl uninstall   # remove the login agent entirely
```

Logs: `~/Library/Logs/WisprFlowClone/{engine,overlay}.log`

### How failures surface without a terminal

- Missing permission or key at startup -> **error pill** appears, then the
  engine exits `78` and is deliberately *not* restarted (restarting cannot fix
  a permission).
- Engine crash -> supervisor restarts with backoff (1s, 2s, 4s ... capped at
  30s), giving up after 6 tries with an error pill.
- launchd `SIGTERM` -> handled explicitly, so the engine is never orphaned.

The honest limit: if the engine is dead, F9 does nothing and says nothing.
The login-time error pill and the log are the only signals. That is the cost of
having no menu bar item.

## Floating overlay

A separate SwiftUI agent app (`overlay/`) draws the pill. Build it once:

```bash
overlay/build_app.sh
```

In terminal mode `flow.py` launches it automatically and shuts it down on exit. Drive it by
hand for debugging:

```bash
overlay/demo.sh                                    # visual tour of all states
printf 'listening\n' | nc -U ~/.wisprflowclone-overlay.sock
printf 'status\n'    | nc -U ~/.wisprflowclone-overlay.sock
```

Disable it entirely with `FLOW_OVERLAY=0 ./.venv/bin/python flow.py`.

**Why Swift and not PyQt/pywebview.** Not mainly for animation quality. On
macOS both a GUI event loop and pynput's listener want the main thread, so the
overlay needs its own process *whatever* toolkit draws it -- the IPC cost is
unavoidable and therefore not a point against Swift. Given that, Swift also
buys real `NSVisualEffectView` vibrancy (no Qt equivalent) and, critically,
`NSPanel(.nonactivatingPanel)` with `canBecomeKey = false`, which is the only
way to guarantee the overlay can never take keyboard focus from the app you
are dictating into.

**Design invariants** (do not break these):

- The overlay never opens the microphone. Python already has the audio buffer,
  computes RMS there, and streams levels. A second tap would mean a second TCC
  prompt and two sources of truth.
- Levels are shipped by a dedicated 30fps pump thread, never from the
  `sounddevice` callback -- a socket write on the audio thread risks dropouts.
- Every `Overlay` method swallows its errors. Missing socket, dead app, wedged
  reader: all degrade to no-ops. Measured at 0.000s for a missing socket.
- The panel sets `ignoresMouseEvents = true`, so it can never intercept a click
  meant for the app underneath.
- A 90s watchdog in the Swift app hides the pill if commands stop arriving, so
  a Python crash cannot strand a pill on screen.

## Files

| File | Purpose |
|---|---|
| `config.py` | Paths, model, hotkey, prompt, OpenRouter model chain |
| `audio.py` | `sounddevice` capture → 16kHz mono 16-bit WAV |
| `transcribe.py` | `whisper-cli` subprocess wrapper + preflight |
| `cleanup.py` | OpenRouter call, echo dedup, bad-output rejection, fallbacks |
| `inject.py` | Clipboard + Cmd+V, hard-fails if Accessibility missing |
| `permissions.py` | TCC checks, responsible-app detection |
| `flow.py` | Main push-to-talk app |
| `overlay.py` | Socket client for the overlay; no-ops if unavailable |
| `overlay/` | SwiftUI app: overlay + engine supervisor (`WisprFlow.app`) |
| `flowctl` | install/start/stop/status/logs for background mode |
| `launchd/` | LaunchAgent plist template |

## Failure behaviour

Everything degrades to *something usable* rather than failing silently:

- No API key / rate limited / timeout / model adds commentary → injects the **raw transcript**
- Response truncated (`finish_reason=length`) → rejected, raw injected (a truncated
  clean-up silently drops the end of your sentence, which is worse than no cleanup)
- Cleanup exceeds `OPENROUTER_TOTAL_BUDGET` (8s wall clock) → raw injected
- Accessibility missing → loud error **and text left on your clipboard**
- Clip under 0.3s or silent → skipped with a message
- Model echoes its own output → deduplicated before injection

## Hard-won configuration notes

Three settings here are non-obvious and were each found by measurement. Do not
change them without re-testing.

**1. `"reasoning": {"enabled": False}` is mandatory.** Every free nemotron model
is a reasoning model. Left on, chain-of-thought consumes the `max_tokens`
budget and the actual answer gets truncated mid-sentence, *and* calls take
50–80s. Measured on the same input:

| | reasoning ON | reasoning OFF |
|---|---|---|
| latency | 52–78s | 0.7–3.7s |
| result | 3/5 rejected as commentary, 1/5 truncated | 5/5 clean |

**2. The system prompt must be specific about punctuation.** A prompt that
stresses "preserve the speaker's wording" makes the model *only* strip fillers
and never capitalize or punctuate. A prompt that just says "fix punctuation"
makes it **answer questions** — one test transcript asking about rate limiting
came back as a 200-word essay. The current prompt numbers the three permitted
edits explicitly, which fixed both.

**3. `requests`' `timeout=` is not a wall clock.** It is a between-bytes read
timeout, so a trickling response can run for minutes past it — one measured
call took 45s under a nominal 10s timeout. `cleanup._post_bounded()` therefore
runs the request on a worker thread and abandons it at the budget. Verified: a
0.6s budget returns in 0.60s.

## OpenRouter account requirements

Free models are blocked by default on accounts with Zero Data Retention.
At <https://openrouter.ai/settings/privacy> you need:

- **Zero Data Retention → "Non-frontier"**: OFF. While on, all non-frontier
  requests require ZDR endpoints, and no free endpoint offers ZDR, so every
  free model 404s with `ZDR violation (account settings)`.
- **Data Training → "Allow free endpoints that train on request data"**: ON.

Both are required; either one alone still fails. The consequence is real:
your transcripts go to a provider that may retain and train on them. Audio
never leaves the machine, but the text does.

## Notes

- Core ML was skipped deliberately. Metal already gives ~15x realtime on the
  M1 Pro, so the PyTorch/coremltools install (and its SSL-cert pitfalls on
  python.org Python) buys nothing here.
- Your clipboard is saved and restored around each injection.
