/** CareerAdapt AI Assistant: a panel that stays across pages, so it has its own listeners. */
import { aiAvatar } from "./icons.js";
import { botBody, botHead } from "./bot.js";
import { api, confirmDialog, emptyView, esc, fmtDateTime, getLang, safeUrl, toast } from "./core.js";

const state = { status: null, conversationId: null, messages: [], conversations: [], view: "chat", page: "other", busy: false, open: false, hidden: true, image: null, listening: false };
// Each suggested task gets the small icon and tint of the mock-up; the label always comes from the server.
const TASK_STYLE = {
    jd_analysis: ["📄", "is-blue"], explain_result: ["📊", "is-pink"], skill_analysis: ["🧩", "is-violet"], learning_guide: ["🎓", "is-teal"],
    explain_roadmap: ["🗺️", "is-green"], journey_report: ["🏆", "is-amber"], readiness_advice: ["⏱️", "is-sky"],
};
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
const IMAGE_MAX_BYTES = 5 * 1024 * 1024;
const PAGES = { "/": "dashboard", "/process": "process", "/resources": "resources", "/tests": "tests", "/profile": "profile" };
const GROUNDING = { SOURCED: "Có nguồn đã duyệt", DATA: "Từ dữ liệu của bạn", CHAT: "", INSUFFICIENT: "Chưa đủ căn cứ", BLOCKED: "Đã chặn" };

const panel = () => document.getElementById("assistant-panel");
const fab = () => document.getElementById("assistant-fab");

function pageKey(path) {
    const plan = path.match(/^\/plan(?:\/(?:da|backend|qa))?(?:\/([a-z]+))?/);
    if (plan) return `plan_${plan[1] || "overview"}`;
    if (path.startsWith("/flow")) return "process";
    return PAGES[path] || "other";
}

