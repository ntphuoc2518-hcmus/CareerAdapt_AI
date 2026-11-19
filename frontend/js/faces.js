/** Facial expressions of the CareerAdapt robot (5.43).
 *
 * The head is the team's painted art with the face erased from the visor (ai-head-blank.webp); the face is drawn
 * on top as glowing SVG in the same style (cyan eyes, pink mouth, blush), so it can change and move: blink, tears,
 * twinkling star eyes, thinking dots. Coordinates are in the image's own 300 x 238 frame, where the painted face
 * sat (eyes at 87,151 and 184,151; mouth at 136,180; blush at 63,181 and 202,183).
 *
 * An expression only reflects what already happened (a score the checker computed, a message the page shows);
 * it never decides anything.
 */

/** Each expression and the moment it is meant for. */
export const EXPRESSIONS = {
    neutral: "Mặc định",
    happy: "Chào hỏi, hướng dẫn các bước",
    joy: "Đạt bài kiểm tra, thông báo thành công",
    celebrate: "Đạt từ 85 điểm, hoàn tất quy trình",
    proud: "Đạt mục tiêu (dự phòng)",
    encouraging: "Chưa đạt nhưng từ 40 điểm; trước khi làm bài",
    thinking: "Đang chấm bài, đang chờ máy chủ",
    surprised: "Caps Lock đang bật",
    worried: "Điểm cao nhưng có lỗi trọng yếu; sai mật khẩu",
    sad: "Từ 20 đến dưới 40 điểm",
    crying: "Dưới 20 điểm",
    shy: "Đang gõ mật khẩu",
};

const L = [87, 151];
const R = [184, 151];
let counter = 0;

const oval = ([x, y], rx = 13, ry = 19) => `<g class="xf-eye"><ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" class="xf-fill" fill="url(#__ID__-eye)"/><ellipse cx="${x - rx * 0.32}" cy="${y - ry * 0.38}" rx="${rx * 0.3}" ry="${ry * 0.28}" class="xf-shine"/></g>`;
const arc = ([x, y], w = 14, lift = 16, drop = 6) => `<path d="M${x - w} ${y + drop} Q${x} ${y - lift} ${x + w} ${y + drop}" class="xf-line"/>`;
const closedDown = ([x, y], w = 13) => `<path d="M${x - w} ${y - 2} Q${x} ${y + 11} ${x + w} ${y - 2}" class="xf-line"/>`;
const star = ([x, y], r = 17) => {
    const points = Array.from({ length: 10 }, (unused, index) => {
        const angle = -Math.PI / 2 + index * Math.PI / 5;
        const radius = index % 2 ? r * 0.45 : r;
        return `${(x + radius * Math.cos(angle)).toFixed(1)},${(y + radius * Math.sin(angle)).toFixed(1)}`;
    }).join(" ");
    return `<g class="xf-star"><polygon points="${points}" class="xf-fill" fill="url(#__ID__-eye)"/></g>`;
};
// Sad eye: the inner corner is raised, so the top edge slopes up toward the nose.
const sadEye = ([x, y], inner) => {
    const s = inner === "right" ? 1 : -1;
    return `<g class="xf-eye"><path d="M${x - 13 * s} ${y + 1} L${x + 13 * s} ${y - 9} Q${x + 15 * s} ${y + 16} ${x} ${y + 16} Q${x - 15 * s} ${y + 16} ${x - 13 * s} ${y + 1} Z" class="xf-fill" fill="url(#__ID__-eye)"/><ellipse cx="${x - 3 * s}" cy="${y + 4}" rx="3.4" ry="4" class="xf-shine"/></g>`;
};
const brow = ([x, y], inner, up = true) => {
    const s = inner === "right" ? 1 : -1;
    const lift = up ? -6 : 6;
    return `<path d="M${x - 12 * s} ${y - 27} L${x + 11 * s} ${y - 27 + lift}" class="xf-line xf-thin"/>`;
};
const blush = (strength = 1) => [[63, 181], [202, 183]].map(([x, y]) => `<g class="xf-blush" opacity="${strength}">${[-7, 0, 7].map(dx => `<path d="M${x + dx - 2} ${y + 4} L${x + dx + 2} ${y - 4}"/>`).join("")}</g>`).join("");

const MOUTHS = {
    small: '<path d="M121 177 Q136 190 151 177" class="xf-line"/>',
    open: '<path d="M118 172 Q136 174 154 172 Q152 195 136 197 Q120 195 118 172 Z" class="xf-mouth" fill="url(#__ID__-mouth)"/><path d="M127 190 Q136 184 145 190 Q141 196 136 196 Q131 196 127 190 Z" class="xf-tongue"/>',
    big: '<path d="M110 169 Q136 172 162 169 Q160 202 136 204 Q112 202 110 169 Z" class="xf-mouth" fill="url(#__ID__-mouth)"/><path d="M123 196 Q136 187 149 196 Q143 203 136 203 Q129 203 123 196 Z" class="xf-tongue"/>',
    gentle: '<path d="M123 179 Q136 189 149 179" class="xf-line"/>',
    frown: '<path d="M123 191 Q136 178 149 191" class="xf-line"/>',
    wail: '<path d="M118 196 Q136 170 154 196 Q136 189 118 196 Z" class="xf-mouth" fill="url(#__ID__-mouth)"/>',
    o: '<ellipse cx="136" cy="185" rx="7.5" ry="9.5" class="xf-mouth" fill="url(#__ID__-mouth)"/>',
    flat: '<path d="M128 186 L148 183" class="xf-line"/>',
    wavy: '<path d="M117 186 q5 -5 10 0 t10 0 t10 0 t10 0" class="xf-line xf-thin"/>',
    smirk: '<path d="M122 180 Q138 190 152 175" class="xf-line"/>',
};

