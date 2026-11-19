/** Kế hoạch Career Adapt: what the finished process produced. Gap, roadmap and progress reuse their pages. */
import { alertBox, api, emptyView, esc, fmtDate, fmtDateTime, formatText, register, setSubnav, setView, skillName, SOURCE_TYPES, withBusy } from "../core.js";
import { openAssistantTask } from "../assistant.js";
import { icon, skillTile, tile, aiAvatar } from "../icons.js";
import { renderReview } from "./exam.js";
import { renderGap } from "./gap.js";
import { renderProgress } from "./progress.js";
import { basisCard, levelOf, openLevelGuide, renderRank, standing } from "./rank.js";
import { openResetDialog } from "./process.js";
import { renderRoadmap } from "./roadmap.js";
import { pageHero } from "../hero.js";
import { disclose } from "../disclose.js";
import { mountPlanAdvisor } from "../plan-advisor.js";
import { expressionForScore, expressiveHead } from "../faces.js";

const CAREER_TABS = [["da", "Data Analyst", "chart"], ["backend", "Backend Developer", "code"], ["qa", "QA Tester", "flask"]];
const SECTIONS = [["overview", "Khai báo và JD", "file"], ["exam", "Kết quả bài làm", "check"], ["gap", "Khoảng cách kỹ năng", "pulse"], ["roadmap", "Lộ trình học tập", "route"], ["rank", "Xếp hạng và lương", "trophy"], ["progress", "Nhắc nhở", "bell"]];
const METHODS = { PICK: "Chọn từ danh sách", IMPORT: "Nhập hoặc import tệp", FORM: "Biểu mẫu" };

/* 5.53: the plan's menu stands on the left like the Hồ sơ menu (a row above the page on narrower screens).
   Careers first, then the Data Analyst sections; each item is a link, so the page and history work as before. */
function subnav(career, section) {
    const item = (href, name, label, active, extra = "") => `<a class="pn-item ${active ? "is-active" : ""}" href="${href}" ${active ? 'aria-current="page"' : ""}>${icon(name)}<span>${label}</span>${extra}</a>`;
    const careers = CAREER_TABS.map(([id, label, name]) => item(`#/plan/${id}${id === "da" ? "/overview" : ""}`, name, label, id === career, id === "da" ? "" : '<span class="pn-soon">Sắp có</span>')).join("");
    const sections = career === "da" && section
        ? `<div class="pn-group pn-sections"><span class="pn-label">Data Analyst</span>${SECTIONS.map(([id, label, name]) => item(`#/plan/da/${id}`, name, label, id === section)).join("")}</div>` : "";
    setSubnav(`<div class="pn"><div class="pn-group pn-careers"><span class="pn-label">Nghề</span>${careers}</div>${sections}</div>`, { side: true });
    // As a row (narrow screens) the open item may sit past the edge; bring it into view. As a column this does nothing.
    document.querySelectorAll("#subnav .pn-group").forEach(group => {
        const active = group.querySelector(".pn-item.is-active");
        if (active && group.scrollWidth > group.clientWidth) group.scrollLeft = Math.max(0, active.offsetLeft - (group.clientWidth - active.offsetWidth) / 2);
    });
}

/* --- Khai báo và JD (5.49): one table compares what the learner reported with what the JD asks, a compact JD card
   and a quiet reset. The process is locked once finished, so everything here is shown, not edited. --- */
const METER_LABELS = { self: "Bạn khai", jd: "JD cần", verified: "Đã xác thực" };
function meter(level, kind) {
    const value = Number(level) || 0;
    return `<span class="ov-meter is-${kind}" role="img" aria-label="${METER_LABELS[kind]}: mức ${value}/3"><span class="ov-dots" aria-hidden="true">${[1, 2, 3].map(step => `<i class="${step <= value ? "is-on" : ""}"></i>`).join("")}</span><b>${value}</b></span>`;
}

