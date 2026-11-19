import { api, emptyView, esc, fmtDate, fmtHours, formData, register, safeUrl, setView, skillName, statusBadge } from "../core.js";
import { icon, skillIcon, tile } from "../icons.js";
import { pageHero } from "../hero.js";

const TYPES = { COURSE: "Khóa học", LECTURE: "Bài giảng", EXERCISE: "Bài tập", OFFICIAL_DOC: "Tài liệu chính thức", ARTICLE: "Bài viết", INTERNAL_GUIDE: "Hướng dẫn nội bộ" };
// Provider logos are not ours to use; the tile shows the kind of resource instead.
const TYPE_TILES = { COURSE: ["book", "brand"], LECTURE: ["chat", "s3"], EXERCISE: ["code", "s4"], OFFICIAL_DOC: ["file", "s1"], ARTICLE: ["file", "s2"], INTERNAL_GUIDE: ["pen", "s5"] };

function card(item) {
    const [name, tone] = TYPE_TILES[item.resource_type] || ["book", "brand"];
    return `<article class="card stack-sm"><div class="card-head" style="margin-bottom:0"><div class="card-title">${tile(name, tone)}<div><h3><a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a></h3>
        <p class="sub">${esc(item.provider)} · ${esc(TYPES[item.resource_type] || item.resource_type)} · ${item.language === "vi" ? "Tiếng Việt" : "Tiếng Anh"}</p></div></div><span class="badge badge-good">${icon("check")}<span>Đã duyệt</span></span></div>
        <p class="small">${esc(item.learning_outcome)}</p>
        <div class="row">${item.topic ? `<span class="badge">${icon("book")}<span>${esc(item.topic)}</span></span>` : ""}${item.skill_ids.map(code => `<span class="badge">${skillIcon(code)}${esc(skillName(code))}</span>`).join("")}<span class="badge badge-muted">${icon("chart")}<span>Mức ${item.level}</span></span></div>
        <p class="meta">${icon("clock")}<span>≈ ${fmtHours(item.estimated_minutes / 60)} (${esc(item.duration_source)}) · ${esc(item.cost_access)}</span></p>
        <p class="sub small">${statusBadge(item.link_status)} Kiểm tra link: ${fmtDate(item.last_checked_at)}</p>
        <p class="sub small">${esc(item.source_note)}</p></article>`;
}

/* 5.57: the shared page hero counts the catalogue as it stood on the first, unfiltered load; filtering only changes
   the result line under the toolbar, which is announced to screen readers. */
function resourcesHero(overview) {
    return pageHero({
        tone: "green", icon: "book", kicker: "Học liệu", title: "Học liệu đã duyệt cho lộ trình của bạn",
        text: "Chỉ hiển thị học liệu đã duyệt, đã kiểm tra link và không bị tạm ẩn. Hệ thống không tự sinh liên kết.",
        stats: [["book", "Học liệu", overview.total, "good"], ["chart", "Kỹ năng có học liệu", overview.skills, "teal"], ["user", "Nguồn cung cấp", overview.providers, "violet"]],
    });
}

export async function renderResources() {
    let overview = null;
    const draw = async (filters, { focusResults = false } = {}) => {
        const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
        const data = await api(`/learning-resources${query ? `?${query}` : ""}`);
        overview = overview || { total: data.total, skills: data.filters.skills.length, providers: data.filters.providers.length };
        const filtered = Object.values(filters).some(Boolean);
        const options = (values, selected, map = value => value) => values.map(value => `<option value="${esc(value)}" ${selected === value ? "selected" : ""}>${esc(map(value))}</option>`).join("");
        setView(`<div class="stack">${resourcesHero(overview)}
            <form class="card res-filter" data-form="filter" role="search" aria-label="Bộ lọc học liệu"><div class="res-filter-grid">
                <label class="field res-search"><span>Tìm kiếm</span><span class="res-search-box">${icon("search")}<input class="input" name="q" value="${esc(filters.q || "")}" placeholder="Tên, nhà cung cấp hoặc kết quả học tập"></span></label>
                <label class="field"><span>Kỹ năng</span><select class="select" name="skill_id"><option value="">Tất cả</option>${options(data.filters.skills, filters.skill_id, skillName)}</select></label>
                <label class="field"><span>Mức</span><select class="select" name="level"><option value="">Tất cả</option>${options(["1", "2", "3"], filters.level)}</select></label>
                <label class="field"><span>Nhà cung cấp</span><select class="select" name="provider"><option value="">Tất cả</option>${options(data.filters.providers, filters.provider)}</select></label>
                <div class="res-filter-actions"><button class="btn btn-primary" type="submit">${icon("filter")}<span>Lọc</span></button>${filtered ? '<button class="btn btn-ghost" type="button" data-act="clear-filters">Bỏ lọc</button>' : ""}</div></div></form>
            <p class="sub res-count" id="res-count" tabindex="-1" aria-live="polite">${data.total} học liệu</p>
            ${data.items.length ? `<div class="grid grid-2">${data.items.map(card).join("")}</div>` : `<div class="card">${emptyView("Không có học liệu phù hợp", "Hãy đổi bộ lọc.")}</div>`}</div>`);
        if (focusResults) document.getElementById("res-count")?.focus({ preventScroll: true });
    };
    await draw({});
    register({
        actions: { "clear-filters": () => draw({}, { focusResults: true }) },
        forms: { filter: async form => draw(formData(form), { focusResults: true }) },
    });
}
