/** Secondary screen: the Career Adapt process. The server decides which step is shown. */
import { api, confirmDialog, emptyView, esc, formData, register, setBar, setView, skillName, toast, withBusy } from "../core.js";
import { icon } from "../icons.js";
import { allowAssistantHere } from "../assistant.js";
import { celebrationBot, guide, mountGuide } from "../guide.js";
import { expressionForScore } from "../faces.js";
import { importPane, libraryPane, renderJdReview, wireDropzone } from "./target.js";
import { conclusionCard, renderExamRoom, renderGradingWait, renderReview, resultSummary } from "./exam.js";

const choice = (href, title, text, name = "arrow") => `<a class="choice" href="${href}"><span class="choice-icon">${icon(name)}</span><span class="choice-body"><strong>${esc(title)}</strong><span>${esc(text)}</span></span><span class="choice-go" aria-hidden="true">${icon("arrow")}</span></a>`;
let stepCount = 6;
let stepIndex = 0;
const stepLabel = () => `Bước ${stepIndex + 1}/${stepCount}`;
const STEP_ICONS = ["user", "file", "quiz", "chart", "route", "trophy"];

function stepBar(state, leave = true) {
    const current = state.run.step_index;
    stepCount = state.steps.length;
    stepIndex = current;
    const progress = Math.round((Math.min(current, state.steps.length - 1) / Math.max(1, state.steps.length - 1)) * 100);
    setBar(`<div class="flow-bar"><div class="flow-title"><strong>Quy trình Career Adapt</strong><small>${esc(state.run.career_title)} · ${stepLabel()}</small></div>
        <ol class="flow-steps" style="--progress:${progress}">${state.steps.map((step, index) => `<li class="${index < current ? "is-done" : index === current ? "is-current" : ""}" ${index === current ? 'aria-current="step"' : ""}><span>${index < current ? "✓" : icon(STEP_ICONS[index] || "check")}</span><em>${esc(step.label)}</em></li>`).join("")}</ol>
        ${leave ? `<a class="btn btn-ghost btn-sm" href="#/">${icon("logout")}<span>Tạm rời</span></a>` : "<span></span>"}</div>`);
}

function narrow(html) {
    setView(`<div class="flow-page">${html}</div>`);
    mountGuide(document.getElementById("view"));
}

function skillsHome() {
    narrow(`${guide({ step: stepLabel(), title: "Báo cáo kỹ năng hiện tại",
        text: "Chào bạn. Trước hết, hãy cho mình biết kỹ năng hiện tại của bạn. Thông tin này chỉ để chọn độ khó bài kiểm tra, chưa được xem là trình độ thật. Bạn muốn báo cáo theo cách nào?",
        tips: ["Cách 1: dán mô tả kinh nghiệm hoặc tải CV, hệ thống gợi ý mức cho từng kỹ năng để bạn kiểm tra lại.", "Cách 2: tự chọn mô tả đúng nhất với bạn cho từng kỹ năng.", "Sau khi xác nhận, bạn sang bước chọn JD và không quay lại sửa được."],
        ask: { question: "Ở bước Báo cáo kỹ năng của Quy trình Career Adapt, mình nên tự đánh giá kỹ năng thế nào cho đúng?" } })}
        <div class="choices">${choice("#/flow/skills/import", "Nhập hoặc import file PDF", "Dán mô tả kinh nghiệm hoặc tải CV. Hệ thống gợi ý mức, bạn kiểm tra lại.", "upload")}${choice("#/flow/skills/pick", "Chọn từ danh sách kỹ năng", "Chọn mô tả đúng nhất với bạn cho từng kỹ năng.", "check")}</div>`);
}

async function confirmSkills(skills, method) {
    if (!(await confirmDialog("Xác nhận kỹ năng?", "Sau khi xác nhận, bạn sang bước chọn JD và không quay lại sửa được.", { confirmLabel: "Xác nhận" }))) return;
    await api("/me/skill-report/confirm", { method: "POST", body: { skills, products: [], method } });
    toast("Đã lưu kỹ năng.", "good");
    window.location.hash = "#/flow";
}

