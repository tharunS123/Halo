import { useEffect, useRef, useState } from 'react';
import { brand, nav } from '../content/site';
import { CloseIcon, ExternalIcon, MenuIcon } from './icons';
import './Header.css';

const DESKTOP_QUERY = '(min-width: 880px)';

/** Sticky site header with a disclosure menu on narrow screens. Owned by the website agent. */
export default function Header() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Show the hairline border only once the page has scrolled.
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      setScrolled(window.scrollY > 8);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  // While the menu is open: Escape closes it and returns focus; a click outside closes it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open]);

  // Reaching the desktop layout closes the mobile menu.
  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => {
      if (mql.matches) setOpen(false);
    };
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const close = () => setOpen(false);

  return (
    <header ref={headerRef} className="hdr" data-scrolled={scrolled || open ? 'true' : 'false'}>
      <div className="container hdr-inner">
        <a className="hdr-home" href="#top" onClick={close}>
          <img src={brand.wordmark} alt={`${brand.name} home`} width={716} height={240} />
        </a>

        <nav className="hdr-nav" aria-label="Main">
          <button
            ref={buttonRef}
            type="button"
            className="hdr-menu-btn"
            aria-expanded={open}
            aria-controls="hdr-panel"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
            {/* COPY: menu button name */}
            <span className="visually-hidden">Menu</span>
          </button>

          <div id="hdr-panel" className="hdr-panel" data-open={open ? 'true' : 'false'}>
            <ul className="hdr-links">
              {nav.items.map((item) => (
                <li key={item.href}>
                  <a
                    className="hdr-link"
                    href={item.href}
                    onClick={close}
                    {...(item.external ? { rel: 'noopener' } : {})}
                  >
                    {item.label}
                    {item.external && <ExternalIcon size={13} className="hdr-ext" />}
                  </a>
                </li>
              ))}
            </ul>
            <a className="btn btn-primary hdr-panel-cta" href={nav.cta.href} onClick={close}>
              {nav.cta.label}
            </a>
          </div>
        </nav>

        <a className="btn btn-primary btn-sm hdr-cta" href={nav.cta.href} onClick={close}>
          {nav.cta.label}
        </a>
      </div>
    </header>
  );
}
