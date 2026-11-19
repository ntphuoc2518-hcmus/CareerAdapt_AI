/** The coloured summary band at the top of the Kế hoạch Career Adapt tabs (same look as the Nhắc nhở band).
 *  Callers pass text that is already escaped; every figure comes from data the page already loaded. */
import { icon } from "./icons.js";

/**
 * @param {object} options
 * @param {string} options.tone   accent of this tab: brand, violet, teal, green, amber
 * @param {string} options.icon   icon name for the small label
 * @param {string} options.kicker small label above the title
 * @param {string} options.title  one sentence that says where the learner stands
 * @param {string} [options.text] one line of context under the title
 * @param {Array<[string, string, string|number, string?]>} [options.stats] [icon, label, value, tone]
 */
export function pageHero({ tone = "brand", icon: name, kicker, title, text = "", stats = [] }) {
    const tiles = stats.map(([statIcon, label, value, statTone = "brand"]) => {
        // Words and dates are set smaller than counts so every tile keeps one line.
        const wordy = String(value).length > 6 ? ' class="is-text"' : "";
        return `<div class="rm-kpi is-${statTone}"><span class="rm-kpi-icon">${icon(statIcon)}</span><b${wordy}>${value}</b><span>${label}</span></div>`;
    }).join("");
    return `<section class="rm-hero page-hero is-${tone}"><div class="rm-hero-text"><span class="rm-hero-kicker">${icon(name)}<span>${kicker}</span></span><h2>${title}</h2>${text ? `<p>${text}</p>` : ""}</div>
        ${tiles ? `<div class="rm-hero-stats" style="--n:${stats.length}">${tiles}</div>` : ""}</section>`;
}
