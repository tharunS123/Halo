import { useState } from 'react';
import { AnimatePresence } from 'motion/react';
import * as m from 'motion/react-m';
import { usePrefersReducedMotion } from '../hooks/useMotionPrefs';
import './ContextDemo.css';

type Use = { app: string; spoken?: string; text: string };

/** Interactive, verified per-app examples without impersonating another app's interface. */
export default function ContextDemo({ uses }: { uses: Use[] }) {
  const [selected, setSelected] = useState(0);
  const reduced = usePrefersReducedMotion();
  const example = uses[selected];
  const code = example.app === 'Editor' || example.app === 'Terminal';

  return (
    <div className="ctx" aria-label="Halo output examples by app">
      <div className="ctx-apps" role="group" aria-label="Choose an app example">
        {uses.map((item, index) => (
          <button
            key={item.app}
            type="button"
            className="ctx-app"
            aria-pressed={selected === index}
            onClick={() => setSelected(index)}
          >
            <span className="ctx-app-dot" aria-hidden="true" />
            {item.app}
          </button>
        ))}
      </div>

      <div className="ctx-output" aria-live="polite" aria-atomic="true">
        <div className="ctx-output-top">
          <span>HALO / {example.app.toUpperCase()}</span>
          <span>EXAMPLE OUTPUT</span>
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <m.div
            key={example.app}
            className="ctx-content"
            initial={{ opacity: 0, y: reduced ? 0 : 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: reduced ? 0 : -10 }}
            transition={{ duration: reduced ? 0.12 : 0.36, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="ctx-kicker">You say</p>
            <p className="ctx-spoken">“{example.spoken ?? example.text}”</p>
            <div className="ctx-rule" aria-hidden="true"><span /></div>
            <p className="ctx-kicker">Halo types</p>
            <p className={`ctx-result${code ? ' ctx-result--code' : ''}`}>{example.text}</p>
          </m.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