function skillTable(run) {
    const declared = new Map(run.skills.map(item => [item.skill_code, item]));
    const required = new Map(((run.jd || {}).requirements || []).map(item => [item.skill_code, item]));
    const codes = [...required.keys(), ...[...declared.keys()].filter(code => !required.has(code))];
    if (!codes.length) return `<section class="card ov-skills">${emptyView("Không có", "Bạn chưa khai báo kỹ năng nào.")}</section>`;
    const rows = codes.map(code => {
        const self = declared.get(code);
        const need = required.get(code);
        const note = self?.evidence_note ? `<span class="ov-note">${esc(self.evidence_note)}</span>` : "";
        return `<li class="ov-row">${skillTile(code, "tile-sm")}<span class="ov-name"><strong>${esc(skillName(code))}</strong>${need?.is_core ? '<span class="ov-core">Cốt lõi</span>' : ""}${note}</span>
            ${self ? meter(self.level, "self") : '<span class="ov-none">—</span>'}${need ? meter(need.target_level, "jd") : '<span class="ov-none">—</span>'}</li>`;
    }).join("");
    return `<section class="card ov-skills"><div class="ov-head"><h2>Kỹ năng</h2><span class="ov-col is-self">Bạn khai</span><span class="ov-col is-jd">JD cần</span></div>
        <ul class="ov-rows">${rows}</ul>
        <p class="ov-foot-note">${icon("info")}<span>Mức tự khai chưa được xác thực.</span>${METHODS[run.skill_method] ? `<span class="ov-method">${esc(METHODS[run.skill_method])}</span>` : ""}</p></section>`;
}

function jdCard(jd) {
    const source = SOURCE_TYPES[jd.source_type];
    return `<section class="card ov-jd"><div class="ov-jd-head">${tile("file", "brand", "tile-sm")}<h2>JD</h2>${source ? `<span class="badge badge-muted">${esc(source)}</span>` : ""}</div>
        ${jd.summary ? `<div class="ov-summary" id="ov-summary">${formatText(jd.summary)}</div>
        <div class="ov-jd-meta"><span class="badge ${jd.summary_source === "AI" ? "badge-info" : "badge-muted"}">${jd.summary_source === "AI" ? "AI tóm tắt" : "Tóm tắt theo quy tắc"}</span><button class="btn btn-ghost btn-sm" type="button" data-act="jd-more" aria-expanded="false" aria-controls="ov-summary">Xem thêm</button></div>` : ""}
        <button class="btn btn-secondary ov-ai" type="button" data-act="jd-ai">${aiAvatar("xs")}<span>Phân tích JD của tôi</span></button></section>`;
}

function overviewHero(run) {
    const jd = run.jd || {};
    return pageHero({
        tone: "brand", icon: "file", kicker: "Khai báo và JD", title: jd.name ? esc(jd.name) : "JD chưa có tên",
        stats: [["user", "Tự khai", run.skills.length], ["target", "JD yêu cầu", (jd.requirements || []).length], ["lock", "Hoàn tất", fmtDate(run.completed_at), "muted"]],
    });
}

async function overview(run) {
    setView(`<div class="stack">${overviewHero(run)}<div class="ov-grid">${skillTable(run)}${jdCard(run.jd || {})}</div>
        <div class="ov-reset"><span>${icon("lock")}<span>Quy trình đã khóa từ ${fmtDateTime(run.completed_at)}</span></span><button class="btn btn-ghost btn-sm is-danger" type="button" data-act="reset">${icon("refresh")}<span>Làm lại từ đầu</span></button></div></div>`);
    register({
        actions: {
            reset: element => withBusy(element, openResetDialog),
            // The server's JD task: AI when available, otherwise its rule-based explanation, never an invented one.
            "jd-ai": element => openAssistantTask("jd_analysis", element.textContent.trim()),
            "jd-more": element => {
                const open = element.getAttribute("aria-expanded") !== "true";
                document.getElementById("ov-summary")?.classList.toggle("is-open", open);
                element.setAttribute("aria-expanded", String(open));
                element.textContent = open ? "Thu gọn" : "Xem thêm";
            },
        },
    });
    // The two-line preview needs "Xem thêm" only when the summary is longer than that.
    const summary = document.getElementById("ov-summary");
    if (summary && summary.scrollHeight <= summary.clientHeight + 2) document.querySelector('[data-act="jd-more"]')?.setAttribute("hidden", "");
}

/* Results tab. Every figure is read from /career-process/exam/review; only differences and counts are derived here. */
const round1 = value => Math.round(Number(value) * 10) / 10;

