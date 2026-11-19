/**
 * Live password requirements checklist. Rule ids match backend/accounts.py PASSWORD_RULES;
 * the server re-checks every rule, so this is guidance only.
 *
 * Rules (5.26, team decision): at least 8 characters; at least one uppercase letter and one special
 * character. A rule turns green when met, then collapses away; when everything is met the list is
 * replaced by one confirmation line.
 *
 *   const check = attachPasswordChecklist(listElement, passwordInput, confirmInput, onChange);
 *   check.isValid()
 */
(function () {
    const RULES = {
        length: value => { const count = [...value].length; return count >= 8 && count <= 128; },
        upper: value => /\p{Lu}/u.test(value),
        // Anything that is not a letter, a digit or a space, as on the server.
        special: value => /[^\p{L}\p{N}\s]/u.test(value),
    };

    const GROUPS = [
        { id: "length", rules: ["length"], label: () => "pw.length" },
        { id: "upper", rules: ["upper"], label: () => "pw.upper" },
        { id: "special", rules: ["special"], label: () => "pw.special" },
    ];
    const HIDE_DELAY_MS = 650;

    function attachPasswordChecklist(list, input, confirmInput, onChange, options = {}) {
        const context = () => (options.context ? options.context() : {});
        const groups = GROUPS.filter(group => !group.needsContext || options.context);
        if (confirmInput) groups.push({ id: "match", rules: ["match"], label: () => "pw.match" });

        list.classList.add("pw-checklist");
        list.setAttribute("aria-live", "polite");
        list.innerHTML = `<li class="pw-checklist-title"></li>` + groups.map(group =>
            `<li data-group="${group.id}"><span class="pw-icon" aria-hidden="true"></span><span class="pw-text"></span><span class="pw-sr"></span></li>`
        ).join("") + `<li class="pw-all-met" hidden><span class="pw-icon" aria-hidden="true">✓</span><span class="pw-text"></span></li>`;
        const timers = {};

        function state() {
            const value = input.value;
            const known = context();
            const result = Object.fromEntries(groups.filter(group => RULES[group.id]).map(group => [group.id, RULES[group.id](value, known)]));
            if (confirmInput) result.match = value.length > 0 && value === confirmInput.value;
            return result;
        }

        function render() {
            const result = state();
            const empty = input.value.length === 0;
            let remaining = 0;
            groups.forEach(group => {
                const item = list.querySelector(`[data-group="${group.id}"]`);
                const missing = group.rules.filter(rule => !result[rule]);
                const met = missing.length === 0;
                if (!met) remaining++;
                item.querySelector(".pw-text").textContent = i18n.t(group.label(met ? group.rules : missing));
                item.querySelector(".pw-sr").textContent = ` (${i18n.t(met ? "pw.met" : "pw.unmet")})`;
                item.querySelector(".pw-icon").textContent = met ? "✓" : "";
                clearTimeout(timers[group.id]);
                if (met && !empty) {
                    // Show the green tick briefly, then collapse the satisfied requirement.
                    item.classList.add("is-met");
                    timers[group.id] = setTimeout(() => item.classList.add("is-gone"), item.classList.contains("is-gone") ? 0 : HIDE_DELAY_MS);
                } else {
                    item.classList.remove("is-met", "is-gone");
                }
            });
            const allMet = remaining === 0 && !empty;
            list.classList.toggle("is-complete", allMet);
            list.querySelector(".pw-checklist-title").textContent = i18n.t("pw.title");
            const done = list.querySelector(".pw-all-met");
            done.hidden = !allMet;
            done.querySelector(".pw-text").textContent = i18n.t("pw.allMet");
            if (confirmInput) {
                const mismatch = confirmInput.value.length > 0 && !result.match;
                confirmInput.setAttribute("aria-invalid", String(mismatch));
            }
            onChange?.(isValid());
        }

        function isValid() {
            return Object.values(state()).every(Boolean);
        }

        input.addEventListener("input", render);
        confirmInput?.addEventListener("input", render);
        (options.watch || []).forEach(element => element?.addEventListener("input", render));
        i18n.onChange(render);
        render();
        return { isValid, render };
    }

    window.attachPasswordChecklist = attachPasswordChecklist;
})();
