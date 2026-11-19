/** The CareerAdapt AI guide of the Career Adapt process (5.42).
 *
 * A robot that blinks and "speaks" a short, fixed instruction for the screen the learner is on, with numbered
 * steps of what to do there. The words are written by the team and match the screen: the guide never decides,
 * scores or changes anything. Outside the test step, a button hands a question about the step to the real
 * Assistant (the server's AI, with the learner's own data); during the test step there is no such button and the
 * Assistant stays closed.
 */
import { esc } from "./core.js";
import { botBody } from "./bot.js";
import { expressiveHead } from "./faces.js";
import { icon } from "./icons.js";
import { translateText } from "./translate.js";
import { askAssistant } from "./assistant.js";

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * @param {object} options
 * @param {string} options.title  short heading of what to do now
 * @param {string} options.text   what the guide says (typed out on screen; screen readers get it whole)
 * @param {string[]} [options.tips] numbered steps on this screen
 * @param {string} [options.step] e.g. "Bước 1/6"
 * @param {{question?: string, task?: string, label?: string}} [options.ask] offers "Hỏi Trợ lý về bước này"
 * @param {string} [options.mood] the robot's expression (see faces.js), e.g. "joy" after a passed test
 */
export function guide({ title, text, tips = [], step = "", ask = null, mood = "happy" }) {
    const askButton = ask ? `<button type="button" class="btn btn-secondary btn-sm ca-guide-ask" data-guide-ask data-question="${esc(ask.question || "")}" data-task="${esc(ask.task || "")}" data-label="${esc(ask.label || "")}">${icon("chat")}<span>${esc(ask.button || "Hỏi Trợ lý về bước này")}</span></button>` : "";
    return `<section class="ca-guide" aria-label="Hướng dẫn của Trợ lý CareerAdapt AI">
        <div class="ca-guide-bot" aria-hidden="true"><span class="ca-guide-halo"></span>${expressiveHead(mood, "ca-guide-head")}<span class="ca-guide-voice"><i></i><i></i><i></i><i></i></span></div>
        <div class="ca-guide-bubble">
            <div class="ca-guide-meta"><span class="ca-guide-name">${icon("sparkles")}<strong>Trợ lý CareerAdapt AI</strong></span>${step ? `<span class="ca-guide-step">${esc(step)}</span>` : ""}</div>
            ${title ? `<h2 class="ca-guide-title">${esc(title)}</h2>` : ""}
            <p class="ca-guide-text"><span class="sr-only">${esc(text)}</span><span class="ca-guide-typed" aria-hidden="true" data-no-i18n data-text="${esc(text)}"></span></p>
            ${tips.length ? `<ol class="ca-guide-tips">${tips.map((tip, index) => `<li style="--i:${index}"><span class="ca-guide-num">${index + 1}</span><span>${esc(tip)}</span></li>`).join("")}</ol>` : ""}
            ${askButton}
        </div>
    </section>`;
}

/** Types the guide's words out and wires its "ask" button. Call once after the view is on screen. */
export function mountGuide(root = document) {
    root.querySelectorAll(".ca-guide").forEach(section => {
        const typed = section.querySelector(".ca-guide-typed");
        if (typed && !typed.dataset.done) {
            typed.dataset.done = "1";
            // In English the words are translated first, then typed; the visible copy is not translated again.
            const full = translateText(typed.dataset.text || "");
            if (reduced() || !full) {
                typed.textContent = full;
            } else {
                section.classList.add("is-talking");
                const step = Math.max(1, Math.ceil(full.length / 70));
                let shown = 0;
                const timer = setInterval(() => {
                    shown = Math.min(full.length, shown + step);
                    typed.textContent = full.slice(0, shown);
                    if (shown >= full.length || !typed.isConnected) {
                        clearInterval(timer);
                        typed.textContent = full;
                        section.classList.remove("is-talking");
                    }
                }, 18);
            }
        }
        section.querySelector("[data-guide-ask]")?.addEventListener("click", event => {
            const button = event.currentTarget;
            // The question goes out in the language on screen, like a question the learner typed.
            askAssistant(translateText(button.dataset.question), button.dataset.task || null, translateText(button.dataset.label || ""));
        });
    });
}

/** The whole robot, waving among sparkles: the finish screen of the process. */
export function celebrationBot() {
    const spark = '<svg viewBox="0 0 24 24"><path d="M12 1.5 13.9 9.6 22 12l-8.1 2.4L12 22.5l-1.9-8.1L2 12l8.1-2.4Z"/></svg>';
    return `<div class="ca-celebrate" aria-hidden="true"><span class="ca-celebrate-ring"></span>
        <span class="ca-confetti">${Array.from({ length: 14 }, (unused, index) => `<i style="--k:${index}"></i>`).join("")}</span>
        <span class="chat-spark is-a">${spark}</span><span class="chat-spark is-b">${spark}</span><span class="chat-spark is-c">${spark}</span>
        <span class="as-bot ca-celebrate-bot"><span class="as-bot-halo"></span>${botBody("cg", "as-bot-body")}${expressiveHead("celebrate", "as-bot-head")}<span class="as-bot-shadow"></span></span></div>`;
}
