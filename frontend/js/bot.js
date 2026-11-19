/** The CareerAdapt robot, shared by the dashboard welcome (5.39) and the Assistant panel (5.41).
 *  The head is the team's painted art in two frames (eyes open, eyes closed) so it can blink; the body is drawn
 *  in the same style (navy outline, glossy white shell, blue joints like the headphones, scarf and cape, a glowing
 *  "AI" screen, a hover glow). Gradient ids carry a prefix, so two robots on one page never share an id.
 *  Class names inside (hb-arm-r, hb-cape, hb-scan, hb-led, hb-ai, hb-jet) are what the stylesheets animate. */
export function botBody(prefix = "hb", className = "hero-bot-body") {
    return `<svg class="${className}" viewBox="0 0 140 86" aria-hidden="true" focusable="false">
    <defs>
        <linearGradient id="${prefix}-shell" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".5" stop-color="#EEF3FD"/><stop offset="1" stop-color="#C3D1F0"/></linearGradient>
        <linearGradient id="${prefix}-navy" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3159C9"/><stop offset="1" stop-color="#172C7E"/></linearGradient>
        <linearGradient id="${prefix}-cape" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2747B3"/><stop offset="1" stop-color="#0D1A4F"/></linearGradient>
        <radialGradient id="${prefix}-joint" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#7FB2FF"/><stop offset=".5" stop-color="#2F6FE8"/><stop offset="1" stop-color="#1B3B9A"/></radialGradient>
        <linearGradient id="${prefix}-ai" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E0FBFF"/><stop offset="1" stop-color="#5EC8FF"/></linearGradient>
        <radialGradient id="${prefix}-jet" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#A5F3FC" stop-opacity=".95"/><stop offset=".45" stop-color="#38BDF8" stop-opacity=".55"/><stop offset="1" stop-color="#38BDF8" stop-opacity="0"/></radialGradient>
        <filter id="${prefix}-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <clipPath id="${prefix}-screen"><rect x="52" y="33" width="36" height="23" rx="7"/></clipPath>
    </defs>
    <ellipse class="hb-jet" cx="70" cy="79" rx="20" ry="5.5" fill="url(#${prefix}-jet)"/>
    <g class="hb-cape"><path d="M45 15C32 30 27 52 22 72C38 67 53 73 70 71C87 73 102 67 118 72C113 52 108 30 95 15Z" fill="url(#${prefix}-cape)" stroke="#13235F" stroke-width="2.6" stroke-linejoin="round"/>
        <path d="M33 60C46 58 58 63 70 62M107 60C94 58 82 63 70 62" fill="none" stroke="#4C74DB" stroke-width="1.4" stroke-linecap="round" opacity=".55"/></g>
    <g class="hb-arm hb-arm-l"><rect x="34" y="25" width="12" height="25" rx="6" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><rect x="35.3" y="39" width="9.4" height="4" fill="#2F6FE8"/><circle cx="40" cy="55" r="7.2" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/></g>
    <g class="hb-arm hb-arm-r"><rect x="94" y="25" width="12" height="25" rx="6" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><rect x="95.3" y="39" width="9.4" height="4" fill="#2F6FE8"/><circle cx="100" cy="55" r="7.2" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="2.6"/><path d="M95.5 58.5c2 1.6 6.6 1.6 9 0" fill="none" stroke="#13235F" stroke-width="1.3" stroke-linecap="round" opacity=".5"/></g>
    <path d="M46 10C58 5 82 5 94 10C99 12 101 18 101 26V50C101 64 88 73 70 73C52 73 39 64 39 50V26C39 18 41 12 46 10Z" fill="url(#${prefix}-shell)" stroke="#13235F" stroke-width="3" stroke-linejoin="round"/>
    <path d="M91 15C98 21 98.5 32 98.5 48C98.5 60 92 67 83 70.5C91 60 93.5 41 91 15Z" fill="#8FA6DC" opacity=".38"/>
    <ellipse cx="50" cy="31" rx="4.2" ry="9" fill="#FFFFFF" opacity=".85" transform="rotate(14 50 31)"/>
    <path d="M45 60C53 66 87 66 95 60" fill="none" stroke="#B9C8EC" stroke-width="2" stroke-linecap="round"/>
    <path d="M40 13C55 23 85 23 100 13L101.5 21.5C85 32 55 32 38.5 21.5Z" fill="url(#${prefix}-navy)" stroke="#13235F" stroke-width="2.6" stroke-linejoin="round"/>
    <circle cx="40" cy="27" r="6.6" fill="url(#${prefix}-joint)" stroke="#13235F" stroke-width="2.4"/>
    <circle cx="100" cy="27" r="6.6" fill="url(#${prefix}-joint)" stroke="#13235F" stroke-width="2.4"/>
    <rect x="52" y="33" width="36" height="23" rx="7" fill="#0A1640" stroke="#13235F" stroke-width="2.6"/>
    <g clip-path="url(#${prefix}-screen)"><rect x="52" y="33" width="36" height="23" fill="#1B3A8F" opacity=".35"/><rect class="hb-scan" x="40" y="30" width="7" height="30" fill="#BFE9FF" opacity=".16" transform="skewX(-18)"/></g>
    <rect x="54.4" y="35.4" width="31.2" height="18.2" rx="5" fill="none" stroke="#60A5FA" stroke-opacity=".45" stroke-width="1"/>
    <text class="hb-ai" x="70" y="49.4" text-anchor="middle" font-family="Inter, Segoe UI, sans-serif" font-size="13" font-weight="800" letter-spacing="1" fill="url(#${prefix}-ai)" filter="url(#${prefix}-glow)">AI</text>
    <circle class="hb-led" cx="62" cy="64" r="2.3" fill="#93C5FD"/><circle class="hb-led" cx="70" cy="64" r="2.3" fill="#5EEAD4"/><circle class="hb-led" cx="78" cy="64" r="2.3" fill="#93C5FD"/>
</svg>`;
}

/** The two head frames; the closed-eye frame sits on top and its opacity makes the blink. */
export function botHead(className, blinkClass) {
    return `<span class="${className}"><img src="/img/ai-head-open.webp" alt="" width="300" height="238" decoding="async"><img class="${blinkClass}" src="/img/ai-head-closed.webp" alt="" width="300" height="238" decoding="async"></span>`;
}