function scoreRing(data) {
    const percent = Math.max(0, Math.min(100, (Number(data.score) / Number(data.max_score || 100)) * 100));
    const length = 2 * Math.PI * 52;
    const mark = (Number(data.pass_threshold) / Number(data.max_score || 100)) * 360;
    return `<div class="ring result-ring ${data.passed ? "is-pass" : "is-fail"}" role="img" aria-label="${esc(String(data.score))}/${esc(String(data.max_score))}"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="52" class="ring-track"/><circle cx="60" cy="60" r="52" class="ring-bar" stroke-dasharray="${(length * percent) / 100} ${length}"/><line class="ring-mark" x1="104" y1="60" x2="118" y2="60" transform="rotate(${mark} 60 60)"/></svg><div><strong>${esc(String(data.score))}</strong><span>/ ${esc(String(data.max_score))} điểm</span></div></div>`;
}

/* --- Kết quả bài làm (5.50, filled out in 5.54): a score card with the robot and every task's points, a strip of
   what to do next, a dense skill table whose rows open their reason, and the AI comment beside the basis.
   Every figure comes from /career-process/exam/review and /career-process/insights; nothing is scored here. --- */
const percentOf = (part, whole) => Math.max(0, Math.min(100, Math.round((100 * Number(part)) / (Number(whole) || 1))));

function taskList(data) {
    const rows = data.questions.map((question, index) => {
        const state = question.blank ? "is-blank" : question.correct ? "is-right" : Number(question.points_awarded) > 0 ? "is-partial" : "is-wrong";
        return `<li><a class="rs-task ${state}" href="#/plan/da/review?q=${index}" title="${esc(question.topic)}">
            <span class="rs-task-name"><strong>${esc(question.label)}</strong><span>${esc(skillName(question.skill_code))} · ${esc(question.tier_label)}</span></span>
            <span class="rs-task-bar"><b style="width:${percentOf(question.points_awarded, question.max_points)}%"></b></span>
            <span class="rs-task-pts">${question.blank ? '<span class="rs-task-tag">Trống</span>' : ""}<strong>${question.points_awarded}</strong>/${question.max_points}</span></a></li>`;
    }).join("");
    return `<div class="rs-tasks"><span class="rs-tasks-title">Điểm từng bài</span><ol>${rows}</ol></div>`;
}

function scoreCard(data) {
    const gap = round1(Number(data.score) - Number(data.pass_threshold));
    const pasted = data.integrity?.large_inserts || 0;
    const flags = [
        data.auto_submitted ? ["clock", "Tự động nộp"] : null,
        data.violations ? ["alert", `Rời màn hình ${data.violations} lần`] : null,
        pasted ? ["file", `Dán nhiều chữ ${pasted} lần`, "Máy chủ tự ghi nhận, chỉ để tham khảo, không ảnh hưởng điểm."] : null,
    ].filter(Boolean);
    const mood = expressionForScore(data);
    return `<section class="card rs-score ${data.passed ? "is-pass" : "is-fail"}">
        <div class="rs-score-main">${scoreRing(data)}
            <div class="rs-verdict"><div class="rs-verdict-top"><span class="badge ${data.passed ? "badge-good" : "badge-bad"} verdict-badge">${icon(data.passed ? "check" : "alert")}<span>${data.passed ? "Đạt" : "Chưa đạt"}</span></span><span class="rs-bot" aria-hidden="true">${expressiveHead(mood, "rs-face")}</span></div>
                <strong class="rs-gap">${data.passed ? `Cao hơn ngưỡng ${gap} điểm` : `Còn thiếu ${Math.abs(gap)} điểm`}</strong>
                <span class="rs-meta"><span>Ngưỡng ${data.pass_threshold}/${data.max_score}</span><span>${fmtDateTime(data.submitted_at)}</span></span>
                ${flags.length ? `<div class="rs-flags">${flags.map(([name, label, hint]) => `<span class="rs-flag"${hint ? ` title="${esc(hint)}"` : ""}>${icon(name)}<span>${esc(label)}</span></span>`).join("")}</div>` : ""}
                <a class="btn btn-primary btn-glow rs-review" href="#/plan/da/review"><span>Xem lại bài làm</span>${icon("arrow")}</a></div></div>
        ${taskList(data)}
        ${data.critical_violations.length ? `<p class="rs-critical">${icon("alert")}<span><strong>Lỗi trọng yếu:</strong> ${esc(data.critical_violations.join("; "))}</span></p>` : ""}</section>`;
}

