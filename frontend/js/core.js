/** Shared client: API calls, escaping, page states, toasts, modals and event delegation. */
import { icon } from "./icons.js";

export const app = { user: null, caps: {}, skills: [], actions: {}, forms: {}, cleanup: null };

export const SKILL_NAMES = { SQL: "SQL", DATA_QUALITY: "Chất lượng dữ liệu", PYTHON: "Python", DATA_VIZ: "Trực quan hóa", WRITTEN_COMM: "Giao tiếp viết", STATISTICS: "Thống kê" };
export const skillName = code => SKILL_NAMES[code] || code || "Không gắn kỹ năng";
export const LEVEL_NAMES = { INTERN: "Thực tập", FRESHER: "Fresher", JUNIOR: "Junior", MIDDLE: "Middle", SENIOR: "Senior" };
export const SOURCE_TYPES = { JD_USER: "JD bạn nhập", JD_LIBRARY: "JD trong thư viện", DEFAULT: "Bộ mục tiêu mặc định", LEGACY_PROFILE: "Hồ sơ yêu cầu cũ", LEGACY_CUSTOM: "JD tùy chỉnh cũ" };
export const REQUIREMENT_TYPES = { REQUIRED: "Bắt buộc", PREFERRED: "Ưu tiên", UNSPECIFIED: "Chưa rõ", NOT_IN_JD: "Không có trong JD" };

const STATUS = {
    GRADED: ["Đã chấm", "good"], REVIEWED_APPROVED: ["Đã duyệt", "good"], NEEDS_REVIEW: ["Cần kiểm tra", "warn"], PENDING_RETRY: ["Chờ chấm lại", "warn"],
    INCOMPLETE: ["Chưa hoàn thành", "muted"], INVALID: ["Không hợp lệ", "bad"], RECEIVED: ["Đã nhận", "muted"], PROCESSING: ["Đang chấm", "muted"],
    PASSED: ["Đạt", "good"], FAILED: ["Chưa đạt", "bad"], PENDING: ["Đang chờ làm", "warn"], UNAVAILABLE: ["Thiếu câu hỏi", "muted"], CANCELLED: ["Đã hủy", "muted"],
    SCHEDULED: ["Đã lên lịch", ""], DUE: ["Đến hạn", "warn"], SNOOZED: ["Tạm hoãn", "muted"], COMPLETED: ["Hoàn thành", "good"], SUPERSEDED: ["Đã thay lịch", "muted"],
    NOT_STARTED: ["Chưa bắt đầu", "muted"], IN_PROGRESS: ["Đang học", ""], PAUSED: ["Tạm dừng", "muted"], RUNNING: ["Đang chạy", ""], SUBMITTED: ["Đã nộp, chờ chấm", "warn"], GRADING: ["Đang chấm", "warn"], ENDED: ["Đã kết thúc", "muted"],
    APPROVED: ["Đã duyệt", "good"], DRAFT: ["Nháp", "muted"], HIDDEN: ["Tạm ẩn", "bad"], EXPIRED: ["Hết hiệu lực", "bad"],
    OK: ["Link hoạt động", "good"], BROKEN: ["Link lỗi", "bad"], UNKNOWN: ["Cần kiểm tra thủ công", "warn"], UNCHECKED: ["Chưa kiểm tra link", "muted"], UNVERIFIED_CONTENT: ["Chưa đối chiếu nội dung", "warn"],
    IN_SCOPE: ["Đúng phạm vi", "good"], OUT_OF_SCOPE: ["Ngoài phạm vi", "bad"], UNCERTAIN: ["Cần xác nhận", "warn"],
};
export function statusBadge(code) {
    const [label, tone] = STATUS[code] || [code || "—", "muted"];
    return `<span class="badge ${tone ? `badge-${tone}` : ""}">${esc(label)}</span>`;
}

