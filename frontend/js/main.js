/** App entry: session, navigation, hash router and event delegation. */
import { api, app, closeModal, errorView, loadingView, setBar, setSubnav, setView, toast, withBusy, refreshAvatar, esc } from "./core.js";
import { assistantRoute, initAssistant } from "./assistant.js";
import { icon } from "./icons.js";
import { reminderAction, reminderState, reminderTitle } from "./reminders.js";
import { addPrivateCatalog, startTranslator } from "./translate.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderResult } from "./pages/assess.js";
import { renderFlow } from "./pages/flow.js";
import { renderPlan } from "./pages/plan.js";
import { renderProcess } from "./pages/process.js";
import { renderResources } from "./pages/resources.js";
import { renderMiniTest } from "./pages/check.js";
import { renderTests, renderTestRunner, renderTestReport } from "./pages/tests.js";
import { renderProfile } from "./pages/profile.js";
import { renderAdmin } from "./pages/admin.js";
import { renderReport } from "./pages/report.js";
import { renderFinalExam } from "./pages/roadmap.js";
import { renderContribute } from "./pages/contribute.js";
import { initEffects } from "./effects.js";
import { initLayout } from "./layout.js";
import { companionRoute } from "./companion.js";

const NAV = [
    ["Tổng quan", [["#/", "Bảng điều khiển", "dashboard"]]],
    ["Career Adapt", [["#/process", "Quy trình Career Adapt", "journey"], ["#/plan", "Kế hoạch Career Adapt", "plan"]]],
    ["Tài nguyên", [["#/resources", "Học liệu", "learn"], ["#/tests", "Kiểm tra kiến thức", "test"]]],
    ["Tài khoản", [["#/profile", "Hồ sơ", "account"]]],
];

// [pattern, title, header icon, render]
const ROUTES = [
    [/^\/$/, "Bảng điều khiển", "dashboard", () => renderDashboard()],
    [/^\/process$/, "Quy trình Career Adapt", "journey", () => renderProcess()],
    [/^\/flow(?:\/(.*))?$/, "Quy trình Career Adapt", "journey", m => renderFlow(m[1] || "")],
    [/^\/plan(?:\/(da|backend|qa))?(?:\/(overview|exam|review|gap|rank|roadmap|progress))?(?:\/(.+))?$/, "Kế hoạch Career Adapt", "plan", m => renderPlan(m[1] || "da", m[2] || "overview", m[3] || "")],
    [/^\/result\/([^/]+)$/, "Kết quả đánh giá", "check", m => renderResult(m[1])],
    [/^\/resources$/, "Học liệu đã duyệt", "learn", () => renderResources()],
    [/^\/mini\/([^/]+)$/, "Kiểm tra học phần", "quiz", m => renderMiniTest(m[1])],
    [/^\/tests$/, "Kiểm tra kiến thức", "test", () => renderTests()],
    [/^\/tests\/run\/([^/]+)$/, "Làm bài kiểm tra", "test", m => renderTestRunner(m[1])],
    [/^\/tests\/report\/([^/]+)$/, "Báo cáo bài kiểm tra", "file", m => renderTestReport(m[1])],
    [/^\/report$/, "Báo cáo năng lực", "file", () => renderReport()],
    [/^\/final-exam$/, "Bài đánh giá tổng hợp", "quiz", () => renderFinalExam()],
    [/^\/profile$/, "Hồ sơ", "account", () => renderProfile()],
    [/^\/admin(?:\/([a-z]+))?$/, "Quản trị nội dung", "admin", m => renderAdmin(m[1] || "")],
    [/^\/contribute(?:\/(.+))?$/, "Đóng góp câu hỏi", "write", m => renderContribute(m[1] || "")],
];

// Old links land on the place that replaced them.
const MOVED = { "/target": "/process", "/assess": "/process", "/gap": "/plan/da/gap", "/roadmap": "/plan/da/roadmap", "/progress": "/plan/da/progress" };

function renderNav() {
    // Experts granted the right (and administrators) also see the page for writing questions.
    const resources = app.user.contributor ? NAV.map(([title, links]) => (title === "Tài nguyên" ? [title, [...links, ["#/contribute", "Đóng góp câu hỏi", "write"]]] : [title, links])) : NAV;
    const groups = app.user.role === "admin" ? [...resources, ["Quản trị", [["#/admin", "Quản trị nội dung", "admin"]]]] : resources;
    document.getElementById("nav").innerHTML = groups.map(([title, links]) => `<div class="nav-group"><div class="nav-title">${title}</div>${links.map(([href, label, name]) =>
        `<a class="nav-link" href="${href}" data-nav="${href}">${icon(name)}<span>${label}</span></a>`).join("")}</div>`).join("");
}

