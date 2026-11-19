import { api, esc, fmtDate, fmtDateTime, LOCALE, register, setView, skillName, statusBadge, toast, withBusy } from "../core.js";
import { reminderAction, reminderState, reminderTitle, remindersChanged } from "../reminders.js";
import { icon, tile } from "../icons.js";

export const EVENTS = {
    JD_IMPORTED: "Nhập JD", TARGET_CONFIRMED: "Xác nhận mục tiêu", SUBMIT_ASSESSMENT: "Nộp bài đánh giá", SUBMIT_PRACTICE: "Nộp bài luyện tập", GENERATE_ROADMAP: "Lộ trình mới",
    UPDATE_PROGRESS: "Cập nhật tiến độ", CYCLE_SET: "Đặt chu kỳ", CYCLE_POSTPONED: "Hoãn kiểm tra", CYCLE_CANCELLED: "Hủy lịch", REMINDER_SNOOZED: "Nhắc lại sau",
    MINI_TEST_SUBMITTED: "Nộp mini-test", UPDATE_PROFILE: "Cập nhật hồ sơ", TEST_SUBMITTED: "Nộp bài kiểm tra", TEST_STARTED: "Bắt đầu kiểm tra", ADMIN_REVIEW_RESOLVED: "Người duyệt quyết định",
    SKILL_REPORT_CONFIRMED: "Xác nhận tự khai", GRADING_FAILED: "Lỗi chấm bài", JD_DELETED: "Xóa JD",
    LESSON_CHECK_ISSUED: "Mở bài kiểm tra kiến thức", LESSON_CHECK_SUBMITTED: "Nộp bài kiểm tra kiến thức",
    GOAL_CHANGE_STARTED: "Bắt đầu đổi mục tiêu", GOAL_CHANGED: "Đổi mục tiêu",
    PROCESS_STARTED: "Bắt đầu quy trình", PROCESS_COMPLETED: "Hoàn tất quy trình", PROCESS_RESET: "Reset quy trình", EXAM_STARTED: "Bắt đầu bài kiểm tra",
    STUDY_STARTED: "Bắt đầu phiên học", STUDY_ENDED: "Kết thúc phiên học", REVIEW_SCHEDULED: "Lên lịch ôn tập", ROADMAP_REPLANNED: "Cập nhật lộ trình",
    LEVEL_RECONFIRMED: "Xác nhận lại mức", FINAL_STARTED: "Bắt đầu bài đánh giá tổng hợp", FINAL_GRADED: "Kết quả bài đánh giá tổng hợp",
};

/* Nhắc nhở tab (5.29): an inbox of what needs doing, most pressing first, with filters, snooze choices and the
   reminder settings beside it. The server decides every state, order and count; this file only draws them. */
const KIND_FILTERS = [["ALL", "Tất cả"], ["MINI_TEST", "Ôn tập"], ["ACTIVITY_DUE", "Hạn bài học"], ["SCHEDULE", "Lịch học"]];
const KIND_LABELS = { MINI_TEST: "Bài ôn tập đến hạn", ACTIVITY_DUE: "Bài học sắp đến hạn hoặc quá hạn", SCHEDULE: "Lịch học cần xem lại" };
const SNOOZE_CHOICES = [[1, "Ngày mai"], [3, "Sau 3 ngày"], [7, "Sau 1 tuần"]];
let filter = "ALL";
let data = null;

