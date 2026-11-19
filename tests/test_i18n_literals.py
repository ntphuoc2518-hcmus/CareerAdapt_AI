"""5.56.1: every plain Vietnamese string literal in the app's scripts has an English entry.

The interface extractor reads strings inside markup and calls; a literal elsewhere, such as a parameter's default
value (the "Đang tải dữ liệu..." loader), slipped past it and showed in Vietnamese while the app was in English.
This scan reads every quoted literal instead. Literals that are not shown as they are sit in ``NOT_SHOWN``.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "frontend" / "js" / "lang" / "en.json").read_text(encoding="utf-8"))
VIETNAMESE = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE)
LITERAL = re.compile(r'"([^"\\\n$<>{}]{2,200})"|\'([^\'\\\n$<>{}]{2,200})\'')
# Own bilingual tables (boot.js theme labels, i18n.js, login.js) and text that is never shown on its own.
SKIP_FILES = {"i18n.js", "login.js"}
NOT_SHOWN = {
    "bấm để chuyển sang",  # boot.js: the theme button's own Vietnamese/English label table
    "mã | nội dung",  # contribute.js: quoted inside a longer label that is translated whole
    "Trình độ đã xác thực: Chưa có nền tảng (mức 0/3).",  # core.js: an example in a comment
    "Bước 1/6",  # guide.js: an example in a JSDoc comment
}


def untranslated() -> dict[str, str]:
    found = {}
    for path in (ROOT / "frontend" / "js").rglob("*.js"):
        if path.name in SKIP_FILES or "vendor" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in LITERAL.finditer(line):
                text = (match.group(1) or match.group(2)).strip()
                if not VIETNAMESE.search(text) or text in NOT_SHOWN or text in CATALOG:
                    continue
                if text.rstrip(".:…!?") in CATALOG or text + "." in CATALOG:
                    continue
                found.setdefault(text, f"{path.name}:{number}")
    return found


def test_every_vietnamese_literal_in_the_scripts_has_an_english_entry():
    missing = untranslated()
    assert not missing, "\n".join(f"{where}: {text}" for text, where in missing.items())


def test_the_loading_message_is_translated():
    assert CATALOG["Đang tải dữ liệu..."] == "Loading data..."