function nextStrip(data, insights) {
    const skills = data.conclusion.skills;
    const unmet = skills.filter(item => item.verified_level < item.target_level);
    // Same rule as the server summary: the unmet skill furthest below its JD level.
    const weakest = unmet.length ? unmet.reduce((low, item) => (item.verified_level - item.target_level < low.verified_level - low.target_level ? item : low)) : null;
    const ranking = insights.ranking;
    const overall = levelOf(insights.levels, data.conclusion.overall_level);
    const fact = (name, label, value, sub, tone = "") => `<div class="rs-fact ${tone}">${tile(name, "brand", "tile-sm")}<div><span>${label}</span><strong>${value}</strong>${sub ? `<small>${sub}</small>` : ""}</div></div>`;
    return `<section class="card rs-strip">
        ${fact("shield", "Trình độ", esc(data.conclusion.overall_label), `Mức ${data.conclusion.overall_level}/3 · ${esc(overall.stage)}`)}
        ${fact("trophy", "Cạnh tranh", ranking.me ? esc(standing(ranking)) : "Chưa xếp hạng", ranking.me && ranking.top_percent ? `Hạng ${ranking.me.rank}/${ranking.total}` : "")}
        ${weakest ? fact("route", "Ưu tiên học", esc(skillName(weakest.skill_code)), `Mức ${weakest.verified_level} → ${weakest.target_level}`, "is-focus") : fact("check", "Ưu tiên học", "Đã đạt mọi kỹ năng JD", "", "is-focus")}
        <a class="btn btn-secondary rs-roadmap" href="#/plan/da/roadmap"><span>Mở lộ trình</span>${icon("arrow")}</a></section>`;
}

function resultTable(data, insights) {
    const byskill = new Map(data.questions.map(question => [question.skill_code, question]));
    const rows = data.conclusion.skills.map(item => {
        const gap = item.target_level - item.verified_level;
        const level = levelOf(insights.levels, item.verified_level);
        const question = byskill.get(item.skill_code);
        const points = question ? `<span class="rs-points" title="Điểm bài ${esc(question.label)}"><span class="rs-mini"><b style="width:${percentOf(question.points_awarded, question.max_points)}%"></b></span><span><strong>${question.points_awarded}</strong>/${question.max_points}</span></span>` : '<span class="rs-points is-none">—</span>';
        return `<li><details class="rs-row"><summary class="rs-row-main">${skillTile(item.skill_code, "tile-sm")}
                <span class="rs-name"><strong>${esc(skillName(item.skill_code))}</strong><span>${esc(item.topic)} · ${esc(item.tier_label)}</span></span>
                ${points}<span title="${esc(level.name)}">${meter(item.verified_level, "verified")}</span>${meter(item.target_level, "jd")}
                <span class="badge ${gap <= 0 ? "badge-good" : "badge-warn"} rs-badge">${gap <= 0 ? "Đạt" : `Thiếu ${gap}`}</span><span class="rs-chev" aria-hidden="true">${icon("arrow")}</span></summary>
            <p class="rs-why"><strong>Vì sao:</strong> ${esc(item.reason)} ${esc(item.compare)}</p></details></li>`;
    }).join("");
    return `<section class="card rs-skills"><div class="rs-head"><h2>Kỹ năng</h2><span class="ov-col is-points">Điểm bài</span><span class="ov-col is-verified">Đã xác thực</span><span class="ov-col is-jd">JD cần</span>
            <button class="btn btn-ghost btn-sm rs-guide" type="button" data-act="guide" title="Cách phân bậc">${icon("info")}<span>Cách phân bậc</span></button></div>
        <ul class="rs-rows">${rows}</ul>
        ${data.conclusion.scope_note ? `<p class="ov-foot-note">${icon("info")}<span>${esc(data.conclusion.scope_note)}</span></p>` : ""}</section>`;
}