function reminderCard(item) {
    const state = reminderState(item);
    const action = reminderAction(item);
    const id = esc(item.reminder_id);
    const snooze = SNOOZE_CHOICES.map(([days, label]) => `<button type="button" role="menuitem" data-act="snooze" data-id="${id}" data-days="${days}">${label}</button>`).join("");
    const last = item.can_dismiss ? `<button class="btn btn-ghost btn-sm" data-act="dismiss" data-id="${id}">${icon("check")}<span>Đã xem</span></button>` : "";
    return `<li class="rm-card is-${state.tone}">
        <span class="rm-card-icon" aria-hidden="true">${icon(state.icon)}</span>
        <div class="rm-card-main">
            <div class="rm-card-top"><span class="rm-pill is-${state.tone}">${state.label}</span><span class="rm-card-time">${icon("clock")}<span>${fmtDateTime(item.scheduled_at)}</span></span></div>
            <strong class="rm-card-title">${esc(reminderTitle(item))}</strong>
            <p class="rm-card-body">${esc(item.body || "")}</p>
            <div class="rm-card-actions"><a class="btn btn-primary btn-sm" href="${action.href}">${action.label}</a>
                <details class="rm-menu"><summary class="btn btn-secondary btn-sm">${icon("clock")}<span>Nhắc lại sau</span></summary><div class="rm-menu-list" role="menu">${snooze}</div></details>${last}</div>
        </div></li>`;
}

function snoozedRow(item) {
    return `<li class="rm-row"><span class="rm-row-icon" aria-hidden="true">${icon("pause")}</span><div class="rm-text"><strong>${esc(reminderTitle(item))}</strong><span class="sub small">Sẽ nhắc lại vào ${fmtDate(item.snooze_until)}</span></div>
        <button class="btn btn-secondary btn-sm" data-act="resume" data-id="${esc(item.reminder_id)}">Nhắc lại ngay</button></li>`;
}

function dateChip(value) {
    const date = new Date(value);
    return `<span class="rm-date" aria-hidden="true"><b>${String(date.getDate()).padStart(2, "0")}</b><small>${String(date.getMonth() + 1).padStart(2, "0")}/${date.getFullYear()}</small></span>`;
}

function smallEmpty(name, title, text, action = "") {
    return `<div class="rm-empty">${icon(name)}<div><strong>${title}</strong><span class="sub small">${text}</span></div>${action}</div>`;
}

function summaryLine(reminders) {
    if (!reminders.unread_count) return "Bạn không có việc nào cần xử lý lúc này.";
    if (reminders.overdue_count) return `Bạn có ${reminders.unread_count} việc cần xử lý, trong đó ${reminders.overdue_count} việc đã quá hạn.`;
    return `Bạn có ${reminders.unread_count} việc cần xử lý.`;
}

function inbox(reminders) {
    const counts = { ALL: reminders.unread_count, ...reminders.counts };
    const shown = reminders.active.filter(item => filter === "ALL" || item.kind === filter);
    const tabs = KIND_FILTERS.map(([kind, label]) => `<button type="button" class="rm-tab" role="tab" aria-selected="${kind === filter}" data-act="filter" data-kind="${kind}"><span>${label}</span><b>${counts[kind] || 0}</b></button>`).join("");
    const canClear = reminders.active.some(item => item.can_dismiss);
    const clear = canClear ? `<button class="btn btn-ghost btn-sm" data-act="dismiss-all">${icon("check")}<span>Đánh dấu tất cả đã xem</span></button>` : "";
    const empty = reminders.unread_count
        ? smallEmpty("filter", "Không có nhắc nhở loại này", "Chọn nhóm khác để xem các việc còn lại.")
        : smallEmpty("check", "Bạn đã xử lý hết", "Nhắc nhở mới sẽ hiện ở đây khi bài học sắp đến hạn hoặc đến lịch ôn tập.");
    const list = shown.length ? `<ul class="rm-cards">${shown.map(reminderCard).join("")}</ul>` : empty;
    const snoozed = reminders.snoozed.length ? `<div class="rm-sub"><h3 class="h-ic">${icon("pause")}<span>Đang tạm hoãn</span><span class="badge badge-muted">${reminders.snoozed.length}</span></h3><ul class="rm-rows">${reminders.snoozed.map(snoozedRow).join("")}</ul></div>` : "";
    return `<div class="rm-inbox-head"><h2 class="h-ic">${icon("bell")}<span>Việc cần xử lý</span></h2>${clear}</div><div class="rm-tabs" role="tablist" aria-label="Lọc nhắc nhở">${tabs}</div>${list}${snoozed}`;
}

