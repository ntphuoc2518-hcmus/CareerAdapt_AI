/** JD input, library and requirement review used by the process screen. */
import { api, alertBox, emptyView, esc, fmtDate, LEVEL_NAMES, register, REQUIREMENT_TYPES, safeUrl, setView, skillName, statusBadge, toast } from "../core.js";
import { guide, mountGuide } from "../guide.js";

const confidenceBadge = value => `<span class="badge ${value >= 0.85 ? "badge-good" : value >= 0.7 ? "" : "badge-warn"}" title="Độ tin cậy của phép ánh xạ">${Math.round(value * 100)}%</span>`;

export function importPane() {
    return `<form data-form="import" class="stack" id="import-form">
        <label class="dropzone" id="dropzone"><strong>Chọn tệp hoặc kéo thả vào đây</strong><span class="sub">PDF, DOCX hoặc TXT, tối đa 5 MB</span><span class="sub" id="file-name"></span><input type="file" name="file" id="jd-file" accept=".pdf,.docx,.txt" hidden></label>
        <label class="field"><span>Hoặc dán nội dung JD</span><textarea class="textarea" name="text" rows="8" maxlength="30000" placeholder="Vị trí: Data Analyst Intern&#10;Yêu cầu:&#10;- Thành thạo SQL..."></textarea></label>
        <div class="form-grid"><label class="field"><span>Chức danh (nếu cần sửa)</span><input class="input" name="title" maxlength="180"></label><label class="field"><span>Đơn vị tuyển dụng</span><input class="input" name="employer" maxlength="180"></label></div>
        <label class="field"><span>URL nguồn (không bắt buộc)</span><input class="input" name="source_url" type="url" maxlength="500" placeholder="https://"></label>
        <p class="sub small">Hệ thống giữ bản gốc để đối chiếu. Bạn có thể xóa JD đã nhập bất cứ lúc nào.</p>
        <div class="row"><button class="btn btn-primary" type="submit">Phân tích JD</button></div></form>`;
}

function libraryCard(item) {
    return `<article class="card stack-sm"><div class="row-between"><h3>${esc(item.title)}</h3>${statusBadge(item.review_status)}</div><p class="sub">${esc(item.employer || "Đơn vị chưa công khai")} · ${esc(LEVEL_NAMES[item.role_level] || item.role_level || "Chưa rõ cấp độ")} · ${esc(item.industry || "")}</p><p class="small">${esc(item.description || "")}</p><div class="row small"><span class="badge badge-muted">${item.skill_count} kỹ năng đã chuẩn hóa</span><span class="sub">Kiểm tra nguồn: ${fmtDate(item.last_checked_at)}</span></div><div class="row"><a class="btn btn-secondary btn-sm" href="#/flow/jd/review/${esc(item.jd_id)}/${item.jd_version}">Xem chi tiết và chọn</a>${item.source_url ? `<a class="btn btn-ghost btn-sm" href="${safeUrl(item.source_url)}" target="_blank" rel="noopener noreferrer">Nguồn</a>` : ""}</div></article>`;
}

export async function libraryPane(filters = {}) {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
    const data = await api(`/jds/catalog${query ? `?${query}` : ""}`);
    const select = (name, label, values, map = {}) => `<label class="field"><span>${label}</span><select class="select" name="${name}"><option value="">Tất cả</option>${values.map(value => `<option value="${esc(value)}" ${filters[name] === value ? "selected" : ""}>${esc(map[value] || value)}</option>`).join("")}</select></label>`;
    return `<form data-form="library" class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:14px">
            <label class="field"><span>Tìm kiếm</span><input class="input" name="q" value="${esc(filters.q || "")}" placeholder="Công ty, ngành"></label>
            ${select("role_level", "Cấp độ", data.filters.role_levels, LEVEL_NAMES)}${select("industry", "Ngành", data.filters.industries)}${select("language", "Ngôn ngữ", data.filters.languages, { vi: "Tiếng Việt", en: "Tiếng Anh" })}
            <div class="field" style="justify-content:flex-end"><button class="btn btn-secondary" type="submit">Lọc</button></div></form>
        ${data.items.length ? `<div class="grid grid-2">${data.items.map(libraryCard).join("")}</div>` : emptyView("Không có JD phù hợp", data.fallback.message)}`;
}

export function wireDropzone() {
    const zone = document.getElementById("dropzone");
    const input = document.getElementById("jd-file");
    if (!zone) return;
    const label = () => { document.getElementById("file-name").textContent = input.files[0]?.name || ""; };
    input.addEventListener("change", label);
    ["dragover", "dragenter"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove("is-over"); }));
    zone.addEventListener("drop", event => { input.files = event.dataTransfer.files; label(); });
}