/** Inline marks on already-escaped text: bold, italic, inline code and source markers. */
function inline(line) {
    return line
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[\s(])\*(?!\s)([^*]+?)\*(?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>")
        .replace(/\x60([^\x60]+)\x60/g, "<code>$1</code>")
        .replace(/\[S(\d{1,2})\]/g, '<sup class="cite">S$1</sup>');
}

/**
 * A small, safe Markdown subset for answers. The text is escaped first, then only these shapes are added back:
 * headings (#, ##, ### or a line that is only **bold**), "---" dividers, "- " bullets, "1. " numbered steps,
 * paragraphs, and the inline marks above. Anything else stays plain text.
 */
function richText(text) {
    const sentences = text.includes("\n") ? null : text.split(/(?<=[.!?])\s+(?=[\p{Lu}\d(])/u);
    if (sentences && sentences.length >= 3) text = sentences.join("\n");
    let html = "";
    let list = null;
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    const open = tag => { if (list !== tag) { close(); html += `<${tag}>`; list = tag; } };
    for (const raw of esc(text).split("\n")) {
        const line = raw.trim();
        const bullet = line.match(/^[-*•]\s+(.*)/);
        const step = line.match(/^(\d{1,2})[.)]\s+(.*)/);
        // A heading: "# Title", a line that is only **bold**, or a short "Title:" line such as "Bước tiếp theo:".
        const heading = line.match(/^#{1,4}\s+(.*)/) || line.match(/^\*\*([^*]+?):?\*\*:?$/) || line.match(/^([^.!?:]{2,40}):$/);
        if (bullet) { open("ul"); html += `<li>${inline(bullet[1])}</li>`; continue; }
        if (step) { open("ol"); html += `<li value="${Number(step[1])}">${inline(step[2])}</li>`; continue; }
        close();
        if (!line) continue;
        if (/^(-{3,}|_{3,}|\*{3,})$/.test(line)) html += '<hr class="chat-rule">';
        else if (heading) html += `<p class="chat-heading">${inline(heading[1])}</p>`;
        else html += `<p>${inline(line)}</p>`;
    }
    close();
    return html;
}

/* --- System figures beside an answer: label and value on one line, and a small bar when the row has numbers. --- */
function levelBar(row) {
    const scale = Math.max(row.scale || 3, row.target || 0, row.level || 0);
    const level = row.level ?? 0;
    const target = row.target ?? 0;
    const met = row.target != null && level >= target;
    const cells = Array.from({ length: scale }, (_, index) => {
        const state = index < level ? "is-on" : index < target ? "is-goal" : "";
        return `<span class="${state}"></span>`;
    }).join("");
    // The value text beside the bar already says the level in words, so the bar is decoration for screen readers.
    const classes = met ? "chat-level is-met" : "chat-level";
    return `<span class="${classes}" aria-hidden="true">${cells}</span>`;
}

function meter(percent) {
    const width = Math.max(0, Math.min(100, Number(percent)));
    return `<span class="chat-meter" aria-hidden="true"><span style="width:${width}%"></span></span>`;
}

function rowView(row) {
    const hasLevel = row.level !== undefined || row.target !== undefined;
    const bar = row.percent != null ? meter(row.percent) : hasLevel ? levelBar(row) : "";
    // A long text value (a JD name, for example) goes under its label at full width instead of beside it.
    const classes = !bar && String(row.value).length > 24 ? "chat-card-row is-long" : "chat-card-row";
    return `<div class="${classes}"><span class="chat-card-label">${esc(row.label)}</span><span class="chat-card-value">${esc(row.value)}</span>${bar}</div>`;
}

const cardView = card => `<div class="chat-card"><div class="chat-card-title">${esc(card.title)}</div><div class="chat-card-rows">${card.rows.map(rowView).join("")}</div><span class="chat-card-note">Số liệu do hệ thống tính</span></div>`;

function citationsView(items) {
    if (!items?.length) return "";
    return `<details class="chat-sources"><summary>Nguồn (${items.length})</summary>${items.map(item => `<div class="chat-source"><strong>${esc(item.source_id)}. ${item.url ? `<a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.heading)}</a>` : esc(item.heading)}</strong><span class="sub small">Phiên bản ${esc(item.version)}</span>${item.excerpt ? `<p class="small">${esc(item.excerpt)}</p>` : ""}</div>`).join("")}</details>`;
}

function messageView(message) {
    if (message.role === "user") {
        // A picture shown here exists only in this browser tab; the server keeps no copy, only that one was attached.
        const picture = message.imageUrl ? `<img class="chat-image" src="${esc(message.imageUrl)}" alt="Ảnh đính kèm">` : message.attachment === "image" ? '<span class="chat-attachment-note">📎 Ảnh đính kèm</span>' : "";
        return `<div class="chat-row chat-user" data-no-i18n><div class="chat-bubble">${picture}${esc(message.content).replace(/\n/g, "<br>")}</div></div>`;
    }
    const tags = [message.mode === "RULE" ? "Tra cứu, chưa qua AI" : "", GROUNDING[message.grounding] || ""].filter(Boolean);
    return `<div class="chat-row chat-ai">${aiAvatar("sm")}<div class="chat-bubble">${richText(message.content)}${(message.cards || []).map(cardView).join("")}${citationsView(message.citations)}${tags.length ? `<div class="chat-tags">${tags.map(tag => `<span class="badge badge-muted">${esc(tag)}</span>`).join("")}</div>` : ""}</div></div>`;
}

const SPARK = '<svg viewBox="0 0 24 24"><path d="M12 1.5 13.9 9.6 22 12l-8.1 2.4L12 22.5l-1.9-8.1L2 12l8.1-2.4Z"/></svg>';
// The face that blinks (1 s open, 1 s closed, like the "Trợ lý" button); used for the header and while answering.
const blinkingFace = size => `<span class="ai-avatar ai-avatar-${size} fab-blink" aria-hidden="true"><img src="/img/ai-avatar-open.webp" alt="" width="32" height="32"><img class="fab-blink-closed" src="/img/ai-avatar-closed.webp" alt="" width="32" height="32"></span>`;

/** Welcome scene (5.41): the CareerAdapt robot floats and waves inside a turning ring of light, with speech
 *  bubbles, sound waves and sparkles around it. Decorative only; with reduced motion only the blink remains. */
function stage() {
    const dots = "<i></i><i></i><i></i>";
    const bars = Array.from({ length: 5 }, (unused, index) => `<i style="--d:${index}"></i>`).join("");
    return `<div class="chat-stage" aria-hidden="true">
        <span class="chat-stage-ring"></span><span class="chat-stage-ring is-inner"></span>
        <span class="chat-float is-a">${dots}</span><span class="chat-float is-b">${dots}</span><span class="chat-float is-c">${dots}</span>
        <span class="chat-wave is-left">${bars}</span><span class="chat-wave is-right">${bars}</span>
        <span class="chat-spark is-a">${SPARK}</span><span class="chat-spark is-b">${SPARK}</span><span class="chat-spark is-c">${SPARK}</span>
        <span class="as-bot"><span class="as-bot-halo"></span>${botBody("as", "as-bot-body")}${botHead("as-bot-head", "as-bot-blink")}<span class="as-bot-shadow"></span></span>
    </div>`;
}

function welcome() {
    const tasks = state.status?.tasks || [];
    const chip = (task, index) => {
        const [emoji, tone] = TASK_STYLE[task.task] || ["✨", "is-blue"];
        return `<button class="chat-chip ${tone}" type="button" data-assistant="task" data-task="${esc(task.task)}" style="--i:${index}"><span aria-hidden="true">${emoji}</span><span class="chat-chip-label">${esc(task.label)}</span></button>`;
    };
    return `<div class="chat-welcome">${stage()}<strong>Mình có thể giúp gì cho hành trình của bạn?</strong><p class="sub small">Mình trả lời từ kho kiến thức đã duyệt và dữ liệu của chính bạn. Điểm và mức kỹ năng luôn do hệ thống tính.</p><div class="chat-tasks">${tasks.map(chip).join("")}</div></div>`;
}

function drawChat() {
    const notice = state.status?.ai_enabled === false ? `<div class="alert alert-warn chat-notice"><div>Chưa cấu hình dịch vụ AI. Trợ lý chỉ tra cứu kho kiến thức và dữ liệu của bạn.</div></div>` : (state.status?.budget_notice ? `<div class="alert alert-warn chat-notice"><div>${esc(state.status.budget_notice)}</div></div>` : "");
    const body = state.messages.length ? state.messages.map(messageView).join("") : welcome();
    const typing = state.busy ? `<div class="chat-row chat-ai"><span class="chat-thinking">${blinkingFace("sm")}</span><div class="chat-bubble chat-typing" role="status"><span class="chat-typing-dot" aria-hidden="true"></span><span class="chat-typing-dot" aria-hidden="true"></span><span class="chat-typing-dot" aria-hidden="true"></span><span class="sr-only">Đang xử lý...</span></div></div>` : "";
    panel().querySelector(".assistant-body").innerHTML = `${notice}<div class="chat-log" id="chat-log" aria-live="polite">${body}${typing}</div>`;
    panel().querySelector(".assistant-form").hidden = false;
    const log = document.getElementById("chat-log");
    log.scrollTop = log.scrollHeight;
}

function drawHistory() {
    panel().querySelector(".assistant-form").hidden = true;
    panel().querySelector(".assistant-body").innerHTML = state.conversations.length
        ? `<ul class="chat-history">${state.conversations.map(item => `<li><button type="button" class="chat-open" data-assistant="open" data-id="${esc(item.conversation_id)}"><strong>${esc(item.title)}</strong><span class="sub small">${fmtDateTime(item.updated_at)}</span></button><button type="button" class="btn btn-ghost btn-sm" data-assistant="delete" data-id="${esc(item.conversation_id)}" aria-label="Xóa hội thoại ${esc(item.title)}">Xóa</button></li>`).join("")}</ul>`
        : emptyView("Chưa có hội thoại", "Hội thoại của bạn sẽ được lưu ở đây.");
}

function draw() {
    if (state.view === "history") drawHistory(); else drawChat();
}

function errorRow(message) {
    state.messages.push({ role: "assistant", content: message, grounding: "", mode: "" });
}

async function refreshStatus() {
    state.status = await api("/assistant/status");
}

async function ensureConversation() {
    if (!state.conversationId) state.conversationId = (await api("/assistant/conversations", { method: "POST" })).conversation_id;
    return state.conversationId;
}

async function submit(request) {
    if (state.busy) return;
    state.busy = true;
    drawChat();
    try {
        await request();
    } catch (error) {
        errorRow(error.message);
        await refreshStatus().catch(() => {});
        applyVisibility();
    } finally {
        state.busy = false;
        draw();
    }
}

async function send(text) {
    const image = state.image;
    state.messages.push({ role: "user", content: text, imageUrl: image?.url });
    setImage(null);
    await submit(async () => {
        const id = await ensureConversation();
        if (image) {
            const form = new FormData();
            form.append("content", text);
            form.append("page", state.page);
            form.append("image", image.file);
            state.messages.push(await api(`/assistant/conversations/${id}/messages/image`, { method: "POST", form }));
        } else {
            state.messages.push(await api(`/assistant/conversations/${id}/messages`, { method: "POST", body: { content: text, page: state.page } }));
        }
    });
}

/* --- Image attachment: checked here for a quick answer, checked again and cleaned on the server. --- */
// The preview is a data: URL because the page's security policy allows data: images but not blob: ones.
function setImage(file, url = "") {
    state.image = file ? { file, url } : null;
    const box = panel().querySelector(".assistant-attachment");
    box.hidden = !state.image;
    if (state.image) {
        box.querySelector("img").src = state.image.url;
        box.querySelector(".assistant-attachment-name").textContent = file.name;
    }
    panel().querySelector('[data-assistant="attach"]').classList.toggle("is-on", Boolean(state.image));
}

function pickImage(file) {
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) { toast("Chỉ nhận ảnh PNG, JPG hoặc WebP.", "bad"); return; }
    if (file.size > IMAGE_MAX_BYTES) { toast("Ảnh lớn hơn 5 MB. Hãy chọn ảnh nhỏ hơn.", "bad"); return; }
    const reader = new FileReader();
    reader.onload = () => setImage(file, String(reader.result));
    reader.onerror = () => toast("Không đọc được ảnh này. Hãy thử ảnh khác.", "bad");
    reader.readAsDataURL(file);
    if (state.status?.ai_enabled === false) toast("Dịch vụ AI chưa được cấu hình nên ảnh sẽ chưa được phân tích.", "bad");
}

/* --- Voice: the browser's own speech recognition turns speech into text in the box; nothing is sent until you press Gửi. --- */
let recognition = null;

function voiceState(text) {
    panel().querySelector(".assistant-voice-state").textContent = text;
}

function toggleVoice() {
    if (state.listening) { recognition?.stop(); return; }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { toast("Trình duyệt này chưa hỗ trợ nhập bằng giọng nói. Hãy dùng Chrome hoặc Edge.", "bad"); return; }
    const input = panel().querySelector(".assistant-input");
    const before = input.value.trim();
    recognition = new Recognition();
    recognition.lang = getLang() === "en" ? "en-US" : "vi-VN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = event => {
        const heard = [...event.results].map(result => result[0].transcript).join("");
        input.value = before ? `${before} ${heard}` : heard;
    };
    recognition.onerror = event => {
        const reason = event.error === "not-allowed" || event.error === "service-not-allowed"
            ? "Trình duyệt chưa được phép dùng micro. Hãy cho phép micro cho trang này rồi thử lại."
            : event.error === "no-speech" ? "Không nghe thấy giọng nói. Hãy thử lại." : "Không nhận dạng được giọng nói lúc này.";
        toast(reason, "bad");
    };
    recognition.onend = () => {
        state.listening = false;
        const button = panel().querySelector('[data-assistant="voice"]');
        button.classList.remove("is-listening");
        button.setAttribute("aria-pressed", "false");
        voiceState("");
        input.focus();
    };
    try {
        recognition.start();
    } catch {
        toast("Không bật được micro lúc này.", "bad");
        return;
    }
    state.listening = true;
    const button = panel().querySelector('[data-assistant="voice"]');
    button.classList.add("is-listening");
    button.setAttribute("aria-pressed", "true");
    voiceState("Đang nghe… bấm micro lần nữa để dừng");
}

