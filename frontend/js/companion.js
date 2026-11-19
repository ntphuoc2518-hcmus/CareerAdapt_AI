/**
 * AI moments (5.62, reworked in 5.63 and 5.64): when the learner reaches a part of a page where the AI can help, the
 * CareerAdapt robot flies out of the face in the Assistant button to just above it, says one short thing about that
 * part and offers one or two questions for the real Assistant. It never covers the middle of the page: the part it
 * talks about gets a soft glowing outline instead, and the bubble names it (a click on the name scrolls there).
 * It arrives in steps (the face in the button squashes and a ring bursts from it, the robot rises out of it and lands
 * with sparks, the bubble unfolds from the robot, the words appear as if typed, the questions slide in) and leaves the
 * opposite way, back into the button, whose face then pops back. Each moment shows at most once per session
 * and once per page visit, never during a test (the Assistant is closed or locked there), over a dialog, or while the
 * Assistant panel is open. Learners can turn the moments off here and on again in Hồ sơ.
 *
 * The robot only reads what the page already shows and only passes questions on; answers come from the Assistant
 * (the learner's own data and the approved knowledge base). It never scores, decides or writes questions, so there is
 * no moment on Đóng góp câu hỏi, on test reports (the Assistant has no tool for them) or on the admin pages.
 */
import { toast } from "./core.js";
import { expressiveHead } from "./faces.js";
import { icon } from "./icons.js";
import { translateText } from "./translate.js";
import { askAssistant, assistantReady } from "./assistant.js";

const OFF_KEY = "careeradapt_ai_moments";
const SEEN_KEY = "careeradapt_ai_moments_seen";
const DWELL_MS = 900; // how long the part must stay on screen before the robot comes
const STAY_MS = 16000; // how long it waits for the learner before leaving
const AWAY_MS = 1500; // how long its part may be off screen before it leaves
const LESSON = /^\/plan\/[a-z]+\/roadmap\/lesson\//;
const heading = target => target.querySelector("h2, h3")?.textContent.trim() || "";
const skillQuestion = skill => `Kỹ năng “${skill}” của tôi chưa đạt mức JD yêu cầu. Tôi nên học và luyện gì trước để bù?`;

/*
 * route: where the moment can happen; target: the part of the page it belongs to; when: an extra check on the page;
 * read: picks the words it needs from what is on screen (so nothing is made up); about: the name of that part;
 * asks: a task of the server's AI catalogue (task_engine.py) or a question, sent like a typed one.
 */
