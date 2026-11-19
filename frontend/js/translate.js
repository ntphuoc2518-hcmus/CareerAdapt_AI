/**
 * English display layer. Vietnamese stays the source everywhere: state, API payloads and form values
 * are never changed, so a saved edit can not overwrite the original content with its translation.
 * The observer runs before the browser paints, so English readers never see Vietnamese flash.
 * Text the learner wrote stays as written: inputs, code blocks and [data-no-i18n].
 */
// "Sai:" is the one label with no tone mark, so it needs naming.
const VIETNAMESE = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]|^Sai: /i;
const ATTRIBUTES = ["placeholder", "title", "aria-label", "alt"];
const SKIP = "textarea, script, style, code, pre, .code, .CodeMirror, [data-no-i18n]";
const SEPARATORS = [/ · /, /(?<=[.!?;])\s+/, /(?<=:)\s+/, / — /, /, /];

const SENTENCE_BREAK = /[.!?;]\s+\S/;

const exact = new Map();
const cache = new Map();
let patterns = [];
let active = false;
const missing = new Set();

const escapeRegex = text => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function addEntries(entries) {
    const added = [];
    for (const [source, target] of Object.entries(entries)) {
        if (/\{\d+\}/.test(source)) {
            const order = [];
            // Side-by-side values cannot be told apart, so the first takes them all and the rest stay empty.
            const body = source.split(/(\{\d+\})/).filter(Boolean).map((part, index, parts) => {
                const match = part.match(/^\{(\d+)\}$/);
                if (!match) return escapeRegex(part);
                order.push(Number(match[1]));
                if (/^\{\d+\}$/.test(parts[index - 1] || "")) return "()";
                return /^\{\d+\}$/.test(parts[index + 1] || "") ? "(.+)" : "(.+?)";
            }).join("");
            added.push({ regex: new RegExp(`^${body}$`, "s"), order, target, weight: source.replace(/\{\d+\}/g, "").length, anchored: !source.startsWith("{") });
        } else {
            exact.set(source, target);
        }
    }
    patterns = [...patterns, ...added].sort((a, b) => b.weight - a.weight);
    cache.clear();
}

/** A pattern that opens with a value, such as "{0} level {1}", must not claim a whole paragraph. */
function byPattern(text, minimumCover, strict = false) {
    for (const { regex, order, target, weight, anchored } of patterns) {
        if ((strict || !anchored) && weight / text.length < minimumCover) continue;
        const match = text.match(regex);
        if (match) {
            const values = {};
            order.forEach((index, position) => { values[index] = translateText(match[position + 1]); });
            return target.replace(/\{(\d+)\}/g, (all, index) => values[index] ?? all);
        }
    }
    return null;
}

/** "Skill name:" or "Two levels short." can be a known label plus its punctuation. */
function withoutEnding(text) {
    const match = text.match(/^(.*?)([.:;,])$/s);
    const hit = match && (exact.get(match[1]) ?? exact.get(match[1].toLowerCase()));
    return hit ? `${hit.replace(/[.:;,]$/, "")}${match[2]}` : null;
}

function bySplitting(text) {
    for (const separator of SEPARATORS) {
        const parts = text.split(separator);
        if (parts.length > 1) {
            const joiner = text.match(separator)[0];
            return parts.map(translateText).join(joiner.trim() ? joiner : " ");
        }
    }
    return null;
}

/** Whole sentence first, then a sentence with values, then its smaller parts. */
export function translateText(text) {
    if (!active) return text;
    if (exact.has(text)) return exact.get(text);
    const trimmed = text.replace(/\s+/g, " ").trim();
    const clean = trimmed.replace(/^·\s*|\s*·$/g, "");
    if (!clean || !VIETNAMESE.test(clean)) return exact.get(clean) ?? text;
    const lead = trimmed.startsWith("·") ? "· " : "";
    const tail = trimmed.endsWith("·") ? " ·" : "";
    if (!cache.has(clean)) {
        cache.set(clean, clean);
        // A line built from dotted parts is safest piece by piece; a pattern could swallow two of them.
        const multiSentence = SENTENCE_BREAK.test(clean);
        let result = exact.get(clean) ?? exact.get(clean.toLowerCase()) ?? withoutEnding(clean) ?? (clean.includes(" · ") ? bySplitting(clean) : null)
            ?? (multiSentence ? byPattern(clean, 0.6, true) ?? bySplitting(clean) : byPattern(clean, 0.4)) ?? bySplitting(clean) ?? byPattern(clean, 0);
        if (result === null) {
            result = clean;
            missing.add(clean);
        }
        // Two amounts joined in a sentence; a general "{0} and {1}" pattern would split real titles.
        cache.set(clean, result.replace(/(\d) và (\d)/g, "$1 and $2"));
    }
    return `${lead}${cache.get(clean)}${tail}`;
}

function keepSpacing(original, translated) {
    if (translated === original) return original;
    const [lead] = original.match(/^\s*/);
    const [trail] = original.match(/\s*$/);
    return `${lead}${translated.trim()}${trail}`;
}

function translateNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        if (!node.parentElement?.closest(SKIP)) {
            const next = keepSpacing(node.nodeValue, translateText(node.nodeValue));
            if (next !== node.nodeValue) node.nodeValue = next;
        }
        return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.matches("[data-no-i18n], script, style")) return;
    for (const name of ATTRIBUTES) {
        const value = node.getAttribute(name);
        if (value) {
            const next = translateText(value);
            if (next !== value) node.setAttribute(name, next);
        }
    }
    if (node.matches('a[href="/guides/report-writing.html"]')) node.setAttribute("href", "/guides/report-writing.en.html");
    // The seeded major is not something the learner wrote. Other inputs keep their source for editing.
    if (node.matches('input[name="major"]') && exact.has(node.value)) node.value = exact.get(node.value);
    if (node.matches("textarea, pre, code, .code")) return;
    node.childNodes.forEach(translateNode);
}

export function startObserver() {
    new MutationObserver(records => {
        for (const record of records) {
            if (record.type === "characterData") translateNode(record.target);
            else if (record.type === "attributes") translateNode(record.target);
            else record.addedNodes.forEach(translateNode);
        }
    }).observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTES });
}

/** Loads before the first page renders. A failed load leaves one whole language, not a mix. */
export async function startTranslator() {
    if (window.i18n?.getLang() !== "en") return false;
    const response = await fetch(`/js/lang/en.json?v=${document.documentElement.dataset.build || "1"}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`catalog ${response.status}`);
    addEntries(await response.json());
    active = true;
    translateNode(document.documentElement);
    startObserver();
    window.careerI18n = { missing: () => [...missing], translateText };
    return true;
}

/** Admins also see the private exam content, which is not in the public catalog. */
export function addPrivateCatalog(entries) {
    if (!active) return;
    addEntries(entries);
    translateNode(document.body);
}

export const isTranslating = () => active;
