/**
 * All page copy and product facts live here, so claims can be verified in one place.
 *
 * Owner: brand/content agent (values). The exported names and TYPES are a contract with
 * the website and motion agents: change values freely, but do not rename or remove fields
 * without coordinating through the integrator.
 *
 * Every claim must be checked against README.md, INSTALL.md, CHANGELOG.md, ARCHITECTURE.md
 * and the Python source. See ../../CLAIMS.md for the evidence log.
 */

/** Resolve a file in /public against Vite's base, so the site works from any path. */
export const asset = (path: string): string => `${import.meta.env.BASE_URL}${path.replace(/^\//, '')}`;

export const links = {
  repo: 'https://github.com/tharunS123/Halo',
  installGuide: 'https://github.com/tharunS123/Halo/blob/main/INSTALL.md',
  license: 'https://github.com/tharunS123/Halo/blob/main/LICENSE',
  changelog: 'https://github.com/tharunS123/Halo/blob/main/CHANGELOG.md',
  architecture: 'https://github.com/tharunS123/Halo/blob/main/ARCHITECTURE.md',
  formula: 'https://github.com/tharunS123/homebrew-halo/blob/main/Formula/halo.rb',
  homebrew: 'https://brew.sh',
  releases: 'https://github.com/tharunS123/Halo/releases/latest',
} as const;

export const release = {
  version: '0.4.3',
  date: '2026-09-29',
};

export const media = {
  /** 1920×1080 H.264 + AAC, 23.0 s, 2.6 MB. Already fast-start (moov before mdat). */
  demoVideo: asset('media/brag.mp4'),
  /** Optional: 1280×720 H.264 + AAC 96 kbps, 0.9 MB, fast-start. Same content; for small screens. */
  demoVideoSmall: asset('media/brag-720.mp4'),
  demoPoster: asset('media/brag.jpg'),
  /** Accessible description of what the video shows. */
  demoVideoLabel: 'Halo demo video, 23 seconds, music only, no narration',
  /**
   * Optional: what kind of video this is. It is a produced, animated walkthrough with a music
   * bed (stylized message window and app examples), not a screen recording.
   */
  demoVideoNote: 'Animated walkthrough, music only',
  demoPosterAlt:
    'A message window to Sam with the sentence “Can we meet Friday at 3 PM?” at the cursor. Above it, the spoken words “Can we meet Thursday— actually Friday at three p.m.?” with “Thursday” struck out; below it, an F9 key and Halo’s round orb.',
  demoDurationLabel: '23-second demo',
  /** Plain-text description for people who cannot watch the video. */
  demoTranscript:
    'No narration; music only. On screen: an F9 key is pressed and Halo’s orb appears, labelled “Listening”. The spoken words “Can we meet Thursday— actually Friday at three p.m.?” appear, and “Thursday” is struck out. The key is released, the orb shows “Cleaning up”, and “Can we meet Friday at 3 PM?” is typed in a message window to Sam, with the label “Processed on your Mac”. Under the title “Wherever your cursor is.”, four examples show what was said and what Halo typed: Mail, “Thanks for the update. I’ll review the draft by Friday.”; Messages, “Running 10 minutes late, save me a seat”; Editor, “Add a SwiftUI view that reads config.json.”; Terminal, “brew upgrade halo”. A Wi-Fi symbol is crossed out: “Works with Wi-Fi off. No account. No telemetry. No API key. After the one-time speech model download.” It ends on the Halo logo, “Speak freely. Keep it local.”, the command “brew install halo” and “Apple Silicon · macOS 14+ · No account”.',
  hasAudio: true,
  /** WebVTT captions path if the video contains speech; undefined when it does not. */
  captions: undefined as string | undefined,
};

export const brand = {
  name: 'Halo',
  wordmark: asset('brand/halo-wordmark-chalk.svg'),
  mark: asset('brand/halo-mark-chalk.svg'),
  markImperial: asset('brand/halo-mark-imperial.svg'),
  appIcon: asset('brand/halo-app-icon.svg'),
};

export type NavItem = { label: string; href: string; external?: boolean };

export const nav: { items: NavItem[]; cta: { label: string; href: string } } = {
  items: [
    { label: 'How it works', href: '#how-it-works' },
    { label: 'Features', href: '#features' },
    { label: 'Privacy', href: '#privacy' },
    { label: 'Install', href: '#install' },
    { label: 'GitHub', href: links.repo, external: true },
  ],
  cta: { label: 'Get Halo for Mac', href: '#install' },
};

