/** Question inputs shared by mini-tests and the Test Center. */
import { esc } from "../core.js";

export function questionInput(item, saved = null) {
    const name = `item_${esc(item.item_id)}`;
    if (item.type === "single" || item.type === "multiple") {
        const kind = item.type === "single" ? "radio" : "checkbox";
        const chosen = Array.isArray(saved) ? saved : [saved];
        return item.options.map(option => `<label class="option"><input type="${kind}" name="${name}" value="${esc(option.id)}" ${chosen.includes(option.id) ? "checked" : ""}><span>${esc(option.text)}</span></label>`).join("");
    }
    if (item.type === "numeric") {
        return `<label class="field"><span>Đáp án${item.unit ? ` (${esc(item.unit)})` : ""}</span><input class="input" name="${name}" inputmode="decimal" autocomplete="off" value="${esc(saved ?? "")}" style="max-width:240px"></label>`;
    }
    const order = Array.isArray(saved) && saved.length ? saved.map(id => item.options.find(option => option.id === id)).filter(Boolean) : item.options;
    return `<ol class="stack-sm" data-ordering="${esc(item.item_id)}">${order.map(option => `<li class="option" data-option="${esc(option.id)}"><span style="flex:1">${esc(option.text)}</span><button type="button" class="btn btn-ghost btn-sm" data-move="-1" aria-label="Chuyển lên">↑</button><button type="button" class="btn btn-ghost btn-sm" data-move="1" aria-label="Chuyển xuống">↓</button></li>`).join("")}</ol><p class="sub small">Sắp xếp theo thứ tự đúng bằng các nút mũi tên.</p>`;
}

export function readAnswer(root, item) {
    const name = `item_${item.item_id}`;
    if (item.type === "single") return root.querySelector(`[name="${name}"]:checked`)?.value ?? null;
    if (item.type === "multiple") return [...root.querySelectorAll(`[name="${name}"]:checked`)].map(input => input.value);
    if (item.type === "numeric") return root.querySelector(`[name="${name}"]`)?.value.trim() ?? "";
    return [...root.querySelectorAll(`[data-ordering="${item.item_id}"] [data-option]`)].map(row => row.dataset.option);
}

/** Reordering buttons; `onChange` runs after a move so callers can autosave. */
document.addEventListener("click", event => {
    const button = event.target.closest("[data-move]");
    if (!button) return;
    const row = button.closest("[data-option]");
    const sibling = button.dataset.move === "-1" ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    if (button.dataset.move === "-1") sibling.before(row); else sibling.after(row);
    row.dispatchEvent(new Event("input", { bubbles: true }));
});