async function runTask(task, label) {
    state.messages.push({ role: "user", content: label });
    await submit(async () => {
        const result = await api(`/assistant/tasks/${task}`, { method: "POST", body: { conversation_id: state.conversationId } });
        state.conversationId = result.conversation_id;
        state.messages.push(result.message);
    });
}

async function showHistory() {
    state.view = "history";
    state.conversations = await api("/assistant/conversations");
    draw();
}

async function openConversation(id) {
    const data = await api(`/assistant/conversations/${id}`);
    state.conversationId = id;
    state.messages = data.messages;
    state.view = "chat";
    draw();
}

function newConversation() {
    state.conversationId = null;
    state.messages = [];
    state.view = "chat";
    draw();
}

async function removeConversation(id) {
    if (!await confirmDialog("Xóa hội thoại", "Hội thoại này sẽ bị xóa vĩnh viễn và không khôi phục được.", { confirmLabel: "Xóa", danger: true })) return;
    await api(`/assistant/conversations/${id}`, { method: "DELETE" });
    if (state.conversationId === id) newConversation();
    await showHistory();
}

function setOpen(open) {
    state.open = open;
    panel().hidden = !open;
    fab().setAttribute("aria-expanded", String(open));
    if (open) {
        draw();
        panel().querySelector("textarea").focus();
    }
}

