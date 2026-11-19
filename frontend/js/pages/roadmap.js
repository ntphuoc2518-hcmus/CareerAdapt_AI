/** Learning Roadmap 2.0: overview, week, lesson (study timer, content, practice, checks) and the final assessment.
 * Every state shown here comes from the server: study time, the lesson's two states, scores and the verdict.
 * The browser only keeps a running clock between server replies and reports a heartbeat. */
import { alertBox, api, closeModal, confirmDialog, emptyView, esc, fmtDate, fmtDateTime, fmtHours, formData, openModal, register, safeUrl, setBar, setView, skillName, statusBadge, toast, withBusy } from "../core.js";
import { icon, skillIcon, tile } from "../icons.js";
import { mountWorkspace } from "../workspaces.js";
import { pageHero } from "../hero.js";
import { renderExamRoom, renderGradingWait, renderReview } from "./exam.js";

const BASE = "#/plan/da/roadmap";
const REASONS = {
    NO_APPROVED_RESOURCE: "Thiếu học liệu", MISSING_PREREQUISITE: "Thiếu tiên quyết", INSUFFICIENT_HOURS: "Không đủ giờ", EXCEEDS_WEEKLY_BUDGET: "Vượt giờ mỗi tuần",
    MISSING_EVIDENCE: "Thiếu bằng chứng", OUTSIDE_CATALOG: "Ngoài danh mục", NO_ACTIVITY: "Chưa có học phần", INCOMPLETE_ACTIVITY: "Thiếu thông tin", ZERO_WEEKLY_HOURS: "Không có giờ học",
};
// [label, tone, icon] for the learning state; the review state is shown beside it, never merged into it.
const LEARNING = {
    NOT_STARTED: ["Chưa bắt đầu", "muted", "clock"], STUDYING: ["Đang học", "", "route"], PAUSED: ["Đã tạm dừng", "muted", "pause"],
    PENDING_CHECK: ["Chờ kiểm tra hoàn thành", "warn", "quiz"], NEEDS_REVIEW: ["Chưa đạt, cần học lại", "bad", "refresh"], COMPLETED: ["Đã hoàn thành", "good", "check"],
};
const REVIEW = { SCHEDULED: ["Đã lên lịch ôn tập", ""], DUE: ["Đến hạn ôn tập", "warn"], PASSED: ["Ôn tập đạt", "good"], RELEARN: ["Cần ôn tập lại", "bad"] };
const WEEK = { DONE: ["Hoàn thành", "good"], NEEDS_REVIEW: ["Cần học lại", "bad"], PENDING_CHECK: ["Chờ kiểm tra", "warn"], IN_PROGRESS: ["Đang học", ""], NOT_STARTED: ["Chưa bắt đầu", "muted"], ASSESSMENT: ["Đánh giá", ""] };
const RESOURCE_TYPES = { COURSE: "Khóa học", LECTURE: "Bài giảng", EXERCISE: "Bài tập", OFFICIAL_DOC: "Tài liệu chính thức", ARTICLE: "Bài viết", INTERNAL_GUIDE: "Hướng dẫn nội bộ", VIDEO: "Video" };
const LEVEL_NAMES = { 1: "Nền tảng", 2: "Sẵn sàng thực tập", 3: "Sẵn sàng đầu nghề" };
const PAUSE_REASONS = { INTERRUPTED: "Phiên tự tạm dừng vì trang bị đóng hoặc mất kết nối. Thời gian sau lần ghi nhận cuối không được tính.", LIMIT: "Phiên tự tạm dừng sau 4 giờ liên tục." };
const RULES = { SCORE: "Điểm tổng", CORE: "Kỹ năng cốt lõi", COVERAGE: "Mức đáp ứng JD", COMPLETE: "Làm đủ bài", CRITICAL: "Không lỗi trọng yếu" };

const badge = ([label, tone]) => `<span class="badge ${tone ? `badge-${tone}` : ""}">${esc(label)}</span>`;
// A check passed under the old one-step rule is not a failure: the level only needs confirming.
const learningBadge = (state, levelShort = false) => badge(levelShort ? ["Cần xác nhận mức", "warn"] : LEARNING[state] || LEARNING.NOT_STARTED);
const reviewBadge = (state, due) => (REVIEW[state] ? badge(state === "SCHEDULED" && due ? [`Ôn tập ${fmtDate(due)}`, ""] : REVIEW[state]) : "");
const pad = value => String(value).padStart(2, "0");
const clockText = seconds => `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor((seconds % 3600) / 60))}:${pad(Math.floor(seconds % 60))}`;
const duration = seconds => {
    const minutes = Math.round((seconds || 0) / 60);
    if (minutes < 60) return `${minutes} phút`;
    return `${Math.floor(minutes / 60)} giờ ${pad(minutes % 60)} phút`;
};
const weekTitle = week => week.topics.map(topic => skillName(topic.skill_code)).join(" · ") || "Bài đánh giá";
const sectionHead = (name, title, note, extra = "") => `<div class="rd-head">${tile(name, "brand", "tile-sm")}<div><h2>${title}</h2>${note ? `<p class="sub small">${note}</p>` : ""}</div>${extra}</div>`;
const crumbs = items => `<nav class="jr-crumbs" aria-label="Vị trí">${items.map(([label, href]) => (href ? `<a href="${href}">${esc(label)}</a>` : `<span aria-current="page">${esc(label)}</span>`)).join(`<span aria-hidden="true">/</span>`)}</nav>`;

/* ------------------------------------------------------------------ overview */

function metric(name, label, value, note) {
    return `<div class="jr-metric"><span class="jr-metric-label">${icon(name)}<span>${esc(label)}</span></span><strong>${value}</strong>${note ? `<span class="sub small">${note}</span>` : ""}</div>`;
}

function sessionBanner(session) {
    if (!session) return "";
    const running = session.status === "RUNNING";
    return `<a class="jr-session ${running ? "is-running" : ""}" href="${BASE}/lesson/${esc(session.activity_id)}">${icon(running ? "clock" : "pause")}
        <span><strong>${running ? "Đang bấm giờ" : "Phiên học đang tạm dừng"}:</strong> ${esc(session.activity_title)}</span><span class="jr-session-time" data-session-clock data-elapsed="${session.elapsed_seconds}" data-running="${running ? 1 : 0}">${clockText(session.elapsed_seconds)}</span>${icon("arrow")}</a>`;
}

function weekTile(week) {
    const [label, tone] = week.overdue_days ? [`Trễ ${week.overdue_days} ngày`, "bad"] : WEEK[week.state] || WEEK.NOT_STARTED;
    return `<a class="card jr-week ${week.state === "DONE" ? "is-done" : ""} ${week.overdue_days ? "is-late" : ""}" href="${BASE}/week/${week.week_number}">
        <div class="row-between"><span class="eyebrow-label">Tuần ${week.week_number}</span>${badge([label, tone])}</div>
        <h3>${esc(weekTitle(week))}</h3><span class="sub small">${fmtDate(week.start_date)} – ${fmtDate(week.end_date)}</span>
        <div class="jr-week-progress"><span class="meter"><span style="width:${week.percent}%"></span></span><span class="small"><strong>${week.lessons_done}/${week.lessons_total}</strong> bài · ${week.percent}%</span></div>
        <span class="jr-week-next">${week.next_lesson ? `${icon("route")}<span>Tiếp theo: ${esc(week.next_lesson.title)}</span>` : `${icon("check")}<span>Đã hoàn thành mọi bài của tuần</span>`}</span></a>`;
}

