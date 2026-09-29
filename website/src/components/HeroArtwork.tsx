import DesignCrop, { ORB_CROP, SETTINGS_CROP } from './DesignCrop';
import { useSceneVisibility } from './demo/useSceneVisibility';
import './HeroArtwork.css';

/** Product imagery from Halo's approved interface boards, cropped without redrawing them. */
export default function HeroArtwork() {
  const [artRef, { visible }] = useSceneVisibility<HTMLDivElement>();
  return (
    <div ref={artRef} className="hero-art" data-visible={visible ? 'true' : 'false'} aria-label="Halo interface design preview">
      <div className="hero-art-screen">
        <div className="hero-art-caption">
          <span className="hero-art-live" aria-hidden="true" />
          HALO / DICTATION
        </div>
        <DesignCrop
          file="01-night-settings.png"
          crop={SETTINGS_CROP}
          label="Halo's Night interface design: Dictation settings with F9 and Normal cleanup selected"
          className="hero-art-settings"
        />
      </div>

      <div className="hero-art-side">
        <span className="hero-art-side-index">01 / YOUR VOICE</span>
        <div className="hero-art-orb">
          <DesignCrop
            file="03-original-orb-plus-beam.png"
            crop={ORB_CROP}
            label="A frame of Halo's original grayscale dotted orb from the approved design"
          />
        </div>
        <div className="hero-art-side-copy">
          <span className="hero-art-key">F9 <span aria-hidden="true">↘</span></span>
          <span>Hold. Speak. Release.</span>
          <p>The shortcut is the interface.</p>
        </div>
      </div>
      <p className="hero-art-credit">Approved interface design preview · Original orb geometry</p>
    </div>
  );
}
