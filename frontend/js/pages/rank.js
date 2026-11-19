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

function changeChip(change) {
    if (change === null || change === undefined) return "";
    if (change > 0) return `<span class="rk-change is-up">${icon("growth")}<span>Tăng ${change} hạng so với bài đầu vào</span></span>`;
    if (change < 0) return `<span class="rk-change is-down">${icon("pulse")}<span>Giảm ${Math.abs(change)} hạng so với bài đầu vào</span></span>`;
    return `<span class="rk-change">${icon("check")}<span>Giữ nguyên hạng so với bài đầu vào</span></span>`;
}

function heroCard(ranking, levels) {
    const me = ranking.me;
    if (!me) return `<section class="card">${emptyView("Chưa có vị trí xếp hạng", "Bảng xếp hạng tính từ bài kiểm tra Career Adapt đã chấm.")}</section>`;
    const level = levelOf(levels, me.overall_level);
    const scope = ranking.skill ? skillName(ranking.skill) : "Tất cả kỹ năng";
    const note = ranking.enough ? `Hạng ${me.rank} trên ${ranking.total} học viên Data Analyst.` : `Hiện có ${ranking.total} học viên. Cần ít nhất ${ranking.min_cohort} người để tính tỉ lệ Top.`;
    return `<section class="card rk-hero page-hero is-amber"><div class="rk-hero-main">${tile("trophy", "brand")}<div><span class="eyebrow-label">Vị trí của bạn · ${esc(BASES.find(item => item[0] === ranking.basis)[1])} · ${esc(scope)}</span>
            <strong class="rank-big">${esc(standing(ranking))}</strong><span class="sub small">${esc(note)}</span>${changeChip(ranking.rank_change)}</div></div>
        <div class="rk-facts"><div><span class="sub small">${ranking.skill ? "Mức kỹ năng" : "Trình độ trung bình"}</span><strong>${esc(level.name)}</strong><span class="sub small">Mức ${me.overall_level}/3 · ${esc(level.stage)}</span></div>
            <div><span class="sub small">Tổng mức đã xác thực</span><strong>${me.level_points}/${me.max_points}</strong><span class="meter"><span style="width:${Math.round((100 * me.level_points) / (me.max_points || 1))}%"></span></span></div>
            <div><span class="sub small">Điểm bài đầu vào</span><strong>${me.score}/100</strong><span class="sub small">bài Career Adapt gần nhất</span></div></div>
        <div class="rk-actions"><button class="btn btn-primary btn-sm" type="button" data-act="share">${icon("link")}<span>Sao chép để chia sẻ</span></button>
            <label class="check"><input type="checkbox" data-act="visible" ${ranking.visible ? "checked" : ""}><span>Hiện tên tôi trên bảng xếp hạng</span></label>
            <span class="meta">${icon("info")}<span>Người khác chỉ thấy tên bạn khi bạn bật lựa chọn này.</span></span></div></section>`;
}

function controls(ranking) {
    return `<section class="card rk-controls"><div class="seg rk-seg" role="radiogroup" aria-label="Cách xếp hạng">${BASES.map(([id, label, name]) => `<button type="button" class="seg-option ${ranking.basis === id ? "is-active" : ""}" aria-pressed="${ranking.basis === id}" data-act="basis" data-basis="${id}">${icon(name)}<span>${label}</span></button>`).join("")}</div>
        <label class="field rk-skill"><span>Kỹ năng</span><select class="select" data-skill-filter><option value="">Tất cả kỹ năng</option>${ranking.skills.map(code => `<option value="${esc(code)}" ${ranking.skill === code ? "selected" : ""}>${esc(skillName(code))}</option>`).join("")}</select></label></section>`;
}

/** A row's picture: the server sends one only for you and for learners who chose to show their name. */
function rowAvatar(item) {
    if (item.avatar) return `<span class="rk-avatar has-photo"><img src="${esc(item.avatar)}" alt="" loading="lazy" decoding="async"></span>`;
    if (item.is_me) return `<span class="rk-avatar is-me">${esc((app.user?.full_name || "?").trim().slice(0, 1).toUpperCase())}</span>`;
    return `<span class="rk-avatar is-anon">${icon("user")}</span>`;
}

function boardCard(ranking, levels) {
    const rows = ranking.board.map(item => {
        const percent = Math.round((100 * item.level_points) / (item.max_points || 1));
        return `<li class="rk-row ${item.is_me ? "is-me" : ""}"><span class="rk-rank ${MEDALS[item.rank] || ""}">${item.rank}</span>
            <div class="rk-who">${rowAvatar(item)}<div class="rk-who-text"><strong ${item.is_me || item.name === "Học viên ẩn danh" ? "" : "data-no-i18n"}>${esc(item.name)}</strong><span class="sub small">${esc(levelOf(levels, item.overall_level).name)}</span></div></div>
            <div class="rk-points"><span class="meter"><span style="width:${percent}%"></span></span><span class="small"><strong>${item.level_points}</strong>/${item.max_points}</span></div>
            <span class="rk-score" title="Điểm bài đầu vào">${item.score}</span></li>`;
    }).join("");
    return `<section class="card rk-board">${sectionHead("chart", "Bảng xếp hạng", `${ranking.total} học viên · hiển thị ${ranking.board.length} dòng`)}
        ${ranking.board.length ? `<div class="rk-head small"><span>Hạng</span><span>Học viên</span><span>Tổng mức</span><span>Điểm</span></div><ol class="rk-list">${rows}</ol>`
        : emptyView("Chưa có ai trên bảng", "Bảng xếp hạng sẽ có dữ liệu khi có bài kiểm tra được chấm.")}
        <p class="meta">${icon("info")}<span>${esc(ranking.rule)}</span></p></section>`;
}

