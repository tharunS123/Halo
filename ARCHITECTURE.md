# Architecture

Why Halo is built the way it is. Most of this exists because macOS, whisper,
or a language model behaved differently than expected, and the workaround is
not obvious from the code alone.

```
mic -> whisper.cpp (local, Metal) -> cleanup: rules, then a model on this Mac (optional) -> verified insertion into the app you started in
```

Everything in that line runs on this Mac, and since 0.4 that is enforced
rather than merely true -- see *Local only, enforced* below.

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

## Distribution: a downloadable app, and Homebrew

There is no paid Apple Developer ID, so nothing Halo ships is notarized. It
is distributed two ways, and each one answers the same two questions
differently: how does it get past Gatekeeper, and what identity does macOS
key the permissions on.

### The downloaded app

Each release attaches `Halo.dmg`: a self-contained `Halo.app`
(`scripts/make-app.sh`) that needs no Homebrew, no Python and no Terminal.

```
Contents/MacOS/Halo              the Swift app
Contents/Helpers/whisper-cli     whisper.cpp, static, Metal shaders embedded
Contents/Helpers/llama-server    llama.cpp, static, no OpenSSL, no web UI
Contents/Resources/python/       python-build-standalone 3.13 + requirements.txt
Contents/Resources/engine/       *.py, the same layout as the formula's libexec
```

- **Static helpers.** Homebrew's whisper-cli links `@rpath/libwhisper` and
  `/opt/homebrew/opt/ggml/...`, which a download does not have. Built with
  `BUILD_SHARED_LIBS=OFF` and `GGML_METAL_EMBED_LIBRARY=ON` it is one file
  linking only system frameworks. Measured on small.en with jfk.wav: 0.64 s
  against Homebrew's 0.70 s — but the *first* run on a Mac took 23.7 s while
  Metal compiled the embedded shaders, then cached them. That is why the
  engine transcribes a second of silence at start (`transcribe.warm_up`):
  the first thing anyone dictates is otherwise the one that waits.
- **Signed by one certificate, forever.** Releases are signed with a
  self-signed certificate held in repository secrets, so the designated
  requirement is `identifier "io.github.tharuns123.halo" and certificate
  root = H"bc0e931e..."` for every version. TCC keys on that, so updates keep
  Accessibility, Input Monitoring and Microphone with no re-grant.
  `release.yml` pins the hash and refuses to publish anything else, because a
  new certificate would silently cost every user a re-grant.
- **Gatekeeper, once.** A browser marks the download with
  `com.apple.quarantine`. `spctl` rejects the app, and `syspolicy_check`
  names exactly one reason: no notarization ticket — the signature and seal
  are fine, which is what the "damaged" message is about. So the first launch
  is macOS's "could not verify" dialog, and the user allows Halo once in
  System Settings › Privacy & Security › Open Anyway.
- **The quarantine has to go, after that.** Approving the app does not
  approve the programs inside it: a quarantined `python3` or `whisper-cli` is
  SIGKILLed (exit 137, measured) the moment it is exec'd. So on launch the
  app removes `com.apple.quarantine` from its own bundle (`AppBundle.swift`,
  0.17 s). The attribute is not part of the signature; `codesign --verify
  --strict` still passes afterwards. Run from the disk image or a translocated
  path the bundle is read-only and this cannot work, so the app asks to be
  moved to Applications instead of failing mysteriously.
- **The bundle is never written to.** Python would drop `__pycache__` into
  it on first import, breaking the seal. Every `.pyc` is compiled at build
  time with `--invalidation-mode unchecked-hash` (a copy out of a .dmg can
  change mtimes), and everything that runs the bundled Python sets
  `PYTHONDONTWRITEBYTECODE`. `make-app.sh` runs the engine and re-verifies the
  seal to prove it.
- **No setup step.** `EngineSupervisor.locate()` finds the engine inside the
  bundle before anything else; `config.find_whisper_bin()` and
  `local_llm.find_server_binary()` look in `Contents/Helpers` first. The
  setup guide opens on the first launch, and its last page turns on a macOS
  login item (`SMAppService`) instead of the LaunchAgent `halo setup` writes.

### Homebrew