async function skillsPick() {
    const { skills } = await api("/career-process/skill-options");
    narrow(`${guide({ step: stepLabel(), title: "Chọn mức cho từng kỹ năng",
        text: "Với mỗi kỹ năng, hãy chọn mô tả đúng nhất với bạn. Kỹ năng bạn bỏ qua sẽ nhận câu hỏi ở mức cơ bản.",
        tips: ["Bấm vào ô mô tả gần nhất với bạn ở từng kỹ năng.", "Ghi ví dụ đã làm nếu muốn; phần này không bắt buộc.", "Bấm Xác nhận kỹ năng ở cuối trang, rồi xác nhận lần nữa trong hộp thoại."],
        ask: { question: "Mình nên chọn mức kỹ năng tự khai thế nào khi chưa chắc chắn?" } })}
        <form data-form="pick" class="stack">${skills.map(skill => `<fieldset class="card pick"><legend>${esc(skillName(skill.skill_code))}</legend><div class="pick-options">${skill.options.map(option => `<label class="option"><input type="radio" name="level_${esc(skill.skill_code)}" value="${option.level}"><span><strong>${esc(option.label)}</strong><br><span class="sub small">${esc(option.detail)}</span></span></label>`).join("")}</div><label class="field" style="margin-top:8px"><span>Ví dụ đã làm (không bắt buộc)</span><input class="input" name="note_${esc(skill.skill_code)}" maxlength="600"></label></fieldset>`).join("")}
        <div class="row-between"><a class="btn btn-ghost" href="#/flow">Chọn cách khác</a><button class="btn btn-primary" type="submit">Xác nhận kỹ năng</button></div></form>`);
    register({
        forms: {
            pick: async form => {
                const values = formData(form);
                const picked = skills.filter(skill => values[`level_${skill.skill_code}`] !== undefined).map(skill => ({ skill_code: skill.skill_code, level: Number(values[`level_${skill.skill_code}`]), description: values[`note_${skill.skill_code}`] || "" }));
                if (!picked.length) { toast("Hãy chọn ít nhất một kỹ năng.", "bad"); return; }
                await confirmSkills(picked, "PICK");
            },
        },
    });
}

async function skillsImport() {
    const { skills } = await api("/career-process/skill-options");
    narrow(`${guide({ step: stepLabel(), title: "Nhập kinh nghiệm hoặc tải CV",
        text: "Hãy dán mô tả kỹ năng, kinh nghiệm của bạn hoặc tải tệp PDF. Mình gợi ý mức cho từng kỹ năng, bạn sửa lại nếu chưa đúng.",
        tips: ["Kéo thả tệp PDF, DOCX hoặc TXT (tối đa 2 MB) vào khung, hoặc dán nội dung vào ô bên dưới.", "Bấm Phân tích để nhận gợi ý mức, kèm câu trích làm căn cứ.", "Xem lại từng gợi ý, sửa nếu chưa đúng, rồi bấm Xác nhận kỹ năng."],
        ask: { question: "Mình nên viết mô tả kinh nghiệm thế nào để hệ thống gợi ý mức kỹ năng chính xác?" } })}
        <form data-form="analyze" class="card stack"><label class="dropzone" id="dropzone"><strong>Chọn tệp hoặc kéo thả vào đây</strong><span class="sub">PDF, DOCX hoặc TXT, tối đa 2 MB</span><span class="sub" id="file-name"></span><input type="file" name="file" id="jd-file" accept=".pdf,.docx,.txt,.md" hidden></label>
            <label class="field"><span>Hoặc nhập trực tiếp</span><textarea class="textarea" name="text" rows="7" maxlength="30000" placeholder="Ví dụ: Em đã làm đồ án dùng SQL để JOIN và GROUP BY dữ liệu bán hàng, vẽ dashboard Power BI..."></textarea></label>
            <div class="row-between"><a class="btn btn-ghost" href="#/flow">Chọn cách khác</a><button class="btn btn-primary" type="submit">Phân tích</button></div></form><div id="suggestions"></div>`);
    wireDropzone();
    let suggestions = [];
    const levels = code => skills.find(skill => skill.skill_code === code)?.options || [];
    register({
        forms: {
            analyze: async form => {
                const file = form.querySelector("[name=file]").files[0];
                let text = formData(form).text || "";
                if (file) {
                    const payload = new FormData();
                    payload.append("file", file);
                    text = (await api("/me/skill-report/extract-text", { method: "POST", form: payload })).text;
                }
                const result = await api("/me/skill-report/analyze", { method: "POST", body: { experience_text: text } });
                suggestions = result.suggestions;
                document.getElementById("suggestions").innerHTML = `<form data-form="confirm-import" class="card stack"><h2>Gợi ý từ nội dung của bạn</h2><p class="sub small">${esc(result.notice)}</p>
                    ${suggestions.map(item => `<div class="suggestion"><label class="field"><span>${esc(skillName(item.skill_code))}</span><select class="select" name="level_${esc(item.skill_code)}"><option value="">Không khai báo</option>${levels(item.skill_code).map(option => `<option value="${option.level}" ${item.detected && option.level === item.suggested_level ? "selected" : ""}>${esc(option.label)}: ${esc(option.detail)}</option>`).join("")}</select></label>${item.evidence.length ? `<div class="source-quote">${esc(item.evidence[0])}</div>` : '<p class="sub small">Không thấy nhắc đến kỹ năng này.</p>'}</div>`).join("")}
                    <div class="row"><button class="btn btn-primary" type="submit">Xác nhận kỹ năng</button></div></form>`;
            },
            "confirm-import": async form => {
                const values = formData(form);
                const picked = suggestions.filter(item => values[`level_${item.skill_code}`] !== "").map(item => ({ skill_code: item.skill_code, level: Number(values[`level_${item.skill_code}`]), description: item.evidence[0] || "" }));
                if (!picked.length) { toast("Hãy chọn mức cho ít nhất một kỹ năng.", "bad"); return; }
                await confirmSkills(picked, "IMPORT");
            },
        },
    });
}

