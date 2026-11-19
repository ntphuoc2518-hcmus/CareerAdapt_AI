/** Kế hoạch Career Adapt: what the finished process produced. Gap, roadmap and progress reuse their pages. */
import { alertBox, api, emptyView, esc, fmtDate, fmtDateTime, formatText, register, setSubnav, setView, skillName, SOURCE_TYPES, withBusy } from "../core.js";
import { openAssistantTask } from "../assistant.js";
import { icon, skillIcon, skillTile, tile, aiAvatar } from "../icons.js";
import { renderReview } from "./exam.js";
import { renderGap } from "./gap.js";
import { renderProgress } from "./progress.js";
import { basisCard, levelOf, openLevelGuide, renderRank, standing } from "./rank.js";
import { openResetDialog } from "./process.js";
import { renderRoadmap } from "./roadmap.js";
import { pageHero } from "../hero.js";
import { disclose } from "../disclose.js";
import { mountPlanAdvisor } from "../plan-advisor.js";

const CAREER_TABS = [["da", "Data Analyst", "chart"], ["backend", "Backend Developer", "code"], ["qa", "QA Tester", "flask"]];
const SECTIONS = [["overview", "Khai báo và JD", "file"], ["exam", "Kết quả bài làm", "check"], ["gap", "Khoảng cách kỹ năng", "pulse"], ["roadmap", "Lộ trình học tập", "route"], ["rank", "Xếp hạng và lương", "trophy"], ["progress", "Nhắc nhở", "bell"]];
const METHODS = { PICK: "Chọn từ danh sách", IMPORT: "Nhập hoặc import tệp", FORM: "Biểu mẫu" };

function subnav(career, section) {
    const careers = CAREER_TABS.map(([id, label, name]) => `<a class="tab ${id === career ? "is-active" : ""}" href="#/plan/${id}${id === "da" ? "/overview" : ""}" ${id === career ? 'aria-current="page"' : ""}>${icon(name)}${label}${id === "da" ? "" : ' <span class="badge badge-warn">Sắp có</span>'}</a>`).join("");
    const sections = career === "da" && section ? `<div class="tabs tabs-sub">${SECTIONS.map(([id, label, name]) => `<a class="tab ${id === section ? "is-active" : ""}" href="#/plan/da/${id}" ${id === section ? 'aria-current="page"' : ""}>${icon(name)}${label}</a>`).join("")}</div>` : "";
    setSubnav(`<div class="tabs">${careers}</div>${sections}`);
}

/** The skills reported at the start. The process is locked once finished, so they are shown, not edited. */
function skillCard(run) {
    const grid = run.skills.length
        ? `<ul class="self-grid">${run.skills.map(item => `<li class="self-skill">${skillTile(item.skill_code, "tile-sm")}<div><strong>${esc(skillName(item.skill_code))}</strong>
            <span class="self-level"><span class="level-pill level-self">${item.level}</span><span class="sub small">Mức ${item.level}/3</span>${levelSteps(Number(item.level))}</span>
            ${item.evidence_note ? `<span class="sub small">${esc(item.evidence_note)}</span>` : ""}</div></li>`).join("")}</ul>`
        : emptyView("Không có", "Bạn chưa khai báo kỹ năng nào.");
    return `<section class="card self-card"><div class="rd-head">${tile("user", "brand", "tile-sm")}<div><h2>Kỹ năng bạn tự khai</h2><p class="sub small">${esc(METHODS[run.skill_method] || "")}</p></div><span class="badge badge-muted">${run.skills.length} kỹ năng</span></div>
        ${grid}<p class="meta">${icon("info")}<span>Chỉ để so sánh với kết quả bài làm, không phải trình độ đã xác thực.</span></p></section>`;
}

function jdCard(jd) {
    const requirements = jd.requirements || [];
    return `<section class="card self-card"><div class="rd-head">${tile("file", "brand", "tile-sm")}<div><h2>JD đã sử dụng</h2><p class="sub small">${esc(jd.name || "")}${SOURCE_TYPES[jd.source_type] ? ` · ${esc(SOURCE_TYPES[jd.source_type])}` : ""}</p></div>
            <button class="btn btn-secondary btn-sm" type="button" data-act="jd-ai">${aiAvatar("xs")}<span>AI tóm tắt</span></button></div>
        <div class="jd-summary"><span class="jd-summary-head"><strong>Tóm tắt</strong><span class="badge badge-muted">${jd.summary_source === "AI" ? "AI tóm tắt" : "Tóm tắt theo quy tắc, chưa dùng AI"}</span></span>${formatText(jd.summary || "")}</div>
        ${requirements.length ? `<div class="stack-sm"><strong class="jd-req-title">Kỹ năng JD yêu cầu <span class="badge badge-muted">${requirements.length} kỹ năng</span></strong>
            <ul class="self-grid">${requirements.map(item => `<li class="self-skill">${skillTile(item.skill_code, "tile-sm")}<div><strong>${esc(skillName(item.skill_code))}</strong><span class="self-level"><span class="level-pill level-target">${item.target_level}</span><span class="sub small">Cần mức ${item.target_level}/3</span>${levelSteps(Number(item.target_level))}</span></div></li>`).join("")}</ul></div>` : ""}</section>`;
}

