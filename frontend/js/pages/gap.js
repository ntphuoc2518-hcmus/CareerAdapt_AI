/** Khoảng cách kỹ năng: every figure comes from /me/gap. This page only arranges it; it computes no level, gap or score. */
import { api, esc, fmtDate, openModal, REQUIREMENT_TYPES, register, setView, skillName, SOURCE_TYPES } from "../core.js";
import { icon, tile } from "../icons.js";
import { gapChart } from "../charts.js";
import { pageHero } from "../hero.js";
import { revealPanelOf } from "../disclose.js";

const EVIDENCE_SOURCES = { ASSESSMENT: "Bài kiểm tra Quy trình Career Adapt", MINI_TEST: "Mini-test hoặc bài kiểm tra học phần" };
const has = value => value !== null && value !== undefined;
const pill = (level, kind) => (has(level) ? `<span class="level-pill level-${kind}">${level}</span>` : '<span class="sub">—</span>');

/** Counts over the server's statuses, shown above the chart so the answer to "how far am I" comes first. */
function gapCounts(gap) {
    const assessed = gap.skill_evaluations.filter(item => item.status === "ASSESSED");
    const met = assessed.filter(item => item.gap === 0).length;
    const chips = [["is-met", "check", "Đạt mục tiêu", met], ["is-todo", "target", "Còn thiếu", assessed.length - met], ["is-none", "clock", "Chưa đánh giá", gap.skill_evaluations.length - assessed.length]];
    return `<div class="gap-counts">${chips.map(([tone, name, label, value]) => `<span class="gap-count ${tone}">${icon(name)}<span>${label}</span><b>${value}</b></span>`).join("")}</div>`;
}

