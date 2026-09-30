# Installing Halo

Hold **F9**, speak, let go. Your words appear wherever your cursor is.

This guide assumes nothing. There are two ways to install Halo:

- **[Download the app](#download-the-app)** — no Terminal, no commands.
  Drag it to Applications, allow it once in System Settings, and a setup
  guide does the rest. Start here unless you already use Homebrew.
- **[Homebrew](#or-install-with-homebrew)** — three commands in Terminal,
  and Halo is built on your Mac.

Either way it takes about ten minutes, most of which is a download running
by itself.

---

## What you need

| | |
|---|---|
| **A Mac with Apple Silicon** | M1 or newer. Click the Apple menu → About This Mac; it should say "Apple M1" or similar, not "Intel". |
| **macOS 14 (Sonoma) or newer** | Same window shows your version. |
| **About 1 GB free** | The speech model is ~500 MB; the rest is small. |
| **An internet connection** | For the download and the one-time speech model. Dictation itself works offline. |

You do **not** need an account, a credit card, or an API key. Halo runs
entirely on your Mac.

---

## Download the app

1. Download **[Halo.dmg](https://github.com/tharunS123/Halo/releases/latest/download/Halo.dmg)**
   (about 35 MB) and open it.
2. Drag **Halo** onto the **Applications** folder beside it.
3. Open **Halo** from your Applications folder.

**The first time, macOS blocks it.** It says it cannot verify Halo and offers
only **Done** and **Move to Trash**. Click **Done**. Halo is signed, but not
with a paid Apple Developer ID, so macOS wants you to allow it yourself, once:

4. Open **System Settings › Privacy & Security** and scroll down to
   **Security**. Next to the message that Halo was blocked, click
   **Open Anyway**, then confirm with your password or Touch ID.
5. Click **Open**. The Halo setup guide appears.

That is the only time. Updates open normally and keep your permissions.

Then follow the guide — it is the same one described in
[Step 3](#step-3-run-setup) below, starting at **Welcome**, and ends with an
**Open Halo at login** switch (on by default). Everything in
[Step 4](#step-4-grant-three-permissions) onwards applies to you too;
wherever it says `~/Applications/Halo.app`, yours is `/Applications/Halo.app`.

**Settings later:** open Halo again from Applications (or Spotlight) and its
Settings window appears.

**Want the `halo` command too?** It is inside the app. One line in Terminal
puts it on your path:

```bash
sudo ln -sf /Applications/Halo.app/Contents/Resources/bin/halo /usr/local/bin/halo
```

---

## Or install with Homebrew

### Step 1: Install Homebrew

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

### Step 2: Install Halo

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

### Step 3: Run setup

```bash
halo setup
```

It installs Halo into your Applications folder, sets it to start at login,
and then **opens the Halo setup guide** — a window that walks through the
rest, one screen at a time:

1. **Welcome** and **Privacy** — what stays on your Mac: everything.
2. **Microphone permission** — click Allow when macOS asks.
3. **Accessibility and Input Monitoring** — the guide opens the right page
   of System Settings; switch Halo on in each list. The guide ticks each
   one off by itself. (More detail in Step 4 below if you get stuck.)
4. **Microphone** — pick one, watch the level move, record a test and play
   it back.
5. **Speech model** — it recommends one for your Mac (`small.en`, 488 MB,
   for most people; `small` if you dictate in other languages) and downloads
   it with a checksum check. Halo then compiles its graphics shaders in the
   background, once (about 25 seconds), so the test dictation is not the
   one that waits.
6. **Language** and **shortcut** — the guide checks your key really arrives
   as F9 and not as a brightness or volume key.
7. **Try it** — hold the key, speak, and watch the text appear in the box.

Close the guide at any point and it picks up where you left off next time.
**Prefer Terminal?** `halo setup --cli` does all of this with prompts
instead of a window.

**An optional cleanup model.** Without one you still get punctuation,
capitals, filler removal, spoken marks ("comma", "new line"),
self-corrections ("Thursday — actually Friday"), lists, and numbers, dates
and links written properly — all local rules. For grammar repair on your Mac
(1.1 GB), open **Settings › Models** later and click Download next to the
cleanup model; nothing leaves the machine. There is no cloud option: Halo
never sends what you say anywhere.

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

A small dark bubble appears at the bottom of your screen while you speak,
ringed in Imperial red, and the dotted orb inside ripples with your voice. A moment after you release, your words appear at the cursor.

If nothing happens, run:

```bash
halo doctor
```

It checks everything in order and prints a fix for whatever it finds.

---

## Using it

F9 is the whole interface. There is no Dock icon, and the menu bar icon is
off unless you turn it on. When you want to change something, `halo settings`
opens the Settings window.

**Voice commands** — say these on their own and Halo acts instead of typing:

| Say | What happens |
|---|---|
| "scratch that" | Removes the text Halo just typed — only Halo's own text |
| "new line" / "new paragraph" | Inserts a line break |
| "switch to Spanish" | Changes the dictation language |
| "privacy on" / "privacy off" | Stops (or resumes) History, cursor context and vocabulary learning. A lock appears on the orb. |
| "hey halo, make that shorter" | Rewrites what Halo last typed |

These only work when said **on their own**. "I had to scratch that idea"
dictates normally.

**Escape** cancels whatever Halo is doing — recording, transcribing or
cleaning up — and nothing is typed.

**Command Mode** — press **fn + Shift + F9** (on a full-size keyboard, just
**Shift + F9**), and say what to do with
the text you have selected (or, with nothing selected, with what Halo just
typed): "make this shorter", "fix the grammar", "turn this into bullet
points", "replace John with Sarah", "delete the last sentence". The orb turns
violet while it listens. Rewrites need the local cleanup model (Settings ›
Models); exact edits like replacing and deleting work without it.

---

## Making it yours

The easiest way is the Settings window:

```bash
halo settings
```

It has twelve sections: **General** (launch at login, menu bar, the orb,
sounds), **Dictation** (the shortcut, hold or press-to-talk, the cleanup level
— Off, Verbatim, Light, Normal or Polished — languages and formatting),
**Microphone**, **Intelligence** (the local model, Context Awareness,
Developer Mode), **Styles** (how Halo sounds in each app), **Dictionary**
(words whisper mishears — **add your own name first**, because whisper will
not guess it), **Commands** (Command Mode and transforms), **Models**,
**History** (off by default), **Privacy**, **Permissions** and **Advanced**.
`halo settings models` opens straight to a section.

Everything it changes is saved in `~/.config/halo/`, which upgrades never
overwrite. You can edit the same files from Terminal if you prefer:

```bash
halo config          # show every setting and where it came from
halo config edit     # open settings.json in your editor
```

| File | What it does |
|---|---|
| `settings.json` | Hotkey, activation, languages, microphone, orb, cleanup, context, history, Command Mode. |
| `styles.json` | The writing style for each kind of app, per-app overrides, your own styles. |
| `transforms.json` | Your custom Command Mode transforms. |
| `dictionary.json` | Words whisper mishears. |
| `snippets.json` | Say a phrase, get stored text. Good for signatures and templates. |
| `commands.json` | The phrases that trigger the voice commands above. |

Changes take effect within a second, with no restart, whichever way you make
them.

To change the hotkey (for example if F9 is your volume key), pick another in
Settings › General, or:

```bash
halo config set hotkey f12
```

### Upgrading from 0.3 with an OpenRouter key

Halo 0.4 no longer sends anything off your Mac, so the key is not used any
more. If you stored one, **Settings › Privacy** shows it with a **Remove**
button, or run:

```bash
halo key delete
```

A `settings.json` that still says `"provider": "openrouter"` keeps working —
it reads as the model on this Mac, or the local rules without one.

---

## Troubleshooting

Start with `halo doctor`. It catches nearly everything and names the fix.

| What you see | What it means |
|---|---|
| Nothing happens when you hold F9 | Accessibility is off, or the engine is not running. `halo doctor`. |
| The orb says "App changed" and nothing was typed | You switched apps while Halo was working, and it will not type into a different app. The text is on the clipboard (⌘V), and **Retry insertion** in Settings › History (or the menu bar) types it where you are now. |
| A dictation failed | Nothing is lost for 30 minutes: Settings › History › **Didn't make it** retries the transcription, the cleanup or the insertion, or copies it. |
| Every transcript is empty, or `peak 0.000` in the log | The Microphone prompt was missed or denied. `halo setup --repair`. |
| It worked, then stopped after an update | Updating the app voids its permissions (see below). `halo doctor`. |
| Saying "comma" types the word, or there is no full stop at the end | Those are switched off in Settings › Dictation: **Turn spoken punctuation into marks** and **End each utterance with a full stop**. |
| Grammar is not being repaired | That needs the local model: **Settings › Models › Download** next to the cleanup model. Without it the local rules still punctuate and format. `halo logs` shows the reason cleanup was skipped. |
| Cmd+V does nothing in the Settings window | You are on 0.3.2. Update to 0.3.3 or later. |
| `Refusing to load formula ... from untrusted tap` | You skipped `brew trust tharuns123/halo` in step 2. Run it, then `brew install halo` again. |
| `command not found: halo` | Homebrew install: Homebrew is not on your path; re-run the "Next steps" from step 1. Downloaded app: the command is optional, see [Download the app](#download-the-app). |
| "Move Halo to Applications first" | You opened Halo straight from the disk image or Downloads. Drag it into Applications and open it from there. |
| macOS says Halo "cannot be opened" or "could not be verified" | Expected the first time: System Settings › Privacy & Security › **Open Anyway**. See [Download the app](#download-the-app). |
| Something else | `halo logs` shows what the engine actually did. |

---

## Updating

**Downloaded app:** quit Halo (menu bar item › Quit, or `halo stop`),
download the new [Halo.dmg](https://github.com/tharunS123/Halo/releases/latest/download/Halo.dmg),
drag it onto Applications and choose **Replace**, then open it. Every release
is signed with the same certificate, so macOS keeps your Accessibility, Input
Monitoring and Microphone permissions, and there is no second "Open Anyway".

**Homebrew:**

```bash
brew upgrade halo
halo doctor
```

**If you said yes to the signing certificate during setup, upgrades just
work.** macOS keys your Accessibility and Input Monitoring grants to that
certificate, and `halo setup` re-signs each new version with the same one, so
nothing lapses.

If you declined it, Halo is signed "ad-hoc" — publishing a properly signed app
needs a paid Apple developer account, which this project does not have. Ad-hoc
means the app's code hash *is* its identity, so **macOS treats each new version
as a brand new app and silently forgets your grants.** The version number is
stored inside the bundle, so this happens on every upgrade, not only the ones
that change how Halo behaves.

Either way `halo doctor` tells you which mode you are in and detects a lapsed
grant, and `halo setup --repair` clears the stale entries and re-opens the
panes. You can switch on the certificate at any time:

```bash
halo setup --stable-identity
```

---

## Uninstalling

**Downloaded app:** quit Halo, then drag it from Applications to the Trash.
Your settings and models stay in `~/.config/halo` and
`~/Library/Application Support/Halo`; delete those folders too if you are not
coming back. (`halo uninstall --purge` does all of it, permissions included,
if you set up the `halo` command.)

**Homebrew:**

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
- **Your transcript text: never.** Cleanup, Command Mode and transforms run
  on your Mac, and the engine refuses any network connection that would leave
  it — Halo works the same with Wi-Fi off. Only a model download, which you
  start, uses the network.
- **What is around your cursor: never.** Context Awareness reads a few
  hundred characters near the cursor into memory for one dictation, so names
  and formatting come out right. It never reads password fields, is never
  logged or saved, and is never sent anywhere. Settings › Privacy turns it off.
- **Nothing else.** No telemetry, no analytics, no accounts.