function applyVisibility() {
    // On a test page the assistant is gone; elsewhere a lock (a test is open) is explained in the sidebar card.
    const locked = !state.hidden && Boolean(state.status?.blocked);
    const hide = state.hidden || locked;
    fab().hidden = hide;
    const card = document.getElementById("ai-card");
    card.hidden = state.hidden;
    card.classList.toggle("is-locked", locked);
    document.getElementById("ai-card-title").textContent = locked ? "Trợ lý đang tạm dừng" : "Khám phá tiềm năng cùng Trợ lý AI";
    const note = document.getElementById("ai-card-note");
    note.hidden = !locked;
    note.textContent = locked ? state.status.block_reason || "" : "";
    document.getElementById("ai-card-open").hidden = locked;
    const resume = document.getElementById("ai-card-resume");
    resume.hidden = !(locked && state.status.block_link);
    if (locked && state.status.block_link) resume.setAttribute("href", state.status.block_link);
    if (hide && state.open) setOpen(false);
}

/** Opens the panel and runs one of the server's AI tasks, e.g. "jd_analysis", in a fresh conversation. */
export function openAssistantTask(task, label) {
    if (fab().hidden) { toast(state.status?.block_reason || "Trợ lý đang tạm khóa trên trang này.", "bad"); return; }
    newConversation();
    setOpen(true);
    runTask(task, label);
}

