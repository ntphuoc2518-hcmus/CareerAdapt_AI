/**
 * The working environment of an exam question, chosen only from question.workspace.
 * Every workspace reads and writes one text answer, so saving and grading stay the same for all of them.
 * Learner text and data carry data-no-i18n: the English layer must not touch them.
 */
import { api, esc } from "./core.js";
import { translateText as t } from "./translate.js";

const SQL_KEYWORDS = /\b(select|from|where|group\s+by|order\s+by|having|limit|join|left\s+join|inner\s+join|on|and|or|as|with|distinct|case|when|then|else|end|over|partition\s+by|union|asc|desc|not|null|is|in|between|like|cast|sum|count|avg|min|max|round|coalesce|nullif|trim|substr|lag|lead)\b/gi;
const SQL_BREAKS = /\s+(from|where|group\s+by|order\s+by|having|limit|left\s+join|inner\s+join|join)\b/gi;
const CHART_TYPES = [["bar", "Biểu đồ cột"], ["line", "Biểu đồ đường"], ["pie", "Biểu đồ tròn"]];
const AGGREGATES = [["sum", "Tổng"], ["avg", "Giá trị trung bình"], ["count", "Đếm số dòng"]];
const ISSUE_LABELS = ["Trùng", "Số lượng bằng 0", "Thiếu vùng", "Khác"];
const PIE_COLORS = ["var(--brand)", "var(--info)", "var(--progress-met)", "var(--progress-near)", "var(--progress-far)", "var(--muted)"];
const STATUS_TEXT = {
    OK: ["Thành công", "good"], ERROR: ["Lỗi", "bad"], SYNTAX_ERROR: ["Lỗi cú pháp", "bad"], BLOCKED: ["Không được phép", "bad"], RUNTIME_ERROR: ["Lỗi khi chạy", "bad"],
    TIMEOUT: ["Quá thời gian", "warn"], RESOURCE_LIMIT: ["Vượt giới hạn", "warn"], UNAVAILABLE: ["Chưa chạy được", "warn"], RUNNING: ["Đang chạy...", "muted"], IDLE: ["Chưa chạy", "muted"],
};

function createEditor(host, value, options) {
    const editor = window.CodeMirror(host, { value, lineNumbers: true, tabSize: 4, indentUnit: 4, indentWithTabs: false, smartIndent: true, matchBrackets: true, autoCloseBrackets: true, spellcheck: false, viewportMargin: Infinity, ...options });
    // Tab indents; Shift-Tab outdents, so the keyboard stays useful for code.
    editor.setOption("extraKeys", { Tab: instance => instance.execCommand(instance.somethingSelected() ? "indentMore" : "insertSoftTab"), "Shift-Tab": "indentLess", ...(options.extraKeys || {}) });
    return editor;
}

const statusBadge = status => {
    const [label, tone] = STATUS_TEXT[status] || STATUS_TEXT.IDLE;
    return `<span class="badge badge-${tone}">${esc(label)}</span>`;
};

