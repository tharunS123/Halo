import { install } from '../content/site';
import CopyButton from './CopyButton';
import { ArrowIcon, DownloadIcon, GithubIcon } from './icons';
import Reveal from './Reveal';
import { renderInline } from './RichText';
import './Install.css';

/** Standalone Mac app first, with Homebrew as an optional install path. */
export default function Install() {
  const { dmg } = install;

  return (
    <section id={install.id} className="section inst" aria-labelledby="inst-title">
      <div className="container inst-grid">
        <Reveal className="inst-intro">
          <p className="eyebrow">{install.eyebrow}</p>
          <h2 id="inst-title" className="inst-title">
            {install.title}
          </h2>
          <p className="inst-lede">{install.intro}</p>

          <div className="inst-dmg" aria-labelledby="inst-dmg-title" role="group">
            <h3 id="inst-dmg-title" className="inst-dmg-title">
              {dmg.title}
            </h3>
            <p className="inst-dmg-body">{renderInline(dmg.body)}</p>
            <a className="btn btn-primary inst-dmg-btn" href={dmg.href}>
              <DownloadIcon size={18} />
              {dmg.label}
            </a>
            <p className="inst-dmg-caveat">{renderInline(dmg.caveat)}</p>
          </div>

          {/* COPY: requirements heading */}
          <h3 className="inst-subhead">Requirements</h3>
          <ul className="inst-reqs">
            {install.requirements.map((req) => (
              <li key={req}>{req}</li>
            ))}
          </ul>
        </Reveal>

        <Reveal className="inst-main" delay={0.08}>
          <h3 className="inst-homebrew-title">{install.homebrewTitle}</h3>
          <p className="inst-homebrew-intro">{install.homebrewIntro}</p>
          <div className="inst-term" role="group" aria-labelledby="inst-term-title">
            <div className="inst-term-bar">
              <span className="inst-term-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
              {/* COPY: terminal window title (also the group's accessible name) */}
              <span id="inst-term-title" className="inst-term-title">
                Install commands
              </span>
              <CopyButton text={install.commands.join('\n')} label="Copy all install commands">
                {/* COPY: visible copy-all label */}
                Copy all
              </CopyButton>
            </div>
            <ol className="inst-cmds">
              {install.commands.map((cmd) => (
                <li key={cmd} className="inst-cmd">
                  <span className="inst-prompt" aria-hidden="true">
                    $
                  </span>
                  <code className="inst-code">{cmd}</code>
                  {/* COPY: per-command accessible name */}
                  <CopyButton text={cmd} label={`Copy command: ${cmd}`} />
                </li>
              ))}
            </ol>
          </div>

          <div className="inst-notes">
            <p>{renderInline(install.trustNote)}</p>
            <p>{renderInline(install.setupNote)}</p>
          </div>

          <ul className="inst-links">
            <li>
              <a className="inst-link" href={install.newToHomebrew.href}>
                {install.newToHomebrew.label}
                <ArrowIcon size={14} className="inst-link-trail" />
              </a>
            </li>
            <li>
              <a className="inst-link" href={install.source.href}>
                <GithubIcon size={15} className="inst-link-lead" />
                {install.source.label}
              </a>
            </li>
          </ul>

        </Reveal>
      </div>
    </section>
  );
}
