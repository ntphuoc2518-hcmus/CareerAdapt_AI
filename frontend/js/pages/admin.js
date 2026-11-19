/** Content administration: reviews, JD library, resources, tasks, activities, skills, analytics.
 *  5.40: grouped side navigation with counts (a single scrolling row on small screens), a hero with real
 *  workload figures, a header per section, loading and error states, search and filters on long lists,
 *  actions that follow each item's state, and a link per section (#/admin/<section>). */
import { alertBox, api, app, closeModal, confirmDialog, emptyView, esc, fmtDate, fmtDateTime, formData, LEVEL_NAMES, openModal, register, safeUrl, setView, skillName, statusBadge, toast, withBusy } from "../core.js";
import { BANK_NAMES, LEVEL_NAMES as TIER_NAMES, eventsView, questionPreview, questionText, statusPill, validationView } from "../contribution-view.js";
import { pageHero } from "../hero.js";
import { icon } from "../icons.js";

let tab = "reviews";
/** id: [label, icon, short description shown above the section] */
const SECTIONS = {
    reviews: ["Bài cần duyệt", "check", "Bài nộp mà máy và AI bất đồng, hoặc AI lỗi nhiều lần. Người duyệt quyết định mức cuối cùng."],
    contributions: ["Câu hỏi đóng góp", "pen", "Câu do chuyên gia viết, đã qua kiểm tra tự động, chờ một quản trị viên khác người viết duyệt."],
    contributors: ["Người đóng góp", "user", "Cấp hoặc thu hồi quyền viết câu hỏi cho tài khoản chuyên gia."],
    jds: ["Thư viện JD", "file", "JD thật dùng để so khớp năng lực. Kiểm tra link và rà soát định kỳ."],
    resources: ["Học liệu", "book", "Nguồn học gắn với kỹ năng. Chỉ duyệt được khi link đã kiểm tra thành công."],
    tasks: ["Đề bài", "code", "Đề thực hành và tính tương đương giữa các phiên bản đề."],
    activities: ["Học phần", "route", "Các bước của lộ trình: kỹ năng, thời lượng, tiên quyết và học liệu."],
    skills: ["Kỹ năng", "target", "Mức mục tiêu và trọng số. Trọng số 0 là kỹ năng tùy chọn, chỉ đo khi JD yêu cầu."],
    analytics: ["Câu hỏi & hiệu chỉnh", "chart", "Độ khó và độ phân loại của câu trắc nghiệm, và mẫu hiệu chỉnh chấm điểm."],
    knowledge: ["Kho kiến thức AI", "database", "Tài liệu Trợ lý được phép đọc, và mức dùng AI 7 ngày gần nhất."],
    salary: ["Lương tham khảo", "growth", "Số liệu lương có nguồn công khai, hiển thị cho học viên ở mục Xếp hạng và lương."],
};
const GROUPS = [["Kiểm duyệt", ["reviews", "contributions", "contributors"]], ["Nội dung học", ["jds", "resources", "tasks", "activities", "skills"]], ["Chất lượng & dữ liệu", ["analytics", "knowledge", "salary"]]];

const TASK_STATUS = { PUBLISHED: ["Đã phát hành", "good"], DRAFT: ["Nháp", "muted"], RETIRED: ["Ngừng dùng", "muted"] };
const EQUIVALENCE = { APPROVED: ["Đã duyệt tương đương", "good"], NOT_REVIEWED: ["Chưa duyệt tương đương", "warn"], REJECTED: ["Không tương đương", "bad"] };
const KNOWLEDGE_STATUS = { APPROVED: ["Đã duyệt", "good"], DRAFT: ["Nháp", "warn"], REJECTED: ["Từ chối", "bad"], RETIRED: ["Ngừng dùng", "muted"] };
const KNOWLEDGE_KIND = { SKILL: "Kỹ năng", JOB_PROFILE: "Vị trí công việc", SKILL_MAPPING: "Ánh xạ kỹ năng", JD_LIBRARY: "JD", RESOURCE: "Học liệu", ACTIVITY: "Học phần", MARKET: "Thị trường", GUIDE: "Hướng dẫn", DOCUMENT: "Tài liệu" };
const AI_TASK = { assistant: "Trợ lý trả lời", assistant_summary: "Tóm tắt hội thoại", grading: "Nhận xét bài chấm", embedding: "Tạo vector" };

const pill = ([label, tone]) => `<span class="badge badge-${tone}">${esc(label)}</span>`;
const today = () => new Date().toISOString().slice(0, 10);

/* --- Workload figures for the hero and the navigation counts (all read from the server) --- */
let summary = null;
async function loadSummary() {
    const settle = promise => promise.then(value => value, () => null);
    const [reviews, flags, waiting, jds, resources, knowledge] = await Promise.all([
        settle(api("/admin/reviews")), settle(api("/career-process/admin/ai-flags")), settle(api("/admin/contributions?status=SUBMITTED")),
        settle(api("/admin/jds")), settle(api("/admin/resources")), settle(api("/assistant/admin/knowledge")),
    ]);
    const count = (list, test) => (Array.isArray(list) ? list.filter(test).length : null);
    summary = {
        reviews: Array.isArray(reviews) ? reviews.length : null,
        flags: Array.isArray(flags) ? flags.length : null,
        contributions: Array.isArray(waiting) ? waiting.length : null,
        jds: count(jds, item => item.review_status !== "APPROVED" || (item.next_review_at && item.next_review_at.slice(0, 10) <= today()) || !["OK", "UNKNOWN"].includes(item.link_status)),
        resources: count(resources, item => item.status === "DRAFT" || !["OK", "UNKNOWN"].includes(item.link_status)),
        knowledge: count(knowledge, item => item.status === "DRAFT"),
    };
}

function heroView() {
    const value = key => (summary?.[key] ?? "—");
    return pageHero({
        tone: "brand", icon: "admin", kicker: "Quản trị", title: "Quản trị nội dung",
        text: "Duyệt bài, quản lý nội dung học và theo dõi chất lượng chấm điểm. Mọi thay đổi ở đây có hiệu lực với tất cả học viên.",
        stats: [["check", "Bài cần duyệt", value("reviews"), "amber"], ["pen", "Câu hỏi chờ duyệt", value("contributions"), "violet"], ["file", "JD cần rà soát", value("jds"), "teal"], ["book", "Học liệu cần xử lý", value("resources"), "rose"]],
    });
}

function navView() {
    const badge = id => {
        const n = summary?.[id];
        return n ? `<b class="adm-count" aria-label="${n} mục cần xử lý">${n}</b>` : "";
    };
    return GROUPS.map(([group, ids]) => `<div class="adm-nav-group" role="presentation"><span class="adm-nav-label">${group}</span>
        ${ids.map(id => `<button type="button" class="adm-nav-item" role="tab" id="adm-tab-${id}" aria-controls="admin-pane" aria-selected="${id === tab}" data-act="tab" data-tab="${id}">${icon(SECTIONS[id][1])}<span>${SECTIONS[id][0]}</span>${badge(id)}</button>`).join("")}</div>`).join("");
}

