import type { ReactNode } from 'react';

/** Small inline icons, drawn on a 16px grid. Decorative: always aria-hidden. Owned by the website agent. */

type IconProps = { size?: number; className?: string };

function Svg({ size = 16, className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5.25 3.4v9.2a.5.5 0 0 0 .76.43l7.4-4.6a.5.5 0 0 0 0-.86l-7.4-4.6a.5.5 0 0 0-.76.43Z" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function PauseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="3" width="2.75" height="10" rx="0.75" fill="currentColor" stroke="none" />
      <rect x="9.25" y="3" width="2.75" height="10" rx="0.75" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function CopyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 3.25V3A1.5 1.5 0 0 0 9 1.5H4A1.5 1.5 0 0 0 2.5 3v5A1.5 1.5 0 0 0 4 9.5h.25" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.25 8.5 6.5 11.5l6.25-7" />
    </Svg>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 5.25h11M2.5 10.75h11" />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.75 3.75l8.5 8.5M12.25 3.75l-8.5 8.5" />
    </Svg>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6.5 3.5H4A1.5 1.5 0 0 0 2.5 5v7A1.5 1.5 0 0 0 4 13.5h7a1.5 1.5 0 0 0 1.5-1.5V9.5" />
      <path d="M9.5 2.5h4v4M13.25 2.75 7.5 8.5" />
    </Svg>
  );
}

export function ArrowIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.75 8h10.5M9 3.75 13.25 8 9 12.25" />
    </Svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 2.25v8.25M4.5 7 8 10.5 11.5 7M2.75 13.75h10.5" />
    </Svg>
  );
}

/** A generic source-repository glyph (book with a bookmark), drawn for this site. */
export function GithubIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 12.5V3A1.5 1.5 0 0 1 4.5 1.5h8.5v10H4.5A1.5 1.5 0 0 0 3 13a1.5 1.5 0 0 0 1.5 1.5h2" />
      <path d="M9 11.5v3.25l1.25-.9 1.25.9V11.5" />
    </Svg>
  );
}

export function MicIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5.75" y="1.75" width="4.5" height="8" rx="2.25" />
      <path d="M3.25 7.75a4.75 4.75 0 0 0 9.5 0M8 12.5v2" />
    </Svg>
  );
}
