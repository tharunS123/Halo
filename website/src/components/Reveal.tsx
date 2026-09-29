import type { ReactNode } from 'react';
import * as m from 'motion/react-m';

/**
 * A small one-time fade-and-rise when a block scrolls into view.
 * Under reduced motion, App's MotionConfig drops the rise and keeps only a short fade.
 * Owned by the website agent.
 */
export default function Reveal({
  children,
  className,
  delay = 0,
  id,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  id?: string;
}) {
  return (
    <m.div
      id={id}
      className={className}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -10% 0px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </m.div>
  );
}
