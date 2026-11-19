/** Read-only view of a past assessment. New assessments happen only inside the process. */
import { alertBox, api, esc, fmtDateTime, formatText, register, setView, skillName, statusBadge, toast, withBusy } from "../core.js";
import { criteriaBars } from "../charts.js";

const modeLabel = mode => (mode === "PRACTICE" ? "Luyện tập" : "Đánh giá");

const BANNERS = {
    INCOMPLETE: ["warn", "Bài chưa có câu trả lời nên chưa được chấm. Hồ sơ kỹ năng không thay đổi."],
    INVALID: ["bad", "Bài thiếu đầu ra bắt buộc hoặc không hợp lệ nên chưa được chấm. Hồ sơ kỹ năng không thay đổi."],
    PENDING_RETRY: ["warn", "Bài đã được lưu an toàn nhưng dịch vụ AI chưa hoàn tất. Hồ sơ kỹ năng chưa thay đổi; bạn có thể chấm lại."],
    NEEDS_REVIEW: ["warn", "Kết quả cần người duyệt kiểm tra. Hồ sơ kỹ năng chưa thay đổi cho đến khi có quyết định."],
};

function testCaseTable(scoring) {
    return `<div class="table-wrap"><table><thead><tr><th>Kiểm tra</th><th>Kỳ vọng</th><th>Thực tế</th><th class="num">Điểm</th><th></th></tr></thead><tbody>${scoring.test_case_results.map(item => `<tr><td>${esc(item.description)}</td><td class="small">${esc(item.expected_summary)}</td><td class="small">${esc(item.actual_summary)}</td><td class="num nowrap">${item.points_awarded}/${item.points_max}</td><td>${item.passed ? '<span class="badge badge-good">Đạt</span>' : `<span class="badge ${item.failure_code === "BLANK_ANSWER" ? "badge-muted" : "badge-bad"}">${item.failure_code === "BLANK_ANSWER" ? "Bỏ trống" : "Chưa đạt"}</span>`}</td></tr>`).join("")}</tbody></table></div>`;
}

function skillResults(record) {
    const results = Object.values(record.per_skill_results || {});
    if (!results.length) return "";
    const counted = record.status === "GRADED" || record.status === "REVIEWED_APPROVED";
    return `<section class="card"><h2>Mức kỹ năng quan sát được</h2><ul>${results.map(item => `<li class="list-item"><div><strong>${esc(skillName(item.skill_code))}</strong>${item.capped_by_critical_error ? ' <span class="badge badge-warn">Giới hạn do lỗi trọng yếu</span>' : ""}${item.feedback ? `<p class="small sub">${esc(item.feedback)}</p>` : ""}</div><span class="badge">Mức ${item.level}${counted ? "" : " (chưa ghi nhận)"}</span></li>`).join("")}</ul>${record.scope_note ? `<p class="sub small">${esc(record.scope_note)}</p>` : ""}</section>`;
}

function aiSection(record) {
    const ai = record.ai_result;
    if (!ai) return "";
    const criteria = Object.values(ai.criteria_feedback || {});
    const trace = (record.ai_traces || []).slice(-1)[0];
    return `<section class="card"><div class="card-head"><h2>Nhận xét</h2><span class="badge badge-muted">${ai.status === "DETERMINISTIC_ONLY" ? "Từ bộ kiểm tra, không có AI" : `AI: ${esc(ai.provider)}`}</span></div>
        ${ai.feedback ? formatText(ai.feedback) : ""}
        ${ai.strengths?.length ? `<h3 style="margin-top:10px">Điểm làm tốt</h3><ul class="small">${ai.strengths.map(text => `<li>${esc(text)}</li>`).join("")}</ul>` : ""}
        ${ai.areas_for_improvement?.length ? `<h3 style="margin-top:10px">Việc nên làm tiếp</h3><ul class="small stack-sm" style="gap:3px">${ai.areas_for_improvement.map(text => `<li>${esc(text)}</li>`).join("")}</ul>` : ""}
        ${criteria.map(item => `<div style="margin-top:10px"><strong class="small">${esc(item.criterion_id)}</strong> <span class="badge badge-muted">Đề xuất mức ${item.proposed_level}</span>${formatText(item.reason)}${item.evidence.map(reference => `<div class="source-quote small">${reference.verified ? '<span class="badge badge-good">Đã xác minh</span>' : '<span class="badge badge-bad">Không tìm thấy</span>'} ${esc(reference.value)}</div>`).join("")}</div>`).join("")}
        ${trace ? `<p class="sub small" style="margin-top:10px">Lần chấm ${trace.grade_attempt}: ${esc(trace.validation_result)}${trace.error ? ` (${esc(trace.error)})` : ""} · ${esc(trace.prompt_version)} · ${esc(trace.rubric_version)}</p>` : ""}</section>`;
}