/* --- Search and status filters for long lists (rows carry data-search and data-status) --- */
const filters = {};
function toolbar({ placeholder, statuses = [], count }) {
    const state = filters[tab] || { query: "", status: "" };
    const chips = statuses.length ? `<div class="adm-chips" role="group" aria-label="Lọc theo trạng thái">${[["", "Tất cả"], ...statuses].map(([value, label]) => `<button type="button" class="adm-chip" data-act="adm-filter" data-value="${value}" aria-pressed="${state.status === value}">${label}</button>`).join("")}</div>` : "";
    return `<div class="adm-toolbar"><label class="adm-search">${icon("search")}<input class="input" type="search" data-adm-search placeholder="${placeholder}" value="${esc(state.query)}" aria-label="${placeholder}"></label>${chips}<span class="sub small adm-shown" data-adm-shown>${count}</span></div>`;
}
function applyFilters() {
    const pane = document.getElementById("admin-pane");
    const state = filters[tab] || { query: "", status: "" };
    const rows = [...pane.querySelectorAll("[data-search]")];
    if (!rows.length) return;
    const query = state.query.trim().toLowerCase();
    let shown = 0;
    rows.forEach(row => {
        const visible = (!query || row.dataset.search.includes(query)) && (!state.status || row.dataset.status === state.status);
        row.hidden = !visible;
        if (visible) shown += 1;
    });
    const label = pane.querySelector("[data-adm-shown]");
    if (label) label.textContent = shown === rows.length ? `${rows.length} mục` : `${shown}/${rows.length} mục`;
    const empty = pane.querySelector("[data-adm-empty]");
    if (empty) empty.hidden = shown > 0;
}
const searchText = (...parts) => esc(parts.filter(Boolean).join(" ").toLowerCase());
const noMatch = '<p class="adm-nomatch sub" data-adm-empty hidden>Không có mục nào khớp bộ lọc.</p>';

/* --- Sections --- */
async function aiFlags() {
    const flags = await api("/career-process/admin/ai-flags");
    return flags.length ? `<section class="adm-block"><h3>Bài có nhận xét AI bị loại <span class="badge badge-muted">${flags.length}</span></h3><p class="sub small">Điểm vẫn do bộ kiểm tra chấm; quy trình của học viên không bị chặn. Danh sách để theo dõi chất lượng AI.</p>
        <ul class="adm-flags">${flags.map(item => `<li><span class="adm-flag-icon">${icon("alert")}</span><div><strong>${esc(item.message)}</strong><span class="sub small"><code>${esc(item.code)}</code> · bài nộp <span class="mono">${esc(item.submission_id.slice(0, 8))}</span></span></div></li>`).join("")}</ul></section>` : "";
}

async function reviewsPane() {
    return (await aiFlags()) + await manualReviews();
}

async function manualReviews() {
    const items = await api("/admin/reviews");
    if (!items.length) return emptyView("Không có bài cần duyệt", "Bài có bất đồng giữa máy và AI, hoặc AI lỗi nhiều lần, sẽ xuất hiện ở đây.");
    return `<h3 class="adm-subhead">Chờ người duyệt <span class="badge badge-warn">${items.length}</span></h3>` + items.map(item => `<article class="adm-review"><div class="row-between"><strong>${esc(item.task_id)}</strong><span class="sub small">${fmtDateTime(item.created_at)}</span></div>${alertBox("warn", esc(item.reason))}
        ${Object.entries(item.answers || {}).map(([question, text]) => `<details class="adm-answer"><summary class="small">${esc(question)}</summary><pre class="code">${esc(text || "")}</pre></details>`).join("")}
        <form data-form="resolve" data-id="${esc(item.submission_id)}" class="stack-sm"><div class="row">${Object.values(item.per_skill_results || {}).map(skill => `<label class="field"><span>${esc(skillName(skill.skill_code))}</span><select class="select" name="skill_${esc(skill.skill_code)}">${[0, 1, 2, 3].map(level => `<option ${level === skill.level ? "selected" : ""}>${level}</option>`).join("")}</select></label>`).join("") || '<span class="sub small">Bài chưa có kết quả theo kỹ năng; hãy mở bằng API để xử lý.</span>'}</div><label class="field"><span>Nhận xét của người duyệt</span><textarea class="textarea" name="reviewer_notes" rows="2" required></textarea></label><div class="row"><button class="btn btn-primary btn-sm" type="submit">Lưu quyết định</button></div></form></article>`).join("");
}

async function jdsPane() {
    const items = await api("/admin/jds");
    const rows = items.map(item => {
        const due = item.next_review_at && item.next_review_at.slice(0, 10) <= today();
        const actions = [`<button class="btn btn-secondary btn-sm" data-act="jd-check" data-id="${esc(item.jd_id)}">${icon("link")}<span>Kiểm tra link</span></button>`];
        if (item.review_status !== "APPROVED") actions.push(`<button class="btn btn-primary btn-sm" data-act="jd-review" data-id="${esc(item.jd_id)}" data-version="${item.jd_version}" data-status="APPROVED">Duyệt</button>`);
        if (item.review_status !== "EXPIRED") actions.push(`<button class="btn btn-ghost btn-sm" data-act="jd-review" data-id="${esc(item.jd_id)}" data-version="${item.jd_version}" data-status="EXPIRED">Hết hiệu lực</button>`);
        return `<tr data-search="${searchText(item.title, item.employer, item.industry)}" data-status="${esc(item.review_status)}"><td><strong>${esc(item.title)}</strong><span class="sub small adm-line">${esc(item.employer || "")} · v${item.jd_version}</span>${item.review_note ? `<span class="small adm-line adm-warn-text">${esc(item.review_note)}</span>` : ""}</td>
            <td>${esc(LEVEL_NAMES[item.role_level] || "—")}</td><td>${statusBadge(item.review_status)}</td>
            <td>${statusBadge(item.link_status)}<span class="sub small adm-line">${item.source_url ? `<a href="${safeUrl(item.source_url)}" target="_blank" rel="noopener noreferrer">Mở nguồn</a> · ` : ""}${fmtDate(item.last_checked_at)}</span></td>
            <td>${fmtDate(item.next_review_at)}${due ? '<span class="adm-line"><span class="badge badge-warn">Đến hạn</span></span>' : ""}</td><td><div class="adm-actions">${actions.join("")}</div></td></tr>`;
    }).join("");
    return `<details class="adm-add"><summary>${icon("upload")}<span>Thêm JD vào thư viện</span></summary><form data-form="add-jd" class="stack-sm"><div class="form-grid"><label class="field"><span>URL nguồn</span><input class="input" name="source_url" type="url" required></label><label class="field"><span>Ngành</span><input class="input" name="industry"></label></div><label class="field"><span>Nội dung JD</span><textarea class="textarea" name="text" rows="4" required></textarea></label><div class="row"><button class="btn btn-primary btn-sm" type="submit">Thêm bản nháp</button></div></form></details>
        ${toolbar({ placeholder: "Tìm JD theo tên, công ty", statuses: [["APPROVED", "Đã duyệt"], ["NEEDS_REVIEW", "Cần duyệt"], ["DRAFT", "Nháp"], ["EXPIRED", "Hết hiệu lực"]], count: `${items.length} mục` })}
        <div class="table-wrap adm-table"><table><thead><tr><th>JD</th><th>Cấp độ</th><th>Duyệt</th><th>Link nguồn</th><th>Rà soát tiếp</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${noMatch}`;
}

