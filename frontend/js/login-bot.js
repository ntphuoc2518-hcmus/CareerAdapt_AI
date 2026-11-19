/* CareerAdapt AI robot on the sign-in page (5.38).
 *
 * It only reacts to what the page already does; it never changes the form or decides anything:
 * - greets per form (sign in, create account, forgot, reset);
 * - looks toward the pointer, and toward the field being filled;
 * - closes its eyes while a password is typed, opens them if the password is shown;
 * - thinks while a request runs, shakes its head on an error, hops on a success message;
 * - warns about Caps Lock.
 * Everything is decorative (aria-hidden): the form message box stays what screen readers announce.
 */
import { faceSvg, setExpression } from "./faces.js";

(() => {
    const bot = document.querySelector(".login-bot");
    if (!bot) return;
    // 5.43: the face is drawn on the head's empty visor and changes with what happens on the page.
    const head = bot.querySelector(".login-bot-face");
    head?.insertAdjacentHTML("beforeend", faceSvg("happy"));
    const feel = expression => setExpression(head, expression);
    const text = bot.querySelector(".login-bot-text");
    const bubble = bot.querySelector(".login-bot-bubble");
    const act = bot.querySelector(".login-bot-act");
    const look = bot.querySelector(".login-bot-look");
    const message = document.getElementById("login-message");
    const forms = ["login", "register", "forgot", "reset"].map(name => [name, document.getElementById(`${name}-form`)]).filter(([, form]) => form);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const ACTIONS = ["do-hop", "do-shake", "do-nod", "do-think"];
    const GREETING = { login: "login.bot.hello", register: "login.bot.register", forgot: "login.bot.forgot", reset: "login.bot.reset" };
    const FIELD_LINES = {
        "login-email": "login.bot.email", "register-email": "login.bot.emailNew", "forgot-email": "login.bot.emailForgot",
        "register-name": "login.bot.name"
    };
    const tr = key => (window.i18n ? window.i18n.t(key) : key);

    let saying = null;
    let tone = "";
    let focused = null;
    let settleTimer = 0;
    let nodAt = 0;

    function say(key, nextTone = "") {
        if (key === saying && nextTone === tone) return;
        saying = key;
        tone = nextTone;
        text.textContent = tr(key);
        bubble.dataset.tone = tone;
        // Replay the pop each time the line changes (the first line uses the entrance instead).
        if (!bot.classList.contains("is-ready")) return;
        bubble.classList.remove("is-pop");
        void bubble.offsetWidth;
        bubble.classList.add("is-pop");
    }

    function play(action) {
        if (reduced.matches && action !== "do-think") return;
        act.classList.remove(...ACTIONS);
        void act.offsetWidth;
        act.classList.add(action);
    }
    act.addEventListener("animationend", event => {
        if (event.target === act && event.animationName !== "bot-think") act.classList.remove(...ACTIONS);
    });

    function eyes(state) {
        // Eyes closed (shy) while a password is typed, joy for a moment after a success, otherwise a happy face.
        bot.dataset.eyes = state || "";
        feel({ closed: "shy", happy: "joy" }[state] || "happy");
    }

    function mode() {
        const open = forms.find(([, form]) => !form.hidden);
        return open ? open[0] : "login";
    }

    function aim(x, y, tilt) {
        look.style.setProperty("--look-x", `${x.toFixed(1)}px`);
        look.style.setProperty("--look-y", `${y.toFixed(1)}px`);
        look.style.setProperty("--tilt", `${tilt.toFixed(1)}deg`);
    }

    function aimAt(element) {
        if (!element || reduced.matches) return aim(0, 0, 0);
        const from = bot.querySelector(".login-bot-stage").getBoundingClientRect();
        const to = element.getBoundingClientRect();
        const dx = (to.left + to.width / 2) - (from.left + from.width / 2);
        const dy = (to.top + to.height / 2) - (from.top + from.height / 2);
        const length = Math.hypot(dx, dy) || 1;
        aim(dx / length * 6, dy / length * 5, Math.max(-9, Math.min(9, dx / length * 9)));
    }

    function settle() {
        // Back to the greeting of the open form once nothing is focused and nothing is pending.
        clearTimeout(settleTimer);
        settleTimer = setTimeout(() => {
            if (focused || (message && !message.hidden)) return;
            eyes("");
            say(GREETING[mode()]);
            aim(0, 0, 0);
        }, 900);
    }

    // --- Fields ----------------------------------------------------------------------------
    function onFocus(input) {
        focused = input;
        clearTimeout(settleTimer);
        aimAt(input);
        if (input.dataset.botPassword !== undefined) {
            if (input.type === "password") {
                eyes("closed");
                say("login.bot.password");
            } else {
                eyes("");
                feel("surprised");
                say("login.bot.peek", "warn");
            }
            return;
        }
        eyes("");
        say(FIELD_LINES[input.id] || GREETING[mode()]);
    }

    document.querySelectorAll(".login-form input").forEach(input => {
        if (input.autocomplete.includes("password")) input.dataset.botPassword = "";
        input.addEventListener("focus", () => onFocus(input));
        input.addEventListener("blur", () => { if (focused === input) focused = null; settle(); });
        input.addEventListener("input", () => {
            // A small nod while typing in a visible field, at most a few times a second.
            if (input.type === "password" || performance.now() - nodAt < 380) return;
            nodAt = performance.now();
            play("do-nod");
        });
        if (input.dataset.botPassword !== undefined) {
            // The eye button switches type between password and text.
            new MutationObserver(() => { if (focused === input || document.activeElement?.dataset?.togglePassword === input.id) onFocus(input); })
                .observe(input, { attributes: true, attributeFilter: ["type"] });
        }
    });

    // Caps Lock hint (shown by login.js) becomes a spoken warning.
    document.querySelectorAll("[data-caps-for]").forEach(hint => {
        new MutationObserver(() => {
            if (!hint.hidden) { feel("surprised"); say("login.bot.caps", "warn"); }
            else if (focused) onFocus(focused);
        }).observe(hint, { attributes: true, attributeFilter: ["hidden"] });
    });

    // --- Requests and results ----------------------------------------------------------------
    document.querySelectorAll(".login-submit").forEach(button => {
        new MutationObserver(() => {
            if (button.classList.contains("is-loading")) {
                eyes("");
                feel("thinking");
                say("login.bot.checking");
                play("do-think");
            } else {
                act.classList.remove("do-think");
            }
        }).observe(button, { attributes: true, attributeFilter: ["class"] });
    });

    if (message) {
        new MutationObserver(() => {
            if (message.hidden || !message.textContent.trim()) return;
            if (message.classList.contains("is-error")) {
                eyes("");
                feel("worried");
                say("login.bot.error", "bad");
                play("do-shake");
            } else {
                eyes("happy");
                say("login.bot.success", "good");
                play("do-hop");
                setTimeout(() => { if (bot.dataset.eyes === "happy") eyes(""); }, 1600);
            }
        }).observe(message, { attributes: true, attributeFilter: ["hidden", "class"], childList: true, characterData: true, subtree: true });
    }

    // Switching between the forms changes the greeting.
    forms.forEach(([, form]) => new MutationObserver(() => {
        if (form.hidden) return;
        focused = document.activeElement?.closest?.(".login-form") === form && document.activeElement.tagName === "INPUT" ? document.activeElement : null;
        if (focused) onFocus(focused);
        else { eyes(""); say(GREETING[mode()]); }
    }).observe(form, { attributes: true, attributeFilter: ["hidden"] }));

    // --- Pointer: the robot glances toward the mouse when no field is being filled -----------
    let frame = 0;
    document.addEventListener("pointermove", event => {
        if (focused || reduced.matches || !finePointer.matches || frame) return;
        frame = requestAnimationFrame(() => {
            frame = 0;
            const box = bot.querySelector(".login-bot-stage").getBoundingClientRect();
            const dx = event.clientX - (box.left + box.width / 2);
            const dy = event.clientY - (box.top + box.height / 2);
            const reach = Math.max(260, Math.hypot(dx, dy));
            aim(dx / reach * 6, dy / reach * 5, dx / reach * 8);
        });
    }, { passive: true });
    document.addEventListener("pointerleave", () => { if (!focused) aim(0, 0, 0); });

    // Hovering the robot makes it hop once (a small reward for noticing it).
    bot.querySelector(".login-bot-stage").addEventListener("pointerenter", () => { if (!focused) play("do-hop"); });

    // --- Language switch: say the same line in the new language --------------------------------
    if (window.i18n) window.i18n.onChange(() => { if (saying) text.textContent = tr(saying); });

    // First line: the open form's greeting (the reset link opens the reset form directly).
    say(GREETING[mode()]);
    requestAnimationFrame(() => bot.classList.add("is-ready"));
})();
