import { Fragment, type ReactNode } from 'react';

/**
 * Renders a copy string from site.ts, turning `backtick` segments into <code>.
 * Owned by the website agent.
 */
export function renderInline(text: string): ReactNode[] {
  return text
    .split('`')
    .map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : <Fragment key={i}>{part}</Fragment>));
}
