# Halo website

The marketing site for [Halo](https://github.com/tharunS123/Halo), local push-to-talk dictation for Apple Silicon Macs. It is a static single page built with Vite, React and TypeScript, using the free [`motion`](https://motion.dev) package for the one signature animation.

It is independent of the macOS app: nothing here is imported by, or changes, the Python engine or the Swift overlay.

## Run locally

Requires Node 20+.

```sh
cd website
npm install
npm run dev        # http://localhost:5173
```

## Build

```sh
npm run build      # type-checks, then writes static files to website/dist/
npm run preview    # serves dist/ at http://localhost:4173
```

`vite.config.ts` uses a relative `base`, so `dist/` can be hosted from a domain root or a subpath (for example GitHub Pages) without changes. Nothing is deployed automatically.

Before publishing, set the absolute site URL in `index.html` (`canonical`, `og:url`, `og:image`, `twitter:image`); social cards need absolute image URLs.

## Layout

| Path | What it is |
| --- | --- |
| `src/content/site.ts` | Every piece of copy, link and product fact. Edit words here, not in components. |
| `CLAIMS.md` | Where each product claim was verified in the Halo repo. Update it when copy changes. |
| `src/styles/tokens.css` | Night + Imperial tokens from `halo-design-v2/design-tokens.json`. |
| `src/styles/base.css` | Reset, type, and shared utilities (`.btn`, `.kbd`, `.eyebrow`, `.container`). |
| `src/styles/fonts.css` | Self-hosted, subset OFL fonts (Oswald, Source Sans 3, Source Code Pro, Noto Serif Italic). |
| `src/components/` | Page sections, approved design previews, the per-app output selector, and shared controls. |
| `src/components/demo/` | "From thought to text": the Hold F9 → Speak → Release illustration. |
| `public/` | Brand SVGs, fonts, demo video and poster, social image, and approved interface board images. |

## Behavior notes

- **Demo video.** `public/media/brag.mp4` is the produced demo video from `docs/media/` (rendered from `brag-output/` in the repo root), not a screen recording. It is not fetched until someone presses Play, never autoplays, and plays with native controls.
- **Illustration.** The "From thought to text" scene is a labeled web illustration, not a live Halo session. It starts once when scrolled into view, pauses off-screen or in a background tab, and has Play/Pause and Replay controls. With `prefers-reduced-motion` it shows the finished state without animating.
- **Interface imagery.** The hero, interface gallery, and illustration orb use unchanged images from `halo-design-v2/boards/`. The site crops to the app UI/orb area with SVG view boxes and labels the result as an approved design preview. These are not runtime screenshots; the showcased status values are illustrative.
- **Interactive examples.** The interface gallery and per-app output selector animate on selection, with a still transition under reduced motion. The output examples use the verified strings in `src/content/site.ts`.
- **No third parties.** No analytics, no remote fonts, no CDN scripts. The only outbound links go to GitHub and brew.sh.

## Updating for a new Halo release

1. Update `release`, the download link, and the install copy in `src/content/site.ts`.
2. Re-check any changed behavior against `README.md`, `INSTALL.md` and `CHANGELOG.md`, and update `CLAIMS.md`.
3. If the demo recording changes, replace `public/media/brag.mp4` and `brag.jpg` (keep `-movflags +faststart`).