function settingsCard(preferences) {
    const rows = Object.keys(KIND_LABELS).map(kind => {
        const on = Boolean(preferences.enabled_kinds[kind]);
        return `<button type="button" class="rm-switch" role="switch" aria-checked="${on}" data-act="toggle-kind" data-kind="${kind}"><span class="rm-switch-track" aria-hidden="true"></span><span class="rm-switch-label">${KIND_LABELS[kind]}</span></button>`;
    }).join("");
    return `<section class="card rm-side"><h2 class="h-ic">${icon("filter")}<span>Thiết lập nhắc</span></h2><div class="rm-switches">${rows}</div>
        <p class="sub small">Chu kỳ ôn tập mặc định: ${preferences.default_cycle_days} ngày · Múi giờ: ${esc(preferences.timezone)}. Nhắc chỉ hiện trong ứng dụng, không gửi email.</p>
        <a class="btn btn-secondary btn-sm" href="#/profile">Đổi chu kỳ và múi giờ</a></section>`;
}

/* --- Thay đổi mức kỹ năng and Nhật ký hoạt động (5.30). The server works out levels, steps, groups and counts. --- */
const SOURCES = { ASSESSMENT: "Bài đánh giá", MINI_TEST: "Mini-test", FINAL_ASSESSMENT: "Bài đánh giá tổng hợp", HUMAN_REVIEW: "Người duyệt" };
const LOG_GROUPS = [["", "Tất cả", "clock"], ["PROCESS", "Quy trình", "target"], ["ASSESS", "Đánh giá", "quiz"], ["LEARN", "Học tập", "book"], ["REMIND", "Nhắc nhở", "bell"], ["OTHER", "Khác", "info"]];
const LOG_PAGE = 20;
let log = { group: null, items: [], total: 0, allTotal: 0, counts: {}, hasMore: false };

const logPath = offset => `/me/activity-log?limit=${LOG_PAGE}&offset=${offset}${log.group ? `&group=${log.group}` : ""}`;

function levelCells(level, target, max) {
    const cells = Array.from({ length: max }, (_, index) => `<span class="${index < level ? "is-on" : index < (target || 0) ? "is-goal" : ""}"></span>`).join("");
    const classes = target !== null && level >= target ? "rm-level is-met" : "rm-level";
    return `<span class="${classes}" aria-hidden="true">${cells}</span>`;
}

function changeBadge(change) {
    if (change > 0) return `<span class="rm-change is-up">${icon("growth")}<span>Tăng ${change} mức</span></span>`;
    if (change < 0) return `<span class="rm-change is-down">${icon("alert")}<span>Giảm ${-change} mức</span></span>`;
    return `<span class="rm-change">Chưa đổi</span>`;
}

function entryRow(entry) {
    const step = entry.previous_level === null ? `Mức ${entry.level}` : `Mức ${entry.previous_level} → ${entry.level}`;
    const tone = entry.delta > 0 ? "is-up" : entry.delta < 0 ? "is-down" : "";
    const score = entry.score !== null && entry.score !== undefined ? `<span class="sub small">${Math.round(entry.score)}/100</span>` : "";
    return `<li class="rm-entry ${tone}"><span class="rm-entry-dot" aria-hidden="true"></span><span class="rm-entry-date">${fmtDate(entry.created_at)}</span><span class="rm-entry-source">${esc(SOURCES[entry.source_type] || entry.source_type)}</span>${score}<strong class="rm-entry-step">${step}</strong></li>`;
}

