/** How a contributed question and its automatic check read; shared by the contributor page and the review tab. */
import { esc, fmtDateTime, skillName } from "./core.js";
import { icon } from "./icons.js";

export const STATUS = {
    DRAFT: ["Bản nháp", "muted"], SUBMITTED: ["Chờ duyệt", "warn"], CHANGES_REQUESTED: ["Cần chỉnh sửa", "bad"],
    APPROVED: ["Đã xuất bản", "good"], REJECTED: ["Không được duyệt", "bad"], RETIRED: ["Ngừng dùng", "muted"],
};
export const BANK_NAMES = { EXAM: "Đề thi tự luận", TEST: "Trắc nghiệm" };
export const LEVEL_NAMES = { 1: "Cơ bản", 2: "Trung bình", 3: "Khó" };
const EVENTS = { CREATED: "Tạo bản nháp", SUBMITTED: "Gửi duyệt", WITHDRAWN: "Rút lại", CHANGES_REQUESTED: "Yêu cầu chỉnh sửa", REJECTED: "Không duyệt", APPROVED: "Duyệt và xuất bản", RETIRED: "Ngừng dùng" };

// Same rule as the server: a text with no accent mark and no d-bar needs no English.
const hasVietnamese = text => /[\u0300-\u036f\u0111\u0110]/.test(String(text).normalize("NFD"));

/** Every text a learner reads, with the key its English is stored under. Mirrors contributions.english_fields. */
export function englishFields(bank, payload) {
    const p = payload || {};
    const fields = [["topic", "Chủ đề", p.topic]];
    if (bank === "EXAM") {
        fields.push(["prompt", "Đề bài", p.prompt], ["placeholder", "Gợi ý trong ô trả lời", p.placeholder]);
        (Array.isArray(p.cases) ? p.cases : []).forEach(item => item && fields.push([`cases.${item.id}`, `Tiêu chí ${item.id}`, item.description]));
        (Array.isArray(p.gates) ? p.gates : []).forEach(item => item && fields.push([`gates.${item.gate_id}`, `Lỗi trọng yếu ${item.gate_id}`, item.label]));
        (Array.isArray(p.report_sections) ? p.report_sections : []).forEach((section, index) => fields.push([`report_sections.${index}`, `Mục báo cáo ${index + 1}`, section]));
    } else {
        fields.push(["stem", "Câu hỏi", p.stem]);
        (Array.isArray(p.options) ? p.options : []).forEach(item => item && fields.push([`options.${item.id}`, `Lựa chọn ${item.id}`, item.text]));
        fields.push(["unit", "Đơn vị", p.unit], ["explanation", "Giải thích", p.explanation]);
    }
    const english = p.en || {};
    return fields.filter(([, , text]) => typeof text === "string" && text.trim())
        .map(([key, label, text]) => ({ key, label, vi: text.trim(), en: String(english[key] || "").trim(), needed: hasVietnamese(text) }));
}

/** The English a reviewer reads next to the Vietnamese. */
export function englishView(item) {
    const fields = englishFields(item.bank, item.payload);
    const given = fields.filter(field => field.en);
    if (!given.length) return `<p class="sub small ct-en-none">${icon("info")}<span>Chưa có bản tiếng Anh: giao diện tiếng Anh sẽ hiện câu này bằng tiếng Việt.</span></p>`;
    return `<details class="ct-en-view"><summary class="small"><strong>Bản tiếng Anh</strong> · ${given.length}/${fields.length} mục</summary><dl>${fields.map(field => `<dt>${esc(field.label)}</dt><dd lang="en">${field.en ? esc(field.en) : `<span class="sub">giữ nguyên: ${esc(field.vi)}</span>`}</dd>`).join("")}</dl></details>`;
}

export function statusPill(status) {
    const [label, tone] = STATUS[status] || [status, "muted"];
    return `<span class="ct-pill is-${tone}">${label}</span>`;
}

export function questionText(item) {
    return item.bank === "EXAM" ? item.payload.prompt || "" : item.payload.stem || "";
}