export function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}
/** Only http(s) and same-site paths become links; anything else renders as text. */
export function safeUrl(url) {
    return /^(https?:\/\/|\/)/i.test(String(url || "")) ? esc(url) : "#";
}
export const getLang = () => window.i18n?.getLang() || "vi";
export const LOCALE = () => (getLang() === "en" ? "en-GB" : "vi-VN");
export const fmtDate = value => {
    if (!value) return "—";
    const date = new Date(String(value).length === 10 ? `${value}T00:00:00` : value);
    return Number.isNaN(date.getTime()) ? esc(value) : date.toLocaleDateString(LOCALE());
};
export const fmtDateTime = value => {
    const date = new Date(value);
    return value && !Number.isNaN(date.getTime()) ? date.toLocaleString(LOCALE(), { dateStyle: "short", timeStyle: "short" }) : "—";
};
export const fmtHours = value => `${Number(value || 0).toLocaleString(LOCALE(), { maximumFractionDigits: 1 })} giờ`;
export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(16).slice(2)}`);

function csrfToken() {
    const entry = document.cookie.split(";").map(item => item.trim()).find(item => /^(__Host-)?careeradapt_csrf=/.test(item));
    return entry ? decodeURIComponent(entry.slice(entry.indexOf("=") + 1)) : "";
}

export class ApiError extends Error {
    constructor(message, status) { super(message); this.status = status; }
}

/** Every call goes to the server; there is no offline or simulated mode. */
/** The user's picture if they uploaded one, otherwise their initial. The version busts the browser cache after a change. */
export function avatarMarkup(user) {
    const initial = esc((user?.full_name || "?").trim().slice(0, 1).toUpperCase());
    return user?.avatar_version ? `<img src="/api/v1/auth/me/avatar?v=${encodeURIComponent(user.avatar_version)}" alt="" decoding="async">` : initial;
}

/** Updates every place that shows the signed-in user's picture. */
export function refreshAvatar(user) {
    if (user) app.user = { ...app.user, ...user };
    document.querySelectorAll("[data-user-avatar]").forEach(element => { element.innerHTML = avatarMarkup(app.user); element.classList.toggle("has-photo", Boolean(app.user.avatar_version)); });
}

/* An in-app page to return to after signing in: "#/" and route characters only, never a query or another origin. */
const RETURN_KEY = "ca-return-to";
const RETURN_HASH = /^#\/[A-Za-z0-9_\-/]{0,200}$/;

export async function api(path, { method = "GET", body, form } = {}) {
    const headers = {};
    if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
        headers["X-Language"] = getLang();
        response = await fetch(`/api/v1${path}`, { method, headers, credentials: "same-origin", cache: "no-store", body: form || (body !== undefined ? JSON.stringify(body) : undefined) });
    } catch {
        throw new ApiError("Không kết nối được máy chủ. Hãy kiểm tra máy chủ đang chạy rồi thử lại.", 0);
    }
    if (response.status === 401) {
        // Remember the page so signing in again returns here instead of the dashboard (audit 2026-11-18).
        try { if (RETURN_HASH.test(window.location.hash)) sessionStorage.setItem(RETURN_KEY, window.location.hash); } catch { /* storage may be blocked */ }
        window.location.href = "/login";
        throw new ApiError("Phiên đăng nhập đã hết hạn.", 401);
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
        const message = data?.error?.message;
        throw new ApiError(typeof message === "string" ? message : `Máy chủ báo lỗi (${response.status}).`, response.status);
    }
    return data;
}

export function toast(message, tone = "") {
    const element = document.createElement("div");
    element.className = `toast ${tone ? `toast-${tone}` : ""}`;
    element.textContent = message;
    document.getElementById("toasts").append(element);
    setTimeout(() => element.remove(), 4600);
}

export const loadingView = (text = "Đang tải dữ liệu...") => `<div class="loading"><span class="spinner" aria-hidden="true"></span>${esc(text)}</div>`;
export const errorView = message => `<div class="alert alert-bad" role="alert"><div><strong>Không tải được dữ liệu.</strong><br>${esc(message)}<div class="row" style="margin-top:8px"><button class="btn btn-secondary btn-sm" data-act="reload">Thử lại</button></div></div></div>`;
export const emptyView = (title, text, action = "") => `<div class="empty"><strong>${esc(title)}</strong><span>${esc(text)}</span>${action}</div>`;
const ALERT_ICONS = { info: "info", warn: "alert", bad: "alert", good: "check" };
/**
 * AI comments and system explanations arrive as plain text. They are shown as short lines, never one long block:
 * existing line breaks and "- " bullets are kept; one or two sentences become separate lines; three or more become
 * a lead line plus bullets; a "Label: a, b, c." sentence becomes a small heading over its own list.
 */
export function formatText(text) {
    const clean = String(text ?? "").trim();
    if (!clean) return "";
    const bullet = /^\s*[-•*]\s+/;
    const sentences = clean.includes("\n")
        ? clean.split(/\n+/).map(line => line.trim()).filter(Boolean)
        : clean.split(/(?<=[.!?;])\s+(?=[\p{Lu}\d(])/u).map(line => line.trim()).filter(Boolean);
    const listMode = sentences.length >= 3 || sentences.some(line => bullet.test(line));
    const html = [];
    let items = [];
    const flush = () => { if (items.length) { html.push(`<ul class="text-list">${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul>`); items = []; } };
    sentences.forEach((line, index) => {
        const labelled = line.replace(bullet, "").match(/^([^:]{2,40}):\s*(.+?)\.?$/);
        if (labelled && labelled[2].includes(",")) {
            flush();
            html.push(`<p class="text-label">${esc(labelled[1])}</p>`);
            items = labelled[2].split(/\s*,\s*/).filter(Boolean).map(item => item.charAt(0).toLocaleUpperCase("vi") + item.slice(1));
            flush();
        } else if (labelled && !bullet.test(line) && labelled[2].length <= 60 && !/^[0-9]/.test(labelled[2])) {
            // "Trình độ đã xác thực: Chưa có nền tảng (mức 0/3)." reads as a label with its value on the next line.
            flush();
            html.push(`<p class="text-label">${esc(labelled[1])}</p><p class="text-value">${esc(labelled[2])}</p>`);
        } else if (!listMode || (index === 0 && !bullet.test(line))) {
            flush();
            html.push(index === 0 && listMode ? `<p class="text-lead">${esc(line)}</p>` : `<p>${esc(line)}</p>`);
        } else {
            items.push(line.replace(bullet, ""));
        }
    });
    flush();
    return `<div class="text-blocks">${html.join("")}</div>`;
}

export const alertBox = (tone, html) => `<div class="alert alert-${tone}">${icon(ALERT_ICONS[tone] || "info")}<div>${html}</div></div>`;

export function setView(html) {
    document.getElementById("view").innerHTML = html;
}
/** Fixed bar of the process screen and tab row of the plan page; empty hides them. */
export function setBar(html = "") {
    const bar = document.getElementById("flow-bar");
    bar.innerHTML = html;
    bar.hidden = !html;
}
export function setSubnav(html = "") {
    const nav = document.getElementById("subnav");
    nav.innerHTML = html;
    nav.hidden = !html;
}

export const getTheme = () => window.careerTheme.get();
export const saveTheme = theme => window.careerTheme.set(theme);

/** Page registration: `actions` handle [data-act] clicks and `forms` handle [data-form] submits. */
export function register({ actions = {}, forms = {}, cleanup = null }) {
    Object.assign(app.actions, actions);
    Object.assign(app.forms, forms);
    if (cleanup) {
        const previous = app.cleanup;
        app.cleanup = () => { previous?.(); cleanup(); };
    }
}

export async function withBusy(button, task) {
    if (button) { button.classList.add("is-busy"); button.disabled = true; }
    try {
        return await task();
    } catch (error) {
        toast(error.message || "Có lỗi xảy ra.", "bad");
        return undefined;
    } finally {
        if (button) { button.classList.remove("is-busy"); button.disabled = false; }
    }
}

export function formData(form) {
    return Object.fromEntries(new FormData(form).entries());
}

export function openModal(html, { wide = false, drawer = false } = {}) {
    closeModal();
    const root = document.getElementById("modal-root");
    root.innerHTML = `<div class="modal-backdrop ${drawer ? "is-drawer" : ""}" data-modal-backdrop><div class="modal ${wide ? "modal-wide" : ""} ${drawer ? "modal-drawer" : ""}" role="dialog" aria-modal="true">${html}</div></div>`;
    root.querySelector("input, select, textarea, button")?.focus();
}
export function closeModal() {
    document.getElementById("modal-root").innerHTML = "";
}

export function confirmDialog(title, text, { confirmLabel = "Xác nhận", danger = false } = {}) {
    return new Promise(resolve => {
        openModal(`<h2>${esc(title)}</h2><p class="prose">${esc(text)}</p><div class="modal-actions"><button class="btn btn-secondary" data-dialog="no">Hủy</button><button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-dialog="yes">${esc(confirmLabel)}</button></div>`);
        document.getElementById("modal-root").addEventListener("click", function handler(event) {
            const choice = event.target.closest("[data-dialog]")?.dataset.dialog;
            if (!choice) return;
            event.currentTarget.removeEventListener("click", handler);
            closeModal();
            resolve(choice === "yes");
        });
    });
}

/** Options for a mode-aware level display; an unmeasured skill is shown as such, never as 0. */
export const levelText = level => (level === null || level === undefined ? "Chưa đánh giá" : `Mức ${level}`);

const DRAFT_PREFIX = "careeradapt_draft_";
export const drafts = {
    read(key) { try { return JSON.parse(localStorage.getItem(DRAFT_PREFIX + key) || "null"); } catch { return null; } },
    write(key, value) { try { localStorage.setItem(DRAFT_PREFIX + key, JSON.stringify(value)); } catch { /* A draft is only a convenience. */ } },
    clear(key) { try { localStorage.removeItem(DRAFT_PREFIX + key); } catch { /* See above. */ } },
};
