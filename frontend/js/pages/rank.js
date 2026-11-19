/** Xếp hạng và lương: where the learner stands among people who took the exam, what the market pays,
 *  how the levels are defined and what a result rests on. Every figure comes from /career-process/insights. */
import { api, app, emptyView, esc, fmtDate, openModal, register, safeUrl, setView, skillName, toast, withBusy } from "../core.js";
import { icon, skillIcon, tile } from "../icons.js";

export const levelOf = (levels, level) => levels.scale.find(item => item.level === Number(level)) || { name: "", stage: "" };

/** "Top 20%" needs enough people; with fewer the position alone is shown. */
export const standing = ranking => (ranking.top_percent ? `Top ${ranking.top_percent}%` : `Hạng ${ranking.me.rank}/${ranking.total}`);

export function openLevelGuide(levels) {
    const scale = levels.scale.map(item => `<tr><td class="center"><span class="level-pill level-verified" data-level="${item.level}">${item.level}</span></td>
        <td><strong>${esc(item.name)}</strong><span class="sub small guide-stage">${esc(item.stage)}</span></td><td>${esc(item.meaning)}</td><td>${esc(item.proof)}</td></tr>`).join("");
    const skills = levels.skills.map(skill => `<details class="guide-skill"><summary>${esc(skillName(skill.skill_code))}</summary>
        <ol class="guide-levels" start="0">${[0, 1, 2, 3].map(level => `<li><span class="level-pill">${level}</span><span>${esc(skill.levels[level] || "Chưa có mô tả.")}</span></li>`).join("")}</ol></details>`).join("");
    openModal(`<div class="row-between"><h2>Cách phân bậc kỹ năng</h2><button class="btn btn-ghost btn-sm" type="button" data-close-modal>Đóng</button></div>
        <div class="stack guide"><p class="sub">Mỗi kỹ năng có 4 mức. Mức chỉ tăng khi có bài làm chứng minh, mức tự khai không được tính.</p>
            <div class="table-wrap result-table guide-table"><table><thead><tr><th class="center">Mức</th><th>Tên mức</th><th>Ý nghĩa</th><th>Cách chứng minh</th></tr></thead><tbody>${scale}</tbody></table></div>
            <div class="stack-sm"><strong>Tiêu chí từng mức theo kỹ năng</strong>${skills}</div></div>`, { wide: true });
}

export function basisCard(basis) {
    const rows = basis.map(item => `<li><strong>${esc(item.title)}</strong><span>${esc(item.detail)}</span>${item.links.length
        ? `<span class="basis-links">${item.links.map(link => `<a href="${esc(safeUrl(link.url))}" target="_blank" rel="noopener noreferrer" data-no-i18n>${esc(link.label)}</a>`).join("")}</span>` : ""}</li>`).join("");
    return `<details class="card basis"><summary>${tile("shield", "brand", "tile-sm")}<span><strong>Kết quả này dựa trên gì</strong><span class="sub small">Nguồn của khung kỹ năng, mức JD, điểm số và học liệu</span></span>${icon("arrow")}</summary><ul class="basis-list">${rows}</ul></details>`;
}

const BASES = [["current", "Năng lực hiện tại", "route"], ["exam", "Bài kiểm tra đầu vào", "quiz"]];
const MEDALS = { 1: "is-gold", 2: "is-silver", 3: "is-bronze" };
let view = { basis: "current", skill: "" };

/* --- 5.51: fewer words. Long explanations moved into tooltips or a closed "Cách xếp hạng"; every control kept. --- */
function changeChip(change) {
    if (change === null || change === undefined) return "";
    const [name, label, tone] = change > 0 ? ["growth", `Tăng ${change} hạng`, "is-up"] : change < 0 ? ["pulse", `Giảm ${Math.abs(change)} hạng`, "is-down"] : ["check", "Giữ hạng", ""];
    return `<span class="rk-change ${tone}" title="So với bài kiểm tra đầu vào">${icon(name)}<span>${label}</span></span>`;
}

