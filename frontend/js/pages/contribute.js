/** Đóng góp câu hỏi (5.35): experts write questions, the server checks them, an administrator approves. */
import { alertBox, api, confirmDialog, emptyView, esc, fmtDateTime, register, setView, skillName, toast, withBusy } from "../core.js";
import { icon } from "../icons.js";
import { pageHero } from "../hero.js";
import { BANK_NAMES, LEVEL_NAMES, englishFields, eventsView, questionPreview, questionText, statusPill, validationView } from "../contribution-view.js";

const BASE = "#/contribute";
let meta = null;

/* Starting points the expert edits; every value here is a placeholder to replace, not bank content. */
const CASE_TEMPLATES = {
    sql: [
        { id: "runs", type: "sql_runs", points: 10, description: "Câu truy vấn chạy được và trả về dữ liệu" },
        { id: "result", type: "sql_result", points: 90, expected_sql: "SELECT ... FROM orders_raw WHERE ...", description: "Kết quả đúng với yêu cầu" },
    ],
    python: [
        { id: "parse", type: "py_parses", points: 10, description: "Code đúng cú pháp Python" },
        { id: "runs", type: "py_runs", points: 10, description: "Code chạy xong không lỗi" },
        { id: "read", type: "py_calls", points: 20, all: ["read_csv"], description: "Đọc tệp bằng read_csv" },
        { id: "result", type: "text_number", points: 60, section: "output", exact: true, expected_sql: "SELECT ... FROM orders_raw", description: "Kết quả in ra đúng" },
    ],
    text: [
        { id: "figure", type: "text_number", points: 50, expected_sql: "SELECT ... FROM orders_raw", description: "Nêu đúng con số" },
        { id: "reason", type: "text_regex", points: 50, patterns: ["tu khoa 1|tu khoa 2", "tu khoa 3"], min_matches: 2, description: "Giải thích có lập luận" },
    ],
};

async function loadMeta() {
    meta = meta || await api("/contributions/meta");
    return meta;
}

