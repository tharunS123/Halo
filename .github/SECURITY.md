# Security

Halo runs with Accessibility and Input Monitoring, which means it can see
keystrokes and synthesize them. Take that seriously.

## Reporting

Please report anything security-relevant privately through GitHub's
[security advisories](https://github.com/tharunS123/Halo/security/advisories/new)
rather than a public issue. There is no bounty; this is a hobby project
maintained by one person, but reports are read and acted on.

## What Halo does with your data

- Audio is recorded to a temporary WAV, transcribed locally, and deleted.
- Transcript text is sent to OpenRouter **only** if you configured an API key
  and Privacy Mode is off.
- The API key is stored in the macOS Keychain, never in a file in the repo.
- Your clipboard is saved and restored around each injection.
- Nothing else is transmitted. There is no telemetry.

## Known limitations

- The app is signed ad-hoc, so its code identity is a hash rather than a
  certificate. Verify what you install: the Homebrew formula builds from this
  source on your machine.
- Halo cannot distinguish a password field from any other text field. Do not
  dictate secrets.
