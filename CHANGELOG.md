# Changelog

Dates are the release date. Versions follow [semver](https://semver.org),
loosely: Halo is an app, so "breaking" means something you have to do by hand
after upgrading, and that gets called out under **Action needed**.

## 0.4.0 — unreleased

The release where Halo understands what you meant, not only what you said —
and can do it without the network.

### Added

- **Cleanup modes: Off, Verbatim, Light, Normal, Polished.** Settings ›
  Dictation, or `cleanup.mode`. Light is 0.3's local polish plus stumbles
  ("the the") and obvious question marks. **Normal, the new default**, adds
  self-corrections, lists and number formatting, then grammar repair if a
  language model is ready. Polished lets the model reword for readability.
  Off types exactly what whisper heard.
- **Spoken self-correction.** "Meet me Thursday — actually Friday" types
  *Meet me Friday.*; "send it to John, no, Jake" and "we need five, make that
  six, copies" work the same way, as do *sorry*, *I mean*, *correction*,
  *rather*, *wait*, *scratch that* and *let me rephrase* mid-sentence. Only a
  correction marked by a pause counts, and what it replaces is found by
  meaning (a day replaces a day, a name a name), so "I actually like it" and
  "sorry for the delay" type as said.
- **Smart formatting.** "Number one … number two" and "bullet point" become
  lists (with sub-bullets); numbers, percentages, money, times, dates,
  ordinals, phone numbers, emails and URLs are written the way you would type
  them; days and months get their capitals; prose gets curly quotes and em
  dashes, terminals keep ASCII.
- **An optional language model on your Mac.** `halo model local install`
  (or Settings › Privacy › Download) fetches a 1.1 GB Qwen2.5 model, verified
  by checksum; Halo runs it with llama.cpp and stops it after 30 idle
  minutes. 0.1–0.5s per utterance on an M1 Pro. A 2.5 GB Qwen3 model is
  there for better rewrites. Ollama, LM Studio or `mlx_lm.server` on this Mac
  work too, as `cleanup.local.backend = "endpoint"`. Every answer is checked
  and must not invent a name, number or address; if the model is missing,
  loading, slow, crashed or wrong, you get the rule-based text.
- **Context Awareness** (Settings › Privacy, on by default). Halo reads the
  app you are dictating into and a little text around the cursor: no full
  stop on a short chat reply, a greeting on its own line in email, no capital
  mid-sentence, a space where you would have typed one, names spelled the way
  the screen spells them, developer words cased in editors. It never reads
  password or other secure fields, keeps the text in memory for one
  dictation only, never logs or saves it, and never sends it to OpenRouter.
- **Where cleanup runs**, Settings › Privacy: Automatic (this Mac first),
  This Mac only, OpenRouter, or Rules only.
- `halo settings <tab>` opens the Settings window straight to a tab.
- `halo doctor` reports the cleanup mode, the local model and llama-server.

### Fixed

- **"Send transcripts to OpenRouter for cleanup" did nothing.** The setting
  was read and then ignored, so turning it off still sent text when a key was
  stored. It is now enforced.
- The dictionary's near-miss matching joined lines back together with
  spaces, which would have flattened a list into one line.

### Changed

- The Homebrew formula depends on `llama.cpp`, for the optional local model.
  The model itself is never downloaded unless you ask.
- `halo setup` offers the local model before the OpenRouter key.

## 0.3.3 — unreleased

### Added

- **Add, replace or remove the OpenRouter key from Settings › Privacy**,
  instead of running `halo key set` in Terminal. The window writes the key
  through `/usr/bin/security` with the same access list `halo key set` uses, so
  the background engine can still read it with no Keychain prompt. The key is
  passed on stdin rather than the command line, so it never appears in a
  process listing. The window never reads the key back, and it forgets
  anything you typed but didn't save when you close it.

### Fixed

- **Cmd+V, Cmd+C, Cmd+X, Cmd+A and Cmd+Z did nothing in the Settings
  window.** AppKit delivers those shortcuts through the main menu, and Halo
  had never needed one, so you couldn't paste into the key field or a
  vocabulary row. The window now installs a small Halo and Edit menu. It has
  no Quit item, because Cmd+Q would stop dictation, not just close the window.

### Changed

- **INSTALL.md caught up with 0.3.2 and 0.3.3.** It still said a key-less
  install has no punctuation or capitals, that Halo has no window, and that
  `settings.json` needs a restart. None of those are true any more. It now walks
  through the Settings window, adds a section on adding an OpenRouter key
  later with the two OpenRouter privacy switches free models need, and adds
  troubleshooting rows for a key that seems to do nothing. `halo setup` points
  at Settings › Privacy when you skip the key.

## 0.3.2 — 2026-09-20

The release where Halo punctuates by itself, and where there is finally a
window to change things in.

### Added

- **A Settings window.** `halo settings` opens it; so does the menu bar item,
  if you turn that on. Five tabs — General, Orb, Dictation, Vocabulary,
  Privacy — covering the hotkey, how dictation starts, language and model, the
  orb's size and corner, every local formatting rule, your personal
  vocabulary, and what may leave the machine.

  It edits `~/.config/halo/*.json` directly rather than talking to the engine
  over a socket, because those files were already the contract shared by the
  engine, `halo config` and a text editor; a second channel would have made
  the window a fourth writer with its own idea of the truth. The merge is
  careful to keep every key it does not itself show, including the `_comment`
  strings and the `cleanup.models` fallback chain, and writes are atomic so
  the engine can never read a half-written file.

- **Press-to-talk, as an alternative to press-and-hold.** Settings › General.
  One press starts, the next press sends, and Escape throws the clip away.
  Hold remains the default because it cannot leave the microphone open;
  toggle mode has a `max_recording_sec` backstop (120s) so a recording you
  walked away from ends by itself.

- **Spoken punctuation, offline.** Say "comma", "question mark", "new line",
  "open paren" and Halo types the mark instead of the word — the thing Apple
  Dictation does, and the thing Halo previously could not do at all.

  Words that are also ordinary English are guarded rather than substituted
  blindly: an ambiguous one only counts as a command when nothing follows it
  but the end of the utterance, and never after a determiner. "The Jurassic
  period was long" and "add a dash of salt" both type as spoken.

- **An optional menu bar item**, off by default. Settings, Privacy Mode,
  Restart Dictation, Quit. The README's "no window, no menu bar icon" promise
  still holds unless you ask for it.

### Changed

- **Punctuation and capitalization are now local.** A new `punctuate.py` runs
  on every utterance before cleanup: sentence case, the pronoun `I`, filler
  removal, a terminal full stop. It is pure text rules, ~0.1ms, no key and no
  network.

  This is mostly a privacy fix. Punctuation used to arrive only from the
  OpenRouter pass, so Privacy Mode — and anyone with no API key — silently got
  a raw whisper dump. Turning on the feature that protects you no longer
  downgrades your output.

- **whisper is primed with your vocabulary and your previous utterance.**
  Passing `--prompt` conditions the decoder before it starts, so a name or
  term it has never seen is far likelier to survive than the ordinary English
  word it used to collapse into. This is the largest accuracy gain available
  without a bigger model, because proper nouns and jargon are exactly what a
  487MB model is worst at. Guarded against the one failure mode it has: if a
  clip with no speech makes the decoder regurgitate the prompt, that output is
  discarded rather than pasted at your cursor.

- **Clips are conditioned before whisper sees them**: DC offset removed, quiet
  audio normalized, and 0.25s of silence welded to each end. The padding is
  the one that matters — push-to-talk puts your first phoneme in the encoder's
  very first frame, where it was routinely clipped. Normalization deliberately
  does nothing below a peak of 0.02, so a dead microphone is still reported as
  silence instead of being amplified into confident nonsense.

- **Non-speech tokens are suppressed at decode time** (`--suppress-nst`), so
  the beam spends its probability on words rather than on `[BLANK_AUDIO]`.

- **`settings.json` now reloads while Halo runs.** It used to be read once,
  because the hotkey is bound at startup. It now reloads on mtime, and the
  hotkey rebinds when Halo is idle — never mid-utterance. The watcher polls
  once a second, so a Settings change applies to the next utterance started
  after it is noticed, with no restart. The decode
  parameters are also pinned in the file rather than inherited, so an upstream
  whisper.cpp default change cannot silently retune your dictation.

- **Privacy Mode state reloads across processes**, so the menu bar item and
  the voice command cannot disagree about whether it is on.

- `halo config` lists the new keys and no longer tells you to restart.

### Fixed

- Capitalization after a full stop now requires the whitespace that actually
  ends a sentence. Without it, the new local pass turned `whisper.cpp` into
  `whisper.Cpp` and `example.com` into `example.Com` — corrupting the dotted
  terms in the user's own dictionary. Caught by the dictionary test.

## 0.3.1 — 2026-09-20

The release where permissions stop being a running battle.

### Action needed

One last re-grant, then no more. Upgrading changes the bundle, which under
ad-hoc signing voids your grants:

```bash
brew upgrade halo
halo setup --repair
```

Say **yes** when it offers the signing certificate. After that, macOS keys your
grants to the certificate instead of to the bundle's contents, and upgrades
stop asking.

### Added

- **A stable signing identity, so upgrades keep your permissions.** `halo
  setup` offers to generate a certificate on your Mac and sign Halo with it.
  The designated requirement then stops mentioning the code hash:

  ```
  ad-hoc       designated => cdhash H"d8cc7900..."
  certificate  designated => identifier "io.github.tharuns123.halo"
                             and certificate leaf = H"34d3a474..."
  ```

  Verified end to end: two builds differing in `CFBundleVersion` (cdhash
  `d692b8a0` and `516876f7`), the second installed over the first and re-signed
  with the same certificate, and all three permissions were still granted after
  the restart with no re-grant.

  It needs no admin password and changes no trust settings — `codesign` accepts
  an untrusted certificate. It adds no dependency: the system LibreSSL
  generates it. Gatekeeper rejects such a signature, which does not matter,
  because a locally built app is never quarantined. The private key lives in
  its own keychain, so `halo uninstall` removes it outright. Opt out with
  `--no-stable-identity`; it stays ad-hoc and every upgrade costs a re-grant.

### Fixed

- **Setup could wait for a switch that already looked on.** When the bundle
  changes, the old TCC row stays in System Settings with its switch ON while
  the app is refused, because the row is bound to the previous code hash. The
  wait-for-the-grant loop added in 0.3.0 therefore sat for five minutes with
  nothing useful for the user to do. Setup now clears stale entries first.
- `halo doctor` and `halo setup` compare the **designated requirement** rather
  than the code hash, so they are correct under either signing mode and stop
  reporting a voided grant when nothing lapsed.

### Changed

- The docs no longer claim engine-only updates keep your permissions. Under
  ad-hoc they never did: `CFBundleVersion` lives in `Info.plist`, inside the
  bundle, so every version bump changes it. That is now said plainly, alongside
  the certificate that actually fixes it.

## 0.3.0 — 2026-09-20

The first release you can install without reading the source. 0.2.0 was
installable in principle; this is the one where the documented commands
actually work start to finish on a Mac that has never seen Halo.

### Action needed

Upgrading replaces the app bundle, because this release adds an icon to it.
Halo is signed ad-hoc, so macOS treats a changed bundle as a new app and voids
its permissions. Once:

```bash
brew upgrade halo
halo setup --repair
```

`halo doctor` detects this state on its own and says the same thing.

**Expect this on every upgrade** — under ad-hoc signing, which is all 0.3.0
had. The version number is stored in the app bundle's `Info.plist`, so bumping
it changes the bundle whatever else did or did not move. What 0.3.0 fixed is
the *accidental* churn: reinstalling the same version used to produce a
different app every time. 0.3.1 removes the per-upgrade re-grant as well.

### Fixed

- **Upgrades stop voiding your permissions.** The app did not build
  reproducibly: `LC_UUID` and the symbol table's debug-map entries embedded the
  absolute build path, and Homebrew builds in a randomly named temp directory.
  So every `brew install` produced a different code hash, macOS saw a new app
  every time, and the hotkey silently stopped working — even for a release that
  changed nothing but Python. Same source now builds byte-identically anywhere,
  and CI fails if that stops being true.
- **`brew install` failed outright on a clean Mac.** Homebrew 7 refuses a
  third-party tap until you trust it, and the documented install did not
  mention `brew trust`. Every new user hit it.
- **The LaunchAgent pointed into `Cellar/halo/<version>/`.** The next
  `brew upgrade` deleted that directory and the agent failed to launch with
  nothing in the log explaining why. It now uses the version-stable `opt` path.
- **`halo uninstall` never actually reset your permissions.** It deleted the
  app before calling `tccutil`, which resolves a bundle identifier through
  LaunchServices — so every reset failed and the stale rows stayed behind. A
  later reinstall then showed Halo switched on in System Settings while the
  grant no longer matched, which looks exactly like a Halo bug.
- **`halo config set` could wipe `settings.json`.** A parse error left the
  in-memory settings empty and the write replaced the whole file with the one
  key being set, so a single trailing comma left by `halo config edit` cost you
  every other setting. It now refuses to overwrite a file it cannot read.
- **"scratch that" with nothing dictated** sent Cmd+Z anyway, undoing your own
  last edit in whatever app was focused.
- `config.reload()` silently skipped `hotkey` and `privacy_default` despite
  documenting itself as recomputing everything.
- `overlay/Info.plist.in` was not well-formed XML (a comment containing `--`).
  Apple's parser tolerates it; nothing else does. CI now checks strictly.

### Added

- **A logo.** A halo with a voice passing through it, in `docs/media/`, and an
  app icon — so the Accessibility and Input Monitoring dialogs show a mark
  instead of the blank generic square when they ask for keyboard access.
- `ruff` in CI, with a deliberately narrow rule set.
- `CHANGELOG.md`, this file.

### Changed

- **Setup waits for the permission instead of assuming it.** It used to ask you
  to press Return and check once — but System Settings wants Touch ID, so the
  switch usually goes on a few seconds later, by which point setup had recorded
  a failure and moved on. Worse, the engine had already exited, and it is not
  respawned on a config error: you flipped the switch and nothing happened.
  Setup now polls until the grant lands, then restarts the engine, because
  macOS only re-reads a grant when the process starts.
- Input Monitoring usually needs no second trip to System Settings: it
  registers itself once the engine builds its event tap.
- `halo doctor` reports the app-running-but-engine-dead state, which previously
  read as completely healthy while the hotkey did nothing.
- `scripts/release.sh` refuses to run from a branch other than `main`, to
  re-tag an existing version, or when `origin` is not the release repository.

## 0.2.0 — 2026-09-20

Halo becomes installable rather than merely runnable. Previously it had to be
run from a checkout, with whisper.cpp compiled into exactly `~/whisper.cpp`, a
virtualenv named exactly `.venv`, and personal vocabulary edited into JSON
inside the repository. The app could not even be moved.

- Homebrew tap and formula. The formula builds on your machine on purpose:
  nothing is downloaded as an archive, so nothing is quarantined, and an
  ad-hoc-signed app that *was* quarantined would be refused as "damaged".
- The `halo` command: `setup`, `doctor`, `status`, `logs`, `config`, `model`,
  `key`, `uninstall`, `start`/`stop`/`restart`.
- Settings and vocabulary move to `~/.config/halo/`, seeded once and never
  overwritten by an upgrade.
- The app is relocatable, and lives at `~/Applications/Halo.app` — a stable
  path, so upgrades do not move the thing your permissions are attached to.
- Neutral shipped defaults, offline hermetic tests, and CI that builds with the
  Command Line Tools alone.
