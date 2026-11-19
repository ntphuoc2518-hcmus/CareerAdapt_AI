/**
 * Motion and feedback layer: cards rise in as they enter the view, figures count up to their value, meters fill,
 * buttons ripple where they are pressed, plus a scroll progress line and a back-to-top button.
 * Purely visual: a count-up always ends on the exact original text, and nothing runs when the person asks the
 * system for reduced motion. Pages need no changes; new content in #view is picked up automatically.
 */
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
const COUNT_SELECTOR = ".stat-value, .rd-metric strong, .ring > div > strong, .gap-count b, .level-fact strong, .rm-stat b, .progress-row strong";
const CARD_SELECTOR = ".card, .lesson, .self-skill, .review-topics li";
const RIPPLE_SELECTOR = ".btn, .tab, .nav-link, .seg-option, .gap-row, .icon-btn, .link-card, .rd-flag";

let revealer = null;

/** "25%", "13", "0/4", "30.8%" count up; anything else (dates, words) is left alone. */
function countUp(element) {
    if (element.dataset.fxCounted) return;
    element.dataset.fxCounted = "1";
    const original = element.textContent.trim();
    const match = original.match(/^(\d+(?:[.,]\d+)?)(%|\/\d+)?$/) || original.match(/^(\d+(?:[.,]\d+)?)(%|\/\d+)? (\S+(?: \S+)?)$/);
    if (!match || element.children.length) return;
    const target = parseFloat(match[1].replace(",", "."));
    if (!target) return;
    const decimals = (match[1].split(/[.,]/)[1] || "").length;
    const separator = match[1].includes(",") ? "," : ".";
    const rest = original.slice(match[1].length);
    const started = performance.now();
    const duration = 700;
    const step = now => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        if (progress < 1) {
            element.textContent = (target * eased).toFixed(decimals).replace(".", separator) + rest;
            requestAnimationFrame(step);
        } else {
            element.textContent = original;
        }
    };
    requestAnimationFrame(step);
}

/** Meters and rings start empty and fill to the width or arc the page already set. */
function fill(root) {
    root.querySelectorAll(".meter > span[style*='width']").forEach(bar => {
        if (bar.dataset.fxFilled) return;
        bar.dataset.fxFilled = "1";
        const width = bar.style.width;
        bar.style.width = "0";
        requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = width; }));
    });
    root.querySelectorAll(".ring-bar").forEach(ring => {
        if (ring.dataset.fxFilled) return;
        ring.dataset.fxFilled = "1";
        const dash = ring.getAttribute("stroke-dasharray") || "";
        const total = dash.split(" ")[1];
        if (!total) return;
        ring.setAttribute("stroke-dasharray", `0 ${total}`);
        requestAnimationFrame(() => requestAnimationFrame(() => ring.setAttribute("stroke-dasharray", dash)));
    });
}

function reveal(root) {
    const cards = [...root.querySelectorAll(CARD_SELECTOR)].filter(card => !card.dataset.fxSeen && !card.closest(".modal"));
    if (!revealer) {
        cards.forEach(card => card.querySelectorAll(COUNT_SELECTOR).forEach(countUp));
        return;
    }
    cards.forEach(card => { card.dataset.fxSeen = "1"; card.classList.add("fx-hidden"); revealer.observe(card); });
}

function enhance(root) {
    if (reduced.matches) return;
    reveal(root);
    fill(root);
}

function ripple(event) {
    if (reduced.matches || event.button !== 0) return;
    const host = event.target.closest(RIPPLE_SELECTOR);
    if (!host || host.disabled) return;
    // The ripple sits in its own clipped layer, so badges that stick out of a button are never cut off.
    if (window.getComputedStyle(host).position === "static") host.classList.add("fx-ripple-host");
    let clip = host.querySelector(":scope > .fx-ripple-clip");
    if (!clip) {
        clip = document.createElement("span");
        clip.className = "fx-ripple-clip";
        clip.setAttribute("aria-hidden", "true");
        host.append(clip);
    }
    const box = host.getBoundingClientRect();
    const size = Math.max(box.width, box.height) * 1.4;
    const dot = document.createElement("span");
    dot.className = "fx-ripple";
    dot.style.cssText = `width:${size}px;height:${size}px;left:${event.clientX - box.left - size / 2}px;top:${event.clientY - box.top - size / 2}px`;
    clip.append(dot);
    dot.addEventListener("animationend", () => dot.remove());
}

function scrollAids() {
    const topbar = document.querySelector(".topbar");
    const line = document.createElement("div");
    line.className = "fx-scroll-line";
    line.setAttribute("aria-hidden", "true");
    topbar?.append(line);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "fx-top";
    button.setAttribute("aria-label", "Lên đầu trang");
    button.title = "Lên đầu trang";
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';
    button.addEventListener("click", () => window.scrollTo({ top: 0, behavior: reduced.matches ? "auto" : "smooth" }));
    document.body.append(button);
    let queued = false;
    const update = () => {
        queued = false;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        const ratio = max > 0 ? Math.min(1, window.scrollY / max) : 0;
        line.style.transform = `scaleX(${ratio})`;
        button.classList.toggle("is-shown", window.scrollY > 480);
    };
    window.addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(update); } }, { passive: true });
    window.addEventListener("hashchange", () => requestAnimationFrame(update));
    update();
}

export function initEffects() {
    if ("IntersectionObserver" in window) {
        let batch = 0;
        let timer = null;
        revealer = new IntersectionObserver(entries => {
            entries.filter(entry => entry.isIntersecting).forEach(entry => {
                const card = entry.target;
                revealer.unobserve(card);
                // Cards that appear together rise one after another.
                card.style.setProperty("--fx-delay", `${Math.min(batch, 8) * 55}ms`);
                batch += 1;
                card.classList.remove("fx-hidden");
                card.classList.add("fx-in");
                card.addEventListener("animationend", () => card.classList.remove("fx-in"), { once: true });
                card.querySelectorAll(COUNT_SELECTOR).forEach(countUp);
                clearTimeout(timer);
                timer = setTimeout(() => { batch = 0; }, 120);
            });
        }, { rootMargin: "0px 0px -6% 0px", threshold: 0.05 });
    }
    const view = document.getElementById("view");
    // Count-ups change text every frame; one pass per frame is enough to pick up newly rendered content.
    let pending = false;
    if (view) new MutationObserver(() => { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; enhance(view); }); } }).observe(view, { childList: true, subtree: true });
    document.addEventListener("pointerdown", ripple);
    scrollAids();
    enhance(document);
}