function requirementRow(item, skills) {
    if (!item.in_catalog) {
        return `<tr><td><strong>${esc(item.label || item.normalized_text)}</strong><br><span class="badge badge-muted">Chưa có bài đo</span></td><td colspan="3"><div class="source-quote">${esc(item.source_excerpt)}</div></td><td><span class="sub small">Giữ để theo dõi, không tính vào mục tiêu</span></td></tr>`;
    }
    const excerpts = (item.source_excerpts || [item.source_excerpt]).filter(Boolean);
    return `<tr data-req="${esc(item.requirement_id)}" data-low="${item.needs_confirmation ? 1 : 0}">
        <td><select class="select" data-field="skill" aria-label="Kỹ năng">${skills.map(skill => `<option value="${esc(skill.skill_code)}" ${skill.skill_code === item.skill_code ? "selected" : ""} ${skill.has_rubric ? "" : "disabled"}>${esc(skillName(skill.skill_code))}${skill.has_rubric ? "" : " (chưa có rubric)"}</option>`).join("")}</select></td>
        <td><select class="select" data-field="type" aria-label="Loại yêu cầu">${["REQUIRED", "PREFERRED", "UNSPECIFIED"].map(type => `<option value="${type}" ${type === item.requirement_type ? "selected" : ""}>${REQUIREMENT_TYPES[type]}</option>`).join("")}</select></td>
        <td>${confidenceBadge(item.confidence)}<br><span class="sub small">${esc(item.mapping_rule || "")}</span></td>
        <td>${excerpts.map(text => `<div class="source-quote">${esc(text)}</div>`).join("")}${(item.confirmation_reasons || []).map(reason => `<div class="sub small" style="color:var(--warn)">${esc(reason)}</div>`).join("")}</td>
        <td><select class="select" data-field="decision" aria-label="Quyết định">${item.needs_confirmation ? '<option value="">Hãy chọn</option>' : ""}<option value="CONFIRM" ${item.needs_confirmation ? "" : "selected"}>Giữ</option><option value="REJECT">Loại bỏ</option></select></td></tr>`;
}

