(() => {
    const messageBox = document.getElementById("login-message");
    const forms = {
        login: document.getElementById("login-form"),
        register: document.getElementById("register-form"),
        forgot: document.getElementById("forgot-form"),
        reset: document.getElementById("reset-form")
    };
    const loginTab = document.getElementById("tab-login");
    const registerTab = document.getElementById("tab-register");
    const HEADINGS = {
        login: ["login.titleLogin", "login.subtitleLogin"],
        register: ["login.titleRegister", "login.subtitleRegister"],
        forgot: ["login.titleForgot", "login.subtitleForgot"],
        reset: ["login.titleReset", "login.subtitleReset"]
    };
    let csrfToken = "";
    let mode = "login";
    let resetToken = "";
    // Keep the last message as a translation key so it follows a language switch.
    let lastMessage = null;

    const showMessage = (key, vars, isError = false, raw = null) => {
        lastMessage = key || raw ? { key, vars, isError, raw } : null;
        const text = raw || (key ? i18n.t(key, vars) : "");
        messageBox.textContent = text;
        messageBox.hidden = !text;
        messageBox.classList.toggle("is-error", isError);
        messageBox.classList.toggle("is-success", !isError && Boolean(text));
    };

    async function refreshCsrfToken() {
        const response = await fetch("/api/v1/auth/csrf", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error(i18n.t("login.csrfInit"));
        csrfToken = (await response.json()).csrf_token;
    }

    function renderHeading() {
        const [title, subtitle] = HEADINGS[mode];
        document.getElementById("form-title").textContent = i18n.t(title);
        document.getElementById("form-subtitle").textContent = i18n.t(subtitle);
        document.title = i18n.t("login.pageTitle");
    }

    function switchMode(next, { keepMessage = false } = {}) {
        mode = next;
        Object.entries(forms).forEach(([name, form]) => { form.hidden = name !== next; });
        const tabbed = next === "login" || next === "register";
        document.getElementById("login-tabs").hidden = !tabbed;
        loginTab.classList.toggle("is-active", next === "login");
        registerTab.classList.toggle("is-active", next === "register");
        loginTab.setAttribute("aria-selected", String(next === "login"));
        registerTab.setAttribute("aria-selected", String(next === "register"));
        renderHeading();
        if (!keepMessage) showMessage(null);
        forms[next].querySelector("input")?.focus();
    }

    async function post(endpoint, payload) {
        if (!csrfToken) await refreshCsrfToken();
        const response = await fetch(`/api/v1/auth/${endpoint}`, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
            body: JSON.stringify({ ...payload, ...(endpoint === "register" || endpoint === "password/forgot" ? { preferred_language: i18n.getLang() } : {}) })
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 403) csrfToken = "";
        return { ok: response.ok, data };
    }

    async function withBusy(form, action) {
        const button = form.querySelector("button[type=submit]");
        const label = button.querySelector("span:first-child");
        button.disabled = true;
        button.classList.add("is-loading");
        label.textContent = i18n.t("login.processing");
        showMessage(null);
        try {
            await action();
        } catch (error) {
            showMessage("login.network", null, true);
        } finally {
            button.classList.remove("is-loading");
            label.textContent = i18n.t(label.dataset.i18n);
            button.disabled = form.dataset.requiresValid === "true" && !form._checklist?.isValid();
        }
    }

    function showServerError(data) {
        const code = data?.error?.code;
        if (code) showMessage(`error.${code}`, null, true);
        else showMessage(null, null, true, i18n.errorMessage(data));
    }

    // --- Mode switching ---------------------------------------------------
    loginTab.addEventListener("click", () => switchMode("login"));
    registerTab.addEventListener("click", () => switchMode("register"));
    document.getElementById("forgot-link").addEventListener("click", () => {
        document.getElementById("forgot-email").value = document.getElementById("login-email").value;
        switchMode("forgot");
    });
    document.querySelectorAll("[data-back-to-login]").forEach(button => button.addEventListener("click", () => switchMode("login")));

    // --- Checklists -------------------------------------------------------
    [["register", "register-password", "register-confirm", "register-checklist"],
     ["reset", "reset-password", "reset-confirm", "reset-checklist"]].forEach(([name, pw, confirm, list]) => {
        const form = forms[name];
        const submit = form.querySelector("button[type=submit]");
        form.dataset.requiresValid = "true";
        // Registration knows the email and name being typed; a reset does not, so the server checks those.
        const email = name === "register" ? document.getElementById("register-email") : null;
        const fullName = name === "register" ? document.getElementById("register-name") : null;
        form._checklist = attachPasswordChecklist(
            document.getElementById(list), document.getElementById(pw), document.getElementById(confirm),
            valid => { if (!submit.classList.contains("is-loading")) submit.disabled = !valid; },
            email ? { context: () => ({ email: email.value, fullName: fullName.value }), watch: [email, fullName] } : {}
        );
    });

    // --- Where to go after signing in ------------------------------------------
    // The page a learner was on when the session ended (saved by the app), or the page of a link opened while
    // signed out (/app#/... is redirected here with its fragment). Only in-app routes are accepted (audit 2026-11-18).
    const RETURN_HASH = /^#\/[A-Za-z0-9_\-/]{0,200}$/;
    const linkedHash = RETURN_HASH.test(window.location.hash) ? window.location.hash : "";
    function returnHash() {
        let saved = "";
        try { saved = sessionStorage.getItem("ca-return-to") || ""; sessionStorage.removeItem("ca-return-to"); } catch { /* storage may be blocked */ }
        const target = linkedHash || saved;
        return RETURN_HASH.test(target) ? target : "";
    }

    // --- Submissions --------------------------------------------------------
    forms.login.addEventListener("submit", event => {
        event.preventDefault();
        if (!forms.login.reportValidity()) return;
        const data = new FormData(forms.login);
        withBusy(forms.login, async () => {
            const result = await post("login", { email: String(data.get("email")).trim(), password: String(data.get("password")) });
            if (!result.ok) return showServerError(result.data);
            // Apply the account's saved language only if this browser has not chosen one.
            const saved = result.data?.user?.preferred_language;
            if (saved && !i18n.hasStoredChoice()) i18n.setLang(saved, { silent: true });
            window.location.replace("/app" + returnHash());
        });
    });

    forms.register.addEventListener("submit", event => {
        event.preventDefault();
        if (!forms.register.reportValidity() || !forms.register._checklist.isValid()) return showMessage("login.fixFields", null, true);
        const data = new FormData(forms.register);
        const email = String(data.get("email")).trim();
        withBusy(forms.register, async () => {
            const result = await post("register", {
                full_name: String(data.get("full_name")).trim(),
                email,
                password: String(data.get("password")),
                confirm_password: String(data.get("confirm_password"))
            });
            if (!result.ok) return showServerError(result.data);
            // No automatic sign-in: the learner confirms the new credentials on the sign-in form.
            forms.register.reset();
            forms.register._checklist.render();
            switchMode("login", { keepMessage: true });
            document.getElementById("login-email").value = email;
            document.getElementById("login-password").value = "";
            document.getElementById("login-password").focus();
            showMessage("login.registered", { email });
        });
    });

    forms.forgot.addEventListener("submit", event => {
        event.preventDefault();
        if (!forms.forgot.reportValidity()) return;
        const email = String(new FormData(forms.forgot).get("email")).trim();
        withBusy(forms.forgot, async () => {
            const result = await post("password/forgot", { email });
            if (!result.ok) return showServerError(result.data);
            showMessage("login.forgotSent");
        });
    });

    forms.reset.addEventListener("submit", event => {
        event.preventDefault();
        if (!forms.reset._checklist.isValid()) return showMessage("login.fixFields", null, true);
        const data = new FormData(forms.reset);
        withBusy(forms.reset, async () => {
            const result = await post("password/reset", {
                token: resetToken,
                new_password: String(data.get("password")),
                confirm_password: String(data.get("confirm_password"))
            });
            if (!result.ok) return showServerError(result.data);
            resetToken = "";
            forms.reset.reset();
            switchMode("login", { keepMessage: true });
            showMessage("login.resetDone");
        });
    });

    // --- Password visibility -------------------------------------------------
    function renderToggle(button) {
        const revealed = document.getElementById(button.dataset.togglePassword).type === "text";
        // The eye icons swap by CSS; the hidden label keeps the old Hiện/Ẩn text for screen readers and tests.
        button.dataset.revealed = String(revealed);
        const label = button.querySelector(".pw-toggle-label");
        if (label) label.textContent = i18n.t(revealed ? "login.hide" : "login.show");
        else button.textContent = i18n.t(revealed ? "login.hide" : "login.show");
        button.setAttribute("aria-label", i18n.t(revealed ? "login.hidePassword" : "login.showPassword"));
        button.title = i18n.t(revealed ? "login.hidePassword" : "login.showPassword");
    }
    // --- Caps Lock warning on password fields ---------------------------------------
    document.querySelectorAll("[data-caps-for]").forEach(hint => {
        const input = document.getElementById(hint.dataset.capsFor);
        if (!input) return;
        const update = event => { hint.hidden = !(event.getModifierState && event.getModifierState("CapsLock")); };
        input.addEventListener("keydown", update);
        input.addEventListener("keyup", update);
        input.addEventListener("blur", () => { hint.hidden = true; });
    });
    document.querySelectorAll("[data-toggle-password]").forEach(button => {
        renderToggle(button);
        button.addEventListener("click", () => {
            const input = document.getElementById(button.dataset.togglePassword);
            input.type = input.type === "password" ? "text" : "password";
            renderToggle(button);
        });
    });

    i18n.onChange(() => {
        renderHeading();
        document.querySelectorAll("[data-toggle-password]").forEach(renderToggle);
        if (lastMessage) showMessage(lastMessage.key, lastMessage.vars, lastMessage.isError, lastMessage.raw);
    });

    // --- Reset link: /login#reset=<token> (fragment never reaches the server) ---
    function openResetFromHash() {
        const match = window.location.hash.match(/^#reset=([A-Za-z0-9_-]{20,200})$/);
        if (!match) return false;
        resetToken = match[1];
        history.replaceState(null, "", window.location.pathname);
        switchMode("reset");
        return true;
    }
    window.addEventListener("hashchange", openResetFromHash);
    if (!openResetFromHash()) renderHeading();

    refreshCsrfToken().catch(error => showMessage(null, null, true, error.message));
})();