function finalCard(final) {
    if (!final) return "";
    let body;
    if (final.passed_attempt_id) {
        body = `<p>Bạn đã đạt bài đánh giá tổng hợp theo JD đã chọn.</p><a class="btn btn-primary btn-sm" href="${BASE}/final/result/${esc(final.passed_attempt_id)}">${icon("trophy")}<span>Xem kết quả hoàn thành</span></a>`;
    } else if (final.current && final.current.status !== "IN_PROGRESS") {
        body = `<p>Bài đánh giá tổng hợp đã nộp và đang được chấm.</p><a class="btn btn-secondary btn-sm" href="${BASE}/final/result/${esc(final.current.attempt_id)}">${icon("clock")}<span>Xem tiến trình chấm</span></a>`;
    } else if (final.current) {
        body = `<p>Bạn đang làm bài đánh giá tổng hợp.</p><a class="btn btn-primary btn-sm" href="#/final-exam">${icon("quiz")}<span>Tiếp tục làm bài</span></a>`;
    } else if (final.eligible) {
        body = `<p>${final.can_start ? "Bạn đã hoàn thành mọi bài học bắt buộc. Bài đánh giá tổng hợp đã mở." : esc(final.reason || "")}</p><a class="btn btn-primary btn-sm" href="${BASE}/final">${icon("trophy")}<span>${final.can_start ? "Làm bài đánh giá tổng hợp" : "Xem bài đánh giá"}</span></a>`;
    } else {
        body = `<p class="sub">${icon("lock")} ${esc(final.reason || "")} Bài đánh giá tổng hợp mở khi mọi bài học đạt bài kiểm tra hoàn thành.</p>`;
    }
    return `<section class="card jr-final ${final.eligible ? "is-open" : ""}">${sectionHead("trophy", "Bài đánh giá tổng hợp cuối lộ trình", "Bài thực hành mô phỏng công việc theo JD đã chọn.")}${body}</section>`;
}

/** What the last re-plan changed, and the lessons it kept or no longer needs. Their history stays. */
function replanBlock(data) {
    const carried = data.carried_lessons || [];
    const retired = data.retired_lessons || [];
    const note = data.replanned_at ? alertBox("info", `<strong>Lộ trình đã được cập nhật ngày ${fmtDate(data.replanned_at)}.</strong> ${esc(data.change_reason || "")}`) : "";
    const carriedList = carried.length ? `<details class="card jr-unscheduled"><summary>${icon("check")}<span><strong>Đã hoàn thành ở phiên bản trước (${carried.length})</strong><span class="sub small">Các bài này vẫn tính vào tiến độ, lịch ôn tập và lịch sử được giữ nguyên.</span></span>${icon("arrow")}</summary>
        <ul class="task-list">${carried.map(item => `<li class="jr-lesson is-completed"><span class="lesson-dot" aria-hidden="true">${icon("check")}</span><div class="lesson-body"><a class="lesson-title" href="${BASE}/lesson/${esc(item.activity_id)}">${esc(item.title)}</a><span class="lesson-meta"><span>${esc(skillName(item.target_skill))}</span>${item.review_due_at ? `<span>Kiểm tra lại ${fmtDate(item.review_due_at)}</span>` : ""}</span></div><div class="jr-lesson-badges">${learningBadge(item.learning_state)}${reviewBadge(item.review_state, item.review_due_at)}</div></li>`).join("")}</ul></details>` : "";
    const retiredList = retired.length ? `<details class="card jr-unscheduled"><summary>${icon("info")}<span><strong>Không còn trong lộ trình (${retired.length})</strong><span class="sub small">Bài được bỏ khi cập nhật lộ trình. Thời gian đã học và kết quả cũ vẫn được lưu.</span></span>${icon("arrow")}</summary>
        <ul class="rules">${retired.map(item => `<li><strong>${esc(item.title)}</strong>: ${esc(item.reason)}</li>`).join("")}</ul></details>` : "";
    return note + carriedList + retiredList;
}

