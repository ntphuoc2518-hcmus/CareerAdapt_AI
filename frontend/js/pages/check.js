/** Knowledge checks and mini-tests: one question at a time, answers saved as a server draft,
 * graded only on submit. The result page explains every question; AI feedback is optional. */
import { alertBox, api, confirmDialog, emptyView, esc, formatText, loadingView, newKey, register, safeUrl, setView, skillName, toast, withBusy } from "../core.js";
import { icon, skillIcon, tile, aiAvatar } from "../icons.js";
import { questionInput, readAnswer } from "./questions.js";

const hasAnswer = value => value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && !value.length);
const backHref = kind => (kind === "LESSON_CHECK" ? "#/plan/da/roadmap" : "#/plan/da/progress");

function counts(result) {
    if (result.counts) return result.counts;
    const items = result.item_results || [];
    const correct = items.filter(item => item.credit >= 1).length;
    const answered = items.filter(item => item.answered).length;
    return { correct, wrong: answered - correct, unanswered: items.length - answered };
}

function itemVerdict(item) {
    if (!item.answered) return ['Bỏ trống', "muted"];
    if (item.credit >= 1) return ["Đúng", "good"];
    return item.credit > 0 ? ["Đúng một phần", "warn"] : ["Sai", "bad"];
}

function resultView(result, meta) {
    if (result.status === "INCOMPLETE") {
        return `<div class="stack">${alertBox("info", `<strong>${esc(result.message)}</strong>`)}<div class="row"><a class="btn btn-primary" href="#/mini/${esc(meta.micro_id)}" data-act="reload">Tiếp tục làm bài</a><a class="btn btn-secondary" href="${backHref(meta.kind)}">Để sau</a></div></div>`;
    }
    const passed = result.status === "PASSED";
    const tally = counts(result);
    const lesson = meta.kind === "LESSON_CHECK";
    const weak = result.weak_topics || [];
    const strong = result.strong_topics || [];
    return `<div class="stack">
        <section class="card result-hero ${passed ? "is-pass" : "is-fail"}">${tile(passed ? "trophy" : "alert", passed ? "good" : "warn")}
            <div class="result-score"><span class="score-number">${result.score}<small> / 100</small></span><span class="badge ${passed ? "badge-good" : "badge-warn"}">${passed ? "Đạt" : "Chưa đạt"}</span></div>
            <div class="result-text"><strong>${esc(result.message)}</strong><span class="sub small">${esc(result.activity_title || meta.activity_title || "")} · Ngưỡng đạt ${result.pass_threshold}/100 · ${esc(skillName(result.skill_code))}: mức ${result.previous_level ?? "chưa đánh giá"} → ${result.current_level ?? "chưa đánh giá"}</span>${result.roadmap_update?.changed ? `<span class="small"><a href="#/plan/da/roadmap">Lộ trình đã được cập nhật theo mức mới</a>: thêm ${result.roadmap_update.added.length} bài, bỏ ${result.roadmap_update.removed.length} bài.</span>` : ""}</div></section>
        <div class="grid grid-3">
            <div class="card stat-tile">${tile("check", "good", "tile-sm")}<div><span class="stat-label">Câu đúng</span><span class="stat-value">${tally.correct}</span></div></div>
            <div class="card stat-tile">${tile("alert", "bad", "tile-sm")}<div><span class="stat-label">Câu sai</span><span class="stat-value">${tally.wrong}</span></div></div>
            <div class="card stat-tile">${tile("clock", "brand", "tile-sm")}<div><span class="stat-label">Chưa trả lời</span><span class="stat-value">${tally.unanswered}</span></div></div>
        </div>
        <div class="grid grid-2">
            <section class="card"><h2 class="h-ic">${icon("sparkles")}<span>Điểm mạnh</span></h2>${strong.length ? `<div class="row" style="margin-top:8px">${strong.map(topic => `<span class="badge badge-good">${esc(topic)}</span>`).join("")}</div>` : '<p class="sub small" style="margin-top:6px">Chưa có chủ đề nào trả lời đúng hoàn toàn.</p>'}</section>
            <section class="card"><h2 class="h-ic">${icon("book")}<span>Kiến thức cần ôn</span></h2>${weak.length ? `<div class="row" style="margin-top:8px">${weak.map(topic => `<span class="badge badge-warn">${esc(topic)}</span>`).join("")}</div>` : '<p class="sub small" style="margin-top:6px">Không có phần nào cần ôn trong bài này.</p>'}</section>
        </div>
        <section class="card stack-sm"><div class="card-head" style="margin-bottom:0"><h2 class="h-ic">${icon("route")}<span>Đề xuất ôn tập</span></h2><button class="btn btn-secondary btn-sm" type="button" data-act="ai-feedback">${aiAvatar("xs")}<span>Nhận xét bằng AI</span></button></div>
            ${weak.length ? `<p class="text-label">Chủ đề cần ôn lại (${weak.length})</p>
                <ol class="review-topics">${weak.map(topic => `<li>${esc(topic)}</li>`).join("")}</ol>
                <p class="meta">${icon("refresh")}<span>Ôn xong các chủ đề trên rồi làm lại bài kiểm tra.</span></p>` : '<p class="small">Bạn có thể chuyển sang học phần tiếp theo trong lộ trình.</p>'}
            ${result.review_resources?.length ? `<p class="text-label">Học liệu gợi ý</p><ul class="review-resources">${result.review_resources.map(item => `<li class="resource-link">${icon("book")}<div><a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a><span class="sub small">${esc(item.provider)}</span></div></li>`).join("")}</ul>` : ""}
            <div id="ai-feedback" aria-live="polite"></div></section>
        <section class="card" id="answer-review"><h2 class="h-ic">${icon("file")}<span>Giải thích đáp án</span></h2><ol class="review-list">${(result.item_results || []).map((item, index) => {
            const [label, tone] = itemVerdict(item);
            return `<li><div class="row-between"><strong class="small">Câu ${index + 1}${item.topic ? ` · ${esc(item.topic)}` : ""}</strong><span class="badge badge-${tone}">${label}</span></div><p class="small">${esc(item.stem)}</p>${item.explanation ? `<p class="sub small">${esc(item.explanation)}</p>` : ""}<span class="sub small">${item.points_earned}/${item.points_possible} điểm</span></li>`;
        }).join("")}</ol></section>
        ${result.scope_note ? `<p class="sub small">${esc(result.scope_note)}</p>` : ""}
        <div class="row"><button class="btn btn-secondary" type="button" data-act="to-review">${icon("file")}<span>Xem lại bài làm</span></button>
            ${lesson && !passed ? `<button class="btn btn-primary" type="button" data-act="retry" data-id="${esc(result.activity_id)}">${icon("refresh")}<span>Làm lại bài kiểm tra</span></button>` : ""}
            ${!lesson && result.suggested_cycle_days ? `<a class="btn btn-secondary" href="#/plan/da/roadmap">Đặt lịch kiểm tra lại (gợi ý ${result.suggested_cycle_days} ngày)</a>` : ""}
            <a class="btn btn-ghost" href="${backHref(meta.kind)}">${lesson ? "Về lộ trình" : "Về trang tiến độ"}</a></div></div>`;
}

