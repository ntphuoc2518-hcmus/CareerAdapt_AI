/** Báo cáo năng lực: one printable page built only from the learner's own records.
 * Nothing here is computed beyond counts; levels, gaps and readiness come from the server. */
import { api, app, emptyView, esc, fmtDate, fmtDateTime, formatText, register, setView, skillName, SOURCE_TYPES } from "../core.js";
import { icon } from "../icons.js";

const MASTERY = { VERIFIED: "Đã xác minh", NEEDS_IMPROVEMENT: "Cần cải thiện", IN_PROGRESS: "Đang đánh giá", NOT_ASSESSED: "Chưa đánh giá" };
const has = value => value !== null && value !== undefined;
const optional = promise => promise.catch(() => null);

function examSection(review) {
    if (!review) return `<section class="card report-section"><h2>Bài kiểm tra năng lực</h2><p class="sub">Chưa có bài kiểm tra đã chấm.</p></section>`;
    return `<section class="card report-section"><h2>Bài kiểm tra năng lực</h2>
        <dl class="report-facts"><div><dt>Điểm</dt><dd>${esc(String(review.score))}/${esc(String(review.max_score))}</dd></div><div><dt>Kết quả</dt><dd><span>${review.passed ? "Đạt" : "Chưa đạt"}</span> <span class="sub small">Ngưỡng đạt ${review.pass_threshold}/100</span></dd></div>
            <div><dt>Mức đã xác thực</dt><dd>${esc(review.conclusion.overall_label)} (mức ${review.conclusion.overall_level}/3)</dd></div><div><dt>Ngày nộp</dt><dd>${fmtDateTime(review.submitted_at)}</dd></div></dl>
        ${formatText(review.conclusion.summary)}</section>`;
}

