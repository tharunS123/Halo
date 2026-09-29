import { why } from '../content/site';
import { ArrowIcon, MicIcon } from './icons';
import Reveal from './Reveal';
import ContextDemo from './ContextDemo';
import './WhyHalo.css';

/** Three story blocks: ready to send, wherever your cursor is, private by design. Owned by the website agent. */
export default function WhyHalo() {
  const { ready, anywhere, privacy } = why.stories;

  return (
    <section id={why.id} className="section why" aria-labelledby="why-title">
      <div className="container">
        <Reveal className="why-head">
          <p className="eyebrow">{why.eyebrow}</p>
          <h2 id="why-title" className="why-title">
            {why.title}
          </h2>
        </Reveal>

        {/* 1. Text beside example */}
        <div id={ready.id} className="why-story why-story--ready">
          <Reveal className="why-copy">
            <h3 className="why-h3">{ready.title}</h3>
            {ready.body.map((p, i) => (
              <p key={i} className="why-body">
                {p}
              </p>
            ))}
            {ready.points && (
              <ul className="why-points">
                {ready.points.map((pt) => (
                  <li key={pt}>{pt}</li>
                ))}
              </ul>
            )}
          </Reveal>

          <Reveal className="why-visual" delay={0.08}>
            <div className="why-example">
              <div className="why-spoken">
                {/* COPY: example labels */}
                <p className="why-label">
                  <MicIcon size={14} />
                  You say
                </p>
                <p className="why-spoken-text">“{ready.example.spoken}”</p>
              </div>
              <div className="why-arrow" aria-hidden="true">
                <ArrowIcon size={18} />
              </div>
              <div className="why-typed">
                <p className="why-label">Halo types</p>
                <div className="why-field">
                  <p className="why-field-text">
                    {ready.example.result}
                    <span className="why-cursor" aria-hidden="true" />
                  </p>
                </div>
              </div>
            </div>
          </Reveal>
        </div>

        {/* 2. Example beside text, reversed */}
        <div id={anywhere.id} className="why-story why-story--anywhere">
          <Reveal className="why-copy">
            <h3 className="why-h3">{anywhere.title}</h3>
            {anywhere.body.map((p, i) => (
              <p key={i} className="why-body">
                {p}
              </p>
            ))}
          </Reveal>

          <Reveal className="why-visual" delay={0.08}>
            <ContextDemo uses={anywhere.uses} />
          </Reveal>
        </div>

        {/* 3. Full-width privacy */}
        <div id={privacy.id} className="why-story why-story--privacy">
          <Reveal className="why-privacy-head">
            <h3 className="why-h3">{privacy.title}</h3>
            {privacy.body.map((p, i) => (
              <p key={i} className="why-body why-lede">
                {p}
              </p>
            ))}
          </Reveal>

          <Reveal className="why-privacy-facts" delay={0.08}>
            <dl className="why-facts">
              {privacy.facts.map((fact) => (
                <div key={fact.label} className="why-fact">
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
