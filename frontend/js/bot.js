/** The CareerAdapt robot, shared by the dashboard welcome (5.39), the Assistant panel (5.41) and the process finish.
 *  The head is the team's painted art in two frames (eyes open, eyes closed) so it can blink. The body is drawn in
 *  the same style. 5.60 dresses it as a graduate to match the mortarboard: a royal-blue gown open over the white
 *  shell, a gold stole with a gem at each end, gold piping on the cape, ring lights on the shoulders, a framed
 *  glowing AI screen, a voice equaliser, a rim light and sparks under the jet. Gradient ids carry a prefix, so two
 *  robots on one page never share an id. Class names inside (hb-arm-r, hb-cape, hb-scan, hb-ai, hb-jet, hb-eq,
 *  hb-core, hb-ring, hb-gem, hb-rim, hb-seam, hb-spark) are what the stylesheets animate. */
export function botBody(prefix = "hb", className = "hero-bot-body") {
    return `<svg class="${className}" viewBox="0 0 140 86" aria-hidden="true" focusable="false">
    <defs>
        <linearGradient id="${prefix}-shell" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".5" stop-color="#EEF3FD"/><stop offset="1" stop-color="#C3D1F0"/></linearGradient>
        <linearGradient id="${prefix}-navy" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3159C9"/><stop offset="1" stop-color="#172C7E"/></linearGradient>
        <linearGradient id="${prefix}-gown" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3567E0"/><stop offset=".55" stop-color="#2346B8"/><stop offset="1" stop-color="#16287A"/></linearGradient>
        <linearGradient id="${prefix}-cape" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2747B3"/><stop offset="1" stop-color="#0D1A4F"/></linearGradient>
        <linearGradient id="${prefix}-stole" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#F7C948"/><stop offset=".5" stop-color="#FFE08A"/><stop offset="1" stop-color="#E0A526"/></linearGradient>
        <radialGradient id="${prefix}-joint" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#7FB2FF"/><stop offset=".5" stop-color="#2F6FE8"/><stop offset="1" stop-color="#1B3B9A"/></radialGradient>
        <linearGradient id="${prefix}-bezel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A5F3FC"/><stop offset=".5" stop-color="#3B82F6"/><stop offset="1" stop-color="#1E3A8A"/></linearGradient>
        <linearGradient id="${prefix}-ai" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E0FBFF"/><stop offset="1" stop-color="#5EC8FF"/></linearGradient>
        <radialGradient id="${prefix}-jet" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#A5F3FC" stop-opacity=".95"/><stop offset=".45" stop-color="#38BDF8" stop-opacity=".55"/><stop offset="1" stop-color="#38BDF8" stop-opacity="0"/></radialGradient>
        <filter id="${prefix}-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <clipPath id="${prefix}-screen"><rect x="53" y="34" width="34" height="21" rx="6"/></clipPath>
    </defs>
    <ellipse class="hb-jet" cx="70" cy="79" rx="20" ry="5.5" fill="url(#${prefix}-jet)"/>
    <circle class="hb-spark" cx="62" cy="79.5" r="1.1" fill="#A5F3FC"/><circle class="hb-spark" cx="70" cy="81" r="1.3" fill="#E0FBFF"/><circle class="hb-spark" cx="78" cy="79.5" r="1" fill="#A5F3FC"/>
    <g class="hb-cape"><path d="M45 15C32 30 27 52 22 72C38 67 53 73 70 71C87 73 102 67 118 72C113 52 108 30 95 15Z" fill="url(#${prefix}-cape)" stroke="#13235F" stroke-width="2.6" stroke-linejoin="round"/>
        <path d="M44.5 17C33.5 31 28.8 52 24.4 69.6M95.5 17C106.5 31 111.2 52 115.6 69.6" fill="none" stroke="#4C74DB" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>
        <path d="M24.2 70.8C40 66.2 54 72 70 70C86 72 100 66.2 115.8 70.8" fill="none" stroke="#F2C14E" stroke-width="1.5" stroke-linecap="round"/></g>
    <g class="hb-arm hb-arm-l"><rect x="34" y="25" width="12" height="25" rx="6" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><rect x="35.2" y="39.6" width="9.6" height="5" rx="1.4" fill="url(#${prefix}-gown)"/><path class="hb-cuff" d="M37 42.1h6" stroke="#A5F3FC" stroke-width="1.1" stroke-linecap="round"/><circle cx="40" cy="55" r="7.2" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/></g>
    <g class="hb-arm hb-arm-r"><rect x="94" y="25" width="12" height="25" rx="6" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><rect x="95.2" y="39.6" width="9.6" height="5" rx="1.4" fill="url(#${prefix}-gown)"/><path class="hb-cuff" d="M97 42.1h6" stroke="#A5F3FC" stroke-width="1.1" stroke-linecap="round"/><circle cx="100" cy="55" r="7.2" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><path d="M95.5 58.5c2 1.6 6.6 1.6 9 0" fill="none" stroke="#13235F" stroke-width="1.3" stroke-linecap="round" opacity=".5"/></g>
    <path d="M46 10C58 5 82 5 94 10C99 12 101 18 101 26V50C101 64 88 73 70 73C52 73 39 64 39 50V26C39 18 41 12 46 10Z" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="3" stroke-linejoin="round"/>
    <path d="M46 10C42 12 39 18 39 26V50C39 60 46 68 57 71.6L56.5 24C53 19 50 14 46 10Z" fill="url(#${prefix}-gown)" stroke="#13235F" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M94 10C98 12 101 18 101 26V50C101 60 94 68 83 71.6L83.5 24C87 19 90 14 94 10Z" fill="url(#${prefix}-gown)" stroke="#13235F" stroke-width="2.2" stroke-linejoin="round"/>
    <ellipse cx="43.2" cy="36" rx="2" ry="8" fill="#9DBBFF" opacity=".38" transform="rotate(6 43.2 36)"/>
    <path d="M45.5 16C47.5 15.4 49.5 15.4 51.5 16.2L51 61L48.2 67.5L45.4 61Z" fill="url(#${prefix}-stole)" stroke="#13235F" stroke-width="1.5" stroke-linejoin="round"/>
    <path d="M94.5 16C92.5 15.4 90.5 15.4 88.5 16.2L89 61L91.8 67.5L94.6 61Z" fill="url(#${prefix}-stole)" stroke="#13235F" stroke-width="1.5" stroke-linejoin="round"/>
    <path d="M48.3 21V58M91.7 21V58" stroke="#FFF6D6" stroke-width=".8" stroke-linecap="round" opacity=".8"/>
    <path class="hb-gem" d="M48.2 60.4L50.1 63L48.2 65.6L46.3 63Z" fill="#A5F3FC" stroke="#13235F" stroke-width=".9" stroke-linejoin="round"/>
    <path class="hb-gem" d="M91.8 60.4L93.7 63L91.8 65.6L89.9 63Z" fill="#A5F3FC" stroke="#13235F" stroke-width=".9" stroke-linejoin="round"/>
    <path d="M40 13C55 23 85 23 100 13L101.5 21.5C85 32 55 32 38.5 21.5Z" fill="url(#${prefix}-navy)" stroke="#13235F" stroke-width="2.6" stroke-linejoin="round"/>
    <path class="hb-seam" d="M40.6 19.6C55 28.6 85 28.6 99.4 19.6" fill="none" stroke="#5EEAD4" stroke-width="1.1" stroke-linecap="round"/>
    <circle cx="40" cy="27" r="6.6" fill="url(#${prefix}-joint)" stroke="#13235F" stroke-width="2.4"/><circle class="hb-ring" cx="40" cy="27" r="3.3" fill="none" stroke="#A5F3FC" stroke-width="1.2"/>
    <circle cx="100" cy="27" r="6.6" fill="url(#${prefix}-joint)" stroke="#13235F" stroke-width="2.4"/><circle class="hb-ring" cx="100" cy="27" r="3.3" fill="none" stroke="#A5F3FC" stroke-width="1.2"/>
    <rect class="hb-core" x="49.5" y="30.5" width="41" height="28" rx="9.5" fill="none" stroke="#38BDF8" stroke-width="2.4" filter="url(#${prefix}-glow)"/>
    <rect x="51" y="32" width="38" height="25" rx="8" fill="#0A1640" stroke="url(#${prefix}-bezel)" stroke-width="2.2"/>
    <g clip-path="url(#${prefix}-screen)"><rect x="53" y="34" width="34" height="21" fill="#1B3A8F" opacity=".45"/><path d="M53 41h34M53 47.5h34" stroke="#60A5FA" stroke-width=".8" opacity=".14"/><rect class="hb-scan" x="40" y="30" width="7" height="30" fill="#BFE9FF" opacity=".16" transform="skewX(-18)"/></g>
    <rect x="54.4" y="35.4" width="31.2" height="18.2" rx="5" fill="none" stroke="#60A5FA" stroke-opacity=".4" stroke-width="1"/>
    <text class="hb-ai" x="70" y="49.4" text-anchor="middle" font-family="Inter, Segoe UI, sans-serif" font-size="13" font-weight="800" letter-spacing="1" fill="url(#${prefix}-ai)" filter="url(#${prefix}-glow)">AI</text>
    <g class="hb-eqs"><rect class="hb-eq" x="60.8" y="60.4" width="2.4" height="6.2" rx="1.2" fill="#93C5FD"/><rect class="hb-eq" x="64.8" y="60.4" width="2.4" height="6.2" rx="1.2" fill="#5EEAD4"/><rect class="hb-eq" x="68.8" y="60.4" width="2.4" height="6.2" rx="1.2" fill="#A5F3FC"/><rect class="hb-eq" x="72.8" y="60.4" width="2.4" height="6.2" rx="1.2" fill="#5EEAD4"/><rect class="hb-eq" x="76.8" y="60.4" width="2.4" height="6.2" rx="1.2" fill="#93C5FD"/></g>
    <path class="hb-rim" d="M99.4 23C101 32 101 47 98.4 56" fill="none" stroke="#7DD3FC" stroke-width="1.4" stroke-linecap="round"/>
</svg>`;
}

/** The two head frames; the closed-eye frame sits on top and its opacity makes the blink. */
export function botHead(className, blinkClass) {
    return `<span class="${className}"><img src="/img/ai-head-open.webp" alt="" width="300" height="238" decoding="async"><img class="${blinkClass}" src="/img/ai-head-closed.webp" alt="" width="300" height="238" decoding="async"></span>`;
}
