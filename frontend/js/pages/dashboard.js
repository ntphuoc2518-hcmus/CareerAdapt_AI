/** Dashboard: every number comes from the same APIs the plan tabs use; a widget without data says so. */
import { api, app, emptyView, esc, fmtDate, fmtDateTime, LOCALE, safeUrl, setView, skillName, statusBadge } from "../core.js";
import { botBody } from "../bot.js";
import { icon, skillIcon, tile } from "../icons.js";
import { EVENTS } from "./progress.js";

const EVENT_TILES = {
    PROCESS_COMPLETED: ["trophy", "warn"], PROCESS_STARTED: ["target", "brand"], EXAM_STARTED: ["quiz", "brand"], TEST_SUBMITTED: ["check", "good"], TEST_STARTED: ["quiz", "s3"],
    GENERATE_ROADMAP: ["route", "s4"], UPDATE_PROGRESS: ["check", "good"], SKILL_REPORT_CONFIRMED: ["pen", "s5"], TARGET_CONFIRMED: ["file", "s1"], MINI_TEST_SUBMITTED: ["quiz", "s3"],
    UPDATE_PROFILE: ["user", "brand"], PROCESS_RESET: ["refresh", "bad"],
    LESSON_CHECK_ISSUED: ["quiz", "warn"], LESSON_CHECK_SUBMITTED: ["check", "good"],
    STUDY_STARTED: ["clock", "brand"], STUDY_ENDED: ["clock", "s3"], REVIEW_SCHEDULED: ["calendar", "s4"], ROADMAP_REPLANNED: ["route", "s4"],
    LEVEL_RECONFIRMED: ["shield", "good"], FINAL_STARTED: ["trophy", "brand"], FINAL_GRADED: ["trophy", "warn"],
};
const RESOURCE_TILES = { COURSE: ["book", "brand"], LECTURE: ["chat", "s3"], EXERCISE: ["code", "s4"], OFFICIAL_DOC: ["file", "s1"], ARTICLE: ["file", "s2"], INTERNAL_GUIDE: ["pen", "s5"] };

/** A failed call leaves only its own widget in an error state. */
const settle = promise => promise.then(value => ({ value }), error => ({ error: error.message }));
const widgetError = message => `<div class="alert alert-bad">${icon("alert")}<div>Không tải được phần này. ${esc(message)}</div></div>`;

function ago(time) {
    const seconds = (new Date(time).getTime() - Date.now()) / 1000;
    if (Number.isNaN(seconds)) return "";
    const format = new Intl.RelativeTimeFormat(LOCALE(), { numeric: "auto" });
    for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]]) {
        if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
    }
    return format.format(0, "second");
}

const SPARK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.5 13.9 9.6 22 12l-8.1 2.4L12 22.5l-1.9-8.1L2 12l8.1-2.4Z"/></svg>';

/** The robot beside the welcome: one head in two frames (eyes open, eyes closed) so it blinks; tiles show only real figures. */
function heroArt(readiness) {
    const match = readiness === null || readiness === undefined
        ? `<span class="hero-tile hero-tile-match">${icon("chart")}</span>`
        : `<span class="hero-tile hero-tile-match">${icon("chart")}<strong>${Math.round(readiness)}%</strong><small>đáp ứng JD</small></span>`;
    return `<div class="hero-art" aria-hidden="true">
        <span class="hero-glass"></span>
        <span class="hero-spark hero-spark-a">${SPARK}</span><span class="hero-spark hero-spark-b">${SPARK}</span><span class="hero-spark hero-spark-c">${SPARK}</span>
        ${match}
        <span class="hero-tile hero-tile-chat">${icon("chat")}</span>
        <span class="hero-tile hero-tile-check">${icon("shield")}<i>${icon("check")}</i></span>
        <span class="hero-orbit"><i></i></span>
        <span class="hero-bot">
            <span class="hero-bot-halo"></span>
            ${botBody("hb", "hero-bot-body")}
            <span class="hero-bot-head"><img src="/img/ai-head-open.webp" alt="" width="300" height="238"><img class="hero-bot-blink" src="/img/ai-head-closed.webp" alt="" width="300" height="238"></span>
            <span class="hero-bot-shadow"></span>
        </span>
    </div>`;
}

