/** Test Center: timed knowledge tests. Results here never change verified skill levels. */
import { alertBox, api, confirmDialog, emptyView, esc, fmtDateTime, register, setView, skillName, toast, withBusy } from "../core.js";
import { questionInput, readAnswer } from "./questions.js";
import { icon, skillTile, tile } from "../icons.js";

const testTile = item => (item.mode === "PRACTICE" ? tile("sparkles", "brand") : item.skills?.length === 1 ? skillTile(item.skills[0]) : tile("trophy", "warn"));

export async function renderTests() {
    const [catalog, history] = await Promise.all([api("/tests/blueprints"), api("/tests/attempts")]);
    setView(`<div class="stack">${alertBox("info", "Đây là phần luyện tập kiến thức, tách biệt với bài kiểm tra trong Quy trình Career Adapt và không làm thay đổi kết quả của quy trình.")}
        <div class="row-between"><span class="sub">Ngân hàng câu hỏi ${esc(catalog.bank_version)}</span></div>
        <div class="grid grid-3 grid-even push-last">${catalog.blueprints.map(item => `<article class="card stack-sm"><div class="card-title">${testTile(item)}<h3>${esc(item.title)}</h3></div><p class="small sub">${esc(item.description || "")}</p><p class="meta">${icon("clock")}<span>${item.item_count} câu · ${item.time_limit_minutes ? `${item.time_limit_minutes} phút` : "Không giới hạn giờ"}${item.mode === "PRACTICE" ? " · Luyện tập" : ""}</span></p>${item.last_score !== null ? `<p class="small">Lần gần nhất: <strong>${item.last_score}</strong></p>` : ""}${item.attempts_remaining === 0 ? '<p class="small" style="color:var(--warn)">Đã hết lượt trong 24 giờ.</p>' : ""}<button class="btn ${item.in_progress_attempt_id ? "btn-primary" : "btn-secondary"}" data-act="start" data-id="${esc(item.blueprint_id)}" ${item.attempts_remaining === 0 && !item.in_progress_attempt_id ? "disabled" : ""}><span>${item.in_progress_attempt_id ? "Tiếp tục làm" : "Bắt đầu"}</span>${icon("arrow")}</button></article>`).join("")}</div>
        <section class="card"><h2 class="h-ic">${icon("clock")}<span>Lịch sử làm bài</span></h2>${history.attempts.length ? `<div class="table-wrap"><table><thead><tr><th>Bài</th><th>Thời gian</th><th class="num">Điểm</th><th>Kết quả</th></tr></thead><tbody>${history.attempts.map(item => `<tr><td>${item.status === "SUBMITTED" ? `<a href="#/tests/report/${esc(item.attempt_id)}">${esc(item.title)}</a>` : `<a href="#/tests/run/${esc(item.attempt_id)}">${esc(item.title)}</a>`}</td><td class="nowrap">${fmtDateTime(item.submitted_at || item.started_at)}</td><td class="num">${item.composite_score ?? "—"}</td><td>${item.status === "SUBMITTED" ? esc(item.band?.label || "") : "Đang làm"}</td></tr>`).join("")}</tbody></table></div>` : emptyView("Chưa có lượt làm bài", "Chọn một bài ở trên để bắt đầu.")}</section></div>`);
    register({
        actions: {
            start: element => withBusy(element, async () => {
                const attempt = await api("/tests/attempts", { method: "POST", body: { blueprint_id: element.dataset.id } });
                window.location.hash = `#/tests/run/${attempt.attempt_id}`;
            }),
        },
    });
}

