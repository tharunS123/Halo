import {
  RESULT_GROUP_FADE,
  SPOKEN_AFTER_END,
  SPOKEN_AFTER_START,
  SPOKEN_BEFORE_END,
  SPOKEN_BEFORE_START,
  SPOKEN_WORD_FADE,
  TYPE_GROUPS_END,
  TYPE_START,
} from './timeline';

/** One word of the spoken caption, with its reveal time. */
export type SpokenToken = {
  /** Text shown, including any opening/closing quote. */
  text: string;
  start: number;
  /** Set on the word the speaker takes back ("Thursday"). */
  retracted?: { lead: string; core: string; trail: string };
};

export type DemoModel = {
  spoken: SpokenToken[];
  words: string[];
  /** Start time of each 2–3 word group. */
  groupStarts: number[];
  /** Index (into `words`) of the last word of each group. */
  groupLastWord: number[];
  /** Group index for each word. */
  wordGroup: number[];
};

const splitWords = (s: string): string[] => s.trim().split(/\s+/).filter(Boolean);

/** Spread word start times across [from, to], weighted by word length. */
function timeWords(words: string[], from: number, to: number): number[] {
  const weights = words.map((w) => Math.max(2, w.length));
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  const span = Math.max(0, to - from - SPOKEN_WORD_FADE);
  let acc = 0;
  return weights.map((w) => {
    const start = from + (span * acc) / total;
    acc += w;
    return start;
  });
}

/** Group words in pairs; a trailing single word joins the previous group (so groups are 2–3 words). */
function groupWords(count: number): number[] {
  const groups: number[] = [];
  for (let i = 0; i < count; i++) groups.push(Math.floor(i / 2));
  if (count >= 3 && count % 2 === 1) groups[count - 1] = groups[count - 2];
  return groups;
}

export function buildModel(spoken: { before: string; after: string }, result: string): DemoModel {
  const before = splitWords(spoken.before);
  const after = splitWords(spoken.after);
  const beforeStarts = timeWords(before, SPOKEN_BEFORE_START, SPOKEN_BEFORE_END);
  const afterStarts = timeWords(after, SPOKEN_AFTER_START, SPOKEN_AFTER_END);

  const tokens: SpokenToken[] = [
    ...before.map((text, i) => ({ text, start: beforeStarts[i] })),
    ...after.map((text, i) => ({ text, start: afterStarts[i] })),
  ];
  if (tokens.length > 0) {
    tokens[0] = { ...tokens[0], text: `“${tokens[0].text}` };
    const last = tokens.length - 1;
    tokens[last] = { ...tokens[last], text: `${tokens[last].text}”` };
  }
  // The last word before the pause is the one the speaker corrects.
  if (before.length > 0 && after.length > 0) {
    const idx = before.length - 1;
    const m = /^([\p{Ps}\p{Pi}"']*)(.*?)([\p{P}\p{S}]*)$/u.exec(tokens[idx].text);
    const lead = m?.[1] ?? '';
    const core = m?.[2] || tokens[idx].text;
    const trail = m?.[2] ? (m?.[3] ?? '') : '';
    tokens[idx] = { ...tokens[idx], retracted: { lead: m?.[2] ? lead : '', core, trail } };
  }

  const words = splitWords(result);
  const wordGroup = groupWords(words.length);
  const groupCount = words.length ? wordGroup[words.length - 1] + 1 : 0;
  const gap = groupCount > 1 ? Math.max(0, TYPE_GROUPS_END - RESULT_GROUP_FADE - TYPE_START) / (groupCount - 1) : 0;
  const groupStarts = Array.from({ length: groupCount }, (_, g) => TYPE_START + g * gap);
  const groupLastWord = Array.from({ length: groupCount }, (_, g) => wordGroup.lastIndexOf(g));

  return { spoken: tokens, words, groupStarts, groupLastWord, wordGroup };
}
