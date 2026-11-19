/** Runs in <head> on every page, before anything is painted, so a dark page never flashes light. */
(function () {
    const KEY = "careeradapt_theme";
    const CHOICES = ["light", "dark", "system"];
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function get() {
        try {
            const value = localStorage.getItem(KEY);
            return CHOICES.includes(value) ? value : "system";
        } catch (e) {
            return "system";
        }
    }

    function apply(theme = get()) {
        const dark = theme === "dark" || (theme === "system" && media.matches);
        document.documentElement.dataset.theme = dark ? "dark" : "light";
        document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#08101F" : "#0B1F45");
    }

    // One button cycles light -> dark -> system; it shows the current mode and says which one comes next.
    const LABELS = {
        vi: { light: "Sáng", dark: "Tối", system: "Theo hệ thống", now: "Giao diện", next: "bấm để chuyển sang" },
        en: { light: "Light", dark: "Dark", system: "Match system", now: "Theme", next: "click to switch to" },
    };

    function mark(theme = get()) {
        const words = LABELS[document.documentElement.lang === "en" ? "en" : "vi"];
        const next = CHOICES[(CHOICES.indexOf(theme) + 1) % CHOICES.length];
        document.querySelectorAll("[data-theme-cycle]").forEach(button => {
            button.dataset.current = theme;
            const label = `${words.now}: ${words[theme]} (${words.next} ${words[next]})`;
            button.setAttribute("aria-label", label);
            button.setAttribute("title", label);
        });
        document.querySelectorAll("[data-theme-option]").forEach(button => {
            const active = button.dataset.themeOption === theme;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }

    function set(theme) {
        if (!CHOICES.includes(theme)) return;
        try { localStorage.setItem(KEY, theme); } catch (e) { /* The choice then lasts for this page only. */ }
        apply(theme);
        document.querySelectorAll("input[data-theme-choice]").forEach(input => { input.checked = input.value === theme; });
        mark(theme);
        window.dispatchEvent(new CustomEvent("careeradapt:theme", { detail: theme }));
    }

    media.addEventListener("change", () => { if (get() === "system") apply(); });
    // Another tab of this site changed the choice.
    window.addEventListener("storage", event => { if (event.key === KEY) { apply(); mark(); } });
    document.addEventListener("click", event => {
        const option = event.target.closest("[data-theme-option]");
        if (option) set(option.dataset.themeOption);
        else if (event.target.closest("[data-theme-cycle]")) set(CHOICES[(CHOICES.indexOf(get()) + 1) % CHOICES.length]);
    });
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => mark());
    else mark();

    window.careerTheme = { get, set, apply, mark, CHOICES };
    apply();
    try {
        const lang = localStorage.getItem("careeradapt_lang");
        if (lang === "en" || lang === "vi") document.documentElement.lang = lang;
        // 5.58: folded navigation (js/layout.js) is applied before the first paint so the page does not jump.
        document.documentElement.classList.toggle("side-collapsed", localStorage.getItem("careeradapt_side_collapsed") === "1");
        document.documentElement.classList.toggle("plan-menu-collapsed", localStorage.getItem("careeradapt_plan_menu_collapsed") === "1");
    } catch (e) { /* The page stays in its default language. */ }
})();
