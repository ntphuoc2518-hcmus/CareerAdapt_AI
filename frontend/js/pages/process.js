/** Main screen: choose a career and enter the process. Only the server can start a run. */
import { alertBox, api, closeModal, esc, openModal, register, setView, toast, withBusy } from "../core.js";
import { icon } from "../icons.js";
import { pageHero } from "../hero.js";
import { guide, mountGuide } from "../guide.js";

const STATUS_TEXT = { IN_PROGRESS: "Đang thực hiện", COMPLETED: "Đã hoàn tất" };
const CAREER_ICONS = { DATA_ANALYST: "chart", BACKEND_DEVELOPER: "code", QA_TESTER: "flask" };

/** Shown before any reset: the exact data affected, then an explicit confirmation. */
export async function openResetDialog() {
    const preview = await api("/career-process/reset-preview");
    if (preview.exam_in_progress) { toast("Bài kiểm tra đang diễn ra. Hãy nộp bài trước khi reset.", "bad"); return; }
    openModal(`<h2>Reset Quy trình Career Adapt</h2><p class="prose">Quy trình ${esc(preview.career_title)} sẽ trở về con số 0. Các dữ liệu sau sẽ bị xóa khỏi tài khoản của bạn:</p>
        <ul class="reset-list">${preview.items.map(item => `<li><span>${esc(item.label)}</span><strong>${item.count}</strong></li>`).join("")}</ul>
        <p class="small" style="margin-top:10px"><strong>Không bị ảnh hưởng:</strong> ${esc(preview.kept.join("; "))}.</p>
        <p class="sub small" style="margin-top:6px">${esc(preview.archive_note)}</p>
        <form data-form="reset" class="stack-sm" style="margin-top:12px"><label class="check"><input type="checkbox" name="agree" id="reset-agree"> Tôi đã đọc và muốn reset quy trình</label>
        <div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-danger" type="submit" id="reset-go" disabled>Reset quy trình</button></div></form>`);
    document.getElementById("reset-agree").addEventListener("change", event => { document.getElementById("reset-go").disabled = !event.target.checked; });
    register({
        forms: {
            reset: async () => {
                const result = await api("/career-process/reset", { method: "POST", body: { confirm: true } });
                closeModal();
                toast(result.message, "good");
                if (window.location.hash === "#/process") renderProcess(); else window.location.hash = "#/process";
            },
        },
    });
}

/** Change the target JD while keeping verified levels: a lighter path than a reset. */
export async function openChangeGoalDialog() {
    openModal(`<h2>Đổi JD mục tiêu</h2><p class="prose">Bạn sẽ chọn một JD mới. Hệ thống tính lại khoảng cách kỹ năng và lập lại lộ trình theo JD đó.</p>
        <ul class="reset-list"><li><span>Mức kỹ năng đã xác thực, bài kiểm tra và bằng chứng</span><strong>Giữ nguyên</strong></li><li><span>Bài học đã đạt bài kiểm tra hoàn thành</span><strong>Giữ nguyên</strong></li><li><span>Thời gian học và lịch sử</span><strong>Giữ nguyên</strong></li><li><span>Lộ trình học tập</span><strong>Lập lại theo JD mới</strong></li></ul>
        <p class="sub small" style="margin-top:8px">Kỹ năng JD mới cần mà bạn chưa từng được đo sẽ hiện là "Chưa đánh giá" và được đo qua bài kiểm tra hoàn thành và bài đánh giá tổng hợp. Muốn làm lại toàn bộ từ đầu, dùng Reset.</p>
        <form data-form="goal" class="stack-sm" style="margin-top:12px"><div class="modal-actions"><button class="btn btn-secondary" type="button" data-close-modal>Hủy</button><button class="btn btn-primary" type="submit">Chọn JD mới</button></div></form>`);
    register({
        forms: {
            goal: async () => {
                await api("/career-process/change-goal", { method: "POST", body: { confirm: true } });
                closeModal();
                window.location.hash = "#/flow";
            },
        },
    });
}

