"""List every Vietnamese string a learner can see, so the English catalog can be checked for gaps.

Interpolated values become {0}, {1}, ... The same extraction backs tests/test_i18n.py.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VI = re.compile("[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.IGNORECASE)
# Sent to the model, used as search vocabulary, or read only by developers.
BACKEND_SKIP = {"assessment_provider.py", "security.py", "knowledge.py", "tool_registry.py", "mailer.py", "sql_sandbox_worker.py", "main.py"}
SKIP_NAMES = {"SYSTEM_PROMPT", "SUMMARY_PROMPT", "INSTRUCTIONS", "SYSTEM_INSTRUCTIONS", "JD_SUMMARY_INSTRUCTIONS", "ASSISTANT_NAME"}
JS_SKIP = {"i18n.js", "login.js", "password.js", "boot.js", "translate.js"}
# Field names in the catalogs that hold prose. Codes and search terms stay out.
DATA_FILES = ("skills_v1.json", "practice_items_v1.json", "job_profiles_v1.json", "jd_library_v4.json", "learning_resources_v4.json", "activities_v1.json", "tasks_v1.json", "skill_level_options_v5.json", "assessment_blueprints_v4.json", "assessment_rubrics_v1.json")
SENSITIVE_FILES = ("question_bank_v1.json", "exam_items_v5.json")
DATA_SKIP_KEYS = {"terms", "patterns", "labels", "expected_sql", "allowed_sql", "pattern", "forbid", "any", "all", "note"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _template_parts(text: str):
    """Yield (literal with {n} markers, nested expressions) for one template body."""
    out, nested, count, index = [], [], 0, 0
    while index < len(text):
        if text.startswith("${", index):
            depth, cursor = 1, index + 2
            while cursor < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[cursor], 0)
                cursor += 1
            nested.append(text[index + 2:cursor - 1])
            out.append(f"{{{count}}}")
            count += 1
            index = cursor
        else:
            out.append(text[index])
            index += 1
    return "".join(out), nested


def _html_pieces(text: str):
    for value in re.findall(r"""(?:placeholder|aria-label|title|alt)="([^"]*)\"""", text):
        yield value
    for piece in re.split(r"<[^>]*>", text):
        yield piece


def _renumber(text: str) -> str:
    seen: dict[str, int] = {}
    return re.sub(r"\{(\d+)\}", lambda match: f"{{{seen.setdefault(match.group(1), len(seen))}}}", text)


def js_strings(source: str) -> set[str]:
    found: set[str] = set()

    def visit(code: str) -> None:
        index = 0
        while index < len(code):
            char = code[index]
            if code.startswith("//", index):
                index = code.find("\n", index)
                index = len(code) if index < 0 else index
            elif code.startswith("/*", index):
                index = code.find("*/", index) + 2
            elif char in "\"'":
                end = index + 1
                while end < len(code) and code[end] != char:
                    end += 2 if code[end] == "\\" else 1
                add(code[index + 1:end], [])
                index = end + 1
            elif char == "`":
                end, depth = index + 1, 0
                while end < len(code):
                    if code[end] == "\\":
                        end += 2
                        continue
                    if code.startswith("${", end):
                        depth += 1
                        end += 2
                        continue
                    if depth and code[end] == "}":
                        depth -= 1
                    elif depth and code[end] == "{":
                        depth += 1
                    elif not depth and code[end] == "`":
                        break
                    end += 1
                body, nested = _template_parts(code[index + 1:end])
                add(body, nested)
                index = end + 1
            else:
                index += 1

    def add(text: str, nested: list[str]) -> None:
        for piece in _html_pieces(text):
            piece = _clean(piece.replace("\\n", " "))
            if VI.search(piece):
                found.add(_renumber(piece))
        for expression in nested:
            visit(expression)

    visit(source)
    return found


def _skip_nodes(tree: ast.AST) -> set[int]:
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
            skipped.add(id(node.body[0].value))
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in SKIP_NAMES for target in node.targets):
            skipped.update(id(child) for child in ast.walk(node.value))
    return skipped


def python_strings(source: str) -> set[str]:
    tree = ast.parse(source)
    skipped = _skip_nodes(tree)
    found: set[str] = set()
    inside_fstring = {id(child) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for child in node.values if isinstance(child, ast.Constant)}
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.JoinedStr):
            parts, count = [], 0
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                else:
                    parts.append(f"{{{count}}}")
                    count += 1
            text = _clean("".join(parts))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in inside_fstring:
            text = _clean(node.value)
        else:
            continue
        if VI.search(text) and text.count("\\") < 2:
            found.add(text)
    return found


def data_strings(value, key: str = "") -> set[str]:
    found: set[str] = set()
    if key in DATA_SKIP_KEYS:
        return found
    if isinstance(value, dict):
        for name, item in value.items():
            if VI.search(name):
                found.add(_clean(name))
            found |= data_strings(item, name)
    elif isinstance(value, list):
        for item in value:
            found |= data_strings(item, key)
    elif isinstance(value, str) and VI.search(value):
        found.add(value.strip())
    return found


def ui_catalog() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "frontend" / "js").rglob("*.js"):
        if path.name not in JS_SKIP:
            found |= js_strings(path.read_text(encoding="utf-8"))
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for piece in _html_pieces(re.sub(r"<script.*?</script>|<link[^>]*>|<meta[^>]*>", "", html, flags=re.S)):
        if VI.search(piece):
            found.add(_clean(piece))
    return found


def backend_catalog() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "backend").rglob("*.py"):
        if path.name not in BACKEND_SKIP:
            found |= python_strings(path.read_text(encoding="utf-8"))
    return found


def data_catalog() -> set[str]:
    found: set[str] = set()
    for name in DATA_FILES:
        found |= data_strings(json.loads((ROOT / "data" / name).read_text(encoding="utf-8")))
    return found


def sensitive_catalog() -> set[str]:
    found: set[str] = set()
    for name in SENSITIVE_FILES:
        found |= data_strings(json.loads((ROOT / "data" / name).read_text(encoding="utf-8")))
    return found


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    groups = {"ui": ui_catalog(), "backend": backend_catalog(), "data": data_catalog(), "sensitive": sensitive_catalog()}
    print({name: (len(items), sum(map(len, items))) for name, items in groups.items()})
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        target.mkdir(parents=True, exist_ok=True)
        for name, items in groups.items():
            (target / f"{name}.txt").write_text("\n".join(sorted(item.replace("\n", "\\n") for item in items)), encoding="utf-8")