function skillRow(skill, max) {
    const goal = skill.target_level === null ? `Mức ${skill.current_level}` : `Mức ${skill.current_level} / mục tiêu ${skill.target_level}`;
    const times = skill.entries.length;
    return `<li class="rm-skill"><details><summary>
            <span class="rm-skill-name">${esc(skill.skill_name)}</span><span class="rm-skill-level">${goal}</span>
            ${levelCells(skill.current_level, skill.target_level, max)}
            <span class="rm-skill-meta">${changeBadge(skill.change)}<span class="sub small">${times} lần ghi nhận · gần nhất ${fmtDate(skill.last_at)}</span></span>
        </summary><ul class="rm-entries">${skill.entries.map(entryRow).join("")}</ul></details></li>`;
}

function skillsSection(skills) {
    const head = `<div class="rm-sec-head"><h2 class="h-ic">${icon("chart")}<span>Thay đổi mức kỹ năng</span></h2><span class="badge badge-muted">${skills.skills.length} kỹ năng</span></div>`;
    if (!skills.skills.length) return `${head}${smallEmpty("chart", "Chưa có bằng chứng", "Mức kỹ năng sẽ hiện ở đây sau bài đánh giá hợp lệ đầu tiên.")}`;
    const facts = [["growth", "Kỹ năng đã tăng mức", skills.raised], ["check", "Đạt mục tiêu JD", `${skills.met}/${skills.with_target}`], ["file", "Lần ghi nhận", skills.total_entries]];
    return `${head}<p class="sub small">Mức chỉ đổi khi có bài đánh giá, mini-test hoặc bài tổng hợp hợp lệ. Bấm vào một kỹ năng để xem từng lần ghi nhận.</p>
        <div class="rm-facts">${facts.map(([name, label, value]) => `<span class="rm-fact">${icon(name)}<b>${value}</b><span>${label}</span></span>`).join("")}</div>
        <ul class="rm-skills">${skills.skills.map(skill => skillRow(skill, skills.max_level)).join("")}</ul>
        <p class="rm-legend"><span class="rm-level"><span class="is-on"></span></span><span>Mức đã đạt</span><span class="rm-level"><span class="is-goal"></span></span><span>Còn thiếu so với mục tiêu</span></p>`;
}

function logRows() {
    const icons = Object.fromEntries(LOG_GROUPS.map(([group, , name]) => [group, name]));
    let day = "";
    let html = "";
    for (const item of log.items) {
        const date = fmtDate(item.time);
        if (date !== day) { html += `${day ? "</ul>" : ""}<h3 class="rm-day">${date}</h3><ul class="rm-timeline">`; day = date; }
        const time = new Date(item.time).toLocaleTimeString(LOCALE(), { hour: "2-digit", minute: "2-digit" });
        html += `<li class="rm-event is-${item.group.toLowerCase()}"><span class="rm-event-icon" aria-hidden="true">${icon(icons[item.group] || "info")}</span><div class="rm-event-text"><strong>${esc(EVENTS[item.event] || item.event)}</strong><span class="sub small">${esc(item.detail || "")}</span></div><span class="rm-event-time">${time}</span></li>`;
    }
    return day ? `${html}</ul>` : "";
}

function logSection() {
    const head = `<div class="rm-sec-head"><h2 class="h-ic">${icon("clock")}<span>Nhật ký hoạt động</span></h2><span class="badge badge-muted">${log.allTotal} hoạt động</span></div>`;
    if (!log.allTotal) return `${head}${smallEmpty("clock", "Chưa có hoạt động", "Mỗi việc bạn làm trong hệ thống sẽ được ghi lại tại đây.")}`;
    const tabs = LOG_GROUPS.filter(([group]) => !group || log.counts[group]).map(([group, label]) => {
        const selected = (log.group || "") === group;
        return `<button type="button" class="rm-tab" role="tab" aria-selected="${selected}" data-act="log-group" data-group="${group}"><span>${label}</span><b>${group ? log.counts[group] : log.allTotal}</b></button>`;
    }).join("");
    const more = log.hasMore ? `<button class="btn btn-secondary btn-sm" data-act="log-more">Xem thêm</button>` : "";
    return `${head}<div class="rm-tabs" role="tablist" aria-label="Lọc nhật ký">${tabs}</div>${logRows()}
        <div class="rm-log-foot"><span class="sub small">Đang hiện ${log.items.length}/${log.total} hoạt động</span>${more}</div>`;
}