/** The process pages start with the Assistant closed (see assistantRoute); a step that is not the test opens it
 *  again (5.42), so the guide can hand a question over. The whole test step keeps it closed. */
export function allowAssistantHere(allowed) {
    state.hidden = !allowed;
    applyVisibility();
    if (allowed) refreshStatus().then(applyVisibility).catch(() => {});
}

/** Opens the panel in a fresh conversation and asks one question, or runs one of the server's tasks. */
export async function askAssistant(question, task = null, label = "") {
    if (state.hidden) { toast("Trợ lý tạm dừng ở bước này.", "bad"); return; }
    if (!state.status) await refreshStatus().catch(() => {});
    applyVisibility();
    if (fab().hidden) { toast(state.status?.block_reason || "Trợ lý đang tạm khóa trên trang này.", "bad"); return; }
    newConversation();
    setOpen(true);
    if (task) runTask(task, label || question);
    else if (question) await send(question);
}

/** Hidden while a test is on screen. The server refuses as well, so this only keeps the screen clean. */
export async function assistantRoute(path) {
    state.page = pageKey(path);
    state.hidden = path.startsWith("/flow") || path.startsWith("/tests/run") || path.startsWith("/mini") || path === "/final-exam";
    applyVisibility();
    if (state.hidden) return;
    try {
        await refreshStatus();
        applyVisibility();
    } catch { /* The trigger stays; opening the panel reports the error. */ }
}

// The panel's header lines up with the app's top bar: same height, so both bottom borders form one line.
function alignWithTopbar() {
    const bar = document.querySelector(".topbar");
    if (!bar) return;
    const apply = () => document.documentElement.style.setProperty("--topbar-h", `${bar.getBoundingClientRect().height}px`);
    apply();
    if ("ResizeObserver" in window) new ResizeObserver(apply).observe(bar);
    else window.addEventListener("resize", apply);
}

export function initAssistant() {
    alignWithTopbar();
    fab().addEventListener("click", () => setOpen(!state.open));
    document.getElementById("ai-card-open").addEventListener("click", () => setOpen(true));
    panel().addEventListener("click", event => {
        const element = event.target.closest("[data-assistant]");
        if (!element) return;
        const action = element.dataset.assistant;
        const guarded = task => task().catch(error => toast(error.message, "bad"));
        if (action === "close") setOpen(false);
        if (action === "new") newConversation();
        if (action === "history") guarded(showHistory);
        if (action === "open") guarded(() => openConversation(element.dataset.id));
        if (action === "delete") guarded(() => removeConversation(element.dataset.id));
        if (action === "task") runTask(element.dataset.task, element.querySelector(".chat-chip-label")?.textContent || element.textContent);
        if (action === "attach") document.getElementById("assistant-file").click();
        if (action === "detach") setImage(null);
        if (action === "voice") toggleVoice();
    });
    const form = panel().querySelector(".assistant-form");
    const input = form.querySelector("textarea");
    document.getElementById("assistant-file").addEventListener("change", event => { pickImage(event.target.files?.[0]); event.target.value = ""; });
    // A picture can also be pasted straight into the question box.
    input.addEventListener("paste", event => {
        const file = [...(event.clipboardData?.files || [])].find(item => item.type.startsWith("image/"));
        if (file) { event.preventDefault(); pickImage(file); }
    });
    const post = () => {
        if (state.listening) recognition?.stop();
        const text = input.value.trim() || (state.image ? "Hãy giải thích nội dung trong ảnh này giúp mình." : "");
        if (!text || state.busy) return;
        input.value = "";
        send(text);
    };
    form.addEventListener("submit", event => { event.preventDefault(); post(); });
    input.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); post(); }
    });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && state.open && !document.querySelector(".modal")) setOpen(false); });
}
