# Architecture

Why Halo is built the way it is. Most of this exists because macOS, whisper,
or a free LLM endpoint behaved differently than expected, and the workaround
is not obvious from the code alone.

```
mic -> whisper.cpp (local, Metal) -> cleanup: rules, then a model on this Mac or OpenRouter (optional) -> Cmd+V into the focused app
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
  reinstalling the same version keeps your permissions even under ad-hoc.
- **A self-signed certificate removes the problem entirely**, and `halo setup`
  offers one. Signed with a certificate the designated requirement stops
  mentioning the hash at all:

  ```
  ad-hoc       designated => cdhash H"d8cc7900..."
  certificate  designated => identifier "io.github.tharuns123.halo"
                             and certificate leaf = H"34d3a474..."
  ```

  Measured end to end: two builds differing only in CFBundleVersion (cdhash
  `d692b8a0` and `516876f7`) were signed with one certificate, the second
  installed over the first, and Accessibility, Input Monitoring and Microphone
  all remained granted across the restart with no re-grant.

  Three things make this practical. `codesign` accepts an untrusted
  certificate — `security find-identity` reports `CSSMERR_TP_NOT_TRUSTED` and
  signing succeeds — so there is no admin password and no trust-settings
  change. The system LibreSSL at `/usr/bin/openssl` can generate it, so no new
  dependency. And Gatekeeper refusing such a signature does not matter here,
  because a locally built app is never quarantined, which is the same reason
  this project does not ship a downloadable build. The private key lives in its
  own keychain so `halo uninstall` can delete it outright.
- Ad-hoc remains the fallback, and it is honest about the cost: because
  CFBundleVersion lives in Info.plist, inside the bundle, *every* version bump
  is a bundle change however little else moved, so every upgrade needs a
  re-grant.
- `halo doctor` and `halo setup` compare the **designated requirement**, not
  the code hash, so they stay correct under both signing modes — and do not
  send you to re-grant something that never lapsed.

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

## Settings are files, and everything reloads

`settings.json` used to be read **once at startup**, because pynput binds the
hotkey then and tearing the key listener down mid-utterance would drop a
keypress. The Settings window made that untenable: nobody expects to restart
an app after moving a slider.

It now reloads on mtime like everything else, with one guard. The watcher
(`Halo._watch_settings`) refuses to reload while a recording is in flight —
busy, key held, or toggled on — and only rebinds the hotkey when idle. Every
*other* setting is read from `config` per utterance, so activation style, the
polish toggles, the whisper knobs and the cleanup budgets take effect on the
next thing you say with no rebinding at all.

`dictionary.json`, `snippets.json` and `commands.json` hot-reload the same
way, as they always have. So does `state.json`, which is what lets the menu
bar item and the voice command agree about Privacy Mode: the overlay is a
separate process and cannot reach into the engine, so it writes the file the
engine re-reads.

**Why the Settings window edits files instead of using the socket.** Those
JSON files were already the contract between the engine, `halo config` and a
text editor. A socket command would have made the window a fourth writer with
its own idea of the truth, and the first disagreement would have been a
setting that reverted for no visible reason. `SettingsStore` therefore merges
into the loaded tree rather than re-encoding a struct — it must not delete the
`_comment` strings or the `cleanup.models` fallback chain it does not show —
and writes go to a temp file and are renamed, because the engine polls on
mtime and must never read a half-written file.

**Why no `@State` anywhere in the window.** In a current SDK `@State` is a
macro, expanded by a compiler plugin that ships only with Xcode. Halo must
build with the Command Line Tools alone, because the Homebrew formula builds
from source on the user's machine. CI runs `xcode-select -s
/Library/Developer/CommandLineTools` before building for exactly this reason.
View-local state lives in a plain `ObservableObject` (`SettingsUI`).

**Why the window flips the activation policy.** The app is `.accessory`, so it
has no Dock icon and can never steal focus — the guarantee the overlay depends
on. An accessory app can open a window but cannot properly activate it: it
comes up behind, and text fields do not take the caret. So
`SettingsWindowController` switches to `.regular` while the window is open and
back to `.accessory` in `windowWillClose`, which is why it is the window's
delegate rather than trusting a button action — Cmd+W must restore it too.

Environment variables still override both, which is how a one-off
`HALO_LANGUAGE=es halo ...` works. Note that launchd sources no shell profile,
so env vars do not reach a background install — that is precisely why
`settings.json` exists.

## The pipeline

After transcription, each utterance passes through ordered stages. The order
is deliberate, and each stage can short-circuit:

```
key down   context capture starts (context.py, own thread, 0.25s budget)
           local model prewarm starts (local_llm.py, returns at once)