function unscheduledBlock(items) {
    if (!items?.length) return "";
    return `<details class="card jr-unscheduled"><summary>${icon("alert")}<span><strong>Chưa xếp được (${items.length})</strong><span class="sub small">Không có hoạt động nào bị bỏ âm thầm; lý do được ghi cho từng hoạt động.</span></span>${icon("arrow")}</summary>
        <div class="table-wrap plan-table"><table><thead><tr><th>Hoạt động</th><th>Lý do</th><th>Chi tiết</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.title)}</td><td class="nowrap"><span class="badge badge-warn">${esc(REASONS[item.reason_code] || item.reason_code)}</span></td><td class="small">${esc(item.reason)}${item.self_study?.length ? `<span class="self-study"><strong>Học liệu tự học gợi ý</strong>${item.self_study.map(link => `<a href="${esc(safeUrl(link.url))}" target="_blank" rel="noopener noreferrer"><span data-no-i18n>${esc(link.title)}</span> · ${esc(link.provider)}</a>`).join("")}<span class="sub">Tự học, không xếp lịch và không tính là bằng chứng năng lực.</span></span>` : ""}</td></tr>`).join("")}</tbody></table></div></details>`;
}

async function overviewPage() {
    const data = await api("/me/journey");
    if (!data) {
        setView(`<div class="card">${emptyView("Chưa có lộ trình", "Lộ trình được tạo ở bước cuối của Quy trình Career Adapt.")}</div>`);
        return;
    }
    const next = data.next_lesson;
    const waitingNote = [data.due_reviews ? `${data.due_reviews} bài đến hạn ôn tập` : "", data.pending_completion_checks ? `${data.pending_completion_checks} bài chờ kiểm tra hoàn thành` : ""].filter(Boolean).join(" · ") || "Không có bài nào đang chờ";
    const finished = data.lessons_total && data.lessons_done === data.lessons_total;
    const heroTitle = finished ? "Bạn đã hoàn thành mọi bài học trong lộ trình." : `Bạn đã hoàn thành ${data.lessons_done}/${data.lessons_total} bài học.`;
    const hero = pageHero({
        tone: "green", icon: "route", kicker: "Lộ trình học tập", title: heroTitle,
        text: `${data.total_weeks} tuần · ${data.weekly_hours_budget} giờ/tuần · đã học ${duration(data.study_seconds)}. ${esc(waitingNote)}.`,
        stats: [["route", "Tiến độ học tập", `${data.percent}%`, "good"], ["calendar", "Dự kiến hoàn thành", data.expected_end_date ? fmtDate(data.expected_end_date) : "—", "muted"],
            ["quiz", "Chờ kiểm tra lại", data.waiting_checks, data.waiting_checks ? "warn" : "muted"], ["alert", "Ngày chậm lịch", data.behind ? data.behind.days : 0, data.behind ? "bad" : "muted"]],
    });
    setView(`<div class="stack">${sessionBanner(data.current_session)}${hero}
        <section class="card jr-overview is-solo"><div class="jr-metrics">
            <div class="jr-metric jr-next"><span class="jr-metric-label">${icon("target")}<span>Bài học tiếp theo</span></span>${next ? `<strong class="jr-next-title">${esc(next.title)}</strong><span class="sub small">Tuần ${next.week_number} · ${esc(skillName(next.target_skill))}</span><a class="btn btn-primary btn-sm" href="${BASE}/lesson/${esc(next.activity_id)}">${icon("arrow")}<span>Học tiếp</span></a>` : `<strong>Đã xong mọi bài</strong><span class="sub small">Hãy làm bài đánh giá tổng hợp.</span>`}</div>
        </div>
        ${data.meets_deadline === false ? `<p class="meta">${icon("alert")}<span>Một số hoạt động chưa xếp kịp thời hạn; xem mục Chưa xếp được bên dưới.</span></p>` : ""}</section>
        ${data.behind ? `<div class="jr-behind">${alertBox("warn", `<strong>Bạn đang chậm so với lịch:</strong> ${data.behind.weeks} tuần đã qua ngày kết thúc mà còn ${data.behind.lessons} bài chưa đạt (trễ nhất ${data.behind.days} ngày). Ngày dự kiến hoàn thành phía trên không còn đúng nếu giữ lịch cũ.`)}<button class="btn btn-primary btn-sm" type="button" data-act="replan">${icon("calendar")}<span>Dời lịch từ hôm nay</span></button></div>` : ""}
        ${replanBlock(data)}
        ${sectionHead("calendar", "Các tuần học", "Bấm vào một tuần để xem chủ đề và bài học.", `<span class="badge badge-muted">${data.total_weeks} tuần · ${data.lessons_total} bài</span><button class="btn btn-secondary btn-sm" type="button" data-act="replan">${icon("refresh")}<span>Cập nhật lộ trình</span></button>`)}
        ${data.weeks.length ? `<div class="jr-weeks">${data.weeks.map(weekTile).join("")}</div>` : `<div class="card">${emptyView("Không có bài học cần xếp", "Bạn đã đạt mục tiêu trên các kỹ năng đã đo, hoặc xem phần chưa xếp bên dưới.")}</div>`}
        ${finalCard(data.final)}
        ${unscheduledBlock(data.unscheduled)}
        <p class="sub small">Mục tiêu: ${esc(data.target?.name || "")}. Thời gian học chỉ là tiến độ; mức năng lực chỉ thay đổi khi bạn đạt bài kiểm tra.</p></div>`);
    startSessionClocks();
    register({
        actions: {
            replan: async element => {
                if (!(await confirmDialog("Cập nhật lộ trình?", "Các bài còn lại được xếp lại từ hôm nay theo mức đã xác thực hiện tại. Bài đã hoàn thành, thời gian học, lịch ôn tập và lịch sử được giữ nguyên; phiên bản cũ vẫn lưu trong lịch sử lộ trình.", { confirmLabel: "Cập nhật" }))) return;
                await withBusy(element, async () => {
                    const result = await api("/me/journey/replan", { method: "POST" });
                    toast(result.message, "good");
                    overviewPage();
                });
            },
        },
    });
}

/* ------------------------------------------------------------------ week */

function lessonRow(lesson) {
    const [, , name] = LEARNING[lesson.learning_state] || LEARNING.NOT_STARTED;
    const split = lesson.total_segments > 1 ? `<span>Phần ${lesson.segment}/${lesson.total_segments}</span>` : "";
    return `<li class="jr-lesson is-${(lesson.learning_state || "").toLowerCase().replace("_", "-")}"><span class="lesson-dot" aria-hidden="true">${icon(name)}</span>
        <div class="lesson-body"><a class="lesson-title" href="${BASE}/lesson/${esc(lesson.activity_id)}">${esc(lesson.title)}</a>
            <span class="lesson-meta"><span>Mức ${lesson.target_level}</span><span>Dự kiến ${fmtHours(lesson.estimated_hours)}</span>${split}<span>Đã học ${duration(lesson.study_seconds)}</span>${lesson.review_due_at ? `<span>Kiểm tra lại ${fmtDate(lesson.review_due_at)}</span>` : ""}</span>
            <span class="lesson-bar" title="Thời gian đã học so với dự kiến"><span class="meter"><span style="width:${lesson.time_percent || 0}%"></span></span><span class="small">${lesson.time_percent || 0}%</span></span></div>
        <div class="jr-lesson-badges">${learningBadge(lesson.learning_state, lesson.level_short)}${reviewBadge(lesson.review_state, lesson.review_due_at)}</div>
        <a class="btn btn-secondary btn-sm" href="${BASE}/lesson/${esc(lesson.activity_id)}">Mở bài</a></li>`;
}

async function weekPage(number) {
    const week = await api(`/me/journey/weeks/${number}`);
    const firstOpen = week.topics.findIndex(topic => topic.lessons.some(lesson => lesson.learning_state !== "COMPLETED"));
    setView(`<div class="stack">${crumbs([["Lộ trình học tập", BASE], [`Tuần ${week.week_number}`]])}
        <section class="card jr-week-head"><div class="row-between"><div><span class="eyebrow-label">Tuần ${week.week_number}/${week.weeks_total} · ${fmtDate(week.start_date)} – ${fmtDate(week.end_date)}</span><h2>${esc(weekTitle(week))}</h2></div>${badge(WEEK[week.state] || WEEK.NOT_STARTED)}</div>
            <div class="jr-week-stats"><span><strong>${week.topics.length}</strong> chủ đề</span><span><strong>${week.lessons_total}</strong> bài học</span><span><strong>${fmtHours(week.allocated_hours)}</strong> theo kế hoạch</span>
                <span class="jr-week-meter"><span class="meter"><span style="width:${week.percent}%"></span></span><span class="small">${week.lessons_done}/${week.lessons_total} bài · ${week.percent}%</span></span></div>
            ${week.objectives.length ? `<div><h3 class="h-ic">${icon("target")}<span>Mục tiêu tuần</span></h3><ul class="rules">${week.objectives.map(text => `<li>${esc(text)}</li>`).join("")}</ul></div>` : ""}</section>
        ${week.topics.map((topic, index) => {
            const done = topic.lessons.filter(lesson => lesson.learning_state === "COMPLETED").length;
            return `<details class="card jr-topic" ${index === Math.max(firstOpen, 0) ? "open" : ""}><summary>${skillIcon(topic.skill_code)}<span><strong>Chủ đề ${index + 1}: ${esc(skillName(topic.skill_code))}</strong><span class="sub small">${done}/${topic.lessons.length} bài đã hoàn thành</span></span>${icon("arrow")}</summary>
                <ul class="task-list">${topic.lessons.map(lessonRow).join("")}</ul></details>`;
        }).join("")}
        ${week.assessments.length ? alertBox("info", `Tuần này có bài đánh giá để tạo bằng chứng cho: ${esc(week.assessments.flatMap(item => item.skills || []).map(skillName).join(", "))}.`) : ""}
        <div class="row-between jr-pager">${week.previous_week ? `<a class="btn btn-secondary btn-sm" href="${BASE}/week/${week.previous_week}">← Tuần ${week.previous_week}</a>` : "<span></span>"}${week.next_week ? `<a class="btn btn-secondary btn-sm" href="${BASE}/week/${week.next_week}">Tuần ${week.next_week} →</a>` : ""}</div></div>`);
}

/* ------------------------------------------------------------------ lesson */

let clockTimer = null;

/** Every element marked as a session clock counts on from the server's last value. */
function startSessionClocks() {
    clearInterval(clockTimer);
    const started = Date.now();
    const draw = () => document.querySelectorAll("[data-session-clock]").forEach(element => {
        const base = Number(element.dataset.elapsed || 0);
        element.textContent = clockText(element.dataset.running === "1" ? base + Math.floor((Date.now() - started) / 1000) : base);
    });
    draw();
    clockTimer = setInterval(draw, 1000);
    register({ cleanup: () => clearInterval(clockTimer) });
}

function resourceItem(resource) {
    return `<li class="jr-resource ${resource.available ? "" : "is-off"}"><div><a href="${safeUrl(resource.url)}" target="_blank" rel="noopener noreferrer" data-no-i18n>${esc(resource.title)}</a>
        <span class="sub small">${esc(resource.provider)} · ${esc(RESOURCE_TYPES[resource.resource_type] || resource.resource_type)} · Mức ${resource.level} · ≈ ${duration((resource.estimated_minutes || 0) * 60)} · ${resource.language === "vi" ? "Tiếng Việt" : "Tiếng Anh"}</span>
        <span class="small">${esc(resource.learning_outcome || "")}</span></div>${resource.available ? "" : '<span class="badge badge-bad">Tạm ẩn</span>'}</li>`;
}

function historyList(items, empty, row) {
    return items.length ? `<ul class="feed">${items.map(row).join("")}</ul>` : `<p class="sub small">${esc(empty)}</p>`;
}

function timerCard(detail) {
    const { state } = detail;
    const own = state.session;
    const other = detail.current_session && detail.current_session.activity_id !== detail.activity.activity_id && detail.current_session.status === "RUNNING" ? detail.current_session : null;
    const running = own?.status === "RUNNING";
    const total = state.study_seconds;
    let actions;
    if (running) actions = `<button class="btn btn-secondary" data-act="study" data-action="pause">${icon("pause")}<span>Tạm dừng</span></button><button class="btn btn-ghost" data-act="study-end">${icon("stop")}<span>Kết thúc phiên</span></button>`;
    else if (own) actions = `<button class="btn btn-primary" data-act="study" data-action="resume">${icon("play")}<span>Tiếp tục học</span></button><button class="btn btn-ghost" data-act="study-end">${icon("stop")}<span>Kết thúc phiên</span></button>`;
    else actions = `<button class="btn btn-primary" data-act="study-start">${icon("play")}<span>${total ? "Bắt đầu phiên mới" : "Bắt đầu học"}</span></button>`;
    return `<section class="card jr-timer ${running ? "is-running" : ""}" id="jr-timer"><div class="row-between"><span class="eyebrow-label">Đồng hồ học</span>${own ? statusBadge(own.status) : badge(["Chưa chạy", "muted"])}</div>
        <div class="jr-clock" data-session-clock data-elapsed="${own ? own.elapsed_seconds : 0}" data-running="${running ? 1 : 0}" role="timer" aria-live="off">${clockText(own ? own.elapsed_seconds : 0)}</div>
        <span class="sub small">Phiên hiện tại</span>
        ${own?.pause_reason && PAUSE_REASONS[own.pause_reason] ? alertBox("warn", esc(PAUSE_REASONS[own.pause_reason])) : ""}
        ${other ? alertBox("info", `Bạn đang bấm giờ cho bài <a href="${BASE}/lesson/${esc(other.activity_id)}">${esc(other.activity_title)}</a>. Bắt đầu bài này sẽ tạm dừng bài kia.`) : ""}
        <div class="jr-timer-actions">${actions}</div>
        <div class="jr-timer-total"><span>Tổng đã học <strong>${duration(total)}</strong> / dự kiến ${fmtHours(state.estimated_hours)}</span><span class="meter"><span style="width:${state.time_percent}%"></span></span></div>
        <p class="meta">${icon("calendar")}<span>${state.cycle_locked ? `Kiểm tra lại sau <strong>${state.review_cycle_days} ngày</strong> kể từ khi đạt bài kiểm tra hoàn thành (đã chốt).` : "Lần đầu bắt đầu học, bạn chọn thời gian kiểm tra lại cho bài này."}</span></p></section>`;
}

function completionCard(detail) {
    const { state } = detail;
    const latest = state.latest_check;
    let body;
    const practicalNote = state.target_level > (state.confirm_level ?? state.target_level)
        ? `<p class="meta">${icon("info")}<span>Bài trắc nghiệm xác nhận tối đa mức ${state.confirm_level}. Mức ${state.target_level} được xác nhận bằng bài làm thực hành ở Bài đánh giá tổng hợp cuối lộ trình.</span></p>` : "";
    if (state.learning_state === "COMPLETED") {
        body = `${alertBox("good", `<strong>Đã đạt bài kiểm tra hoàn thành</strong> với ${latest?.score ?? "—"}/100.`)}<a class="btn btn-secondary btn-sm" href="#/mini/${esc(latest.micro_id)}">Xem kết quả</a>${practicalNote}`;
    } else if (state.open_check_id && state.learning_state === "PENDING_CHECK") {
        body = `<p>Bài kiểm tra hoàn thành đang mở.</p><a class="btn btn-primary btn-sm" href="#/mini/${esc(state.open_check_id)}">${icon("quiz")}<span>Tiếp tục bài kiểm tra</span></a>`;
    } else if (state.learning_state === "NEEDS_REVIEW" && state.level_short && !state.open_check_id) {
        body = `${alertBox("warn", `<strong>Cần xác nhận mức ${state.confirm_level ?? state.target_level}.</strong> Bài kiểm tra trước đạt ${latest?.score ?? "—"}/100 nhưng mức ${esc(skillName(detail.activity.target_skill))} đã xác thực mới là ${state.skill_level ?? 0}, chưa tới mức ${state.confirm_level ?? state.target_level} của bài này. Hãy làm bài kiểm tra xác nhận; thời gian học và lịch sử vẫn được giữ.`)}
            <button class="btn btn-primary btn-sm" data-act="check">${icon("quiz")}<span>Làm bài kiểm tra xác nhận</span></button>`;
    } else if (state.learning_state === "NEEDS_REVIEW") {
        body = `${alertBox("warn", `<strong>Lần kiểm tra gần nhất chưa đạt</strong> (${latest?.score ?? "—"}/100, cần ${latest?.pass_threshold ?? 80}). Hãy ôn lại phần còn yếu, rồi làm lại. Thời gian học và lịch sử vẫn được giữ.`)}
            <div class="row">${latest ? `<a class="btn btn-secondary btn-sm" href="#/mini/${esc(latest.micro_id)}">Xem phần chưa đạt</a>` : ""}${state.retry_at && !state.open_check_id
                ? `<span class="meta">${icon("clock")}<span>Bài mới mở lúc <strong>${fmtDateTime(state.retry_at)}</strong>, sau khi bạn có thời gian ôn lại.</span></span>`
                : `<button class="btn btn-primary btn-sm" data-act="check">${icon("refresh")}<span>${state.open_check_id ? "Tiếp tục làm lại" : "Làm lại bài kiểm tra"}</span></button>`}</div>`;
    } else {
        body = `${state.time_reached ? alertBox("good", "Bạn đã học đủ thời lượng dự kiến. Hãy làm bài kiểm tra hoàn thành.") : `<p class="sub small">Bạn có thể kiểm tra sớm nếu đã tự tin. Bài học chỉ hoàn thành khi bạn đạt bài kiểm tra, không phải khi đủ giờ.</p>`}
            <button class="btn ${state.time_reached ? "btn-primary" : "btn-secondary"} btn-sm" data-act="check">${icon("quiz")}<span>Làm bài kiểm tra hoàn thành</span></button>`;
    }
    return `<section class="card jr-side">${sectionHead("quiz", "Kiểm tra hoàn thành", "Ngưỡng đạt 80/100, chấm theo đáp án.")}${body}</section>`;
}

function reviewCard(detail) {
    const { state } = detail;
    const latest = detail.reviews.find(item => ["PASSED", "FAILED"].includes(item.status));
    let body;
    if (state.review_state === "DUE") {
        body = `${alertBox("warn", "<strong>Đến hạn ôn tập.</strong> Bài ôn tập ngắn dùng câu hỏi tương đương, không lặp nguyên câu cũ.")}${state.review_micro_id ? `<a class="btn btn-primary btn-sm" href="#/mini/${esc(state.review_micro_id)}">${icon("quiz")}<span>Làm bài ôn tập</span></a>` : '<p class="sub small">Bài ôn tập đang được tạo, hãy tải lại sau ít phút.</p>'}`;
    } else if (state.review_state === "SCHEDULED") {
        body = `<p>Ôn tập vào <strong>${fmtDateTime(state.review_due_at)}</strong>. Đến hạn, hệ thống nhắc và mở bài ôn tập.</p>`;
    } else if (state.review_state === "RELEARN") {
        body = `${alertBox("bad", `<strong>Lần ôn tập gần nhất chưa đạt</strong> (${latest?.score ?? "—"}/100). ${latest?.weak_topics?.length ? `Cần củng cố: ${esc(latest.weak_topics.join(", "))}.` : ""} Kết quả này không hạ mức năng lực đã xác thực.`)}
            <button class="btn btn-primary btn-sm" data-act="reschedule">${icon("calendar")}<span>Đã ôn lại, đặt lịch kiểm tra</span></button>`;
    } else if (state.review_state === "PASSED") {
        body = alertBox("good", `<strong>Ôn tập đạt</strong> (${latest?.score ?? "—"}/100).`);
    } else {
        body = `<p class="sub small">Lịch ôn tập bắt đầu đếm khi bạn đạt bài kiểm tra hoàn thành.</p>`;
    }
    return `<section class="card jr-side">${sectionHead("refresh", "Ôn tập định kỳ", "Theo dõi khả năng ghi nhớ, không tự hạ mức năng lực.")}${body}</section>`;
}

function practicePane(detail) {
    if (!detail.practice.length) return `<div class="card">${emptyView("Chưa có bài thực hành", "Bài học này chưa có bài thực hành riêng.")}</div>`;
    return detail.practice.map(item => `<section class="card stack-sm jr-practice" data-exercise="${esc(item.exercise_id)}">
        <div class="row-between"><h3>${esc(item.title)}</h3><span class="row">${item.latest ? `<span class="badge ${item.latest.score === 100 ? "badge-good" : "badge-warn"}">Lần gần nhất ${item.latest.score}/100</span>` : ""}<span class="badge badge-muted">≈ ${item.minutes} phút</span></span></div>
        <p class="exam-prompt">${esc(item.prompt)}</p>
        <details class="exam-data"><summary class="small"><strong>Dữ liệu mẫu</strong> (bảng <code>orders_raw</code>, tệp <code>orders.csv</code>)</summary><div class="dataset" style="margin-top:6px"><table><thead><tr>${item.dataset.columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${item.dataset.rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>
        <div data-practice-workspace></div>
        <div class="row-between"><span class="sub small">Hệ thống kiểm tra: ${esc(item.checks.join("; "))}.</span><button class="btn btn-primary btn-sm" data-act="practice-check" data-id="${esc(item.exercise_id)}">${icon("check")}<span>Kiểm tra bài làm</span></button></div>
        <div data-practice-result>${item.latest ? practiceResult(item.latest) : ""}</div>
        <p class="sub small">Bài thực hành chỉ để tự kiểm tra, không phải bằng chứng năng lực.</p></section>`).join("");
}

function practiceResult(result) {
    return `<div class="jr-practice-result"><strong>${result.score}/100</strong><ul class="stack-sm">${result.cases.map(item => `<li class="case ${item.passed ? "is-pass" : "is-fail"}"><span class="case-mark" aria-hidden="true">${item.passed ? "✓" : "✕"}</span><div><span>${esc(item.description)}</span><span class="sub small nowrap">${item.passed ? item.points : 0}/${item.points} điểm</span></div></li>`).join("")}</ul></div>`;
}

const TABS = [["overview", "Tổng quan", "info"], ["content", "Nội dung", "book"], ["resources", "Học liệu", "link"], ["practice", "Thực hành", "code"], ["progress", "Tiến độ và ôn tập", "clock"]];

function lessonPane(detail, tab) {
    const { activity, state } = detail;
    if (tab === "content") {
        return `<section class="card stack-sm">${sectionHead("book", "Nội dung cần học", "Học lần lượt từng phần, mỗi phần dùng học liệu ở tab Học liệu.")}
            <ol class="jr-parts">${(activity.learning_objectives || []).map((text, index) => `<li><span class="jr-part-no">${index + 1}</span><div><strong>Phần ${index + 1}</strong><p>${esc(text)}</p></div></li>`).join("")}</ol>
            <p class="small"><strong>Đầu ra cần đạt:</strong> ${esc(activity.learning_outcome || "")}</p></section>`;
    }
    if (tab === "resources") {
        return `<section class="card stack-sm">${sectionHead("link", "Học liệu", "Học liệu đã duyệt, đường dẫn được kiểm tra định kỳ.")}${detail.resources.length ? `<ul class="jr-resources">${detail.resources.map(resourceItem).join("")}</ul>` : alertBox("warn", "Bài học này chưa có học liệu đã duyệt.")}</section>`;
    }
    if (tab === "practice") return practicePane(detail);
    if (tab === "progress") {
        return `<div class="grid grid-2">
            <section class="card">${sectionHead("clock", "Các phiên học", `Tổng ${duration(state.study_seconds)}`)}${historyList(detail.sessions, "Chưa có phiên học nào.", item => `<li><div><strong class="small">${fmtDateTime(item.started_at)}</strong><span class="sub small">${duration(item.elapsed_seconds)} · ${esc(item.status === "ENDED" ? "Đã kết thúc" : item.status === "RUNNING" ? "Đang chạy" : "Tạm dừng")}${item.pause_reason === "INTERRUPTED" ? " · tự dừng do gián đoạn" : ""}</span></div></li>`)}</section>
            <section class="card">${sectionHead("quiz", "Kiểm tra hoàn thành", `${state.graded_attempts} lần đã chấm`)}${historyList(detail.checks, "Chưa làm bài kiểm tra.", item => `<li><div><a class="small" href="#/mini/${esc(item.micro_id)}"><strong>Lần ${item.attempt_no ?? "—"}</strong></a><span class="sub small">${item.score === null || item.score === undefined ? "Chưa nộp" : `${item.score}/100`} · ${fmtDateTime(item.submitted_at || item.created_at)}</span></div>${statusBadge(item.status)}</li>`)}</section>
            <section class="card">${sectionHead("refresh", "Ôn tập định kỳ", state.review_due_at ? `Lần tới: ${fmtDate(state.review_due_at)}` : "")}${historyList(detail.reviews, "Chưa có lần ôn tập nào.", item => `<li><div><a class="small" href="#/mini/${esc(item.micro_id)}"><strong>${fmtDate(item.due_at)}</strong></a><span class="sub small">${item.score === null || item.score === undefined ? "Chưa làm" : `${item.score}/100`}${item.weak_topics?.length ? ` · cần củng cố: ${esc(item.weak_topics.join(", "))}` : ""}</span></div>${statusBadge(item.status)}</li>`)}</section>
        </div>`;
    }
    const prerequisites = detail.prerequisites.length ? `<p class="small"><strong>Cần học trước:</strong> ${detail.prerequisites.map(item => `<a href="${BASE}/lesson/${esc(item.activity_id)}">${esc(item.title)}</a> ${learningBadge(item.learning_state)}`).join(", ")}</p>` : "";
    return `<section class="card stack-sm">${sectionHead("info", "Tổng quan bài học", "")}
        <p>${esc(activity.learning_outcome || "")}</p>
        <dl class="jr-facts"><div><dt>Kỹ năng</dt><dd>${skillIcon(activity.target_skill)} ${esc(skillName(activity.target_skill))}</dd></div><div><dt>Cấp độ kỹ năng</dt><dd>Mức ${activity.target_level} · ${esc(LEVEL_NAMES[activity.target_level] || "")}</dd></div>
            <div><dt>Thời lượng dự kiến</dt><dd>${fmtHours(activity.estimated_hours)}</dd></div><div><dt>Tuần</dt><dd>${detail.weeks.map(number => `<a href="${BASE}/week/${number}">Tuần ${number}</a>`).join(", ") || (detail.carried_over ? "Đã hoàn thành ở phiên bản trước" : "—")}</dd></div></dl>
        <h3 class="h-ic">${icon("target")}<span>Mục tiêu cần đạt</span></h3><ul class="rules">${(activity.learning_objectives || []).map(text => `<li>${esc(text)}</li>`).join("")}</ul>${prerequisites}</section>
        ${mistakesCard(detail.mistakes)}`;
}

/** The checks this learner failed in their newest graded practical answer of this skill (server list, read only). */
function mistakesCard(mistakes) {
    if (!mistakes?.length) return "";
    const row = item => `<li><div><strong>${esc(item.check)}</strong>${item.related ? ' <span class="badge">Gần với bài này</span>' : ""}
        <span class="sub small">${esc(item.source)} · ${esc(item.topic || "")} · ${esc(fmtDate(item.submitted_at))}</span>
        ${item.blank ? '<span class="sub small">Bạn đã bỏ trống câu này.</span>' : item.answer_gave ? `<span class="sub small">Bài làm khi đó: ${esc(item.answer_gave)}</span>` : ""}</div></li>`;
    return `<section class="card stack-sm jr-mistakes">${sectionHead("alert", "Lỗi bạn đã mắc ở kỹ năng này", "Từ bài làm có chạy test case gần nhất. Học bài này để sửa đúng những chỗ đó.")}
        <ul class="jr-mistake-list">${mistakes.map(row).join("")}</ul></section>`;
}

function cycleModal(detail, onChosen) {
    const presets = detail.review_presets;
    openModal(`<h2 class="h-ic">${icon("calendar")}<span>Chọn thời gian kiểm tra lại</span></h2><p class="sub">${esc(detail.activity.title)}</p>
        <form data-form="cycle" class="stack" style="margin-top:12px"><div class="seg" role="radiogroup" aria-label="Thời gian kiểm tra lại">${presets.map((days, index) => `<label class="seg-option"><input type="radio" name="preset" value="${days}" ${index === 2 ? "checked" : ""}>${icon("calendar")}<span>${days} ngày</span></label>`).join("")}<label class="seg-option"><input type="radio" name="preset" value="custom">${icon("pen")}<span>Tùy chỉnh</span></label></div>
        <label class="field" data-custom hidden><span>Số ngày (${detail.review_limits.min}-${detail.review_limits.max})</span><input class="input" type="number" name="custom" min="${detail.review_limits.min}" max="${detail.review_limits.max}" value="10"></label>
        <div class="hint-box">${icon("info")}<span>Ngày kiểm tra lại được tính từ lúc bạn đạt bài kiểm tra hoàn thành. Sau khi bắt đầu học, lựa chọn này được chốt và không đổi được.</span></div>
        <div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-primary" type="submit">${icon("play")}<span>Chốt và bắt đầu học</span></button></div></form>`);
    const form = document.querySelector('form[data-form="cycle"]');
    form.addEventListener("change", () => { form.querySelector("[data-custom]").hidden = formData(form).preset !== "custom"; });
    register({
        forms: {
            cycle: async element => {
                const values = formData(element);
                const days = Number(values.preset === "custom" ? values.custom : values.preset);
                if (!Number.isInteger(days) || days < detail.review_limits.min || days > detail.review_limits.max) { toast(`Hãy nhập từ ${detail.review_limits.min} đến ${detail.review_limits.max} ngày.`, "bad"); return; }
                closeModal();
                await onChosen(days);
            },
        },
    });
}

// Timers and listeners of the lesson on screen; a re-render or leaving the page stops them first.
let stopLesson = () => {};

async function lessonPage(activityId, tab = "overview") {
    stopLesson();
    const detail = await api(`/me/journey/lessons/${encodeURIComponent(activityId)}`);
    const { activity, state } = detail;
    const week = detail.weeks[0];
    const workspaceState = {};
    const answers = {};
    setView(`<div class="stack">${crumbs([["Lộ trình học tập", BASE], ...(week ? [[`Tuần ${week}`, `${BASE}/week/${week}`]] : []), [activity.title]])}
        <section class="card jr-lesson-head"><div class="jr-lesson-title">${tile("book", "brand")}<div><span class="eyebrow-label">${esc(skillName(activity.target_skill))} · Mức ${activity.target_level}</span><h2>${esc(activity.title)}</h2>
            <div class="row">${learningBadge(state.learning_state, state.level_short)}${reviewBadge(state.review_state, state.review_due_at)}<span class="meta">${icon("clock")}<span>Dự kiến ${fmtHours(activity.estimated_hours)}</span></span></div></div></div></section>
        <div class="jr-lesson-grid"><div class="stack">
            <div class="tabs jr-tabs" role="tablist">${TABS.map(([id, label, name]) => `<button type="button" role="tab" class="tab ${id === tab ? "is-active" : ""}" aria-selected="${id === tab}" data-act="tab" data-tab="${id}">${icon(name)}<span>${label}</span></button>`).join("")}</div>
            <div id="jr-pane">${lessonPane(detail, tab)}</div>
            <div class="row-between jr-pager">${detail.previous_lesson ? `<a class="btn btn-secondary btn-sm" href="${BASE}/lesson/${esc(detail.previous_lesson)}">← Bài trước</a>` : "<span></span>"}${detail.next_lesson ? `<a class="btn btn-secondary btn-sm" href="${BASE}/lesson/${esc(detail.next_lesson)}">Bài tiếp theo →</a>` : ""}</div>
        </div><aside class="stack jr-aside">${timerCard(detail)}${completionCard(detail)}${reviewCard(detail)}</aside></div></div>`);
    startSessionClocks();
    if (tab === "practice") mountPractice(detail, workspaceState, answers);

    // Heartbeat while the page is open; the server decides what counts.
    const session = state.session;
    if (session?.status === "RUNNING") {
        const send = async () => {
            try {
                const result = await api(`/me/study/${session.session_id}`, { method: "POST", body: { action: "heartbeat" } });
                if (result.session.status !== "RUNNING") { toast("Phiên học đã tạm dừng.", "bad"); lessonPage(activityId, tab); }
            } catch { /* Offline: the server pauses the session at the last heartbeat it received. */ }
        };
        const beat = setInterval(send, (session.heartbeat_seconds || 60) * 1000);
        const onVisible = () => { if (!document.hidden) send(); };
        document.addEventListener("visibilitychange", onVisible);
        window.addEventListener("online", send);
        stopLesson = () => { clearInterval(beat); clearInterval(clockTimer); document.removeEventListener("visibilitychange", onVisible); window.removeEventListener("online", send); stopLesson = () => {}; };
    } else {
        stopLesson = () => { clearInterval(clockTimer); stopLesson = () => {}; };
    }
    const reload = () => lessonPage(activityId, tab);
    const startStudy = async (days, switching = false) => {
        try {
            await api("/me/study/start", { method: "POST", body: { activity_id: activityId, review_cycle_days: days ?? null, switch: switching } });
            toast("Đã bắt đầu phiên học.", "good");
            reload();
        } catch (error) {
            if (error.status === 409 && !switching && /đang bấm giờ/.test(error.message)) {
                if (await confirmDialog("Chuyển sang bài này?", `${error.message} Bài kia sẽ được tạm dừng và giữ nguyên thời gian đã học.`, { confirmLabel: "Tạm dừng bài kia và bắt đầu" })) await startStudy(days, true);
                return;
            }
            toast(error.message, "bad");
        }
    };
    register({
        cleanup: () => stopLesson(),
        actions: {
            tab: element => lessonPage(activityId, element.dataset.tab),
            "study-start": element => {
                if (state.cycle_locked) { withBusy(element, () => startStudy(null)); return; }
                cycleModal(detail, days => startStudy(days));
            },
            study: element => withBusy(element, async () => {
                await api(`/me/study/${session.session_id}`, { method: "POST", body: { action: element.dataset.action } });
                toast(element.dataset.action === "pause" ? "Đã tạm dừng. Thời gian đã học được giữ lại." : "Đã tiếp tục phiên học.", "good");
                reload();
            }),
            "study-end": async element => {
                if (!(await confirmDialog("Kết thúc phiên học?", "Thời gian của phiên này được lưu vào tổng thời gian học. Bạn có thể bắt đầu phiên mới bất cứ lúc nào.", { confirmLabel: "Kết thúc phiên" }))) return;
                await withBusy(element, async () => {
                    const result = await api(`/me/study/${session.session_id}`, { method: "POST", body: { action: "end" } });
                    toast(`Đã lưu phiên học ${duration(result.session.elapsed_seconds)}.`, "good");
                    reload();
                });
            },
            check: async element => {
                if (state.open_check_id) { window.location.hash = `#/mini/${state.open_check_id}`; return; }
                const text = state.time_reached ? "Bài kiểm tra theo mục tiêu của bài học. Phiên học đang mở sẽ được kết thúc trước." : `Bạn đã học ${duration(state.study_seconds)} trên ${fmtHours(state.estimated_hours)} dự kiến. Bạn vẫn có thể kiểm tra sớm nếu tự tin; nếu chưa đạt, bạn học tiếp và làm lại.`;
                if (!(await confirmDialog("Làm bài kiểm tra hoàn thành?", text, { confirmLabel: "Làm bài kiểm tra" }))) return;
                await withBusy(element, async () => {
                    const result = await api(`/activities/${encodeURIComponent(activityId)}/knowledge-check`, { method: "POST", body: { confirm: true } });
                    if (result.lesson_check.status === "UNAVAILABLE") { toast(result.message, "bad"); reload(); return; }
                    window.location.hash = `#/mini/${result.lesson_check.micro_id}`;
                });
            },
            reschedule: element => withBusy(element, async () => {
                const result = await api(`/activities/${encodeURIComponent(activityId)}/review/reschedule`, { method: "POST" });
                toast(`Đã đặt lịch ôn tập vào ${fmtDate(result.review_due_at)}.`, "good");
                reload();
            }),
            "practice-check": element => withBusy(element, async () => {
                const id = element.dataset.id;
                const result = await api(`/me/practice/${id}/check`, { method: "POST", body: { answer: answers[id] || "" } });
                document.querySelector(`[data-exercise="${id}"] [data-practice-result]`).innerHTML = practiceResult(result);
                toast(result.score === 100 ? "Bài thực hành đúng hoàn toàn." : `Bài thực hành đạt ${result.score}/100.`, result.score === 100 ? "good" : "");
            }),
        },
    });
}

function mountPractice(detail, workspaceState, answers) {
    detail.practice.forEach(item => {
        answers[item.exercise_id] = item.latest?.answer || "";
        const root = document.querySelector(`[data-exercise="${item.exercise_id}"] [data-practice-workspace]`);
        mountWorkspace(root, { ...item, question_id: item.exercise_id, dataset: item.dataset }, {
            value: answers[item.exercise_id], state: (workspaceState[item.exercise_id] ||= {}),
            onChange: value => { answers[item.exercise_id] = value.slice(0, item.max_chars); },
            run: code => api(`/me/practice/${item.exercise_id}/run`, { method: "POST", body: { code } }),
        });
    });
}

/* ------------------------------------------------------------------ final assessment */

function rulesList(rules) {
    return `<ul class="jr-rules">${rules.map(rule => `<li class="${rule.passed ? "is-pass" : "is-fail"}"><span class="case-mark" aria-hidden="true">${rule.passed ? "✓" : "✕"}</span><div><strong>${esc(RULES[rule.rule] || rule.rule)}</strong><span class="sub small">${esc(rule.detail)}</span></div></li>`).join("")}</ul>`;
}

async function finalPage() {
    const data = await api("/me/final-assessment");
    if (data.attempt) {
        // An attempt in progress always opens on the exam screen.
        window.location.replace("#/final-exam");
        return;
    }
    setBar();
    const last = data.attempts.find(item => item.status === "GRADED");
    const intro = `<section class="card stack">${sectionHead("trophy", "Bài đánh giá tổng hợp cuối lộ trình", "Mô phỏng công việc thực tế theo JD đã chọn.")}
        <ul class="rules"><li>Mỗi kỹ năng JD yêu cầu có một bài thực hành ở đúng độ khó của mức JD: viết SQL, code Python, xử lý dữ liệu, trực quan hóa hoặc viết báo cáo.</li>
            <li>Chấm hoàn toàn bằng test case và rubric; AI không chấm điểm.</li>
            <li>Đạt khi: điểm tổng từ ${data.pass_rules.score}, mọi kỹ năng cốt lõi đạt mức JD, đáp ứng từ ${data.pass_rules.coverage}% trọng số JD, làm đủ mọi bài và không mắc lỗi trọng yếu.</li>
            <li>Có giới hạn thời gian. Rời màn hình 3 lần bài tự nộp; không dùng sao chép, dán; trợ lý AI tạm dừng trong lúc làm.</li>
            <li>Chưa đạt thì học tiếp phần còn thiếu và làm lại sau ${data.pass_rules.retake_hours} giờ. Lịch sử học tập được giữ nguyên.</li></ul>
        ${data.can_start ? `<button class="btn btn-primary" data-act="final-start">${icon("play")}<span>Bắt đầu bài đánh giá</span></button>` : alertBox(data.passed_attempt_id ? "good" : "info", esc(data.reason || ""))}
        ${data.retake_at && !data.can_start && !data.passed_attempt_id ? `<p class="sub small">Có thể làm lại từ ${fmtDateTime(data.retake_at)}.</p>` : ""}</section>`;
    const history = data.attempts.length ? `<section class="card">${sectionHead("clock", "Lịch sử bài đánh giá", "")}<ul class="feed">${data.attempts.map(item => `<li><div><a class="small" href="${BASE}/final/result/${esc(item.attempt_id)}"><strong>${fmtDateTime(item.started_at)}</strong></a><span class="sub small">${item.score ?? "—"}/100${item.auto_submitted ? " · tự động nộp" : ""}</span></div>${item.passed === true ? statusBadge("PASSED") : item.passed === false ? statusBadge("FAILED") : statusBadge(item.status)}</li>`).join("")}</ul></section>` : "";
    setView(`<div class="stack">${crumbs([["Lộ trình học tập", BASE], ["Bài đánh giá tổng hợp"]])}${intro}${last ? `<a class="btn btn-secondary btn-sm" href="${BASE}/final/result/${esc(last.attempt_id)}">Xem kết quả gần nhất</a>` : ""}${history}</div>`);
    register({
        actions: {
            "final-start": async element => {
                if (!(await confirmDialog("Bắt đầu bài đánh giá tổng hợp?", "Đồng hồ chạy ngay khi bắt đầu và không dừng lại. Hãy chuẩn bị đủ thời gian.", { confirmLabel: "Bắt đầu" }))) return;
                await withBusy(element, async () => { await api("/me/final-assessment/start", { method: "POST" }); window.location.hash = "#/final-exam"; });
            },
        },
    });
}

async function finalResultPage(attemptId) {
    const status = await api("/me/final-assessment").catch(() => null);
    const own = (status?.attempts || []).find(item => item.attempt_id === attemptId);
    if (own && ["SUBMITTED", "GRADING"].includes(own.status)) { waitForFinal(attemptId); return; }
    const data = await api(`/me/final-assessment/${encodeURIComponent(attemptId)}/review`);
    const summary = data.summary;
    const rows = data.skills.map(item => `<tr><td><span class="skill-name">${skillIcon(item.skill_code)}<strong>${esc(skillName(item.skill_code))}</strong></span>${item.is_core ? ' <span class="badge">Cốt lõi</span>' : ""}</td>
        <td class="center">${summary.levels_at_roadmap_start[item.skill_code] ?? "—"}</td><td class="center">${item.level_before ?? "—"}</td><td class="center"><span class="level-pill level-verified" data-level="${item.verified_level}">${item.verified_level}</span></td><td class="center">${item.level_after}</td><td class="center">${item.target_level}</td>
        <td>${item.met ? statusBadge("PASSED") : `<span class="badge badge-warn">Thiếu ${item.target_level - item.verified_level} mức</span>`}<span class="sub small">${item.percent}/100</span></td></tr>`).join("");
    const head = data.passed
        ? `<section class="card jr-congrats">${tile("trophy", "good")}<div><span class="eyebrow-label">Hoàn thành lộ trình</span><h2>Chúc mừng! Bạn đã hoàn thành hành trình học tập CareerAdapt.</h2><p>Đạt tiêu chí đánh giá theo JD đã chọn.</p></div></section>`
        : `<section class="card jr-retry">${tile("target", "warn")}<div><span class="eyebrow-label">Chưa đạt</span><h2>Chưa đạt bài đánh giá tổng hợp</h2><p>Hãy học tiếp các kỹ năng còn thiếu bên dưới. Bài học đã hoàn thành và thời gian học vẫn được giữ.${data.retake_at ? ` Có thể làm lại từ ${fmtDateTime(data.retake_at)}.` : ""}</p></div></section>`;
    setView(`<div class="stack">${crumbs([["Lộ trình học tập", BASE], ["Bài đánh giá tổng hợp", `${BASE}/final`], ["Kết quả"]])}${head}
        <section class="card"><div class="jr-metrics">
            <div class="jr-metric"><span class="jr-metric-label">${icon("quiz")}<span>Điểm bài đánh giá</span></span><strong>${data.score}/100</strong><span class="sub small">Ngưỡng ${data.pass_threshold} · đáp ứng ${data.coverage}% JD</span></div>
            <div class="jr-metric"><span class="jr-metric-label">${icon("clock")}<span>Tổng thời gian học</span></span><strong>${duration(summary.study_seconds)}</strong></div>
            <div class="jr-metric"><span class="jr-metric-label">${icon("check")}<span>Bài học đã hoàn thành</span></span><strong>${summary.lessons_done}/${summary.lessons_total}</strong></div>
            <div class="jr-metric"><span class="jr-metric-label">${icon("shield")}<span>Kỹ năng đạt mức JD</span></span><strong>${data.skills.filter(item => item.met).length}/${data.skills.length}</strong></div></div>
            <h3 style="margin-top:14px">Các điều kiện đạt</h3>${rulesList(data.rules)}</section>
        <section class="card">${sectionHead("chart", "Cấp độ kỹ năng trước và sau", "Bài đánh giá có thể nâng mức đã xác thực, không bao giờ hạ.")}
            <div class="table-wrap result-table"><table><thead><tr><th>Kỹ năng</th><th class="center">Khi bắt đầu lộ trình</th><th class="center">Trước bài này</th><th class="center">Bài này</th><th class="center">Sau</th><th class="center">JD yêu cầu</th><th>Kết quả</th></tr></thead><tbody>${rows}</tbody></table></div></section>
        ${summary.remaining_gaps.length ? `<section class="card">${sectionHead("pulse", "Khoảng cách kỹ năng còn lại", "")}<ul class="rules">${summary.remaining_gaps.map(item => `<li>${esc(skillName(item.skill_code))}: mức ${item.current_level ?? "—"}, JD cần ${item.target_level}</li>`).join("")}</ul>
            ${summary.weak_lessons.length ? `<p class="small" style="margin-top:8px"><strong>Học lại:</strong> ${summary.weak_lessons.map(item => `<a href="${BASE}/lesson/${esc(item.activity_id)}">${esc(item.title)}</a>`).join(", ")}</p>` : ""}</section>` : ""}
        <div class="row"><a class="btn btn-secondary" href="${BASE}/final/review/${esc(data.attempt_id)}">${icon("quiz")}<span>Xem lại từng bài</span></a><a class="btn btn-primary" href="#/report">${icon("file")}<span>Báo cáo năng lực</span></a></div>
        <p class="sub small">${esc(data.scope_note)}</p></div>`);
}

async function finalReviewPage(attemptId) {
    const data = await api(`/me/final-assessment/${encodeURIComponent(attemptId)}/review`);
    renderReview(data, { backHref: `${BASE}/final/result/${attemptId}`, backLabel: "Quay lại kết quả" });
}

/** The exam screen of the final assessment: the same room, bar and rules as the Career Adapt exam, nothing else. */
/** Wait for a submitted final attempt to be graded, then open its result. */
function waitForFinal(attemptId) {
    renderGradingWait(async () => {
        const data = await api("/me/final-assessment");
        return (data.attempts || []).some(item => item.attempt_id === attemptId && item.status === "GRADED");
    }, () => { window.location.hash = `${BASE}/final/result/${attemptId}`; }, { title: "Đang chấm bài đánh giá tổng hợp" });
}

export async function renderFinalExam() {
    const data = await api("/me/final-assessment");
    if (!data.attempt) { window.location.replace(`${BASE}/final`); return; }
    if (data.attempt.status !== "IN_PROGRESS") { waitForFinal(data.attempt.attempt_id); return; }
    const attemptId = data.attempt.attempt_id;
    await renderExamRoom(data.attempt, () => waitForFinal(attemptId), { base: "/me/final-assessment" });
}

/* ------------------------------------------------------------------ router */

export async function renderRoadmap(rest = "") {
    stopLesson();
    setBar();
    const [kind, id, extra] = rest.split("/");
    if (kind === "week" && id) return weekPage(Number(id));
    if (kind === "lesson" && id) return lessonPage(decodeURIComponent(id));
    if (kind === "final" && id === "result" && extra) return finalResultPage(extra);
    if (kind === "final" && id === "review" && extra) return finalReviewPage(extra);
    if (kind === "final") return finalPage();
    return overviewPage();
}