function heroCard(ranking, levels) {
    const me = ranking.me;
    if (!me) return `<section class="card">${emptyView("Chưa có vị trí xếp hạng", "Bảng xếp hạng tính từ bài kiểm tra Career Adapt đã chấm.")}</section>`;
    const level = levelOf(levels, me.overall_level);
    const scope = ranking.skill ? skillName(ranking.skill) : "Tất cả kỹ năng";
    const percent = Math.round((100 * me.level_points) / (me.max_points || 1));
    return `<section class="card rk-hero page-hero is-amber rk2-hero"><div class="rk2-main">${tile("trophy", "brand")}<div class="rk2-place">
            <span class="rk2-scope">${esc(BASES.find(item => item[0] === ranking.basis)[1])} · ${esc(scope)}</span>
            <strong class="rank-big">${esc(standing(ranking))}</strong>
            <span class="rk2-chips">${changeChip(ranking.rank_change)}${ranking.enough ? "" : `<span class="rk-change" title="Cần ít nhất ${ranking.min_cohort} học viên để tính tỉ lệ Top">${icon("info")}<span>${ranking.total}/${ranking.min_cohort} người để tính Top</span></span>`}</span></div></div>
        <div class="rk2-kpis">
            <div title="Mức ${me.overall_level}/3 · ${esc(level.stage)}"><span>${ranking.skill ? "Mức kỹ năng" : "Trình độ"}</span><strong>${esc(level.name)}</strong></div>
            <div><span>Tổng mức</span><strong>${me.level_points}/${me.max_points}</strong><span class="meter"><span style="width:${percent}%"></span></span></div>
            <div><span>Điểm đầu vào</span><strong>${me.score}/100</strong></div></div>
        <div class="rk2-actions"><button class="btn btn-primary btn-sm" type="button" data-act="share">${icon("link")}<span>Chia sẻ</span></button>
            <label class="check rk2-visible" title="Người khác chỉ thấy tên bạn khi bạn bật lựa chọn này."><input type="checkbox" data-act="visible" ${ranking.visible ? "checked" : ""}><span>Hiện tên tôi</span></label>
            <button class="btn btn-ghost btn-sm rk2-guide" type="button" data-act="guide">${icon("info")}<span>Cách phân bậc</span></button></div></section>`;
}

function controls(ranking) {
    return `<div class="rk2-controls"><div class="seg rk-seg" role="radiogroup" aria-label="Cách xếp hạng">${BASES.map(([id, label, name]) => `<button type="button" class="seg-option ${ranking.basis === id ? "is-active" : ""}" aria-pressed="${ranking.basis === id}" data-act="basis" data-basis="${id}">${icon(name)}<span>${label}</span></button>`).join("")}</div>
        <select class="select rk2-skill" data-skill-filter aria-label="Kỹ năng"><option value="">Tất cả kỹ năng</option>${ranking.skills.map(code => `<option value="${esc(code)}" ${ranking.skill === code ? "selected" : ""}>${esc(skillName(code))}</option>`).join("")}</select></div>`;
}

/** A row's picture: the server sends one only for you and for learners who chose to show their name. */
function rowAvatar(item) {
    if (item.avatar) return `<span class="rk-avatar has-photo"><img src="${esc(item.avatar)}" alt="" loading="lazy" decoding="async"></span>`;
    if (item.is_me) return `<span class="rk-avatar is-me">${esc((app.user?.full_name || "?").trim().slice(0, 1).toUpperCase())}</span>`;
    return `<span class="rk-avatar is-anon">${icon("user")}</span>`;
}

function boardCard(ranking, levels, note = "") {
    const rows = ranking.board.map(item => {
        const percent = Math.round((100 * item.level_points) / (item.max_points || 1));
        return `<li class="rk-row ${item.is_me ? "is-me" : ""}"><span class="rk-rank ${MEDALS[item.rank] || ""}">${item.rank}</span>
            <div class="rk-who">${rowAvatar(item)}<div class="rk-who-text"><strong ${item.is_me || item.name === "Học viên ẩn danh" ? "" : "data-no-i18n"}>${esc(item.name)}</strong><span class="sub small">${esc(levelOf(levels, item.overall_level).name)}</span></div></div>
            <div class="rk-points"><span class="meter"><span style="width:${percent}%"></span></span><span class="small"><strong>${item.level_points}</strong>/${item.max_points}</span></div>
            <span class="rk-score" title="Điểm bài đầu vào">${item.score}</span></li>`;
    }).join("");
    return `<section class="card rk-board"><div class="rk2-board-head"><h2>Bảng xếp hạng</h2><span class="badge badge-muted">${ranking.total} học viên</span></div>
        ${controls(ranking)}
        ${ranking.board.length ? `<div class="rk-head small"><span>Hạng</span><span>Học viên</span><span>Tổng mức</span><span>Điểm</span></div><ol class="rk-list">${rows}</ol>`
        : emptyView("Chưa có ai trên bảng", "Bảng xếp hạng sẽ có dữ liệu khi có bài kiểm tra được chấm.")}
        <div class="rk2-board-foot">${note}<details class="rk2-rule"><summary>${icon("info")}<span>Cách xếp hạng</span></summary><p>${esc(ranking.rule)}</p></details></div></section>`;
}