function overviewHero(run) {
    const jd = run.jd || {};
    const name = jd.name ? esc(jd.name) : "JD chưa có tên";
    return pageHero({
        tone: "brand", icon: "file", kicker: "Khai báo và JD", title: `Mục tiêu: ${name}`,
        text: "Kỹ năng bạn tự khai và JD dùng để đánh giá. Quy trình đã khóa sau khi hoàn tất.",
        stats: [["user", "Kỹ năng tự khai", run.skills.length], ["target", "Kỹ năng JD yêu cầu", (jd.requirements || []).length], ["calendar", "Ngày hoàn tất", fmtDate(run.completed_at), "muted"]],
    });
}

async function overview(run) {
    setView(`<div class="stack">${overviewHero(run)}${skillCard(run)}${jdCard(run.jd || {})}
        <section class="card row-between"><div class="card-title">${tile("refresh", "bad")}<div><h2>Làm lại từ đầu</h2><p class="sub small">Hoàn tất lúc ${fmtDateTime(run.completed_at)}. Quy trình đã khóa, muốn làm lại phải reset.</p></div></div><button class="btn btn-danger" data-act="reset">${icon("refresh")}<span>Reset quy trình</span></button></section></div>`);
    register({
        actions: {
            reset: element => withBusy(element, openResetDialog),
            // The server's JD task: AI when available, otherwise its rule-based explanation, never an invented one.
            "jd-ai": element => openAssistantTask("jd_analysis", element.textContent.trim()),
        },
    });
}

/* Results tab. Every figure is read from /career-process/exam/review; only differences and counts are derived here. */
const round1 = value => Math.round(Number(value) * 10) / 10;

function scoreRing(data) {
    const percent = Math.max(0, Math.min(100, (Number(data.score) / Number(data.max_score || 100)) * 100));
    const length = 2 * Math.PI * 52;
    const mark = (Number(data.pass_threshold) / Number(data.max_score || 100)) * 360;
    return `<div class="ring result-ring ${data.passed ? "is-pass" : "is-fail"}" role="img" aria-label="${esc(String(data.score))}/${esc(String(data.max_score))}"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="52" class="ring-track"/><circle cx="60" cy="60" r="52" class="ring-bar" stroke-dasharray="${(length * percent) / 100} ${length}"/><line class="ring-mark" x1="104" y1="60" x2="118" y2="60" transform="rotate(${mark} 60 60)"/></svg><div><strong>${esc(String(data.score))}</strong><span>/ ${esc(String(data.max_score))} điểm</span></div></div>`;
}

function scorePanel(data) {
    const gap = round1(Number(data.score) - Number(data.pass_threshold));
    const remark = data.passed ? `Cao hơn ngưỡng đạt ${gap} điểm.` : `Còn thiếu ${Math.abs(gap)} điểm để đạt ngưỡng.`;
    const pasted = data.integrity?.large_inserts || 0;
    const notes = [data.auto_submitted ? "Bài được tự động nộp." : "", data.violations ? `Rời màn hình ${data.violations} lần.` : "", pasted ? `Máy chủ ghi nhận ${pasted} lần dán nhiều chữ (chỉ để tham khảo, không ảnh hưởng điểm).` : ""].filter(Boolean);
    return `<section class="card result-score ${data.passed ? "is-pass" : "is-fail"}">${scoreRing(data)}
        <div class="result-verdict"><span class="eyebrow-label">Kết quả đánh giá</span><h2>Bài kiểm tra năng lực Data Analyst</h2>
            <span class="badge ${data.passed ? "badge-good" : "badge-bad"} verdict-badge">${icon(data.passed ? "check" : "alert")}<span>${data.passed ? "Đạt" : "Chưa đạt"}</span></span>
            <span class="sub small">Ngưỡng đạt ${data.pass_threshold}/${data.max_score}</span>
            ${notes.length ? `<span class="sub small">${esc(notes.join(" "))}</span>` : ""}
            ${data.critical_violations.length ? `<span class="small" style="color:var(--bad)"><strong>Lỗi trọng yếu:</strong> ${esc(data.critical_violations.join("; "))}</span>` : ""}</div>
        <div class="result-remark">${tile(data.passed ? "trophy" : "target", data.passed ? "good" : "warn")}<p><strong>${remark}</strong></p></div></section>`;
}