const FACES = {
    neutral: () => `<g class="xf-eyes is-blinking">${oval(L)}${oval(R)}</g>${MOUTHS.small}${blush(0.55)}`,
    happy: () => `<g class="xf-eyes is-blinking">${oval(L)}${oval(R)}</g>${MOUTHS.open}${blush(0.75)}`,
    joy: () => `${arc(L)}${arc(R)}${MOUTHS.big}${blush(1)}`,
    celebrate: () => `${star(L)}${star(R)}${MOUTHS.big}${blush(1)}<g class="xf-sparks"><path d="M60 128 l3 -8 l3 8 l8 3 l-8 3 l-3 8 l-3 -8 l-8 -3z"/><path d="M214 120 l2 -6 l2 6 l6 2 l-6 2 l-2 6 l-2 -6 l-6 -2z"/></g>`,
    proud: () => `${arc(L)}<g class="xf-eyes">${oval(R)}</g>${MOUTHS.smirk}${blush(0.8)}`,
    encouraging: () => `${arc(L, 12, 11, 5)}${arc(R, 12, 11, 5)}${MOUTHS.gentle}${blush(0.7)}`,
    thinking: () => `<g class="xf-eyes is-blinking xf-look-up">${oval([L[0] + 5, L[1] - 5], 11, 16)}${oval([R[0] + 5, R[1] - 5], 11, 16)}</g>${brow(R, "left", true)}${MOUTHS.flat}<g class="xf-dots"><circle cx="196" cy="124" r="3.4"/><circle cx="207" cy="118" r="3.4"/><circle cx="218" cy="112" r="3.4"/></g>`,
    surprised: () => `<g class="xf-eyes">${oval(L, 15, 15)}${oval(R, 15, 15)}</g>${MOUTHS.o}`,
    worried: () => `<g class="xf-eyes is-blinking">${oval(L, 11, 15)}${oval(R, 11, 15)}</g>${brow(L, "right", true)}${brow(R, "left", true)}${MOUTHS.wavy}`,
    sad: () => `${sadEye(L, "right")}${sadEye(R, "left")}${MOUTHS.frown}`,
    crying: () => `${closedDown(L)}${closedDown(R)}${brow(L, "right", true)}${brow(R, "left", true)}${MOUTHS.wail}
        <g class="xf-tears"><path d="M80 162 q-4 8 0 12 q4 -4 0 -12z"/><path d="M93 163 q-4 8 0 12 q4 -4 0 -12z"/><path d="M178 162 q-4 8 0 12 q4 -4 0 -12z"/><path d="M191 163 q-4 8 0 12 q4 -4 0 -12z"/></g>`,
    shy: () => `${closedDown(L, 12)}${closedDown(R, 12)}${MOUTHS.gentle}${blush(1)}`,
};

/** The SVG face for one expression; ``id`` keeps gradient ids unique when several faces share a page. */
export function faceSvg(expression, id = `xf${++counter}`) {
    const draw = FACES[expression] || FACES.neutral;
    return `<svg class="xbot-face" viewBox="0 0 300 238" aria-hidden="true" focusable="false" data-id="${id}">
        <defs><radialGradient id="${id}-eye" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#F2FDFF"/><stop offset=".45" stop-color="#7FDCFF"/><stop offset="1" stop-color="#2F8FEA"/></radialGradient>
            <linearGradient id="${id}-mouth" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF9CC4"/><stop offset="1" stop-color="#F0628F"/></linearGradient>
            <filter id="${id}-glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
        <g class="xf" filter="url(#${id}-glow)">${draw().replaceAll("__ID__", id)}</g></svg>`;
}

/** The whole head: the painted head with an empty visor, and the face on top. */
export function expressiveHead(expression = "neutral", className = "") {
    return `<span class="xbot ${className}" data-expr="${expression}" aria-hidden="true"><img class="xbot-shell" src="/img/ai-head-blank.webp" alt="" width="300" height="238" decoding="async">${faceSvg(expression)}</span>`;
}

/** Changes the face in place with a quick blink, so the change reads as the robot reacting. */
export function setExpression(head, expression) {
    if (!head || head.dataset.expr === expression) return;
    head.dataset.expr = expression;
    head.classList.add("is-switching");
    window.setTimeout(() => {
        const old = head.querySelector(".xbot-face");
        if (old) old.outerHTML = faceSvg(expression);
        head.classList.remove("is-switching");
    }, 110);
}

/** The expression for a graded test: from the checker's score and pass decision only. */
export function expressionForScore({ score, max_score: max = 100, passed, critical_violations: critical = [] }) {
    const percent = max ? (100 * Number(score || 0)) / max : 0;
    if (passed && percent >= 85) return "celebrate";
    if (passed) return "joy";
    if (critical.length && percent >= 40) return "worried";
    if (percent >= 40) return "encouraging";
    if (percent >= 20) return "sad";
    return "crying";
}