whisper transcript   (primed with your vocabulary and terms near the cursor)
  1. dictionary   fix vocabulary first, so every stage below matches clean text
  2. commands     BEFORE cleanup -- cleanup would rewrite "scratch that" as prose
  3. snippets     whole-utterance triggers; fully local, never hits the network
  4. pipeline.py  the cleanup mode:
                    rules   spoken marks, self-corrections, fillers, lists,
                            numbers, questions, casing -- local, ~0.3ms
                    model   Normal/Polished, only if one is ready right now
                    finish  vocabulary re-applied, app house style, cursor fit
  -> inject, then the context is cleared
```

Stage 4's spoken punctuation runs *after* commands, so a whole-utterance "new line" is still the
command rather than being swallowed as spoken punctuation, and a mid-sentence
"new line" is still handled — commands are whole-utterance only, so the two
compose instead of competing. It runs *before* cleanup so the LLM starts from
correct text rather than being the only thing standing between the user and
unpunctuated prose.

To add a stage, edit `Halo.dispatch()` in `halo.py`. To add a command, add a
phrase to `commands.json` and a branch in `Halo.run_command()`.

Command detection is **whole-utterance only** (≤6 words, fuzzy threshold
0.87), so "I had to scratch that idea" dictates normally. Mid-sentence
corrections are the cleanup pipeline's job since 0.4 — see *Self-correction*
below — so the two never compete: a lone "scratch that" is still undo.

The dictionary's fuzzy pass needs three vetoes to avoid corrupting ordinary
speech, each found by testing: the system wordlist (`launch` must not become
`launchd`), de-inflection (that list holds base forms, so `launched` needs
stemming), and all-words-English (`a sync` must not become `async`). ~0.5ms
per transcript. Deliberate tradeoff: `jason` is left alone, because it is both
a common name and a plausible mis-hearing of `JSON`. Protecting the name wins.

Undo only fires when Halo has something of its own to undo (`last_injected`).
Sending Cmd+Z into an app Halo has not typed into would eat the user's work.

## Punctuation without a network

`punctuate.py` exists because punctuation used to arrive **only** from the
OpenRouter pass. That meant Privacy Mode — the feature whose entire job is to
protect you — silently downgraded your output to a raw whisper dump, as did
simply not having an API key. Turning on the safe option should not cost
quality.

It is pure text rules, ~0.1ms, no model. It deliberately does **not** split
sentences heuristically: whisper already places most boundaries, and a wrong
split ("Dr. Smith" into two sentences) reads worse than a missing one.

The hard part is spoken punctuation. Apple substitutes "period" and "comma"
unconditionally; Halo cannot, because deleting a word the speaker actually
said is worse than leaving a command untranslated. Multi-word phrases
("question mark", "open parenthesis") are never ordinary speech and substitute
freely. The ambiguous single words must clear two tests:

- **Nothing follows but the end of the utterance** (or another mark). A spoken
  "period" is the last thing you say in a sentence; a Jurassic one has a verb
  after it.
- **No determiner in front.** "Add a dash of salt" survives.

Bare "quote" and "unquote" were dropped entirely: "a quote from the article"
is common, and the clause-end test cannot rescue it because a quotation mark
is rarely the last thing you say. A trailing "period" after a noun like
"the grace period" is still taken as a command — that case is genuinely
ambiguous, and Apple resolves it the same way.

Two spacing details were each found by a failing test. Opening and closing
quotation marks are the same character but bind in opposite directions, so the
two phrases substitute to sentinels that are resolved after every other
substitution has landed. And capitalization after `.` requires the whitespace
that actually ends a sentence — without that check, `whisper.cpp` became
`whisper.Cpp` and `example.com` became `example.Com`, corrupting the dotted
terms in the user's own dictionary.

## Cleanup modes, and why a model can only make things better

`pipeline.py` runs one of five modes — off, verbatim, light, normal, polished —
in three passes. The **rules** always run and are the fallback for
everything; the **model** pass is optional and only ever *replaces* the
rules' text if it clears every check; the **finish** re-applies your
vocabulary and the app's house style, so a model cannot undo either.

Every way a model can fail ends in the rules' text, never in a hang or a lost
dictation: not installed, still loading (skipped, not waited for), too slow
(a hard wall-clock budget — 1.5s in Normal, 3.5s in Polished — enforced by
the same abandon-the-thread helper the OpenRouter call uses), crashed
(noticed on the next dictation and restarted with backoff), or wrong. "Wrong"
is the interesting one, and there are three checks:

- `_looks_wrong()` from the OpenRouter path: too long, too short, or too far
  from the transcript (similarity 0.55; 0.35 in Polished, which may reword).
- **The invention check.** Every number, email, domain and capitalised
  non-initial word in the answer must appear in the transcript, your
  vocabulary, or the names near the cursor. This is what caught the model
  *answering* "What's the capital of France?" with Paris, and it is why
  Polished can reword freely without being able to make things up.
- A list the rules built must come back with the same line count.

Measured on an M1 Pro, over the same eight utterances:

| | load | per utterance |
|---|---|---|
| rules only (Normal) | — | 0.30ms |
| rules only (Light) | — | 0.13ms |
| Qwen2.5 1.5B Q4_K_M (default) | 1.2s | 0.11–0.55s |
| Qwen3 4B Instruct Q4_K_M | 1.7s | 0.25–1.2s |

The load happens while you speak: `start_recording()` calls `prewarm()`, and
the engine prewarms at start too. After 30 idle minutes the server is
stopped to give back its ~1.5GB, and the next key-down reloads it.

**Why llama.cpp, as a child process.** It is the same shape as whisper.cpp —
a Homebrew bottle with Metal, no Python build dependency (MLX and
llama-cpp-python both need wheels for whatever Python Homebrew ships this
month) — and a crash, a corrupt model or an out-of-memory kill takes down the
child, not the process holding your hotkey. It speaks the OpenAI chat API,
and so do `mlx_lm.server`, Ollama and LM Studio: the `endpoint` backend is
the same client pointed at a server you run, which is how MLX is supported
without Halo depending on it. Endpoints off the loopback interface are
refused, or "local" would stop meaning local. Core ML is not offered: no
maintained LLM runtime for it builds with the Command Line Tools alone.

The server binds 127.0.0.1 on a fresh port, behind a random API key read from
a 0600 file (not argv, so not `ps`), with its logging off. Measured with
llama.cpp 0.4.1: at default verbosity it logs only slot timings, never the
prompt — but that is a default, and a debug flag must never be able to put
dictation into a file. It runs in its own session so an engine crash does not
take it down; the pid file lets the next engine reap it, and the reaper
checks the command name so a recycled pid never costs an unrelated process
its life.

**Provider choice.** `auto` prefers the model on this Mac. If one is
installed but still loading, auto does *not* fall through to OpenRouter: you
installed a local model to keep text here, and a cold start is not a reason
to overrule that. OpenRouter needs a key, `cleanup.enabled`, and Privacy Mode
off. (Before 0.4 `cleanup.enabled` was read and then ignored — the Settings
toggle for it did nothing.)

## Self-correction

`backtrack.py` turns "meet me Thursday — actually Friday" into "meet me
Friday". It is not a replace table, because every cue is also ordinary
English: "I actually like it", "no problem", "wait for me", "sorry for the
delay", "I mean it". A correction must clear three tests before a word moves:

1. **The cue is delimited.** whisper marks the pause with a comma, dash or
   full stop. No pause, no correction. A cue that opens the utterance has
   nothing to correct.
2. **The replacement is found**: from the cue to the next pause.
3. **What it replaces is found by meaning**, in order: *typed* (a number, day,
   month, pronoun or name replaces the nearest earlier word of the same kind —
   which is how "at 3 PM, actually 4" keeps its PM), *restart* (the
   replacement repeats the words it started from), *clause* ("scratch that",
   "let me rephrase"), and last, *position* — only for cues that are never
   small talk ("I mean", "make that", "correction", "or rather"). "Actually"
   and "rather" are excluded from positional guessing because "it was,
   rather, unusual" must not become "it unusual".

Anything else is left exactly as spoken. The model pass may resolve it; with
no model, you get your words back rather than a guess.

## Formatting follows the app

`formatting.py` holds a `Profile` per kind of app — chat, email, document,
terminal, IDE, browser, unknown — and `context.py` decides which one you are
in. Chat gets no full stop on a single short line (`dictation.chat_period`
restores it). Email gets the greeting and sign-off on their own lines. Prose
targets get curly quotes and em dashes; a terminal gets straight ASCII and
nothing added or removed, because it may be a shell or an AI CLI taking prose
and Halo cannot tell which. Developer words that are never English
(GitHub, JSON, macOS) are cased everywhere; ones that are ("python", "swift")
only in editors and on developer sites.

Structure keys on explicit cues: "number one … number two", "bullet point",
and first/second/third only in documents with three or more items. Rules that
guess structure wrong are worse than rules that do nothing.

Numbers follow the AP convention (one to nine in words, 10 and up in digits)
unless a unit, currency, clock or label makes them a quantity. An email
address needs a reason to be one — a cue word, a structured local part, or a
local part that is not an English word — because "look at google dot com" is
a URL, not look@google.com.

## Context Awareness, and what it must never do

At key-down `context.py` reads, on its own thread with a 0.25s budget: the
focused app, and — for an ordinary text field — up to 300 characters before
the cursor, 100 after and 500 selected. Never the whole document (a field's
full value is read only when it is under 5,000 characters *and* the app lacks
`AXStringForRange`). A browser's page hostname is kept when the browser
publishes one; never the path. The window title classifies an unknown app
(an open `.py` file means an editor) and is then dropped.

**Secure fields are checked before a single text attribute is requested**:
macOS Secure Event Input (on whenever any password field has focus), the
`AXSecureTextField` role or subrole, and the field's own label — "Password",
"One-time code", "API key" and friends, because web forms and custom controls
often skip the secure role. `tests/test_context.py` proves this with a fake
backend that records every attribute asked for.

Where the text goes: the rules (spacing and casing at the cursor), and names
from it prime whisper and the local model. Never the text itself to a model,
never anything to OpenRouter, never a log line (`Context.__repr__` is
redacted; the engine logs only the category), never a file. The engine holds
it for one dictation and clears it in `finish()`'s `finally` and on cancel.

Two measured AX details. The system-wide `AXFocusedApplication` fails with
`kAXErrorCannotComplete` in some sessions, so the fallback is the owner of the
frontmost layer-0 window from Quartz (which needs no Screen Recording) — not
`NSWorkspace.frontmostApplication`, which is refreshed by notifications on a
main run loop the engine does not run. And importing PyObjC costs ~0.65s, so
the engine pays it at start rather than on the first dictation; after that a
capture takes ~75ms. Chromium and Electron apps publish no focused element
unless asked to build their accessibility tree, and Halo does not ask — that
changes how those apps behave for as long as they run — so they get
category-only context.

## Priming whisper, and conditioning the clip

Two changes that cost no model size:

**`--prompt`.** whisper conditions its first decode window on this text, so a
name or term it has never heard becomes far likelier than the ordinary English
word it otherwise collapses to. Halo passes the dictionary terms as a bare
comma-separated list plus the tail of the previous utterance — deliberately
not the sentence `prompt_context()` builds for the LLM, because whisper is not
instruction-following and English scaffolding only dilutes the terms with
tokens it already predicts well. This is the largest accuracy win available
without a bigger model, because proper nouns and jargon are exactly what a
487MB model is worst at.

It has one failure mode, and it is ugly: on a clip with no usable speech the
decoder can fall back to regurgitating its own prompt, which would paste the
entire vocabulary list at the cursor. `_is_prompt_echo()` discards an output
whose words are >90% drawn from the prompt and treats it as the silence it
actually was.

**Clip conditioning** (`Recorder.condition`): DC offset removed, quiet audio
normalized to a 0.85 peak, and 0.25s of silence welded to each end. The
padding is the one that matters — push-to-talk starts the clip the instant the
key goes down, so the first phoneme lands in whisper's very first mel frame
where it is routinely clipped. Normalization is skipped below a 0.02 peak,
deliberately above `halo.py`'s 0.005 silence check, so a missing Microphone
grant is still reported as silence rather than normalised into hiss.

The four numeric decode parameters are pinned in `settings.json` rather than
inherited. They currently match whisper.cpp's own defaults; pinning them means
an upstream default change cannot silently retune someone's dictation.

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

- No model / rate limited / timeout / model adds commentary or invents a
  name or number → injects the **rule-cleaned transcript**
- Local model loading, crashed or past its budget (1.5s Normal, 3.5s
  Polished) → rule-cleaned transcript; a crash restarts it with backoff
- Response truncated (`finish_reason=length`) → rejected, rule-cleaned text injected (a truncated
  clean-up silently drops the end of your sentence, which is worse than no cleanup)
- OpenRouter exceeds its budget (8s wall clock) → rule-cleaned text injected
- Context unavailable, slow (0.25s) or erroring → dictation proceeds without it
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
| `models.py` | Whisper and cleanup model catalogs, resumable download, checksums |
| `audio.py` | `sounddevice` capture → 16kHz mono 16-bit WAV |
| `transcribe.py` | `whisper-cli` subprocess wrapper + preflight |
| `cleanup.py` | OpenRouter call, echo dedup, bad-output rejection, fallbacks |
| `pipeline.py` | Cleanup modes: rules, the optional model pass, and the finish |
| `backtrack.py` | Spoken self-correction |
| `itn.py` | Numbers, dates, times, money, phones, emails, URLs, spoken to written |
| `formatting.py` | Per-app profiles, lists, email layout, typography, fitting to the cursor |
| `context.py` | Context Awareness: AX capture, secure-field checks, classification |
| `local_llm.py` | The model providers, and llama-server supervision |
| `inject.py` | Clipboard + Cmd+V, hard-fails if Accessibility missing |
| `permissions.py` | TCC checks, responsible-app detection |
| `punctuate.py` | Local punctuation, spoken marks, casing; no network |
| `halo.py` | The engine: hotkey, activation modes, pipeline, dispatch |
| `overlay.py` | Socket client for the overlay; no-ops if unavailable |
| `overlay/` | SwiftUI app: overlay + engine supervisor (`Halo.app`) |
| `overlay/Sources/HaloOverlay/Settings*.swift` | The Settings window, its store, and its window controller |
| `overlay/Sources/HaloOverlay/LocalModelStore.swift` | The local model's status and Download button |
| `overlay/Sources/HaloOverlay/MenuBarItem.swift` | The optional menu bar item |
| `overlay/Sources/ThinkingOrbsKit/` | Vendored Orb animation from Libraries.dev (MIT) |
| `defaults/` | Seed copies of settings and vocabulary |
| `packaging/homebrew/halo.rb` | The formula, mirrored into the tap at release |
