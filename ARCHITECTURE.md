# Architecture

Why Halo is built the way it is. Most of this exists because macOS, whisper,
or a free LLM endpoint behaved differently than expected, and the workaround
is not obvious from the code alone.

```
mic -> whisper.cpp (local, Metal) -> OpenRouter cleanup (optional) -> Cmd+V into the focused app
```

Two processes:

- **`Halo.app`** (Swift, `overlay/`) draws the floating orb and, in background
  mode, spawns and supervises the engine.
- **The engine** (Python, `*.py`) owns the hotkey, the microphone, whisper,
  the text pipeline, and injection.

They talk over a Unix socket at `~/.halo-overlay.sock`.

## Why the app supervises Python, not the other way round

In background mode `Halo.app` is what launchd starts, and it spawns `halo.py`
as a child. That inversion is deliberate: a process inherits its nearest
`.app` ancestor as the TCC *responsible process* — the same mechanism that
made Python inherit `Cursor.app` when run from Cursor's terminal. With the app
as parent, the engine's key tap and synthetic Cmd+V are attributed to
`Halo.app`, so permissions are granted once to one stable identity.

Terminal mode is unchanged: `python halo.py` still spawns the overlay itself.
The app only supervises when `HALO_SUPERVISE=1`, which only the LaunchAgent
sets.

The practical payoff: you can revoke Accessibility from your editor and
terminal. The grant belongs to a small purpose-built app instead of something
that can already run arbitrary code.

## Why Homebrew builds from source, and why there is no DMG

Halo is signed ad-hoc — there is no paid Apple Developer ID. That decision
drives the entire distribution design:

- A **downloaded archive** gets the `com.apple.quarantine` attribute. An
  ad-hoc-signed app under quarantine does not produce the familiar "unidentified
  developer" prompt; it produces **"Halo is damaged and can't be opened"**,
  which is strictly worse. So: no release zip, no DMG, and never a prebuilt
  `.app` attached to a GitHub release.
- A **Homebrew formula that builds locally** produces no quarantine attribute
  at all, so there is no Gatekeeper dialog anywhere in the install.

The cost of ad-hoc signing is that the code identity *is* the binary hash
(`codesign -d -r-` shows `cdhash H"..."`), so any rebuild looks like a new app
and macOS voids its TCC grants. Halo mitigates that rather than hiding it:

- The installed bundle lives at `~/Applications/Halo.app`, not in the Cellar,
  because Cellar paths are versioned and would change on every upgrade.
- `halo setup` replaces that bundle **only when its cdhash differs**, so
  reinstalling the same version keeps your permissions. Upgrading to a new
  version does not: CFBundleVersion lives in Info.plist, inside the bundle, so
  a version bump is a bundle change however little else moved. A stable
  self-signed identity is the only thing that would fix that, because TCC
  would key on the certificate rather than the code hash.
- `halo doctor` compares the installed hash against the built one and against
  the hash recorded when permissions were granted, so a voided grant is a
  diagnosis instead of a mystery.

The real fix is a stable signing identity (a self-signed certificate makes TCC
key on the certificate rather than the hash); `overlay/build_app.sh` documents
how to create one and `HALO_SIGN_IDENTITY` uses it.

## Where things live

| Location | Owner | Contents |
|---|---|---|
| `$(brew --prefix)/opt/halo/libexec/` | Homebrew | engine, venv, `Halo.app`, default configs, plist template |
| `~/Applications/Halo.app` | `halo setup` | the TCC identity |
| `~/.config/halo/` | you | settings and vocabulary, seeded once, never overwritten |
| `~/Library/Application Support/Halo/` | Halo | models, state, engine pointer |
| `~/Library/Logs/Halo/` | Halo | `engine.log`, `overlay.log` |

`paths.py` owns all of it, with an environment override for each so tests can
relocate everything. The engine is found through, in order: `HALO_PYTHON` +
`HALO_ENGINE` from the LaunchAgent, the `engine.json` pointer file, the
Homebrew opt path, then a source checkout — see `EngineSupervisor.locate()`.

## Settings vs vocabulary