function reviewPanel(data) {
    return `<section class="card result-review"><div class="card-title">${tile("quiz")}<div><h2>Bài đã làm</h2><p class="sub small">Xem từng bài, chỗ đúng sai và nhận xét.</p></div></div>
        <p class="meta">${icon("check")}<span>${data.questions.length} bài đã chấm · nộp ${fmtDateTime(data.submitted_at)}</span></p>
        <a class="btn btn-primary btn-glow" href="#/plan/da/review"><span>Xem lại bài làm</span>${icon("arrow")}</a></section>`;
}

function levelSteps(verified) {
    return `<span class="lvl-steps" aria-hidden="true">${[1, 2, 3].map(step => `<i class="${step <= verified ? "is-on" : ""}"></i>`).join("")}</span>`;
}

function levelCard(data, insights) {
    const conclusion = data.conclusion;
    const overall = levelOf(insights.levels, conclusion.overall_level);
    const ranking = insights.ranking;
    const met = conclusion.skills.filter(item => item.verified_level >= item.target_level);
    const unmet = conclusion.skills.filter(item => item.verified_level < item.target_level);
    // Same rule as the server summary: the unmet skill furthest below its JD level.
    const weakest = unmet.length ? unmet.reduce((low, item) => (item.verified_level - item.target_level < low.verified_level - low.target_level ? item : low)) : null;
    const facts = [
        ["shield", "Trình độ hiện tại", esc(conclusion.overall_label), `Mức ${conclusion.overall_level}/3 · ${esc(overall.stage)}`],
        ["target", "Kỹ năng đáp ứng JD", `${met.length}/${conclusion.skills.length}`, "kỹ năng đạt mức JD yêu cầu"],
        ["pulse", "Khoảng cách lớn nhất", weakest ? esc(weakest.topic) : "Không có", weakest ? `${esc(skillName(weakest.skill_code))}: mức ${weakest.verified_level}, cần ${weakest.target_level}` : "Đã đáp ứng mọi kỹ năng"],
        ["trophy", "Mức độ cạnh tranh", ranking.me ? esc(standing(ranking)) : "Chưa xếp hạng", ranking.me ? `hạng ${ranking.me.rank} trên ${ranking.total} học viên` : "Chưa có bài được chấm"],
    ];
    const rows = conclusion.skills.map(item => {
        const gap = item.target_level - item.verified_level;
        return `<tr><td><span class="skill-name">${skillIcon(item.skill_code)}<strong>${esc(skillName(item.skill_code))}</strong></span><span class="sub small skill-topic">${esc(item.topic)} · ${esc(item.tier_label)}</span>
                <details class="why"><summary>Vì sao</summary><p>${esc(item.reason)} ${esc(item.compare)}</p></details></td>
            <td><span class="level-cell"><span class="level-pill level-verified" data-level="${item.verified_level}">${item.verified_level}</span>${levelSteps(item.verified_level)}</span><span class="sub small">${esc(levelOf(insights.levels, item.verified_level).name)}</span></td>
            <td><span class="level-cell"><span class="level-pill">${item.target_level}</span></span><span class="sub small">${esc(levelOf(insights.levels, item.target_level).name)}</span></td>
            <td><span class="badge ${gap <= 0 ? "badge-good" : "badge-warn"}">${gap <= 0 ? "Đạt JD" : `Thiếu ${gap} mức`}</span></td></tr>`;
    }).join("");
    const next = weakest ? `Ưu tiên học ${skillName(weakest.skill_code)} trước: đang ở mức ${weakest.verified_level}, JD cần mức ${weakest.target_level}.` : "Bạn đã đáp ứng mọi kỹ năng JD yêu cầu. Hãy giữ nhịp luyện tập theo lộ trình.";
    return `<section class="card level-card"><div class="rd-head">${tile("sparkles")}<div><h2>Nhận xét trình độ hiện tại</h2><p class="sub small">Từ điểm từng bài và quy tắc chấm, không phải chứng chỉ nghề.</p></div><button class="btn btn-secondary btn-sm" type="button" data-act="guide">${icon("info")}<span>Cách phân bậc</span></button></div>
        <div class="level-facts">${facts.map(([name, label, value, note]) => `<div class="level-fact">${icon(name)}<div><span class="sub small">${label}</span><strong>${value}</strong><span class="sub small">${note}</span></div></div>`).join("")}</div>
        <div class="next-step">${icon("route")}<div><span class="sub small">Việc nên làm tiếp</span><strong>${esc(next)}</strong></div><a class="btn btn-primary btn-sm" href="#/plan/da/roadmap"><span>Mở lộ trình</span>${icon("arrow")}</a></div>
        ${data.ai.overall ? `<div class="ai-note">${aiAvatar("sm")}<div>${formatText(data.ai.overall)}</div></div>` : ""}
        <div class="table-wrap result-table"><table><thead><tr><th>Kỹ năng</th><th>Đã xác thực</th><th>JD yêu cầu</th><th>Kết quả</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="sub small">${esc(conclusion.scope_note || "")}</p></section>`;
}

