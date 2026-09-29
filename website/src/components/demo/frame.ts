import { amplitudeAt } from './amplitude';
import type { DemoModel } from './model';
import {
  CARET_BLINK_END,
  CARET_BLINK_PERIOD,
  CHIP_END,
  CHIP_START,
  DURATION,
  KEY_DOWN_END,
  KEY_UP_END,
  ORB_IN_END,
  ORB_IN_START,
  PRESS_START,
  PROCESS_BLEND_END,
  RELEASE_START,
  RESULT_GROUP_FADE,
  SETTLE_END,
  SPOKEN_WORD_FADE,
  STRIKE_END,
  STRIKE_START,
  TYPE_GROUPS_END,
  TYPE_START,
  orbStateAt,
  type OrbState,
} from './timeline';

/**
 * Imperative renderer: maps the clock value `t` to transforms and opacities on the scene's
 * elements. It never changes layout, only `transform`/`opacity` (and the SVG `transform`
 * attribute of the orb dashes). React renders the structure once; this runs per frame.
 */

/* ---------- Orb geometry (SVG user units, viewBox -50 -50 100 100) ---------- */

export const DASH_COUNT = 56;
const RING_R = 24;

export const DASHES = Array.from({ length: DASH_COUNT }, (_, i) => {
  const rad = (i / DASH_COUNT) * Math.PI * 2;
  const deg = (i / DASH_COUNT) * 360;
  /** Fixed per-dash brightness, so the ring reads as fine grayscale dashes of varying opacity. */
  const base = 0.42 + 0.46 * (0.5 + 0.5 * Math.sin(i * 2.39996 + 0.7));
  return {
    deg,
    rad,
    base,
    /** Resting geometry, rendered into the HTML so the ring is drawn before (or without) JavaScript. */
    idleTransform: `rotate(${deg.toFixed(2)}) translate(0 ${(-RING_R).toFixed(2)}) scale(1 1.60)`,
    idleOpacity: base * 0.85,
  };
});

/* ---------- Easing ---------- */

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
const prog = (t: number, a: number, b: number) => clamp01((t - a) / (b - a));
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const easeOut = (x: number) => 1 - (1 - x) ** 3;
const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);
const smooth = (a: number, b: number, x: number) => {
  const k = clamp01((x - a) / (b - a));
  return k * k * (3 - 2 * k);
};

/* ---------- Element registry ---------- */

export type SceneEls = {
  keyCap: HTMLElement | null;
  keyLed: HTMLElement | null;
  orb: HTMLElement | null;
  ring: SVGGElement | null;
  dashes: (SVGLineElement | null)[];
  caption: HTMLElement | null;
  spoken: (HTMLElement | null)[];
  strike: HTMLElement | null;
  words: (HTMLElement | null)[];
  /** carets[0] sits before the first word; carets[i + 1] sits after word i. */
  carets: (HTMLElement | null)[];
  states: Partial<Record<OrbState, HTMLElement | null>>;
  chip: HTMLElement | null;
  progress: HTMLElement | null;
};

export const createSceneEls = (): SceneEls => ({
  keyCap: null,
  keyLed: null,
  orb: null,
  ring: null,
  dashes: [],
  caption: null,
  spoken: [],
  strike: null,
  words: [],
  carets: [],
  states: {},
  chip: null,
  progress: null,
});

/* ---------- Write helpers that skip redundant DOM writes ---------- */

const written = new WeakMap<Element, { o?: string; t?: string }>();

function slot(el: Element) {
  let s = written.get(el);
  if (!s) {
    s = {};
    written.set(el, s);
  }
  return s;
}

function setOpacity(el: HTMLElement | SVGElement | null | undefined, v: number) {
  if (!el) return;
  const s = slot(el);
  const val = clamp01(v).toFixed(3);
  if (s.o !== val) {
    s.o = val;
    el.style.opacity = val;
  }
}

function setTransform(el: HTMLElement | null | undefined, v: string) {
  if (!el) return;
  const s = slot(el);
  if (s.t !== v) {
    s.t = v;
    el.style.transform = v;
  }
}

function setSvgTransform(el: SVGElement | null | undefined, v: string) {
  if (!el) return;
  const s = slot(el);
  if (s.t !== v) {
    s.t = v;
    el.setAttribute('transform', v);
  }
}

const f2 = (n: number) => n.toFixed(2);
const f3 = (n: number) => n.toFixed(3);

/** Caret blink: on for the first half of each period, with short fades. */
function blink(x: number, period: number): number {
  const ph = (((x % period) + period) % period) / period;
  return 1 - smooth(0.45, 0.55, ph) + smooth(0.93, 1, ph);
}

/* ---------- Frame ---------- */

