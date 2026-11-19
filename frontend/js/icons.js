/** Shared icon set (24px grid, 1.8 stroke) and the few decorative illustrations. Inline SVG: the CSP allows no icon CDN. */

const PATHS = {
    home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1Z",
    grid: "M4 4h7v7H4ZM13 4h7v7h-7ZM4 13h7v7H4ZM13 13h7v7h-7Z",
    target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
    chart: "M4 20h16M7 16v-5M12 16V7M17 16v-8",
    book: "M4 19V5a2 2 0 0 1 2-2h14v14H6a2 2 0 0 0-2 2Zm2 2h14v-4",
    quiz: "M9 3h6v3H9ZM8 4.5H6a1 1 0 0 0-1 1V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5.5a1 1 0 0 0-1-1h-2M9 14l2 2 4-4",
    user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
    shield: "M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3Zm-3 9 2 2 4-4",
    sparkles: "M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z",
    arrow: "M5 12h14M13 6l6 6-6 6",
    upload: "M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5M5 15v3.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15",
    info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-10v5m0-8h.01",
    alert: "M12 4l9 16H3Zm0 6v4m0 3h.01",
    clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-14v5l3 2",
    database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    filter: "M4 4h16l-6 7.5V17l-4 3v-8.5Z",
    code: "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
    pen: "M4 20h4L19 9l-4-4L4 16Zm9.5-13.5 4 4",
    calendar: "M4 6a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Zm0 4h16M8 3v4m8-4v4",
    lock: "M6 11h12v10H6Zm2 0V7a4 4 0 0 1 8 0v4",
    refresh: "M20 11a8 8 0 0 0-14.6-4.5L4 8m0-4v4h4m-4 5a8 8 0 0 0 14.6 4.5L20 16m0 4v-4h-4",
    file: "M6 3h8l5 5v13H6Zm8 0v5h5M9 13h6m-6 4h6",
    link: "M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    trophy: "M8 4h8v5a4 4 0 0 1-8 0Zm0 2H5v1a3 3 0 0 0 3 3m8-4h3v1a3 3 0 0 1-3 3m-4 3v4m-3 4h6m-5-4h4",
    route: "M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm12-10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 17h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7",
    pulse: "M3 12h4l3-8 4 16 3-8h4",
    play: "M8 5v14l11-7Z",
    growth: "M3 17l6-6 4 4 8-8M15 7h6v6",
    pause: "M9 5v14M15 5v14",
    stop: "M7 7h10v10H7Z",
    sigma: "M17 5H7l6 7-6 7h10",
    check: "M5 12l5 5 9-10",
    chat: "M4 5h16v11H9l-5 4Z",
    search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm9 2-4-4",
    flask: "M9 3h6m-5 0v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3",
    bell: "M6 9a6 6 0 1 1 12 0c0 6 2.5 7 2.5 7h-17S6 15 6 9Zm4 10a2 2 0 0 0 4 0",
    logout: "M15 4h4v16h-4M10 8l-4 4 4 4m-4-4h10",
    close: "M6 6l12 12M18 6 6 18",
    inbox: "M3 13h5l1.5 3h5l1.5-3h5M5.5 5h13L21 13v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6Z",
};

/* 5.59: the main pages get their own two-tone marks (an outline plus a soft filled part) on the same 24px grid
   and stroke as the set, each filling the same 16-unit square (5.60): Bảng điều khiển = a dashboard of panels, Quy trình = three steps (a dot and a bar each), the first two done,
   Kế hoạch = a plan board with a rising line.
   5.61: the rest of the navigation joins the set (learn, test, write, account, admin). Square marks fill the 16-unit
   square, upright ones (book, clipboard, person, shield) are 15 wide and 16 tall, so every item reads the same size. Other screens keep using chart and target for data. */
