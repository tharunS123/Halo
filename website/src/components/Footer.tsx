import { brand, footer, release } from '../content/site';
import './Footer.css';

/** Site footer. Owned by the website agent. */
export default function Footer() {
  return (
    <footer className="ftr">
      <div className="container ftr-inner">
        <div className="ftr-brand">
          <img className="ftr-mark" src={brand.mark} alt={brand.name} width={40} height={40} loading="lazy" />
          <p className="ftr-tagline">{footer.tagline}</p>
        </div>

        <nav className="ftr-nav" aria-label="Footer">
          <ul className="ftr-links">
            {footer.links.map((link) => (
              <li key={link.href}>
                <a className="ftr-link" href={link.href}>
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <p className="ftr-meta">
          <span>{footer.license}</span>
          <span aria-hidden="true">·</span>
          <span>{footer.compatibility}</span>
          <span aria-hidden="true">·</span>
          <span>v{release.version}</span>
        </p>
      </div>
    </footer>
  );
}
