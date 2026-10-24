"""Safe storage for UTF-8 text submissions (TXT, CSV, SQL)."""
import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
ALLOWED_EXTENSIONS = {".txt", ".csv", ".sql"}
try:
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
except ValueError:
    MAX_FILE_SIZE_MB = 5
if MAX_FILE_SIZE_MB < 1:
    MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
STORAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "secure_storage"))


def _get_file_extension(filename: str) -> str:
    return os.path.splitext(os.path.basename(filename or ""))[1].lower()


def _calculate_sha256(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


def validate_and_save_file(original_filename: str, file_content: bytes, submission_id: str):
    if not isinstance(file_content, (bytes, bytearray)):
        return False, None, None, None, None, "Nội dung file phải ở dạng bytes."
    content = bytes(file_content)
    size_bytes = len(content)
    if size_bytes == 0:
        return False, None, None, None, None, "File rỗng, thiếu đầu ra bắt buộc."
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return False, None, None, None, None, f"Vượt quá giới hạn dung lượng ({MAX_FILE_SIZE_MB}MB)."
    if b"\x00" in content:
        return False, None, None, None, None, "File chứa byte NUL không hợp lệ."
    try:
        content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False, None, None, None, None, "File phải có nội dung UTF-8 hợp lệ."
    ext = _get_file_extension(original_filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False, None, None, None, None, f"Định dạng {ext} không được hỗ trợ. Chỉ nhận TXT, CSV, SQL."
    file_type = ext[1:].upper()
    file_sha256 = _calculate_sha256(content)
    safe_filename = f"{uuid.UUID(str(submission_id))}_{uuid.uuid4().hex}{ext}"
    os.makedirs(STORAGE_ROOT, exist_ok=True)
    absolute_stored_path = os.path.abspath(os.path.join(STORAGE_ROOT, safe_filename))
    if os.path.commonpath([STORAGE_ROOT, absolute_stored_path]) != STORAGE_ROOT:
        return False, None, None, None, None, "Đường dẫn lưu file không hợp lệ."
    try:
        with open(absolute_stored_path, "xb") as f:
            f.write(content)
    except OSError as exc:
        return False, None, None, None, None, f"Lỗi hệ thống khi lưu tệp: {exc}"
    return True, f"secure_storage/{safe_filename}", file_type, size_bytes, file_sha256, "Thành công."


def _resolve_stored_path(relative_stored_path: str) -> str:
    """Resolve only a relative secure_storage filename inside STORAGE_ROOT."""
    raw = str(relative_stored_path or "").replace("\\", "/")
    parts = raw.split("/")
    if len(parts) != 2 or parts[0] != "secure_storage" or parts[1] in ("", ".", ".."):
        raise ValueError("Đường dẫn file không hợp lệ.")
    root = os.path.realpath(STORAGE_ROOT)
    target = os.path.realpath(os.path.join(root, parts[1]))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("Đường dẫn file nằm ngoài vùng lưu trữ.")
    return target


def read_stored_file(relative_stored_path: str) -> bytes:
    path = _resolve_stored_path(relative_stored_path)
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data:
        raise ValueError("File chứa byte NUL không hợp lệ.")
    data.decode("utf-8", errors="strict")
    return data


def delete_physical_file(relative_stored_path: str) -> bool:
    if not relative_stored_path or os.path.basename(str(relative_stored_path).replace("\\", "/")) in ("", ".", "..", ".gitkeep"):
        return False
    try:
        absolute_path = _resolve_stored_path(relative_stored_path)
        os.remove(absolute_path)
        return True
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False
