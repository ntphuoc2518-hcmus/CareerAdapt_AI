"""Profile pictures: check an uploaded image and turn it into a small, clean square WebP.

The upload is never stored as sent. Pillow decodes it (so only real PNG, JPEG or WebP images pass), the
pixel count is checked before decoding to refuse decompression bombs, the picture is turned upright,
cropped to a centred square and re-encoded at 256x256. Re-encoding drops any metadata (GPS position,
camera data) and anything hidden after the image data.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 3 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
SIZE = 256


class AvatarError(ValueError):
    pass


def process_avatar(data: bytes) -> bytes:
    if not data:
        raise AvatarError("Hãy chọn một tệp ảnh.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AvatarError("Ảnh lớn hơn 3 MB. Hãy chọn ảnh nhỏ hơn.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise AvatarError("Tệp không phải ảnh PNG, JPG hoặc WebP hợp lệ.") from None
    if kind not in ALLOWED_FORMATS:
        raise AvatarError("Chỉ nhận ảnh PNG, JPG hoặc WebP.")
    if width * height > MAX_PIXELS or min(width, height) < 32:
        raise AvatarError("Kích thước ảnh không phù hợp (cạnh ngắn ít nhất 32 px, tối đa khoảng 40 triệu điểm ảnh).")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
            image = ImageOps.fit(image, (SIZE, SIZE), Image.LANCZOS, centering=(0.5, 0.45))
            if image.mode == "RGBA":
                # Transparent corners would show the page through; give them a neutral background.
                background = Image.new("RGB", image.size, (232, 239, 252))
                background.paste(image, mask=image.getchannel("A"))
                image = background
            out = io.BytesIO()
            image.save(out, format="WEBP", quality=86, method=4)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise AvatarError("Không đọc được ảnh này. Hãy thử ảnh khác.") from None
    return out.getvalue()


def thumbnail_data_uri(image: bytes, size: int = 64) -> str:
    """A small copy of a stored picture as a data URI, for lists such as the leaderboard."""
    import base64

    with Image.open(io.BytesIO(image)) as picture:
        small = picture.convert("RGB").resize((size, size), Image.LANCZOS)
        out = io.BytesIO()
        small.save(out, format="WEBP", quality=80, method=4)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")


CHAT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
CHAT_IMAGE_SIDE = 1280


def process_chat_image(data: bytes) -> bytes:
    """An image attached to an assistant question: checked like a profile picture, then re-encoded as JPEG,
    at most 1280 px on the long side. Re-encoding drops metadata such as GPS position."""
    if not data:
        raise AvatarError("Hãy chọn một tệp ảnh.")
    if len(data) > CHAT_IMAGE_MAX_BYTES:
        raise AvatarError("Ảnh lớn hơn 5 MB. Hãy chọn ảnh nhỏ hơn.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            kind = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise AvatarError("Tệp không phải ảnh PNG, JPG hoặc WebP hợp lệ.") from None
    if kind not in ALLOWED_FORMATS:
        raise AvatarError("Chỉ nhận ảnh PNG, JPG hoặc WebP.")
    if width * height > MAX_PIXELS or min(width, height) < 16:
        raise AvatarError("Kích thước ảnh không phù hợp.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA", "P"):
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, (255, 255, 255))
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = image.convert("RGB")
            image.thumbnail((CHAT_IMAGE_SIDE, CHAT_IMAGE_SIDE), Image.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise AvatarError("Không đọc được ảnh này. Hãy thử ảnh khác.") from None
    return out.getvalue()
