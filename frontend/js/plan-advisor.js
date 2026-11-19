/** The AI advisor strip of the Career Adapt Plan (5.47).
 *
 * One compact card per section, under the section's hero: the CareerAdapt AI robot says what this section is for and
 * offers a few questions about it. Every button hands the question to the real Assistant (the server's AI tasks and
 * tools, reading only the learner's own data; rule-based answers when no model is available). The strip itself never
 * computes, scores or changes anything, and its words are fixed per section.
 */
import { esc } from "./core.js";
import { expressiveHead } from "./faces.js";
import { icon } from "./icons.js";
import { translateText } from "./translate.js";
import { askAssistant } from "./assistant.js";

/* task: one of the server's AI tasks (backend/ai_service/task_engine.py); question: sent like a typed question. */
const ADVICE = {
    overview: {
        role: "Cố vấn nghề nghiệp",
        text: "Tôi có thể tóm tắt hành trình của bạn, giải thích JD mục tiêu và gợi ý việc nên làm tiếp.",
        asks: [
            { task: "journey_report", label: "Tổng hợp hành trình của tôi", icon: "route" },
            { task: "jd_analysis", label: "Phân tích JD của tôi", icon: "file" },
            { question: "Dựa trên hành trình của tôi, tôi nên làm gì tiếp theo?", label: "Tôi nên làm gì tiếp theo?", icon: "arrow" },
        ],
    },
    exam: {
        role: "Cố vấn kỹ năng",
        text: "Tôi giải thích điểm và mức kỹ năng hệ thống đã chấm. Điểm do bộ chấm tính, tôi không thay đổi được.",
        asks: [
            { task: "explain_result", label: "Giải thích kết quả đánh giá", icon: "quiz" },
            { question: "Kỹ năng nào trong bài kiểm tra tôi cần cải thiện trước, và vì sao?", label: "Tôi cần cải thiện kỹ năng nào trước?", icon: "target" },
        ],
    },
    gap: {
        role: "Cố vấn kỹ năng",
        text: "Tôi đọc khoảng cách kỹ năng của bạn so với JD và giải thích kỹ năng nào ảnh hưởng nhiều nhất.",
        asks: [
            { task: "skill_analysis", label: "Phân tích kỹ năng của tôi", icon: "pulse" },
            { task: "readiness_advice", label: "Tư vấn mức sẵn sàng", icon: "shield" },
        ],
    },
    roadmap: {
        role: "Cố vấn lộ trình",
        text: "Tôi giải thích thứ tự các tuần học và gợi ý bài nên học tiếp từ học liệu đã duyệt.",
        asks: [
            { task: "learning_guide", label: "Tôi nên học gì tiếp theo?", icon: "play" },
            { task: "explain_roadmap", label: "Giải thích lộ trình", icon: "route" },
            { question: "Dựa trên lộ trình hiện tại, tôi nên sắp xếp việc học tuần này thế nào để theo kịp lịch?", label: "Sắp xếp việc học tuần này", icon: "calendar" },
        ],
    },
    rank: {
        role: "Cố vấn sẵn sàng ứng tuyển",
        text: "Tôi giải thích vị trí của bạn và kỹ năng nào giúp cải thiện thứ hạng. Thứ hạng do hệ thống tính.",
        asks: [
            { task: "readiness_advice", label: "Tư vấn mức sẵn sàng", icon: "shield" },
            { question: "Khoảng cách kỹ năng nào giúp tôi cải thiện thứ hạng nhiều nhất?", label: "Làm sao để tăng thứ hạng?", icon: "trophy" },
        ],
    },
    progress: {
        role: "Cố vấn tiến độ",
        text: "Tôi giúp bạn chọn việc cần làm trước trong danh sách nhắc nhở, lịch ôn và mini-test.",
        asks: [
            { question: "Trong các nhắc nhở và tiến độ học của tôi, việc nào nên làm trước?", label: "Việc nào nên làm trước?", icon: "bell" },
            { task: "learning_guide", label: "Tôi nên học gì tiếp theo?", icon: "play" },
        ],
    },
};

export function planAdvisor(section) {
    const advice = ADVICE[section];
    if (!advice) return "";
    const chips = advice.asks.map((ask, index) => `<button type="button" class="pa-ask" data-pa-index="${index}">${icon(ask.icon)}<span>${esc(ask.label)}</span></button>`).join("");
    return `<section class="pa-card" data-pa-section="${esc(section)}" aria-label="Trợ lý AI của mục này">
        <div class="pa-bot" aria-hidden="true"><span class="pa-halo"></span>${expressiveHead("happy", "pa-head")}</div>
        <div class="pa-body">
            <p class="pa-meta">${icon("sparkles")}<strong>Trợ lý CareerAdapt AI</strong><span class="pa-role">${esc(advice.role)}</span></p>
            <p class="pa-text">${esc(advice.text)}</p>
            <div class="pa-asks">${chips}<button type="button" class="pa-ask is-open" data-pa-open>${icon("chat")}<span>Hỏi điều khác</span></button></div>
        </div>
    </section>`;
}

/** Puts the strip right under the section's hero (once per drawn page) and wires its buttons. */
export function mountPlanAdvisor(root, section) {
    if (!root || root.querySelector(":scope > .pa-card") || !ADVICE[section]) return;
    const hero = root.querySelector(":scope > .page-hero, :scope > .rk-hero");
    const holder = document.createElement("div");
    holder.innerHTML = planAdvisor(section);
    const card = holder.firstElementChild;
    if (hero) hero.after(card); else root.prepend(card);
    card.addEventListener("click", event => {
        const button = event.target.closest(".pa-ask");
        if (!button) return;
        if (button.hasAttribute("data-pa-open")) { askAssistant("", null, ""); return; }
        const ask = ADVICE[section].asks[Number(button.dataset.paIndex)];
        if (!ask) return;
        // Sent in the language on screen, like a question the learner typed.
        if (ask.task) askAssistant(translateText(ask.label), ask.task, translateText(ask.label));
        else askAssistant(translateText(ask.question));
    });
}
