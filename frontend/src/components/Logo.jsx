/** SkillWatch AI logo mark: viewfinder brackets around a pulsing lime dot. Pure SVG + CSS, no images.
 *  size: pixels. mono: draws the brackets in lime too (all-lime mark). */
export default function Logo({ size = 28, mono = false, className = "" }) {
  const bracket = mono ? "#C6FF00" : "url(#swl-cb)";
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={`shrink-0 ${className}`} role="img" aria-label="SkillWatch AI">
      <defs>
        <linearGradient id="swl-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0A0F24" />
          <stop offset="1" stopColor="#02030A" />
        </linearGradient>
        <linearGradient id="swl-cb" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3B6BFF" />
          <stop offset="1" stopColor="#1F4BFF" />
        </linearGradient>
        <radialGradient id="swl-glow">
          <stop offset="0" stopColor="#C6FF00" stopOpacity=".55" />
          <stop offset="1" stopColor="#C6FF00" stopOpacity="0" />
        </radialGradient>
      </defs>
      <style>{`
        .swl-frame { transform-box: view-box; transform-origin: 50% 50%; animation: swl-breathe 3.2s ease-in-out infinite; }
        .swl-ring  { transform-box: fill-box; transform-origin: center; animation: swl-ping 2s ease-out infinite; }
        .swl-halo  { transform-box: fill-box; transform-origin: center; animation: swl-halo 2s ease-in-out infinite; }
        @keyframes swl-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(.93); } }
        @keyframes swl-ping { 0% { transform: scale(1); opacity: .95; } 100% { transform: scale(2.3); opacity: 0; } }
        @keyframes swl-halo { 0%,100% { opacity: .55; } 50% { opacity: 1; } }
        @media (prefers-reduced-motion: reduce) { .swl-frame, .swl-ring, .swl-halo { animation: none; } .swl-ring { opacity: 0; } }
      `}</style>
      <rect width="64" height="64" rx="16" fill="url(#swl-bg)" />
      <rect x="1.5" y="1.5" width="61" height="61" rx="14.5" fill="none" stroke={mono ? "#C6FF00" : "#1F4BFF"} strokeOpacity=".6" strokeWidth="3" />
      <g className="swl-frame" fill="none" stroke={bracket} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 27v-7q0-5 5-5h7" />
        <path d="M49 27v-7q0-5-5-5h-7" />
        <path d="M15 37v7q0 5 5 5h7" />
        <path d="M49 37v7q0 5-5 5h-7" />
      </g>
      <circle className="swl-halo" cx="32" cy="32" r="14" fill="url(#swl-glow)" />
      <circle className="swl-ring" cx="32" cy="32" r="7" fill="none" stroke="#C6FF00" strokeWidth="2.5" />
      <circle cx="32" cy="32" r="7" fill="#C6FF00" />
    </svg>
  );
}