function targetSection(gap) {
    const met = gap.skill_evaluations.filter(item => item.status === "ASSESSED" && item.gap === 0).length;
    return `<section class="card report-section"><h2>Mức đáp ứng mục tiêu</h2>
        <dl class="report-facts"><div><dt>Độ phủ bằng chứng</dt><dd>${Math.round(gap.coverage * 100)}% (${gap.skills_measured}/${gap.skills_total} kỹ năng đã đo)</dd></div>
            <div><dt>Mức đáp ứng</dt><dd>${gap.readiness === null ? "Chưa mở" : `${gap.readiness}%`}</dd></div><div><dt>Kỹ năng đạt mục tiêu</dt><dd>${met}/${gap.skills_total}</dd></div></dl>
        ${gap.is_readiness_locked && gap.lock_reasons.length ? `<ul class="report-notes">${gap.lock_reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>` : ""}</section>`;
}

function skillSection(gap, mastery) {
    const byCode = Object.fromEntries((mastery?.skills || []).map(item => [item.skill_code, item]));
    const rows = gap.skill_evaluations.map(item => {
        const check = byCode[item.skill_code];
        const evidence = item.evidence ? `${item.evidence.source_type === "MINI_TEST" ? "Mini-test" : "Bài kiểm tra"} ${fmtDate(item.evidence.assessed_at)}` : "Chưa có";
        return `<tr><td><strong>${esc(skillName(item.skill_code))}</strong>${item.is_core ? ' <span class="badge">Cốt lõi</span>' : ""}</td><td class="center">${item.self_reported_level ?? "—"}</td>
            <td class="center">${item.status === "ASSESSED" ? item.current_level : "Chưa đánh giá"}</td><td class="center">${item.target_level}</td><td class="center">${has(item.gap) ? (item.gap === 0 ? "Đạt" : item.gap) : "—"}</td>
            <td class="center">${Math.round(item.weight * 100)}%</td><td>${esc(evidence)}</td><td>${esc(MASTERY[check?.status] || "—")}</td></tr>`;
    }).join("");
    return `<section class="card report-section"><h2>Kỹ năng theo mục tiêu</h2>
        <div class="table-wrap plan-table"><table><thead><tr><th>Kỹ năng</th><th class="center">Tự khai</th><th class="center">Đã xác thực</th><th class="center">Mục tiêu</th><th class="center">Còn thiếu</th><th class="center">Trọng số</th><th>Bằng chứng</th><th>Thành thạo</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="sub small">Mức tự khai chỉ để tham khảo, không được tính là bằng chứng.</p></section>`;
}

function roadmapSection(plan, tasks) {
    if (!plan) return `<section class="card report-section"><h2>Lộ trình học tập</h2><p class="sub">Chưa có lộ trình.</p></section>`;
    const weeks = plan.schedule.scheduled_weeks;
    const state = Object.fromEntries((tasks?.tasks || []).map(item => [item.activity_id, item.state]));
    const next = weeks.flatMap(week => week.activities.filter(item => item.kind !== "ASSESSMENT" && state[item.activity_id] !== "VERIFIED").map(item => ({ ...item, week: week.week_number })));
    const seen = new Set();
    const upcoming = next.filter(item => !seen.has(item.activity_id) && seen.add(item.activity_id)).slice(0, 5);
    const end = weeks.length ? new Date(`${weeks[weeks.length - 1].start_date}T00:00:00`) : null;
    if (end) end.setDate(end.getDate() + 6);
    return `<section class="card report-section"><h2>Lộ trình học tập</h2>
        <dl class="report-facts"><div><dt>Tiến độ học tập</dt><dd>${plan.verified_progress_percent ?? 0}%</dd></div><div><dt>Bài học đã xác minh</dt><dd>${tasks?.counts?.VERIFIED || 0}/${tasks?.total ?? 0}</dd></div>
            <div><dt>Thời lượng</dt><dd>${weeks.length} tuần · ${plan.weekly_hours_budget} giờ/tuần</dd></div><div><dt>Dự kiến hoàn thành</dt><dd>${end ? fmtDate(end.toISOString().slice(0, 10)) : "—"}</dd></div></dl>
        ${upcoming.length ? `<h3>Việc tiếp theo</h3><ol class="report-list">${upcoming.map(item => `<li><strong>${esc(item.title)}</strong> <span class="sub small">Tuần ${item.week} · ${esc(skillName(item.target_skill))} mức ${item.target_level}</span></li>`).join("")}</ol>` : '<p class="sub">Mọi học phần trong lộ trình đã được xác minh.</p>'}</section>`;
}

export async function renderReport() {
    const gap = await api("/me/gap");
    if (!gap.skill_evaluations.length) {
        setView(`<div class="card">${emptyView("Chưa có dữ liệu để lập báo cáo", "Hãy hoàn thành Quy trình Career Adapt trước.", '<a class="btn btn-primary" href="#/process">Đi đến quy trình</a>')}</div>`);
        return;
    }
    // 5.57.2: the graded exam is asked for only once some skill has evidence; before that the server answers 409
    // and the browser logged it as an error, although the page showed its empty state correctly.
    const measured = gap.skill_evaluations.some(item => item.evidence);
    const [mastery, review, plan, tasks] = await Promise.all([optional(api("/me/skill-mastery")), measured ? optional(api("/career-process/exam/review")) : null, optional(api("/me/roadmap")), optional(api("/me/learning-tasks"))]);
    const target = gap.target;
    setView(`<div class="stack report">
        <div class="report-actions"><a class="btn btn-secondary" href="#/plan/da/gap">${icon("arrow")}<span>Về Khoảng cách kỹ năng</span></a><button class="btn btn-primary" type="button" data-act="print">${icon("file")}<span>In hoặc lưu PDF</span></button></div>
        <header class="card report-cover"><img class="report-logo logo-light" src="/img/logo-mark.png" alt="CareerAdapt AI"><img class="report-logo logo-dark" src="/img/logo-mark-white.png" alt="CareerAdapt AI"><div><span class="eyebrow-label">CareerAdapt AI · Báo cáo năng lực</span><h2 data-no-i18n>${esc(app.user.full_name)}</h2>
            <p class="sub small">${esc(target.name || "")}${SOURCE_TYPES[target.source_type] ? ` · ${esc(SOURCE_TYPES[target.source_type])}` : ""}${target.jd_version ? ` · phiên bản ${esc(target.jd_version)}` : ""}</p>
            <p class="sub small">Lập lúc ${fmtDateTime(new Date().toISOString())}</p></div></header>
        ${examSection(review)}${targetSection(gap)}${skillSection(gap, mastery)}${roadmapSection(plan, tasks)}
        <p class="sub small"><span>${esc(gap.scope_notice)}</span> <span>Báo cáo không phải chứng chỉ nghề.</span></p></div>`);
    register({ actions: { print: () => window.print() } });
}
