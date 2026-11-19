/**
 * Room to work (5.58): the main navy rail and the Kế hoạch Career Adapt menu can each fold into a narrow column of
 * icons. Each choice is kept in this browser (localStorage) and applied by boot.js before the first paint, so the
 * page never jumps. Below 821px the rail is a drawer and below 1200px the plan menu is a row, so the buttons are
 * hidden there.
 *
 * 5.58.1: a folded item shows its name in the app's own tooltip (beside the icon, with a pointer), not the
 * browser's plain title box. It appears on hover and on keyboard focus; the name stays in the link for screen
 * readers, so the tooltip itself is hidden from them.
 */
const KEYS = { side: "careeradapt_side_collapsed", plan: "careeradapt_plan_menu_collapsed" };
const CLASSES = { side: "side-collapsed", plan: "plan-menu-collapsed" };
const LABELS = {
    side: ["Thu gọn thanh bên", "Mở rộng thanh bên"],
    plan: ["Thu gọn menu", "Mở rộng menu"],
};
const TIP_TARGETS = "#nav .nav-link[data-tip], #subnav .pn-item[data-tip], [data-tip-button][data-tip]";

const isCollapsed = which => document.documentElement.classList.contains(CLASSES[which]);

function save(which, collapsed) {
    try { localStorage.setItem(KEYS[which], collapsed ? "1" : "0"); } catch { /* The choice then lasts for this page only. */ }
}

/** Folded links carry their on-screen name for the tooltip; open links show the name already. */
function nameTips(selector, labelSelector, on) {
    document.querySelectorAll(selector).forEach(link => {
        const name = link.querySelector(labelSelector)?.textContent.trim();
        link.removeAttribute("title");
        if (on && name) link.dataset.tip = name;
        else delete link.dataset.tip;
    });
}

function markButton(button, which) {
    if (!button) return;
    const collapsed = isCollapsed(which);
    const label = LABELS[which][collapsed ? 1 : 0];
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", label);
    button.removeAttribute("title");
    button.dataset.tipButton = "";
    const text = button.querySelector("[data-toggle-text]");
    if (text) text.textContent = label;
    // The label is set in Vietnamese and translated on the page; read it back on the next frame for the tooltip.
    requestAnimationFrame(() => { button.dataset.tip = button.getAttribute("aria-label") || label; });
}

/** Called after the plan page draws its menu, so a new menu picks up the current state. */
export function syncPlanMenu() {
    markButton(document.querySelector("[data-plan-menu-toggle]"), "plan");
    nameTips("#subnav .pn-item", ":scope > span:not(.pn-soon)", isCollapsed("plan"));
}

export function syncRail() {
    markButton(document.getElementById("rail-btn"), "side");
    nameTips("#nav .nav-link", ":scope > span", isCollapsed("side"));
}

function toggle(which) {
    const collapsed = !isCollapsed(which);
    document.documentElement.classList.toggle(CLASSES[which], collapsed);
    save(which, collapsed);
    hideTip();
    if (which === "side") syncRail(); else syncPlanMenu();
}

/* --- Tooltip: one element for the whole page, placed beside the item (or below a toolbar button). --- */
let tip = null;
let current = null;

function hideTip() {
    current = null;
    if (tip) tip.classList.remove("is-shown");
}

function showTip(target) {
    const text = target.dataset.tip;
    // Only folded items and the fold buttons have a tip; the plan fold button shows its words while the menu is open.
    if (!text || (target.matches(".pn-fold") && !isCollapsed("plan"))) return;
    current = target;
    tip.textContent = text;
    const box = target.getBoundingClientRect();
    const below = target.hasAttribute("data-tip-button") && target.id === "rail-btn";
    tip.dataset.side = below ? "bottom" : "right";
    tip.classList.add("is-measuring");
    const width = tip.offsetWidth;
    const height = tip.offsetHeight;
    tip.classList.remove("is-measuring");
    let left = below ? box.left + box.width / 2 - width / 2 : box.right + 12;
    let top = below ? box.bottom + 10 : box.top + box.height / 2 - height / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
    // The pointer stays on the item even when the box is pushed back inside the window.
    tip.style.setProperty("--tip-arrow", below ? `${Math.round(box.left + box.width / 2 - left)}px` : `${Math.round(box.top + box.height / 2 - top)}px`);
    tip.classList.add("is-shown");
}

function initTip() {
    tip = document.createElement("div");
    tip.className = "nav-tip";
    tip.setAttribute("aria-hidden", "true");
    document.body.append(tip);
    document.addEventListener("pointerover", event => {
        const target = event.target.closest?.(TIP_TARGETS);
        if (target && target !== current) showTip(target);
        else if (!target && current) hideTip();
    });
    document.addEventListener("focusin", event => {
        const target = event.target.closest?.(TIP_TARGETS);
        if (target && target.matches(":focus-visible")) showTip(target); else hideTip();
    });
    document.addEventListener("focusout", hideTip);
    document.addEventListener("pointerdown", hideTip);
    document.addEventListener("keydown", event => { if (event.key === "Escape") hideTip(); });
    window.addEventListener("scroll", hideTip, { passive: true, capture: true });
    window.addEventListener("hashchange", hideTip);
}

export function initLayout() {
    document.getElementById("rail-btn")?.addEventListener("click", () => toggle("side"));
    // The plan menu is redrawn on every route, so its button is found through the menu holder.
    document.getElementById("subnav")?.addEventListener("click", event => {
        if (event.target.closest("[data-plan-menu-toggle]")) toggle("plan");
    });
    initTip();
    syncRail();
}