function hero(state, gap) {
    const run = state.run;
    let status = "Bạn chưa thực hiện Quy trình Career Adapt";
    let tone = "is-idle";
    let actions = `<a class="btn btn-light" href="#/process"><span>Bắt đầu ngay</span>${icon("arrow")}</a>`;
    if (run?.status === "COMPLETED") {
        status = `Đã hoàn tất quy trình ${esc(run.career_title)}`;
        tone = "is-done";
        actions = `<a class="btn btn-light" href="#/plan/da/overview"><span>Xem kết quả và luyện tập</span>${icon("arrow")}</a>
            <a class="btn hero-btn-ghost" href="#/plan/da/roadmap">${icon("route")}<span>Lộ trình kỹ năng</span></a>`;
    } else if (run) {
        status = `Đang ở bước ${run.step_index + 1}/${state.steps.length}: ${esc(state.steps[run.step_index].label)}`;
        tone = "is-active";
        actions = `<a class="btn btn-light" href="#/flow"><span>Tiếp tục</span>${icon("arrow")}</a>`;
    }
    const readiness = gap?.value?.is_readiness_locked === false ? gap.value.readiness : null;
    return `<section class="hero hero-v2"><div class="hero-copy">
        <span class="hero-state ${tone}"><i aria-hidden="true"></i><span>${status}</span></span>
        <h2>Chào mừng trở lại, <span class="hero-name" data-no-i18n>${esc(app.user.full_name)}</span>! <span aria-hidden="true">👋</span></h2>
        <p>Cùng khám phá lộ trình Career Adapt và phát triển bản thân với sự hỗ trợ của AI.</p>
        <div class="hero-actions">${actions}</div></div>
        ${heroArt(readiness)}</section>`;
}

const shortcut = (href, name, tone, title, text) => `<a class="card link-card" href="${href}">${tile(name, tone)}<div><strong>${esc(title)}</strong><span class="sub">${esc(text)}</span></div><span class="go">${icon("arrow")}</span></a>`;

function ring(percent, label = "Lộ trình hoàn thành") {
    const length = 2 * Math.PI * 52;
    return `<div class="ring" role="img" aria-label="${percent}%"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="52" class="ring-track"/><circle cx="60" cy="60" r="52" class="ring-bar" stroke-dasharray="${(length * percent) / 100} ${length}"/></svg><div><strong>${percent}%</strong><span>${esc(label)}</span></div></div>`;
}

const studied = seconds => {
    const minutes = Math.round((seconds || 0) / 60);
    return minutes < 60 ? `${minutes} phút` : `${Math.floor(minutes / 60)} giờ ${String(minutes % 60).padStart(2, "0")} phút`;
};

/** One figure: icon, label, value, a short note and a bar coloured by whether it is met. */
function metricTile(name, label, value, note, percent, met) {
    const tone = percent === null ? "muted" : met ? "good" : "warn";
    return `<li class="pc-tile is-${tone}"><span class="pc-tile-icon" aria-hidden="true">${icon(name)}</span><div class="pc-tile-body">
        <span class="pc-tile-label">${esc(label)}</span><strong class="pc-tile-value">${value}</strong><span class="pc-tile-note">${note}</span>
        <span class="meter pc-meter"><span style="width:${percent ?? 0}%"></span></span></div></li>`;
}

/** The single next step: the final assessment when lessons are done, otherwise the next lesson. */
function nextStep(journey) {
    if (!journey) return "";
    const final = journey.final || {};
    if (final.passed_attempt_id) return `<a class="pc-next is-good" href="#/plan/da/roadmap/final/result/${esc(final.passed_attempt_id)}">${icon("trophy")}<span><strong>Đã đạt bài đánh giá tổng hợp</strong><span>Xem kết quả hoàn thành và báo cáo năng lực.</span></span>${icon("arrow")}</a>`;
    if (final.eligible) return `<a class="pc-next" href="#/plan/da/roadmap/final">${icon("trophy")}<span><strong>${final.can_start ? "Sẵn sàng làm bài đánh giá tổng hợp" : "Đã hoàn thành mọi bài học"}</strong><span>${esc(final.can_start ? "Mọi bài học đã đạt kiểm tra hoàn thành." : final.reason || "")}</span></span>${icon("arrow")}</a>`;
    const next = journey.next_lesson;
    if (next) return `<a class="pc-next" href="#/plan/da/roadmap/lesson/${esc(next.activity_id)}">${icon("route")}<span><strong>Bài tiếp theo: ${esc(next.title)}</strong><span>Tuần ${next.week_number} · ${esc(skillName(next.target_skill))}</span></span>${icon("arrow")}</a>`;
    return "";
}

