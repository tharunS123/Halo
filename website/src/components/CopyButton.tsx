import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { CheckIcon, CopyIcon } from './icons';
import './CopyButton.css';

type State = 'idle' | 'copied' | 'failed';

async function copyText(text: string, returnFocus: HTMLElement | null): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path.
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.setAttribute('aria-hidden', 'true');
    Object.assign(ta.style, { position: 'fixed', top: '0', left: '0', opacity: '0', pointerEvents: 'none' });
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    returnFocus?.focus({ preventScroll: true });
    return ok;
  } catch {
    return false;
  }
}

/**
 * Copies `text` and confirms for ~2 s, announced through a polite live region.
 * `label` is the accessible name and should say what gets copied.
 * With `children`, the button also shows a visible text label. Owned by the website agent.
 */
export default function CopyButton({
  text,
  label,
  children,
  className = '',
}: {
  text: string;
  label: string;
  children?: ReactNode;
  className?: string;
}) {
  const [state, setState] = useState<State>('idle');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const onClick = async (e: MouseEvent<HTMLButtonElement>) => {
    const button = e.currentTarget;
    const ok = await copyText(text, button);
    setState(ok ? 'copied' : 'failed');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState('idle'), ok ? 2000 : 4000);
  };

  const hasText = children !== undefined;

  return (
    <>
      <button
        type="button"
        className={`copy-btn ${hasText ? 'copy-btn--text' : 'copy-btn--icon'} ${className}`.trim()}
        data-state={state}
        aria-label={label}
        onClick={onClick}
      >
        {state === 'copied' ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
        {/* COPY: "Copied" confirmation */}
        {hasText && <span className="copy-btn-text">{state === 'copied' ? 'Copied' : children}</span>}
      </button>
      <span className="visually-hidden" role="status">
        {/* COPY: live-region announcements */}
        {state === 'copied' ? 'Copied to clipboard' : state === 'failed' ? 'Couldn’t copy. Select the text to copy it.' : ''}
      </span>
    </>
  );
}
