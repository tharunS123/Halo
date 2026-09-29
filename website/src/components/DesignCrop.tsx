import { asset } from '../content/site';

type DesignCropProps = {
  file: string;
  crop: [number, number, number, number];
  label: string;
  className?: string;
};

/** Displays only the interface area of an approved, unmodified design board. */
export default function DesignCrop({ file, crop, label, className }: DesignCropProps) {
  const [x, y, width, height] = crop;
  return (
    <svg
      className={className}
      viewBox={`${x} ${y} ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={label}
    >
      <image href={asset(`design/${file}`)} x="0" y="0" width="1600" height="1120" />
    </svg>
  );
}

export const SETTINGS_CROP: [number, number, number, number] = [63, 220, 966, 773];
export const SETUP_CROP: [number, number, number, number] = [63, 220, 881, 763];
export const ORB_CROP: [number, number, number, number] = [276, 353, 280, 280];