async function resourcesPane() {
    const items = await api("/admin/resources");
    const rows = items.map(item => {
        const actions = [`<button class="btn btn-secondary btn-sm" data-act="resource-check" data-id="${esc(item.resource_id)}">${icon("link")}<span>Kiểm tra link</span></button>`];
        if (item.status !== "APPROVED") actions.push(`<button class="btn btn-primary btn-sm" data-act="resource-decide" data-id="${esc(item.resource_id)}" data-decision="APPROVED">Duyệt</button>`);
        if (item.status !== "HIDDEN") actions.push(`<button class="btn btn-ghost btn-sm" data-act="resource-decide" data-id="${esc(item.resource_id)}" data-decision="HIDDEN">Tạm ẩn</button>`);
        return `<tr data-search="${searchText(item.title, item.provider, ...item.skill_ids.map(skillName))}" data-status="${esc(item.status)}"><td><a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a><span class="sub small adm-line">${esc(item.provider)} · v${item.resource_version}</span></td>
            <td class="small">${esc(item.skill_ids.map(skillName).join(", "))}</td><td>${statusBadge(item.status)}</td><td>${statusBadge(item.link_status)}<span class="sub small adm-line">${fmtDate(item.last_checked_at)}</span></td><td><div class="adm-actions">${actions.join("")}</div></td></tr>`;
    }).join("");
    return `<div class="adm-pane-tools">${toolbar({ placeholder: "Tìm học liệu theo tên, nguồn, kỹ năng", statuses: [["APPROVED", "Đã duyệt"], ["DRAFT", "Nháp"], ["HIDDEN", "Tạm ẩn"]], count: `${items.length} mục` })}<button class="btn btn-primary btn-sm" data-act="resource-new">${icon("book")}<span>Thêm học liệu</span></button></div>
        <div class="table-wrap adm-table"><table><thead><tr><th>Học liệu</th><th>Kỹ năng</th><th>Trạng thái</th><th>Link</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${noMatch}`;
}

async function tasksPane() {
    const items = await api("/admin/tasks");
    return `<div class="table-wrap adm-table"><table><thead><tr><th>Đề</th><th class="num">Phiên bản</th><th>Trạng thái</th><th>Tương đương</th><th></th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(item.task_id)}</strong><span class="small adm-line">${esc(item.title)}</span></td><td class="num">${item.content_version}</td><td>${pill(TASK_STATUS[item.status] || [item.status, "muted"])}</td>
        <td>${item.is_reassessment_variant ? pill(EQUIVALENCE[item.comparability_status] || [item.comparability_status, "muted"]) : '<span class="sub small">Đề gốc</span>'}</td>
        <td>${item.is_reassessment_variant ? `<button class="btn btn-secondary btn-sm" data-act="task-equivalence" data-id="${esc(item.task_id)}" data-status="${item.comparability_status === "APPROVED" ? "NOT_REVIEWED" : "APPROVED"}">${item.comparability_status === "APPROVED" ? "Hủy duyệt tương đương" : "Duyệt tương đương"}</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
        <p class="sub small adm-note">${icon("info")}<span>Chỉ duyệt tương đương sau khi kiểm tra kỹ năng, độ khó và rubric. Đề chỉ phát hành được khi đã có blueprint.</span></p>`;
}

async function activitiesPane() {
    const [items, resources] = await Promise.all([api("/admin/activities"), api("/admin/resources")]);
    app.adminActivities = items;
    app.adminResources = resources;
    const missing = items.filter(item => !item.resource_ids?.length).length;
    return `<div class="adm-pane-tools"><span class="sub small">Đồ thị tiên quyết được kiểm tra chu trình khi lưu.${missing ? ` <span class="badge badge-warn">${missing} học phần thiếu học liệu</span>` : ""}</span><button class="btn btn-primary btn-sm" data-act="activity-edit">${icon("pen")}<span>Thêm học phần</span></button></div>
        <div class="table-wrap adm-table"><table><thead><tr><th>Học phần</th><th>Kỹ năng</th><th class="num">Giờ</th><th>Tiên quyết</th><th class="num">Học liệu</th><th></th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(item.activity_id)}</strong><span class="small adm-line">${esc(item.title)}</span></td><td>${esc(skillName(item.target_skill))}<span class="sub small adm-line">Mức ${item.target_level}</span></td><td class="num">${item.estimated_hours}</td><td class="small">${esc((item.prerequisites || []).join(", ") || "—")}</td><td class="num">${item.resource_ids?.length ? item.resource_ids.length : '<span class="badge badge-warn">Thiếu</span>'}</td><td><button class="btn btn-secondary btn-sm" data-act="activity-edit" data-id="${esc(item.activity_id)}">Sửa</button></td></tr>`).join("")}</tbody></table></div>`;
}

async function skillsPane() {
    const data = await api("/admin/skills");
    app.adminSkills = data.skills;
    const total = data.skills.reduce((sum, item) => sum + Number(item.weight || 0), 0);
    return `${data.is_weight_valid ? `<p class="adm-note sub small">${icon("check")}<span>Tổng trọng số các kỹ năng bắt buộc là ${Math.round(total * 100)}%.</span></p>` : alertBox("warn", `Tổng trọng số hiện là ${data.total_weight}, cần bằng 1.`)}
        <div class="table-wrap adm-table"><table><thead><tr><th>Kỹ năng</th><th class="num">Mức mục tiêu</th><th>Trọng số</th><th>Loại</th><th></th></tr></thead><tbody>${data.skills.map(item => `<tr><td><strong>${esc(item.skill_name)}</strong><span class="sub small adm-line mono">${esc(item.skill_code)}</span></td><td class="num">${item.target_level}</td>
            <td><div class="adm-weight"><span class="adm-weight-bar"><i style="width:${Math.round(Number(item.weight) * 100)}%"></i></span><b>${Math.round(Number(item.weight) * 100)}%</b></div></td>
            <td>${Number(item.weight) === 0 ? '<span class="badge badge-muted">Tùy chọn</span>' : item.is_core ? '<span class="badge badge-good">Cốt lõi</span>' : '<span class="badge badge-info">Bổ trợ</span>'}</td><td><button class="btn btn-secondary btn-sm" data-act="skill-edit" data-id="${esc(item.skill_code)}">Sửa</button></td></tr>`).join("")}</tbody></table></div>`;
}