function drawLog() {
    const box = document.getElementById("rm-log");
    if (box) box.innerHTML = logSection();
}

/* The log and the skill levels stay folded away until asked for; the choice is kept while the app is open. */
const shown = { log: false, skills: false };

function moreButton(name, iconName, title, count) {
    return `<button type="button" class="rm-more-btn" data-act="show-record" data-record="${name}" aria-expanded="${shown[name]}" aria-controls="rm-${name}">
        <span class="rm-more-icon" aria-hidden="true">${icon(iconName)}</span><span class="rm-more-text"><strong>${title}</strong><span class="sub small">${count}</span></span>
        <span class="rm-more-state">${shown[name] ? "Ẩn" : "Xem"}</span></button>`;
}

function showRecords() {
    for (const name of Object.keys(shown)) {
        document.getElementById(`rm-${name}`).hidden = !shown[name];
        const button = document.querySelector(`.rm-more-btn[data-record="${name}"]`);
        button.setAttribute("aria-expanded", String(shown[name]));
        button.querySelector(".rm-more-state").textContent = shown[name] ? "Ẩn" : "Xem";
    }
    const box = document.getElementById("rm-records");
    box.hidden = !shown.log && !shown.skills;
    box.classList.toggle("is-single", shown.log !== shown.skills);
}

function drawInbox() {
    const box = document.getElementById("rm-inbox");
    if (box) box.innerHTML = inbox(data.reminders);
}

async function reload(message, tone) {
    if (message) toast(message, tone);
    remindersChanged();
    await renderProgress();
}