function progressCard(state, gap, roadmap, attempts, journey) {
    const head = `<div class="card-head"><h2 class="h-ic">${tile("chart", "brand", "tile-sm")}<span>Tổng quan tiến độ</span></h2><a class="btn btn-ghost btn-sm" href="#/plan/da/gap"><span>Chi tiết</span>${icon("arrow")}</a></div>`;
    if (state.run?.status !== "COMPLETED") {
        return `<section class="card">${head}${emptyView("Chưa có số liệu tiến độ", "Tiến độ được tính sau khi bạn hoàn tất Quy trình Career Adapt.", '<a class="btn btn-primary btn-sm" href="#/process">Đi đến quy trình</a>')}</section>`;
    }
    if (gap.error || roadmap.error) return `<section class="card">${head}${widgetError(gap.error || roadmap.error)}</section>`;
    const skills = gap.value.skill_evaluations || [];
    const core = skills.filter(item => item.is_core);
    const coreMet = core.filter(item => item.current_level !== null && item.current_level >= item.target_level).length;
    const last = (attempts.value?.attempts || []).find(item => item.status === "SUBMITTED" && item.composite_score !== null);
    const readiness = gap.value.readiness;
    const coverage = Math.round(gap.value.coverage * 100);
    const plan = journey?.value;
    // The ring counts lessons that passed their completion check, the same figure as the roadmap page.
    const lessons = plan ? `${plan.lessons_done}/${plan.lessons_total} bài học${plan.study_seconds >= 60 ? ` · đã học ${studied(plan.study_seconds)}` : ""}` : "";
    const lastScore = last ? Math.round(last.composite_score) : null;
    return `<section class="card progress-card">${head}<div class="pc-grid">
        <div class="pc-ring">${ring(plan ? plan.percent : 0, "Bài học hoàn thành")}${lessons ? `<span class="pc-ring-note">${esc(lessons)}</span>` : ""}</div>
        <ul class="pc-tiles">
            ${metricTile("target", "Mức đáp ứng mục tiêu", readiness === null ? "Chưa mở" : `${readiness}%`, readiness === null ? "Mở khi đủ bằng chứng" : "Theo JD đã chọn", readiness, readiness !== null && readiness >= 100)}
            ${metricTile("shield", "Kỹ năng cốt lõi", `${coreMet}/${core.length}`, "đạt mức JD yêu cầu", core.length ? Math.round((coreMet / core.length) * 100) : null, core.length > 0 && coreMet === core.length)}
            ${metricTile("check", "Độ phủ bằng chứng", `${gap.value.skills_measured}/${gap.value.skills_total}`, "kỹ năng đã có bài đo", coverage, coverage >= 100)}
            ${metricTile("quiz", "Kiểm tra kiến thức gần nhất", lastScore === null ? "Chưa có" : `${lastScore}/100`, last ? `${esc(last.title)} · ${fmtDate(last.submitted_at)}` : "Luyện tập ở mục Kiểm tra kiến thức", lastScore, lastScore !== null && lastScore >= 60)}
        </ul></div>
        ${nextStep(plan)}
        ${readiness === null ? '<p class="meta">' + icon("info") + "<span>Mức đáp ứng mở khi độ phủ từ 80% và đủ kỹ năng cốt lõi.</span></p>" : ""}</section>`;
}

function activityCard(history) {
    const head = `<div class="card-head"><h2 class="h-ic">${icon("bell")}<span>Hoạt động gần đây</span></h2><a class="small" href="#/plan/da/progress">Xem tất cả</a></div>`;
    if (history.error) return `<section class="card">${head}${widgetError(history.error)}</section>`;
    const items = history.value.slice(0, 5);
    return `<section class="card">${head}${items.length ? `<ul class="feed">${items.map(item => {
        const [name, tone] = EVENT_TILES[item.event] || ["clock", "brand"];
        return `<li>${tile(name, tone, "tile-sm")}<div><strong>${esc(EVENTS[item.event] || item.event)}</strong><span class="sub small">${esc(item.detail)}</span></div><time class="sub small" datetime="${esc(item.time)}" title="${fmtDateTime(item.time)}">${ago(item.time)}</time></li>`;
    }).join("")}</ul>` : emptyView("Chưa có hoạt động", "Lịch sử sẽ được ghi lại tại đây.")}</section>`;
}

/** Resources of the roadmap's unfinished learning activities first, then the approved catalogue. */
function featuredResources(roadmap, catalogue) {
    const verified = new Set(roadmap?.verified_activity_ids || []);
    const fromPlan = (roadmap?.schedule?.scheduled_weeks || []).flatMap(week => week.activities)
        .filter(item => item.kind !== "ASSESSMENT" && !verified.has(item.activity_id))
        .flatMap(item => item.resources.filter(resource => resource.available !== false).map(resource => ({ ...resource, skill_ids: resource.skill_ids || [item.target_skill] })));
    const seen = new Set();
    return [...fromPlan, ...(catalogue?.items || [])].filter(item => item.url && !seen.has(item.url) && seen.add(item.url)).slice(0, 3);
}