function jdHome(state) {
    const intro = state?.run?.goal_change
        ? "Bạn đang đổi JD mục tiêu. Mức kỹ năng đã xác thực, bài kiểm tra và lịch sử học được giữ nguyên; sau khi chọn JD mới, mình sẽ lập lại lộ trình theo JD đó. Bạn muốn báo JD theo cách nào?"
        : "Tiếp theo, hãy cho mình biết công việc bạn nhắm tới. Bài kiểm tra sẽ bám theo các kỹ năng JD yêu cầu. Bạn muốn báo JD theo cách nào?";
    narrow(`${guide({ step: stepLabel(), title: state?.run?.goal_change ? "Chọn JD mục tiêu mới" : "Chọn công việc bạn nhắm tới", text: intro,
        tips: ["Nhập hoặc import JD: dán nội dung hoặc tải tệp JD của công ty bạn muốn ứng tuyển.", "Chọn JD có sẵn: danh sách JD Data Analyst đã được tổng hợp và duyệt.", "Bài kiểm tra sẽ gồm các kỹ năng mà JD bạn chọn yêu cầu."],
        ask: { question: "Ở bước Chọn JD, mình nên chọn JD như thế nào cho phù hợp với mục tiêu nghề Data Analyst?" } })}
        <div class="choices">${choice("#/flow/jd/import", "Nhập hoặc import JD", "Dán nội dung hoặc tải tệp JD của công ty bạn muốn ứng tuyển.", "upload")}${choice("#/flow/jd/library", "Chọn JD có sẵn", "Chọn từ danh sách JD Data Analyst đã được tổng hợp và duyệt.", "book")}</div>
        ${state?.run?.goal_change ? `<button class="btn btn-ghost goal-cancel" type="button" data-act="cancel-goal-change">Hủy đổi mục tiêu, giữ JD đang dùng</button>` : ""}`);
    if (!state?.run?.goal_change) return;
    register({
        actions: {
            "cancel-goal-change": async element => {
                if (!(await confirmDialog("Hủy đổi mục tiêu?", "JD, lộ trình và tiến độ đang dùng được giữ nguyên như trước khi bấm Đổi JD mục tiêu.", { confirmLabel: "Hủy đổi mục tiêu" }))) return;
                await withBusy(element, async () => {
                    const result = await api("/career-process/change-goal/cancel", { method: "POST" });
                    toast(result.message, "good");
                    window.location.hash = "#/plan/da/overview";
                });
            },
        },
    });
}