export const hero = {
  eyebrow: 'Local dictation for Mac',
  headline: 'Speak freely. Keep it local.',
  subhead:
    'Hold F9, say what’s on your mind, and release. Halo cleans up your words and types them where your cursor is—without sending your audio or text to a cloud service.',
  primaryCta: { label: 'Get Halo for Mac', href: '#install' },
  secondaryCta: { label: 'Watch 23-second demo' },
  compatibility: ['Apple Silicon', 'macOS 14+', 'No account'],
  /**
   * Optional: one short phrase for Noto Serif Italic (e.g. under the subhead or beside the
   * compatibility line). Verified: README.md:12, INSTALL.md:321-333, netguard.py:1-8.
   */
  serifAccent: 'Nothing you say leaves your Mac.',
};

/** The signature interaction. The motion agent reads these strings; do not hardcode them there. */
export const demo = {
  id: 'how-it-works',
  eyebrow: 'How it works',
  title: 'From thought to text',
  intro: 'Hold one key while you talk. Let go, and the sentence you meant lands at your cursor.',
  /** Always visible below the illustration so nothing depends on the animation. */
  disclaimer:
    'Illustration of a sample dictation with Halo’s default Normal cleanup. Not a live Halo session or a benchmark.',
  steps: [
    { key: 'hold', label: 'Hold F9', detail: 'The orb appears at the bottom of your screen.' },
    { key: 'speak', label: 'Speak', detail: 'Change your mind mid-sentence if you need to.' },
    { key: 'release', label: 'Release', detail: 'Clean text is typed at your cursor.' },
  ],
  /** Spoken phrase. `pauseAfter` marks the pause before the correction. */
  /**
   * Verified with Halo's rule pipeline (pipeline.process, mode "normal", no model): this phrase,
   * and whisper-style variants with a comma or "..." at the pause, "3 p.m." or "3pm", all give
   * exactly `result`. Plain "at three" stays a word (itn.py keeps one to nine as words in prose),
   * which is why the spoken phrase says "p.m.". See CLAIMS.md.
   */
  spoken: {
    before: 'Can we meet Thursday—',
    after: 'actually Friday at three p.m.?',
    full: 'Can we meet Thursday—actually Friday at three p.m.?',
  },
  result: 'Can we meet Friday at 3 PM?',
  resultNote: 'Self-correction and time formatting, done on your Mac.',
  processedLabel: 'Processed on your Mac',
  windowTitle: 'Message',
  recipient: 'Sam',
  stateLabels: { idle: 'Ready', listening: 'Listening', processing: 'Cleaning up', done: 'Typed' },
};

export type Story = {
  id: string;
  title: string;
  body: string[];
  /** Short bullet facts shown next to the example. */
  points?: string[];
};

export const why = {
  id: 'features',
  eyebrow: 'Why Halo',
  title: 'Built for the way you already type',
  stories: {
    ready: {
      id: 'ready',
      title: 'Your words, ready to send.',
      body: [
        'Say it the way you think it. Halo drops the “um”s, adds punctuation, and when you correct yourself after a pause (“Thursday, actually Friday”), keeps only the correction.',
        'Lists, numbers, dates, times, emails and links come out the way you would type them. All of that is local rules. An optional language model on your Mac can repair grammar too.',
      ],
      points: ['Punctuation and capitals', 'Spoken self-corrections', 'Lists and numbers', 'Optional local cleanup model'],
      /** Verified: pipeline.process(spoken, mode="normal") returns `result` exactly. */
      example: {
        spoken: 'um, can we meet thursday, actually friday at three p.m. question mark',
        result: 'Can we meet Friday at 3 PM?',
      },
    },
    anywhere: {
      id: 'anywhere',
      title: 'Wherever your cursor is.',
      body: [
        'Halo types into the app you were in when you started: an email, a chat, a note, your editor or a terminal.',
        'If you switch apps while it is working, Halo does not type into the new one. It puts the text on the clipboard instead, so you can paste it or retry.',
      ],
      /**
       * `text` is the verified output of pipeline.process(spoken, mode="normal", no model) with a
       * Context for that app (Mail com.apple.mail, Messages com.apple.MobileSMS, Notes
       * com.apple.Notes, Editor com.microsoft.VSCode, Terminal com.apple.Terminal after a shell
       * prompt). `spoken` (optional) is the whisper-style input. Short chat replies get no full
       * stop by default (dictation.chat_period = false).
       */
      uses: [
        {
          app: 'Mail',
          spoken: "Thanks for the update. I'll review the draft by Friday.",
          text: 'Thanks for the update. I’ll review the draft by Friday.',
        },
        { app: 'Messages', spoken: 'Running ten minutes late, save me a seat.', text: 'Running 10 minutes late, save me a seat' },
        {
          app: 'Notes',
          spoken: 'number one book flights number two renew passport number three call the landlord',
          text: '1. Book flights\n2. Renew passport\n3. Call the landlord',
        },
        {
          app: 'Editor',
          spoken: 'add a swift UI view that reads config dot json',
          text: 'Add a SwiftUI view that reads config.json.',
        },
        { app: 'Terminal', spoken: 'Brew upgrade halo.', text: 'brew upgrade halo' },
      ],
    },
    privacy: {
      id: 'privacy',
      title: 'Private by design.',
      body: [
        'Transcription and cleanup run on your Mac. After the one-time speech model download, dictation works with Wi-Fi off.',
      ],
      facts: [
        { label: 'Audio and text', value: 'Processed on this Mac. The engine refuses network connections that would leave it.' },
        { label: 'Account', value: 'None. No API key, no telemetry, no analytics.' },
        { label: 'History', value: 'Off by default. If you turn it on, it stays on this Mac, for as long as you choose.' },
        {
          label: 'Context Awareness',
          value:
            'On by default. Reads a few hundred characters around the cursor into memory for one dictation, skips password fields, and never logs or saves them. One switch turns it off.',
        },
        {
          label: 'Failed dictations',
          value:
            'The most recent one is kept for up to 30 minutes so you can retry it: the text in memory, the audio on this Mac (none in Privacy Mode).',
        },
        {
          label: 'Network',
          value: 'Used only when you ask Halo to download a model, by a separate process, never by the engine that hears you.',
        },
      ],
    },
  },
};

