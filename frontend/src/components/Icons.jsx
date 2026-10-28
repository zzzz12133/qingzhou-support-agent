import React from 'react';

const PATHS = {
  menu: (
    <>
      <path d="M4 7h16M4 12h16M4 17h10" />
    </>
  ),
  close: <path d="m6 6 12 12M18 6 6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  chat: (
    <>
      <path d="M20 11.5a7.5 7.5 0 0 1-8 7.47 8.5 8.5 0 0 1-2.4-.37L5 20l1.3-3.8A7.5 7.5 0 1 1 20 11.5Z" />
      <path d="M8.7 11.5h.01M12 11.5h.01M15.3 11.5h.01" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16M9 7V4.8A.8.8 0 0 1 9.8 4h4.4a.8.8 0 0 1 .8.8V7M6.5 7l.8 12.1a1 1 0 0 0 1 .9h7.4a1 1 0 0 0 1-.9L17.5 7" />
      <path d="M10 11v5M14 11v5" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" />
    </>
  ),
  panel: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M15 4v16M18.2 8h.01M18.2 12h.01" />
    </>
  ),
  send: (
    <>
      <path d="m21 3-7.2 18-3.4-7.4L3 10.2 21 3Z" />
      <path d="M21 3 10.4 13.6" />
    </>
  ),
  stop: <rect x="7" y="7" width="10" height="10" rx="1.6" fill="currentColor" stroke="none" />,
  shield: (
    <>
      <path d="M12 3 4.8 6v5.3c0 4.4 3 8.1 7.2 9.7 4.2-1.6 7.2-5.3 7.2-9.7V6L12 3Z" />
      <path d="m8.8 12 2.1 2.1 4.5-4.5" />
    </>
  ),
  check: <path d="m4.5 12.5 5 5L19.5 7" />,
  chevronRight: <path d="m9 5 7 7-7 7" />,
  chevronDown: <path d="m5 9 7 7 7-7" />,
  spark: (
    <>
      <path d="M12 3.5c.4 4.4 2.1 6.1 6.5 6.5-4.4.4-6.1 2.1-6.5 6.5-.4-4.4-2.1-6.1-6.5-6.5 4.4-.4 6.1-2.1 6.5-6.5Z" />
      <path d="M18.7 15.5c.2 2.3 1.1 3.2 3.3 3.4-2.2.2-3.1 1.1-3.3 3.3-.2-2.2-1.1-3.1-3.3-3.3 2.2-.2 3.1-1.1 3.3-3.4Z" />
    </>
  ),
  package: (
    <>
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="m4.3 7.8 7.7 4.3 7.7-4.3M12 12.1V21M8 5.1l8 4.5" />
    </>
  ),
  rotate: (
    <>
      <path d="M4 11a8 8 0 1 1 2.35 5.65M4 5v6h6" />
    </>
  ),
  wrench: (
    <>
      <path d="M14.7 6.3a4 4 0 0 1 5-3.9l-2.8 2.7 2 2 2.7-2.8a4 4 0 0 1-4.8 5.1L9 17.2a2.2 2.2 0 0 1-3.1-3.1l7.8-7.8Z" />
      <path d="m5.5 18.5 2 2" />
    </>
  ),
  headset: (
    <>
      <path d="M4 13v-1a8 8 0 0 1 16 0v1" />
      <path d="M4 12.5h2.5a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-5ZM20 12.5h-2.5a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1H19a1 1 0 0 0 1-1v-5ZM17 19.5c-.7 1.2-1.8 1.8-3.3 1.8H12" />
    </>
  ),
  brain: (
    <>
      <path d="M9.5 5.2A3 3 0 0 0 4.8 8a3 3 0 0 0-1 5.7A3.3 3.3 0 0 0 7 19a3 3 0 0 0 5-2.2V6.8a2.1 2.1 0 0 0-2.5-1.6Z" />
      <path d="M14.5 5.2A3 3 0 0 1 19.2 8a3 3 0 0 1 1 5.7A3.3 3.3 0 0 1 17 19a3 3 0 0 1-5-2.2M8 9.5c1 .1 2 .7 2.5 1.6M16 9.5c-1 .1-2 .7-2.5 1.6M8.5 14.5c.8.1 1.5.5 2 1.1M15.5 14.5c-.8.1-1.5.5-2 1.1" />
    </>
  ),
  book: (
    <>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16.5H6.5A2.5 2.5 0 0 0 4 22V5.5Z" />
      <path d="M4 17.5A2.5 2.5 0 0 1 6.5 15H20M8 7h8M8 10.5h5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.4l3.5 2" />
    </>
  ),
  alert: (
    <>
      <path d="M10.3 3.9 2.8 17a1.9 1.9 0 0 0 1.7 2.8h15a1.9 1.9 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4.2M12 16.8h.01" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6M20 4l-9 9" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </>
  ),
  thumbsUp: (
    <>
      <path d="M7 10v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h3ZM7 10l3.6-7a2 2 0 0 1 1.8 2v4h5.7a2 2 0 0 1 2 2.3l-1.2 7a2 2 0 0 1-2 1.7H7" />
    </>
  ),
  thumbsDown: (
    <>
      <path d="M17 14V4h3a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-3ZM17 14l-3.6 7a2 2 0 0 1-1.8-2v-4H5.9a2 2 0 0 1-2-2.3l1.2-7a2 2 0 0 1 2-1.7H17" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M6.1 8.5A7.5 7.5 0 0 1 19.8 12M4.2 12a7.5 7.5 0 0 0 13.7 3.5" />
    </>
  ),
  arrowDown: <path d="M12 4v16M6 14l6 6 6-6" />,
  lock: (
    <>
      <rect x="4.5" y="10" width="15" height="10" rx="2.5" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" />
    </>
  ),
  route: (
    <>
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="18" r="2" />
      <path d="M7 6h5a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h8" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.5 12h2M19.5 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  moon: <path d="M20.2 14.2A8.6 8.6 0 0 1 9.8 3.8 8.6 8.6 0 1 0 20.2 14.2Z" />,
  monitor: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2.5" />
      <path d="M8 21h8M12 17v4" />
    </>
  ),
  settings: (
    <>
      <path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h8M16 18h4" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="8" cy="12" r="2" />
      <circle cx="14" cy="18" r="2" />
    </>
  ),
};

export default function Icon({ name, size = 18, strokeWidth = 1.7, className = '' }) {
  const path = PATHS[name] || PATHS.spark;
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {path}
    </svg>
  );
}

export function BoatMark({ size = 38 }) {
  return (
    <span className="boat-mark" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 64 64" width={size} height={size}>
        <path d="M15 36h34l-6 13H23c-3.4 0-6.2-2.1-7.4-5.2L15 36Z" fill="currentColor" />
        <path
          d="M31 14v21M31 17l15 17H31M31 21 19 34h12"
          fill="none"
          stroke="#f4b860"
          strokeWidth="3.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M15 36c8 3 23 3 34 0" fill="none" stroke="#0e7c66" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </span>
  );
}
