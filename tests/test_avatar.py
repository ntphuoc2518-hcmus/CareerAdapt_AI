"""Profile pictures (5.23): upload, replace, remove; only real images; never another account's picture."""
import io

import pytest
from PIL import Image

from backend.avatar import MAX_UPLOAD_BYTES, AvatarError, process_avatar
from test_auth_sessions import _signed_in, _write_headers, reset_throttles  # noqa: F401  (fixture reused)


def image_bytes(fmt="PNG", size=(400, 300), color=(30, 90, 200), exif_gps=False):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    if exif_gps and fmt == "JPEG":
        exif = Image.Exif()
        exif[0x8825] = {2: (10.0, 46.0, 0.0)}  # GPS latitude
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, data, name="me.png", mime="image/png"):
    return client.put("/api/v1/auth/me/avatar", headers=_write_headers(client), files={"file": (name, data, mime)})


def test_upload_shows_the_picture_and_changes_the_version():
    client, _ = _signed_in()
    assert client.get("/api/v1/auth/me").json()["user"]["avatar_version"] is None
    assert client.get("/api/v1/auth/me/avatar").status_code == 404
    first = upload(client, image_bytes())
    assert first.status_code == 200 and first.json()["user"]["avatar_version"]
    picture = client.get("/api/v1/auth/me/avatar")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/webp"
    stored = Image.open(io.BytesIO(picture.content))
    assert stored.format == "WEBP" and stored.size == (256, 256)
    second = upload(client, image_bytes("JPEG", color=(200, 30, 30)), "me.jpg", "image/jpeg")
    assert second.json()["user"]["avatar_version"] >= first.json()["user"]["avatar_version"]


def test_remove_returns_to_the_initial():
    client, _ = _signed_in()
    upload(client, image_bytes())
    removed = client.delete("/api/v1/auth/me/avatar", headers=_write_headers(client))
    assert removed.status_code == 200 and removed.json()["user"]["avatar_version"] is None
    assert client.get("/api/v1/auth/me/avatar").status_code == 404


def test_each_account_sees_only_its_own_picture():
    alice, _ = _signed_in()
    bob, _ = _signed_in()
    upload(alice, image_bytes())
    assert bob.get("/api/v1/auth/me/avatar").status_code == 404


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"GIF89a" + b"\x00" * 64, b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"])
def test_files_that_are_not_png_jpg_or_webp_are_refused(data):
    client, _ = _signed_in()
    response = upload(client, data)
    assert response.status_code == 422 and response.json()["error"]["code"] == "AVATAR_INVALID"


def test_oversized_and_tiny_images_are_refused():
    client, _ = _signed_in()
    assert upload(client, b"\x89PNG" + b"0" * (MAX_UPLOAD_BYTES + 10)).status_code == 413
    assert upload(client, image_bytes(size=(10, 10))).status_code == 422


def test_metadata_is_dropped_and_the_crop_is_square():
    out = process_avatar(image_bytes("JPEG", size=(900, 300), exif_gps=True))
    image = Image.open(io.BytesIO(out))
    assert image.size == (256, 256) and not image.getexif()
    with pytest.raises(AvatarError):
        process_avatar(b"")


def test_upload_needs_a_session_and_the_csrf_token():
    client, _ = _signed_in()
    no_csrf = client.put("/api/v1/auth/me/avatar", headers={"Origin": "http://testserver"}, files={"file": ("a.png", image_bytes(), "image/png")})
    assert no_csrf.status_code == 403
    from fastapi.testclient import TestClient
    from backend.main import app
    stranger = TestClient(app)
    assert stranger.get("/api/v1/auth/me/avatar").status_code == 401
