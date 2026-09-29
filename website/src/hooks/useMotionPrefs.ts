import { useEffect, useRef, useState, type RefObject } from 'react';

/** Shared hooks. Owned by the integrator. */

/**
 * Starts false on every first render, so the prerendered HTML and the first client render
 * agree (no hydration mismatch); the real value arrives in the effect before any animation runs.
 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

/** True when the visitor asked the OS for reduced motion. */
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}

/** True when the visitor asked for reduced data (Chromium only; false elsewhere). */
export function usePrefersReducedData(): boolean {
  return useMediaQuery('(prefers-reduced-data: reduce)');
}

/** True at widths where the desktop layout applies. */
export function useIsDesktop(minWidth = 900): boolean {
  return useMediaQuery(`(min-width: ${minWidth}px)`);
}

/** Tracks whether an element is in the viewport. */
export function useInView<T extends Element>(
  options: IntersectionObserverInit = { threshold: 0.35 },
): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  const { root, rootMargin, threshold } = options;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      root,
      rootMargin,
      threshold,
    });
    io.observe(el);
    return () => io.disconnect();
  }, [root, rootMargin, threshold]);
  return [ref, inView];
}
