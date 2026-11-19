"""5.57: the design system stays in one place.

- tokens.css loads on the app and the sign-in page, after boot.js and before the page's own stylesheet;
- the shared components read the scales (type, radius, motion, layers) instead of literal values;
- app.css carries no dead declarations: no rule sets a property that a later rule with the very same selector,
  in the same at-rule, sets again (the clean-up of 5.57 removed 125 of them and proved the page looked the same).
"""
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "frontend" / "css"
TOKENS = (CSS / "tokens.css").read_text(encoding="utf-8")
APP = (CSS / "app.css").read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def rules(text: str):
    """(context, selector, [(property, important)]) for every style rule; @keyframes bodies are skipped."""
    clean = strip_comments(text)
    found = []

    def block(start: int, end: int, context: tuple):
        i = start
        while i < end:
            open_at = clean.find("{", i, end)
            if open_at < 0:
                return
            prelude = clean[i:open_at].strip().split(";")[-1].strip()
            depth, j = 0, open_at
            while j < end:
                if clean[j] == "{":
                    depth += 1
                elif clean[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if prelude.startswith("@"):
                if prelude.split()[0] in ("@media", "@supports", "@container", "@layer"):
                    block(open_at + 1, j, context + (" ".join(prelude.split()),))
            else:
                decls = []
                for part in clean[open_at + 1:j].split(";"):
                    if ":" in part:
                        name, value = part.split(":", 1)
                        decls.append((name.strip().lower(), "!important" in value.replace(" ", "")))
                found.append((context, " ".join(prelude.split()), decls))
            i = j + 1

    block(0, len(clean), ())
    return found


def test_tokens_define_every_scale():
    for name in ("--fs-base", "--fw-semibold", "--sp-4", "--radius-md", "--radius-pill", "--shadow-lg", "--control-md", "--dur-2", "--ease-out", "--z-modal", "--z-toast", "--z-skip"):
        assert re.search(rf"{name}\s*:", TOKENS), name


def test_both_pages_load_the_tokens_first():
    for page, own in (("index.html", "/css/app.css"), ("login.html", "/css/login.css")):
        html = (ROOT / "frontend" / page).read_text(encoding="utf-8")
        assert html.index("/js/boot.js") < html.index("/css/tokens.css") < html.index(own), page


def test_global_layers_use_the_layer_tokens():
    literal = [line.strip()[:80] for line in APP.splitlines() if re.search(r"z-index:\s*(5|10|20|25|30|40|41|45|60|70|80|100)\s*[;}]", line)]
    assert literal == []


def test_type_has_no_half_pixel_sizes():
    assert re.findall(r"font-size:\s*\d+\.5px", APP) == []


def test_app_css_has_no_dead_declarations():
    by_selector = defaultdict(list)
    parsed = rules(APP)
    for order, (context, selector, decls) in enumerate(parsed):
        for single in selector.split(","):
            by_selector[(context, single.strip())].append((order, decls))
    dead = []
    for order, (context, selector, decls) in enumerate(parsed):
        for name, important in decls:
            overridden = all(
                any(later > order and any(prop == name and (imp or not important) for prop, imp in later_decls) for later, later_decls in by_selector[(context, single.strip())])
                for single in selector.split(","))
            if overridden:
                dead.append(f"{selector} {{ {name} }}")
    assert dead == []