async function analyticsPane() {
    const [analysis, calibration] = await Promise.all([api("/admin/tests/item-analysis"), api("/admin/calibration-samples")]);
    const items = Array.isArray(analysis.items) ? analysis.items : Array.isArray(analysis) ? analysis : [];
    const report = calibration.report;
    const number = value => (value === null || value === undefined ? "—" : value);
    const rows = items.map(item => `<tr data-search="${searchText(item.item_id, item.topic, skillName(item.skill_code))}" data-status="${esc(item.skill_code)}"><td><strong class="mono">${esc(item.item_id)}</strong><span class="sub small adm-line">${esc(item.topic || "")}</span></td><td>${esc(skillName(item.skill_code))}<span class="sub small adm-line">Mức ${item.level ?? "—"}</span></td>
        <td class="num">${number(item.exposures ?? item.responses ?? item.attempts)}</td><td class="num">${number(item.p_value ?? item.difficulty)}</td><td class="num">${number(item.discrimination ?? item.point_biserial)}</td>
        <td>${(item.flags || []).map(flag => `<span class="badge ${flag === "Chưa đủ dữ liệu" ? "badge-muted" : "badge-warn"}">${esc(flag)}</span>`).join(" ") || '<span class="badge badge-good">Ổn</span>'}</td></tr>`).join("");
    const skills = [...new Set(items.map(item => item.skill_code))].map(code => [code, skillName(code)]);
    return `<section class="adm-block"><h3>Hiệu chỉnh chấm điểm</h3><p class="sub small">Mục tiêu sai lệch tuyệt đối trung bình ≤ ${calibration.target_mae} mức. Tập giữ lại được báo riêng.</p>
        <div class="adm-stats">${Object.entries(report).map(([split, value]) => `<div class="adm-stat"><span>${split === "HOLDOUT" ? "Tập giữ lại" : "Tập hiệu chỉnh"}</span><b>${value.mae ?? "—"}</b><small>${value.count} mẫu · sai lệch TB</small></div>`).join("")}</div>
        <details class="adm-add"><summary>${icon("upload")}<span>Thêm mẫu hiệu chỉnh ẩn danh</span></summary>
        <form data-form="calibration" class="form-grid adm-calibration"><label class="field"><span>Mã bài nộp</span><input class="input" name="submission_id" required></label><label class="field"><span>Kỹ năng</span><select class="select" name="skill_code">${app.skillCodes.map(code => `<option value="${esc(code)}">${esc(skillName(code))}</option>`).join("")}</select></label><label class="field"><span>Mức tham chiếu của người chấm</span><select class="select" name="reference_level">${[0, 1, 2, 3].map(level => `<option>${level}</option>`).join("")}</select></label><label class="field"><span>Tập</span><select class="select" name="split"><option value="CALIBRATION">Hiệu chỉnh</option><option value="HOLDOUT">Giữ lại</option></select></label><label class="field"><span>Cơ sở được phép sử dụng</span><input class="input" name="consent_basis" required minlength="3"></label><div class="field adm-calibration-submit"><button class="btn btn-primary" type="submit">Thêm mẫu ẩn danh</button></div></form></details></section>
        <section class="adm-block"><div class="row-between adm-block-head"><div><h3>Phân tích câu hỏi</h3><p class="sub small">${analysis.attempts_analyzed ?? 0} bài kiểm tra đã nộp. Cần từ 5 lượt làm mỗi câu để đánh giá độ khó và độ phân loại.</p></div><a class="btn btn-secondary btn-sm" href="/api/v1/admin/tests/results.csv">${icon("file")}<span>Tải kết quả CSV</span></a></div>
        ${items.length ? `${toolbar({ placeholder: "Tìm câu theo mã, chủ đề", statuses: skills, count: `${items.length} mục` })}<div class="table-wrap adm-table"><table><thead><tr><th>Câu</th><th>Kỹ năng</th><th class="num">Lượt làm</th><th class="num">Độ khó p</th><th class="num">Phân loại</th><th>Đánh giá</th></tr></thead><tbody>${rows}</tbody></table></div>${noMatch}` : emptyView("Chưa có dữ liệu", "Cần có bài kiểm tra đã nộp để phân tích câu hỏi.")}</section>`;
}

async function knowledgePane() {
    const [items, usage] = await Promise.all([api("/assistant/admin/knowledge"), api("/assistant/admin/usage")]);
    const usageRows = usage.rows.length ? `<div class="table-wrap adm-table"><table><thead><tr><th>Nghiệp vụ</th><th>Kết quả</th><th class="num">Lượt</th><th class="num">Token vào</th><th class="num">Token ra</th><th class="num">Độ trễ TB (ms)</th></tr></thead><tbody>${usage.rows.map(row => `<tr><td>${esc(AI_TASK[row.task] || row.task)}</td><td>${esc(row.status)}${row.error ? ` · <span class="sub small">${esc(row.error)}</span>` : ""}</td><td class="num">${row.calls}</td><td class="num">${row.input_tokens ?? 0}</td><td class="num">${row.output_tokens ?? 0}</td><td class="num">${Math.round(row.avg_latency_ms ?? 0)}</td></tr>`).join("")}</tbody></table></div>` : emptyView("Chưa có lượt dùng AI", "Số liệu 7 ngày gần nhất sẽ xuất hiện ở đây.");
    const missing = items.reduce((sum, item) => sum + Math.max(0, (item.chunks || 0) - (item.embedded || 0)), 0);
    const rows = items.map(item => `<tr data-search="${searchText(item.title, KNOWLEDGE_KIND[item.kind] || item.kind)}" data-status="${esc(item.status)}"><td><strong>${esc(item.title)}</strong><span class="sub small adm-line">v${item.version}${item.reviewer_id ? ` · duyệt bởi ${esc(item.reviewer_id === "seed-import" ? "dữ liệu gốc" : "quản trị viên")}` : ""}</span></td><td class="small">${esc(KNOWLEDGE_KIND[item.kind] || item.kind)}</td><td>${pill(KNOWLEDGE_STATUS[item.status] || [item.status, "muted"])}</td><td class="num">${item.chunks}</td><td class="num">${item.embedded}</td>
        <td><div class="adm-actions">${item.status === "APPROVED" ? `<button class="btn btn-ghost btn-sm" data-act="knowledge-decide" data-id="${esc(item.document_id)}" data-status="RETIRED">Ngừng dùng</button>` : `<button class="btn btn-primary btn-sm" data-act="knowledge-decide" data-id="${esc(item.document_id)}" data-status="APPROVED">Duyệt</button>`}</div></td></tr>`).join("");
    return `<details class="adm-add"><summary>${icon("upload")}<span>Thêm tài liệu</span></summary><form data-form="add-knowledge" class="stack-sm"><p class="sub small">Tài liệu mới ở trạng thái nháp, chỉ trợ lý đọc được sau khi duyệt. Nội dung ngân hàng đề bị từ chối.</p><div class="form-grid"><label class="field"><span>Tiêu đề</span><input class="input" name="title" required minlength="3" maxlength="200"></label><label class="field"><span>URL nguồn</span><input class="input" name="source_url" type="url"></label></div><label class="field"><span>Nội dung</span><textarea class="textarea" name="body" rows="5" required minlength="20"></textarea></label><div class="row"><button class="btn btn-primary btn-sm" type="submit">Thêm bản nháp</button></div></form></details>
        <div class="adm-pane-tools">${toolbar({ placeholder: "Tìm tài liệu", statuses: [["APPROVED", "Đã duyệt"], ["DRAFT", "Nháp"], ["RETIRED", "Ngừng dùng"]], count: `${items.length} mục` })}<button class="btn btn-secondary btn-sm" data-act="knowledge-embed" ${missing ? "" : "disabled"} title="${missing ? `${missing} đoạn chưa có vector` : "Mọi đoạn đã có vector"}">${icon("refresh")}<span>Tạo vector còn thiếu${missing ? ` (${missing})` : ""}</span></button></div>
        <div class="table-wrap adm-table"><table><thead><tr><th>Tài liệu</th><th>Loại</th><th>Trạng thái</th><th class="num">Đoạn</th><th class="num">Có vector</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${noMatch}
        <section class="adm-block"><h3>Mức dùng AI 7 ngày <span class="badge badge-muted">${usage.total_tokens} token</span></h3>${usageRows}</section>`;
}

