/** Exam room and the locked review. The server owns the clock, the answers and the lock. */
import { alertBox, api, confirmDialog, esc, fmtDate, formatText, register, setBar, setView, skillName, toast, withBusy } from "../core.js";
import { icon, aiAvatar } from "../icons.js";
import { mountWorkspace, renderMarkdown } from "../workspaces.js";
import { expressiveHead } from "../faces.js";

const SAVE_DELAY_MS = 1500;
const clockText = seconds => `${String(Math.floor(Math.max(seconds, 0) / 60)).padStart(2, "0")}:${String(Math.max(seconds, 0) % 60).padStart(2, "0")}`;

function datasetBlock(dataset) {
    return `<details class="exam-data" open><summary class="small"><strong>Dữ liệu của bài</strong> (bảng <code>orders_raw</code>)</summary><div class="dataset" style="margin-top:6px"><table><thead><tr>${dataset.columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${dataset.rows.map(row => `<tr>${row.map(cell => `<td>${cell === "" ? '<span class="sub">trống</span>' : esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}

const listButton = (question, index, current, state) => `<button type="button" class="exam-item ${index === current ? "is-current" : ""} ${state}" data-act="goto" data-index="${index}"><strong>${esc(question.label)}</strong><small>${esc(skillName(question.skill_code || ""))}${question.tier_label ? ` · ${esc(question.tier_label)}` : ""}</small></button>`;

/** `base` is the API of the attempt: the Career Adapt exam by default, or the final assessment. */
const GRADING_POLL_MS = 2500;
const GRADING_GIVE_UP_MS = 10 * 60 * 1000;

/**
 * Shown while the server grades a submitted exam in the background (code runs can take a while).
 * ``isReady`` asks the server; when it says yes, ``onReady`` opens the result. Nothing is decided here.
 */
export function renderGradingWait(isReady, onReady, { title = "Đang chấm bài" } = {}) {
    setBar("");
    setView(`<section class="card grading-wait" role="status" aria-live="polite"><span class="grading-bot" aria-hidden="true"><span class="grading-ring"></span>${expressiveHead("thinking", "grading-head")}</span><div><h2>${esc(title)}</h2>
        <p class="sub">Bài làm đã được khóa và lưu trên máy chủ. Máy chủ đang chạy code và chấm từng câu; thường mất dưới một phút. Bạn có thể rời trang này, kết quả vẫn được chấm và lưu.</p>
        <p class="sub small" id="grading-note"></p></div></section>`);
    const started = Date.now();
    const view = document.getElementById("app-view") || document.body;
    let stopped = false;
    const tick = async () => {
        if (stopped || !document.querySelector(".grading-wait")) return;
        let ready = false;
        try { ready = await isReady(); } catch { ready = false; }
        if (ready) { stopped = true; onReady(); return; }
        if (Date.now() - started > GRADING_GIVE_UP_MS) {
            const note = document.getElementById("grading-note");
            if (note) note.textContent = "Việc chấm lâu hơn thường lệ. Hệ thống sẽ tự thử lại; bạn có thể quay lại sau.";
        }
        setTimeout(tick, GRADING_POLL_MS);
    };
    setTimeout(tick, 800);
    return view;
}

export async function renderExamRoom(attempt, onFinished, { base = "/career-process/exam", title = "" } = {}) {
    const answers = Object.fromEntries(attempt.questions.map(question => [question.question_id, question.answer]));
    const saved = { ...answers };
    // When each answer was last saved as this page knows it; the server refuses to overwrite a newer save from another tab.
    const savedAt = Object.fromEntries(attempt.questions.map(question => [question.question_id, question.saved_at || ""]));
    let stale = false;
    // Tool state per question: last run, sort, marks and chart settings survive moving between questions.
    const workspaceState = {};
    let index = 0;
    let remaining = attempt.remaining_seconds;
    let saveTimer = null;
    let timer = null;
    let awayCounted = false;
    let finishing = false;
    let violations = attempt.violations;

    setBar(`<div class="exam-bar"><span class="exam-date">${title ? `<strong>${esc(title)}</strong> · ` : ""}Ngày làm bài: <strong>${fmtDate(attempt.started_at)}</strong></span><span class="timer" id="timer" role="timer" aria-live="off">${clockText(remaining)}</span><button class="btn btn-primary" data-act="submit-exam">Nộp bài</button></div>`);
    const warningBox = () => alertBox("warn", `<strong>Bạn đã rời màn hình làm bài ${violations}/${attempt.max_violations} lần.</strong> Đến lần thứ ${attempt.max_violations}, bài sẽ tự động nộp.`);
    const save = async question => {
        const value = answers[question.question_id];
        if (value === saved[question.question_id] || stale) return;
        let result;
        try {
            result = await api(`${base}/responses/${question.question_id}`, { method: "PUT", body: { text: value, base_saved_at: savedAt[question.question_id] } });
        } catch (error) {
            if (error.status === 409) {
                stale = true;
                const state = document.getElementById("save-state");
                if (state) state.textContent = "Chưa lưu: bài đang mở ở tab khác. Hãy tải lại trang.";
            }
            throw error;
        }
        saved[question.question_id] = value;
        savedAt[question.question_id] = result.saved_at;
        const status = document.getElementById("save-state");
        if (status) status.textContent = "Đã lưu";
    };
    const finish = () => {
        if (finishing) return;
        finishing = true;
        clearInterval(timer);
        onFinished();
    };
    const submit = async () => {
        await save(attempt.questions[index]).catch(() => {});
        const result = await api(`${base}/submit`, { method: "POST", body: {} });
        toast(result.auto_submitted ? "Bài đã được tự động nộp." : result.status === "GRADED" ? "Đã nộp bài. Bài làm đã được khóa." : "Đã nộp bài. Bài làm đã được khóa và đang được chấm.", "good");
        finish();
    };
    const draw = () => {
        const question = attempt.questions[index];
        setView(`<div class="exam-grid"><aside class="exam-list" aria-label="Danh sách bài">${attempt.questions.map((item, position) => listButton(item, position, index, (answers[item.question_id] || "").trim() ? "is-answered" : "")).join("")}<p class="sub small">Bài làm tự lưu trên máy chủ.</p></aside>
            <section class="card exam-main"><div id="exam-warning">${violations ? warningBox() : ""}</div><div class="row-between"><h2>${esc(question.label)}: ${esc(question.topic)}</h2><span class="badge">${esc(question.tier_label)}</span></div>
                <p class="exam-prompt">${esc(question.prompt)}</p><div id="workspace"></div>
                <div class="row-between"><span class="sub small" id="save-state">${answers[question.question_id] === saved[question.question_id] ? "Đã lưu" : ""}</span><div class="row"><button type="button" class="btn btn-secondary" data-act="move" data-step="-1" ${index === 0 ? "disabled" : ""}>Bài trước</button><button type="button" class="btn btn-secondary" data-act="move" data-step="1" ${index === attempt.questions.length - 1 ? "disabled" : ""}>Bài sau</button></div></div></section></div>`);
        mountWorkspace(document.getElementById("workspace"), question, {
            value: answers[question.question_id] || "",
            state: (workspaceState[question.question_id] ||= {}),
            run: code => api(`${base}/run`, { method: "POST", body: { question_id: question.question_id, code } }),
            onChange: value => {
                answers[question.question_id] = value.slice(0, question.max_chars);
                document.getElementById("save-state").textContent = "Đang lưu...";
                clearTimeout(saveTimer);
                saveTimer = setTimeout(() => save(question).catch(error => toast(error.message, "bad")), SAVE_DELAY_MS);
            },
        });
    };
    const go = async target => {
        clearTimeout(saveTimer);
        await save(attempt.questions[index]).catch(error => toast(error.message, "bad"));
        index = target;
        draw();
    };
    const report = (kind, detail = "") => api(`${base}/events`, { method: "POST", body: { kind, detail } });
    const leave = async () => {
        if (awayCounted || finishing) return;
        awayCounted = true;
        const result = await report("focus_lost", document.hidden ? "tab" : "window").catch(() => null);
        if (!result) return;
        violations = result.violations;
        if (result.auto_submitted) { toast("Bạn đã rời bài quá số lần cho phép nên bài đã được tự động nộp.", "bad"); finish(); }
    };
    const back = () => {
        if (!awayCounted) return;
        awayCounted = false;
        const warning = document.getElementById("exam-warning");
        if (warning && !finishing) warning.innerHTML = warningBox();
    };
    const onVisibility = () => (document.hidden ? leave() : back());
    const block = event => {
        if (!event.target.closest?.(".exam-grid")) return;
        event.preventDefault();
        event.stopPropagation();
        if (event.type === "paste") report("paste_blocked").catch(() => {});
        if (event.type === "copy") report("copy_blocked").catch(() => {});
        toast("Không dùng sao chép, dán trong bài kiểm tra.", "bad");
    };
    const blockMenu = event => { if (event.target.closest?.(".exam-grid")) event.preventDefault(); };
    const guard = event => { event.preventDefault(); event.returnValue = ""; };
    const tick = () => {
        remaining -= 1;
        const clock = document.getElementById("timer");
        if (clock) { clock.textContent = clockText(remaining); clock.classList.toggle("is-low", remaining <= 300); }
        if (remaining <= 0) { clearInterval(timer); withBusy(null, submit); }
    };

    draw();
    timer = setInterval(tick, 1000);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", leave);
    window.addEventListener("focus", back);
    // Capture phase: the editors handle paste on their own elements before it would bubble up here.
    ["paste", "copy", "cut", "drop"].forEach(name => document.addEventListener(name, block, true));
    document.addEventListener("contextmenu", blockMenu);
    window.addEventListener("beforeunload", guard);
    register({
        cleanup: () => {
            clearInterval(timer);
            clearTimeout(saveTimer);
            document.removeEventListener("visibilitychange", onVisibility);
            window.removeEventListener("blur", leave);
            window.removeEventListener("focus", back);
            ["paste", "copy", "cut", "drop"].forEach(name => document.removeEventListener(name, block, true));
            document.removeEventListener("contextmenu", blockMenu);
            window.removeEventListener("beforeunload", guard);
        },
        actions: {
            goto: element => go(Number(element.dataset.index)),
            move: element => go(index + Number(element.dataset.step)),
            "submit-exam": async element => {
                clearTimeout(saveTimer);
                await save(attempt.questions[index]).catch(() => {});
                const blank = attempt.questions.filter(item => !(answers[item.question_id] || "").trim());
                const text = blank.length ? `Còn ${blank.length} bài chưa làm (${blank.map(item => item.label).join(", ")}) và sẽ nhận 0 điểm. Sau khi nộp, bài bị khóa và không làm lại được.` : "Sau khi nộp, bài bị khóa và không làm lại được.";
                if (await confirmDialog("Nộp bài?", text, { confirmLabel: "Nộp bài" })) await withBusy(element, submit);
            },
        },
    });
}

const caseRow = item => `<li class="case ${item.passed ? "is-pass" : "is-fail"}"><span class="case-mark" aria-hidden="true">${item.passed ? "✓" : "✕"}</span><div><span>${esc(item.explanation)}</span><span class="sub small nowrap">${item.points_awarded}/${item.points_max} điểm</span></div></li>`;

/** The exam as it was submitted, read-only, with marks and reasons. */
export function renderReview(data, { backHref, backLabel, start = 0 }) {
    // 5.54: a link can open the review on one task (Kết quả bài làm > Điểm từng bài).
    let index = Math.min(Math.max(0, Number(start) || 0), Math.max(0, data.questions.length - 1));
    const draw = () => {
        const question = data.questions[index];
        const written = ["report", "data_quality", "visualization"].includes(question.workspace);
        setView(`<div class="stack"><div class="row-between"><a class="small" href="${backHref}">← ${esc(backLabel)}</a><span class="badge badge-muted">Chỉ xem, không sửa được</span></div>
            <div class="exam-grid"><aside class="exam-list" aria-label="Danh sách bài">${data.questions.map((item, position) => listButton(item, position, index, item.correct ? "is-right" : item.blank ? "" : "is-wrong")).join("")}</aside>
            <section class="card exam-main"><div class="row-between"><h2>${esc(question.label)}: ${esc(question.topic)}</h2><span class="row"><span class="badge">${esc(question.tier_label)}</span><strong>${question.points_awarded}/${question.max_points} điểm</strong></span></div>
                <p class="exam-prompt">${esc(question.prompt)}</p>${datasetBlock(question.dataset)}
                <div><h3>Bài làm của bạn</h3>${question.blank ? '<p class="sub">Bạn đã bỏ trống bài này.</p>' : (written ? `<div class="ws-preview prose" data-no-i18n>${renderMarkdown(question.answer)}</div>` : `<pre class="code">${esc(question.answer)}</pre>`)}</div>
                ${question.critical.length ? alertBox("bad", `<strong>Lỗi trọng yếu:</strong> ${esc(question.critical.join("; "))}`) : ""}
                <div><h3>Chỗ đúng, chỗ sai và lý do</h3><ul class="stack-sm" style="margin-top:6px">${question.cases.map(caseRow).join("")}</ul></div>
                <div><h3>Nhận xét</h3>${question.ai_comment ? `<div class="ai-note">${aiAvatar("sm")}<div>${formatText(question.ai_comment.reason)}</div></div>${question.ai_comment.evidence.map(text => `<div class="source-quote">${esc(text)}</div>`).join("")}<p class="sub small" style="margin-top:6px">Nhận xét do AI viết, đã đối chiếu trích dẫn với bài làm. AI không thay đổi điểm.</p>` : `<p class="sub small">${data.ai.flag ? "Nhận xét AI không đạt kiểm tra nên đã bị loại." : "Chưa bật dịch vụ AI."} Giải thích ở trên do bộ kiểm tra tạo ra từ kết quả thực tế của bài làm.</p>`}</div>
            </section></div></div>`);
    };
    draw();
    register({ actions: { goto: element => { index = Number(element.dataset.index); draw(); window.scrollTo(0, 0); } } });
}

/** Score and verified-level verdict, shared by the process and the plan page. */
export function resultSummary(data) {
    return `<section class="card"><div class="score-hero"><div class="score-number">${data.score}<small> / ${data.max_score}</small></div><div class="stack-sm" style="flex:1;min-width:220px"><span class="badge ${data.passed ? "badge-good" : "badge-bad"}">${data.passed ? "Đạt" : "Chưa đạt"}</span><span class="sub small">Ngưỡng đạt ${data.pass_threshold}/100${data.auto_submitted ? ". Bài được tự động nộp" : ""}${data.violations ? `. Rời màn hình ${data.violations} lần` : ""}.</span>${data.critical_violations.length ? `<span class="small" style="color:var(--bad)"><strong>Lỗi trọng yếu:</strong> ${esc(data.critical_violations.join("; "))}</span>` : ""}</div></div></section>`;
}

export function conclusionCard(data) {
    const conclusion = data.conclusion;
    return `<section class="card stack-sm"><h2 class="h-ic">${icon("sparkles")}<span>Nhận xét trình độ hiện tại</span></h2><div class="conclusion">${formatText(conclusion.summary)}</div>${data.ai.overall ? `<div class="ai-note">${icon("sparkles")}<div>${formatText(data.ai.overall)}</div></div>` : ""}
        <div class="table-wrap"><table><thead><tr><th>Kỹ năng</th><th class="num">Tự khai</th><th class="num">Đã xác thực</th><th class="num">JD yêu cầu</th><th>Vì sao</th></tr></thead><tbody>${conclusion.skills.map(item => `<tr><td><strong>${esc(skillName(item.skill_code))}</strong></td><td class="num">${item.declared_level ?? "—"}</td><td class="num"><strong>${item.verified_level}</strong></td><td class="num">${item.target_level}</td><td class="small">${esc(item.reason)} ${esc(item.compare)}</td></tr>`).join("")}</tbody></table></div>
        <p class="sub small">${esc(conclusion.scope_note || "")}</p></section>`;
}
