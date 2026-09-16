# Installing Halo

Hold **F9**, speak, release — your words are typed into whatever app has focus.
Speech is transcribed locally on your Mac; only the text is sent to OpenRouter
for punctuation cleanup (and you can turn that off).

This guide takes a fresh Mac to working background dictation that starts at
login. Budget about 20 minutes, most of it downloads.

## Requirements

- Apple Silicon Mac (M1 or later)
- macOS 14 Sonoma or later
- ~2 GB free disk space
- An [OpenRouter](https://openrouter.ai) account (free) — optional, see step 5
- **Full Xcode is not needed**; the Command Line Tools are enough

---

## 1. Install the tools

Open **Terminal** and run each of these.

**Command Line Tools** (compilers, git, swift). Skip if already installed —
it will tell you:

```bash
xcode-select --install
```

**Homebrew**, if you do not have it (check with `brew --version`). Follow the
"Next steps" it prints at the end to add `brew` to your PATH:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**cmake and Python 3.10+:**

```bash
brew install cmake python@3.13
```

> **Why a separate Python?** The `python3` that ships with macOS is 3.9, and
> this project needs 3.10 or newer. With 3.9 it crashes on startup with
> `TypeError: unsupported operand type(s) for |`.

## 2. Get the code

The project can live anywhere. This guide uses `~/Developer`:

```bash
mkdir -p ~/Developer && cd ~/Developer
git clone https://github.com/tharunS123/Halo.git
cd Halo
```

**Every command from here on runs inside this `Halo` folder**
unless it says otherwise.

## 3. Install whisper.cpp (the local speech engine)

whisper.cpp must live at exactly `~/whisper.cpp` — the app looks for it there.

```bash
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git ~/whisper.cpp
cd ~/whisper.cpp
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 8 --config Release --target whisper-cli
sh ./models/download-ggml-model.sh small.en
cd -
```

That downloads the English model (~465 MB). **Dictating in other languages?**
Also run this (another ~465 MB):

```bash
sh ~/whisper.cpp/models/download-ggml-model.sh small
```

## 4. Set up Python

The virtual environment **must** be named `.venv` inside the project folder —
the background app looks for exactly that path.

```bash
python3.13 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Check everything so far:

```bash
./.venv/bin/python -c "import transcribe; print(transcribe.preflight() or 'OK')"
```

It should print `OK`. Anything else names the missing piece — revisit step 3.

## 5. OpenRouter API key (optional but recommended)

Without a key, dictation still works, but you get raw transcripts: no
punctuation or capitalisation fixes, filler words left in.

**a. Create a key** at <https://openrouter.ai/keys>. It starts with `sk-or-v1-`.

**b. Change two account settings** at <https://openrouter.ai/settings/privacy>,
or every request fails. The app uses free models, and these are blocked by
default:

| Setting | Set to |
|---|---|
| Zero Data Retention → **Non-frontier** | **Off** |
| Data Training → **Allow free endpoints that train on request data** | **On** |

Both are required. **Understand the tradeoff:** your transcript *text* goes to
a provider that may keep it and train on it. Your *audio* never leaves the Mac.
If that is not acceptable, skip this step, or say "privacy on" while dictating
to stop all network calls.

**c. Store the key in your Keychain.** The background app starts at login,
before any terminal, so it cannot read environment variables — it reads the
Keychain instead:

```bash
security add-generic-password -s halo -a "$USER" -T /usr/bin/security -U -w
```

It asks for **"password data" — this is your OpenRouter API key, not your Mac
password.** Paste the key, press Return, paste it again, press Return. Nothing
shows while you paste; that is normal.

Check it saved (this does not print the key):

```bash
security find-generic-password -s halo >/dev/null && echo "key stored"
```

Pasted the wrong thing? Run the `add-generic-password` command again; it
replaces the old value.

## 6. Build the app

```bash
overlay/build_app.sh
```

It ends with `Built: .../overlay/Halo.app`. A `NOTE: signed ad-hoc`
message is expected — see [Updating](#updating) for what it means.

## 7. Install the login agent

```bash
./haloctl install
```

This starts Halo now and at every login. You will probably see a red
error pill: that is expected, because it has no permissions yet.

## 8. Grant permissions

macOS needs three permissions, all granted to **Halo** — not Terminal,
not Python.

Open **System Settings → Privacy & Security**, then:

1. **Accessibility** → enable **Halo**
2. **Input Monitoring** → enable **Halo**

If Halo is not in a list, click **+**, press **Cmd+Shift+G**, paste the
path below, and choose `Halo.app`. Print the path with:

```bash
echo "$PWD/overlay/Halo.app"
```

Then restart it, because macOS only reads permissions at launch:

```bash
./haloctl restart
```

3. **Microphone** — a prompt appears after the restart. Click **Allow**.
   (There is no **+** button in the Microphone list; the prompt is the only way
   in. If you missed it, see [Troubleshooting](#troubleshooting).)

## 9. Check it works

```bash
./haloctl status
```

You want to see:

```
permissions (as Halo.app):
  accessibility    : OK
  input monitoring : OK
  microphone       : OK
api key:
   found
```

plus both `app` and `engine` listed as running.

Now the real test: open **Notes**, click into a note, **hold F9**, say
"this is a test of dictation", and **release**. A small pill appears near the
bottom of the screen while you speak, and the text appears in the note a moment
after you let go.

You can close Terminal. It keeps working, and starts again at login.

---

## Using it

| Do | Result |
|---|---|
| Hold **F9**, speak, release | Text typed at the cursor |
| Say "scratch that" | Undo the last dictation |
| Say "new line" | Insert a line break |
| Say "privacy on" / "privacy off" | Stop / resume sending text to OpenRouter (the pill shows a lock) |
| Say "hey halo, make that more formal" | Rewrite your last dictation |

Commands only work when spoken **on their own**, so "I had to scratch that
idea" is typed normally.

Personalise by editing these files in the project folder. Changes apply
immediately, no restart:

- `dictionary.json` — words whisper keeps getting wrong (names, jargon)
- `snippets.json` — say a short phrase, get a long stored text
- `commands.json` — the phrases for the commands above

**F9 not convenient?** On MacBooks, F9 may be a media key. If holding it
changes brightness or volume instead of dictating, turn on **System Settings →
Keyboard → Keyboard Shortcuts → Function Keys → Use F1, F2, etc. keys as
standard function keys**, or hold **fn** with F9.

## Managing it

```bash
./haloctl status      # is it running, are permissions and the key OK
./haloctl restart
./haloctl stop        # turn off until next login or ./haloctl start
./haloctl start
./haloctl logs        # live logs (Ctrl+C to exit)
```

## Updating

```bash
git pull
./.venv/bin/pip install -r requirements.txt
overlay/build_app.sh
./haloctl restart
```

**After every rebuild, re-grant Accessibility and Input Monitoring.** The app
is signed without a developer certificate, so macOS treats each new build as a
different app and silently drops its permissions. Symptom: F9 stops working and
`./haloctl status` shows `NOT GRANTED`. Fix:

```bash
tccutil reset Accessibility io.github.tharuns123.halo
tccutil reset ListenEvent io.github.tharuns123.halo
```

Then repeat [step 8](#8-grant-permissions). To avoid this permanently, create a
self-signed code-signing certificate once, as described at the bottom of
`overlay/build_app.sh`.

## Uninstalling

```bash
./haloctl uninstall                                  # stop and remove from login
security delete-generic-password -s halo   # remove the API key
tccutil reset All io.github.tharuns123.halo         # remove its permissions
```

Then delete the project folder and `~/whisper.cpp`. Logs are in
`~/Library/Logs/Halo`, and settings in `~/.halo-state.json`.

---

## Troubleshooting

Start with `./haloctl status`, then `./haloctl logs`.

| Symptom | Cause and fix |
|---|---|
| `security add-generic-password` asks for a "password" | It wants your **OpenRouter API key**, not your Mac password. See step 5c. |
| `TypeError: unsupported operand type(s) for \|` | Wrong Python. Delete `.venv` and redo step 4 with `python3.13`. |
| Error pill says **"venv missing"** | `.venv` is missing or misnamed. Redo step 4 inside the project folder. |
| `preflight` mentions `whisper-cli not found` | whisper.cpp is not at `~/whisper.cpp`, or the build failed. Redo step 3. |
| Build error mentioning `SwiftUIMacros` | Someone added `@State` to the overlay code; it needs full Xcode. Update with `git pull`. |
| `NOT GRANTED` in status after granting | You rebuilt the app, or did not restart. See [Updating](#updating), then `./haloctl restart`. |
| F9 does nothing, no pill | Engine is not running or Accessibility is missing. Check `./haloctl status`. Also check the F-key setting under [Using it](#using-it). |
| Pill appears but no text is typed | Accessibility is missing — that is what allows pasting. Grant it and restart. |
| Text is typed but never punctuated | No API key (`api key: MISSING`), or the OpenRouter settings in step 5b. `./haloctl logs` shows the reason. |
| Every recording is empty / logs say `peak 0.000` | Microphone was denied. macOS returns silence instead of an error. Run `tccutil reset Microphone io.github.tharuns123.halo`, then `./haloctl restart` and click **Allow**. |
| First dictation takes ~25 seconds | Normal, once only: whisper compiles its GPU shaders. Later ones take under a second. |
| Error pill: "Dictation keeps crashing" | Check `./haloctl logs` for the Python error, fix it, then `./haloctl restart`. |