function setTitle(title, name) {
    document.getElementById("page-title").textContent = title;
    document.getElementById("page-icon").innerHTML = icon(name);
}

function markActive(path) {
    const section = `#/${path.split("/")[1] || ""}`;
    const owner = { "#/result": "#/plan", "#/mini": "#/plan", "#/final-exam": "#/plan" }[section] || section;
    document.querySelectorAll("[data-nav]").forEach(link => {
        const active = link.dataset.nav === owner;
        link.classList.toggle("is-active", active);
        if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
}

function closeMenu() {
    document.getElementById("sidebar").classList.remove("is-open");
    document.getElementById("scrim").hidden = true;
    document.getElementById("menu-btn").setAttribute("aria-expanded", "false");
}

let bellData = null;

export async function refreshBell() {
    try {
        bellData = await api("/me/reminders");
        const badge = document.getElementById("bell-count");
        badge.textContent = bellData.unread_count;
        badge.hidden = !bellData.unread_count;
        document.getElementById("bell").classList.toggle("has-late", Boolean(bellData.overdue_count));
        if (!document.getElementById("bell-panel").hidden) drawBell();
    } catch { /* The bell is secondary; pages report their own errors. */ }
}

/* The bell opens a short list of the most pressing reminders; the full page is one click further. */
function bellRow(item) {
    const state = reminderState(item);
    const action = reminderAction(item);
    return `<a class="bell-item is-${state.tone}" href="${action.href}"><span class="bell-item-icon" aria-hidden="true">${icon(state.icon)}</span><span class="bell-item-text"><strong>${esc(reminderTitle(item))}</strong><span class="rm-pill is-${state.tone}">${state.label}</span></span><span class="bell-item-go">${action.label}</span></a>`;
}

function drawBell() {
    const total = bellData?.unread_count || 0;
    const items = (bellData?.active || []).slice(0, 5);
    const more = total - items.length;
    const body = items.length ? items.map(bellRow).join("") : `<div class="bell-empty">${icon("check")}<span>Không có việc nào cần xử lý.</span></div>`;
    const extra = more > 0 ? `<span class="sub small">và ${more} nhắc nhở khác</span>` : "";
    document.getElementById("bell-panel").innerHTML = `<div class="bell-head"><strong>Nhắc nhở</strong><span class="badge badge-muted">${total}</span></div><div class="bell-list">${body}</div><div class="bell-foot">${extra}<a class="btn btn-secondary btn-sm" href="#/plan/da/progress">Xem tất cả</a></div>`;
}

function setBell(open) {
    const panel = document.getElementById("bell-panel");
    if (panel.hidden === !open) return;
    panel.hidden = !open;
    document.getElementById("bell").setAttribute("aria-expanded", String(open));
    if (open) { drawBell(); refreshBell(); }
}

function initBell() {
    document.getElementById("bell").addEventListener("click", event => { event.stopPropagation(); setBell(document.getElementById("bell-panel").hidden); });
    document.addEventListener("click", event => { if (!event.target.closest(".bell-wrap") || event.target.closest("#bell-panel a")) setBell(false); });
    document.addEventListener("keydown", event => { if (event.key === "Escape") setBell(false); });
    document.addEventListener("reminders-changed", refreshBell);
    // A reminder's snooze menu closes when the click lands anywhere else.
    document.addEventListener("click", event => document.querySelectorAll("details.rm-menu[open]").forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }));
}

/* 5.57: the new page fades in (opacity only, so fixed and sticky parts are untouched); off with reduced motion. */
function enterView() {
    const view = document.getElementById("view");
    view.classList.remove("is-entering");
    void view.offsetWidth;
    view.classList.add("is-entering");
    view.addEventListener("animationend", event => { if (event.target === view) view.classList.remove("is-entering"); }, { once: true });
}

async function route(event) {
    const path = (window.location.hash.slice(1) || "/").split("?")[0];
    const moved = MOVED[path] || (path.startsWith("/assess/") || path.startsWith("/target/") ? "/process" : null);
    if (moved) { window.location.replace(`#${moved}`); return; }
    app.cleanup?.();
    app.cleanup = null;
    app.actions = {};
    app.forms = {};
    closeModal();
    closeMenu();
    setBell(false);
    markActive(path);
    document.body.classList.toggle("flow-mode", path.startsWith("/flow") || path === "/final-exam");
    assistantRoute(path);
    setBar();
    setSubnav();
    const match = ROUTES.map(([pattern, title, name, render]) => ({ found: path.match(pattern), title, name, render })).find(item => item.found);
    if (!match) {
        setTitle("Không tìm thấy trang", "info");
        setView(`<div class="empty"><strong>Không tìm thấy trang này</strong><a class="btn btn-primary" href="#/">Về bảng điều khiển</a></div>`);
        return;
    }
    setTitle(match.title, match.name);
    document.title = `${match.title} · CareerAdapt AI`;
    setView(loadingView(undefined, { page: true }));
    window.scrollTo(0, 0);
    // A link or a menu took the learner here: focus moves to the content, so a screen reader starts at the new page
    // and the next Tab continues from it. A page that focuses its own field afterwards still wins.
    if (event?.type === "hashchange") document.getElementById("view").focus({ preventScroll: true });
    try {
        await match.render(match.found);
    } catch (error) {
        setView(errorView(error.message));
    }
    enterView();
    // 5.62: the AI robot may come to the part of this page where it can help (companion.js).
    companionRoute(path);
    refreshBell();
}

