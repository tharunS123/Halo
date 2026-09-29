import { useRef } from 'react';
import { hero } from '../content/site';
import DemoVideo, { type DemoVideoHandle } from './DemoVideo';
import HeroArtwork from './HeroArtwork';
import { PlayIcon } from './icons';
import './Hero.css';

/** Hero: headline, actions and the real demo recording. Owned by the website agent. */
export default function Hero() {
  const videoRef = useRef<DemoVideoHandle>(null);

  // Split the headline into its sentences so each sits on its own line when there is room.
  const lines = hero.headline.split(/(?<=[.!?])\s+/);

  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="container">
        {/* The entrance is a CSS animation so the headline never waits on JavaScript. */}
        <div className="hero-intro hero-enter">
          <div className="hero-heading">
            <p className="eyebrow hero-eyebrow">{hero.eyebrow}</p>
            <h1 id="hero-title" className="hero-title">
              {lines.map((line, i) => (
                <span key={i} className="hero-line">
                  {line}
                  {i < lines.length - 1 ? ' ' : ''}
                </span>
              ))}
            </h1>
          </div>

          <div className="hero-aside">
            <p className="hero-sub">{hero.subhead}</p>
            <div className="hero-actions">
              <a className="btn btn-primary" href={hero.primaryCta.href}>
                {hero.primaryCta.label}
              </a>
              <button type="button" className="btn btn-secondary" onClick={() => videoRef.current?.play()}>
                <PlayIcon size={14} />
                {hero.secondaryCta.label}
              </button>
            </div>
            <p className="hero-compat">{hero.compatibility.join(' · ')}</p>
          </div>
        </div>

        <div className="hero-media">
          <HeroArtwork />
        </div>

        <div className="hero-film">
          <div className="hero-film-intro">
            <p className="eyebrow">SEE IT IN MOTION</p>
            <p>One key. Your voice. Clean text at the cursor.</p>
          </div>
          <DemoVideo ref={videoRef} />
        </div>
      </div>
    </section>
  );
}
