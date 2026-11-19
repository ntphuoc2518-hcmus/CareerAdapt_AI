import { alertBox, api, avatarMarkup, confirmDialog, esc, formData, getLang, refreshAvatar, register, setView, toast, withBusy } from "../core.js";
import { icon, illustration, tile } from "../icons.js";

const KIND_LABELS = { MINI_TEST: "Mini-test đến hạn", ACTIVITY_DUE: "Hoạt động sắp đến hạn hoặc quá hạn", SCHEDULE: "Lịch không còn phù hợp" };

const heading = (name, title, text) => `<div class="card-title">${tile(name)}<div><h2>${esc(title)}</h2><p class="sub">${esc(text)}</p></div></div>`;

export async function renderProfile() {
    const [me, profile, preferences] = await Promise.all([api("/auth/me"), api("/me/profile"), api("/me/reminder-preferences")]);
    const user = me.user;
    setView(`<div class="grid grid-2">
        <form class="card" data-form="account"><div class="form-body">${heading("user", "Tài khoản", "Thông tin tài khoản của bạn")}
            <div class="avatar-editor"><span class="avatar avatar-lg ${user.avatar_version ? "has-photo" : ""}" data-user-avatar aria-hidden="true">${avatarMarkup(user)}</span>
                <div class="avatar-editor-body"><strong>Ảnh đại diện</strong><span class="sub small">PNG, JPG hoặc WebP, tối đa 3 MB. Ảnh được cắt vuông ở giữa và thu nhỏ.</span>
                    <div class="row"><label class="btn btn-secondary btn-sm avatar-pick">${icon("upload")}<span>${user.avatar_version ? "Đổi ảnh" : "Tải ảnh lên"}</span><input type="file" id="avatar-file" accept="image/png,image/jpeg,image/webp" hidden></label>${user.avatar_version ? '<button class="btn btn-ghost btn-sm" type="button" data-act="avatar-remove">Xóa ảnh</button>' : ""}</div></div></div>
            <label class="field"><span>Họ và tên</span><input class="input" name="full_name" required minlength="2" maxlength="100" value="${esc(user.full_name)}"></label><label class="field"><span>Email</span><input class="input" value="${esc(user.email)}" disabled></label><label class="field"><span>Số điện thoại</span><input class="input" name="phone" maxlength="20" value="${esc(user.phone || "")}"></label><div class="row"><button class="btn btn-primary" type="submit">${icon("check")}<span>Lưu</span></button></div></div></form>
        <form class="card form-body" data-form="goals">${heading("target", "Mục tiêu học tập", "Giá trị gợi ý khi tạo lộ trình học")}<label class="field"><span>Ngành học</span><input class="input" name="major" maxlength="120" value="${esc(profile.major || "")}"></label><div class="form-grid"><label class="field"><span>Giờ học mỗi tuần</span><input class="input" type="number" name="weekly_hours_budget" min="0.5" max="40" step="0.5" required value="${profile.weekly_hours_budget}"></label><label class="field"><span>Thời hạn (tuần)</span><input class="input" type="number" name="target_timeline_weeks" min="1" max="52" required value="${profile.target_timeline_weeks}"></label></div><p class="meta">${icon("info")}<span>Giờ học dùng làm giá trị gợi ý khi tạo lộ trình. Lộ trình đã tạo không đổi theo.</span></p><div class="row"><button class="btn btn-primary" type="submit">${icon("check")}<span>Lưu</span></button></div></form>
        <form class="card with-art with-art-end" data-form="preferences"><div class="form-body">${heading("bell", "Nhắc nhở", "Cài đặt nhắc học trong ứng dụng")}<label class="field"><span>Chu kỳ mặc định</span><select class="select" name="default_cycle_days">${[...new Set([...preferences.preset_cycles, preferences.default_cycle_days])].map(days => `<option value="${days}" ${days === preferences.default_cycle_days ? "selected" : ""}>${days} ngày</option>`).join("")}</select></label><label class="field"><span>Múi giờ</span><select class="select" name="timezone">${[...new Set(["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Tokyo", "Europe/London", "America/New_York", preferences.timezone])].map(zone => `<option ${zone === preferences.timezone ? "selected" : ""}>${esc(zone)}</option>`).join("")}</select></label>${preferences.kinds.map(kind => `<label class="check"><input type="checkbox" name="kind_${kind}" ${preferences.enabled_kinds[kind] ? "checked" : ""}> ${esc(KIND_LABELS[kind] || kind)}</label>`).join("")}<p class="sub small">Nhắc chỉ hiện trong ứng dụng. Hệ thống không gửi email hay thông báo đẩy.</p><div class="row"><button class="btn btn-primary" type="submit">${icon("check")}<span>Lưu</span></button></div></div><div class="art-soft">${illustration("calendar")}</div></form>
        <form class="card with-art with-art-end" data-form="password" autocomplete="off"><div class="form-body">${heading("lock", "Đổi mật khẩu", "Thay đổi mật khẩu để bảo vệ tài khoản")}<label class="field"><span>Mật khẩu hiện tại</span><input class="input" type="password" name="current_password" autocomplete="current-password" required></label><label class="field"><span>Mật khẩu mới</span><input class="input" type="password" id="new-password" name="new_password" autocomplete="new-password" required></label><label class="field"><span>Nhập lại mật khẩu mới</span><input class="input" type="password" id="confirm-password" name="confirm_password" autocomplete="new-password" required></label><ul id="password-checklist"></ul><div class="row"><button class="btn btn-primary" type="submit">${icon("lock")}<span>Đổi mật khẩu</span></button></div></div><div class="art-soft">${illustration("shield")}</div></form>
        <section class="card stack span-all">${heading("shield", "Dữ liệu cá nhân", "Tải về hoặc xóa dữ liệu học tập của bạn")}<p class="sub small">Bạn có thể tải toàn bộ dữ liệu hoặc yêu cầu xóa hồ sơ, bài nộp và JD đã nhập. Nội dung bài nộp được giữ tối đa 90 ngày; điểm và lịch sử vẫn còn sau đó.</p>${user.role === "admin" ? alertBox("info", 'Bạn có quyền quản trị. <a href="#/admin">Mở trang quản trị</a>.') : ""}<div class="row"><button class="btn btn-secondary" data-act="export">Tải dữ liệu (JSON)</button><button class="btn btn-danger" data-act="erase">Xóa toàn bộ dữ liệu học tập</button></div></section></div>`);
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