export type Feature = { title: string; body: string; example?: string };

export const moreFeatures: { eyebrow: string; title: string; items: Feature[] } = {
  eyebrow: 'Go further',
  title: 'When you want more control',
  items: [
    { title: 'Styles per app', body: 'Casual in Messages, concise in Slack, professional in Mail, exact in your editor, or a style you write yourself.' },
    { title: 'Personal dictionary', body: 'Teach Halo names and terms it mishears. When you fix a word it typed, it offers to learn it.' },
    {
      title: 'Command Mode',
      body: 'Select text, hold Shift with F9, and say what to change. Exact edits work on their own; rewrites like “make this shorter” use the local language model.',
      example: '“replace John with Sarah”',
    },
    {
      title: 'Developer Mode',
      body: 'On automatically in editors and terminals: spoken code comes out as code.',
      example: '“rename camel case user id” → Rename userId.',
    },
    {
      title: 'Optional local language model',
      body: 'A 1.1 GB download that runs on your Mac’s GPU for grammar repair. If it is missing, loading or slow, you still get the rule-based text.',
    },
  ],
};

export const install = {
  id: 'install',
  eyebrow: 'Install',
  title: 'Ready when you are.',
  intro: 'Download the Mac app, drag it to Applications, and let the setup guide walk you through the rest.',
  requirements: [
    'Apple Silicon Mac (M1 or newer)',
    'macOS 14 Sonoma or newer',
    'Microphone, Accessibility and Input Monitoring permissions (setup walks you through each)',
    'About 1 GB of free space',
    'Internet for the install and a one-time speech model download',
  ],
  commands: ['brew tap tharuns123/halo', 'brew trust tharuns123/halo', 'brew install halo', 'halo setup'],
  trustNote: '`brew trust` is required: Homebrew will not load a formula from a third-party tap until you trust it.',
  setupNote: '`halo setup` opens the same guide for permissions, your microphone, a speech model and a test dictation. Then hold F9 anywhere.',
  dmg: {
    title: 'Download Halo for Mac',
    body: 'Open Halo.dmg, drag Halo to Applications, then launch it. No Terminal or Homebrew needed. The in-app setup guide helps with permissions and the speech model.',
    caveat:
      'The first launch may be blocked because Halo does not use a paid Apple Developer ID. Click Done, then allow Halo in System Settings › Privacy & Security › Open Anyway. You only need to do this once.',
    href: 'https://github.com/tharunS123/Halo/releases/latest/download/Halo.dmg',
    label: 'Download Halo.dmg',
  },
  homebrewTitle: 'Prefer Homebrew?',
  homebrewIntro: 'Install from Terminal and build Halo on your Mac. Homebrew is optional.',
  newToHomebrew: { label: 'Read the step-by-step install guide', href: links.installGuide },
  source: { label: 'View source on GitHub', href: links.repo },
};

export const footer = {
  tagline: 'Local push-to-talk dictation for macOS.',
  compatibility: 'Apple Silicon · macOS 14+',
  license: 'MIT License',
  links: [
    { label: 'GitHub', href: links.repo },
    { label: 'Install guide', href: links.installGuide },
    { label: 'Changelog', href: links.changelog },
    { label: 'License', href: links.license },
  ],
};
