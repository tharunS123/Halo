import { useEffect, useRef, useState, type RefObject } from 'react';

export type SceneVisibility = {
  /** Any part of the element is in the viewport. Playback pauses when this is false. */
  visible: boolean;
  /** At least half the element (or half the viewport) is covered. Autoplay waits for this. */
  prominent: boolean;
};

/**
 * Like the shared useInView, but reports two levels. An IntersectionObserver with a single
 * 0.5 threshold still fires with `isIntersecting: true` as soon as 1px enters the viewport,
 * so the ratio has to be checked explicitly for "≥50% in view".
 */
export function useSceneVisibility<T extends Element>(): [RefObject<T | null>, SceneVisibility] {
  const ref = useRef<T | null>(null);
  const [state, setState] = useState<SceneVisibility>({ visible: false, prominent: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setState({ visible: true, prominent: true });
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        const rootH = entry.rootBounds?.height ?? window.innerHeight;
        const visible = entry.isIntersecting;
        const prominent =
          visible && (entry.intersectionRatio >= 0.5 || entry.intersectionRect.height >= rootH * 0.5);
        setState((prev) =>
          prev.visible === visible && prev.prominent === prominent ? prev : { visible, prominent },
        );
      },
      { threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return [ref, state];
}