const SALARY_ROWS = 4;

/** Salary reference shown to learners: only figures with a public source are accepted by the server. */
async function salaryPane() {
    const salary = (await api("/career-process/admin/salary-reference")).salary || { bands: [], source: {} };
    const field = (name, label, value, extra = "") => `<label class="field"><span>${label}</span><input class="input" name="${name}" value="${esc(value ?? "")}" ${extra}></label>`;
    const bands = Array.from({ length: SALARY_ROWS }, (unused, index) => salary.bands[index] || {});
    return `<form data-form="salary" class="stack salary-form"><p class="adm-note sub small">${icon("info")}<span>Chỉ nhập số liệu lấy từ báo cáo công khai và ghi đúng nguồn.</span></p>
        <fieldset class="adm-fieldset"><legend>Vị trí và loại số liệu</legend><div class="form-grid">${field("role_label", "Nhóm vị trí", salary.role_label, 'required maxlength="160"')}${field("statistic", "Loại số liệu", salary.statistic, 'required maxlength="60"')}${field("unit", "Đơn vị", salary.unit, 'required maxlength="40"')}</div></fieldset>
        <fieldset class="adm-fieldset"><legend>Các nhóm kinh nghiệm, từ thấp đến cao</legend>
        ${bands.map((band, index) => `<div class="band-row">${field(`band_label_${index}`, `Nhóm ${index + 1}`, band.label, 'maxlength="80"')}${field(`band_value_${index}`, "Giá trị", band.value, 'type="number" step="0.01" min="0" max="1000"')}</div>`).join("")}
        <div class="band-row">${field("overall_label", "Dòng tổng (không bắt buộc)", salary.overall?.label, 'maxlength="80"')}${field("overall_value", "Giá trị", salary.overall?.value, 'type="number" step="0.01" min="0" max="1000"')}</div>
        ${field("missing_note", "Ghi chú số liệu còn thiếu", salary.missing_note, 'maxlength="300"')}${field("scope_note", "Ghi chú phạm vi", salary.scope_note, 'maxlength="400"')}</fieldset>
        <fieldset class="adm-fieldset"><legend>Nguồn</legend>
        <div class="form-grid">${field("source_label", "Tên báo cáo", salary.source.label, 'required maxlength="200"')}${field("source_url", "Đường dẫn", salary.source.url, 'type="url" required maxlength="500"')}${field("survey_period", "Thời gian khảo sát", salary.source.survey_period, 'maxlength="120"')}${field("sample_size", "Số người trả lời", salary.source.sample_size, 'type="number" min="1"')}${field("checked_at", "Ngày kiểm tra", salary.source.checked_at, 'type="date" required')}</div></fieldset>
        <div><button class="btn btn-primary" type="submit">Lưu lương tham khảo</button></div></form>`;
}

/* --- Questions written by experts (5.35) --- */
let contributionFilter = "SUBMITTED";
const CONTRIBUTION_FILTERS = [["SUBMITTED", "Chờ duyệt"], ["CHANGES_REQUESTED", "Đã yêu cầu sửa"], ["APPROVED", "Đã xuất bản"], ["REJECTED", "Không duyệt"], ["RETIRED", "Ngừng dùng"]];

async function contributionsPane() {
    const items = await api(`/admin/contributions?status=${contributionFilter}`);
    const chips = CONTRIBUTION_FILTERS.map(([value, label]) => `<button type="button" class="adm-chip" data-act="ct-filter" data-status="${value}" aria-pressed="${value === contributionFilter}">${label}</button>`).join("");
    const rows = items.map(item => `<li class="ct-row"><div class="ct-row-main"><div class="ct-meta">${statusPill(item.status)}<span class="ct-pill is-brand">${BANK_NAMES[item.bank]}</span><span class="ct-pill is-muted">${esc(skillName(item.skill_code))} · ${TIER_NAMES[item.level]}</span>${item.revision > 1 ? `<span class="ct-pill is-muted">Lần gửi ${item.revision}</span>` : ""}</div>
            <strong>${esc(item.payload.topic || "")}</strong><span class="sub small">${esc(questionText(item).slice(0, 160))}</span><span class="sub small">Người viết: ${esc(item.author_name || "đã xóa tài khoản")} · ${fmtDateTime(item.submitted_at || item.updated_at)}</span></div>
            <button class="btn btn-secondary btn-sm" data-act="ct-open" data-id="${esc(item.contribution_id)}">Xem và duyệt</button></li>`).join("");
    return `<p class="adm-note sub small">${icon("info")}<span>Câu đã qua kiểm tra tự động (đáp án mẫu đạt 100 trên bốn bộ dữ liệu, bài sai dưới 40 điểm, không trùng). Người duyệt đọc nội dung, đúng chuyên môn và cách hỏi. Không ai tự duyệt câu của mình.</span></p>
        <div class="adm-chips" role="group" aria-label="Lọc theo trạng thái">${chips}</div>${items.length ? `<ul class="ct-list">${rows}</ul>` : emptyView("Không có câu nào", "Câu ở trạng thái này sẽ hiện tại đây.")}`;
}