function examHero(data) {
    const skills = data.conclusion.skills;
    const met = skills.filter(item => item.verified_level >= item.target_level).length;
    const gap = round1(Number(data.pass_threshold) - Number(data.score));
    const title = data.passed ? `Bạn đã đạt bài kiểm tra với ${data.score}/${data.max_score} điểm.` : `Bạn được ${data.score}/${data.max_score} điểm, còn thiếu ${gap} điểm để đạt.`;
    return pageHero({
        tone: "violet", icon: "check", kicker: "Kết quả bài làm", title,
        text: `Trình độ đã xác thực: ${esc(data.conclusion.overall_label)} (mức ${data.conclusion.overall_level}/3). Điểm do bộ chấm tính từ test case, không do AI.`,
        stats: [["quiz", "Điểm bài làm", `${data.score}/${data.max_score}`, data.passed ? "good" : "bad"], ["shield", "Ngưỡng đạt", data.pass_threshold, "muted"],
            ["target", "Kỹ năng đạt JD", `${met}/${skills.length}`, met === skills.length ? "good" : "warn"], ["file", "Bài đã chấm", data.questions.length]],
    });
}

async function examResult() {
    const [data, insights] = await Promise.all([api("/career-process/exam/review"), api("/career-process/insights")]);
    setView(`<div class="stack">${examHero(data)}<div class="result-top">${scorePanel(data)}${reviewPanel(data)}</div>${levelCard(data, insights)}${basisCard(insights.basis)}</div>`);
    register({ actions: { guide: () => openLevelGuide(insights.levels) } });
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
        renderReview(await api("/career-process/exam/review"), { backHref: "#/plan/da/exam", backLabel: "Quay lại kết quả" });
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
     overview: declared skills shown · JD, reset behind buttons
     exam:     score and review shown · level assessment, basis behind buttons
     gap:      gap chart shown · detail, priority, other JDs behind buttons
     roadmap:  progress, next lesson and the weekly breakdown shown · final, older lessons behind buttons
     rank:     ranking board shown · salary, level guide behind buttons
     progress: due tasks shown · log behind a button --- */
const has = selector => element => Boolean(element.querySelector(selector));
const PANELS = {
    overview: [
        { id: "jd", title: "JD đã sử dụng", hint: "Tóm tắt JD và các kỹ năng JD yêu cầu", icon: "file", match: has('[data-act="jd-ai"]') },
        { id: "reset", title: "Làm lại từ đầu", hint: "Reset quy trình, xem trước dữ liệu bị xóa", icon: "refresh", tone: "rose", match: has('[data-act="reset"]') },
    ],
    exam: [
        { id: "levels", title: "Nhận xét trình độ", hint: "Mức từng kỹ năng so với JD, việc nên làm tiếp", icon: "sparkles", match: el => el.matches(".level-card") },
        { id: "basis", title: "Cơ sở đánh giá", hint: "Kết quả được tính từ đâu", icon: "info", match: el => el.matches(".basis") },
    ],
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
    rank: [
        { id: "pay", title: "Lương tham khảo", hint: "Lương theo nhóm kinh nghiệm, có nguồn công khai", icon: "growth", match: el => el.matches(".pay-card") },
        { id: "levels", title: "Cách phân bậc kỹ năng", hint: "Ý nghĩa từng mức 0 đến 3", icon: "info", match: has('[data-act="guide"]') },
    ],
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