function jdImport() {
    narrow(`${guide({ step: stepLabel(), title: "Nhập JD của bạn", text: "Dán JD hoặc tải tệp PDF, DOCX, TXT. Mình sẽ tách các yêu cầu để bạn kiểm tra.",
        tips: ["Dán nội dung JD hoặc kéo thả tệp vào khung.", "Có thể ghi thêm chức danh, công ty và đường dẫn nguồn.", "Sau khi gửi, bạn kiểm tra từng yêu cầu được tách ra trước khi xác nhận JD."],
        ask: { question: "Một JD Data Analyst thường có những yêu cầu kỹ năng nào mình cần chú ý?" } })}<section class="card">${importPane()}</section><a class="btn btn-ghost" href="#/flow" style="align-self:flex-start">Chọn cách khác</a>`);
    wireDropzone();
    register({
        forms: {
            import: async form => {
                const file = form.querySelector("[name=file]").files[0];
                const values = formData(form);
                const payload = new FormData();
                if (file) payload.append("file", file); else if (values.text?.trim()) payload.append("text", values.text);
                ["title", "employer", "source_url"].forEach(key => { if (values[key]) payload.append(key, values[key]); });
                const jd = await api("/jds/import", { method: "POST", form: payload });
                window.location.hash = `#/flow/jd/review/${jd.jd_id}/${jd.jd_version}`;
            },
        },
    });
}

async function jdLibrary() {
    const draw = async filters => { document.getElementById("library").innerHTML = await libraryPane(filters); };
    narrow(`${guide({ step: stepLabel(), title: "Chọn một JD đã duyệt", text: "Đây là các JD Data Analyst đã được duyệt. Hãy mở một JD để xem yêu cầu rồi xác nhận.",
        tips: ["Dùng ô tìm kiếm và bộ lọc cấp độ, ngành, ngôn ngữ để thu hẹp danh sách, rồi bấm Lọc.", "Bấm Xem chi tiết và chọn ở JD bạn quan tâm.", "Ở trang chi tiết, xem các kỹ năng JD yêu cầu rồi bấm Xác nhận JD này."],
        ask: { question: "Nên chọn JD cấp độ nào (thực tập, junior, middle) khi mình mới bắt đầu học Data Analyst?" } })}<section class="card" id="library"></section><a class="btn btn-ghost" href="#/flow" style="align-self:flex-start">Chọn cách khác</a>`);
    await draw();
    register({ forms: { library: form => draw(formData(form)) } });
}

function examIntro(state) {
    const count = state.run.jd?.requirements?.length || 0;
    const rules = [["clock", "Chỉ làm một lần duy nhất. Đồng hồ chạy ngay khi bắt đầu và không dừng."], ["lock", "Không có gợi ý hay chế độ luyện tập. Không dùng AI, tài liệu hay sao chép, dán."], ["alert", "Chuyển tab hoặc rời cửa sổ sẽ bị ghi nhận. Đến lần thứ 3, bài tự động nộp."], ["refresh", "Có thể đổi qua lại giữa các bài, câu trả lời được giữ nguyên."], ["check", "Hết giờ, hệ thống tự nộp phần bạn đã làm. Bài bỏ trống nhận 0 điểm."]];
    narrow(`${guide({ step: stepLabel(), mood: "encouraging", title: "Sẵn sàng làm bài kiểm tra", text: `Mình đã chuẩn bị bài kiểm tra gồm ${count} bài, mỗi bài một chủ đề JD yêu cầu, độ khó theo mức JD yêu cầu.`,
        tips: ["Đọc kỹ quy định bên dưới trước khi bắt đầu.", "Chọn lúc có đủ thời gian yên tĩnh: đồng hồ không dừng.", "Từ bước này đến khi nộp bài, Trợ lý tạm dừng để bài làm là của riêng bạn."] })}
        <section class="card stack-sm exam-rules"><h2>${icon("shield")}<span>Quy định làm bài</span></h2><ul class="rules">${rules.map(([name, text]) => `<li><span class="rule-icon">${icon(name)}</span><span>${text}</span></li>`).join("")}</ul>
            <div class="row"><button class="btn btn-primary" data-act="start-exam">${icon("play")}<span>Bắt đầu làm bài</span></button></div></section>`);
    register({
        actions: {
            "start-exam": async element => {
                if (await confirmDialog("Bắt đầu làm bài?", "Đồng hồ sẽ chạy ngay và bạn chỉ được làm một lần.", { confirmLabel: "Bắt đầu" })) {
                    await withBusy(element, async () => { await api("/career-process/exam/start", { method: "POST" }); renderFlow(); });
                }
            },
        },
    });
}