function resourcesCard(roadmap, catalogue) {
    const head = `<div class="card-head"><h2 class="h-ic">${icon("book")}<span>Tài liệu nổi bật</span></h2><a class="small" href="#/resources">Xem thêm</a></div>`;
    if (catalogue.error) return `<section class="card">${head}${widgetError(catalogue.error)}</section>`;
    const items = featuredResources(roadmap.value, catalogue.value);
    return `<section class="card">${head}${items.length ? `<div class="res-grid">${items.map(item => {
        const [name, tone] = RESOURCE_TILES[item.resource_type] || ["book", "brand"];
        return `<a class="res-mini" href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${tile(name, tone)}<strong>${esc(item.title)}</strong><span class="sub small">${esc(item.provider)}</span>
            <span class="row">${(item.skill_ids || []).slice(0, 2).map(code => `<span class="badge">${skillIcon(code)}<span>${esc(skillName(code))}</span></span>`).join("")}</span></a>`;
    }).join("")}</div>` : emptyView("Chưa có học liệu", "Học liệu đã duyệt sẽ hiện ở đây.")}</section>`;
}

function roadmapCard(state, roadmap) {
    const plan = roadmap.value;
    const progress = plan?.activity_progress || {};
    // Only lessons whose completion check is passed count as done; a self-marked lesson stays in the list.
    const verified = new Set(plan?.verified_activity_ids || []);
    const activities = (plan?.schedule?.scheduled_weeks || []).flatMap(week => week.activities.map(item => ({ ...item, week: week.week_number }))).filter(item => item.kind !== "ASSESSMENT");
    // An activity split over several weeks is one item to the learner.
    const open = activities.filter((item, index) => !verified.has(item.activity_id) && activities.findIndex(other => other.activity_id === item.activity_id) === index);
    const badge = !plan ? "" : open.length ? '<span class="badge badge-good">Đang thực hiện</span>' : '<span class="badge badge-good">Hoàn thành</span>';
    const head = `<div class="card-head"><h2 class="h-ic">${icon("route")}<span>Lộ trình học tập của bạn</span></h2>${badge}</div>`;
    if (roadmap.error) return `<section class="card">${head}${widgetError(roadmap.error)}</section>`;
    if (!plan) {
        return `<section class="card">${head}${emptyView("Chưa có lộ trình", "Lộ trình được tạo ở bước cuối của Quy trình Career Adapt.", state.run ? "" : '<a class="btn btn-primary btn-sm" href="#/process">Bắt đầu quy trình</a>')}</section>`;
    }
    return `<section class="card">${head}<div class="meter" style="margin-bottom:12px"><span style="width:${plan.verified_progress_percent ?? 0}%"></span></div>
        ${open.length ? `<ul class="route-list">${open.slice(0, 3).map(item => `<li>${skillIcon(item.target_skill)}<div><strong>${esc(item.title)}</strong><span class="sub small">Tuần ${item.week} · ${fmtDate(item.planned_start)} – ${fmtDate(item.planned_end)}</span></div>${statusBadge(progress[item.activity_id]?.status || "NOT_STARTED")}</li>`).join("")}</ul>`
            : emptyView("Đã xong mọi học phần", "Bạn có thể làm mini-test hoặc luyện tập thêm.")}
        <a class="btn btn-secondary btn-sm" href="#/plan/da/roadmap" style="margin-top:12px"><span>Mở lộ trình</span>${icon("arrow")}</a></section>`;
}

export async function renderDashboard() {
    const state = await api("/career-process/state");
    const done = state.run?.status === "COMPLETED";
    const [gap, roadmap, history, catalogue, attempts, journey] = await Promise.all([
        done ? settle(api("/me/gap")) : { value: null }, done ? settle(api("/me/roadmap")) : { value: null },
        settle(api("/me/history")), settle(api("/learning-resources")), done ? settle(api("/tests/attempts")) : { value: null },
        done ? settle(api("/me/journey")) : { value: null },
    ]);
    setView(`<div class="stack">${hero(state, gap)}
        <div class="grid grid-3">
            ${shortcut(done ? "#/plan/da/overview" : "#/plan", "chart", "brand", "Kế hoạch Career Adapt", "Kết quả, khoảng cách kỹ năng, lộ trình và nhắc nhở.")}
            ${shortcut("#/resources", "book", "s4", "Kho tài liệu", "Học liệu đã duyệt theo từng kỹ năng.")}
            ${shortcut("#/tests", "quiz", "s3", "Luyện tập kiểm tra kiến thức", "Làm bài trắc nghiệm để ôn tập, không ảnh hưởng kết quả quy trình.")}
        </div>
        <div class="grid grid-main">${progressCard(state, gap, roadmap, attempts, journey)}${activityCard(history)}</div>
        <div class="grid grid-main">${resourcesCard(roadmap, catalogue)}${roadmapCard(state, roadmap)}</div></div>`);
}