function cohortCard(ranking) {
    const body = ranking.cohort.length
        ? `<ul class="rk-cohort">${ranking.cohort.map(item => `<li><div class="row-between"><span class="skill-name">${skillIcon(item.skill_code)}<strong>${esc(skillName(item.skill_code))}</strong></span><span class="small">≥ <strong>${item.at_or_below_percent}%</strong></span></div>
            <div class="rk-scale" aria-label="Mức của bạn ${item.mine}, trung bình nhóm ${item.average}"><span class="rk-avg" style="left:${(item.average / 3) * 100}%" title="Trung bình nhóm"></span><span class="rk-mine" style="left:${(item.mine / 3) * 100}%" title="Bạn"></span></div></li>`).join("")}</ul>
            <p class="rk-legend small"><span class="rk-dot is-mine"></span>Bạn <span class="rk-dot is-avg"></span>Trung bình nhóm · mức 0-3</p>`
        : `<p class="rk2-empty">${icon("lock")}<span>Cần từ ${ranking.min_cohort} học viên để so sánh, để không ai bị nhận ra.</span></p>`;
    return `<section class="card rk2-side"><h2 title="Số liệu gộp, không hiện kết quả của riêng ai.">So với nhóm</h2>${body}</section>`;
}

function distributionCard(ranking, levels) {
    if (!ranking.distribution.length) return "";
    const most = Math.max(...ranking.distribution.map(item => item.count), 1);
    const mine = ranking.me?.overall_level;
    return `<section class="card rk2-side"><h2>Phân bố trình độ</h2>
        <ul class="rk-dist">${ranking.distribution.map(item => `<li class="${item.level === mine ? "is-mine" : ""}"><span class="rk-dist-label">${esc(levelOf(levels, item.level).name)}</span><span class="rk-dist-bar"><span style="width:${(item.count / most) * 100}%"></span></span><strong>${item.count}</strong></li>`).join("")}</ul></section>`;
}

export function salaryCard(salary) {
    if (!salary) return `<section class="card">${emptyView("Chưa có số liệu lương", "Lương tham khảo chỉ hiện khi có số liệu kèm nguồn công khai.")}</section>`;
    const max = Math.max(...salary.bands.map(item => item.value), salary.overall?.value || 0);
    const source = salary.source;
    const number = value => value.toLocaleString("vi-VN");
    // Bars and the overall line share one pixel scale, so the line sits exactly at its value.
    const PLOT = 170;
    const px = value => Math.round((value / max) * PLOT);
    const columns = salary.bands.map((item, index) => `<li class="pay-col"><strong class="pay-col-value">${number(item.value)}</strong><span class="pay-col-bar ${index === salary.bands.length - 1 ? "is-top" : ""}" style="height:${px(item.value)}px"></span><span class="pay-col-label">${esc(item.label)}</span></li>`).join("");
    const overall = salary.overall ? `<span class="pay-overall" style="bottom:${px(salary.overall.value)}px"></span>` : "";
    const notes = [salary.missing_note, salary.scope_note].filter(Boolean).map(esc).join(" ");
    const tiles = [
        salary.growth_percent ? `<div class="rk2-pay-tile is-growth">${icon("growth")}<div><strong>+${salary.growth_percent}%</strong><span><span>${esc(salary.bands[0].label)}</span> → <span>${esc(salary.bands[salary.bands.length - 1].label)}</span></span></div></div>` : "",
        salary.overall ? `<div class="rk2-pay-tile">${icon("chart")}<div><strong>${number(salary.overall.value)}</strong><span>${esc(salary.overall.label)} · ${esc(salary.unit)}</span></div></div>` : "",
        source.sample_size ? `<div class="rk2-pay-tile">${icon("user")}<div><strong>${source.sample_size.toLocaleString("vi-VN")}</strong><span>người trả lời khảo sát</span></div></div>` : "",
    ].join("");
    return `<section class="card pay-card rk2-pay"><div class="rk2-board-head"><h2>Lương tham khảo</h2><span class="badge badge-muted" title="${esc(salary.role_label)}">${esc(salary.statistic)} · ${esc(salary.unit)}</span></div>
        <div class="rk2-pay-body"><div class="rk2-pay-chart"><div class="pay-chart"><ul class="pay-cols">${columns}</ul>${overall}</div>
                ${salary.overall ? `<p class="rk2-pay-legend"><i></i><span>${esc(salary.overall.label)}: ${number(salary.overall.value)}</span></p>` : ""}</div>
            <div class="rk2-pay-tiles">${tiles}</div></div>
        <div class="rk2-pay-foot"><p class="rk2-source">${icon("file")}<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${esc(source.label)}</a></p>
            <details class="rk2-rule"><summary>${icon("info")}<span>Về số liệu</span></summary><p>${notes}</p><p class="rk2-facts"><span>${esc(salary.role_label)}</span>${source.survey_period ? `<span>Khảo sát ${esc(source.survey_period)}</span>` : ""}${source.sample_size ? `<span>${source.sample_size.toLocaleString("vi-VN")} người trả lời</span>` : ""}<span>Kiểm tra ngày ${fmtDate(source.checked_at)}</span></p></details></div></section>`;
}