`settings.json` is read **once at startup**, because every value in it is
bound then: pynput binds the hotkey, transcribe picks the model, the overlay
client reads its enabled flag. Making it live would mean tearing down the key
listener mid-utterance. `halo config set` writes the file and offers a restart.

`dictionary.json`, `snippets.json` and `commands.json` **hot-reload** on mtime
while Halo runs, which is what makes tuning your vocabulary bearable.

Environment variables still override both, which is how a one-off
`HALO_LANGUAGE=es halo ...` works. Note that launchd sources no shell profile,
so env vars do not reach a background install — that is precisely why
`settings.json` exists.

## The pipeline

After transcription, each utterance passes through ordered stages. The order
is deliberate, and each stage can short-circuit:

```
whisper transcript
  1. dictionary   fix vocabulary first, so every stage below matches clean text
  2. commands     BEFORE cleanup -- cleanup would rewrite "scratch that" as prose
  3. snippets     whole-utterance triggers; fully local, never hits the network
  4. dictation    OpenRouter cleanup, or skipped entirely in Privacy Mode
  -> inject
```

To add a stage, edit `Halo.dispatch()` in `halo.py`. To add a command, add a
phrase to `commands.json` and a branch in `Halo.run_command()`.

Command detection is **whole-utterance only** (≤6 words, fuzzy threshold
0.87), so "I had to scratch that idea" dictates normally. The tradeoff is that
mid-sentence self-correction is not supported: "wait, scratch that" inside a
longer sentence is treated as dictation.

The dictionary's fuzzy pass needs three vetoes to avoid corrupting ordinary
speech, each found by testing: the system wordlist (`launch` must not become
`launchd`), de-inflection (that list holds base forms, so `launched` needs
stemming), and all-words-English (`a sync` must not become `async`). ~0.5ms
per transcript. Deliberate tradeoff: `jason` is left alone, because it is both
a common name and a plausible mis-hearing of `JSON`. Protecting the name wins.

Undo only fires when Halo has something of its own to undo (`last_injected`).
Sending Cmd+Z into an app Halo has not typed into would eat the user's work.

## The overlay

A separate SwiftUI agent app draws the pill.