export async function renderResult(id) {
    const record = await api(`/assessments/${id}`);
    const scoring = record.scoring;
    const banner = BANNERS[record.status];
    const score = record.final_score ?? record.provisional_score;
    const verdict = record.passed === true ? '<span class="badge badge-good">Đạt</span>' : record.passed === false ? '<span class="badge badge-bad">Không đạt</span>' : "";
    const answers = Object.entries(record.answers || {});
    setView(`<div class="stack"><div class="row-between"><a href="#/profile" class="small">← Về Hồ sơ</a></div>
        ${banner ? alertBox(banner[0], `<strong>${esc(banner[1])}</strong>${record.notes ? `<br>${esc(record.notes)}` : ""}${record.review_reason ? `<br>${esc(record.review_reason)}` : ""}`) : ""}
        ${record.mode === "PRACTICE" ? alertBox("info", "Bài luyện tập: kết quả chỉ lưu vào lịch sử, không thay thế bằng chứng đánh giá độc lập.") : ""}
        <section class="card"><div class="card-head"><div><h2>${esc(record.task_title || record.task_id)}</h2><p class="sub">${modeLabel(record.mode)} · ${fmtDateTime(record.created_at)}</p></div>${statusBadge(record.status)}</div>
            <div class="score-hero">${score === null || score === undefined ? '<div class="score-number">—</div>' : `<div class="score-number">${score}<small> / 100${record.final_score === null ? " (tạm tính)" : ""}</small></div>`}<div class="stack-sm" style="flex:1;min-width:220px">${verdict}${scoring ? `<div class="sub small">Ngưỡng đạt ${scoring.pass_threshold}/100.</div>` : ""}${scoring?.critical_violations?.length ? `<div class="small" style="color:var(--bad)"><strong>Lỗi trọng yếu:</strong> ${esc(scoring.critical_violations.map(item => item.label).join("; "))}</div>` : ""}${scoring?.blank_questions?.length ? `<div class="small">Câu bỏ trống tính 0 điểm: ${esc(scoring.blank_questions.join(", "))}</div>` : ""}</div>
            ${record.can_retry ? `<button class="btn btn-primary" data-act="retry">Chấm lại</button>` : ""}</div></section>
        ${scoring ? `<div class="grid grid-2"><section class="card stack-sm"><h2>Điểm theo tiêu chí</h2>${criteriaBars(scoring.criteria)}</section>${skillResults(record) || "<div></div>"}</div><section class="card"><h2>Kết quả test case</h2>${testCaseTable(scoring)}</section>` : ""}
        ${aiSection(record)}
        ${record.human_review ? `<section class="card"><h2>Quyết định của người duyệt</h2><p class="prose">${esc(record.human_review.notes)}</p><p class="sub small">${fmtDateTime(record.human_review.reviewed_at)}</p></section>` : ""}
        ${answers.length ? `<details class="card"><summary><strong>Bài làm đã nộp</strong></summary>${answers.map(([question, text]) => `<h3 style="margin-top:10px">${esc(question)}</h3>${text ? `<pre class="code">${esc(text)}</pre>` : '<p class="sub small">Bỏ trống hoặc đã hết thời hạn lưu.</p>'}`).join("")}</details>` : ""}
        <p class="sub small">Đề v${esc(record.task_version)} · ${esc(record.blueprint_version)} · ${esc(record.rubric_version)} · ${esc(record.rule_version)}${record.target_snapshot?.jd_id ? ` · Mục tiêu ${esc(record.target_snapshot.jd_id)}${record.target_snapshot.jd_version ? ` (v${esc(record.target_snapshot.jd_version)})` : ""}` : ""} · Mã bài ${esc(record.submission_id)}</p></div>`);
    register({
        actions: {
            retry: element => withBusy(element, async () => {
                const result = await api(`/submissions/${id}/grade`, { method: "POST" });
                toast(result.message);
                renderResult(id);
            }),
        },
    });
}
