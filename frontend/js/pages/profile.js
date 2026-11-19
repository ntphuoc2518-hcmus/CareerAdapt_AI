/** Hồ sơ (5.52): a header with the picture and who the learner is, then one settings panel at a time chosen from a
 *  side menu. Every form, field and request is the same as before; only the layout changed. */
import { api, avatarMarkup, confirmDialog, esc, fmtDate, fmtDateTime, formData, getLang, refreshAvatar, register, setView, toast, withBusy } from "../core.js";
import { icon, tile } from "../icons.js";

const KIND_LABELS = { MINI_TEST: "Mini-test đến hạn", ACTIVITY_DUE: "Hoạt động sắp đến hạn hoặc quá hạn", SCHEDULE: "Lịch không còn phù hợp" };
const TABS = [["account", "Thông tin", "user"], ["goals", "Mục tiêu", "target"], ["preferences", "Nhắc nhở", "bell"], ["password", "Bảo mật", "lock"], ["data", "Dữ liệu", "shield"]];
const TAB_KEY = "profile-tab";
const savedTab = () => { try { return sessionStorage.getItem(TAB_KEY); } catch { return null; } };
const rememberTab = id => { try { sessionStorage.setItem(TAB_KEY, id); } catch { /* storage may be blocked */ } };

const heading = (name, title, text) => `<div class="pf-panel-head">${tile(name, "brand", "tile-sm")}<div><h2>${esc(title)}</h2>${text ? `<p class="sub small">${esc(text)}</p>` : ""}</div></div>`;
const saveButton = (label = "Lưu", name = "check") => `<div class="pf-actions"><button class="btn btn-primary" type="submit">${icon(name)}<span>${label}</span></button></div>`;

function profileHero(user, profile) {
    const chips = [
        profile.major ? ["book", esc(profile.major)] : null,
        ["clock", `${profile.weekly_hours_budget} giờ/tuần · ${profile.target_timeline_weeks} tuần`],
        user.created_at ? ["calendar", `Tham gia <span data-no-i18n>${fmtDate(user.created_at)}</span>`] : null,
    ].filter(Boolean);
    return `<section class="pf-hero"><div class="pf-id">
            <div class="pf-avatar-wrap"><span class="avatar pf-avatar ${user.avatar_version ? "has-photo" : ""}" data-user-avatar aria-hidden="true">${avatarMarkup(user)}</span>
                <label class="pf-camera avatar-pick" title="PNG, JPG hoặc WebP, tối đa 3 MB">${icon("upload")}<span class="sr-only">${user.avatar_version ? "Đổi ảnh đại diện" : "Tải ảnh đại diện lên"}</span><input type="file" id="avatar-file" accept="image/png,image/jpeg,image/webp" hidden></label></div>
            <div class="pf-who"><span class="pf-role">${user.role === "admin" ? "Quản trị viên" : "Học viên"}${user.contributor ? '<span class="pf-tag">Đóng góp câu hỏi</span>' : ""}</span>
                <h2 class="pf-name" data-no-i18n>${esc(user.full_name)}</h2><span class="pf-email" data-no-i18n>${esc(user.email)}</span>
                <div class="pf-chips">${chips.map(([name, text]) => `<span>${icon(name)}<span>${text}</span></span>`).join("")}</div></div></div>
        <div class="pf-hero-actions">${user.avatar_version ? '<button class="btn btn-sm pf-ghost" type="button" data-act="avatar-remove">Xóa ảnh</button>' : ""}
            ${user.role === "admin" ? `<a class="btn btn-sm pf-ghost" href="#/admin">${icon("shield")}<span>Trang quản trị</span></a>` : ""}</div></section>`;
}

function accountPanel(user) {
    return `<form class="pf-form" data-form="account">${heading("user", "Thông tin cá nhân", "")}
        <div class="form-grid"><label class="field"><span>Họ và tên</span><input class="input" name="full_name" required minlength="2" maxlength="100" value="${esc(user.full_name)}"></label>
            <label class="field"><span>Số điện thoại</span><input class="input" name="phone" maxlength="20" value="${esc(user.phone || "")}"></label></div>
        <label class="field"><span>Email</span><input class="input" value="${esc(user.email)}" disabled></label>${saveButton()}</form>`;
}

function goalsPanel(profile) {
    return `<form class="pf-form" data-form="goals">${heading("target", "Mục tiêu học tập", "Gợi ý khi tạo lộ trình mới")}
        <label class="field"><span>Ngành học</span><input class="input" name="major" maxlength="120" value="${esc(profile.major || "")}"></label>
        <div class="form-grid"><label class="field"><span>Giờ học mỗi tuần</span><input class="input" type="number" name="weekly_hours_budget" min="0.5" max="40" step="0.5" required value="${profile.weekly_hours_budget}"></label>
            <label class="field"><span>Thời hạn (tuần)</span><input class="input" type="number" name="target_timeline_weeks" min="1" max="52" required value="${profile.target_timeline_weeks}"></label></div>
        <p class="pf-note">${icon("info")}<span>Lộ trình đã tạo không đổi theo.</span></p>${saveButton()}</form>`;
}