function contributionModal(item) {
    const deciding = item.status === "SUBMITTED";
    const decision = deciding ? `<form class="stack-sm ct-decide" data-form="ct-decide" data-id="${esc(item.contribution_id)}"><label class="field"><span>Nhận xét gửi người viết (bắt buộc khi yêu cầu sửa hoặc không duyệt)</span><textarea class="textarea" name="note" rows="3" maxlength="2000"></textarea></label>
        <fieldset class="ct-checklist"><legend>Người duyệt xác nhận trước khi xuất bản</legend><p class="sub small">Máy chỉ chứng minh đáp án mẫu qua được tiêu chí chấm. Những điểm dưới đây chỉ người đọc mới đánh giá được; chỉ cần khi bấm duyệt.</p>
            ${(item.review_items || []).map(check => `<label class="ct-check-item"><input type="checkbox" name="check_${esc(check.key)}"><span>${esc(check.label)}</span></label>`).join("")}</fieldset>
        <div class="row"><button class="btn btn-primary" type="submit" name="decision" value="APPROVE">${"Duyệt và xuất bản"}</button><button class="btn btn-secondary" type="submit" name="decision" value="REQUEST_CHANGES">Yêu cầu chỉnh sửa</button><button class="btn btn-danger" type="submit" name="decision" value="REJECT">Không duyệt</button></div></form>` : "";
    const confirmed = item.review_checklist ? `<p class="sub small">${icon("check")} Người duyệt đã xác nhận ${item.review_checklist.items.length} mục kiểm tra lúc ${fmtDateTime(item.review_checklist.confirmed_at)}.</p>` : "";
    const retire = item.status === "APPROVED" ? `${confirmed}<div class="row"><span class="sub small">Đã xuất bản thành ${esc(item.published_item_id)}.</span><button class="btn btn-secondary btn-sm" data-act="ct-retire" data-id="${esc(item.contribution_id)}">Ngừng dùng câu này</button></div>` : "";
    openModal(`<div class="modal-head"><h2>Câu hỏi đóng góp</h2><button class="icon-btn" type="button" data-close-modal aria-label="Đóng">✕</button></div>
        <div class="ct-review">${questionPreview(item)}${item.review_note ? alertBox("info", `<strong>Nhận xét trước:</strong> ${esc(item.review_note)}`) : ""}
            <h3>Kiểm tra tự động</h3>${validationView(item.validation)}<h3>Lịch sử</h3>${eventsView(item.events)}${decision}${retire}</div>`, { wide: true });
}

async function contributorsPane() {
    const people = await api("/admin/contributors");
    const rows = people.map(person => `<tr><td><strong>${esc(person.full_name || "")}</strong><span class="sub small ct-block">${esc(person.email || person.user_id)}${person.note ? ` · ${esc(person.note)}` : ""}</span></td><td class="num">${person.total}</td><td class="num">${person.waiting}</td><td class="num">${person.approved}</td>
        <td class="sub small">${esc(person.granted_by)} · ${fmtDate(person.granted_at)}</td><td><button class="btn btn-ghost btn-sm" data-act="contributor-revoke" data-id="${esc(person.user_id)}">Thu hồi</button></td></tr>`).join("");
    return `<form class="adm-grant ct-grant" data-form="contributor-grant"><label class="field"><span>Email tài khoản chuyên gia</span><input class="input" type="email" name="email" required maxlength="254"></label>
            <label class="field"><span>Ghi chú (chuyên môn, đơn vị)</span><input class="input" name="note" maxlength="300"></label><button class="btn btn-primary" type="submit">Cấp quyền đóng góp</button></form>
        <p class="adm-note sub small">${icon("info")}<span>Người được cấp quyền viết được câu hỏi và gửi duyệt; họ không duyệt được câu của chính mình, và câu của họ không bao giờ xuất hiện trong bài thi của họ.</span></p>
        ${people.length ? `<div class="table-wrap adm-table"><table><thead><tr><th>Người đóng góp</th><th class="num">Tổng câu</th><th class="num">Chờ duyệt</th><th class="num">Đã xuất bản</th><th>Cấp bởi</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : emptyView("Chưa có người đóng góp", "Cấp quyền bằng email tài khoản của chuyên gia.")}`;
}

const PANES = { salary: salaryPane, reviews: reviewsPane, jds: jdsPane, resources: resourcesPane, tasks: tasksPane, activities: activitiesPane, skills: skillsPane, analytics: analyticsPane, contributions: contributionsPane, contributors: contributorsPane, knowledge: knowledgePane };

/* --- Drawing --- */
let drawToken = 0;
function drawChrome() {
    const hero = document.getElementById("adm-hero");
    if (hero) hero.innerHTML = heroView();
    const nav = document.getElementById("adm-nav");
    if (!nav) return;
    // 5.57.1: the counts arrive after the menu is drawn and the menu is drawn again; keyboard focus stays on the
    // same section instead of falling back to the page.
    const focused = nav.contains(document.activeElement) ? document.activeElement.dataset.tab : null;
    nav.innerHTML = navView();
    if (focused) nav.querySelector(`.adm-nav-item[data-tab="${focused}"]`)?.focus({ preventScroll: true });
}

async function drawPane() {
    const pane = document.getElementById("admin-pane");
    const token = ++drawToken;
    const [label, name, about] = SECTIONS[tab];
    document.querySelectorAll(".adm-nav-item").forEach(button => button.setAttribute("aria-selected", String(button.dataset.tab === tab)));
    document.querySelector(".adm-nav-item[aria-selected='true']")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    pane.setAttribute("aria-labelledby", `adm-tab-${tab}`);
    pane.setAttribute("aria-busy", "true");
    const head = `<header class="adm-pane-head"><span class="adm-pane-icon">${icon(name)}</span><div><h2>${label}</h2><p class="sub small">${about}</p></div></header>`;
    pane.innerHTML = `${head}<div class="adm-skeleton" aria-hidden="true"><i></i><i></i><i></i><i></i></div>`;
    try {
        const body = await PANES[tab]();
        if (token !== drawToken) return;
        pane.innerHTML = `${head}<div class="adm-pane-body">${body}</div>`;
        applyFilters();
    } catch (error) {
        if (token !== drawToken) return;
        pane.innerHTML = `${head}${alertBox("bad", `Không tải được mục này: ${esc(error.message || "lỗi không xác định")}`)}<button class="btn btn-secondary btn-sm" data-act="pane-retry">${icon("refresh")}<span>Thử lại</span></button>`;
    } finally {
        if (token === drawToken) pane.removeAttribute("aria-busy");
    }
}

function activityModal(activity) {
    const item = activity || { activity_id: "", title: "", target_skill: "SQL", target_level: 2, estimated_hours: 2, prerequisites: [], learning_outcome: "", resource_ids: [], splittable: true, assessment_task_id: "" };
    openModal(`<h2>${activity ? "Sửa" : "Thêm"} học phần</h2><form data-form="activity" data-existing="${activity ? esc(item.activity_id) : ""}" class="stack">
        <div class="form-grid"><label class="field"><span>Mã</span><input class="input" name="activity_id" required value="${esc(item.activity_id)}" ${activity ? "readonly" : ""}></label><label class="field"><span>Tên</span><input class="input" name="title" required value="${esc(item.title)}"></label>
        <label class="field"><span>Kỹ năng</span><select class="select" name="target_skill">${app.skillCodes.map(code => `<option value="${esc(code)}" ${code === item.target_skill ? "selected" : ""}>${esc(skillName(code))}</option>`).join("")}</select></label><label class="field"><span>Mức</span><select class="select" name="target_level">${[1, 2, 3].map(level => `<option ${level === item.target_level ? "selected" : ""}>${level}</option>`).join("")}</select></label>
        <label class="field"><span>Giờ dự kiến</span><input class="input" type="number" name="estimated_hours" min="0.5" step="0.5" required value="${item.estimated_hours}"></label><label class="field"><span>Bài đánh giá</span><input class="input" name="assessment_task_id" value="${esc(item.assessment_task_id || "")}"></label></div>
        <label class="field"><span>Tiên quyết (mã, cách nhau bởi dấu phẩy)</span><input class="input" name="prerequisites" value="${esc((item.prerequisites || []).join(", "))}"></label>
        <label class="field"><span>Đầu ra</span><input class="input" name="learning_outcome" value="${esc(item.learning_outcome || "")}"></label>
        <fieldset class="stack-sm adm-resource-picks"><legend class="label">Học liệu</legend>${app.adminResources.map(resource => `<label class="check small"><input type="checkbox" name="resource_ids" value="${esc(resource.resource_id)}" ${(item.resource_ids || []).includes(resource.resource_id) ? "checked" : ""}> ${esc(resource.title)} ${statusBadge(resource.status)}</label>`).join("")}</fieldset>
        <label class="check"><input type="checkbox" name="splittable" ${item.splittable ? "checked" : ""}> Cho phép chia nhỏ qua nhiều tuần</label>
        <div class="modal-actions">${activity ? `<button class="btn btn-danger" type="button" data-act="activity-delete" data-id="${esc(item.activity_id)}">Xóa</button>` : ""}<button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-primary" type="submit">Lưu</button></div></form>`, { wide: true });
}