const feedbackView = data => `<div class="ai-note">${aiAvatar("sm")}<div>${formatText(data.summary)}${[["Điểm mạnh", data.strengths], ["Cần ôn", data.to_review], ["Bước tiếp theo", data.next_steps]].filter(([, list]) => list?.length).map(([title, list]) => `<p class="small"><strong>${title}:</strong></p><ul class="rules small">${list.map(line => `<li>${esc(line)}</li>`).join("")}</ul>`).join("")}<span class="sub small">AI chỉ giải thích kết quả đã chấm, không thay đổi điểm.</span></div></div>`;

function showResult(result, meta) {
    setView(resultView(result, meta));
    register({
        actions: {
            "to-review": () => document.getElementById("answer-review")?.scrollIntoView({ behavior: "smooth" }),
            retry: element => withBusy(element, async () => {
                const next = await api(`/activities/${element.dataset.id}/knowledge-check`, { method: "POST", body: { confirm: true } });
                if (next.lesson_check.status === "UNAVAILABLE") { toast(next.message, "bad"); return; }
                window.location.hash = `#/mini/${next.lesson_check.micro_id}`;
            }),
            "ai-feedback": element => withBusy(element, async () => {
                const box = document.getElementById("ai-feedback");
                box.innerHTML = loadingView("AI đang viết nhận xét...");
                try {
                    box.innerHTML = feedbackView(await api(`/micro-tests/${meta.micro_id}/ai-feedback`, { method: "POST" }));
                } catch (error) {
                    box.innerHTML = alertBox("warn", `${esc(error.message)} <button class="btn btn-secondary btn-sm" type="button" data-act="ai-feedback">Thử lại</button>`);
                }
            }),
        },
    });
}

