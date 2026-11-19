import { api, emptyView, esc, fmtDate, fmtHours, formData, register, safeUrl, setView, skillName, statusBadge } from "../core.js";
import { icon, skillIcon, tile } from "../icons.js";

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

export async function renderResources() {
    const draw = async filters => {
        const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
        const data = await api(`/learning-resources${query ? `?${query}` : ""}`);
        const options = (values, selected, map = value => value) => values.map(value => `<option value="${esc(value)}" ${selected === value ? "selected" : ""}>${esc(map(value))}</option>`).join("");
        setView(`<div class="stack"><p class="page-intro">Chỉ hiển thị học liệu đã duyệt, đã kiểm tra link và không bị tạm ẩn. Hệ thống không tự sinh liên kết.</p>
            <form class="card" data-form="filter"><div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));align-items:end">
                <label class="field"><span>Tìm kiếm</span><input class="input" name="q" value="${esc(filters.q || "")}"></label>
                <label class="field"><span>Kỹ năng</span><select class="select" name="skill_id"><option value="">Tất cả</option>${options(data.filters.skills, filters.skill_id, skillName)}</select></label>
                <label class="field"><span>Mức</span><select class="select" name="level"><option value="">Tất cả</option>${options(["1", "2", "3"], filters.level)}</select></label>
                <label class="field"><span>Nhà cung cấp</span><select class="select" name="provider"><option value="">Tất cả</option>${options(data.filters.providers, filters.provider)}</select></label>
                <button class="btn btn-primary" type="submit">${icon("search")}<span>Lọc</span></button></div></form>
            ${data.items.length ? `<p class="sub">${data.total} học liệu</p><div class="grid grid-2">${data.items.map(card).join("")}</div>` : `<div class="card">${emptyView("Không có học liệu phù hợp", "Hãy đổi bộ lọc.")}</div>`}</div>`);
    };
    await draw({});
    register({ forms: { filter: async form => draw(formData(form)) } });
}