function cohortCard(ranking) {
    const body = ranking.cohort.length
        ? `<ul class="rk-cohort">${ranking.cohort.map(item => `<li><div class="row-between"><span class="skill-name">${skillIcon(item.skill_code)}<strong>${esc(skillName(item.skill_code))}</strong></span><span class="small">Bằng hoặc cao hơn <strong>${item.at_or_below_percent}%</strong></span></div>
            <div class="rk-scale" aria-label="Mức của bạn ${item.mine}, trung bình nhóm ${item.average}"><span class="rk-avg" style="left:${(item.average / 3) * 100}%" title="Trung bình nhóm"></span><span class="rk-mine" style="left:${(item.mine / 3) * 100}%" title="Bạn"></span></div>
            <div class="row-between sub small"><span>Bạn: mức ${item.mine}</span><span>Trung bình nhóm: ${String(item.average).replace(".", ",")}</span></div></li>`).join("")}</ul>
            <p class="rk-legend small"><span class="rk-dot is-mine"></span>Bạn <span class="rk-dot is-avg"></span>Trung bình nhóm · thang mức 0-3</p>`
        : emptyView("Chưa đủ người để so sánh", `So sánh nhóm chỉ hiện khi có từ ${ranking.min_cohort} học viên, để không ai bị nhận ra.`);
    return `<section class="card">${sectionHead("pulse", "So với nhóm học viên", "Số liệu gộp, không hiện kết quả của riêng ai.")}${body}</section>`;
}

function distributionCard(ranking, levels) {
    if (!ranking.distribution.length) return "";
    const most = Math.max(...ranking.distribution.map(item => item.count), 1);
    const mine = ranking.me?.overall_level;
    return `<section class="card">${sectionHead("grid", "Phân bố trình độ", ranking.skill ? `Theo mức ${skillName(ranking.skill)}` : "Theo mức trung bình của các kỹ năng")}
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
    const overall = salary.overall ? `<span class="pay-overall" style="bottom:${px(salary.overall.value)}px"><span>${esc(salary.overall.label)}: ${number(salary.overall.value)}</span></span>` : "";
    return `<section class="card pay-card">${sectionHead("growth", "Lương tham khảo trên thị trường", `${esc(salary.role_label)} · ${esc(salary.statistic)} (${esc(salary.unit)})`)}
        <div class="pay-layout"><div class="pay-chart"><ul class="pay-cols">${columns}</ul>${overall}</div>
            <div class="pay-side">${salary.growth_percent ? `<div class="pay-growth-big"><span class="sub small">Mức tăng theo kinh nghiệm</span><strong>+${salary.growth_percent}%</strong><span class="sub small">từ ${esc(salary.bands[0].label)} lên ${esc(salary.bands[salary.bands.length - 1].label)}</span></div>` : ""}
                ${salary.missing_note ? `<p class="sub small">${esc(salary.missing_note)}</p>` : ""}<p class="sub small">${esc(salary.scope_note || "")}</p></div></div>
        <p class="meta">${icon("file")}<span>Nguồn: <a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${esc(source.label)}</a>${source.survey_period ? ` · khảo sát ${esc(source.survey_period)}` : ""}${source.sample_size ? ` · ${source.sample_size.toLocaleString("vi-VN")} người trả lời` : ""} · kiểm tra ngày ${fmtDate(source.checked_at)}</span></p></section>`;
}

const sectionHead = (name, title, note) => `<div class="rd-head">${tile(name, "brand", "tile-sm")}<div><h2>${esc(title)}</h2>${note ? `<p class="sub small">${note}</p>` : ""}</div></div>`;

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
    setView(`<div class="stack rk">${heroCard(ranking, levels)}${controls(ranking)}
        <div class="rk-grid">${boardCard(ranking, levels)}<div class="stack">${cohortCard(ranking)}${distributionCard(ranking, levels)}</div></div>
        ${salaryCard(salary)}
        <section class="card row-between"><div class="card-title">${tile("info")}<div><h2>Cách phân bậc kỹ năng</h2><p class="sub small">Tên từng mức, ý nghĩa và bài làm cần có để được ghi nhận.</p></div></div><button class="btn btn-secondary" type="button" data-act="guide">Xem cách phân bậc</button></section></div>`);
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
