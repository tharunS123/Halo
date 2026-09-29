import { LazyMotion, MotionConfig, domAnimation } from 'motion/react';
import Header from './components/Header';
import Hero from './components/Hero';
import ThoughtToText from './components/demo/ThoughtToText';
import WhyHalo from './components/WhyHalo';
import MoreFeatures from './components/MoreFeatures';
import Install from './components/Install';
import Footer from './components/Footer';

/** Page composition. Owned by the integrator. Each section renders its own <section id>. */
export default function App() {
  // LazyMotion + the `m` component keeps the motion runtime to the DOM-animation feature set.
  // reducedMotion="user" turns scroll-in rises into plain fades when the OS asks for less motion.
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user">
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <Header />
        <main id="main" tabIndex={-1}>
          <Hero />
          <ThoughtToText />
          <WhyHalo />
          <MoreFeatures />
          <Install />
        </main>
        <Footer />
      </MotionConfig>
    </LazyMotion>
  );
}
