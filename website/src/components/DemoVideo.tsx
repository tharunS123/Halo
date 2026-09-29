import { useEffect, useId, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { flushSync } from 'react-dom';
import { media } from '../content/site';
import { usePrefersReducedMotion } from '../hooks/useMotionPrefs';
import { PlayIcon } from './icons';
import './DemoVideo.css';

export type DemoVideoHandle = {
  /** Scroll the demo into view if needed, load it, play it, and move focus to it. */
  play: () => void;
};

/**
 * The demo video. Shows only the poster until the visitor asks to play:
 * no <video src> exists (and nothing is fetched) before the first click.
 * Owned by the website agent.
 */
export default function DemoVideo({ ref }: { ref?: Ref<DemoVideoHandle> }) {
  const [active, setActive] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [src, setSrc] = useState(media.demoVideo);
  const frameRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const reduced = usePrefersReducedMotion();
  const descId = useId();

  // Runs inside the click handler so the browser sees a user gesture (needed for sound).
  const start = () => {
    if (!active) {
      // Small screens and reduced-data visitors get the 720p encode (0.9 MB instead of 2.9 MB).
      const small =
        media.demoVideoSmall && window.matchMedia('(max-width: 720px), (prefers-reduced-data: reduce)').matches;
      flushSync(() => {
        if (small) setSrc(media.demoVideoSmall);
        setActive(true);
      });
    }
    const video = videoRef.current;
    if (!video) return;
    video.focus({ preventScroll: true });
    setBlocked(false);
    const attempt = video.play();
    if (attempt !== undefined) {
      attempt.catch((err: unknown) => {
        // AbortError just means a pause interrupted loading; anything else was a refusal.
        if (!(err instanceof DOMException && err.name === 'AbortError')) setBlocked(true);
      });
    }
  };

  useImperativeHandle(ref, () => ({
    play() {
      const frame = frameRef.current;
      if (frame) {
        const rect = frame.getBoundingClientRect();
        const headerH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--header-h')) || 64;
        const fullyVisible = rect.top >= headerH && rect.bottom <= window.innerHeight;
        if (!fullyVisible) frame.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
      }
      start();
    },
  }));

  // Pause once the video has been on screen and then leaves it entirely.
  useEffect(() => {
    const frame = frameRef.current;
    if (!active || !frame || typeof IntersectionObserver === 'undefined') return;
    let wasVisible = false;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          wasVisible = true;
        } else if (wasVisible) {
          videoRef.current?.pause();
        }
      },
      { threshold: 0 },
    );
    io.observe(frame);
    return () => io.disconnect();
  }, [active]);

  // COPY: play button label, built from media.demoDurationLabel
  const playLabel = `Play ${media.demoDurationLabel}`;

  return (
    <figure className="vid">
      <div ref={frameRef} className="vid-frame">
        {active ? (
          <video
            ref={videoRef}
            className="vid-media"
            src={src}
            poster={media.demoPoster}
            controls
            playsInline
            preload="none"
            width={1920}
            height={1080}
            aria-label={media.demoVideoLabel}
            aria-describedby={descId}
            onPlay={() => setBlocked(false)}
          >
            {media.captions && (
              // COPY: caption track label
              <track kind="captions" src={media.captions} srcLang="en" label="English" default />
            )}
          </video>
        ) : (
          <>
            <img
              className="vid-media"
              src={media.demoPoster}
              alt={media.demoPosterAlt}
              width={1920}
              height={1080}
              decoding="async"
              fetchPriority="high"
            />
            <button type="button" className="vid-play" onClick={start} aria-describedby={descId}>
              <span className="vid-play-pill">
                <span className="vid-play-icon">
                  <PlayIcon size={18} />
                </span>
                <span className="vid-play-text">{playLabel}</span>
              </span>
            </button>
          </>
        )}
      </div>

      <figcaption className="vid-caption">
        <span className="vid-label">
          <span className="vid-dot" aria-hidden="true" />
          {media.demoVideoNote} · {media.demoDurationLabel}
        </span>
        <details className="vid-desc">
          {/* COPY: disclosure for the text description */}
          <summary>Video description</summary>
          <p id={descId}>{media.demoTranscript}</p>
        </details>
      </figcaption>

      {blocked && (
        <p className="vid-note" role="status">
          {/* COPY: shown only if the browser refuses to start playback */}
          Your browser didn’t start the video. Use the play control in the video to watch it.
        </p>
      )}
    </figure>
  );
}