/** Coverage, readiness and the target in one card; the lock reasons and unmeasured JD items sit under the figures they explain. */
function readinessCard(gap) {
    const coverage = Math.round(gap.coverage * 100);
    const target = gap.target;
    const readiness = gap.readiness;
    const extra = target.additional_requirements || [];
    const row = (label, value, percent, note = "") => `<li class="progress-row"><div class="row-between"><span>${label}</span><strong>${value}</strong></div>${percent === null ? "" : `<div class="meter"><span style="width:${percent}%"></span></div>`}${note}</li>`;
    return `<section class="card gap-side">${sectionHeadSmall("chart", "Mức đáp ứng mục tiêu")}
        <ul class="progress-list">
            ${row("Độ phủ bằng chứng", `${gap.skills_measured}/${gap.skills_total} kỹ năng · ${coverage}%`, coverage)}
            ${row("Mức đáp ứng", readiness === null ? "Chưa mở" : `${readiness}%`, readiness === null ? null : Math.min(100, readiness),
                gap.is_readiness_locked && gap.lock_reasons.length ? `<ul class="text-list small">${gap.lock_reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>` : "")}
        </ul>
        <div class="gap-goal-info"><span class="sub small">Mục tiêu</span><strong>${esc(target.name || "")}</strong>
            <span class="sub small">${esc(SOURCE_TYPES[target.source_type] || "")}${target.jd_version ? ` · phiên bản ${esc(target.jd_version)}` : ""}</span>
            ${extra.length ? `<span class="sub small">Yêu cầu chưa có bài đo: ${esc(extra.join(", "))}</span>` : ""}
            <a class="small" href="#/plan/da/overview">Xem JD</a></div>
        <div class="gap-report"><div><strong>Báo cáo năng lực</strong><span class="sub small">Kết quả, khoảng cách và lộ trình trên một trang để in hoặc lưu PDF.</span></div><a class="btn btn-secondary btn-sm" href="#/report">${icon("file")}<span>Mở báo cáo</span></a></div></section>`;
}

const sectionHeadSmall = (name, title) => `<div class="card-title gap-card-title">${tile(name, "brand", "tile-sm")}<h2>${title}</h2></div>`;

function jdPending() {
    return `<section class="card gap-note">${tile("info")}<div><h3>Yêu cầu từ JD chưa được phân tích</h3><p class="sub small">Mục tiêu hiện tại chưa có kỹ năng nào để đo. Hãy chọn hoặc phân tích JD để hệ thống xác định các kỹ năng cần có.</p></div>
        <div class="row"><a class="btn btn-secondary btn-sm" href="#/process">Đi đến quy trình</a><a class="btn btn-primary btn-sm" href="#/plan/da/overview"><span>Phân tích JD</span>${icon("arrow")}</a></div></section>`;
}

function detailTable(gap) {
    const TONE = item => (!has(item.gap) || item.status !== "ASSESSED" ? "badge-muted" : item.gap === 0 ? "badge-good" : "badge-warn");
    const rows = gap.skill_evaluations.map(item => {
        const assessed = item.status === "ASSESSED";
        const missing = assessed ? (item.gap === 0 ? "Đạt mục tiêu" : `${item.gap} mức`) : "Chưa kết luận";
        return `<tr id="gap-row-${esc(item.skill_code)}"><td><span class="gap-skill"><strong>${esc(skillName(item.skill_code))}</strong>${item.is_core ? '<span class="badge">Cốt lõi</span>' : ""}</span>${REQUIREMENT_TYPES[item.requirement_type] ? `<span class="sub small">${esc(REQUIREMENT_TYPES[item.requirement_type])}</span>` : ""}</td>
            <td class="center">${has(item.self_reported_level) ? `<span class="level-pill level-self">${item.self_reported_level}</span>` : '<span class="sub">—</span>'}</td>
            <td class="center">${assessed ? pill(item.current_level, "current") : '<span class="badge badge-muted">Chưa đánh giá</span>'}</td>
            <td class="center">${pill(item.target_level, "target")}</td>
            <td class="center"><span class="badge ${TONE(item)}">${missing}</span></td>
            <td class="center">${Math.round(item.weight * 100)}%</td>
            <td class="gap-reason">${esc(item.explanation)}${item.evidence ? `<span class="sub small">Bằng chứng: ${item.evidence.source_type === "MINI_TEST" ? "mini-test" : "bài kiểm tra"} · ${fmtDate(item.evidence.assessed_at)}</span>` : ""}</td>
            <td>${item.evidence ? `<button class="btn btn-ghost btn-sm gap-evidence-btn" type="button" data-act="evidence" data-skill="${esc(item.skill_code)}"><span>Xem bằng chứng</span>${icon("arrow")}</button>` : '<span class="sub small">Chưa có</span>'}</td></tr>`;
    }).join("");
    return `<section class="card gap-card">${sectionHeadSmall("file", "Chi tiết và bằng chứng")}
        <div class="table-wrap gap-table"><table><thead><tr><th>Kỹ năng</th><th class="center">Tự khai</th><th class="center">Hiện tại</th><th class="center">Mục tiêu</th><th class="center">Còn thiếu</th><th class="center">Trọng số</th><th>Lý do và bằng chứng</th><th>Thao tác</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="sub small">Mức tự khai chỉ để tham khảo, không được tính là bằng chứng.</p></section>`;
}

/** Uses the server's order (priority score, then core, then weight); nothing is re-ranked here. */
function priorityCard(gap) {
    const gaps = gap.skill_evaluations.filter(item => item.status === "ASSESSED" && item.gap > 0).slice(0, 2);
    const unassessed = gap.skill_evaluations.filter(item => item.status !== "ASSESSED");
    const reasons = item => [item.is_core ? "Cốt lõi" : "", `Thiếu ${item.gap} mức`, `Trọng số ${Math.round(item.weight * 100)}%`].filter(Boolean).map(text => `<span class="badge badge-muted">${text}</span>`).join("");
    const list = gaps.map(item => `<li>${icon("target")}<div><strong>${esc(skillName(item.skill_code))}</strong><span class="row gap-reasons">${reasons(item)}</span></div></li>`).join("");
    const pending = unassessed.length ? `<p class="sub small">Chưa có bằng chứng: ${esc(unassessed.map(item => skillName(item.skill_code)).join(", "))}.</p>${gap.recommended_assessment ? `<p class="sub small">Bài nên làm: ${esc(gap.recommended_assessment.title)}.</p>` : ""}` : "";
    const lead = gaps.length ? "Bắt đầu từ những kỹ năng có khoảng cách lớn và quan trọng nhất với mục tiêu." : "Bạn đã đạt mục tiêu ở mọi kỹ năng đã đo.";
    return `<section class="card gap-side">${sectionHeadSmall("sparkles", "Kỹ năng cần ưu tiên")}<p class="sub small">${lead}</p>${list ? `<ul class="gap-priority-list">${list}</ul>` : ""}${pending}
        <div class="gap-priority-actions"><a class="btn btn-primary" href="#/plan/da/roadmap">${icon("route")}<span>Xem lộ trình học tập</span></a><a class="btn btn-secondary" href="#/tests">${icon("quiz")}<span>Kiểm tra kiến thức</span></a></div></section>`;
}

function evidenceDrawer(item) {
    const evidence = item.evidence;
    const link = evidence.source_type === "MINI_TEST" ? ["#/plan/da/roadmap", "Mở lộ trình học tập"] : ["#/plan/da/exam", "Xem kết quả bài làm"];
    const facts = [
        ["Mức được đánh giá", `Mức ${item.current_level} / mục tiêu ${item.target_level}`],
        ["Trạng thái", "Đã xác thực bằng bài đánh giá hợp lệ"],
        ["Nguồn bằng chứng", EVIDENCE_SOURCES[evidence.source_type] || evidence.source_type],
        has(evidence.score) ? ["Kết quả", `${Math.round(Number(evidence.score) * 100)}/100`] : null,
        evidence.assessed_at ? ["Ngày đánh giá", fmtDate(evidence.assessed_at)] : null,
    ].filter(Boolean);
    openModal(`<div class="drawer-head"><div class="card-title">${tile("shield")}<div><h2>${esc(skillName(item.skill_code))}</h2><p class="sub small">Bằng chứng đánh giá</p></div></div><button class="icon-btn" type="button" data-close-modal aria-label="Đóng"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>
        <dl class="drawer-facts">${facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>
        <section><h3>Lý do hệ thống xác định mức</h3><p class="prose">${esc(item.explanation)}</p></section>
        ${evidence.scope_note ? `<p class="sub small">${esc(evidence.scope_note)}</p>` : ""}
        <div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Đóng</button><a class="btn btn-primary" href="${link[0]}" data-close-modal><span>${link[1]}</span>${icon("arrow")}</a></div>`, { drawer: true });
}

function focusRow(code) {
    const row = document.getElementById(`gap-row-${code}`);
    if (!row) return;
    revealPanelOf(row); // 5.44: the table sits in its own panel; open it before scrolling to the row
    row.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    row.classList.remove("is-flash");
    void row.offsetWidth;
    row.classList.add("is-flash");
}

/** Every approved library JD scored with the same engine as this page (GET /me/jd-matches). Nothing is computed here. */
function matchesCard(data) {
    if (!data?.has_evidence || !data.items.length) return "";
    const row = item => {
        const ready = item.locked ? `<span class="badge badge-muted">Chưa đủ bằng chứng</span>` : `<span class="match-score"><strong>${Math.round(item.readiness)}%</strong><span class="meter"><span style="width:${Math.round(item.readiness)}%"></span></span></span>`;
        const gaps = item.top_gaps.length ? item.top_gaps.map(gap => `<span>${esc(skillName(gap.skill_code))} <span class="sub">${gap.current_level}→${gap.target_level}</span></span>`).join("") : '<span class="sub">Không thiếu kỹ năng đã đo</span>';
        const unmeasured = item.unmeasured.length ? `<span class="sub small">Chưa đo: ${item.unmeasured.map(code => esc(skillName(code))).join(", ")}</span>` : "";
        return `<tr class="${item.is_current ? "is-current" : ""}"><td><strong>${esc(item.name)}</strong>${item.is_current ? ' <span class="badge">Mục tiêu hiện tại</span>' : ""}${item.role_level ? `<span class="sub small"> · ${esc(item.role_level)}</span>` : ""}</td>
            <td>${ready}</td><td class="nowrap">${item.skills_met}/${item.skills_total}</td><td><span class="match-gaps">${gaps}</span>${unmeasured}</td></tr>`;
    };
    return `<section class="card">${sectionHeadSmall("target", "So khớp với các JD khác")}
        <p class="sub small">Năng lực đã xác thực của bạn so với từng JD đã duyệt trong thư viện, cùng cách tính với trang này. Muốn chuyển sang JD phù hợp hơn, dùng Đổi JD mục tiêu ở mục Quy trình Career Adapt; mức đã xác thực được giữ.</p>
        <div class="table-wrap"><table class="match-table"><thead><tr><th>JD</th><th>Mức đáp ứng</th><th>Kỹ năng đạt</th><th>Còn thiếu nhiều nhất</th></tr></thead><tbody>${data.items.map(row).join("")}</tbody></table></div>
        <p class="sub small">${esc(data.scope_note)}</p></section>`;
}

const TRUST_TONES = { HIGH: "badge-good", MEDIUM: "", LOW: "badge-warn", NONE: "badge-muted" };

/** How far each verified level can be trusted (GET /me/assessment-reliability). The server rates; this only draws. */
function trustCard(data, policy) {
    if (!data?.skills?.length) return "";
    const number = value => (value > 0 && value < 1 ? `${Math.round(value * 100)}%` : String(value));
    const rules = policy?.rules?.length
        ? `<details class="trust-policy"><summary>Ngưỡng đánh giá máy chủ đang áp dụng</summary><ul class="sub small">${policy.rules.map(rule => `<li><strong>${esc(number(rule.value))}</strong> · ${esc(rule.label)}</li>`).join("")}</ul></details>`
        : "";
    const sources = item => item.sources.length
        ? `<ul class="trust-sources">${item.sources.map(source => `<li><span>${esc(source.source_label)}</span> <span class="sub small">${esc(source.kind_label)} · mức ${source.level}${source.score !== null ? ` · ${source.score}/100` : ""} · ${esc(fmtDate(source.created_at))}</span></li>`).join("")}</ul>`
        : '<span class="sub small">Chưa có bài làm được chấm.</span>';
    const row = item => `<tr><td><strong>${esc(skillName(item.skill_code))}</strong><span class="sub small"> · mức ${item.current_level ?? "—"}/${item.target_level}</span></td>
        <td><span class="badge ${TRUST_TONES[item.rating] || ""}">${esc(item.rating_label)}</span></td><td>${sources(item)}</td>
        <td><ul class="trust-reasons">${item.reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul><span class="sub small">${esc(item.next_step)}</span></td></tr>`;
    return `<section class="card trust-card">${sectionHeadSmall("shield", "Độ tin cậy đánh giá")}
        <p class="sub small">${esc(data.note)}</p>
        <div class="table-wrap"><table class="trust-table"><thead><tr><th>Kỹ năng</th><th>Độ tin cậy</th><th>Bài làm đứng sau mức này</th><th>Lý do</th></tr></thead><tbody>${data.skills.map(row).join("")}</tbody></table></div>
        <ul class="trust-rules sub small">${data.rules.map(rule => `<li>${esc(rule)}</li>`).join("")}</ul>${rules}</section>`;
}

function gapHero(gap) {
    const assessed = gap.skill_evaluations.filter(item => item.status === "ASSESSED");
    const met = assessed.filter(item => item.gap === 0).length;
    const unmet = assessed.length - met;
    const unassessed = gap.skill_evaluations.length - assessed.length;
    const title = unmet ? `Còn ${unmet} kỹ năng chưa đạt mức JD yêu cầu.` : unassessed ? `Còn ${unassessed} kỹ năng chưa có bằng chứng.` : "Bạn đã đáp ứng mọi kỹ năng JD yêu cầu.";
    const readiness = gap.readiness === null ? "Chưa mở" : `${gap.readiness}%`;
    return pageHero({
        tone: "teal", icon: "pulse", kicker: "Khoảng cách kỹ năng", title, text: `Mục tiêu: ${esc(gap.target?.name || "")}. So sánh mức đã xác thực với mức JD yêu cầu.`,
        stats: [["check", "Đạt mục tiêu", met, "good"], ["target", "Còn thiếu", unmet, unmet ? "warn" : "muted"],
            ["chart", "Độ phủ bằng chứng", `${Math.round(gap.coverage * 100)}%`], ["pulse", "Mức đáp ứng", readiness, gap.readiness === null ? "muted" : "brand"]],
    });
}

export async function renderGap() {
    setView(`<div class="stack"><div class="card skeleton skeleton-tall"></div><div class="gap-split">${'<div class="card skeleton"></div>'.repeat(2)}</div></div>`);
    const gap = await api("/me/gap");
    if (!gap.skill_evaluations.length) {
        setView(`<div class="stack">${jdPending()}</div>`);
        return;
    }
    // Order: the gaps as a chart, the evidence behind each row, then what to do next beside how ready you are.
    setView(`<div class="stack">${gapHero(gap)}
        <section class="card gap-card gap-main"><div class="gap-main-head">${sectionHeadSmall("pulse", "Khoảng cách theo từng kỹ năng")}${gapCounts(gap)}</div>
            <p class="sub small">Rê chuột để xem chi tiết; bấm vào một kỹ năng để tới dòng của nó trong bảng bên dưới.</p><div id="gap-chart"></div></section>
        ${detailTable(gap)}
        <div class="gap-split">${priorityCard(gap)}${readinessCard(gap)}</div>
        <div id="assessment-trust"></div>
        <div id="jd-matches"></div>
        <p class="sub small">${esc(gap.scope_notice)}</p></div>`);
    Promise.all([api("/me/assessment-reliability"), api("/me/assessment-policy").catch(() => null)])
        .then(([data, policy]) => { const slot = document.getElementById("assessment-trust"); if (slot) slot.innerHTML = trustCard(data, policy); }).catch(() => {});
    api("/me/jd-matches").then(data => { const slot = document.getElementById("jd-matches"); if (slot) slot.innerHTML = matchesCard(data); }).catch(() => {});
    gapChart(document.getElementById("gap-chart"), gap.skill_evaluations, { onSelect: focusRow });
    const byCode = Object.fromEntries(gap.skill_evaluations.map(item => [item.skill_code, item]));
    register({ actions: { evidence: element => { const item = byCode[element.dataset.skill]; if (item?.evidence) evidenceDrawer(item); } } });
}