function resourceModal() {
    openModal(`<h2>Thêm học liệu</h2><form data-form="resource" class="stack"><p class="sub small">Học liệu mới ở trạng thái nháp. Cần kiểm tra link thành công mới được duyệt.</p><div class="form-grid"><label class="field"><span>Tên</span><input class="input" name="title" required minlength="3"></label><label class="field"><span>Nhà cung cấp</span><input class="input" name="provider" required minlength="2"></label>
        <label class="field"><span>Loại</span><select class="select" name="resource_type">${[["COURSE", "Khóa học"], ["LECTURE", "Bài giảng"], ["EXERCISE", "Bài tập"], ["OFFICIAL_DOC", "Tài liệu chính thức"], ["ARTICLE", "Bài viết"]].map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label><label class="field"><span>URL</span><input class="input" name="url" type="url" required></label>
        <label class="field"><span>Kỹ năng</span><select class="select" name="skill">${app.skillCodes.map(code => `<option value="${esc(code)}">${esc(skillName(code))}</option>`).join("")}</select></label><label class="field"><span>Mức</span><select class="select" name="level"><option>1</option><option>2</option><option>3</option></select></label>
        <label class="field"><span>Thời lượng (phút)</span><input class="input" type="number" name="estimated_minutes" min="1" required></label><label class="field"><span>Chi phí / truy cập</span><input class="input" name="cost_access"></label></div>
        <label class="field"><span>Đầu ra học tập</span><input class="input" name="learning_outcome" required minlength="5"></label><label class="field"><span>Cơ sở chọn nguồn</span><input class="input" name="source_note"></label>
        <div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-primary" type="submit">Lưu nháp</button></div></form>`, { wide: true });
}

function skillModal(skill) {
    // Weight 0 marks an optional skill (5.14), which the server accepts, so the form must accept it too.
    openModal(`<h2>Sửa kỹ năng</h2><form data-form="skill" data-id="${esc(skill.skill_code)}" class="stack"><label class="field"><span>Tên</span><input class="input" name="skill_name" required value="${esc(skill.skill_name)}"></label><div class="form-grid"><label class="field"><span>Mức mục tiêu</span><select class="select" name="target_level">${[1, 2, 3].map(level => `<option ${level === skill.target_level ? "selected" : ""}>${level}</option>`).join("")}</select></label><label class="field"><span>Trọng số (0 đến 1)</span><input class="input" type="number" name="weight" min="0" max="1" step="0.01" required value="${skill.weight}"><span class="sub small">0 là kỹ năng tùy chọn: không tính vào tổng, chỉ đo khi JD yêu cầu.</span></label></div><label class="check"><input type="checkbox" name="is_core" ${skill.is_core ? "checked" : ""}> Kỹ năng cốt lõi</label><div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-primary" type="submit">Lưu</button></div></form>`);
}