function coverageGrid(coverage, bank) {
    const cells = bank === "exam" ? coverage.exam : coverage.test;
    const rows = Object.entries(cells).map(([code, levels]) => `<tr><th scope="row">${esc(skillName(code))}</th>${[1, 2, 3].map(level => {
        const count = levels[level] ?? levels[String(level)] ?? 0;
        const tone = count <= 1 ? "is-low" : count <= 3 ? "is-mid" : "is-ok";
        return `<td><span class="ct-count ${tone}">${count}</span></td>`;
    }).join("")}</tr>`).join("");
    return `<div class="table-wrap"><table class="ct-coverage"><thead><tr><th>Kỹ năng</th>${[1, 2, 3].map(level => `<th>${LEVEL_NAMES[level]}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function listRow(item) {
    const text = questionText(item);
    return `<li class="ct-row"><div class="ct-row-main"><div class="ct-meta">${statusPill(item.status)}<span class="ct-pill is-brand">${BANK_NAMES[item.bank]}</span><span class="ct-pill is-muted">${esc(skillName(item.skill_code))} · ${LEVEL_NAMES[item.level]}</span></div>
        <a class="ct-row-title" href="${BASE}/${esc(item.contribution_id)}">${esc(item.payload.topic || text.slice(0, 80) || "Chưa đặt tên")}</a>
        <span class="sub small">${esc(text.slice(0, 140))}${text.length > 140 ? "…" : ""}</span>
        ${item.review_note && ["CHANGES_REQUESTED", "REJECTED"].includes(item.status) ? `<span class="ct-note">${icon("info")}<span>${esc(item.review_note)}</span></span>` : ""}</div>
        <span class="sub small nowrap">${fmtDateTime(item.updated_at)}</span></li>`;
}

async function listPage() {
    const [data, mine] = await Promise.all([loadMeta(), api("/contributions/mine")]);
    const count = status => mine.filter(item => item.status === status).length;
    const lowCells = Object.values(data.coverage.exam).reduce((total, levels) => total + Object.values(levels).filter(value => value <= 1).length, 0);
    setView(`<div class="stack">
        ${pageHero({ tone: "violet", icon: "write", kicker: "Đóng góp câu hỏi", title: lowCells ? `Đề thi còn ${lowCells} ô kỹ năng × độ khó chỉ có một câu.` : "Mọi ô của đề thi đã có từ hai câu trở lên.",
            text: "Câu hỏi do chuyên gia viết. Hệ thống tự kiểm tra đáp án mẫu trên bốn bộ dữ liệu, rồi một quản trị viên khác duyệt trước khi dùng.",
            stats: [["file", "Bản nháp", count("DRAFT") + count("CHANGES_REQUESTED"), "muted"], ["clock", "Chờ duyệt", count("SUBMITTED"), "warn"], ["check", "Đã xuất bản", count("APPROVED"), "good"], ["target", "Ô còn 1 câu", lowCells, lowCells ? "bad" : "good"]] })}
        <div class="ct-layout">
            <section class="card"><div class="ct-head"><h2 class="h-ic">${icon("file")}<span>Câu hỏi của bạn</span></h2>
                <div class="row"><a class="btn btn-primary btn-sm" href="${BASE}/new-exam">${icon("pen")}<span>Viết câu đề thi</span></a><a class="btn btn-secondary btn-sm" href="${BASE}/new-test">${icon("quiz")}<span>Viết câu trắc nghiệm</span></a></div></div>
                ${mine.length ? `<ul class="ct-list">${mine.map(listRow).join("")}</ul>` : emptyView("Chưa có câu nào", "Bắt đầu bằng một ô đang thiếu câu trong bảng bên cạnh.")}</section>
            <aside class="stack">
                <section class="card"><h2 class="h-ic">${icon("grid")}<span>Số câu đề thi theo ô</span></h2><p class="sub small">Ô đỏ chỉ có một câu: mức kỹ năng ở ô đó đang được kết luận từ đúng câu ấy.</p>${coverageGrid(data.coverage, "exam")}</section>
                <section class="card"><h2 class="h-ic">${icon("quiz")}<span>Số câu trắc nghiệm theo ô</span></h2>${coverageGrid(data.coverage, "test")}</section>
            </aside>
        </div></div>`);
}

/* --- Editor ------------------------------------------------------------------------------------------------- */

function skillOptions(selected, examOnly) {
    return meta.skills.filter(skill => !examOnly || skill.in_exam).map(skill => `<option value="${esc(skill.skill_code)}" ${skill.skill_code === selected ? "selected" : ""}>${esc(skill.skill_name)}</option>`).join("");
}

function datasetPreview() {
    const tabs = Object.entries(meta.datasets).map(([variant, data], index) => `<details class="ct-dataset" ${index === 0 ? "open" : ""}><summary>Bộ dữ liệu ${esc(variant)} <span class="sub small">${esc(data.file)} · ${data.total_rows} dòng</span></summary>
        <div class="table-wrap"><table><thead><tr>${data.columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${data.rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`).join("");
    return `<section class="card"><h2 class="h-ic">${icon("database")}<span>Bảng orders_raw</span></h2><p class="sub small">Đề được giao trên một trong bốn bộ dữ liệu này. Con số mong đợi luôn tính bằng SQL bạn viết trong tiêu chí, nên không cần ghi đáp án số.</p>${tabs}</section>`;
}

function examFields(item) {
    const p = item.payload;
    const answer = p.answer_type || "sql";
    const refs = p.reference_answers || {};
    const refFields = answer === "text"
        ? Object.keys(meta.datasets).map(variant => `<label class="field"><span>Đáp án mẫu cho bộ ${esc(variant)}</span><textarea class="textarea mono" name="ref_${variant}" rows="4" maxlength="6000">${esc(refs[variant] || "")}</textarea></label>`).join("")
        : `<label class="field"><span>Đáp án mẫu (dùng cho cả bốn bộ dữ liệu)</span><textarea class="textarea mono" name="ref_all" rows="6" maxlength="6000">${esc(refs["*"] || "")}</textarea></label>`;
    return `<div class="form-grid"><label class="field"><span>Dạng trả lời</span><select class="select" name="answer_type">${["sql", "python", "text"].map(kind => `<option value="${kind}" ${kind === answer ? "selected" : ""}>${{ sql: "SQL", python: "Python", text: "Bài viết" }[kind]}</option>`).join("")}</select></label>
            <label class="field"><span>Không gian làm bài</span><select class="select" name="workspace">${meta.workspaces[answer].map(kind => `<option ${kind === p.workspace ? "selected" : ""}>${kind}</option>`).join("")}</select></label></div>
        <div class="form-grid"><label class="field"><span>Thời gian (phút)</span><input class="input" type="number" name="minutes" min="3" max="40" value="${p.minutes || 8}"></label>
            <label class="field"><span>Độ dài tối đa (ký tự)</span><input class="input" type="number" name="max_chars" min="300" max="8000" value="${p.max_chars || 3000}"></label></div>
        <label class="field"><span>Đề bài</span><textarea class="textarea" name="prompt" rows="5" maxlength="3000" required>${esc(p.prompt || "")}</textarea></label>
        <label class="field"><span>Gợi ý trong ô trả lời</span><input class="input" name="placeholder" maxlength="200" value="${esc(p.placeholder || "")}"></label>
        <label class="field"><span>Tiêu chí chấm (JSON) <button class="btn btn-ghost btn-sm" type="button" data-act="template">Chèn mẫu cho dạng này</button></span>
            <textarea class="textarea mono" name="cases" rows="12" spellcheck="false">${esc(JSON.stringify(p.cases || CASE_TEMPLATES[answer], null, 2))}</textarea>
            <span class="sub small">Loại dùng được: ${meta.case_types[answer].join(", ")}. Tổng điểm 100. Mẫu chữ (patterns) so với bài viết đã bỏ dấu và viết thường.</span></label>
        <label class="field"><span>Lỗi trọng yếu (JSON, có thể để [])</span><textarea class="textarea mono" name="gates" rows="3" spellcheck="false">${esc(JSON.stringify(p.gates || [], null, 2))}</textarea></label>
        ${refFields}`;
}

function testFields(item) {
    const p = item.payload;
    const type = p.type || "single";
    const options = (p.options || [{ id: "a", text: "" }, { id: "b", text: "" }, { id: "c", text: "" }, { id: "d", text: "" }]).map(option => `${option.id} | ${option.text}`).join("\n");
    const answer = Array.isArray(p.answer) ? p.answer.join(", ") : (p.answer ?? "");
    return `<label class="field"><span>Dạng câu</span><select class="select" name="type">${[["single", "Một đáp án"], ["multiple", "Nhiều đáp án"], ["ordering", "Sắp xếp thứ tự"], ["numeric", "Điền số"]].map(([value, label]) => `<option value="${value}" ${value === type ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label class="field"><span>Câu hỏi</span><textarea class="textarea" name="stem" rows="4" maxlength="2000">${esc(p.stem || "")}</textarea></label>
        <label class="field"><span>Đoạn code đi kèm (nếu có)</span><textarea class="textarea mono" name="code" rows="3" maxlength="2000">${esc(p.code || "")}</textarea></label>
        <label class="field"><span>Lựa chọn, mỗi dòng "mã | nội dung" (bỏ trống với câu điền số)</span><textarea class="textarea mono" name="options" rows="5">${esc(options)}</textarea></label>
        <div class="form-grid"><label class="field"><span>Đáp án (mã lựa chọn; nhiều mã cách nhau bằng dấu phẩy; câu sắp xếp ghi theo thứ tự đúng)</span><input class="input" name="answer" value="${esc(String(answer))}"></label>
            <label class="field"><span>Sai số cho phép / đơn vị (câu điền số)</span><div class="row"><input class="input" type="number" step="any" name="tolerance" value="${p.tolerance || 0}"><input class="input" name="unit" maxlength="20" value="${esc(p.unit || "")}"></div></label></div>
        <label class="field"><span>Giải thích (người học đọc sau khi nộp)</span><textarea class="textarea" name="explanation" rows="3" maxlength="2000">${esc(p.explanation || "")}</textarea></label>`;
}

/** English fields for the texts currently in the form; typed English is kept by key. */
function englishInputs(bank, payload, typed = {}) {
    const fields = englishFields(bank, { ...payload, en: { ...(payload.en || {}), ...typed } });
    if (!fields.length) return `<p class="sub small">Viết nội dung tiếng Việt trước, rồi bấm cập nhật.</p>`;
    return fields.map(field => `<label class="field"><span>${esc(field.label)}${field.needed ? "" : ' <em class="sub">(không cần dịch nếu giữ nguyên)</em>'}</span>
        <span class="sub small ct-en-source">${esc(field.vi.length > 160 ? `${field.vi.slice(0, 160)}…` : field.vi)}</span>
        <textarea class="textarea" name="en__${esc(field.key)}" rows="${field.vi.length > 120 ? 4 : 1}" maxlength="4000" lang="en" spellcheck="true">${esc(field.en)}</textarea></label>`).join("");
}

function englishSection(item) {
    const fields = englishFields(item.bank, item.payload);
    const given = fields.filter(field => field.en).length;
    return `<details class="ct-en" ${given ? "open" : ""}><summary><strong>Bản tiếng Anh</strong> <span class="sub small ct-en-meta"><span>không bắt buộc</span><span id="ct-en-count">${given}/${fields.length} mục</span></span></summary>
        <p class="sub small">Người học chọn giao diện tiếng Anh sẽ đọc bản này. Dịch đủ các mục có chữ tiếng Việt, hoặc để trống toàn bộ để câu chỉ hiện tiếng Việt. Người duyệt đọc cả hai bản. Không dùng AI để dịch hộ nếu bạn không kiểm tra được bản dịch.</p>
        <div id="ct-en-fields" class="stack-sm">${englishInputs(item.bank, item.payload)}</div>
        <button class="btn btn-ghost btn-sm" type="button" data-act="en-refresh">Cập nhật theo nội dung tiếng Việt</button></details>`;
}

function readEnglish(form) {
    return Object.fromEntries([...form.elements].filter(element => element.name?.startsWith("en__") && element.value.trim()).map(element => [element.name.slice(4), element.value.trim()]));
}

function readPayload(form, bank) {
    return { ...readBankPayload(form, bank), en: readEnglish(form) };
}

function readBankPayload(form, bank) {
    const value = name => form.elements[name]?.value ?? "";
    if (bank === "EXAM") {
        let cases, gates;
        try { cases = JSON.parse(value("cases") || "[]"); } catch { throw new Error("Tiêu chí chấm chưa phải JSON hợp lệ."); }
        try { gates = JSON.parse(value("gates") || "[]"); } catch { throw new Error("Lỗi trọng yếu chưa phải JSON hợp lệ."); }
        const answer = value("answer_type");
        const references = answer === "text"
            ? Object.fromEntries(Object.keys(meta.datasets).map(variant => [variant, value(`ref_${variant}`)]))
            : { "*": value("ref_all") };
        return { topic: value("topic"), prompt: value("prompt"), answer_type: answer, workspace: value("workspace"), minutes: Number(value("minutes")), max_chars: Number(value("max_chars")),
            placeholder: value("placeholder"), cases, gates, reference_answers: references };
    }
    const type = value("type");
    const options = type === "numeric" ? [] : value("options").split("\n").map(line => line.trim()).filter(Boolean).map(line => {
        const [id, ...rest] = line.split("|");
        return { id: id.trim(), text: rest.join("|").trim() };
    });
    const raw = value("answer").trim();
    const answer = type === "single" ? raw : type === "numeric" ? Number(raw.replace(",", ".")) : raw.split(",").map(part => part.trim()).filter(Boolean);
    return { type, topic: value("topic"), stem: value("stem"), code: value("code") || undefined, options, answer, tolerance: Number(value("tolerance") || 0), unit: value("unit") || undefined, explanation: value("explanation") };
}

async function editorPage(id) {
    await loadMeta();
    const creating = id === "new-exam" || id === "new-test";
    const item = creating
        ? { bank: id === "new-exam" ? "EXAM" : "TEST", skill_code: "SQL", level: 1, status: "DRAFT", payload: id === "new-exam" ? { answer_type: "sql", workspace: "sql" } : { type: "single" }, validation: null }
        : await api(`/contributions/${encodeURIComponent(id)}`);
    const editable = ["DRAFT", "CHANGES_REQUESTED"].includes(item.status);
    const back = `<a class="btn btn-ghost btn-sm" href="${BASE}">${icon("arrow")}<span>Danh sách câu của bạn</span></a>`;
    if (!editable) {
        setView(`<div class="stack">${back}<div class="ct-layout"><section class="card">${questionPreview(item)}${item.review_note ? alertBox(item.status === "APPROVED" ? "good" : "warn", `<strong>Nhận xét của người duyệt:</strong> ${esc(item.review_note)}`) : ""}
                <div class="row">${item.status === "SUBMITTED" ? '<button class="btn btn-secondary" data-act="withdraw">Rút lại để sửa</button>' : ""}${item.status === "REJECTED" ? '<button class="btn btn-ghost" data-act="remove">Xóa</button>' : ""}</div></section>
            <aside class="stack"><section class="card"><h2 class="h-ic">${icon("check")}<span>Kiểm tra tự động</span></h2>${validationView(item.validation)}</section><section class="card"><h2 class="h-ic">${icon("clock")}<span>Lịch sử</span></h2>${eventsView(item.events)}</section></aside></div></div>`);
        register({ actions: {
            withdraw: element => withBusy(element, async () => { await api(`/contributions/${item.contribution_id}/withdraw`, { method: "POST" }); toast("Đã rút lại. Bạn có thể sửa và gửi lại."); editorPage(item.contribution_id); }),
            remove: element => withBusy(element, async () => { await api(`/contributions/${item.contribution_id}`, { method: "DELETE" }); window.location.hash = BASE; }),
        } });
        return;
    }
    const exam = item.bank === "EXAM";
    setView(`<div class="stack">${back}
        ${item.status === "CHANGES_REQUESTED" ? alertBox("warn", `<strong>Người duyệt yêu cầu chỉnh sửa:</strong> ${esc(item.review_note || "")}`) : ""}
        <div class="ct-layout">
            <form class="card stack" id="ct-form" novalidate><div class="ct-head"><h2 class="h-ic">${icon("pen")}<span>${creating ? "Câu mới" : "Sửa câu"} · ${BANK_NAMES[item.bank]}</span></h2>${creating ? "" : statusPill(item.status)}</div>
                <div class="form-grid"><label class="field"><span>Kỹ năng</span><select class="select" name="skill_code">${skillOptions(item.skill_code, exam)}</select></label>
                    <label class="field"><span>Độ khó</span><select class="select" name="level">${[1, 2, 3].map(level => `<option value="${level}" ${level === item.level ? "selected" : ""}>${LEVEL_NAMES[level]}</option>`).join("")}</select></label></div>
                <label class="field"><span>Chủ đề ngắn</span><input class="input" name="topic" maxlength="80" value="${esc(item.payload.topic || "")}"></label>
                <div id="ct-bank-fields">${exam ? examFields(item) : testFields(item)}</div>
                ${englishSection(item)}
                <div class="row ct-actions"><button class="btn btn-secondary" type="button" data-act="save">${icon("file")}<span>Lưu nháp</span></button>
                    <button class="btn btn-secondary" type="button" data-act="check">${icon("check")}<span>Kiểm tra</span></button>
                    <button class="btn btn-primary" type="button" data-act="submit">${icon("arrow")}<span>Gửi duyệt</span></button>
                    ${creating ? "" : '<button class="btn btn-ghost" type="button" data-act="remove">Xóa bản nháp</button>'}</div>
                <p class="sub small">Gửi duyệt sẽ chạy lại kiểm tra tự động; câu chỉ được gửi khi qua hết. Sau đó một quản trị viên khác bạn duyệt.</p></form>
            <aside class="stack"><section class="card" id="ct-report"><h2 class="h-ic">${icon("check")}<span>Kiểm tra tự động</span></h2>${validationView(item.validation)}</section>${exam ? datasetPreview() : ""}</aside>
        </div></div>`);
    let current = item;
    const form = document.getElementById("ct-form");
    const body = () => ({ bank: current.bank, skill_code: form.elements.skill_code.value, level: Number(form.elements.level.value), payload: readPayload(form, current.bank) });
    const save = async () => {
        current = current.contribution_id
            ? await api(`/contributions/${current.contribution_id}`, { method: "PUT", body: body() })
            : await api("/contributions", { method: "POST", body: body() });
        if (creating) history.replaceState(null, "", `${BASE}/${current.contribution_id}`);
        return current;
    };
    // Rebuild the English list from the Vietnamese now in the form (case ids or options may have changed).
    const refreshEnglish = () => {
        let payload;
        try { payload = readBankPayload(form, current.bank); } catch (error) { toast(`${error.message} Chưa cập nhật được danh sách cần dịch.`, "bad"); return; }
        document.getElementById("ct-en-fields").innerHTML = englishInputs(current.bank, payload, readEnglish(form));
        countEnglish();
    };
    const countEnglish = () => {
        const boxes = [...form.querySelectorAll('[name^="en__"]')];
        // Two separate pieces of text (see the summary), so each one has its own translation in English.
        document.getElementById("ct-en-count").textContent = `${boxes.filter(box => box.value.trim()).length}/${boxes.length} mục`;
    };
    form.addEventListener("input", event => { if (event.target.name?.startsWith("en__")) countEnglish(); });
    const showReport = report => { document.getElementById("ct-report").innerHTML = `<h2 class="h-ic">${icon("check")}<span>Kiểm tra tự động</span></h2>${validationView(report)}`; };
    // A change listener, not data-act: the page's click handler would stop the select from opening.
    form.addEventListener("change", event => {
        if (event.target.name !== "answer_type") return;
        const kind = event.target.value;
        const payload = { ...readPayloadSafe(form), answer_type: kind, workspace: meta.workspaces[kind][0], cases: CASE_TEMPLATES[kind], reference_answers: {} };
        document.getElementById("ct-bank-fields").innerHTML = examFields({ payload });
        refreshEnglish();
    });
    register({ actions: {
        template: () => { form.elements.cases.value = JSON.stringify(CASE_TEMPLATES[form.elements.answer_type.value], null, 2); refreshEnglish(); },
        "en-refresh": () => refreshEnglish(),
        save: element => withBusy(element, async () => { await save(); toast("Đã lưu bản nháp.", "good"); }),
        check: element => withBusy(element, async () => {
            await save();
            current = await api(`/contributions/${current.contribution_id}/check`, { method: "POST" });
            showReport(current.validation);
            toast(current.validation.ok ? "Qua kiểm tra tự động." : "Còn lỗi cần sửa, xem bảng bên cạnh.", current.validation.ok ? "good" : "bad");
        }),
        submit: element => withBusy(element, async () => {
            await save();
            try {
                await api(`/contributions/${current.contribution_id}/submit`, { method: "POST" });
                toast("Đã gửi duyệt.", "good");
                // The address may already be this question's (saved earlier), so draw the read-only view directly.
                history.replaceState(null, "", `${BASE}/${current.contribution_id}`);
                await editorPage(current.contribution_id);
            } catch (error) {
                current = await api(`/contributions/${current.contribution_id}`);
                showReport(current.validation);
                throw error;
            }
        }),
        remove: async element => {
            if (!(await confirmDialog("Xóa bản nháp?", "Bản nháp này sẽ bị xóa và không khôi phục được.", { confirmLabel: "Xóa", danger: true }))) return;
            await withBusy(element, async () => { await api(`/contributions/${current.contribution_id}`, { method: "DELETE" }); window.location.hash = BASE; });
        },
    } });
}

function readPayloadSafe(form) {
    try { return readBankPayload(form, "EXAM"); } catch { return {}; }
}

export async function renderContribute(rest = "") {
    if (!rest) return listPage();
    return editorPage(rest);
}