async function resultStep() {
    const data = await api("/career-process/exam/review");
    // The robot's face and words follow the checker's score and pass decision; they change nothing.
    const mood = expressionForScore(data);
    const said = { score: data.score, max: data.max_score, threshold: data.pass_threshold };
    const RESULT_WORDS = {
        celebrate: ["Xuất sắc!", `Tuyệt vời! Bạn đạt ${said.score}/${said.max}, vượt xa ngưỡng ${said.threshold}. Kết quả do bộ kiểm tra chấm từ chính bài làm của bạn.`],
        joy: ["Chúc mừng bạn đã đạt!", `Bạn đạt ${said.score}/${said.max}, qua ngưỡng ${said.threshold}. Kết quả do bộ kiểm tra chấm từ chính bài làm của bạn.`],
        worried: ["Gần đạt, nhưng có lỗi trọng yếu", `Bạn đạt ${said.score}/${said.max}, nhưng bài có lỗi trọng yếu nên chưa đạt. Hãy xem lỗi được ghi bên dưới để tránh lần sau.`],
        encouraging: ["Chỉ còn một chút nữa", `Bạn đạt ${said.score}/${said.max}, còn thiếu một chút so với ngưỡng ${said.threshold}. Lộ trình sẽ ưu tiên các kỹ năng còn khoảng cách.`],
        sad: ["Lần này chưa đạt", `Lần này bạn đạt ${said.score}/${said.max}. Không sao cả: kết quả cho biết chính xác chỗ cần học, và lộ trình sẽ bắt đầu từ đó.`],
        crying: ["Mình buồn cùng bạn một chút", `Bài lần này được ${said.score}/${said.max}. Mình buồn cùng bạn một chút, rồi mình cùng bắt đầu lại nhé: lộ trình sẽ ưu tiên những kỹ năng còn khoảng cách lớn nhất.`],
    };
    const [moodTitle, moodText] = RESULT_WORDS[mood];
    narrow(`${guide({ step: stepLabel(), mood, title: moodTitle, text: moodText,
        tips: ["Xem điểm, mức đạt từng kỹ năng và khoảng cách so với JD.", "Bấm Xem lại để xem câu trả lời và chỗ bị trừ điểm.", "Khi đã xem xong, bấm Tiếp tục tạo lộ trình. Bước này không quay lại được."],
        ask: { task: "explain_result", label: "Giải thích kết quả đánh giá", button: "Nhờ Trợ lý giải thích kết quả" } })}${resultSummary(data)}<section class="card row-between"><div><h2>Xem lại bài làm</h2><p class="sub small">Xem câu trả lời, chỗ sai bị trừ điểm và nhận xét từng bài. Không sửa được.</p></div><a class="btn btn-secondary" href="#/flow/review">Xem lại</a></section>${conclusionCard(data)}
        <div class="row"><button class="btn btn-primary" data-act="confirm-result">Tiếp tục tạo lộ trình</button></div>`);
    register({ actions: { "confirm-result": element => withBusy(element, async () => { await api("/career-process/result/confirm", { method: "POST" }); renderFlow(); }) } });
}