export async function renderTestRunner(id) {
    const attempt = await api(`/tests/attempts/${id}`);
    if (attempt.status !== "IN_PROGRESS") { window.location.hash = `#/tests/report/${id}`; return; }
    let index = 0;
    let shownAt = Date.now();
    const answers = Object.fromEntries(attempt.items.map(item => [item.item_id, item.response]));
    const flags = Object.fromEntries(attempt.items.map(item => [item.item_id, item.flagged]));
    let remaining = attempt.remaining_seconds;
    let timer = null;
    const hasAnswer = value => value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && !value.length);
    // An ordering question always shows some order, so it counts as answered only once the learner moves a row.
    const reordered = new Set(attempt.items.filter(item => item.type === "ordering" && hasAnswer(item.response)).map(item => item.item_id));

    const save = async item => {
        const element = document.getElementById("question-area");
        if (!element?.querySelector(`[name="item_${item.item_id}"], [data-ordering="${item.item_id}"]`)) return;
        answers[item.item_id] = item.type === "ordering" && !reordered.has(item.item_id) ? null : readAnswer(element, item);
        const elapsed = (Date.now() - shownAt) / 1000;
        shownAt = Date.now();
        await api(`/tests/attempts/${id}/responses/${item.item_id}`, { method: "PUT", body: { value: answers[item.item_id], time_spent_seconds: elapsed, flagged: Boolean(flags[item.item_id]) } });
    };
    const draw = () => {
        const item = attempt.items[index];
        document.getElementById("question-area").innerHTML = `<p class="sub small">Câu ${index + 1}/${attempt.items.length} · ${esc(skillName(item.skill_code))} · Mức ${item.level}</p><p style="margin:6px 0"><strong>${esc(item.stem)}</strong></p>${item.code ? `<pre class="code">${esc(item.code)}</pre>` : ""}<div class="stack-sm" style="margin-top:8px">${questionInput(item, answers[item.item_id])}</div>${item.type === "ordering" && !reordered.has(item.item_id) ? '<p class="sub small">Câu sắp xếp chỉ được tính là đã trả lời sau khi bạn đổi thứ tự.</p>' : ""}`;
        document.getElementById("palette").innerHTML = attempt.items.map((entry, position) => `<button type="button" data-act="goto" data-index="${position}" class="${hasAnswer(answers[entry.item_id]) ? "is-answered" : ""} ${flags[entry.item_id] ? "is-flagged" : ""} ${position === index ? "is-current" : ""}" aria-label="Câu ${position + 1}">${position + 1}</button>`).join("");
        document.getElementById("flag").textContent = flags[item.item_id] ? "Bỏ đánh dấu" : "Đánh dấu xem lại";
        document.getElementById("prev").disabled = index === 0;
        document.getElementById("next").disabled = index === attempt.items.length - 1;
        shownAt = Date.now();
    };
    const go = async target => {
        await save(attempt.items[index]).catch(error => toast(error.message, "bad"));
        index = target;
        draw();
    };
    const submit = async () => {
        await save(attempt.items[index]).catch(() => {});
        await api(`/tests/attempts/${id}/submit`, { method: "POST", body: {} });
        window.location.hash = `#/tests/report/${id}`;
    };
    const tick = () => {
        if (remaining === null) return;
        remaining -= 1;
        const clock = document.getElementById("timer");
        if (clock) clock.textContent = `${String(Math.floor(Math.max(remaining, 0) / 60)).padStart(2, "0")}:${String(Math.max(remaining, 0) % 60).padStart(2, "0")}`;
        if (remaining <= 0) { clearInterval(timer); submit().catch(error => toast(error.message, "bad")); }
    };
    const focusLost = () => { if (document.hidden) api(`/tests/attempts/${id}/events`, { method: "POST", body: { type: "focus_lost" } }).catch(() => {}); };

    setView(`<div class="stack"><div class="card row-between"><div><strong>${esc(attempt.title)}</strong><br><span class="sub small">Câu trả lời được lưu khi chuyển câu.</span></div><div class="row">${remaining === null ? "" : '<span class="timer" id="timer" aria-live="off"></span>'}<button class="btn btn-primary" data-act="submit-test">Nộp bài</button></div></div>
        <div class="grid grid-main"><section class="card"><div id="question-area"></div><div class="row-between" style="margin-top:14px"><button class="btn btn-secondary" id="prev" data-act="prev">Câu trước</button><button class="btn btn-ghost" id="flag" data-act="flag"></button><button class="btn btn-primary" id="next" data-act="next">Câu sau</button></div></section>
        <aside class="card"><h2 class="h-ic">${icon("quiz")}<span>Danh sách câu</span></h2><div class="palette" id="palette" style="margin-top:10px"></div></aside></div></div>`);
    document.getElementById("question-area").addEventListener("input", event => {
        const list = event.target.closest("[data-ordering]");
        if (list) reordered.add(list.dataset.ordering);
    });
    draw();
    if (remaining !== null) { remaining += 1; tick(); timer = setInterval(tick, 1000); }
    document.addEventListener("visibilitychange", focusLost);
    register({
        cleanup: () => { clearInterval(timer); document.removeEventListener("visibilitychange", focusLost); },
        actions: {
            goto: element => go(Number(element.dataset.index)),
            prev: () => go(index - 1),
            next: () => go(index + 1),
            flag: () => { const item = attempt.items[index]; flags[item.item_id] = !flags[item.item_id]; draw(); },
            "submit-test": async element => {
                await save(attempt.items[index]).catch(() => {});
                const answered = attempt.items.filter(item => hasAnswer(answers[item.item_id])).length;
                if (await confirmDialog("Nộp bài?", `Bạn đã trả lời ${answered}/${attempt.items.length} câu. Sau khi nộp không thể sửa.`, { confirmLabel: "Nộp bài" })) await withBusy(element, submit);
            },
        },
    });
}