/* Tabs (5.57): in any tab list, arrow keys, Home and End move to a tab and open it. A list with its own keys
   (Hồ sơ) handles them first and marks the event as handled. */
const TAB_KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
document.addEventListener("keydown", event => {
    if (event.defaultPrevented || !TAB_KEYS.includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
    const tab = event.target.closest?.('[role="tab"]');
    const list = tab?.closest('[role="tablist"]');
    if (!list) return;
    const tabs = [...list.querySelectorAll('[role="tab"]')].filter(item => !item.disabled && item.getClientRects().length);
    const index = tabs.indexOf(tab);
    if (index < 0) return;
    event.preventDefault();
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    const next = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] : tabs[(index + step + tabs.length) % tabs.length];
    const position = tabs.indexOf(next);
    const label = list.getAttribute("aria-label");
    next.focus();
    next.click();
    // Some lists redraw themselves on click; focus then goes to the same tab in the new list.
    requestAnimationFrame(() => {
        if (next.isConnected) return;
        const fresh = [...document.querySelectorAll('[role="tablist"]')].find(item => item.getAttribute("aria-label") === label);
        fresh?.querySelectorAll('[role="tab"]')[position]?.focus();
    });
});

document.addEventListener("click", event => {
    if (event.target.matches("[data-modal-backdrop]")) { closeModal(); return; }
    const closer = event.target.closest("[data-close-modal]");
    if (closer) { closeModal(); return; }
    const element = event.target.closest("[data-act]");
    if (!element) return;
    const name = element.dataset.act;
    if (name === "reload") { route(); return; }
    const handler = app.actions[name];
    if (handler) { event.preventDefault(); handler(element, event); }
});
document.addEventListener("submit", event => {
    const form = event.target.closest("[data-form]");
    const handler = form && app.forms[form.dataset.form];
    if (!handler) return;
    event.preventDefault();
    // The event goes along so a form with several submit buttons knows which one was pressed (event.submitter).
    withBusy(event.submitter || form.querySelector("[type=submit]"), () => handler(form, event));
});
document.addEventListener("keydown", event => { if (event.key === "Escape") closeModal(); });
window.addEventListener("hashchange", route);
document.getElementById("menu-btn").addEventListener("click", () => {
    const open = document.getElementById("sidebar").classList.toggle("is-open");
    document.getElementById("scrim").hidden = !open;
    document.getElementById("menu-btn").setAttribute("aria-expanded", String(open));
});
document.getElementById("scrim").addEventListener("click", closeMenu);
document.getElementById("logout").addEventListener("click", async () => {
    try {
        await api("/auth/logout", { method: "POST", body: {} });
    } catch (error) {
        toast(error.message, "bad");
        return;
    }
    window.location.href = "/login";
});

window.i18n.onChange(async lang => {
    await api("/auth/me", { method: "PATCH", body: { full_name: app.user.full_name, phone: app.user.phone || "", preferred_language: lang } }).catch(() => {});
    window.location.reload();
});

async function start() {
    window.careerTheme.mark();
    try {
        const me = await api("/auth/me");
        app.user = me.user;
        // A new browser follows the account; a choice made in this browser wins and is saved back.
        if (app.user.preferred_language && !window.i18n.hasStoredChoice()) window.i18n.setLang(app.user.preferred_language, { silent: true });
        await startTranslator();
        app.caps = await api("/system/capabilities");
    } catch (error) {
        setView(errorView(error.message));
        return;
    }
    document.getElementById("user-name").textContent = app.user.full_name;
    document.getElementById("user-role").textContent = app.user.role === "admin" ? "Quản trị viên" : "Học viên";
    refreshAvatar();
    document.getElementById("app-version").textContent = `v${document.documentElement.dataset.build} · CareerAdapt AI`;
    if (app.user.role === "admin") api("/i18n/private-catalog").then(addPrivateCatalog).catch(() => {});
    renderNav();
    initLayout();
    initAssistant();
    initBell();
    initEffects();
    route();
}
start();