export async function renderMiniTest(id) {
    const test = await api(`/micro-tests/${id}`);
    const meta = { micro_id: id, kind: test.kind, activity_title: test.activity_title };
    if (test.status === "UNAVAILABLE") {
        setView(`<div class="card">${emptyView("Chưa đủ câu hỏi", "Ngân hàng câu hỏi chưa đủ cho kỹ năng này nên chưa thể tạo bài kiểm tra.", `<a class="btn btn-secondary" href="${backHref(test.kind)}">Quay lại</a>`)}</div>`);
        return;
    }
    if (test.status !== "PENDING") {
        if (test.result) showResult(test.result, meta); else setView(alertBox("info", "Bài kiểm tra này không còn hiệu lực."));
        return;
    }
    const items = test.items;
    const answers = { ...(test.draft || {}) };
    let index = Math.max(0, items.findIndex(item => !hasAnswer(answers[item.item_id])));
    let saveTimer = null;
    const key = newKey();
    const lesson = test.kind === "LESSON_CHECK";

    setView(`<div class="stack check-room">
        <section class="card"><div class="row-between"><div><span class="eyebrow-label">${lesson ? "Kiểm tra kiến thức" : "Mini-test"}${test.attempt_no > 1 ? ` · lần ${test.attempt_no}` : ""}</span><h2>${esc(test.activity_title || skillName(test.skill_code))}</h2>
            <div class="row" style="margin-top:6px"><span class="badge">${skillIcon(test.skill_code)}<span>${esc(skillName(test.skill_code))}</span></span><span class="meta">${icon("quiz")}<span>${items.length} câu</span></span><span class="meta">${icon("target")}<span>Đạt từ ${test.pass_threshold}/100</span></span></div></div>
            <a class="btn btn-ghost btn-sm" href="${backHref(test.kind)}">Để sau</a></div>
            <div class="check-progress"><div class="meter"><span id="check-meter"></span></div><span class="small" id="check-count"></span></div>
            ${test.learning_objectives?.length ? `<details class="small" style="margin-top:8px"><summary>Mục tiêu được đánh giá</summary><ul class="rules">${test.learning_objectives.map(item => `<li>${esc(item)}</li>`).join("")}</ul></details>` : ""}</section>
        <div class="grid grid-main"><section class="card"><div id="question-area"></div>
            <div class="row-between" style="margin-top:16px"><button class="btn btn-secondary" type="button" data-act="prev" id="prev">Câu trước</button><button class="btn btn-primary" type="button" data-act="next" id="next">Câu sau</button></div></section>
            <aside class="card stack-sm"><h2 class="h-ic">${icon("quiz")}<span>Danh sách câu</span></h2><div class="palette" id="palette"></div>
                <p class="sub small" id="save-state">Câu trả lời được lưu tự động.</p><button class="btn btn-primary" type="button" data-act="submit-check">${icon("check")}<span>Nộp bài</span></button>
                <p class="sub small">Câu bỏ trống tính 0 điểm. Đáp án và giải thích chỉ hiện sau khi nộp.</p></aside></div></div>`);

    const refresh = () => {
        const done = items.filter(item => hasAnswer(answers[item.item_id])).length;
        document.getElementById("check-meter").style.width = `${Math.round((done / items.length) * 100)}%`;
        document.getElementById("check-count").textContent = `Đã trả lời ${done}/${items.length}`;
        document.getElementById("palette").innerHTML = items.map((entry, position) => `<button type="button" data-act="goto" data-index="${position}" class="${hasAnswer(answers[entry.item_id]) ? "is-answered" : ""} ${position === index ? "is-current" : ""}" aria-label="Câu ${position + 1}${hasAnswer(answers[entry.item_id]) ? ", đã trả lời" : ""}">${position + 1}</button>`).join("");
    };
    const draw = () => {
        const item = items[index];
        document.getElementById("question-area").innerHTML = `<p class="sub small">Câu ${index + 1}/${items.length} · Mức ${item.level}${item.topic ? ` · ${esc(item.topic)}` : ""}</p><p class="exam-prompt" style="margin:6px 0"><strong>${esc(item.stem)}</strong></p>${item.code ? `<pre class="code">${esc(item.code)}</pre>` : ""}
            <div class="stack-sm" style="margin-top:10px">${questionInput(item, answers[item.item_id] ?? null)}</div>${item.type === "ordering" && !hasAnswer(answers[item.item_id]) ? '<p class="sub small">Câu sắp xếp chỉ được tính là đã trả lời sau khi bạn đổi thứ tự.</p>' : ""}`;
        document.getElementById("prev").disabled = index === 0;
        document.getElementById("next").disabled = index === items.length - 1;
        refresh();
    };
    const save = () => {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(async () => {
            const label = document.getElementById("save-state");
            try {
                await api(`/micro-tests/${id}/draft`, { method: "PUT", body: { responses: answers } });
                if (label) label.textContent = `Đã lưu nháp lúc ${new Date().toLocaleTimeString()}`;
            } catch (error) {
                if (label) label.textContent = `Chưa lưu được nháp: ${error.message}`;
            }
        }, 700);
    };
    const capture = () => {
        const item = items[index];
        const value = readAnswer(document.getElementById("question-area"), item);
        if (hasAnswer(value)) answers[item.item_id] = value; else delete answers[item.item_id];
        refresh();
        save();
    };
    // Only a real change records an answer, so an untouched ordering question stays blank.
    const area = document.getElementById("question-area");
    area.addEventListener("change", capture);
    area.addEventListener("input", event => { if (event.target.closest("[data-option]") || event.target.matches("input[inputmode]")) capture(); });
    draw();
    register({
        cleanup: () => clearTimeout(saveTimer),
        actions: {
            goto: element => { index = Number(element.dataset.index); draw(); },
            prev: () => { index = Math.max(0, index - 1); draw(); },
            next: () => { index = Math.min(items.length - 1, index + 1); draw(); },
            "submit-check": async element => {
                const done = items.filter(item => hasAnswer(answers[item.item_id])).length;
                const text = done < items.length ? `Bạn mới trả lời ${done}/${items.length} câu. Câu bỏ trống tính 0 điểm và không được tính là đúng.` : `Bạn đã trả lời đủ ${items.length} câu. Sau khi nộp không sửa được.`;
                if (!(await confirmDialog("Nộp bài kiểm tra?", text, { confirmLabel: "Nộp bài" }))) return;
                await withBusy(element, async () => {
                    clearTimeout(saveTimer);
                    setView(loadingView("Đang chấm bài..."));
                    try {
                        showResult(await api(`/micro-tests/${id}/submissions`, { method: "POST", body: { responses: answers, idempotency_key: key } }), meta);
                    } catch (error) {
                        setView(alertBox("bad", `<strong>Chưa nộp được bài.</strong> ${esc(error.message)} Câu trả lời vẫn được lưu nháp. <a href="#/mini/${esc(id)}" data-act="reload">Thử lại</a>`));
                    }
                });
            },
        },
    });
}