const MOMENTS = [
    {
        id: "dashboard-progress", route: /^\/$/, target: "#view .progress-card", mood: "happy", about: heading,
        text: () => "Muốn mình tóm tắt tiến độ và chỉ ra việc nên làm tiếp?",
        asks: [{ task: "journey_report", label: "Tổng hợp hành trình của tôi", icon: "route" }, { task: "learning_guide", label: "Tôi nên học gì tiếp theo?", icon: "play" }],
    },
    {
        id: "dashboard-start", route: /^\/$/, target: '#view a.link-card[href="#/plan"]', when: () => !document.querySelector("#view .progress-card"), mood: "happy",
        about: target => target.querySelector("strong")?.textContent.trim(),
        text: () => "Mới bắt đầu? Mình giải thích nhanh 6 bước của Quy trình Career Adapt nhé.",
        asks: [{ question: () => "Quy trình Career Adapt gồm những bước nào và mỗi bước để làm gì?", label: "Giải thích 6 bước", icon: "journey" }],
    },
    {
        id: "resources", route: /^\/resources$/, target: "#view .grid-2 > .card", mood: "happy", about: () => "Học liệu đã duyệt",
        text: () => "Chưa biết bắt đầu từ đâu? Mình chọn học liệu hợp với kỹ năng bạn còn thiếu.",
        asks: [{ task: "learning_guide", label: "Tôi nên học gì tiếp theo?", icon: "play" }, { question: () => "Trong các học liệu đã duyệt, học liệu nào hợp nhất với kỹ năng tôi còn thiếu?", label: "Gợi ý học liệu cho tôi", icon: "learn" }],
    },
    {
        id: "tests", route: /^\/tests$/, target: "#view .test-card", mood: "encouraging", about: () => "Chọn bài",
        text: () => "Không biết nên luyện bài nào trước? Mình gợi ý theo khoảng cách kỹ năng của bạn.",
        asks: [{ question: () => "Dựa trên khoảng cách kỹ năng của tôi, tôi nên luyện bài kiểm tra nhanh nào trước và vì sao?", label: "Nên luyện bài nào trước?", icon: "test" }, { task: "skill_analysis", label: "Phân tích kỹ năng của tôi", icon: "pulse" }],
    },
    {
        id: "report", route: /^\/report$/, target: "#view .report-section .plan-table", mood: "proud", about: () => "Kỹ năng theo mục tiêu",
        text: () => "Muốn mình tóm tắt báo cáo này thành vài ý chính?",
        asks: [{ task: "journey_report", label: "Tổng hợp hành trình của tôi", icon: "route" }, { question: () => "Dựa trên kết quả đã xác thực của tôi, nên trình bày kỹ năng trong CV thế nào cho đúng sự thật?", label: "Viết phần kỹ năng trong CV", icon: "write" }],
    },
    {
        id: "plan-result-skill", route: /^\/plan\/[a-z]+\/exam$/, target: "#view .rs-row:has(.badge-warn)", mood: "encouraging",
        read: target => target.querySelector(".rs-name strong")?.textContent.trim(), about: (target, skill) => skill,
        text: skill => `“${skill}” còn thiếu so với mức JD. Muốn mình chỉ cách bù phần này?`,
        asks: [{ question: skillQuestion, label: "Cách bù kỹ năng này", icon: "target" }],
    },
    {
        id: "plan-gap-skill", route: /^\/plan\/[a-z]+\/gap$/, target: "#view .gap-row.is-todo", mood: "encouraging",
        read: target => target.querySelector(".gap-name > span")?.textContent.trim(), about: (target, skill) => skill,
        text: skill => `“${skill}” chưa đạt mức JD yêu cầu. Muốn mình chỉ cách bù khoảng cách này?`,
        asks: [{ question: skillQuestion, label: "Cách bù kỹ năng này", icon: "target" }, { task: "readiness_advice", label: "Tư vấn mức sẵn sàng", icon: "admin" }],
    },
    {
        id: "plan-roadmap-next", route: /^\/plan\/[a-z]+\/roadmap$/, target: "#view .jr-next", mood: "happy",
        read: target => target.querySelector(".jr-next-title")?.textContent.trim(), about: () => "Bài học tiếp theo",
        text: title => `Bài tiếp theo là “${title}”. Muốn mình nói nhanh bài này học gì và vì sao nên học bây giờ?`,
        asks: [{ question: title => `Bài học “${title}” trong lộ trình của tôi học những gì và vì sao nên học bây giờ?`, label: "Bài này học gì?", icon: "learn" }],
    },
    {
        id: "lesson-mistakes", route: LESSON, target: "#view .jr-mistakes", mood: "encouraging", about: heading,
        read: target => target.querySelector(".jr-mistake-list strong")?.textContent.trim(),
        text: check => `Lần trước bạn chưa đạt “${check}”. Muốn mình giải thích lại phần này?`,
        asks: [{ question: check => `Giải thích giúp tôi tiêu chí “${check}” và cách làm đúng phần này.`, label: "Giải thích phần này", icon: "chat" }],
    },
    {
        id: "lesson-practice", route: LESSON, target: "#view .jr-practice", when: () => !document.querySelector("#view .jr-mistakes"), mood: "happy",
        read: target => target.querySelector("h3")?.textContent.trim(), about: (target, title) => title,
        text: () => "Bí ở bài thực hành? Mình gợi ý hướng làm, không làm thay bạn.",
        asks: [{ question: title => `Gợi ý hướng làm bài thực hành “${title}” theo từng bước, không đưa đáp án hoàn chỉnh.`, label: "Gợi ý hướng làm", icon: "sparkles" }],
    },
    {
        id: "profile-goals", route: /^\/profile$/, target: "#pf-panel-goals:not([hidden])", mood: "happy", about: heading,
        text: () => "Muốn mình gợi ý số giờ học mỗi tuần để theo kịp lộ trình?",
        asks: [{ question: () => "Dựa trên lộ trình và tiến độ học của tôi, mỗi tuần tôi nên dành bao nhiêu giờ học để kịp lịch?", label: "Gợi ý số giờ học", icon: "calendar" }],
    },
];

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const storage = (store, action) => { try { return action(window[store]); } catch { return null; } };
const later = (ms, action) => setTimeout(action, reducedMotion() ? 0 : ms);

export const aiMomentsEnabled = () => storage("localStorage", s => s.getItem(OFF_KEY)) !== "off";
export function setAiMoments(on) {
    storage("localStorage", s => s.setItem(OFF_KEY, on ? "on" : "off"));
    if (!on) leave(true);
}
const seen = () => new Set(JSON.parse(storage("sessionStorage", s => s.getItem(SEEN_KEY)) || "[]"));
function markSeen(id) {
    const ids = seen();
    ids.add(id);
    storage("sessionStorage", s => s.setItem(SEEN_KEY, JSON.stringify([...ids])));
}

