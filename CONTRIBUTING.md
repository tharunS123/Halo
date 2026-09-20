# Contributing

Halo is a small, opinionated tool maintained by one person. Bug reports with
`halo doctor` output are the most useful thing you can send. Pull requests are
welcome; please open an issue first for anything large, so neither of us
builds the wrong thing.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing how the app, the
engine or the permissions fit together — most of the surprising code is
load-bearing and the reasons are documented there.

## Running from a checkout

```bash
git clone https://github.com/tharunS123/Halo.git
cd Halo

brew install whisper.cpp python@3.13     # prebuilt; nothing to compile
python3.13 -m venv .venv
./.venv/bin/pip install -r requirements.txt

overlay/build_app.sh                     # builds overlay/Halo.app
./.venv/bin/python cli.py setup          # same setup a user gets
```

`halo setup` from a checkout installs the app to `~/Applications` and points
the LaunchAgent at your checkout's venv and `halo.py`, so you can edit Python
and `halo restart` to pick it up.

For terminal-mode iteration with logs in front of you:

```bash
./.venv/bin/python halo.py               # Ctrl+C to quit
```

## The one build rule: no SwiftUI macros

**Do not add `@State`, `@Observable`, or any other SwiftUI macro to
`overlay/Sources/`.**

On the macOS 27 SDK these are macros whose compiler plugin ships only inside
`Xcode.app`. Halo builds with the Command Line Tools alone — that is what lets
the Homebrew formula avoid a 10 GB Xcode dependency — so a macro breaks the
build for everyone with `'SwiftUIMacros.StateMacro' could not be found`.

If a view needs state, store the wrapper directly:

```swift
private let shownState = State(initialValue: false)
private var shown: Bool {
    get { shownState.wrappedValue }
    nonmutating set { shownState.wrappedValue = newValue }
}
```

CI enforces this by building with `xcode-select -s /Library/Developer/CommandLineTools`.

## Tests

```bash
for t in tests/test_*.py; do ./.venv/bin/python "$t" || exit 1; done
```

These five are offline, hermetic and run in CI. They read
`tests/fixtures/*.json`, never the shipped `defaults/` — which is why the
fixtures still contain personal names (`Tharun`, `Purdue`): those cases are
what exercise multi-word and homophone-adjacent matching. Changing `defaults/`
should never change a test result.

`tests/manual/` needs a microphone, Accessibility, a GUI session, or a human
watching the screen. Run them by hand when touching audio, injection or the
overlay:

```bash
./.venv/bin/python tests/manual/test_audio.py       # mic capture
./.venv/bin/python tests/manual/test_transcribe.py  # whisper + cleanup
./.venv/bin/python tests/manual/hotkey_probe.py     # what your F-keys emit
./.venv/bin/python tests/manual/test_inject.py      # types into another app
./.venv/bin/python tests/manual/test_overlay.py     # every overlay state
```

Tests are plain scripts that print PASS/FAIL and exit non-zero on failure. Keep
them that way unless there is a reason to take on pytest.

## Working on setup and permissions

Test destructive paths against a sandbox HOME rather than your own install:

```bash
HOME=/tmp/halo-test ./.venv/bin/python cli.py setup --no-key --no-agent --model tiny.en
```

`--no-agent` stops before touching launchctl or System Settings. `tiny.en` is
78 MB instead of 488 MB.

For the real thing, a second macOS user account is the only honest test of a
first-run experience: it has no grants, no `~/.config/halo`, and no models.

## Releasing

```bash
scripts/release.sh 0.3.0
```

Tags the repo, waits for the GitHub tarball, computes its sha256, and updates
`Formula/halo.rb` in the tap (set `HALO_TAP_DIR` if your clone of
`homebrew-halo` is not at `~/Developer/homebrew-halo`).

**Never attach a built `Halo.app` to a release.** A downloaded archive gets
quarantined, and a quarantined ad-hoc-signed app is refused as "damaged".
Building from source in the formula is what avoids that entirely —
ARCHITECTURE.md explains it in full.

## Style

Match what is there: comments explain *why*, especially where macOS behaviour
is surprising. If you had to discover something by measurement, write down the
measurement — several of the most important comments in this codebase are
tables of numbers from a failed experiment.