function preferencesPanel(preferences) {
    const cycles = [...new Set([...preferences.preset_cycles, preferences.default_cycle_days])];
    const zones = [...new Set(["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Tokyo", "Europe/London", "America/New_York", preferences.timezone])];
    return `<form class="pf-form" data-form="preferences">${heading("bell", "Nhắc nhở", "Chỉ hiện trong ứng dụng, không gửi email")}
        <div class="form-grid"><label class="field"><span>Chu kỳ mặc định</span><select class="select" name="default_cycle_days">${cycles.map(days => `<option value="${days}" ${days === preferences.default_cycle_days ? "selected" : ""}>${days} ngày</option>`).join("")}</select></label>
            <label class="field"><span>Múi giờ</span><select class="select" name="timezone">${zones.map(zone => `<option ${zone === preferences.timezone ? "selected" : ""}>${esc(zone)}</option>`).join("")}</select></label></div>
        <div class="pf-toggles">${preferences.kinds.map(kind => `<label class="pf-toggle"><input type="checkbox" name="kind_${kind}" ${preferences.enabled_kinds[kind] ? "checked" : ""}><span class="pf-switch" aria-hidden="true"></span><span>${esc(KIND_LABELS[kind] || kind)}</span></label>`).join("")}</div>
        ${saveButton()}</form>`;
}

function passwordPanel(user) {
    const facts = [user.password_changed_at ? `Đổi lần cuối ${fmtDate(user.password_changed_at)}` : "", user.last_login_at ? `Đăng nhập gần nhất ${fmtDateTime(user.last_login_at)}` : ""].filter(Boolean);
    return `<form class="pf-form" data-form="password" autocomplete="off">${heading("lock", "Đổi mật khẩu", "")}
        ${facts.length ? `<p class="pf-facts">${facts.map(fact => `<span>${esc(fact)}</span>`).join("")}</p>` : ""}
        <label class="field"><span>Mật khẩu hiện tại</span><input class="input" type="password" name="current_password" autocomplete="current-password" required></label>
        <div class="form-grid"><label class="field"><span>Mật khẩu mới</span><input class="input" type="password" id="new-password" name="new_password" autocomplete="new-password" required></label>
            <label class="field"><span>Nhập lại mật khẩu mới</span><input class="input" type="password" id="confirm-password" name="confirm_password" autocomplete="new-password" required></label></div>
        <ul id="password-checklist"></ul>${saveButton("Đổi mật khẩu", "lock")}</form>`;
}

function dataPanel() {
    return `<div class="pf-form">${heading("shield", "Dữ liệu cá nhân", "Bài nộp giữ tối đa 90 ngày; điểm và lịch sử vẫn còn")}
        <div class="pf-data-row"><div>${tile("file", "brand", "tile-sm")}<div><strong>Tải dữ liệu</strong><span class="sub small">Toàn bộ dữ liệu của bạn, dạng JSON</span></div></div><button class="btn btn-secondary" type="button" data-act="export">Tải về</button></div>
        <div class="pf-data-row is-danger"><div>${tile("alert", "bad", "tile-sm")}<div><strong>Xóa dữ liệu học tập</strong><span class="sub small">Hồ sơ, bài nộp, JD đã nhập; tài khoản vẫn còn</span></div></div><button class="btn btn-danger" type="button" data-act="erase">Xóa</button></div></div>`;
}

function openTab(id) {
    document.querySelectorAll(".pf-tab").forEach(button => {
        const open = button.dataset.tab === id;
        button.classList.toggle("is-active", open);
        button.setAttribute("aria-selected", String(open));
        button.tabIndex = open ? 0 : -1;
    });
    document.querySelectorAll(".pf-panel").forEach(panel => { panel.hidden = panel.dataset.tab !== id; });
    rememberTab(id);
}