/** The automatic check: errors first, then each dataset's run of the reference answer, wrong answers and look-alikes. */
export function validationView(report) {
    if (!report) return `<div class="ct-check is-none">${icon("info")}<span>Chưa kiểm tra. Bấm <strong>Kiểm tra</strong> trước khi gửi duyệt.</span></div>`;
    const head = report.ok
        ? `<div class="ct-check is-ok">${icon("check")}<span><strong>Qua kiểm tra tự động.</strong> Đáp án mẫu đạt trọn điểm, bài làm sai không qua được.</span></div>`
        : `<div class="ct-check is-bad">${icon("alert")}<div><strong>Chưa qua kiểm tra tự động</strong><ul>${report.errors.map(error => `<li>${esc(error)}</li>`).join("")}</ul></div></div>`;
    const warnings = report.warnings?.length ? `<ul class="ct-warn">${report.warnings.map(item => `<li>${icon("info")}<span>${esc(item)}</span></li>`).join("")}</ul>` : "";
    const datasets = Object.entries(report.datasets || {}).map(([variant, run]) => `<details class="ct-run"><summary><span>Bộ dữ liệu ${esc(variant)}</span><b class="${run.score === 100 ? "is-good" : "is-bad"}">${run.score}/100</b></summary>
        <ul>${run.cases.map(item => `<li class="${item.passed ? "is-good" : "is-bad"}">${icon(item.passed ? "check" : "alert")}<div><strong>${esc(item.description)}</strong>${item.passed ? "" : `<span class="sub small">Cần: ${esc(item.expected)} · Có: ${esc(item.actual)}</span>`}</div></li>`).join("")}</ul></details>`).join("");
    const weak = report.weak?.length ? `<div class="ct-weak"><strong class="small">Bài làm sai thử chấm</strong>${report.weak.map(item => `<span class="ct-weak-item ${item.score >= 40 ? "is-bad" : ""}">${esc(item.label)}: <b>${item.score}/100</b></span>`).join("")}</div>` : "";
    const similar = report.similar?.length ? `<div class="ct-similar"><strong class="small">Câu gần giống</strong><ul>${report.similar.map(item => `<li><span class="ct-pill is-muted">${Math.round(item.similarity * 100)}%</span><span class="sub small">${esc(item.source)} ${esc(item.ref)}: ${esc(item.excerpt)}</span></li>`).join("")}</ul></div>` : "";
    return `${head}${warnings}${datasets ? `<div class="ct-runs">${datasets}</div>` : ""}${weak}${similar}<p class="sub small">Kiểm tra lúc ${fmtDateTime(report.checked_at)}</p>`;
}

/** The question as a learner would read it, plus what only the reviewer and the author see. */
export function questionPreview(item) {
    const p = item.payload;
    const meta = `<div class="ct-meta"><span class="ct-pill is-brand">${BANK_NAMES[item.bank]}</span><span class="ct-pill is-muted">${esc(skillName(item.skill_code))}</span><span class="ct-pill is-muted">${LEVEL_NAMES[item.level] || item.level}</span>${statusPill(item.status)}</div>`;
    if (item.bank === "TEST") {
        const answers = Array.isArray(p.answer) ? p.answer : [p.answer];
        const options = (p.options || []).map(option => `<li class="${answers.includes(option.id) ? "is-key" : ""}"><b>${esc(option.id)}</b><span>${esc(option.text)}</span>${answers.includes(option.id) ? icon("check") : ""}</li>`).join("");
        return `${meta}<h3 class="ct-title">${esc(p.topic || "")}</h3><p class="ct-prompt">${esc(p.stem || "")}</p>${p.code ? `<pre class="code">${esc(p.code)}</pre>` : ""}
            ${options ? `<ol class="ct-options">${options}</ol>` : `<p><strong>Đáp án:</strong> ${esc(String(p.answer))}${p.unit ? ` ${esc(p.unit)}` : ""}</p>`}
            <p class="sub small"><strong>Giải thích:</strong> ${esc(p.explanation || "")}</p>${englishView(item)}`;
    }
    const cases = (p.cases || []).map(item => `<li><b>${item.points}đ</b><span>${esc(item.description || "")}</span><code>${esc(item.type || "")}</code></li>`).join("");
    const refs = Object.entries(p.reference_answers || {}).map(([key, value]) => `<details><summary class="small">Đáp án mẫu ${key === "*" ? "(cả bốn bộ dữ liệu)" : `bộ ${esc(key)}`}</summary><pre class="code">${esc(value)}</pre></details>`).join("");
    return `${meta}<h3 class="ct-title">${esc(p.topic || "")}</h3><p class="ct-prompt">${esc(p.prompt || "")}</p>
        <p class="sub small">${esc(p.answer_type || "")} · ${esc(p.workspace || "")} · ${p.minutes || "?"} phút</p><ul class="ct-cases">${cases}</ul>${refs}${englishView(item)}`;
}

export function eventsView(events) {
    if (!events?.length) return "";
    return `<ul class="ct-events">${events.map(event => `<li><span>${EVENTS[event.action] || esc(event.action)}</span>${event.note ? `<span class="sub small">${esc(event.note)}</span>` : ""}<time class="sub small">${fmtDateTime(event.created_at)}</time></li>`).join("")}</ul>`;
}
