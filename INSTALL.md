# Installing Halo

Hold **F9**, speak, let go. Your words appear wherever your cursor is.

This guide assumes nothing. You will paste three commands into an app called
Terminal, answer a few questions, and flip three switches in System Settings.
It takes about ten minutes, most of which is a download running by itself.

---

## What you need

| | |
|---|---|
| **A Mac with Apple Silicon** | M1 or newer. Click the Apple menu → About This Mac; it should say "Apple M1" or similar, not "Intel". |
| **macOS 14 (Sonoma) or newer** | Same window shows your version. |
| **About 1 GB free** | The speech model is ~500 MB; the rest is small. |
| **An internet connection** | For the install and the one-time model download. Dictation itself works offline. |

You do **not** need an account, a credit card, or an API key. Halo runs
entirely on your Mac unless you later choose otherwise.

---

## Step 1: Install Homebrew

Homebrew is the standard installer for Mac developer tools. Halo uses it so
you never have to compile anything.

Open **Terminal** (press Cmd+Space, type `Terminal`, press Return), then paste
this and press Return:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It will ask for your Mac password (typing shows nothing — that is normal) and
take a few minutes.

When it finishes it prints a short "Next steps" section with two commands to
run. **Run them.** They put `brew` on your path; skipping them is the most
common reason the next step fails with `command not found`.

Already have Homebrew? Skip to step 2.

---

## Step 2: Install Halo

```bash
brew tap tharuns123/halo
brew trust tharuns123/halo
brew install halo
```

The middle line is not optional. Homebrew 7 will not load a formula from
anyone's personal tap until you explicitly trust it, and without it the third
command stops with:

```
Error: Refusing to load formula tharuns123/halo/halo from untrusted tap
```