export async function renderProfile() {
    const [me, profile, preferences] = await Promise.all([api("/auth/me"), api("/me/profile"), api("/me/reminder-preferences")]);
    const user = me.user;
    const panels = { account: accountPanel(user), goals: goalsPanel(profile), preferences: preferencesPanel(preferences), password: passwordPanel(user), data: dataPanel() };
    const first = TABS.some(([id]) => id === savedTab()) ? savedTab() : "account";
    setView(`<div class="stack pf">${profileHero(user, profile)}
        <div class="pf-layout"><nav class="card pf-nav" role="tablist" aria-label="Cài đặt hồ sơ">${TABS.map(([id, label, name]) => `<button type="button" class="pf-tab" role="tab" id="pf-tab-${id}" data-tab="${id}" aria-controls="pf-panel-${id}" aria-selected="false">${icon(name)}<span>${label}</span></button>`).join("")}</nav>
            <div class="pf-panels">${TABS.map(([id]) => `<section class="card pf-panel" role="tabpanel" id="pf-panel-${id}" data-tab="${id}" aria-labelledby="pf-tab-${id}" hidden>${panels[id]}</section>`).join("")}</div></div></div>`);
    openTab(first);
    const nav = document.querySelector(".pf-nav");
    nav.addEventListener("click", event => { const tab = event.target.closest(".pf-tab"); if (tab) openTab(tab.dataset.tab); });
    nav.addEventListener("keydown", event => {
        if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
        const tabs = [...nav.querySelectorAll(".pf-tab")];
        const index = tabs.indexOf(document.activeElement);
        if (index < 0) return;
        event.preventDefault();
        const next = tabs[(index + (event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        openTab(next.dataset.tab);
        next.focus();
    });
    document.getElementById("avatar-file").addEventListener("change", async event => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;
        if (file.size > 3 * 1024 * 1024) { toast("Ảnh lớn hơn 3 MB. Hãy chọn ảnh nhỏ hơn.", "bad"); return; }
        const picker = event.target.closest(".avatar-pick");
        await withBusy(picker, async () => {
            const form = new FormData();
            form.append("file", file);
            const result = await api("/auth/me/avatar", { method: "PUT", form });
            refreshAvatar(result.user);
            toast("Đã cập nhật ảnh đại diện.", "good");
            renderProfile();
        });
    });
    const checklist = window.attachPasswordChecklist?.(document.getElementById("password-checklist"), document.getElementById("new-password"), document.getElementById("confirm-password"), null,
        { context: () => ({ email: user.email, fullName: user.full_name }) });
    register({
        actions: {
            export: element => withBusy(element, async () => {
                const data = await api("/me/export");
                const link = document.createElement("a");
                link.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
                link.download = "careeradapt-du-lieu-ca-nhan.json";
                link.click();
                URL.revokeObjectURL(link.href);
            }),
            "avatar-remove": async element => {
                if (!(await confirmDialog("Xóa ảnh đại diện?", "Tài khoản sẽ hiển thị chữ cái đầu của tên thay cho ảnh.", { confirmLabel: "Xóa ảnh", danger: true }))) return;
                await withBusy(element, async () => {
                    const result = await api("/auth/me/avatar", { method: "DELETE" });
                    refreshAvatar(result.user);
                    toast("Đã xóa ảnh đại diện.", "good");
                    renderProfile();
                });
            },
            erase: async element => {
                if (await confirmDialog("Xóa toàn bộ dữ liệu học tập?", "Hồ sơ, quy trình Career Adapt kể cả bản lưu trữ, bài nộp, kết quả, lộ trình và lịch nhắc sẽ bị xóa vĩnh viễn. Tài khoản đăng nhập vẫn còn.", { confirmLabel: "Xóa vĩnh viễn", danger: true })) {
                    await withBusy(element, async () => { const result = await api("/me/data", { method: "DELETE" }); toast(result.message); renderProfile(); });
                }
            },
        },
        forms: {
            account: async form => {
                const values = formData(form);
                await api("/auth/me", { method: "PATCH", body: { full_name: values.full_name, phone: values.phone, preferred_language: getLang() } });
                document.getElementById("user-name").textContent = values.full_name;
                document.querySelector(".pf-name").textContent = values.full_name;
                toast("Đã lưu thông tin.", "good");
            },
            goals: async form => {
                const values = formData(form);
                await api("/me/profile", { method: "PUT", body: { ...profile, major: values.major, weekly_hours_budget: Number(values.weekly_hours_budget), target_timeline_weeks: Number(values.target_timeline_weeks), target_career_version: "v4.0" } });
                toast("Đã lưu mục tiêu học tập.", "good");
            },
            preferences: async form => {
                const values = formData(form);
                await api("/me/reminder-preferences", { method: "PUT", body: { timezone: values.timezone, default_cycle_days: Number(values.default_cycle_days), enabled_kinds: Object.fromEntries(preferences.kinds.map(kind => [kind, Boolean(values[`kind_${kind}`])])) } });
                toast("Đã lưu thiết lập nhắc nhở.", "good");
            },
            password: async form => {
                if (checklist && !checklist.isValid()) { toast("Mật khẩu mới chưa đáp ứng yêu cầu.", "bad"); return; }
                await api("/auth/password/change", { method: "POST", body: formData(form) });
                toast("Đã đổi mật khẩu.", "good");
                form.reset();
            },
        },
    });
}