const DUO = {
    dashboard: {
        fill: "M4 5.5A1.5 1.5 0 0 1 5.5 4h4A1.5 1.5 0 0 1 11 5.5v13A1.5 1.5 0 0 1 9.5 20h-4A1.5 1.5 0 0 1 4 18.5Z",
        d: "M4 5.5A1.5 1.5 0 0 1 5.5 4h4A1.5 1.5 0 0 1 11 5.5v13A1.5 1.5 0 0 1 9.5 20h-4A1.5 1.5 0 0 1 4 18.5ZM13 5.5A1.5 1.5 0 0 1 14.5 4h4A1.5 1.5 0 0 1 20 5.5v3A1.5 1.5 0 0 1 18.5 10h-4A1.5 1.5 0 0 1 13 8.5ZM13 14.5a1.5 1.5 0 0 1 1.5-1.5h4a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5Z",
    },
    journey: {
        fill: "M7.6 5.8a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0ZM7.6 12a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0ZM12.2 4h6a1.8 1.8 0 0 1 0 3.6h-6a1.8 1.8 0 0 1 0-3.6ZM12.2 10.2h6a1.8 1.8 0 0 1 0 3.6h-6a1.8 1.8 0 0 1 0-3.6Z",
        d: "M7.6 5.8a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0ZM7.6 12a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0ZM7.6 18.2a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0ZM12.2 4h6a1.8 1.8 0 0 1 0 3.6h-6a1.8 1.8 0 0 1 0-3.6ZM12.2 10.2h6a1.8 1.8 0 0 1 0 3.6h-6a1.8 1.8 0 0 1 0-3.6ZM12.2 16.4h3a1.8 1.8 0 0 1 0 3.6h-3a1.8 1.8 0 0 1 0-3.6Z",
    },
    plan: {
        fill: "M4 6.6A2.6 2.6 0 0 1 6.6 4h10.8A2.6 2.6 0 0 1 20 6.6V9H4Z",
        d: "M4 6.6A2.6 2.6 0 0 1 6.6 4h10.8A2.6 2.6 0 0 1 20 6.6v10.8a2.6 2.6 0 0 1-2.6 2.6H6.6A2.6 2.6 0 0 1 4 17.4ZM4 9h16M7.5 16.5l3-3 2.5 2 3.5-4M14.5 11.5h2v2",
    },
    learn: {
        fill: "M4.5 6.5A2.5 2.5 0 0 1 7 4h12.5v12H7a2.5 2.5 0 0 0-2.5 2.5Z",
        d: "M4.5 6.5A2.5 2.5 0 0 1 7 4h12.5v12H7a2.5 2.5 0 0 0-2.5 2.5ZM4.5 18.5A1.5 1.5 0 0 0 6 20h13.5v-4M8.5 8h7",
    },
    test: {
        fill: "M9.5 4h5a1 1 0 0 1 1 1v1.4a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z",
        d: "M8.5 5.6h-2a2 2 0 0 0-2 2V18a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7.6a2 2 0 0 0-2-2h-2M9.5 4h5a1 1 0 0 1 1 1v1.4a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM8.8 13.6l2.2 2.2 4.4-4.6",
    },
    write: {
        fill: "M14.8 4.6a2 2 0 0 1 2.8 0l1.4 1.4a2 2 0 0 1 0 2.8l-1.7 1.7-4.2-4.2Z",
        d: "M14.8 4.6a2 2 0 0 1 2.8 0l1.4 1.4a2 2 0 0 1 0 2.8L8.8 19H4.5v-4.3ZM13.1 6.3l4.2 4.2M12.5 20h7",
    },
    account: {
        fill: "M15.6 7.6a3.6 3.6 0 1 1-7.2 0 3.6 3.6 0 0 1 7.2 0Z",
        d: "M15.6 7.6a3.6 3.6 0 1 1-7.2 0 3.6 3.6 0 0 1 7.2 0ZM4.5 20v-.5A6.5 6.5 0 0 1 11 13h2a6.5 6.5 0 0 1 6.5 6.5v.5Z",
    },
    admin: {
        fill: "M12 4v16c-4.4-.9-7.5-3.6-7.5-8V7Z",
        d: "M12 4l7.5 3v5c0 4.4-3.1 7.1-7.5 8-4.4-.9-7.5-3.6-7.5-8V7ZM9 12l2.2 2.2 4-4.2",
    },
};

