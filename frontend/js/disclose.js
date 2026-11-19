/** Key information first, details on request, for the Career Adapt Plan (5.44, revised 5.45).
 *
 * A section's page is drawn as before; then its supporting blocks are moved, unchanged, into panels that open from a
 * "Xem thêm chi tiết" row of buttons. The section's main block is left where it is, above the buttons. Only one panel is open at a time, and the page remembers the open one for
 * this tab. Nothing is copied or re-rendered, so every button, form and listener inside keeps working. Blocks no
 * group claims (an urgent alert, a running study session) stay visible above the buttons.
 */
import { esc } from "./core.js";
import { icon } from "./icons.js";

const storeKey = key => `plan-open:${key}`;
const remember = (key, id) => { try { if (id) sessionStorage.setItem(storeKey(key), id); else sessionStorage.removeItem(storeKey(key)); } catch { /* storage may be blocked */ } };
const recall = key => { try { return sessionStorage.getItem(storeKey(key)); } catch { return null; } };
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function setOpen(root, key, id, { scroll = true } = {}) {
    root.querySelectorAll(":scope > .pl-deck .pl-tile").forEach(button => {
        const open = button.dataset.panel === id;
        button.setAttribute("aria-expanded", String(open));
        button.classList.toggle("is-open", open);
    });
    let shown = null;
    root.querySelectorAll(":scope > .pl-panels > .pl-panel").forEach(panel => {
        panel.hidden = panel.dataset.panel !== id;
        if (!panel.hidden) shown = panel;
    });
    remember(key, id);
    if (shown && scroll) {
        const top = shown.getBoundingClientRect().top;
        if (top < 70 || top > window.innerHeight * 0.75) shown.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
    }
    if (shown) window.dispatchEvent(new Event("resize")); // charts that size themselves redraw now that they can be seen
}

/**
 * @param {HTMLElement} root  the page's stack (the element setView filled)
 * @param {string} key        remembers the open panel per section
 * @param {{id: string, title: string, hint: string, icon: string, tone?: string, match: (el: Element) => boolean}[]} groups
 */
export function disclose(root, key, groups) {
    if (!root || root.dataset.disclosed) return;
    root.dataset.disclosed = "1";
    const children = [...root.children];
    const hero = children.find(child => child.matches(".page-hero"));
    const claimed = new Set();
    const used = groups.map(group => {
        const blocks = children.filter(child => child !== hero && !claimed.has(child) && group.match(child));
        blocks.forEach(block => claimed.add(block));
        return { ...group, blocks };
    }).filter(group => group.blocks.length);
    if (!used.length) return;

    const deck = document.createElement("nav");
    deck.className = "pl-deck";
    deck.setAttribute("aria-label", "Thông tin trong mục này");
    deck.innerHTML = `<p class="pl-deck-label">${icon("sparkles")}<span>Xem thêm chi tiết</span></p>` + used.map((group, index) => `<button type="button" class="pl-tile is-${group.tone || ["brand", "violet", "teal", "amber"][index % 4]}" data-panel="${esc(group.id)}" id="pl-btn-${esc(key)}-${esc(group.id)}" aria-expanded="false" aria-controls="pl-${esc(key)}-${esc(group.id)}">
        <span class="pl-tile-icon">${icon(group.icon)}</span><span class="pl-tile-text"><strong>${esc(group.title)}</strong><span>${esc(group.hint)}</span></span><span class="pl-tile-go" aria-hidden="true">${icon("arrow")}</span></button>`).join("");
    const host = document.createElement("div");
    host.className = "pl-panels";
    used.forEach(group => {
        const panel = document.createElement("section");
        panel.className = "pl-panel";
        panel.dataset.panel = group.id;
        panel.id = `pl-${key}-${group.id}`;
        panel.hidden = true;
        panel.setAttribute("aria-labelledby", `pl-btn-${key}-${group.id}`);
        // The cards inside carry their own titles; the panel only adds a way to close it.
        panel.innerHTML = `<div class="pl-panel-body"></div><div class="pl-panel-foot"><button type="button" class="btn btn-ghost btn-sm" data-pl-close aria-label="Thu gọn ${esc(group.title)}">${icon("arrow")}<span>Thu gọn</span></button></div>`;
        const body = panel.querySelector(".pl-panel-body");
        group.blocks.forEach(block => body.append(block));
        host.append(panel);
    });
    // Unclaimed blocks (alerts, a running session) sit just above the buttons so they stay in view.
    const anchor = hero ? hero.nextSibling : root.firstChild;
    root.insertBefore(deck, anchor);
    root.insertBefore(host, deck.nextSibling);
    children.filter(child => child !== hero && !claimed.has(child) && child.parentElement === root && children.indexOf(child) > children.indexOf(hero))
        .forEach(child => root.insertBefore(child, deck));

    deck.addEventListener("click", event => {
        const button = event.target.closest(".pl-tile");
        if (!button) return;
        setOpen(root, key, button.getAttribute("aria-expanded") === "true" ? null : button.dataset.panel);
    });
    host.addEventListener("click", event => {
        if (!event.target.closest("[data-pl-close]")) return;
        const id = event.target.closest(".pl-panel").dataset.panel;
        setOpen(root, key, null, { scroll: false });
        root.querySelector(`.pl-tile[data-panel="${CSS.escape(id)}"]`)?.focus();
    });
    const saved = recall(key);
    if (saved && used.some(group => group.id === saved)) setOpen(root, key, saved, { scroll: false });
}

/** Opens the panel that holds ``element`` (for links inside a page that point at a hidden block). */
export function revealPanelOf(element) {
    const panel = element?.closest?.(".pl-panel");
    if (!panel || !panel.hidden) return;
    const root = panel.closest(".pl-panels")?.parentElement;
    const button = root?.querySelector(`:scope > .pl-deck .pl-tile[data-panel="${CSS.escape(panel.dataset.panel)}"]`);
    button?.click();
}