export async function renderTestReport(id) {
    const report = await api(`/tests/attempts/${id}/report`);
    const skills = Object.values(report.score.skills);
    setView(`<div class="stack"><a class="small" href="#/tests">← Danh sách bài</a>
        <section class="card"><div class="score-hero"><div class="score-number">${report.composite_score}<small> / 100</small></div><div class="stack-sm"><strong>${esc(report.band?.label || "")}</strong><span class="sub small">${esc(report.band?.summary || "")}</span><span class="badge ${report.passed ? "badge-good" : "badge-bad"}" style="align-self:flex-start">${report.passed ? "Đạt" : "Chưa đạt"}</span></div></div></section>
        <section class="card"><h2>Theo kỹ năng</h2><div class="table-wrap"><table><thead><tr><th>Kỹ năng</th><th class="num">Tỷ lệ đúng</th><th class="num">Khoảng tin cậy 95%</th><th class="num">Số câu</th></tr></thead><tbody>${skills.map(item => `<tr><td>${esc(skillName(item.skill_code))}</td><td class="num">${item.percent}%</td><td class="num">${item.confidence_interval[0]}–${item.confidence_interval[1]}%</td><td class="num">${item.items}</td></tr>`).join("")}</tbody></table></div><p class="sub small" style="margin-top:8px">Mẫu câu hỏi nhỏ nên khoảng tin cậy rộng; không dùng số này thay cho bài thực hành.</p></section>
        ${report.integrity?.flags?.length ? alertBox("warn", esc(report.integrity.flags.join(" "))) : ""}
        <section class="card"><h2>Xem lại câu hỏi</h2><ul>${report.review.map(item => `<li class="list-item"><div><span class="small"><strong>Câu ${item.number}.</strong> ${esc(item.stem)}</span>${item.explanation ? `<p class="sub small">${esc(item.explanation)}</p>` : ""}</div><span class="badge ${item.credit >= 1 ? "badge-good" : item.credit > 0 ? "badge-warn" : "badge-bad"}">${item.points_earned}/${item.points_possible}</span></li>`).join("")}</ul></section>
        <p class="sub small">Ngân hàng ${esc(report.bank_version)}. Kết quả không cập nhật hồ sơ kỹ năng đã xác minh.</p></div>`);
}
