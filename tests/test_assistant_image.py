"""An image attached to an assistant question (5.27): checked, cleaned, sent to the model, never stored."""
import base64
import io

import pytest
from PIL import Image

from ai_helpers import use_fake
from backend.ai_service.assistant import IMAGE_WITHOUT_AI
from backend.avatar import AvatarError, process_chat_image
from backend.store import store
from v5_helpers import STUDENT, STUDENT_2, client, clock

A = "/api/v1/assistant"


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()
    clock.set_clock(None)


def picture(kind="PNG", size=(64, 48), mode="RGB"):
    out = io.BytesIO()
    Image.new(mode, size, (30, 90, 200) if mode == "RGB" else (30, 90, 200, 0)).save(out, format=kind)
    return out.getvalue()


def conversation(headers=STUDENT):
    return client.post(f"{A}/conversations", headers=headers).json()["conversation_id"]


def ask_with(data, text="Ảnh này nói gì?", headers=STUDENT, conversation_id=None, name="a.png", mime="image/png"):
    return client.post(f"{A}/conversations/{conversation_id or conversation(headers)}/messages/image",
                       data={"content": text, "page": "dashboard"}, files={"image": (name, data, mime)}, headers=headers)


def test_the_image_reaches_the_model_and_only_a_note_is_stored(monkeypatch):
    fake = use_fake(monkeypatch, ["Ảnh cho thấy một biểu đồ màu xanh."])
    conversation_id = conversation()
    response = ask_with(picture(), conversation_id=conversation_id)
    assert response.status_code == 200, response.text
    sent = fake.requests[0].messages[-1]
    assert sent.role == "user" and len(sent.images) == 1 and sent.images[0][0] == "image/jpeg"
    decoded = Image.open(io.BytesIO(base64.b64decode(sent.images[0][1])))
    assert decoded.format == "JPEG" and decoded.size == (64, 48)
    messages = client.get(f"{A}/conversations/{conversation_id}", headers=STUDENT).json()["messages"]
    assert messages[0]["attachment"] == "image" and messages[0]["content"] == "Ảnh này nói gì?"
    stored = str(store.db.query("SELECT content, meta FROM ai_messages"))
    assert sent.images[0][1][:40] not in stored


def test_a_transparent_png_is_flattened_and_a_large_image_is_shrunk():
    cleaned = Image.open(io.BytesIO(process_chat_image(picture(size=(3000, 1000), mode="RGBA"))))
    assert cleaned.mode == "RGB" and max(cleaned.size) == 1280


@pytest.mark.parametrize("data", [b"", b"not an image at all", picture(kind="GIF"), picture(size=(10, 10))])
def test_bad_images_are_refused(data):
    with pytest.raises(AvatarError):
        process_chat_image(data)


def test_the_endpoint_refuses_a_fake_image_without_saving_anything():
    conversation_id = conversation()
    response = ask_with(b"<script>alert(1)</script>", conversation_id=conversation_id, name="x.png")
    assert response.status_code == 422
    assert client.get(f"{A}/conversations/{conversation_id}", headers=STUDENT).json()["messages"] == []


def test_without_ai_the_answer_says_the_image_was_not_read():
    response = ask_with(picture())
    assert response.status_code == 200 and response.json()["mode"] == "RULE"
    assert IMAGE_WITHOUT_AI in response.json()["content"]


def test_another_account_cannot_post_an_image_into_my_conversation():
    conversation_id = conversation()
    assert ask_with(picture(), headers=STUDENT_2, conversation_id=conversation_id).status_code == 404


def test_the_image_route_needs_a_session_and_csrf_protection():
    files = {"image": ("a.png", picture(), "image/png")}
    assert client.post(f"{A}/conversations/x/messages/image", data={"content": "hi"}, files=files).status_code == 403


def test_the_page_may_use_the_microphone_but_not_the_camera():
    policy = client.get("/health").headers["Permissions-Policy"]
    assert "microphone=(self)" in policy and "camera=()" in policy