**The orb.** Speaking is the `composing` animation from
[Orb](https://libraries.dev/orbs.html) (Libraries.dev, MIT), played by your
voice. While you speak, the mic level drives how deeply the ribbon undulates
(`wobMul`) and how fast its waves travel, so it ripples harder the louder you
talk — and a calm band while you are talking is the visible sign the mic hears
nothing. When you stop, the ribbon dissolves into the `breathing` ring, which
carries on through processing and the finish. Voice tuning lives in
`OrbDriver` (`VoiceOrb.swift`), glass tuning in `Style.Glass`
(`OverlayView.swift`).

The orb engine is the library's own SwiftUI port, vendored in
`overlay/Sources/ThinkingOrbsKit` — plain `Canvas` math, no Metal, no
dependencies, so the Command Line Tools still build it. Upstream files are
unmodified; `HaloOverrides.swift` is our one addition. See `VENDORED.md`.

**Why Swift and not PyQt/pywebview.** Not mainly for animation quality. On
macOS both a GUI event loop and pynput's listener want the main thread, so the
overlay needs its own process *whatever* toolkit draws it — the IPC cost is
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
  `sounddevice` callback — a socket write on the audio thread risks dropouts.
- Every `Overlay` method swallows its errors. Missing socket, dead app, wedged
  reader: all degrade to no-ops. Measured at 0.000s for a missing socket.
- The panel sets `ignoresMouseEvents = true`, so it can never intercept a click
  meant for the app underneath.
- A 90s watchdog in the Swift app hides the pill if commands stop arriving, so
  a Python crash cannot strand a pill on screen.

## Failure behaviour

Everything degrades to *something usable* rather than failing silently:

- No API key / rate limited / timeout / model adds commentary → injects the **raw transcript**
- Response truncated (`finish_reason=length`) → rejected, raw injected (a truncated
  clean-up silently drops the end of your sentence, which is worse than no cleanup)
- Cleanup exceeds its budget (8s wall clock) → raw injected
- Accessibility missing → loud error **and text left on your clipboard**
- Clip under 0.3s or silent → skipped with a message
- Model echoes its own output → deduplicated before injection

Missing permission or key at startup → **error pill**, then the engine exits
`78` and is deliberately *not* restarted (restarting cannot fix a permission).
Engine crash → supervisor restarts with backoff (1s, 2s, 4s … capped at 30s),
giving up after 6 tries. launchd `SIGTERM` → handled explicitly, so the engine
is never orphaned.

The honest limit: if the engine is dead, F9 does nothing and says nothing.
The login-time error pill, `halo status` and the log are the only signals.
That is the cost of having no menu bar item.

## Hard-won configuration notes

Three settings are non-obvious and were each found by measurement. Do not
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

## Whisper notes

**Two models, chosen per language.** `ggml-small.en.bin` is measurably better at
English than the multilingual model, because capacity is not shared across 99
languages — it produces "And so, my fellow Americans," where the multilingual
model drops the comma. So English uses the `.en` model and anything else uses
`ggml-small.bin`. An `.en` model silently ignores the language flag, so routing
matters.

Auto-detect is imperfect on short clips: a 6s Spanish sample was labelled `en`
at p=0.76 while French scored `fr` at p=0.99. The engine logs a warning below
p=0.70 — set the language explicitly if you dictate mostly in one language.

Core ML was skipped deliberately. Metal already gives ~15x realtime on the
M1 Pro, so the PyTorch/coremltools install (and its SSL-cert pitfalls on
python.org Python) buys nothing here.

Homebrew's `whisper.cpp` bottle keeps Metal enabled on Apple Silicon, and
benchmarks within ~10% of a local `-DGGML_METAL=ON` build (0.65–0.72s vs
0.59–0.60s for an 11s clip on an M1 Pro), which is why the formula depends on
it rather than compiling whisper itself. The first run of any new model spends
~25s compiling Metal shaders; `halo setup` absorbs that in its smoke test so
the user's first real dictation is fast.

## OpenRouter account requirements

Free models are blocked by default on accounts with Zero Data Retention.
At <https://openrouter.ai/settings/privacy> you need:

- **Zero Data Retention → "Non-frontier"**: OFF. While on, all non-frontier
  requests require ZDR endpoints, and no free endpoint offers ZDR, so every
  free model 404s with `ZDR violation (account settings)`.
- **Data Training → "Allow free endpoints that train on request data"**: ON.

Both are required; either one alone still fails. The consequence is real:
your transcripts go to a provider that may retain and train on them. Audio
never leaves the machine, but the text does. This is why the key is optional
and why `halo setup` spells the tradeoff out before asking.

## Files

| File | Purpose |
|---|---|
| `cli.py` | The `halo` command: setup, doctor, config, model, key, uninstall |
| `paths.py` | Every filesystem location, with env overrides and seeding |
| `settings.py` | `settings.json` plus the env-override table |
| `config.py` | Resolved configuration; `reload()` re-derives it after a change |
| `models.py` | Model catalog, resumable download, checksum verification |
| `audio.py` | `sounddevice` capture → 16kHz mono 16-bit WAV |
| `transcribe.py` | `whisper-cli` subprocess wrapper + preflight |
| `cleanup.py` | OpenRouter call, echo dedup, bad-output rejection, fallbacks |
| `inject.py` | Clipboard + Cmd+V, hard-fails if Accessibility missing |
| `permissions.py` | TCC checks, responsible-app detection |
| `halo.py` | The engine: hotkey, pipeline, dispatch |
| `overlay.py` | Socket client for the overlay; no-ops if unavailable |
| `overlay/` | SwiftUI app: overlay + engine supervisor (`Halo.app`) |
| `overlay/Sources/ThinkingOrbsKit/` | Vendored Orb animation from Libraries.dev (MIT) |
| `defaults/` | Seed copies of settings and vocabulary |
| `packaging/homebrew/halo.rb` | The formula, mirrored into the tap at release |