export async function renderJdReview(id, version) {
    const back = "#/flow";
    const [jd, config] = await Promise.all([api(`/jds/${id}/versions/${version}`), api("/jds/config")]);
    const library = jd.origin === "LIBRARY";
    const blocked = jd.scope_status === "OUT_OF_SCOPE";
    const measurable = jd.requirements.filter(item => item.in_catalog);
    const extras = [];
    const facts = [["Chức danh", jd.title], ["Đơn vị", jd.employer || "Không nêu"], ["Cấp độ", LEVEL_NAMES[jd.role_level] || "Không nêu"], ["Ngày nhập", fmtDate(jd.source_date || jd.created_at)], ["Phiên bản JD", jd.jd_version], ["Bộ ánh xạ", jd.mapping_version]];
    const body = library ? `<div class="table-wrap"><table><thead><tr><th>Kỹ năng</th><th>Loại</th><th class="num">Mức</th><th class="num">Trọng số</th><th>Căn cứ</th></tr></thead><tbody>${measurable.map(item => `<tr><td>${esc(skillName(item.skill_code))}</td><td>${esc(REQUIREMENT_TYPES[item.requirement_type])}</td><td class="num">${item.target_level}</td><td class="num">${Math.round(item.weight * 100)}%</td><td class="small">${esc(item.source_excerpt)}</td></tr>`).join("")}</tbody></table></div>${jd.scope_note ? `<p class="sub small" style="margin-top:8px">${esc(jd.scope_note)}</p>` : ""}${jd.sources?.length ? `<ul class="small" style="margin-top:8px">${jd.sources.map(source => `<li><a href="${safeUrl(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.label)}</a> <span class="sub">(kiểm tra ${fmtDate(source.checked_at)})</span></li>`).join("")}</ul>` : ""}`
        : `<div class="table-wrap"><table id="req-table"><thead><tr><th>Kỹ năng</th><th>Loại yêu cầu</th><th>Tin cậy</th><th>Đoạn nguồn</th><th>Quyết định</th></tr></thead><tbody>${jd.requirements.map(item => requirementRow(item, config.skills)).join("")}</tbody></table></div>
           <div class="row" style="margin-top:10px"><select class="select" id="extra-skill" style="max-width:220px" aria-label="Thêm kỹ năng">${config.skills.filter(skill => skill.has_rubric).map(skill => `<option value="${esc(skill.skill_code)}">${esc(skillName(skill.skill_code))}</option>`).join("")}</select><button class="btn btn-secondary btn-sm" data-act="add-skill" type="button">Thêm yêu cầu thủ công</button></div><ul id="extra-list" class="small"></ul>`;
    const tips = library
        ? ["Xem các kỹ năng JD yêu cầu, mức và trọng số đã được duyệt.", "Mở nguồn nếu muốn đọc JD gốc.", "Bấm Xác nhận JD này để sang bước làm bài kiểm tra."]
        : ["Kiểm tra thông tin trích xuất ở khung đầu tiên.", "Với từng yêu cầu, chọn kỹ năng, loại yêu cầu và Giữ hoặc Loại bỏ; dòng độ tin cậy thấp cần bạn chọn.", "Có thể thêm yêu cầu thủ công, rồi bấm Xác nhận JD này."];
    const help = guide({ title: library ? "Xem JD trước khi chọn" : "Kiểm tra các yêu cầu đã tách", tips,
        text: library ? "Đây là JD đã được duyệt. Hãy xem các kỹ năng JD yêu cầu; nếu phù hợp với mục tiêu của bạn thì xác nhận." : "Mình đã tách các yêu cầu trong JD. Hãy kiểm tra từng dòng trước khi xác nhận, vì bài kiểm tra sẽ bám theo các yêu cầu này.",
        ask: { question: "Khi xem yêu cầu kỹ năng trong một JD Data Analyst, mình nên chú ý điều gì trước khi chọn JD đó?" } });
    setView(`<div class="flow-page"><a href="#/flow" class="small ca-back">← Chọn cách khác</a>${help}
        ${blocked ? alertBox("bad", `<strong>JD này ngoài phạm vi Data Analyst.</strong> ${esc(jd.scope_reason)} Hệ thống không ép JD này vào bộ kỹ năng Data Analyst. Hãy chọn JD khác.`) : ""}
        ${jd.scope_status === "UNCERTAIN" ? alertBox("warn", `<strong>Cần xác nhận phạm vi.</strong> ${esc(jd.scope_reason)}`) : ""}
        ${(jd.warnings || []).map(text => alertBox("warn", esc(text))).join("")}
        <section class="card"><div class="card-head"><h2>Thông tin trích xuất</h2><span class="row">${statusBadge(jd.scope_status)}${library ? statusBadge(jd.review_status) : ""}</span></div>
            <dl class="facts small">${facts.map(([label, value]) => `<div><dt class="sub">${label}</dt><dd><strong>${esc(value)}</strong></dd></div>`).join("")}</dl>
            ${jd.experience_statements?.length ? `<p class="small" style="margin-top:10px"><span class="sub">Kinh nghiệm JD nêu:</span> ${esc(jd.experience_statements.join("; "))}</p>` : ""}
            ${jd.preview ? `<details style="margin-top:10px"><summary class="small">Xem nội dung đã trích xuất${jd.file_name ? ` từ ${esc(jd.file_name)}` : ""}</summary><pre class="code">${esc(jd.preview)}</pre></details>` : ""}</section>
        <section class="card"><div class="card-head"><div><h2>${library ? "Yêu cầu đã chuẩn hóa" : "Kiểm tra và chỉnh sửa yêu cầu"}</h2><p class="sub">${library ? "Phiên bản đã duyệt, không chỉnh sửa." : `${jd.needs_confirmation_count} yêu cầu cần bạn xác nhận. Mức và trọng số lấy từ cấu hình đã duyệt, không suy từ câu chữ JD.`}</p></div></div>${body}</section>
        ${blocked ? "" : `<section class="card"><form data-form="confirm" class="stack">
            ${library ? "" : `<label class="field" style="max-width:360px"><span>Cấu hình mức mục tiêu</span><select class="select" name="config_id">${config.target_configs.map(item => `<option value="${esc(item.config_id)}" ${jd.role_level && jd.role_level !== "INTERN" && item.config_id === "JUNIOR" ? "selected" : ""}>${esc(item.label)}</option>`).join("")}</select></label>`}
            ${jd.scope_status === "UNCERTAIN" ? '<label class="check"><input type="checkbox" name="confirm_scope"> Tôi xác nhận đây là JD Data Analyst</label>' : ""}
            <div class="row"><button class="btn btn-primary" type="submit">Xác nhận JD này</button><a class="btn btn-ghost" href="${back}">Xem JD khác</a></div></form></section>`}</div>`);
    mountGuide(document.getElementById("view"));
    register({
        actions: {
            "add-skill": () => {
                const select = document.getElementById("extra-skill");
                extras.push({ decision: "CONFIRM", skill_code: select.value, requirement_type: "REQUIRED", source_excerpt: "Do người học thêm thủ công." });
                document.getElementById("extra-list").innerHTML = extras.map(item => `<li>Thêm: ${esc(skillName(item.skill_code))} (bắt buộc)</li>`).join("");
            },
        },
        forms: {
            confirm: async form => {
                const body = { jd_id: jd.jd_id, jd_version: jd.jd_version, config_id: form.querySelector("[name=config_id]")?.value || "INTERN", confirm_scope: Boolean(form.querySelector("[name=confirm_scope]")?.checked), decisions: [...extras] };
                for (const row of document.querySelectorAll("[data-req]")) {
                    const decision = row.querySelector("[data-field=decision]").value;
                    if (!decision) { toast("Hãy chọn Giữ hoặc Loại bỏ cho các yêu cầu độ tin cậy thấp.", "bad"); return; }
                    body.decisions.push({ requirement_id: row.dataset.req, decision, skill_code: row.querySelector("[data-field=skill]").value, requirement_type: row.querySelector("[data-field=type]").value });
                }
                const result = await api("/me/target-jd", { method: "POST", body });
                toast(result.notice, "good");
                window.location.hash = "#/flow";
            },
        },
    });
}
