/**
 * SVG charts drawn only from server data. Palette validated with the dataviz checks
 * (light surface): CVD ΔE ≥ 12.8, normal-vision ΔE ≥ 18, contrast ≥ 3:1.
 * Each chart has a legend and a table view, and tooltips work on hover and on keyboard focus.
 */
import { esc, fmtDate, skillName } from "./core.js";

const SERIES = { SQL: "#1F5FA8", DATA_QUALITY: "#C4610F", PYTHON: "#0E8F7E", DATA_VIZ: "#7C4DBD", WRITTEN_COMM: "#C2386E", STATISTICS: "#5E7B16" };
const INK = "var(--chart-ink)";
const SURFACE = "var(--surface)";
// Status colors only pass CVD with a second signal, so every row also states its progress in words.
const PROGRESS = {
    met: { color: "var(--progress-met)", label: "Đạt mục tiêu" },
    // Two states only: met, or still short of the target (by any number of levels).
    todo: { color: "var(--progress-near)", label: "Chưa đạt mục tiêu" },
};

function attachTips(root) {
    const tip = document.getElementById("chart-tip");
    const show = (target, x, y) => {
        tip.replaceChildren();
        const value = document.createElement("strong");
        value.textContent = target.dataset.value;
        // One line per span, so each line is a whole sentence for the translation layer.
        const lines = target.dataset.label.split("\n").map(text => {
            const line = document.createElement("span");
            line.textContent = text;
            return line;
        });
        tip.append(value, ...lines);
        tip.hidden = false;
        tip.style.left = `${Math.min(x + 12, window.innerWidth - tip.offsetWidth - 8)}px`;
        tip.style.top = `${y + 12}px`;
    };
    root.querySelectorAll("[data-value]").forEach(target => {
        target.addEventListener("pointermove", event => show(target, event.clientX, event.clientY));
        target.addEventListener("pointerleave", () => { tip.hidden = true; });
        target.addEventListener("focus", () => { const box = target.getBoundingClientRect(); show(target, box.right, box.top); });
        target.addEventListener("blur", () => { tip.hidden = true; });
    });
}

/** Progress band from the server's gap; null until the skill has valid evidence. */
function progressOf(skill) {
    if (skill.gap === null || skill.gap === undefined) return null;
    if (skill.gap === 0) return PROGRESS.met;
    return PROGRESS.todo;
}

/**
 * Gap rows: bar = level from valid evidence (green once the target is met), tinted segment = what is
 * still missing, dot = verified level, tick = target, ring = self-reported (never counted).
 * An unmeasured skill has no bar or dot: it is labelled, never drawn as zero.
 */
export function gapChart(container, skills, { onSelect } = {}) {
    const at = level => `${(Number(level) / 3) * 100}%`;
    const declared = skill => skill.self_reported_level !== null && skill.self_reported_level !== undefined;
    const TONES = { met: "badge-good", todo: "badge-warn", none: "badge-muted" };
    const rows = skills.map((skill, index) => {
        const progress = progressOf(skill);
        const state = progress ? (skill.gap === 0 ? "met" : "todo") : "none";
        const status = progress ? (skill.gap > 0 ? `Thiếu ${skill.gap} mức` : progress.label) : "Chưa đánh giá";
        const lines = [
            progress ? `Hiện tại: mức ${skill.current_level}` : "Hiện tại: chưa có bằng chứng",
            `Mục tiêu: mức ${skill.target_level}`,
            progress ? `Còn thiếu: ${skill.gap} mức` : "Còn thiếu: chưa kết luận",
            progress ? "Trạng thái: đã xác thực" : "Trạng thái: chưa đánh giá",
            declared(skill) ? `Tự khai: mức ${skill.self_reported_level} (không tính)` : "",
            skill.evidence ? `Bằng chứng: ${skill.evidence.source_type === "MINI_TEST" ? "mini-test" : "bài kiểm tra"}, ${fmtDate(skill.evidence.assessed_at)}` : "",
        ].filter(Boolean);
        const bars = progress
            ? `${skill.current_level > 0 ? `<span class="gap-fill" style="--to:${at(skill.current_level)}"></span>` : ""}${skill.gap > 0 ? `<span class="gap-miss" style="--from:${at(skill.current_level)};--to:${at(skill.target_level)}"></span>` : ""}<span class="gap-dot" style="left:${at(skill.current_level)}"></span>`
            : "";
        return `<button type="button" class="gap-row is-${state}" data-skill="${esc(skill.skill_code)}" data-value="${esc(skillName(skill.skill_code))}" data-label="${esc(lines.join("\n"))}" style="--i:${index}">
            <span class="gap-name"><span>${esc(skillName(skill.skill_code))}</span>${skill.is_core ? '<span class="badge">Cốt lõi</span>' : ""}</span>
            <span class="gap-track">${bars}${declared(skill) ? `<span class="gap-self" style="left:${at(skill.self_reported_level)}"></span>` : ""}<span class="gap-target" style="left:${at(skill.target_level)}"></span></span>
            <span class="gap-status"><span class="badge ${TONES[state]}">${status}</span></span></button>`;
    }).join("");
    const axis = [0, 1, 2, 3].map(level => `<span style="left:${at(level)}">Mức ${level}</span>`).join("");
    container.innerHTML = `<div class="gap-chart"><div class="gap-axis" aria-hidden="true"><span></span><span class="gap-ticks">${axis}</span><span></span></div>${rows}</div>
        <div class="chart-legend gap-legend"><span><i class="lg-dot"></i>Hiện tại (đã xác thực)</span><span><i class="lg-target"></i>Mục tiêu</span><span><i class="lg-met"></i>Đạt mục tiêu</span><span><i class="lg-todo"></i>Chưa đạt mục tiêu (phần còn thiếu)</span><span><i class="lg-self"></i>Tự khai (không tính điểm)</span></div>`;
    attachTips(container);
    if (onSelect) container.querySelectorAll(".gap-row").forEach(row => row.addEventListener("click", () => onSelect(row.dataset.skill)));
    requestAnimationFrame(() => container.querySelector(".gap-chart")?.classList.add("is-drawn"));
}