function tableHtml(columns, rows, { blank = "trống" } = {}) {
    return `<table data-no-i18n><thead><tr>${columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${cell === "" || cell === null ? `<span class="sub">${cell === null ? "NULL" : esc(blank)}</span>` : esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function datasetPreview(dataset, title, open = false) {
    return `<details class="exam-data" ${open ? "open" : ""}><summary class="small"><strong>${esc(title)}</strong> · ${dataset.rows.length} dòng</summary><div class="dataset" style="margin-top:6px">${tableHtml(dataset.columns, dataset.rows)}</div></details>`;
}

function resizeWhenOpened(root, editors) {
    root.querySelectorAll("details").forEach(item => item.addEventListener("toggle", () => editors.forEach(editor => editor.refresh())));
}

export function formatSql(source) {
    // Quoted text and comments keep their spelling; everything else gets upper-case keywords and one clause per line.
    const parts = source.split(/('(?:[^']|'')*'|--[^\n]*)/);
    return parts.map((part, index) => (index % 2 ? part : part.replace(SQL_KEYWORDS, word => word.toUpperCase().replace(/\s+/g, " ")).replace(SQL_BREAKS, (match, word) => `\n${word.toUpperCase().replace(/\s+/g, " ")}`).replace(/\s*,\s*(?=\S)/g, ", ")))
        .join("").replace(/\n{3,}/g, "\n\n").trim();
}

function runner(question, editor, state, { onResult, statusEl, button, run }) {
    const finish = result => {
        state.result = result;
        statusEl.innerHTML = statusBadge(result.status);
        onResult(result);
    };
    return async () => {
        const code = editor.getValue();
        if (!code.trim() || button.disabled) return;
        button.disabled = true;
        statusEl.innerHTML = statusBadge("RUNNING");
        try {
            // The exam, the final assessment and practice each run code through their own endpoint.
            finish(await (run ? run(code) : api("/career-process/exam/run", { method: "POST", body: { question_id: question.question_id, code } })));
        } catch (error) {
            finish({ status: "ERROR", message: error.message, error: { traceback: error.message }, result_sets: [], stdout: "", tables: [], figures: [] });
        } finally {
            button.disabled = false;
        }
    };
}

function sqlWorkspace(root, question, options) {
    const { dataset } = question;
    const state = options.state;
    root.innerHTML = `<div class="ws ws-sql">
        <aside class="ws-explorer" aria-label="Cơ sở dữ liệu"><h3>Cơ sở dữ liệu</h3><p class="small"><strong data-no-i18n>${esc(dataset.table)}</strong><span class="sub"> · ${dataset.rows.length} dòng</span></p>
            <ul class="ws-schema" data-no-i18n>${dataset.schema.map(column => `<li><span>${esc(column.name)}</span><code>${esc(column.type)}</code></li>`).join("")}</ul></aside>
        <div class="ws-main"><div class="ws-toolbar"><button type="button" class="btn btn-primary btn-sm" data-ws="run">Chạy truy vấn</button><button type="button" class="btn btn-secondary btn-sm" data-ws="format">Định dạng</button><button type="button" class="btn btn-ghost btn-sm" data-ws="reset">Đặt lại</button><span class="ws-status" data-ws-status>${statusBadge(state.result?.status || "IDLE")}</span><span class="sub small ws-hint">Ctrl + Enter để chạy</span></div>
            <div class="ws-editor" data-no-i18n></div>
            <div class="ws-output" aria-live="polite"><div class="ws-output-head"><strong>Kết quả</strong><span class="sub small" data-ws-summary></span></div><div data-ws-result></div></div>
            ${datasetPreview(dataset, `Xem trước dữ liệu ${dataset.table}`)}</div></div>`;
    const output = root.querySelector("[data-ws-result]");
    const summary = root.querySelector("[data-ws-summary]");
    const show = result => {
        summary.textContent = result?.elapsed_ms !== undefined ? `${result.elapsed_ms} ms` : "";
        if (!result) { output.innerHTML = '<p class="sub small">Chạy truy vấn để xem kết quả tại đây.</p>'; return; }
        if (result.status !== "OK") { output.innerHTML = `<div class="ws-message is-bad"><strong>Thông báo lỗi</strong><pre class="ws-console">${esc(result.message || "Truy vấn không trả về dữ liệu.")}</pre></div>`; return; }
        output.innerHTML = result.result_sets.map(set => `<p class="sub small">${set.total > set.rows.length ? `${set.total} dòng (hiển thị ${set.rows.length})` : `${set.total} dòng`}</p><div class="dataset">${tableHtml(set.columns, set.rows, { blank: "" })}</div>`).join("");
    };
    let run = () => {};
    const editor = createEditor(root.querySelector(".ws-editor"), options.value, { mode: "text/x-sqlite", extraKeys: { "Ctrl-Enter": () => run(), "Cmd-Enter": () => run() } });
    run = runner(question, editor, state, { onResult: show, statusEl: root.querySelector("[data-ws-status]"), button: root.querySelector('[data-ws="run"]'), run: options.run });
    editor.on("change", () => options.onChange(editor.getValue()));
    root.querySelector('[data-ws="run"]').addEventListener("click", run);
    root.querySelector('[data-ws="format"]').addEventListener("click", () => editor.setValue(formatSql(editor.getValue())));
    root.querySelector('[data-ws="reset"]').addEventListener("click", () => { editor.setValue(""); state.result = null; show(null); root.querySelector("[data-ws-status]").innerHTML = statusBadge("IDLE"); });
    show(state.result);
    resizeWhenOpened(root, [editor]);
    return { editor };
}

function pythonWorkspace(root, question, options) {
    const { dataset } = question;
    const state = options.state;
    root.innerHTML = `<div class="ws ws-python"><div class="ws-toolbar"><button type="button" class="btn btn-primary btn-sm" data-ws="run">Chạy code</button><button type="button" class="btn btn-ghost btn-sm" data-ws="reset">Đặt lại</button><span class="ws-status" data-ws-status>${statusBadge(state.result?.status || "IDLE")}</span><span class="sub small ws-hint">Ctrl + Enter để chạy · Tệp dữ liệu: <code data-no-i18n>${esc(dataset.file)}</code></span></div>
        <div class="ws-editor ws-editor-tall" data-no-i18n></div>
        <div class="ws-output" aria-live="polite"><div class="ws-output-head"><strong>Đầu ra</strong><span class="sub small" data-ws-summary></span></div><div data-ws-result></div></div>
        ${datasetPreview(dataset, `Xem trước tệp ${dataset.file}`)}</div>`;
    const output = root.querySelector("[data-ws-result]");
    const summary = root.querySelector("[data-ws-summary]");
    const show = result => {
        summary.textContent = result?.elapsed_ms ? `${result.elapsed_ms} ms` : "";
        if (!result) { output.innerHTML = '<p class="sub small">Chạy code để xem đầu ra, bảng và biểu đồ tại đây. Hệ thống chấm theo kết quả chạy thật.</p>'; return; }
        const console = result.stdout ? `<h4>Console</h4><pre class="ws-console">${esc(result.stdout)}</pre>` : "";
        const error = result.error ? `<div class="ws-message is-bad"><strong>Thông báo lỗi</strong><pre class="ws-console">${esc(result.error.traceback || result.error.message || "")}</pre></div>` : "";
        const tables = (result.tables || []).map(item => `<h4>${item.name ? `Bảng <code data-no-i18n>${esc(item.name)}</code>` : "Kết quả"} <span class="sub small">${item.shape.join(" × ")}</span></h4><div class="dataset">${tableHtml(item.columns, item.rows, { blank: "" })}</div>`).join("");
        const figures = (result.figures || []).map(image => `<img class="ws-figure" alt="Biểu đồ do code tạo ra" src="data:image/png;base64,${esc(image)}">`).join("");
        output.innerHTML = `${error}${console}${tables}${figures ? `<h4>Biểu đồ</h4>${figures}` : ""}` || '<p class="sub small">Code chạy xong nhưng chưa in ra gì. Hãy dùng print để xem kết quả.</p>';
    };
    let run = () => {};
    const editor = createEditor(root.querySelector(".ws-editor"), options.value, { mode: "python", extraKeys: { "Ctrl-Enter": () => run(), "Cmd-Enter": () => run() } });
    run = runner(question, editor, state, { onResult: show, statusEl: root.querySelector("[data-ws-status]"), button: root.querySelector('[data-ws="run"]'), run: options.run });
    editor.on("change", () => options.onChange(editor.getValue()));
    root.querySelector('[data-ws="run"]').addEventListener("click", run);
    root.querySelector('[data-ws="reset"]').addEventListener("click", () => { editor.setValue(""); state.result = null; show(null); root.querySelector("[data-ws-status]").innerHTML = statusBadge("IDLE"); });
    show(state.result);
    resizeWhenOpened(root, [editor]);
    return { editor };
}

/** Reports are stored as Markdown: readable by the graders and the AI, and displayed through a sanitizer. */
export function renderMarkdown(source) {
    return window.DOMPurify.sanitize(window.marked.parse(source || "", { breaks: true }), { ALLOWED_ATTR: ["align", "colspan", "rowspan"], FORBID_TAGS: ["style", "img", "iframe", "form", "input"] });
}

const countWords = text => (text.replace(/<[^>]+>/g, " ").match(/[\p{L}\p{N}]+(?:[-'’][\p{L}\p{N}]+)*/gu) || []).length;
const tableTemplate = () => `\n| ${t("Cột 1")} | ${t("Cột 2")} |\n| --- | --- |\n|  |  |\n`;

function wrapSelection(editor, before, after = before) {
    const selected = editor.getSelection();
    editor.replaceSelection(`${before}${selected}${after}`);
    if (!selected) editor.setCursor({ line: editor.getCursor().line, ch: editor.getCursor().ch - after.length });
    editor.focus();
}

function prefixLines(editor, prefix) {
    const from = editor.getCursor("from").line;
    const to = editor.getCursor("to").line;
    editor.operation(() => {
        for (let line = from; line <= to; line += 1) {
            editor.replaceRange(typeof prefix === "function" ? prefix(line - from) : prefix, { line, ch: 0 });
        }
    });
    editor.focus();
}

function reportEditor(host, question, options, { sections = [] } = {}) {
    const tools = [["h1", "H1", "Tiêu đề"], ["h2", "H2", "Tiêu đề phụ"], ["bold", "B", "In đậm"], ["italic", "I", "In nghiêng"], ["ul", "•", "Danh sách dấu đầu dòng"], ["ol", "1.", "Danh sách đánh số"], ["table", "▦", "Chèn bảng"], ["left", "⇤", "Căn trái"], ["center", "↔", "Căn giữa"], ["right", "⇥", "Căn phải"], ["undo", "↶", "Hoàn tác"], ["redo", "↷", "Làm lại"]];
    host.innerHTML = `<div class="ws-report"><div class="ws-toolbar ws-format" role="toolbar" aria-label="Định dạng văn bản">${tools.map(([key, mark, label]) => `<button type="button" class="ws-tool" data-tool="${key}" title="${label}" aria-label="${label}">${mark}</button>`).join("")}<span class="ws-spacer"></span>${sections.length ? '<button type="button" class="btn btn-secondary btn-sm" data-tool="sections">Chèn các mục của bài</button>' : ""}<div class="ws-tabs" role="group" aria-label="Chế độ xem"><button type="button" class="is-active" data-mode="write">Soạn thảo</button><button type="button" data-mode="preview">Xem trước</button></div></div>
        <div class="ws-editor ws-editor-writer" data-no-i18n></div><div class="ws-preview prose" data-no-i18n hidden></div>
        <div class="ws-foot sub small"><span data-words></span><span>Hỗ trợ Markdown · Tự động lưu</span></div></div>`;
    const words = host.querySelector("[data-words]");
    const preview = host.querySelector(".ws-preview");
    const box = host.querySelector(".ws-editor");
    const editor = createEditor(box, options.value, { mode: "markdown", lineNumbers: false, lineWrapping: true, tabSize: 2, indentUnit: 2, matchBrackets: false, autoCloseBrackets: false, placeholder: question.placeholder });
    const count = () => { words.textContent = `${countWords(editor.getValue())} từ`; };
    const align = value => {
        const text = editor.getSelection() || t("Nội dung");
        editor.replaceSelection(value === "left" ? text : `<div align="${value}">\n\n${text}\n\n</div>`);
        editor.focus();
    };
    const actions = {
        h1: () => prefixLines(editor, "# "), h2: () => prefixLines(editor, "## "), bold: () => wrapSelection(editor, "**"), italic: () => wrapSelection(editor, "*"), ul: () => prefixLines(editor, "- "),
        ol: () => prefixLines(editor, index => `${index + 1}. `), table: () => { editor.replaceSelection(tableTemplate()); editor.focus(); }, left: () => align("left"), center: () => align("center"), right: () => align("right"),
        undo: () => editor.undo(), redo: () => editor.redo(),
        sections: () => {
            const end = { line: editor.lastLine(), ch: editor.getLine(editor.lastLine()).length };
            const lead = editor.getValue().trim() ? "\n\n" : "";
            editor.replaceRange(`${lead}${sections.map(title => `## ${title}\n\n`).join("")}`.trimEnd() + "\n", end);
            editor.focus();
        },
    };
    host.querySelector(".ws-format").addEventListener("click", event => {
        const tool = event.target.closest("[data-tool]");
        const mode = event.target.closest("[data-mode]");
        if (tool && !box.hidden) actions[tool.dataset.tool]();
        if (mode) {
            const showing = mode.dataset.mode === "preview";
            host.querySelectorAll("[data-mode]").forEach(item => item.classList.toggle("is-active", item === mode));
            if (showing) preview.innerHTML = renderMarkdown(editor.getValue()) || "";
            preview.hidden = !showing;
            box.hidden = showing;
            if (!showing) editor.refresh();
        }
    });
    editor.on("change", () => { options.onChange(editor.getValue()); count(); });
    count();
    return editor;
}

function reportWorkspace(root, question, options) {
    root.innerHTML = `<div class="ws">${datasetPreview(question.dataset, "Dữ liệu của bài")}<div data-ws-writer></div></div>`;
    const editor = reportEditor(root.querySelector("[data-ws-writer]"), question, options, { sections: question.report_sections || [] });
    resizeWhenOpened(root, [editor]);
    return { editor };
}

function dataQualityWorkspace(root, question, options) {
    const { dataset } = question;
    const state = options.state;
    state.marks = state.marks || {};
    state.filter = state.filter || "";
    root.innerHTML = `<div class="ws"><div class="ws-toolbar"><label class="ws-search"><span class="sub small">Lọc dữ liệu</span><input class="input" type="search" data-dq="filter" value="${esc(state.filter)}" placeholder="Nhập giá trị cần tìm"></label><span class="sub small" data-dq="count"></span><span class="ws-spacer"></span><button type="button" class="btn btn-secondary btn-sm" data-dq="insert">Đưa dòng đã đánh dấu vào bài làm</button></div>
        <p class="sub small">Bấm tiêu đề cột để sắp xếp. Chọn loại lỗi ở cột Đánh dấu cho những dòng bạn tự phát hiện; hệ thống không tự tìm lỗi giúp bạn.</p>
        <div class="dataset ws-grid" data-dq="table"></div><div data-ws-writer></div></div>`;
    const area = root.querySelector('[data-dq="table"]');
    const counter = root.querySelector('[data-dq="count"]');
    const rows = dataset.rows.map((row, index) => ({ row, index }));
    const draw = () => {
        const needle = state.filter.trim().toLowerCase();
        const shown = rows.filter(({ row }) => !needle || row.some(cell => cell.toLowerCase().includes(needle)));
        if (state.sort !== undefined) {
            const { column, direction } = state.sort;
            shown.sort((a, b) => {
                const [left, right] = [a.row[column], b.row[column]];
                const numeric = left !== "" && right !== "" && !Number.isNaN(Number(left)) && !Number.isNaN(Number(right));
                return direction * (numeric ? Number(left) - Number(right) : left.localeCompare(right));
            });
        }
        counter.textContent = `${shown.length}/${rows.length} dòng`;
        area.innerHTML = `<table><thead><tr><th>Đánh dấu</th>${dataset.columns.map((column, index) => `<th><button type="button" class="ws-sort" data-sort="${index}" data-no-i18n>${esc(column)}${state.sort?.column === index ? (state.sort.direction > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("")}</tr></thead>
            <tbody>${shown.map(({ row, index }) => `<tr class="${state.marks[index] ? "is-marked" : ""}"><td><select class="select ws-mark" data-mark="${index}" aria-label="Đánh dấu dòng"><option value="">—</option>${ISSUE_LABELS.map(label => `<option ${state.marks[index] === label ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></td>${row.map(cell => `<td data-no-i18n>${cell === "" ? '<span class="ws-empty">trống</span>' : esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    };
    const editor = reportEditor(root.querySelector("[data-ws-writer]"), question, options);
    root.querySelector('[data-dq="filter"]').addEventListener("input", event => { state.filter = event.target.value; draw(); });
    area.addEventListener("click", event => {
        const button = event.target.closest("[data-sort]");
        if (!button) return;
        const column = Number(button.dataset.sort);
        state.sort = { column, direction: state.sort?.column === column ? -state.sort.direction : 1 };
        draw();
    });
    area.addEventListener("change", event => {
        const select = event.target.closest("[data-mark]");
        if (!select) return;
        if (select.value) state.marks[select.dataset.mark] = select.value; else delete state.marks[select.dataset.mark];
        select.closest("tr").classList.toggle("is-marked", Boolean(select.value));
    });
    root.querySelector('[data-dq="insert"]').addEventListener("click", () => {
        const groups = {};
        Object.entries(state.marks).forEach(([index, label]) => { (groups[label] = groups[label] || []).push(dataset.rows[index][0]); });
        const lines = Object.entries(groups).map(([label, ids]) => `- ${label}: ${[...new Set(ids)].join(", ")}`);
        if (lines.length) {
            const end = { line: editor.lastLine(), ch: editor.getLine(editor.lastLine()).length };
            editor.replaceRange(`${editor.getValue().trim() ? "\n" : ""}${lines.join("\n")}\n`, end);
        }
    });
    draw();
    resizeWhenOpened(root, [editor]);
    return { editor };
}

function aggregate(dataset, x, y, how) {
    const column = dataset.columns.indexOf(x);
    const measure = dataset.columns.indexOf(y);
    const groups = new Map();
    for (const row of dataset.rows) {
        const key = row[column] === "" ? t("(trống)") : row[column];
        const value = Number(row[measure]);
        const group = groups.get(key) || { total: 0, count: 0, numbers: 0 };
        group.count += 1;
        if (row[measure] !== "" && !Number.isNaN(value)) { group.total += value; group.numbers += 1; }
        groups.set(key, group);
    }
    return [...groups].map(([label, group]) => ({ label, value: how === "count" ? group.count : how === "avg" ? (group.numbers ? group.total / group.numbers : 0) : group.total }));
}

const short = value => (Math.abs(value) >= 1000 ? value.toLocaleString("en-US", { maximumFractionDigits: 0 }) : String(Math.round(value * 100) / 100));

function chartSvg(type, points) {
    if (!points.length) return "";
    const width = 560;
    const height = 260;
    if (type === "pie") {
        const total = points.reduce((sum, item) => sum + Math.max(item.value, 0), 0) || 1;
        let angle = -Math.PI / 2;
        const slices = points.map((item, index) => {
            const sweep = (Math.max(item.value, 0) / total) * Math.PI * 2;
            const [x1, y1, x2, y2] = [130 + 100 * Math.cos(angle), 130 + 100 * Math.sin(angle), 130 + 100 * Math.cos(angle + sweep * 0.9999), 130 + 100 * Math.sin(angle + sweep * 0.9999)];
            angle += sweep;
            return `<path d="M130 130L${x1} ${y1}A100 100 0 ${sweep > Math.PI ? 1 : 0} 1 ${x2} ${y2}Z" fill="${PIE_COLORS[index % PIE_COLORS.length]}" stroke="var(--surface)" stroke-width="2"><title>${esc(item.label)}: ${short(item.value)}</title></path>`;
        }).join("");
        const legend = points.map((item, index) => `<g transform="translate(270 ${28 + index * 24})"><rect width="12" height="12" rx="3" fill="${PIE_COLORS[index % PIE_COLORS.length]}"/><text x="20" y="11" class="ws-chart-text">${esc(item.label)}: ${short(item.value)}</text></g>`).join("");
        return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Xem trước biểu đồ">${slices}${legend}</svg>`;
    }
    const left = 70;
    const bottom = 32;
    const top = 14;
    const peak = Math.max(...points.map(item => item.value), 1);
    const inner = width - left - 12;
    const step = inner / points.length;
    const scale = value => (height - bottom) - (Math.max(value, 0) / peak) * (height - bottom - top);
    const axis = `<line x1="${left}" y1="${height - bottom}" x2="${width - 8}" y2="${height - bottom}" stroke="var(--border-strong)"/><text x="${left - 6}" y="${top + 8}" text-anchor="end" class="ws-chart-text">${short(peak)}</text><text x="${left - 6}" y="${height - bottom}" text-anchor="end" class="ws-chart-text">0</text>`;
    const labels = points.map((item, index) => `<text x="${left + step * index + step / 2}" y="${height - 12}" text-anchor="middle" class="ws-chart-text">${esc(item.label.slice(0, 12))}</text>`).join("");
    if (type === "line") {
        const coords = points.map((item, index) => `${left + step * index + step / 2},${scale(item.value)}`);
        const dots = points.map((item, index) => `<circle cx="${left + step * index + step / 2}" cy="${scale(item.value)}" r="4" fill="var(--brand)" stroke="var(--surface)" stroke-width="2"><title>${esc(item.label)}: ${short(item.value)}</title></circle>`).join("");
        return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Xem trước biểu đồ">${axis}<polyline points="${coords.join(" ")}" fill="none" stroke="var(--brand)" stroke-width="2"/>${dots}${labels}</svg>`;
    }
    const bars = points.map((item, index) => {
        const barWidth = Math.min(step * 0.6, 56);
        const y = scale(item.value);
        return `<rect x="${left + step * index + (step - barWidth) / 2}" y="${y}" width="${barWidth}" height="${Math.max(height - bottom - y, 1)}" rx="4" fill="var(--brand)"><title>${esc(item.label)}: ${short(item.value)}</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Xem trước biểu đồ">${axis}${bars}${labels}</svg>`;
}

function visualizationWorkspace(root, question, options) {
    const { dataset } = question;
    const numeric = dataset.schema.filter(column => column.type !== "TEXT").map(column => column.name);
    const state = options.state;
    state.chart = state.chart || { type: "bar", x: dataset.columns.includes("region") ? "region" : dataset.columns[0], y: numeric.includes("quantity") ? "quantity" : numeric[0], how: "sum" };
    const pick = (name, items, current, label) => `<label class="field"><span>${esc(label)}</span><select class="select" data-chart="${name}">${items.map(([value, text]) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(text)}</option>`).join("")}</select></label>`;
    const columns = dataset.columns.map(name => [name, name]);
    root.innerHTML = `<div class="ws">${datasetPreview(dataset, "Dữ liệu của bài")}
        <div class="ws-chart"><div class="ws-chart-form">${pick("type", CHART_TYPES, state.chart.type, "Loại biểu đồ")}${pick("x", columns, state.chart.x, "Trục ngang (nhóm)")}${pick("y", numeric.map(name => [name, name]), state.chart.y, "Trục dọc (giá trị)")}${pick("how", AGGREGATES, state.chart.how, "Phép tính")}<button type="button" class="btn btn-secondary btn-sm" data-chart-insert>Đưa mô tả biểu đồ vào bài làm</button></div>
            <div><p class="sub small">Xem trước trên dữ liệu gốc, chưa làm sạch. Nhãn: <span data-chart-title data-no-i18n></span></p><div class="ws-chart-view" data-chart-view></div></div></div>
        <div data-ws-writer></div></div>`;
    const typeName = () => CHART_TYPES.find(item => item[0] === state.chart.type)[1];
    const howName = () => AGGREGATES.find(item => item[0] === state.chart.how)[1];
    const draw = () => {
        const { type, x, y, how } = state.chart;
        root.querySelector("[data-chart-view]").innerHTML = chartSvg(type, aggregate(dataset, x, y, how));
        root.querySelector("[data-chart-title]").textContent = `${how === "count" ? "COUNT" : how.toUpperCase()}(${how === "count" ? "*" : y}) / ${x}`;
    };
    const editor = reportEditor(root.querySelector("[data-ws-writer]"), question, options);
    root.querySelector(".ws-chart-form").addEventListener("change", event => {
        const field = event.target.dataset.chart;
        if (field) { state.chart[field] = event.target.value; draw(); }
    });
    root.querySelector("[data-chart-insert]").addEventListener("click", () => {
        const { x, y, how } = state.chart;
        const end = { line: editor.lastLine(), ch: editor.getLine(editor.lastLine()).length };
        const measure = how === "count" ? t("số dòng") : `${t(howName()).toLowerCase()} ${y}`;
        const sentence = t("{0}: trục ngang là {1}, trục dọc là {2}.").replace("{0}", t(typeName())).replace("{1}", x).replace("{2}", measure);
        editor.replaceRange(`${editor.getValue().trim() ? "\n" : ""}${sentence}\n`, end);
    });
    draw();
    resizeWhenOpened(root, [editor]);
    return { editor };
}

const WORKSPACES = { sql: sqlWorkspace, python: pythonWorkspace, report: reportWorkspace, data_quality: dataQualityWorkspace, visualization: visualizationWorkspace };

/** Show the workspace a question declares. An unknown value falls back to the writing editor, never to a guess from the text. */
export function mountWorkspace(root, question, options) {
    return (WORKSPACES[question.workspace] || reportWorkspace)(root, question, options);
}