export function renderFrame(t: number, els: SceneEls, model: DemoModel, still: boolean): void {
  /* F9 keycap: settles down, rises on release. */
  const down = easeOut(prog(t, PRESS_START, KEY_DOWN_END));
  const up = easeOut(prog(t, RELEASE_START, KEY_UP_END));
  const pressed = down * (1 - up);
  setTransform(els.keyCap, `translate3d(0, ${f3(pressed * 0.16)}em, 0)`);
  setOpacity(els.keyLed, pressed);

  /* Orb: appear → listening (amplitude) → processing (slow rotation, travelling shimmer) → idle. */
  const appear = easeOut(prog(t, ORB_IN_START, ORB_IN_END));
  const idle = easeInOut(prog(t, TYPE_GROUPS_END, SETTLE_END + 0.2));
  const proc = easeInOut(prog(t, RELEASE_START, PROCESS_BLEND_END));
  const amp = still ? 0 : amplitudeAt(t);
  const rot = 150 * easeInOut(prog(t, RELEASE_START, SETTLE_END + 0.2));
  const wavePhase = (t - RELEASE_START) * 5;

  setOpacity(els.orb, appear * (1 - 0.3 * idle));
  setTransform(els.orb, `translate3d(0, ${f2((1 - appear) * 6)}px, 0) scale(${f3(0.86 + 0.14 * appear)})`);
  setSvgTransform(els.ring, `rotate(${f2(rot)}) scale(${f3(1 + 0.06 * amp)})`);

  if (appear > 0) {
    for (let i = 0; i < DASH_COUNT; i++) {
      const el = els.dashes[i];
      if (!el) continue;
      const d = DASHES[i];
      const n = 0.5 + 0.28 * Math.sin(3 * d.rad + 6.3 * t) + 0.22 * Math.sin(5 * d.rad - 4.1 * t + 1.3);
      // Listening: dash length and radius follow the amplitude with a slow angular wobble.
      let len = 1.4 + amp * (2.6 + 3.2 * n);
      let r = RING_R + amp * 2.2 * (n - 0.5);
      let op = d.base * (0.75 + 0.25 * amp) + amp * 0.3 * n;
      // Processing: shorter, dimmer dashes with a shimmer that travels around the ring.
      if (proc > 0) {
        const wave = (0.5 + 0.5 * Math.cos(d.rad - wavePhase)) ** 2;
        len = lerp(len, 2.2, proc);
        r = lerp(r, RING_R - 1, proc);
        op = lerp(op, d.base * (0.28 + 0.72 * wave), proc);
      }
      // Idle: short, even, static.
      if (idle > 0) {
        len = lerp(len, 1.6, idle);
        r = lerp(r, RING_R, idle);
        op = lerp(op, d.base * 0.85, idle);
      }
      setSvgTransform(el, `rotate(${f2(d.deg)}) translate(0 ${f2(-r)}) scale(1 ${f2(len)})`);
      setOpacity(el, op);
    }
  }

  /* State label next to the orb. */
  const state = orbStateAt(t);
  for (const key of Object.keys(els.states) as OrbState[]) {
    setOpacity(els.states[key], key === state ? 1 : 0);
  }

  /* Spoken caption: words arrive with the speech, then the retracted word is struck through. */
  setOpacity(els.caption, 1 - 0.25 * easeInOut(prog(t, TYPE_START, TYPE_START + 0.4)));
  const strike = easeInOut(prog(t, STRIKE_START, STRIKE_END));
  model.spoken.forEach((tok, i) => {
    const el = els.spoken[i];
    const o = easeOut(prog(t, tok.start, tok.start + SPOKEN_WORD_FADE));
    setOpacity(el, tok.retracted ? o * (1 - 0.45 * strike) : o);
    setTransform(el, `translate3d(0, ${f3((1 - o) * 0.3)}em, 0)`);
  });
  setTransform(els.strike, `scaleX(${f3(strike)})`);

  /* Result: grouped word reveals at the cursor. */
  let caretAt = 0;
  model.words.forEach((_, i) => {
    const g = model.wordGroup[i];
    const s = model.groupStarts[g];
    const o = easeOut(prog(t, s, s + RESULT_GROUP_FADE));
    setOpacity(els.words[i], o);
    setTransform(els.words[i], `translate3d(0, ${f3((1 - o) * 0.35)}em, 0)`);
  });
  for (let g = 0; g < model.groupStarts.length; g++) {
    if (t >= model.groupStarts[g] + 0.06) caretAt = model.groupLastWord[g] + 1;
  }

  let caretOpacity = 1;
  if (!still && t > 0) {
    if (t < TYPE_START) caretOpacity = blink(t, 1);
    else if (t >= TYPE_GROUPS_END && t < CARET_BLINK_END) caretOpacity = blink(t - TYPE_GROUPS_END, CARET_BLINK_PERIOD);
  }
  els.carets.forEach((el, i) => setOpacity(el, i === caretAt ? caretOpacity : 0));

  /* Processed chip. */
  const chip = easeOut(prog(t, CHIP_START, CHIP_END));
  setOpacity(els.chip, chip);
  setTransform(els.chip, `translate3d(0, ${f2((1 - chip) * 6)}px, 0)`);

  setTransform(els.progress, `scaleX(${f3(clamp01(t / DURATION))})`);
}