export async function renderAdmin(section = "") {
    if (app.user.role !== "admin") { setView(`<div class="card">${emptyView("Không có quyền truy cập", "Trang này dành cho quản trị viên.")}</div>`); return; }
    if (SECTIONS[section]) tab = section;
    const skills = await api("/admin/skills");
    app.skillCodes = skills.skills.map(item => item.skill_code);
    setView(`<div class="stack adm-page"><div id="adm-hero">${heroView()}</div>
        <div class="adm-shell"><nav class="adm-nav card" id="adm-nav" role="tablist" aria-label="Các mục quản trị">${navView()}</nav>
        <section class="card adm-pane" id="admin-pane" role="tabpanel"></section></div></div>`);
    loadSummary().then(drawChrome).catch(() => {});
    const pane = document.getElementById("admin-pane");
    // Search: an input listener (not data-act), so typing never goes through the page's click handler.
    pane.addEventListener("input", event => {
        if (!event.target.matches("[data-adm-search]")) return;
        filters[tab] = { ...(filters[tab] || { status: "" }), query: event.target.value };
        applyFilters();
    });
    const refresh = async message => {
        closeModal();
        if (message) toast(message, "good");
        await drawPane();
        loadSummary().then(drawChrome).catch(() => {});
    };
    const showTab = async id => {
        if (!SECTIONS[id]) return;
        tab = id;
        history.replaceState(null, "", `#/admin/${id}`);
        await drawPane();
    };
    register({
        actions: {
            tab: element => showTab(element.dataset.tab),
            "pane-retry": () => drawPane(),
            "adm-filter": element => {
                filters[tab] = { ...(filters[tab] || { query: "" }), status: element.dataset.value };
                element.parentElement.querySelectorAll(".adm-chip").forEach(chip => chip.setAttribute("aria-pressed", String(chip === element)));
                applyFilters();
            },
            "ct-filter": async element => { contributionFilter = element.dataset.status; await drawPane(); },
            "ct-open": element => withBusy(element, async () => contributionModal(await api(`/admin/contributions/${element.dataset.id}`))),
            "ct-retire": async element => {
                if (!(await confirmDialog("Ngừng dùng câu này?", "Câu sẽ không còn được chọn cho bài thi mới. Bài đã làm vẫn giữ nguyên câu và điểm.", { confirmLabel: "Ngừng dùng", danger: true }))) return;
                await withBusy(element, async () => { await api(`/admin/contributions/${element.dataset.id}/retire`, { method: "POST", body: { note: "" } }); await refresh("Đã ngừng dùng câu hỏi."); });
            },
            "contributor-revoke": async element => {
                if (!(await confirmDialog("Thu hồi quyền đóng góp?", "Người này không viết hay gửi câu mới được nữa. Câu đã xuất bản vẫn giữ trong ngân hàng.", { confirmLabel: "Thu hồi", danger: true }))) return;
                await withBusy(element, async () => { await api(`/admin/contributors/${element.dataset.id}`, { method: "DELETE" }); await refresh("Đã thu hồi quyền."); });
            },
            "jd-check": element => withBusy(element, async () => { const result = await api(`/admin/jds/${element.dataset.id}/check-link`, { method: "POST" }); await refresh(result.detail); }),
            "jd-review": element => withBusy(element, async () => { await api(`/admin/jds/${element.dataset.id}/versions/${element.dataset.version}/review`, { method: "POST", body: { review_status: element.dataset.status } }); await refresh("Đã cập nhật trạng thái JD."); }),
            "resource-new": () => resourceModal(),
            "resource-check": element => withBusy(element, async () => { const result = await api(`/admin/resources/${element.dataset.id}/check-link`, { method: "POST" }); await refresh(result.detail); }),
            "resource-decide": element => withBusy(element, async () => { await api(`/admin/resources/${element.dataset.id}/review?decision=${element.dataset.decision}`, { method: "POST" }); await refresh("Đã cập nhật học liệu."); }),
            "task-equivalence": element => withBusy(element, async () => {
                const task = (await api("/admin/tasks")).find(item => item.task_id === element.dataset.id);
                await api(`/admin/tasks/${task.task_id}`, { method: "PUT", body: { ...task, comparability_status: element.dataset.status } });
                await refresh("Đã cập nhật tính tương đương.");
            }),
            "activity-edit": element => activityModal(app.adminActivities.find(item => item.activity_id === element.dataset.id)),
            "activity-delete": async element => {
                if (await confirmDialog("Xóa học phần?", "Học phần sẽ bị gỡ khỏi các tiên quyết khác.", { confirmLabel: "Xóa", danger: true })) {
                    await withBusy(null, async () => { await api(`/admin/activities/${element.dataset.id}`, { method: "DELETE" }); await refresh("Đã xóa học phần."); });
                }
            },
            "skill-edit": element => skillModal(app.adminSkills.find(item => item.skill_code === element.dataset.id)),
            "knowledge-decide": element => withBusy(element, async () => { await api(`/assistant/admin/knowledge/${element.dataset.id}/decision`, { method: "POST", body: { status: element.dataset.status } }); await refresh("Đã cập nhật tài liệu."); }),
            "knowledge-embed": element => withBusy(element, async () => { const result = await api("/assistant/admin/knowledge/embed", { method: "POST" }); await refresh(`Đã tạo vector cho ${result.embedded} đoạn.`); }),
        },
        forms: {
            "ct-decide": async (form, event) => {
                // Never default to approving: the pressed button must say what to do.
                const decision = event?.submitter?.value;
                if (!["APPROVE", "REQUEST_CHANGES", "REJECT"].includes(decision)) return;
                const checklist = Object.fromEntries([...form.querySelectorAll('input[type="checkbox"][name^="check_"]')].map(box => [box.name.slice(6), box.checked]));
                if (decision === "APPROVE" && Object.values(checklist).some(value => !value)) {
                    toast("Hãy đánh dấu đủ các mục xác nhận trước khi duyệt.", "bad");
                    return;
                }
                await api(`/admin/contributions/${form.dataset.id}/decision`, { method: "POST", body: { decision, note: form.elements.note.value, checklist } });
                await refresh({ APPROVE: "Đã duyệt và xuất bản câu hỏi.", REQUEST_CHANGES: "Đã gửi yêu cầu chỉnh sửa.", REJECT: "Đã ghi nhận không duyệt." }[decision]);
            },
            "contributor-grant": async form => {
                const values = formData(form);
                await api("/admin/contributors", { method: "POST", body: { email: values.email.trim(), note: values.note } });
                await refresh("Đã cấp quyền đóng góp câu hỏi.");
            },
            salary: async form => {
                const values = formData(form);
                const bands = Array.from({ length: SALARY_ROWS }, (unused, index) => ({ label: values[`band_label_${index}`].trim(), value: Number(values[`band_value_${index}`]) })).filter(band => band.label && band.value > 0);
                await api("/career-process/admin/salary-reference", { method: "PUT", body: {
                    role_label: values.role_label, statistic: values.statistic, unit: values.unit, bands,
                    overall: values.overall_label.trim() && Number(values.overall_value) > 0 ? { label: values.overall_label.trim(), value: Number(values.overall_value) } : null,
                    missing_note: values.missing_note, scope_note: values.scope_note,
                    source: { label: values.source_label, url: values.source_url, survey_period: values.survey_period, sample_size: values.sample_size ? Number(values.sample_size) : null, checked_at: values.checked_at },
                } });
                await refresh("Đã lưu lương tham khảo.");
            },
            resolve: async form => {
                const values = formData(form);
                const skillLevels = Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith("skill_")).map(([key, value]) => [key.slice(6), Number(value)]));
                await api(`/admin/reviews/${form.dataset.id}/resolve`, { method: "POST", body: { skill_levels: skillLevels, reviewer_notes: values.reviewer_notes } });
                await refresh("Đã lưu quyết định.");
            },
            "add-jd": async form => {
                const payload = new FormData(form);
                const jd = await api("/admin/jds", { method: "POST", form: payload });
                await refresh(`Đã thêm bản nháp ${jd.jd_id}. Cần chuẩn hóa yêu cầu trước khi duyệt.`);
            },
            resource: async form => {
                const values = formData(form);
                await api("/admin/resources", { method: "POST", body: { title: values.title, provider: values.provider, resource_type: values.resource_type, url: values.url, skill_ids: [values.skill], level: Number(values.level), estimated_minutes: Number(values.estimated_minutes), cost_access: values.cost_access, learning_outcome: values.learning_outcome, source_note: values.source_note } });
                await refresh("Đã lưu bản nháp.");
            },
            activity: async form => {
                const values = formData(form);
                const body = { activity_id: values.activity_id.trim(), title: values.title, target_skill: values.target_skill, target_level: Number(values.target_level), estimated_hours: Number(values.estimated_hours), prerequisites: values.prerequisites.split(",").map(item => item.trim()).filter(Boolean), learning_outcome: values.learning_outcome, resource_ids: new FormData(form).getAll("resource_ids"), splittable: form.elements.splittable.checked, assessment_task_id: values.assessment_task_id };
                const existing = form.dataset.existing;
                await api(existing ? `/admin/activities/${existing}` : "/admin/activities", { method: existing ? "PUT" : "POST", body });
                await refresh("Đã lưu học phần.");
            },
            skill: async form => {
                const values = formData(form);
                const skill = app.adminSkills.find(item => item.skill_code === form.dataset.id);
                await api(`/admin/skills/${form.dataset.id}`, { method: "PUT", body: { ...skill, skill_name: values.skill_name, target_level: Number(values.target_level), weight: Number(values.weight), is_core: form.elements.is_core.checked } });
                await refresh("Đã lưu kỹ năng.");
            },
            "add-knowledge": async form => {
                const values = formData(form);
                await api("/assistant/admin/knowledge", { method: "POST", body: { title: values.title, body: values.body, source_url: values.source_url || null } });
                await refresh("Đã thêm bản nháp. Tài liệu cần được duyệt trước khi trợ lý sử dụng.");
            },
            calibration: async form => {
                const values = formData(form);
                await api("/admin/calibration-samples", { method: "POST", body: { ...values, reference_level: Number(values.reference_level) } });
                await refresh("Đã thêm mẫu ẩn danh.");
            },
        },
    });
    // 5.57.1: the section buttons work as soon as they show; before, clicks were ignored until the first section loaded.
    await drawPane();
}
