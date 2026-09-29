/**
 * "From thought to text" timeline. All times are seconds from the start of the sequence.
 * Every visual in the scene is derived from a single clock value `t` in [0, DURATION],
 * so the sequence is deterministic and seekable (pause, resume, reduced-motion snapshots).
 *
 * Storyboard (HALO-WEBSITE-CLAUDE-PROMPT.md §3):
 *   0.0–0.5  F9 settles down, orb fades and scales in           → step "Hold F9"
 *   0.5–2.7  orb follows a predetermined amplitude track,
 *            spoken caption with a pause before the correction  → step "Speak"
 *   2.7–3.2  F9 rises, orb switches to its processing state     → step "Release"
 *   3.2–4.4  result appears at the cursor in 2–3 word groups,
 *            cursor settles and blinks
 *   4.4–5.5  "Processed on your Mac" chip, scene rests (no auto loop)
 */

export const DURATION = 5.5;

/* Hold F9 */
export const PRESS_START = 0.02;
export const KEY_DOWN_END = 0.3;
export const ORB_IN_START = 0.05;
export const ORB_IN_END = 0.45;
export const HOLD_END = 0.5;

/* Speak */
export const LISTEN_START = 0.5;
export const SPOKEN_BEFORE_START = 0.6;
export const SPOKEN_BEFORE_END = 1.5;
/** Silence between `spoken.before` and `spoken.after` (the self-correction pause). */
export const SPOKEN_AFTER_START = 1.95;
export const SPOKEN_AFTER_END = 2.55;
/** The retracted word is struck through as the correction arrives. */
export const STRIKE_START = SPOKEN_AFTER_START + 0.2;
export const STRIKE_END = STRIKE_START + 0.35;
export const LISTEN_END = 2.7;

/* Release */
export const RELEASE_START = LISTEN_END;
export const KEY_UP_END = 2.95;
/** Listening → processing crossfade of the orb. */
export const PROCESS_BLEND_END = 3.0;
export const TYPE_START = 3.2;
/** Last word group has started fading in by this point. */
export const TYPE_GROUPS_END = 4.0;
/** Orb eases from processing to idle; cursor settles. */
export const SETTLE_END = 4.4;
export const CARET_BLINK_PERIOD = 0.7;
export const CARET_BLINK_END = TYPE_GROUPS_END + CARET_BLINK_PERIOD * 2;
export const CHIP_START = 4.4;
export const CHIP_END = 4.8;

/* Per-element fades */
export const SPOKEN_WORD_FADE = 0.22;
export const RESULT_GROUP_FADE = 0.3;

export type Phase = 'ready' | 'hold' | 'speak' | 'release' | 'done';

export function phaseAt(t: number): Phase {
  if (t <= 0) return 'ready';
  if (t < HOLD_END) return 'hold';
  if (t < LISTEN_END) return 'speak';
  if (t < DURATION) return 'release';
  return 'done';
}

/** Index into `demo.steps` for a phase: -1 before start, 3 when every step is complete. */
export function stepIndexFor(phase: Phase): number {
  switch (phase) {
    case 'hold':
      return 0;
    case 'speak':
      return 1;
    case 'release':
      return 2;
    case 'done':
      return 3;
    default:
      return -1;
  }
}

/**
 * Reduced motion: the "Step through" button shows these still frames instead of playing.
 * 1 = F9 held, orb present. 2 = full spoken phrase with the correction marked. 3 = end state.
 */
export const REDUCED_STEP_TIMES = [0.45, 2.68, DURATION] as const;

export type OrbState = 'idle' | 'listening' | 'processing' | 'done';

export function orbStateAt(t: number): OrbState {
  if (t <= 0) return 'idle';
  if (t < LISTEN_END) return 'listening';
  if (t < TYPE_GROUPS_END) return 'processing';
  return 'done';
}