That is Homebrew protecting you from running a stranger's build instructions,
which is reasonable — `brew trust` is you saying you have decided to. If you
would rather read them first, they are in
[Formula/halo.rb](https://github.com/tharunS123/homebrew-halo/blob/main/Formula/halo.rb).

The install itself builds Halo on your Mac and takes a couple of minutes.
Building locally is deliberate: it means macOS never flags Halo as "downloaded
from the internet", so you will not have to fight Gatekeeper warnings.

---

## Step 3: Run setup

```bash
halo setup
```

It walks through the rest. Here is what it asks and what to pick.

**Which model?** Press Return for the default (`small.en`, 488 MB, English
only). It is the best accuracy for its size. Choose `base.en` (148 MB) only if
you are short on disk; choose `small` if you dictate in a language other than
English. You can change your mind later with `halo model download <name>`.

**The transcription test.** Setup transcribes a sample clip to prove the whole
chain works. **The first run takes around 25 seconds** while macOS compiles
the graphics shaders whisper uses. This is normal and it happens exactly once
— every run after it is under a second. Do not quit during it.

**An OpenRouter key?** Say no unless you want it. This is genuinely optional:

- **Without a key** (the default): you get the raw transcript. No punctuation,
  no capital letters, and filler words like "um" left in. Everything stays on
  your Mac.
- **With a key**: the *text* of each transcript is sent to a free cleanup
  model that adds punctuation and removes fillers. Your audio never leaves
  your Mac either way, and saying "privacy on" stops even the text from
  leaving.

You can add one later with `halo key set`, so skipping costs you nothing.

---

## Step 4: Grant three permissions

macOS will not let any app watch your keyboard or type for you without
explicit permission. Setup opens each pane for you, in order.

### Microphone

A prompt appears by itself the first time Halo runs. **Click Allow.**

You cannot grant this by hand — the Microphone pane has no "+" button, so an
app only appears there once it has asked. If you miss the prompt, Halo records
perfect silence and every transcript comes back empty, which looks like a bug
rather than a permission problem. If that happens, run `halo doctor`.

### Accessibility, then Input Monitoring

For each one, System Settings opens on the right pane:

1. Find **Halo** in the list and switch it **on**.
2. If Halo is not listed: click **+**, press **Cmd+Shift+G**, paste
   `~/Applications/Halo.app`, press Return, then click Open.

Grant these to **Halo** — not to Terminal, and not to something called
`python`.

Once Halo has them, you can safely revoke Accessibility from your terminal or
code editor if you had granted it there. The permission now belongs to one
small purpose-built app instead of something that can run anything.

---

## Step 5: Try it

Open **Notes** (or any app with a text field), click where you want to type,
then:

**Hold F9. Say "hello from Halo". Let go.**

A dark orb appears at the bottom of your screen while you speak and ripples
with your voice. A moment after you release, your words appear at the cursor.

If nothing happens, run:

```bash
halo doctor
```

It checks everything in order and prints a fix for whatever it finds.

---

## Using it

Halo has no menu bar icon and no window. F9 is the whole interface.

**Voice commands** — say these on their own and Halo acts instead of typing:

| Say | What happens |
|---|---|
| "scratch that" | Undoes the text Halo just typed |
| "new line" / "new paragraph" | Inserts a line break |
| "privacy on" / "privacy off" | Stops (or resumes) sending text for cleanup. A lock appears on the orb. |
| "hey halo, make that shorter" | Rewrites what Halo last typed |

These only work when said **on their own**. "I had to scratch that idea"
dictates normally.

---

## Making it yours

Your settings and vocabulary live in `~/.config/halo/`. Upgrades never
overwrite them.

```bash
halo config          # show every setting and where it came from
halo config edit     # open settings.json in your editor
```

| File | What it does |
|---|---|
| `settings.json` | Hotkey, language, model, cleanup options. Run `halo restart` after changing. |
| `dictionary.json` | Words whisper mishears. **Add your own name first** — whisper will not guess it. |
| `snippets.json` | Say a phrase, get stored text. Good for signatures and templates. |
| `commands.json` | The phrases that trigger the voice commands above. |

The last three take effect immediately — no restart.

To change the hotkey (for example if F9 is your volume key):

```bash
halo config set hotkey f12
```

---

## Troubleshooting

Start with `halo doctor`. It catches nearly everything and names the fix.

| What you see | What it means |
|---|---|
| Nothing happens when you hold F9 | Accessibility is off, or the engine is not running. `halo doctor`. |
| Text appears in the wrong app | Click into the target app *before* holding F9. |
| Every transcript is empty, or `peak 0.000` in the log | The Microphone prompt was missed or denied. `halo setup --repair`. |
| It worked, then stopped after an update | Updating the app voids its permissions (see below). `halo doctor`. |
| Text has no punctuation | Either no API key, or Privacy Mode is on. Check with `halo key status`; say "privacy off". |
| `Refusing to load formula ... from untrusted tap` | You skipped `brew trust tharuns123/halo` in step 2. Run it, then `brew install halo` again. |
| `command not found: halo` | Homebrew is not on your path. Re-run the "Next steps" from step 1. |
| Something else | `halo logs` shows what the engine actually did. |

---

## Updating

```bash
brew upgrade halo
halo doctor
```

Halo is signed "ad-hoc", because publishing a signed app requires a paid Apple
developer account. The practical consequence: **when the app itself changes,
macOS treats it as a brand new app and silently forgets your Accessibility and
Input Monitoring grants.**

`halo doctor` detects exactly this and tells you to run `halo setup --repair`,
which clears the stale entries and re-opens the two panes.

This happens on **every** upgrade, not only the ones that change the app: the
version number is stored inside the bundle, so bumping it changes the bundle.
Reinstalling the *same* version costs nothing, because the build is
reproducible down to the byte.

---

## Uninstalling

```bash
halo uninstall     # the agent, the app, its permissions and the stored key
brew uninstall halo
```

That leaves your settings and the downloaded model in place, in case you come
back. To remove those too:

```bash
halo uninstall --purge
```

---

## What leaves your Mac

- **Your audio: never.** Recording and transcription both happen locally, via
  whisper.cpp.
- **Your transcript text: only if you added an API key**, and only the text,
  to OpenRouter for punctuation. Say "privacy on" to stop that at any time, or
  never add a key.
- **Nothing else.** No telemetry, no analytics, no accounts.

One caveat worth knowing if you do use a key: OpenRouter's free models require
you to allow data retention and training on their privacy settings page, so
those transcripts may be retained by the provider. `halo setup` says so at the
point where it matters.