function aiCard(data) {
    if (!data.ai.overall) return "";
    return `<section class="card rs-ai-card"><div class="rs-ai-head">${aiAvatar("sm")}<h2>Nhận xét của AI</h2><span class="badge badge-muted">Không đổi điểm</span></div>
        <div class="rs-ai-text" id="rs-ai-text">${formatText(data.ai.overall)}</div>
        <button class="btn btn-ghost btn-sm rs-ai-more" type="button" data-act="ai-more" aria-expanded="false" aria-controls="rs-ai-text">Xem thêm</button></section>`;
}

function examHero(data) {
    const skills = data.conclusion.skills;
    const met = skills.filter(item => item.verified_level >= item.target_level).length;
    return pageHero({
        tone: "violet", icon: "check", kicker: "Kết quả bài làm", title: `${data.passed ? "Đạt" : "Chưa đạt"} · ${data.score}/${data.max_score} điểm`,
        stats: [["shield", "Ngưỡng đạt", data.pass_threshold, "muted"], ["target", "Kỹ năng đạt JD", `${met}/${skills.length}`, met === skills.length ? "good" : "warn"], ["file", "Bài đã chấm", data.questions.length]],
    });
}

async function examResult() {
    const [data, insights] = await Promise.all([api("/career-process/exam/review"), api("/career-process/insights")]);
    const ai = aiCard(data);
    setView(`<div class="stack">${examHero(data)}${scoreCard(data)}${nextStrip(data, insights)}${resultTable(data, insights)}
        <div class="rs-bottom ${ai ? "" : "is-single"}">${ai}${basisCard(insights.basis)}</div></div>`);
    register({
        actions: {
            guide: () => openLevelGuide(insights.levels),
            "ai-more": element => {
                const open = element.getAttribute("aria-expanded") !== "true";
                document.getElementById("rs-ai-text")?.classList.toggle("is-open", open);
                element.setAttribute("aria-expanded", String(open));
                element.textContent = open ? "Thu gọn" : "Xem thêm";
            },
        },
    });
    // "Xem thêm" only when the comment is longer than its preview.
    const text = document.getElementById("rs-ai-text");
    if (text && text.scrollHeight <= text.clientHeight + 2) document.querySelector('[data-act="ai-more"]')?.setAttribute("hidden", "");
}

function simulated(title) {
    subnav(title === "Backend Developer" ? "backend" : "qa");
    const parts = [["Kỹ năng tự khai và JD", "file"], ["Kết quả bài làm", "check"], ["Khoảng cách kỹ năng", "pulse"], ["Lộ trình theo tuần", "route"], ["Nhắc nhở", "bell"]];
    setView(`<div class="stack">${alertBox("warn", `<strong>Giao diện mô phỏng.</strong> ${esc(title)} chưa có dữ liệu và bài kiểm tra nên không có kết quả thật. Khi nghề này được mở, trang sẽ gồm các phần dưới đây.`)}
        <div class="grid grid-2">${parts.map(([part, name]) => `<section class="card sim-card card-title">${tile(name, "brand", "tile-sm")}<div><h2>${esc(part)}</h2><p class="sub small">Chưa có dữ liệu.</p></div></section>`).join("")}</div></div>`);
}

export async function renderPlan(career, section, rest = "") {
    if (career === "backend") return simulated("Backend Developer");
    if (career === "qa") return simulated("QA Tester");
    const state = await api("/career-process/state");
    const run = state.run;
    if (!run || run.status !== "COMPLETED") {
        subnav("da");
        setView(`<div class="card">${run
            ? emptyView("Quy trình chưa hoàn tất", "Kết quả và lộ trình chỉ hiện khi bạn hoàn thành Quy trình Career Adapt.", '<a class="btn btn-primary" href="#/flow">Tiếp tục quy trình</a>')
            : emptyView("Bạn chưa thực hiện quy trình", "Hãy thực hiện Quy trình Career Adapt để xem kết quả và lộ trình cải thiện.", '<a class="btn btn-primary" href="#/process">Đi đến Quy trình Career Adapt</a>')}</div>`);
        return undefined;
    }
    if (section === "review") {
        subnav("da", "exam");
        const start = new URLSearchParams(window.location.hash.split("?")[1] || "").get("q");
        renderReview(await api("/career-process/exam/review"), { backHref: "#/plan/da/exam", backLabel: "Quay lại kết quả", start });
        return undefined;
    }
    subnav("da", section);
    const key = SECTIONS.some(([id]) => id === section) ? section : "overview";
    if (key === "exam") await examResult();
    else if (key === "gap") await renderGap();
    else if (key === "rank") await renderRank();
    else if (key === "roadmap") await renderRoadmap(rest);
    else if (key === "progress") await renderProgress();
    else await overview(run);
    // 5.44: a section's main page shows its hero and a row of buttons; each button opens one part.
    if (!(key === "roadmap" && rest)) keepDisclosed(key);
    return undefined;
}