A **Homebrew formula that builds locally** produces no quarantine attribute
at all, so there is no Gatekeeper dialog anywhere in the install — the right
choice for anyone comfortable with Terminal. Built locally, the app is signed
ad-hoc unless the user accepts a certificate generated on their own Mac.

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
  because a locally built app is never quarantined. The private key lives in
  its own keychain so `halo uninstall` can delete it outright.
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
| `~/Applications/Halo.app` | `halo setup` | the TCC identity (Homebrew) |
| `/Applications/Halo.app` | you, by drag | the downloaded app: engine, Python, helpers, and its own TCC identity |
| `~/.config/halo/` | you | settings and vocabulary, seeded once, never overwritten |
| `~/Library/Application Support/Halo/` | Halo | models, state, engine pointer |
| `~/Library/Logs/Halo/` | Halo | `engine.log`, `overlay.log` |

`paths.py` owns all of it, with an environment override for each so tests can
relocate everything. The engine is found through, in order: `HALO_PYTHON` +
`HALO_ENGINE` from the LaunchAgent, the app's own bundle (the download), the
`engine.json` pointer file, the Homebrew opt path, then a source checkout —
see `EngineSupervisor.locate()`.

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
  5. insertion   into the target captured at key-down, verified first
  -> then the context is cleared
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
the abandon-the-thread helper in `cleanup.py`), crashed
(noticed on the next dictation and restarted with backoff), or wrong. "Wrong"
is the interesting one, and there are three checks:

- `cleanup._looks_wrong()`: too long, too short, or too far from the
  transcript (similarity 0.55; 0.35 in Polished, which may reword).
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

**Provider choice.** There is one: the model on this Mac (`auto`, or its
old synonym `local`), or none (`none`, rules only). Before 0.4 `auto` could
fall back to OpenRouter; that provider is gone, and a settings file that still
names it reads as `auto`. A model that is installed but still loading is not
waited for — the rules' text is typed, and the model is warm for the next
dictation.

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