function roadmapStep(state) {
    const intro = state.run.goal_changes
        ? "Mục tiêu mới đã được ghi nhận. Mình giữ các mức đã xác thực và các bài học bạn đã đạt; cho mình biết quỹ thời gian để xếp lại lộ trình theo JD mới."
        : "Mình đã có kết quả xác thực và khoảng cách kỹ năng của bạn. Cho mình biết quỹ thời gian để xếp lộ trình theo tuần. Sau bước này, quy trình hoàn tất và không sửa lại được.";
    narrow(`${guide({ step: stepLabel(), title: "Lập lộ trình học theo tuần", text: intro,
        tips: ["Nhập số giờ bạn học được mỗi tuần (từ 0,5 đến 40).", "Nhập số tuần bạn muốn hoàn thành (từ 1 đến 52).", "Bấm Tạo lộ trình. Lộ trình xếp bài học theo khoảng cách kỹ năng và quỹ thời gian của bạn."],
        ask: { question: "Mình nên chọn bao nhiêu giờ học mỗi tuần và bao nhiêu tuần cho lộ trình Data Analyst?" } })}
        <form class="card stack" data-form="roadmap"><div class="form-grid"><label class="field"><span>Giờ học mỗi tuần</span><input class="input" type="number" name="weekly_hours" min="0.5" max="40" step="0.5" required value="${state.weekly_hours}"></label><label class="field"><span>Số tuần mong muốn</span><input class="input" type="number" name="timeline_weeks" min="1" max="52" required value="${state.timeline_weeks}"></label></div>
            <div class="row"><button class="btn btn-primary" type="submit">Tạo lộ trình</button></div></form>`);
    register({
        forms: {
            roadmap: async form => {
                const values = formData(form);
                await api("/career-process/roadmap", { method: "POST", body: { weekly_hours: Number(values.weekly_hours), timeline_weeks: Number(values.timeline_weeks) } });
                toast("Đã tạo lộ trình.", "good");
                renderFlow();
            },
        },
    });
}

function doneStep() {
    narrow(`<section class="card done">${celebrationBot()}<span class="done-mark" aria-hidden="true">✓</span><h2>Đã hoàn tất Quy trình Career Adapt</h2><p class="sub">Kết quả và lộ trình đã được lưu trong tài khoản của bạn.</p><div class="row" style="justify-content:center"><a class="btn btn-primary" href="#/plan/da/overview">Xem Kế hoạch Career Adapt</a><a class="btn btn-secondary" href="#/">Về Bảng điều khiển</a></div></section>`);
}

/** Entry point for every /flow route. A sub-route only opens if the server's step allows it. */
export async function renderFlow(sub = "") {
    const state = await api("/career-process/state");
    if (!state.run) { window.location.hash = "#/process"; return; }
    const step = state.run.step;
    const section = sub.split("/")[0];
    allowAssistantHere(step !== "EXAM");
    if (step === "EXAM" && ["SUBMITTED", "GRADING"].includes(state.exam_status)) {
        // Submitted: the server grades in the background and moves the step to RESULT when done.
        renderGradingWait(async () => (await api("/career-process/state")).run?.step !== "EXAM", () => renderFlow());
        return;
    }
    if (step === "EXAM" && state.exam_status === "IN_PROGRESS") {
        await renderExamRoom(await api("/career-process/exam"), () => { window.location.hash = "#/flow"; renderFlow(); });
        return;
    }
    if (section === "review" && ["RESULT", "ROADMAP", "DONE"].includes(step)) {
        stepBar(state);
        renderReview(await api("/career-process/exam/review"), { backHref: "#/flow", backLabel: "Quay lại kết quả" });
        return;
    }
    stepBar(state, step !== "DONE");
    if (step === "SKILLS") {
        if (sub === "skills/pick") return skillsPick();
        if (sub === "skills/import") return skillsImport();
        return skillsHome();
    }
    if (step === "JD") {
        if (sub === "jd/import") return jdImport();
        if (sub === "jd/library") return jdLibrary();
        if (sub.startsWith("jd/review/")) {
            const [, , id, version] = sub.split("/");
            return renderJdReview(id, Number(version), { flow: true });
        }
        return jdHome(state);
    }
    if (step === "EXAM") return examIntro(state);
    if (step === "RESULT") return resultStep();
    if (step === "ROADMAP") return roadmapStep(state);
    if (step === "DONE") return doneStep();
    setView(emptyView("Không xác định được bước", "Hãy tải lại trang."));
    return undefined;
}