/* --- One visit to one page --- */
let visit = null;

function stopVisit() {
    if (!visit) return;
    visit.watcher?.disconnect();
    visit.viewer?.disconnect();
    clearTimeout(visit.dwell);
    clearTimeout(visit.scan);
    visit = null;
}

/** Called after every route change: finds the moments of this page and waits for their part to come into view. */
export function companionRoute(path) {
    leave(true);
    stopVisit();
    if (!aiMomentsEnabled()) return;
    const done = seen();
    const candidates = MOMENTS.filter(moment => moment.route.test(path) && !done.has(moment.id));
    if (!candidates.length) return;
    const view = document.getElementById("view");
    visit = { candidates, watched: new Map(), shown: false };
    const current = visit;
    current.viewer = new IntersectionObserver(entries => {
        if (visit !== current || current.shown) return;
        const entry = entries.find(item => item.isIntersecting && item.intersectionRatio >= 0.35);
        if (!entry) { if (entries.some(item => !item.isIntersecting)) clearTimeout(current.dwell); return; }
        clearTimeout(current.dwell);
        current.dwell = setTimeout(() => {
            if (visit !== current || current.shown || !entry.target.isConnected) return;
            arrive(current.watched.get(entry.target), entry.target);
        }, DWELL_MS);
    }, { threshold: [0, 0.35, 0.6] });
    // Parts of a page arrive late (tabs, lazy panels), so the page is scanned again when it changes.
    const scan = () => {
        if (visit !== current || current.shown) return;
        for (const moment of current.candidates) {
            const target = document.querySelector(moment.target);
            if (!target || current.watched.has(target) || (moment.when && !moment.when())) continue;
            current.watched.set(target, moment);
            current.viewer.observe(target);
        }
    };
    current.watcher = new MutationObserver(() => { clearTimeout(current.scan); current.scan = setTimeout(scan, 250); });
    if (view) current.watcher.observe(view, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    current.scan = setTimeout(scan, 1200);
}

/* --- The robot at its corner --- */
let shown = null;

function blocked() {
    return !assistantReady() || document.querySelector("#modal-root .modal") || document.hidden;
}

function spotlight(target) {
    target.classList.remove("ai-spotlight");
    void target.offsetWidth;
    target.classList.add("ai-spotlight");
}

/* The robot comes out of the Assistant button and goes back into it: the face in the button squashes and
   dims while the robot is out ("launch"), then pops back when it returns ("absorb"). */
const fabButton = () => document.getElementById("assistant-fab");
let fabTimer = null;
// Opening the assistant answers the hint too, so the robot goes back at once.
document.addEventListener("click", event => { if (shown && event.target.closest?.("#assistant-fab")) leave(true); }, true);

function fabState(state) {
    const button = fabButton();
    clearTimeout(fabTimer);
    if (!button) return;
    button.classList.remove("is-launching", "is-absorbing");
    if (state === "launch") {
        button.classList.add("is-away", "is-launching");
        fabTimer = later(650, () => button.classList.remove("is-launching"));
        return;
    }
    button.classList.remove("is-away");
    if (state !== "absorb" || reducedMotion()) return;
    void button.offsetWidth;
    button.classList.add("is-absorbing");
    fabTimer = setTimeout(() => button.classList.remove("is-absorbing"), 650);
}

/** The distance from the robot's place to the face in the button, for the flight out and back. */
function launchFrom(element) {
    const face = fabButton()?.querySelector(".ai-avatar-fab");
    if (!face) return;
    const from = face.getBoundingClientRect();
    const bot = element.querySelector(".ai-moment-bot").getBoundingClientRect();
    element.style.setProperty("--from-x", `${Math.round(from.left + from.width / 2 - bot.left - bot.width / 2)}px`);
    element.style.setProperty("--from-y", `${Math.round(from.top + from.height / 2 - bot.top - bot.height / 2)}px`);
}

function arrive(moment, target) {
    if (!moment || !visit || blocked()) return;
    const value = moment.read ? moment.read(target) : "";
    if (moment.read && !value) return;
    visit.shown = true;
    markSeen(moment.id);
    const about = moment.about ? moment.about(target, value) : "";
    const element = document.createElement("aside");
    element.className = "ai-moment";
    element.setAttribute("aria-label", "Gợi ý của Trợ lý AI");
    const asks = moment.asks.map((ask, index) => `<button type="button" class="ai-moment-ask" data-index="${index}" style="--i:${index}">${icon(ask.icon || "sparkles")}<span>${ask.label}</span></button>`).join("");
    element.innerHTML = `<span class="ai-moment-bot" aria-hidden="true"><span class="ai-moment-burst"></span><span class="ai-moment-halo"></span>${expressiveHead(moment.mood || "happy", "ai-moment-head")}<span class="ai-moment-sparks"><i></i><i></i><i></i><i></i><i></i></span></span>
        <div class="ai-moment-bubble"><div class="ai-moment-meta">${icon("sparkles")}<strong>Trợ lý AI</strong><button type="button" class="ai-moment-close" aria-label="Đóng gợi ý">${icon("close")}</button></div>
            ${about ? `<button type="button" class="ai-moment-about" title="Xem phần này">${icon("target")}<span>Về:</span><span class="ai-moment-about-name"></span></button>` : ""}
            <p class="ai-moment-text" aria-live="polite"><span class="ai-moment-typing" aria-hidden="true"><i></i><i></i><i></i></span></p>
            <div class="ai-moment-asks">${asks}</div>
            <button type="button" class="ai-moment-off">Tắt gợi ý trên các trang</button></div>`;
    if (about) element.querySelector(".ai-moment-about-name").textContent = about;
    document.body.append(element);
    document.body.classList.add("has-ai-moment");
    launchFrom(element);
    shown = { element, target, moment, value, timer: null, away: null };
    const current = shown;
    // In steps: the face in the Assistant button squashes and the robot flies up out of it with a light burst,
    // the bubble unfolds from the robot, then the words and the questions.
    fabState("launch");
    requestAnimationFrame(() => { element.classList.add("is-in"); spotlight(target); });
    later(520, () => { if (shown === current) element.classList.add("is-open"); });
    later(1150, () => {
        if (shown !== current) return;
        element.querySelector(".ai-moment-text").textContent = moment.text(value);
        element.classList.add("is-said");
    });
    const wait = () => { clearTimeout(current.timer); current.timer = setTimeout(() => leave(), STAY_MS); };
    element.addEventListener("pointerenter", () => clearTimeout(current.timer));
    element.addEventListener("pointerleave", wait);
    element.addEventListener("focusin", () => clearTimeout(current.timer));
    element.addEventListener("focusout", event => { if (!element.contains(event.relatedTarget)) wait(); });
    element.addEventListener("keydown", event => { if (event.key === "Escape") leave(); });
    element.addEventListener("click", event => {
        if (event.target.closest(".ai-moment-close")) { leave(); return; }
        if (event.target.closest(".ai-moment-about")) {
            target.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
            spotlight(target);
            return;
        }
        if (event.target.closest(".ai-moment-off")) {
            setAiMoments(false);
            toast("Đã tắt gợi ý của Trợ lý AI. Bật lại trong Hồ sơ, mục Nhắc nhở.");
            return;
        }
        const button = event.target.closest(".ai-moment-ask");
        if (!button) return;
        const ask = moment.asks[Number(button.dataset.index)];
        leave(true);
        // Sent in the language on screen, like a question the learner typed.
        if (ask.task) askAssistant(translateText(ask.label), ask.task, translateText(ask.label));
        else askAssistant(translateText(ask.question(value)));
    });
    window.addEventListener("scroll", watchPart, { passive: true, capture: true });
    wait();
}

/** The robot stays while its part is on screen; once the part has been gone a moment, it leaves. */
function watchPart() {
    if (!shown) return;
    const { target } = shown;
    if (!target.isConnected || blocked()) { leave(true); return; }
    const box = target.getBoundingClientRect();
    const away = box.bottom < 64 || box.top > window.innerHeight - 40;
    if (away && !shown.away) shown.away = setTimeout(() => leave(), AWAY_MS);
    if (!away && shown.away) { clearTimeout(shown.away); shown.away = null; }
}

/** The bubble folds back into the robot, which flies back into the Assistant button
    (at once when the page changes or a question was sent). */
function leave(now = false) {
    if (!shown) return;
    const { element, target, timer, away } = shown;
    clearTimeout(timer);
    clearTimeout(away);
    shown = null;
    window.removeEventListener("scroll", watchPart, { capture: true });
    target.classList.remove("ai-spotlight");
    document.body.classList.remove("has-ai-moment");
    if (now || reducedMotion()) { element.remove(); fabState("rest"); return; }
    element.classList.add("is-out");
    clearTimeout(fabTimer);
    fabTimer = setTimeout(() => fabState("absorb"), 560);
    setTimeout(() => element.remove(), 700);
}