function runPanel(run) {
    if (run.status === "COMPLETED") {
        return `${alertBox("info", `<strong>Bạn đã hoàn tất quy trình ${esc(run.career_title)}.</strong> Bạn có thể đổi JD mục tiêu mà vẫn giữ mức kỹ năng đã xác thực, hoặc reset để làm lại toàn bộ từ đầu.`)}
            <div class="row"><a class="btn btn-primary" href="#/plan/da/overview">${icon("chart")}<span>Xem Kế hoạch Career Adapt</span></a><button class="btn btn-secondary" data-act="goal">${icon("target")}<span>Đổi JD mục tiêu</span></button><button class="btn btn-danger" data-act="reset">${icon("refresh")}<span>Reset quy trình</span></button></div>`;
    }
    return `${alertBox("info", `<strong>Bạn đang làm dở quy trình ${esc(run.career_title)}.</strong> Hãy tiếp tục từ bước đang dừng.`)}
        <div class="row"><a class="btn btn-primary" href="#/flow">${icon("play")}<span>Tiếp tục quy trình</span></a><button class="btn btn-danger" data-act="reset">${icon("refresh")}<span>Reset quy trình</span></button></div>`;
}

/** What each step asks of the learner; the step names themselves come from the server. */
const STEP_INFO = [
    ["user", "Tự khai mức hiện tại để chọn độ khó bài kiểm tra."],
    ["file", "Chọn công việc nhắm tới; bài kiểm tra bám theo JD."],
    ["quiz", "Làm một lần, có đồng hồ; máy chấm theo test case."],
    ["chart", "Mức kỹ năng đã xác thực và khoảng cách với JD."],
    ["route", "Bài học xếp theo tuần, theo quỹ thời gian của bạn."],
    ["trophy", "Theo dõi tiến độ trong Kế hoạch Career Adapt."],
];

function timeline(state) {
    const current = state.run ? (state.run.status === "COMPLETED" ? state.steps.length : state.run.step_index) : -1;
    return `<section class="card ca-timeline"><h2>${icon("route")}<span>Các bước của quy trình</span></h2><ol>${state.steps.map((step, index) => {
        const [name, text] = STEP_INFO[index] || ["check", ""];
        const tone = index < current ? "is-done" : index === current ? "is-current" : "";
        return `<li class="${tone}" style="--i:${index}"><span class="ca-timeline-icon">${index < current ? icon("check") : icon(name)}</span><div><strong>${index + 1}. ${esc(step.label)}</strong><span class="sub small">${esc(text)}</span></div></li>`;
    }).join("")}</ol></section>`;
}

function processGuide(state) {
    const run = state.run;
    const ask = { question: "Quy trình Career Adapt gồm những bước nào và mình nên chuẩn bị gì trước khi bắt đầu?" };
    if (!run) {
        return guide({ title: "Chọn nghề để bắt đầu", ask,
            text: `Chào bạn! Mình là Trợ lý CareerAdapt AI. Mình sẽ đi cùng bạn qua ${state.steps.length} bước của quy trình. Hãy chọn nghề bạn muốn khám phá.`,
            tips: ["Chọn thẻ nghề bên dưới. Nghề có nhãn Sắp có chưa mở.", "Bấm Đi vào quy trình Career Adapt để bắt đầu bước 1.", "Các bước làm tuần tự; xong bước nào thì không quay lại sửa được."] });
    }
    if (run.status === "COMPLETED") {
        return guide({ title: "Bạn đã hoàn tất quy trình", ask,
            text: "Kết quả và lộ trình đã được lưu trong tài khoản của bạn. Bạn có thể xem Kế hoạch Career Adapt, đổi JD mục tiêu mà vẫn giữ mức đã xác thực, hoặc reset để làm lại từ đầu.",
            tips: ["Xem Kế hoạch Career Adapt để học theo lộ trình và theo dõi tiến độ.", "Đổi JD mục tiêu: giữ mức kỹ năng, bài kiểm tra và bài học đã đạt; lộ trình được lập lại.", "Reset: hệ thống cho bạn xem trước dữ liệu bị xóa trước khi xác nhận."] });
    }
    const label = state.steps[run.step_index]?.label || "";
    return guide({ title: "Tiếp tục từ bước đang dừng", ask,
        text: `Bạn đang ở bước ${run.step_index + 1}/${state.steps.length}: ${label}. Bấm Tiếp tục quy trình để làm tiếp.`,
        tips: ["Phần đã làm được lưu trên máy chủ, bạn không mất gì khi rời trang.", "Nếu muốn làm lại từ đầu, dùng Reset quy trình; hệ thống cho bạn xem trước dữ liệu bị xóa."] });
}