export async function renderProgress() {
    const [reminders, micro, skills, firstPage] = await Promise.all([api("/me/reminders"), api("/micro-tests"), api("/me/skill-progress"), api(logPath(0))]);
    data = { reminders };
    log = { ...log, items: firstPage.items, total: firstPage.total, allTotal: firstPage.all_total, counts: firstPage.counts, hasMore: firstPage.has_more };
    const waiting = micro.filter(item => item.status === "PENDING").length;
    const stats = [["bell", "Cần xử lý", reminders.unread_count, reminders.overdue_count ? "bad" : "brand"], ["pause", "Tạm hoãn", reminders.snoozed.length, "muted"], ["calendar", "Lịch ôn sắp tới", reminders.upcoming.length, "brand"], ["quiz", "Mini-test chờ làm", waiting, "warn"]];
    const upcoming = reminders.upcoming.length
        ? `<ul class="rm-rows">${reminders.upcoming.map(item => `<li class="rm-row">${dateChip(item.due_at)}<div class="rm-text"><strong>${esc(item.activity_title)}</strong><span class="sub small">Chu kỳ ${item.cycle_days} ngày</span></div></li>`).join("")}</ul>`
        : smallEmpty("calendar", "Chưa có lịch ôn", "Lịch ôn được đặt khi bạn hoàn thành một bài học.", `<a class="btn btn-secondary btn-sm" href="#/plan/da/roadmap">Mở lộ trình</a>`);
    const tests = micro.length
        ? `<ul class="rm-rows">${micro.slice(0, 8).map(item => `<li class="rm-row"><div class="rm-text"><a href="#/mini/${esc(item.micro_id)}"><strong>${esc(item.activity_title || skillName(item.skill_code))}</strong></a><span class="sub small">${fmtDate(item.submitted_at || item.created_at)}${item.result?.score !== null && item.result?.score !== undefined ? ` · ${item.result.score}/100` : ""}</span></div>${statusBadge(item.status)}</li>`).join("")}</ul>`
        : smallEmpty("quiz", "Chưa có mini-test", "Mini-test được tạo khi đến hạn ôn tập.");
    setView(`<div class="stack rm-page">
        <section class="rm-hero page-hero is-rose"><div class="rm-hero-text"><span class="rm-hero-kicker">${icon("bell")}<span>Nhắc nhở</span></span><h2>${summaryLine(reminders)}</h2><p>Việc đến hạn, lịch ôn tập và mini-test của bạn. Việc gấp nhất nằm trên cùng.</p></div>
            <div class="rm-hero-stats">${stats.map(([name, label, value, tone]) => `<div class="rm-kpi is-${value ? tone : "muted"}"><span class="rm-kpi-icon">${icon(name)}</span><b>${value}</b><span>${label}</span></div>`).join("")}</div></section>
        <div class="rm-layout">
            <section class="card rm-inbox" id="rm-inbox">${inbox(reminders)}</section>
            <div class="rm-aside">
                <section class="card rm-side"><h2 class="h-ic">${icon("calendar")}<span>Lịch ôn tập sắp tới</span></h2>${upcoming}</section>
                <section class="card rm-side"><h2 class="h-ic">${icon("quiz")}<span>Mini-test</span></h2>${tests}</section>
                ${settingsCard(reminders.preferences)}
            </div>
        </div>
        <div class="rm-more" role="group" aria-label="Xem thêm">
            ${moreButton("log", "clock", "Nhật ký hoạt động", `${log.allTotal} hoạt động`)}
            ${moreButton("skills", "chart", "Thay đổi mức kỹ năng", `${skills.skills.length} kỹ năng`)}
        </div>
        <div class="rm-records" id="rm-records">
            <section class="card" id="rm-log" ${shown.log ? "" : "hidden"}>${logSection()}</section>
            <section class="card" id="rm-skills" ${shown.skills ? "" : "hidden"}>${skillsSection(skills)}</section>
        </div></div>`);
    showRecords();
    register({
        actions: {
            filter: element => { filter = element.dataset.kind; drawInbox(); },
            "show-record": element => {
                const name = element.dataset.record;
                shown[name] = !shown[name];
                showRecords();
                if (shown[name]) document.getElementById(`rm-${name}`).scrollIntoView({ block: "nearest", behavior: "smooth" });
            },
            "log-group": element => withBusy(element, async () => {
                log.group = element.dataset.group || null;
                const page = await api(logPath(0));
                log = { ...log, items: page.items, total: page.total, allTotal: page.all_total, counts: page.counts, hasMore: page.has_more };
                drawLog();
            }),
            "log-more": element => withBusy(element, async () => {
                const page = await api(logPath(log.items.length));
                log = { ...log, items: [...log.items, ...page.items], total: page.total, hasMore: page.has_more };
                drawLog();
            }),
            snooze: element => withBusy(element, async () => {
                const days = Number(element.dataset.days) || 1;
                await api(`/me/reminders/${element.dataset.id}/snooze`, { method: "POST", body: { days } });
                await reload(days === 1 ? "Sẽ nhắc lại vào ngày mai." : `Sẽ nhắc lại sau ${days} ngày.`);
            }),
            resume: element => withBusy(element, async () => {
                await api(`/me/reminders/${element.dataset.id}/resume`, { method: "POST" });
                await reload("Đã đưa nhắc nhở trở lại danh sách.");
            }),
            dismiss: element => withBusy(element, async () => {
                await api(`/me/reminders/${element.dataset.id}/dismiss`, { method: "POST" });
                await reload();
            }),
            "dismiss-all": element => withBusy(element, async () => {
                const result = await api("/me/reminders/dismiss-all", { method: "POST" });
                await reload(`Đã đánh dấu ${result.dismissed} nhắc nhở là đã xem.`, "good");
            }),
            "toggle-kind": element => withBusy(element, async () => {
                const turnOn = element.getAttribute("aria-checked") !== "true";
                await api("/me/reminder-preferences", { method: "PUT", body: { enabled_kinds: { [element.dataset.kind]: turnOn } } });
                await reload(turnOn ? "Đã bật loại nhắc này." : "Đã tắt loại nhắc này.", "good");
            }),
        },
    });
}