Where the text goes: the rules (spacing and casing at the cursor, and a
name on screen restoring its capitals when whisper wrote it in lower case,
unless it is also an ordinary word like "May"), and names from it prime
whisper and the local model. Never the text itself to a model, never a log
line (`Context.__repr__` is
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

A separate SwiftUI agent app draws the orb bubble and, for errors and
privacy toggles, a one-line message pill.

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

**The glow.** An Imperial ring at the edge of the bubble is
[Border Beam](https://libraries.dev/beam) (Libraries.dev, MIT), vendored in
`overlay/Sources/BorderBeamKit`. Its Metal shader needs full Xcode to compile,
so `scripts/build-beam-metallib.sh` compiles it once and the `.metallib` is
committed; the Command Line Tools build just copies it. Without the file, or
with Reduce Motion on, the ring is drawn static. It is decorative only: the
orb, not the ring, is what shows the mic level.

**The look.** Colours, type and brand art live in `DesignSystem.swift`: Night
`#000F08` and Imperial `#FB3640`, with Oswald for headings, Source Sans 3 for
text, Source Code Pro for technical values and Noto Serif Italic for the
occasional editorial line. The fonts are registered from
`Contents/Resources/Fonts` for this process only, so nothing is installed
system-wide and nothing is downloaded.

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
  computes RMS there, and streams levels. A second tap would mean two sources
  of truth. (The one exception is not the orb: Settings › Microphone and the
  setup guide open it for their meter and test recording, only while on
  screen, and never during a dictation.)
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

- No model / model adds commentary or invents a name or number → injects
  the **rule-cleaned transcript**
- Local model loading, crashed or past its budget (1.5s Normal, 3.5s
  Polished) → rule-cleaned transcript; a crash restarts it with backoff
- Response truncated (`finish_reason=length`) → rejected, rule-cleaned text injected (a truncated
  clean-up silently drops the end of your sentence, which is worse than no cleanup)
- The cleanup rules themselves raise → what whisper heard is typed, and kept
  for Retry Cleanup
- Context unavailable, slow (0.25s) or erroring → dictation proceeds without it
- Accessibility missing → loud error **and text left on your clipboard**
- Clip under 0.3s or silent → skipped with a message
- Model echoes its own output → deduplicated before injection

- Target app switched during transcription → **not typed**; the text waits on
  the clipboard, is kept for Retry Insertion, and the orb says so
- whisper fails, or the text cannot be typed → the clip and the words are
  kept (see *Nothing said is lost*)
- Chosen microphone unplugged → the system default, and the orb says so
- Microphone unplugged *mid-recording* → no audio for 1s is noticed, and
  what it heard before it went is sent at once rather than waiting on a key
  release that could only add silence
- Chosen speech model missing → another installed model, and the orb says so;
  a damaged one → "Speech model damaged", fixed in Settings › Models
- `settings.json` broken by a hand edit → the engine keeps the last good
  settings and shows "settings.json has an error"
- Any other exception in a dictation → a short message on the orb, the type
  and location (never the text) in the log, and the next key press works

Missing permission or speech model at startup → **error pill**, then the
engine exits `78`. That cannot be fixed by an immediate restart, so the
supervisor retries quietly every 20 seconds — and at once when Accessibility
is granted — so fixing the cause brings dictation back with nobody running
`halo restart`. Engine crash → supervisor restarts with backoff (1s, 2s, 4s …
capped at 30s), and after six quick crashes keeps trying every minute rather
than giving up: a hotkey that silently stops working is the worst failure
Halo has. A dictation a crash interrupted is re-transcribed by the next
engine and left on the clipboard (the clip is kept in `recovery/` until its
text lands). launchd `SIGTERM` → handled explicitly, so neither the engine
nor llama-server is orphaned. Crash times and exit codes go to
`diagnostics.json`, shown in Settings › Advanced.

## Where the text goes

Pasting into whatever has focus was the original design, and it had two
failures. Dictate into Slack, switch to Mail while whisper works, and the
Slack message landed in Mail. And the clipboard came back as plain text only:
an image or a Finder file copy you were holding was gone.

`insertion.py` now works from a **target captured at key-down** (the same AX
pass as Context Awareness, but always on and reading no text: app pid, window,
focused element, selection range). Before typing, the target is checked
again: same process, same window, same element where the app publishes them.
Anything else and nothing is typed — the text goes on the clipboard and the
orb says why.

Then the safest method that app supports:

| method | where | why |
|---|---|---|
| AX | Cocoa text (TextEdit, Notes, Mail, Xcode), unknown apps whose field can be read back | no clipboard at all; the inserted range is known exactly |
| paste | terminals, Chromium, Electron, anything that cannot be verified | universal; clipboard saved and restored |
| type | Remote Desktop, VMs, screen sharing | a paste there goes to *this* Mac's clipboard |

AX is only tried where the result can be read back, or the app is known to
honour it. An app that reports success and ignores the write would otherwise
tempt a fallback paste, and you would get your text twice.

**The clipboard** (`clipboard.py`) is saved as every item with every type
it offers — plain and rich text, HTML, URLs, images, file references,
app-private data — and restored after the paste, but only if its
`changeCount` has not moved, so a copy you made in the meantime is never
overwritten. What Halo writes is marked with the nspasteboard.org transient
and concealed types, so clipboard managers do not record your dictation.

**"Scratch that"** used to send Cmd+Z to whatever was in front, which could
undo your own last edit in another app. Each insertion is now remembered in
memory (target, text, range, time, and how many keys you have pressed since —
the key tap sees every key anyway). Undo removes exactly that range if it
still holds exactly that text; falls back to Cmd+Z only for a paste into the
same field with nothing typed since; and otherwise refuses. Command Mode
edits use the same record, with the original text, so "scratch that" puts a
rewrite back.

**Escape** sets one flag every stage checks: the microphone stops, whisper
is killed (it runs under `Popen` now, not `subprocess.run`), the cleanup
result is dropped, and a pending insertion never happens. The key still
reaches the app you are in — pynput can watch keys but not swallow them.

## Styles, vocabulary, learning

**Styles** (`styles.py`) map each app to a category (personal messaging,
work messaging, email, documents, coding/AI prompts, other) and each
category, app or website to a style. A style has rules that apply with no
model — the closing full stop, lowercase, `!`, no em dashes — and plain
instructions for the local model. A few phrasings in custom instructions
("never use em dashes", "no periods on short messages") are also read as
rules, so they hold without a model.

**The dictionary** keeps its file and gains optional fields per entry: type,
pronunciation hint (matched like a variant), `match_case`, and app or
language scope. With no context, only global entries apply — a Slack-only
nickname must not leak into an email because Halo could not tell where it
was. Import/export is one parser (`dictionary.py`) whether it runs from
`halo dictionary` or the Settings window.

**Learning** (`learning.py`) re-reads the inserted stretch 10s and 40s later
and at the next key-down, word-diffs it against what was typed, and discards
nearly everything: rewrites (under half the words kept), changes of mind
(letters less than 0.6 alike — "John" → "Jake"), grammar (a common word for
a common word), and anything over three words. What is left is scored and
becomes a suggestion at 0.7. It never edits the dictionary itself.

## Command Mode and Developer Mode

**Command Mode** (`transforms.py`) parses the spoken instruction into a rule
("delete the last sentence", "replace X with Y", casing), a transform
(built-in or custom, by alias or name), or a free-form instruction. Rules run
without a model; the rest needs the local one, and its output passes the
same invention check as cleanup. The only effect an instruction can have is
replacement text for the selection it was computed from, and
`insertion.replace_selection` refuses if the selection changed meanwhile.
There is no path to a shell, a URL or another app.

**Developer Mode** (`devmode.py`) runs before spoken punctuation, because
"dash dash verbose" must not become " - - verbose" first. Dot notation needs
a reason — a file extension, a receiver like `self`, a code-shaped word, or
a chain of three — or "polka dot dress" becomes `polka.dress`. Identifier
snapping uses only the names Context Awareness already extracted near the
cursor; no source file is read or kept.

## The engine's control socket

Settings stay files. But History's Reinsert and Retry, the menu bar's
Transform Selection and the health readout need the engine itself — it owns
typing, whisper and the model — so the engine listens on
`~/Library/Application Support/Halo/engine.sock` (0600) for a handful of
JSON-line operations. It carries no configuration, so it cannot become a
second source of truth.

## Launch at login and supervision

The `halo setup` LaunchAgent remains, and when it is installed it *is* the
Launch at Login setting. Turning the switch off deletes the plist (not
`launchctl bootout`, which would kill the running app); turning it on
without one registers `SMAppService.mainApp`. There is never more than one.

A login item or Finder launch has no environment, so the app now supervises
the engine for every launch except terminal mode (`python halo.py` marks
the overlay it spawns `HALO_TERMINAL_CHILD`), finding the engine through the
`engine.json` pointer. Because several paths can now start it, the app
refuses to run twice: a second instance would take the socket and start a
second engine on the same hotkey. For testing, `HALO_SUPERVISE=0` and
`HALO_ALLOW_SECOND_INSTANCE=1` turn both off.

## Nothing said is lost

Before 0.4 a failed transcription deleted its clip in the same `finally`
that cleans up a successful one, and a failed insertion left the text on the
clipboard and nowhere else unless History happened to be on — which it is
not, by default. `failed.py` keeps the most recent failure whatever History
says: the clip in the recovery folder (0700 folder, 0600 file), the
transcript and cleaned text **in memory only**, and where and why it failed.
Settings › History and the menu bar offer Retry Transcription, Retry
Cleanup, Retry Insertion (a fresh target, verified as usual), Copy and
Discard over the control socket.

It lasts until a retry lands, Discard, the next failure, or 30 minutes.
Privacy Mode keeps the words for a retry but never writes the audio. A
metadata file beside the clip (stage, reason, language, app — no text) lets
an engine that crashed and restarted offer the audio back; the words were
only in the dead engine's memory, and stay gone. Escape is not a failure:
a cancelled dictation is not kept.

whisper runs in its own process group so that Escape or a timeout kills
everything it started. A test found the reason: killing only the direct
child left a grandchild holding the output pipe, and `communicate()` waited
out the whole decode anyway.

## Local only, enforced

Halo used to offer OpenRouter as a cleanup provider. It was opt-in, needed a
key, and was never sent the text around the cursor — but it meant "local
dictation" had an asterisk, and a promise kept by "no code path happens to
call out" is one refactor from broken. So since 0.4:

- **There is no remote provider.** Cleanup, Command Mode and "hey halo"
  use the model on this Mac or the rules. The OpenRouter client, its key
  prompt and its Settings are gone; `halo key delete` removes a key an older
  Halo stored.
- **The engine cannot reach the network.** `netguard.install()` is the first
  thing `main()` does. It wraps the socket layer so a connect or `sendto` to
  anything but loopback, and a DNS lookup of anything but `localhost` (the
  lookup itself tells a resolver where you are going), raises
  `NetworkBlocked` before a packet is sent. Unix sockets (the overlay, the
  control socket) and 127.0.0.1 (llama-server, a user's Ollama) are
  untouched. Refusals are counted — host and port, never a payload — so a
  test can require zero.
- **Model downloads are a different process.** `halo model …` fetches
  models when you ask, from the CLI or the Settings window, and is the only
  code that names a remote URL. CI fails if any other module does.
- **The proof runs with the network off.** `tests/test_offline_e2e.py`
  re-runs itself under `sandbox-exec` with every outbound connection denied
  except loopback, DNS included, so whisper-cli and llama-server — binaries
  Python cannot police — are held to it too. On a Mac with the models it
  uses the real binaries: Record → Transcribe → Clean → Contextualize →
  Format → Insert → Undo → Transform, then the Notes-to-Messages switch, then
  a scan of every file Halo wrote for the text that was on screen.

**Privacy Mode**, whose job used to be "skip OpenRouter", now means a
dictation leaves no trace: no History entry (text or audio), no text read
around the cursor (only the app's kind, for formatting), no vocabulary
learning. The words are still cleaned up as usual.

## Privacy-safe logging

`engine.log` is a diagnostic file people paste into bug reports, and any app
running as you can read it. Since 0.4 it records the *shape* of text — how
many characters and words — never the text: not transcripts, model output,
selections, clipboard contents, dictionary words or spoken commands
(`logsafe.py`). Exceptions are logged as type and location only, because an
exception message can quote the text it was handling. For the same reason a
model answer rejected for inventing something is logged as "invented a
name", never which name. Settings › Advanced
has a clearly labelled debug switch that writes the text for someone chasing
a bug; the engine prints a warning banner on every start while it is on.

## Hard-won configuration notes

**`requests`' `timeout=` is not a wall clock.** It is a between-bytes read
timeout, so a trickling response can run for minutes past it — one measured
call took 45s under a nominal 10s timeout. `cleanup._post_bounded()` therefore
runs the request on a worker thread and abandons it at the budget. Verified: a
0.6s budget returns in 0.60s. It was found against a remote model and still
guards the local one: a llama-server under memory pressure trickles too.

**A cleanup prompt must name its edits and show an example.** A prompt that
stresses "preserve the speaker's wording" makes a model *only* strip fillers
and never punctuate; one that just says "fix punctuation" makes it **answer
questions** — a transcript asking about rate limiting once came back as a
200-word essay. The prompts in `pipeline.py` list the permitted edits and
carry one worked example each, including a dictated question coming back as
a question.

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
| `cleanup.py` | Bounded requests to the local model, echo dedup, bad-output rejection |
| `pipeline.py` | Cleanup modes: rules, the optional model pass, and the finish |
| `backtrack.py` | Spoken self-correction |
| `itn.py` | Numbers, dates, times, money, phones, emails, URLs, spoken to written |
| `formatting.py` | Per-app profiles, lists, email layout, typography, fitting to the cursor |
| `context.py` | Context Awareness: AX capture, secure-field checks, classification |
| `local_llm.py` | The model providers, and llama-server supervision |
| `inject.py` | Clipboard + Cmd+V, hard-fails if Accessibility missing |
| `permissions.py` | TCC checks, responsible-app detection |
| `punctuate.py` | Local punctuation, spoken marks, casing; no network |
| `halo.py` | The engine: hotkey, activation modes, Command Mode, pipeline, dispatch, recovery |
| `insertion.py` | Target verification, AX/paste/type insertion, safe undo |
| `clipboard.py` | Full pasteboard snapshot and restore |
| `history.py` | Opt-in SQLite dictation history and retention |
| `learning.py` | Correction detection and dictionary suggestions |
| `styles.py` | Writing styles, categories and per-app assignments |
| `transforms.py` | Command Mode parsing, rule edits, model transforms |
| `devmode.py` | Developer vocabulary, case conventions, paths, flags |
| `languages.py` | Language registry, regional variants, recent languages |
| `control.py` | The engine's control socket for the Settings window |
| `logsafe.py` | What the log may say about dictated text |
| `netguard.py` | Refuses every connection off this Mac, in the engine process |
| `failed.py` | The last failed dictation, kept for retry |
| `overlay.py` | Socket client for the overlay; no-ops if unavailable |
| `overlay/` | SwiftUI app: overlay + engine supervisor (`Halo.app`) |
| `overlay/Sources/HaloOverlay/Settings*.swift` | The Settings window, its store, and its window controller |
| `overlay/Sources/HaloOverlay/SettingsView*.swift` | The twelve Settings sections |
| `overlay/Sources/HaloOverlay/Stores.swift` | Styles, transforms, vocabulary and history stores |
| `overlay/Sources/HaloOverlay/ModelsStore.swift` | The model manager, driven by `halo model catalog --json` |
| `overlay/Sources/HaloOverlay/Microphone.swift` | CoreAudio device list, meter and test recording |
| `overlay/Sources/HaloOverlay/Onboarding.swift` | The ten-step first-run guide |
| `overlay/Sources/HaloOverlay/LoginItem.swift` | Launch at login: the setup agent or SMAppService, never both |
| `overlay/Sources/HaloOverlay/MenuBarItem.swift` | The optional menu bar item |
| `overlay/Sources/ThinkingOrbsKit/` | Vendored Orb animation from Libraries.dev (MIT) |
| `defaults/` | Seed copies of settings and vocabulary |
| `packaging/homebrew/halo.rb` | The formula, mirrored into the tap at release |