export async function renderProcess() {
    const state = await api("/career-process/state");
    let selected = state.run?.career_code || null;
    const open = state.careers.filter(item => item.status !== "SIMULATED").length;
    const status = state.run ? STATUS_TEXT[state.run.status] || state.run.status : "Chưa bắt đầu";
    setView(`<div class="stack process">${pageHero({ tone: "teal", icon: "journey", kicker: "Career Adapt", title: "Quy trình Career Adapt",
            text: "Đo năng lực bằng bài làm thật, so với JD bạn nhắm tới và lập lộ trình học theo tuần.",
            stats: [["route", "Bước", state.steps.length, "brand"], ["target", "Nghề đã mở", open, "good"], ["check", "Trạng thái", status, state.run?.status === "COMPLETED" ? "good" : "warn"]] })}
        ${processGuide(state)}
        <div class="ca-process-grid"><div class="stack" id="process-main"></div>${timeline(state)}</div></div>`);
    mountGuide(document.getElementById("view"));
    const draw = () => {
        const career = state.careers.find(item => item.career_code === selected);
        const other = state.run && selected !== state.run.career_code;
        document.getElementById("process-main").innerHTML = `<section class="card ca-careers-card"><h2>${icon("target")}<span>Chọn nghề</span></h2>
            <div class="career-grid" role="group" aria-label="Chọn nghề">${state.careers.map(item => `<button type="button" class="career ${item.career_code === selected ? "is-active" : ""} ${item.status === "SIMULATED" ? "is-soon" : ""}" data-act="pick" data-code="${esc(item.career_code)}" aria-pressed="${item.career_code === selected}"><span class="career-icon">${icon(CAREER_ICONS[item.career_code] || "target")}</span><span class="career-name"><strong>${esc(item.title)}</strong></span>${item.status === "SIMULATED" ? '<span class="badge badge-warn">Sắp có</span>' : state.run?.career_code === item.career_code ? `<span class="badge">${STATUS_TEXT[state.run.status]}</span>` : '<span class="badge badge-good">Đã mở</span>'}</button>`).join("")}</div></section>
            <section class="process-panel">${!career ? `<p class="sub ca-pick-hint">${icon("info")}<span>Chọn một nghề ở trên để xem bước tiếp theo.</span></p>` : career.status === "SIMULATED"
                ? alertBox("warn", `<strong>${esc(career.title)} chưa hoạt động.</strong> ${esc(career.summary)} Nút bên dưới chỉ mở khi nghề này có đủ dữ liệu.`) + '<div class="row"><button class="btn btn-primary" disabled>Đi vào quy trình Career Adapt</button></div>'
                : state.run && !other ? runPanel(state.run)
                : `${alertBox("info", "Quy trình gồm: báo cáo kỹ năng, chọn JD, làm bài kiểm tra một lần, xem kết quả, tạo lộ trình. Bạn phải làm tuần tự và không quay lại sửa được.")}<div class="row"><button class="btn btn-primary" data-act="enter">${icon("play")}<span>Đi vào quy trình Career Adapt</span></button></div>`}</section>`;
    };
    draw();
    register({
        actions: {
            pick: element => { selected = element.dataset.code; draw(); },
            enter: element => withBusy(element, async () => {
                await api("/career-process/runs", { method: "POST", body: { career_code: selected } });
                window.location.hash = "#/flow";
            }),
            reset: element => withBusy(element, openResetDialog),
            goal: element => withBusy(element, openChangeGoalDialog),
        },
    });
}