/** What the learner chooses to send to friends: their own level and standing, plus the public intro page. */
function shareText(ranking, levels) {
    const me = ranking.me;
    const level = levelOf(levels, me.overall_level);
    const place = ranking.top_percent ? `, thuộc Top ${ranking.top_percent}%` : "";
    return `Mình vừa đo năng lực Data Analyst trên CareerAdapt AI: ${level.name} (mức ${me.overall_level}/3)${place}. Bạn thử đo năng lực của mình tại ${window.location.origin}/gioi-thieu`;
}

export async function renderRank() {
    const query = new URLSearchParams({ rank_basis: view.basis, ...(view.skill ? { skill: view.skill } : {}) });
    const data = await api(`/career-process/insights?${query}`);
    const { ranking, levels, salary } = data;
    // 5.56: with too few learners the comparison is one line inside the board instead of a near-empty card.
    const side = [ranking.cohort.length ? cohortCard(ranking) : "", distributionCard(ranking, levels)].filter(Boolean);
    const note = ranking.cohort.length ? "" : `<p class="rk2-empty">${icon("lock")}<span>So với nhóm: cần từ ${ranking.min_cohort} học viên để so sánh, để không ai bị nhận ra.</span></p>`;
    setView(`<div class="stack rk">${heroCard(ranking, levels)}${boardCard(ranking, levels, note)}
        ${side.length ? `<div class="rk2-row ${side.length === 1 ? "is-single" : ""}">${side.join("")}</div>` : ""}
        ${salaryCard(salary)}</div>`);
    document.querySelector("[data-skill-filter]")?.addEventListener("change", event => { view = { ...view, skill: event.target.value }; renderRank(); });
    register({
        actions: {
            guide: () => openLevelGuide(levels),
            basis: element => { view = { ...view, basis: element.dataset.basis }; withBusy(element, renderRank); },
            share: async () => {
                if (!ranking.me) return;
                try {
                    await navigator.clipboard.writeText(shareText(ranking, levels));
                    toast("Đã sao chép. Bạn có thể dán vào tin nhắn hoặc bài đăng.", "good");
                } catch {
                    toast("Trình duyệt không cho sao chép tự động.", "bad");
                }
            },
            visible: element => {
                // Read the new state now: the click is cancelled by the page's handler, and the server's answer redraws the box.
                const visible = element.checked;
                withBusy(element, async () => {
                    const result = await api("/career-process/leaderboard-visibility", { method: "PUT", body: { visible } });
                    toast(result.visible ? "Tên bạn sẽ hiện trên bảng xếp hạng." : "Bạn đang ở chế độ ẩn danh.", "good");
                    renderRank();
                });
            },
        },
    });
}
