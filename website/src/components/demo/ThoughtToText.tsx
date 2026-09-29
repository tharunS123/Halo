import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { demo } from '../../content/site';
import { usePrefersReducedMotion } from '../../hooks/useMotionPrefs';
import DesignCrop, { ORB_CROP } from '../DesignCrop';
import { createSceneEls, renderFrame } from './frame';
import { buildModel } from './model';
import { DURATION, REDUCED_STEP_TIMES, phaseAt, stepIndexFor, type OrbState, type Phase } from './timeline';
import { useSceneVisibility } from './useSceneVisibility';
import './ThoughtToText.css';

type Intent = 'idle' | 'play' | 'pause';
type StepStatus = 'idle' | 'upcoming' | 'active' | 'complete';

const ORB_STATES: OrbState[] = ['idle', 'listening', 'processing', 'done'];

/**
 * "From thought to text": a web-only illustration of Hold F9 → Speak → Release.
 * Renders its own <section>. No props. All copy comes from `demo` in content/site.ts.
 */
export default function ThoughtToText() {
  const reduced = usePrefersReducedMotion();
  const model = useMemo(() => buildModel(demo.spoken, demo.result), []);

  const els = useRef(createSceneEls());
  const tRef = useRef(reduced ? DURATION : 0);
  const phaseRef = useRef<Phase>(phaseAt(tRef.current));
  const [phase, setPhase] = useState<Phase>(phaseRef.current);
  const [intent, setIntent] = useState<Intent>('idle');
  const [docHidden, setDocHidden] = useState(() => typeof document !== 'undefined' && document.hidden);
  const [rmStep, setRmStep] = useState(3);
  const [announcement, setAnnouncement] = useState('');
  const autoStarted = useRef(false);
  const userInitiated = useRef(false);
  const [stageRef, { visible, prominent }] = useSceneVisibility<HTMLDivElement>();

  const apply = useCallback((t: number) => renderFrame(t, els.current, model, reduced), [model, reduced]);

  /** Jump the single clock to `t` and bring every derived value along. */
  const seek = useCallback(
    (t: number) => {
      tRef.current = t;
      apply(t);
      const p = phaseAt(t);
      if (p !== phaseRef.current) {
        phaseRef.current = p;
        setPhase(p);
      }
    },
    [apply],
  );

  // Paint the current frame before the browser does (mount, and if the renderer changes).
  useLayoutEffect(() => {
    apply(tRef.current);
  }, [apply]);

  // Reduced motion switched on mid-session: show the end state and stop.
  const prevReduced = useRef(reduced);
  useEffect(() => {
    if (prevReduced.current === reduced) return;
    prevReduced.current = reduced;
    if (reduced) {
      seek(DURATION);
      setIntent('pause');
      setRmStep(3);
    }
  }, [reduced, seek]);

  // Pause while the tab is hidden.
  useEffect(() => {
    const onChange = () => setDocHidden(document.hidden);
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  // Autoplay once, the first time at least half the scene is in view.
  useEffect(() => {
    if (!prominent || reduced || autoStarted.current) return;
    autoStarted.current = true;
    if (phaseRef.current !== 'done') setIntent('play');
  }, [prominent, reduced]);

  const running = intent === 'play' && phase !== 'done' && visible && !docHidden && !reduced;

  // The clock. Runs only while playing, visible and unfinished; otherwise no rAF work at all.
  useEffect(() => {
    if (!running) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, Math.max(0, (now - last) / 1000));
      last = now;
      const t = Math.min(DURATION, tRef.current + dt);
      seek(t);
      if (t < DURATION) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [running, seek]);

  // Announce phase changes politely, once per phase, and only after the visitor started playback.
  useEffect(() => {
    if (!userInitiated.current) return;
    const i = stepIndexFor(phase);
    const n = demo.steps.length;
    if (phase === 'done') setAnnouncement(`Result: ${demo.result} ${demo.processedLabel}.`);
    else if (phase === 'speak') setAnnouncement(`Step ${i + 1} of ${n}, ${demo.steps[i]?.label}: ${demo.spoken.full}`);
    else if (i >= 0 && demo.steps[i]) setAnnouncement(`Step ${i + 1} of ${n}, ${demo.steps[i].label}. ${demo.steps[i].detail}`);
  }, [phase]);

  const replay = () => {
    userInitiated.current = true;
    autoStarted.current = true;
    seek(0);
    setIntent('play');
  };

  const toggle = () => {
    if (phase === 'done') return replay();
    userInitiated.current = true;
    autoStarted.current = true;
    setIntent((i) => (i === 'play' ? 'pause' : 'play'));
  };

  const stepThrough = () => {
    userInitiated.current = true;
    const next = (rmStep % REDUCED_STEP_TIMES.length) + 1;
    setRmStep(next);
    seek(REDUCED_STEP_TIMES[next - 1]);
  };

  const isPlaying = intent === 'play' && phase !== 'done';
  const active = stepIndexFor(phase);
  const statusFor = (i: number): StepStatus =>
    phase === 'ready' ? 'idle' : i < active ? 'complete' : i === active ? 'active' : 'upcoming';

  const titleId = `${demo.id}-title`;
  const nextRmStep = (rmStep % REDUCED_STEP_TIMES.length) + 1;
  const nextRmLabel = demo.steps[nextRmStep - 1]?.label ?? '';

  return (
    <section id={demo.id} className="section ttt" aria-labelledby={titleId}>
      <div className="container ttt-layout">
        <header className="ttt-head">
          <p className="eyebrow">{demo.eyebrow}</p>
          <h2 id={titleId} className="ttt-title">
            {demo.title}
          </h2>
          <p className="ttt-intro">{demo.intro}</p>
        </header>

        <div className="ttt-aside">
          <ol className="ttt-steps">
            {demo.steps.map((step, i) => {
              const status = statusFor(i);
              return (
                <li
                  key={step.key}
                  className="ttt-step"
                  data-status={status}
                  aria-current={status === 'active' ? 'step' : undefined}
                >
                  <span className="ttt-step-num" aria-hidden="true">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="ttt-step-text">
                    <span className="ttt-step-label">{step.label}</span>
                    <span className="ttt-step-detail">{step.detail}</span>
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="ttt-note">{demo.resultNote}</p>
        </div>

        <div className="ttt-stage" ref={stageRef}>
          <div className="ttt-scene" aria-hidden="true">
            <div className="ttt-scene-inner">
              <div className="ttt-window">
                <div className="ttt-titlebar">
                  <span className="ttt-lights">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="ttt-window-title">{demo.windowTitle}</span>
                  <span />
                </div>
                <div className="ttt-to">
                  <span className="ttt-to-label">To:</span>
                  <span className="ttt-recipient">{demo.recipient}</span>
                </div>
                <div className="ttt-compose">
                  <p className="ttt-result">
                    <span className="ttt-caret-start">
                      <span className="ttt-caret" ref={(el) => void (els.current.carets[0] = el)} />
                    </span>
                    {model.words.map((word, i) => (
                      <span key={i}>
                        <span className="ttt-word" ref={(el) => void (els.current.words[i] = el)}>
                          {word}
                          <span className="ttt-caret" ref={(el) => void (els.current.carets[i + 1] = el)} />
                        </span>
                        {i < model.words.length - 1 ? ' ' : null}
                      </span>
                    ))}
                  </p>
                </div>
              </div>

              <p className="ttt-caption" ref={(el) => void (els.current.caption = el)}>
                {model.spoken.map((tok, i) => (
                  <span key={i}>
                    <span className="ttt-spoken" ref={(el) => void (els.current.spoken[i] = el)}>
                      {tok.retracted ? (
                        <>
                          {tok.retracted.lead}
                          <span className="ttt-retracted">
                            {tok.retracted.core}
                            <span className="ttt-strike" ref={(el) => void (els.current.strike = el)} />
                          </span>
                          {tok.retracted.trail ? <span className="ttt-trail">{tok.retracted.trail}</span> : null}
                        </>
                      ) : (
                        tok.text
                      )}
                    </span>
                    {i < model.spoken.length - 1 ? ' ' : null}
                  </span>
                ))}
              </p>

              <div className="ttt-dock">
                <div className="ttt-key">
                  <span className="ttt-key-base" />
                  <span className="ttt-key-cap" ref={(el) => void (els.current.keyCap = el)}>
                    <span className="ttt-key-label">F9</span>
                    <span className="ttt-key-led" ref={(el) => void (els.current.keyLed = el)} />
                  </span>
                </div>

                <div className="ttt-orb" ref={(el) => void (els.current.orb = el)}>
                  <DesignCrop
                    file="03-original-orb-plus-beam.png"
                    crop={ORB_CROP}
                    label="Halo's original dotted orb, illustrated from the approved interface design"
                  />
                </div>

                <div className="ttt-state">
                  {ORB_STATES.map((key) => (
                    <span key={key} ref={(el) => void (els.current.states[key] = el)}>
                      {demo.stateLabels[key]}
                    </span>
                  ))}
                </div>
              </div>

              <div className="ttt-chip" ref={(el) => void (els.current.chip = el)}>
                <svg viewBox="0 0 16 16" width="14" height="14" focusable="false">
                  <circle cx="8" cy="8" r="6.5" />
                  <path d="M5.2 8.2 7.1 10l3.7-4" />
                </svg>
                <span>{demo.processedLabel}</span>
              </div>
            </div>
            <div className="ttt-progress">
              <span ref={(el) => void (els.current.progress = el)} />
            </div>
          </div>

          <p className="visually-hidden">
            Spoken: {demo.spoken.full} Result: {demo.result}
          </p>

          <div className="ttt-bar">
            <p className="ttt-disclaimer">{demo.disclaimer}</p>
            <div className="ttt-controls" role="group" aria-label="Demo playback">
              {reduced ? (
                <button
                  type="button"
                  className="btn btn-secondary ttt-btn"
                  onClick={stepThrough}
                  aria-label={`Show step ${nextRmStep} of ${REDUCED_STEP_TIMES.length}: ${nextRmLabel}`}
                >
                  <StepIcon />
                  <span>Show step {nextRmStep}</span>
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn btn-secondary ttt-btn ttt-btn-toggle"
                    onClick={toggle}
                    aria-label={isPlaying ? 'Pause demo' : 'Play demo'}
                  >
                    {isPlaying ? <PauseIcon /> : <PlayIcon />}
                    <span>{isPlaying ? 'Pause' : 'Play'}</span>
                  </button>
                  <button type="button" className="btn btn-ghost ttt-btn" onClick={replay} aria-label="Replay demo">
                    <ReplayIcon />
                    <span>Replay</span>
                  </button>
                </>
              )}
            </div>
          </div>

          <p className="visually-hidden" aria-live="polite" aria-atomic="true">
            {announcement}
          </p>
        </div>
      </div>
    </section>
  );
}

function PlayIcon() {
  return (
    <svg className="ttt-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M5 3.5v9l7.5-4.5z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg className="ttt-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <rect x="4" y="3.5" width="2.6" height="9" rx="0.6" fill="currentColor" />
      <rect x="9.4" y="3.5" width="2.6" height="9" rx="0.6" fill="currentColor" />
    </svg>
  );
}

function ReplayIcon() {
  return (
    <svg className="ttt-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M3.2 8a4.8 4.8 0 1 0 1.5-3.5M3.2 2.6v2.6h2.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function StepIcon() {
  return (
    <svg className="ttt-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M4 3.5 8.5 8 4 12.5M9 3.5 13.5 8 9 12.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