/** Skill level over time, one stepped line per skill, one shared 0-3 axis. */
export function levelHistory(container, evidence) {
    const groups = {};
    evidence.forEach(item => { (groups[item.skill_code] ||= []).push(item); });
    const codes = Object.keys(groups);
    const times = evidence.map(item => new Date(item.created_at).getTime());
    const minTime = Math.min(...times), maxTime = Math.max(...times);
    const width = 640, height = 230, left = 44, right = 16, top = 12, bottom = 28;
    const x = time => (maxTime === minTime ? (left + width - right) / 2 : left + ((time - minTime) / (maxTime - minTime)) * (width - left - right));
    const y = level => top + ((3 - level) / 3) * (height - top - bottom);
    let marks = "";
    for (const level of [0, 1, 2, 3]) marks += `<line class="grid-line" x1="${left}" x2="${width - right}" y1="${y(level)}" y2="${y(level)}"/><text class="tick" x="${left - 8}" y="${y(level) + 4}" text-anchor="end">${level}</text>`;
    marks += `<text class="tick" x="${left}" y="${height - 8}">${esc(fmtDate(minTime))}</text>`;
    if (maxTime !== minTime) marks += `<text class="tick" x="${width - right}" y="${height - 8}" text-anchor="end">${esc(fmtDate(maxTime))}</text>`;
    for (const code of codes) {
        const color = SERIES[code] || INK;
        const points = groups[code].map(item => [x(new Date(item.created_at).getTime()), y(item.level), item]);
        if (points.length > 1) {
            let path = `M${points[0][0]} ${points[0][1]}`;
            points.slice(1).forEach(([px, py]) => { path += ` H${px} V${py}`; });
            marks += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
        }
        for (const [px, py, item] of points) {
            const source = { ASSESSMENT: "bài đánh giá", MINI_TEST: "mini-test", HUMAN_REVIEW: "người duyệt" }[item.source_type] || item.source_type;
            marks += `<circle cx="${px}" cy="${py}" r="4.5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/><circle cx="${px}" cy="${py}" r="12" fill="transparent" tabindex="0" data-value="Mức ${item.level}" data-label="${esc(`${skillName(code)}, ${source}, ${fmtDate(item.created_at)}`)}" aria-label="${esc(`${skillName(code)}: mức ${item.level}, ${fmtDate(item.created_at)}`)}"/>`;
        }
    }
    const legend = codes.map(code => `<span><i class="line" style="background:${SERIES[code] || INK}"></i>${esc(skillName(code))}</span>`).join("");
    const rows = evidence.slice().reverse().map(item => `<tr><td>${fmtDate(item.created_at)}</td><td>${esc(skillName(item.skill_code))}</td><td>${item.level}</td><td>${esc(item.task_id || "")}</td></tr>`).join("");
    container.innerHTML = `<div class="chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Thay đổi mức kỹ năng theo thời gian">${marks}</svg></div><div class="chart-legend">${codes.length > 1 ? legend : ""}</div>
        <details class="data-table"><summary>Xem dạng bảng</summary><div class="table-wrap"><table><thead><tr><th>Ngày</th><th>Kỹ năng</th><th>Mức</th><th>Bài</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    attachTips(container);
}

/** Points earned per criterion: bar over a track, so what was lost is visible at a glance. */
export function criteriaBars(criteria) {
    return criteria.map(item => {
        const percent = item.max_points ? (item.points_awarded / item.max_points) * 100 : 0;
        return `<div class="stack-sm" style="gap:3px"><div class="row-between"><span>${esc(item.label)}</span><span class="nowrap small"><strong>${item.points_awarded}</strong> / ${item.max_points} điểm</span></div><div class="meter" role="img" aria-label="${esc(item.label)}: ${item.points_awarded} trên ${item.max_points} điểm"><span style="width:${percent}%"></span></div></div>`;
    }).join("");
}
