# Changelog

Dates are the release date. Versions follow [semver](https://semver.org),
loosely: Halo is an app, so "breaking" means something you have to do by hand
after upgrading, and that gets called out under **Action needed**.

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

This should be the last time an engine-only release costs you a re-grant — see
*Upgrades stop voiding your permissions* below.

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
