import { useState } from 'react';
import { AnimatePresence } from 'motion/react';
import * as m from 'motion/react-m';
import { usePrefersReducedMotion } from '../hooks/useMotionPrefs';
import DesignCrop, { ORB_CROP, SETTINGS_CROP, SETUP_CROP } from './DesignCrop';
import Reveal from './Reveal';
import './InterfaceShowcase.css';

const screens = [
  {
    key: 'dictation',
    tab: 'Dictation',
    eyebrow: 'EVERYDAY / DICTATION',
    title: 'Everything starts with one key.',
    body: 'The shortcut, cleanup level and languages sit together in a focused native settings window.',
    file: '01-night-settings.png',
    crop: SETTINGS_CROP,
    alt: 'Approved Night design of Halo Dictation settings with F9 shortcut and Normal cleanup',
  },
  {
    key: 'light',
    tab: 'Light mode',
    eyebrow: 'THE SAME INTERFACE / CHALK',
    title: 'At home in light and dark.',
    body: 'The same native controls in Halo’s Chalk appearance, with Imperial red reserved for actions and selection.',
    file: '02-chalk-settings.png',
    crop: SETTINGS_CROP,
    alt: 'Approved Chalk design of Halo Dictation settings',
  },
  {
    key: 'setup',
    tab: 'Setup',
    eyebrow: 'FIRST RUN / ACCESS',
    title: 'A clear path to your first dictation.',
    body: 'Setup walks through permissions, microphone, speech model and a real test dictation.',
    file: '04-onboarding-components.png',
    crop: SETUP_CROP,
    alt: 'Approved Halo onboarding design with microphone permission and setup progress',
  },
  {
    key: 'orb',
    tab: 'Voice orb',
    eyebrow: 'THE ORIGINAL / DOTTED ORB',
    title: 'A quiet signal that hears you.',
    body: 'Halo’s original grayscale dot geometry responds to your voice. The Imperial glow lives around its boundary.',
    file: '03-original-orb-plus-beam.png',
    crop: ORB_CROP,
    alt: 'Snapshot of the original Halo dotted orb from the approved visual design',
  },
] as const;

/** Interactive tour using the actual approved Halo design boards. */
export default function InterfaceShowcase() {
  const [selected, setSelected] = useState(0);
  const reduced = usePrefersReducedMotion();
  const current = screens[selected];

  return (
    <section className="section iface" aria-labelledby="iface-title">
      <div className="container">
        <Reveal className="iface-heading">
          <p className="eyebrow">THE HALO INTERFACE</p>
          <h2 id="iface-title">Made to feel at home on your Mac.</h2>
          <p>Explore the interface design behind the shortcut.</p>
        </Reveal>

        <div className="iface-shell">
          <div className="iface-copy">
            <div className="iface-switch" role="group" aria-label="Interface design previews">
              {screens.map((screen, index) => (
                <button
                  key={screen.key}
                  type="button"
                  className="iface-option"
                  aria-pressed={index === selected}
                  onClick={() => setSelected(index)}
                >
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  {screen.tab}
                </button>
              ))}
            </div>
            <div className="iface-description" aria-live="polite" aria-atomic="true">
              <p className="eyebrow">{current.eyebrow}</p>
              <h3>{current.title}</h3>
              <p>{current.body}</p>
            </div>
          </div>

          <div className={`iface-stage iface-stage--${current.key}`}>
            <div className="iface-stage-top">
              <span>HALO / DESIGN PREVIEW</span>
              <span>{String(selected + 1).padStart(2, '0')} / {String(screens.length).padStart(2, '0')}</span>
            </div>
            <AnimatePresence mode="wait" initial={false}>
              <m.div
                key={current.key}
                className="iface-frame"
                initial={{ opacity: 0, y: reduced ? 0 : 18, scale: reduced ? 1 : 0.985 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: reduced ? 0 : -12, scale: reduced ? 1 : 0.985 }}
                transition={{ duration: reduced ? 0.12 : 0.42, ease: [0.22, 1, 0.36, 1] }}
              >
                <DesignCrop file={current.file} crop={current.crop} label={current.alt} />
              </m.div>
            </AnimatePresence>
            <p>Approved design preview. Status values shown are illustrative.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
