# Claims log

Every product fact on the site lives in `src/content/site.ts`. This file records where each
one was checked. Paths are relative to the repository root; line numbers are as of v0.4.2
(2026-09-29).

**Status:** verified = matches the source as written · corrected = the copy was changed to
match · removed = taken off the page · external = checked against a source outside this repo.

## How the text examples were checked

The examples were run through Halo's own rule pipeline, the same way
`tests/test_cleanup_modes.py` and `tests/test_devmode.py` do:
`pipeline.process(text, mode="normal", ctx=<Context for the app>, dictionary=Dictionary(),
select=lambda m: (None, "stub"))`. That means the default Normal cleanup with no local model
and `defaults/` settings, using the repo's `.venv` Python. The inputs are the kind of text
whisper produces, with commas where there are pauses. `ctx.before` was `""`, or a shell prompt
for Terminal.

| Input (whisper-style) | App context | Output (exact) |
|---|---|---|
| `Can we meet Thursday—actually Friday at three p.m.?` | none / Messages / Mail | `Can we meet Friday at 3 PM?` |
| `Can we meet Thursday, actually Friday at three p.m.?` | none | `Can we meet Friday at 3 PM?` |
| `Can we meet Thursday, actually Friday at 3pm?` | none | `Can we meet Friday at 3 PM?` |
| `Can we meet Thursday, actually Friday at three p.m.` (no `?`) | Messages | `Can we meet Friday at 3 PM?` |
| `um, can we meet thursday, actually friday at three p.m. question mark` | none | `Can we meet Friday at 3 PM?` |
| `Can we meet Thursday—actually Friday at three?` (the brief's phrase) | none | `Can we meet Friday at three?` (**not** "at 3") |
| `Can we meet Thursday actually Friday at three?` (no pause mark) | none | unchanged: no self-correction without a pause |
| `Thanks for the update. I'll review the draft by Friday.` | Mail | `Thanks for the update. I’ll review the draft by Friday.` |
| `Running ten minutes late, save me a seat.` | Messages | `Running 10 minutes late, save me a seat` |
| `number one book flights number two renew passport number three call the landlord` | Notes | `1. Book flights\n2. Renew passport\n3. Call the landlord` |
| `add a swift UI view that reads config dot json` | VS Code | `Add a SwiftUI view that reads config.json.` |
| `Brew upgrade halo.` | Terminal, after `user@mac halo % ` | `brew upgrade halo` |
| `rename camel case user id` | VS Code | `Rename userId.` |

## Claims

| Claim on the site | Source | Status |
|---|---|---|
| Hold F9, speak, release; text is typed at the cursor | README.md:10-11, 53; defaults/settings.json `hotkey: f9`, `activation: hold` | verified |
| Local: audio and text are not sent to a cloud service | README.md:13, 125-129; INSTALL.md:321-333; netguard.py:1-20 | verified |
| Hero serif accent “Nothing you say leaves your Mac.” | README.md:13 | verified |
| Apple Silicon, macOS 14+ | README.md:49; INSTALL.md:15-16; dmg `Install Halo.command` (checks `arm64` and major version ≥ 14) | verified |
| No account (no API key, telemetry or analytics) | README.md:49, 139; INSTALL.md:20-21, 333 | verified |
| Demo: “Thursday—actually Friday at three” → “Friday at 3” | Pipeline run above; itn.py:15-17 (one to nine stay words unless a unit, currency, clock or month follows) | **corrected**: the phrase is now “…at three p.m.?” → “Can we meet Friday at 3 PM?” |
| Self-correction needs a pause (“Thursday, actually Friday”) | README.md:191 (“Only a pause-marked correction counts”); tests/test_backtrack.py:30-37 | verified; the Ready copy now says “after a pause” |
| Self-correction, lists and number formatting are the default | defaults/settings.json `cleanup.mode: normal`, `dictation.self_correction`, `smart_formatting: true`; pipeline.py:1-12 | verified; demo disclaimer now names “default Normal cleanup” |
| Fillers, punctuation, capitals are local rules | README.md:59-67; pipeline.py:57-110 | verified |
| Lists, numbers, dates, times, emails and links | README.md:63-67; itn.py:1-8; formatting.py | verified |
| Optional local model repairs grammar; the rules’ text is kept if it is missing or slow | README.md:68-74; pipeline.py:13-17, 281-330 | verified |
| Local model is 1.1 GB and runs on the GPU | models.py:67-74 (`qwen2.5-1.5b`, 1,117,320,736 bytes); README.md:68-70 | verified |
| “Ready” example (`um, … question mark` → `Can we meet Friday at 3 PM?`) | Pipeline run above | **corrected** (old input had no pause, so no correction, and “three” stayed a word) |
| Types into the app where dictation began; no typing after an app switch | insertion.py:1-15, 111-115; README.md:99-101 | verified |
| After a switch the text goes to the clipboard for paste or retry | halo.py:745-756; INSTALL.md:263 | **corrected** (“the text is kept” → “puts the text on the clipboard … paste it or retry”) |
| Mail / Messages / Notes / Editor / Terminal examples | Pipeline run above; context.py:49-83 (bundle categories); formatting.py:26, 37 (no full stop on short chat) | **corrected**: Editor `const userId = session.user.id;` and Terminal `npm run build -- --dry-run` are not what Halo produces (“equals” stays a word, “const” and “npm” get capitalised). They were replaced with verified outputs. Optional `spoken` inputs were added. |
| Mail example uses a curly apostrophe | formatting.typography (pipeline run: `I'll` → `I’ll`) | verified |
| Developer Mode is on automatically in editors and terminals | devmode.py:1-5, 218-229; defaults `developer_mode: auto` | verified |
| Developer Mode example “camel case user id” → userId | devmode.py:8-9; tests/test_devmode.py:41, 82-84 | **corrected** to “rename camel case user id” → `Rename userId.` At the start of a field the pipeline gives `UserId.` |
| Command Mode: Shift + F9 on selected text | README.md:82-84; INSTALL.md:187-192 | verified |
| “make this shorter” needs the local model; “replace John with Sarah” does not | transforms.py:7-13, 279-282; INSTALL.md:191-192 | **corrected**: the example is now the rule-based edit, and the body says rewrites use the local model |
| Styles per app: casual in Messages, concise in Slack, professional in Mail, exact in the editor, or your own | README.md:80-81; defaults/styles.json `categories` | verified |
| Personal dictionary; offers to learn a corrected word | README.md:105-108 | verified |
| History off by default, kept only on this Mac, with a retention you choose | settings.py:143-150 (`enabled: False`, `retention`); README.md:109-110, 136-137 | verified (wording tightened) |
| Context Awareness: a few hundred characters, in memory for one dictation, skips password fields, not logged or saved, one switch | README.md:74-80, 130-133; defaults/settings.json `context`; context.py:106-145 | verified. **Corrected** to say it is **on by default** (`context.enabled: true`). |
| The last failed dictation is kept for up to 30 minutes (text in memory, audio on disk unless Privacy Mode) | failed.py:1-21, 33; halo.py:812-823 | **added** so the page does not imply nothing is ever kept |
| Network used only for a model download you ask for, by a separate process | README.md:141-142; netguard.py:17-18 | verified |
| Offline after the one-time model download | INSTALL.md:18; README.md:14-15 | verified |
| Requirements: Microphone, Accessibility **and Input Monitoring** | INSTALL.md:87-89, 114-141; permissions.py:1, 44-65; dmg `READ ME FIRST.txt` | **corrected** (Input Monitoring was missing) |
| About 1 GB of free space | INSTALL.md:17; dmg `READ ME FIRST.txt` (“about 1 GB free”) | **added** |
| Homebrew install builds on your Mac, so it is never quarantined | INSTALL.md:69-71; dmg script header comment | verified |
| Exact four commands; `brew trust` required | README.md:31-40; INSTALL.md:50-62 | verified |
| `halo setup` opens a guide: permissions, microphone, speech model, test dictation | INSTALL.md:77-99; README.md:41-46 | verified |
| .dmg URL, 21,765 bytes (“22 KB”), sha256 `691b56cd…a42f` | `gh release view v0.4.2` (asset digest and size); `shasum -a 256 dist/Halo-0.4.2.dmg` | verified |
| .dmg holds an installer script, not the app: it checks the Mac, installs Homebrew if missing, puts brew on PATH, runs tap/trust/install (or upgrade), then `halo setup` | `hdiutil attach -readonly` of dist/Halo-0.4.2.dmg: `Install Halo.command`, `READ ME FIRST.txt` | verified (body made more specific) |
| The script is unsigned: right-click → Open | `codesign -dv` reports “code object is not signed at all”; `READ ME FIRST.txt` step 1 | verified |
| On macOS 15+, if it is still blocked, allow it in System Settings › Privacy & Security | Apple, macOS Sequoia Gatekeeper change (Control-click no longer overrides Gatekeeper; approval moves to Privacy & Security) | **external, added**. The dmg’s own `READ ME FIRST.txt` mentions only right-click → Open. |
| MIT License | LICENSE:1 | verified |
| Version 0.4.2, released 2026-09-29 | VERSION; CHANGELOG.md:7 | verified |
| Demo video: 22 seconds | ffprobe: 22.6 s | verified |
| Demo video is narrated | whisper.cpp `small.en` transcription of the audio track (speech 0.0–21.2 s); captions in public/media/brag.en.vtt | **corrected** (was “no narration”) |
| Demo video is an animated walkthrough, not a screen recording | Frames extracted with ffmpeg: stylized Notes window, raw whisper text overlay, pipeline diagram, “11s → 0.73s” figure, title card | **corrected**: added `media.demoVideoNote`, and rewrote `demoTranscript` and `demoPosterAlt` from the frames |
| “11 seconds of speech in under one” (said in the video) | README.md:13-15 (0.73 s, about 15× realtime) | verified (video content, not site copy) |
| The video’s cleanup (“um so the the deploy is uh blocked on jason config” → “The deploy is blocked on the JSON config.”) | Pipeline run: rules alone give `So the deploy is blocked on jason config.` | not reproducible by rules alone. It is video content; the site does not repeat it as a claim. |

## Removed or avoided

- No stats, ratings, testimonials, logos, user counts or pricing are on the page. The only price is `0` in JSON-LD, because Halo is MIT-licensed and installed for free.
- The site does not describe a signed, notarized or drag-to-Applications app.