export const icon = (name, className = "") => {
    const duo = DUO[name];
    const body = duo ? `<path class="ic-fill" d="${duo.fill}"/><path d="${duo.d}"/>` : `<path d="${PATHS[name] || PATHS.info}"/>`;
    return `<svg class="ic ${duo ? "ic-duo" : ""} ${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
};

export const SKILL_ICONS = { SQL: "database", DATA_QUALITY: "filter", PYTHON: "code", DATA_VIZ: "chart", WRITTEN_COMM: "pen", STATISTICS: "sigma" };
const SKILL_TONES = { SQL: "s1", DATA_QUALITY: "s2", PYTHON: "s3", DATA_VIZ: "s4", WRITTEN_COMM: "s5", STATISTICS: "s6" };

/** A rounded square holding an icon; `tone` picks one of the series colours or the brand blue. */
export const tile = (name, tone = "brand", className = "") => `<span class="tile tile-${tone} ${className}">${icon(name)}</span>`;
/** The CareerAdapt AI mascot. Decorative: the text next to it always says what the AI did. */
export const aiAvatar = (size = "sm") => `<img class="ai-avatar ai-avatar-${size}" src="/img/ai-avatar.webp" alt="" aria-hidden="true" width="40" height="40" decoding="async">`;

export const skillTile = (code, className = "") => tile(SKILL_ICONS[code] || "sparkles", SKILL_TONES[code] || "brand", className);
export const skillIcon = code => icon(SKILL_ICONS[code] || "sparkles");

/** Decorative only: every illustration is hidden from assistive technology. */
const ILLUSTRATIONS = {
    growth: `<rect x="20" y="34" width="120" height="84" rx="14" class="il-card"/><rect x="36" y="86" width="14" height="20" rx="3" class="il-soft"/><rect x="58" y="72" width="14" height="34" rx="3" class="il-soft"/><rect x="80" y="60" width="14" height="46" rx="3" class="il-mid"/><rect x="102" y="48" width="14" height="58" rx="3" class="il-strong"/><path d="M36 70l24-14 22 8 34-22" class="il-line"/><rect x="118" y="14" width="56" height="40" rx="10" class="il-card"/><path d="M132 36l8 7 16-16" class="il-check"/><path d="M168 82l3 8 8 3-8 3-3 8-3-8-8-3 8-3Z" class="il-spark"/><path d="M14 18l2 5 5 2-5 2-2 5-2-5-5-2 5-2Z" class="il-spark"/>`,
    robot: `<rect x="8" y="22" width="44" height="34" rx="8" class="il-glass"/><rect x="16" y="40" width="6" height="10" rx="2" class="il-card"/><rect x="26" y="34" width="6" height="16" rx="2" class="il-card"/><rect x="36" y="28" width="6" height="22" rx="2" class="il-card"/>
        <rect x="138" y="70" width="44" height="38" rx="9" class="il-glass"/><path d="M150 89l7 7 14-14" class="il-check-on"/><rect x="10" y="84" width="40" height="26" rx="7" class="il-glass"/><path d="M18 94h24M18 101h16" class="il-line-on"/>
        <rect x="76" y="88" width="42" height="36" rx="12" class="il-card"/><rect x="83" y="96" width="28" height="20" rx="6" class="il-strong"/><text x="97" y="110.5" text-anchor="middle" class="il-text">AI</text>
        <g class="il-bot-head"><image href="/img/ai-head-open.webp" x="54" y="21" width="86" height="68"/><image href="/img/ai-head-closed.webp" x="54" y="21" width="86" height="68" class="il-bot-blink"/></g>
        <path d="M150 22l3 8 8 3-8 3-3 8-3-8-8-3 8-3Z" class="il-spark"/><path d="M58 12l2 5 5 2-5 2-2 5-2-5-5-2 5-2Z" class="il-spark"/>`,
    profile: `<circle cx="95" cy="68" r="46" class="il-ring"/><circle cx="95" cy="56" r="16" class="il-person"/><path d="M67 96a28 28 0 0 1 56 0" class="il-person"/>`,
    calendar: `<rect x="30" y="30" width="96" height="88" rx="12" class="il-card"/><path d="M30 54h96" class="il-line"/><path d="M54 22v16M102 22v16" class="il-line"/><g class="il-soft"><rect x="44" y="66" width="14" height="12" rx="3"/><rect x="66" y="66" width="14" height="12" rx="3"/><rect x="88" y="66" width="14" height="12" rx="3"/><rect x="44" y="88" width="14" height="12" rx="3"/><rect x="66" y="88" width="14" height="12" rx="3"/></g><circle cx="122" cy="108" r="20" class="il-strong"/><path d="M113 108l6 6 12-12" class="il-check-on"/>`,
    shield: `<path d="M80 18l40 16v32c0 26-17 44-40 52-23-8-40-26-40-52V34Z" class="il-strong"/><rect x="64" y="62" width="32" height="26" rx="5" class="il-card"/><path d="M70 62v-8a10 10 0 0 1 20 0v8" class="il-line-on"/><circle cx="80" cy="74" r="3.5" class="il-dot"/>`,
    clipboard: `<rect x="36" y="22" width="80" height="100" rx="12" class="il-card"/><rect x="58" y="14" width="36" height="16" rx="6" class="il-mid"/><g class="il-line"><path d="M52 52l5 5 9-9M52 76l5 5 9-9M52 100l5 5 9-9M76 54h26M76 78h26M76 102h18"/></g><circle cx="118" cy="104" r="18" class="il-strong"/><path d="M110 104l5 5 11-11" class="il-check-on"/>`,
};
export const illustration = (name, className = "") => `<svg class="illus ${className}" viewBox="0 0 190 136" aria-hidden="true" focusable="false">${ILLUSTRATIONS[name] || ""}</svg>`;
