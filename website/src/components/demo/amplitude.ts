import { LISTEN_END, LISTEN_START } from './timeline';

/**
 * Predetermined speech amplitude (0–1) for the illustration, sampled at 20 Hz from
 * LISTEN_START (0.5 s) to LISTEN_END (2.7 s). Hand-authored to follow the syllables of
 * "Can we meet Thursday— … actually Friday at three?", with a near-silent gap for the pause
 * before the correction. It is data, not a recording, and the page never touches the microphone.
 */
export const AMPLITUDE_RATE = 20;

export const AMPLITUDE_TRACK: readonly number[] = [
  // 0.50–0.55 s: breath in
  0.02, 0.05,
  // 0.60–1.50 s: "Can we meet Thurs-day"
  0.35, 0.62, 0.48, 0.3, 0.58, 0.44, 0.28, 0.66, 0.72, 0.5, 0.34, 0.7, 0.82, 0.6, 0.52, 0.74, 0.55, 0.32, 0.16,
  // 1.55–1.90 s: pause
  0.08, 0.05, 0.04, 0.03, 0.04, 0.03, 0.05, 0.12,
  // 1.95–2.60 s: "ac-tu-al-ly Fri-day at three"
  0.46, 0.7, 0.52, 0.64, 0.4, 0.3, 0.78, 0.86, 0.58, 0.42, 0.6, 0.36, 0.72, 0.64,
  // 2.65–2.70 s: tail
  0.3, 0,
];

/** Smoothly interpolated amplitude at time `t` (seconds on the demo clock). */
export function amplitudeAt(t: number): number {
  if (t <= LISTEN_START || t >= LISTEN_END) return 0;
  const x = (t - LISTEN_START) * AMPLITUDE_RATE;
  const i = Math.floor(x);
  const f = x - i;
  const a = AMPLITUDE_TRACK[i] ?? 0;
  const b = AMPLITUDE_TRACK[i + 1] ?? 0;
  const s = (1 - Math.cos(f * Math.PI)) / 2;
  return a + (b - a) * s;
}