/* --- Key information first, details on request (5.44 → 5.45). Each section shows its main block directly (no group
   below claims it); only the supporting blocks go behind the "Xem thêm" buttons. Matching is by each block's own class
   or action, not by its text, so it holds in English too. Unclaimed blocks (the main block, alerts, a running study
   session) stay visible above the buttons in their original order.
     overview: everything shown (5.49): skill table, JD card, reset
     exam:     everything shown (5.50): score card, next card, skill table, basis (closed)
     gap:      gap chart shown · detail, priority, other JDs behind buttons
     roadmap:  progress, next lesson and the weekly breakdown shown · final, older lessons behind buttons
     rank:     everything shown (5.51): hero, board with filters, comparison, salary
     progress: due tasks shown · log behind a button --- */
const has = selector => element => Boolean(element.querySelector(selector));
const PANELS = {
    // 5.49: the whole section fits on one screen, so nothing hides behind a button.
    overview: [],
    // 5.50: score, next step and the skill table are the section; the basis is already a closed <details>.
    exam: [],
    gap: [
        { id: "detail", title: "Chi tiết và bằng chứng", hint: "Bảng mức, trọng số và bằng chứng từng kỹ năng", icon: "file", match: el => el.matches(".gap-card") && !el.matches(".gap-main") },
        { id: "priority", title: "Kỹ năng ưu tiên", hint: "Nên học gì trước và mức đáp ứng mục tiêu", icon: "target", match: el => el.matches(".gap-split") },
        { id: "trust", title: "Độ tin cậy đánh giá", hint: "Mức của bạn dựa trên bao nhiêu bài làm, loại kiểm tra nào", icon: "shield", match: el => el.id === "assessment-trust" },
        { id: "match", title: "So khớp với JD khác", hint: "Mức phù hợp của bạn với các JD đã duyệt", icon: "chart", match: el => el.id === "jd-matches" || el.matches("p.sub.small") },
    ],
    roadmap: [
        { id: "final", title: "Bài đánh giá tổng hợp", hint: "Bài đánh giá cuối lộ trình", icon: "trophy", match: el => el.matches(".jr-final") },
        { id: "other", title: "Bài chưa xếp và bài cũ", hint: "Hoạt động chưa xếp lịch, bài từ phiên bản trước", icon: "file", match: el => el.matches(".jr-unscheduled") },
    ],
    // 5.51: ranking, comparison and salary are all in view; the level guide is a button in the hero.
    rank: [],
    progress: [
        { id: "log", title: "Nhật ký và thay đổi kỹ năng", hint: "Hoạt động đã làm và các lần đổi mức", icon: "clock", match: el => el.matches(".rm-more, .rm-records") },
    ],
};
function keepDisclosed(key) {
    const apply = () => {
        const root = document.querySelector("#view > .stack");
        mountPlanAdvisor(root, key); // 5.47: the AI advisor strip stays in view, under the hero
        disclose(root, key, PANELS[key]);
    };
    apply();
    // A section that redraws itself (after an update) gets its buttons back; the watcher stops when the page changes.
    const view = document.getElementById("view");
    const here = window.location.hash.split("?")[0];
    const watcher = new MutationObserver(() => {
        if (window.location.hash.split("?")[0] !== here) { watcher.disconnect(); return; }
        const root = document.querySelector("#view > .stack");
        if (root && !root.dataset.disclosed && root.querySelector(":scope > .page-hero")) apply();
    });
    watcher.observe(view, { childList: true });
}
