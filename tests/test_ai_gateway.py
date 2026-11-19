"""AI Model Gateway and the Gemini adapter, with the network replaced at urlopen."""
import io
import json
from urllib.error import HTTPError, URLError

import pytest

from backend import config
from backend.ai_service import assessment_provider, gateway
from backend.ai_service.assessment_provider import AssessmentProviderError
from backend.ai_service.gateway import ChatRequest, GatewayError, Message
from backend.store import store

KEY = "AIza-test-secret"
SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}, "required": ["summary"], "additionalProperties": False}


class Reply:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


def gemini_text(text, **extra):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7, "thoughtsTokenCount": 2}, **extra}


@pytest.fixture
def network(monkeypatch):
    calls = []
    queue = []

    def fake(request, timeout):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "body": json.loads(request.data), "timeout": timeout})
        step = queue.pop(0)
        if isinstance(step, Exception):
            raise step
        return Reply(step)

    store.reset()
    monkeypatch.setattr(gateway, "urlopen", fake)
    monkeypatch.setattr(gateway, "_sleep", lambda seconds: None)
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "LLM_API_KEY", KEY)
    monkeypatch.setattr(config, "LLM_MODEL", "gemini-test")
    yield calls, queue
    store.reset()


def http_error(code):
    return HTTPError("https://x", code, "err", {}, io.BytesIO(f"body with {KEY}".encode()))


def simple_request(**extra):
    return ChatRequest(system="sys", messages=[Message("user", "hỏi")], **extra)


def test_chat_sends_the_key_in_a_header_and_never_in_the_url(network):
    calls, queue = network
    queue.append(gemini_text("Trả lời"))
    result = gateway.chat(simple_request(), task="test")
    assert result.text == "Trả lời" and (result.input_tokens, result.output_tokens) == (11, 9)
    assert KEY not in calls[0]["url"] and calls[0]["url"].endswith("/gemini-test:generateContent")
    assert calls[0]["headers"]["X-goog-api-key"] == KEY
    assert calls[0]["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_tool_declarations_fit_what_gemini_accepts(network):
    calls, queue = network
    queue.append(gemini_text("ok"))
    tools = [{"name": "no_args", "description": "d", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
             {"name": "with_args", "description": "d", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "additionalProperties": False}}]
    gateway.chat(simple_request(tools=tools), task="test")
    declared = calls[0]["body"]["tools"][0]["functionDeclarations"]
    assert "parameters" not in declared[0]
    assert declared[1]["parameters"] == {"type": "object", "properties": {"query": {"type": "string"}}}


def test_a_function_call_and_its_thought_signature_go_back_unchanged(network):
    calls, queue = network
    parts = [{"functionCall": {"name": "get_my_skill_gap", "args": {}, "id": "c1"}, "thoughtSignature": "SIGNED"}]
    queue.extend([{"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]}, gemini_text("Xong")])
    first = gateway.chat(simple_request(), task="test")
    assert first.tool_calls[0].name == "get_my_skill_gap" and first.tool_calls[0].call_id == "c1"
    follow_up = ChatRequest(system="s", messages=[Message("user", "hỏi"), Message("assistant", tool_calls=first.tool_calls, raw=first.raw), Message("tool", tool_results=[{"name": "get_my_skill_gap", "call_id": "c1", "data": {"untrusted_data": {"coverage": 60}}}])])
    gateway.chat(follow_up, task="test")
    contents = calls[1]["body"]["contents"]
    assert contents[1]["parts"] == parts
    assert contents[2] == {"role": "user", "parts": [{"functionResponse": {"name": "get_my_skill_gap", "response": {"untrusted_data": {"coverage": 60}}, "id": "c1"}}]}


def test_thought_parts_are_not_shown_as_the_answer(network):
    _, queue = network
    queue.append({"candidates": [{"content": {"parts": [{"text": "suy nghĩ riêng", "thought": True}, {"text": "Câu trả lời"}]}, "finishReason": "STOP"}]})
    assert gateway.chat(simple_request(), task="test").text == "Câu trả lời"


def test_structured_output_is_returned_when_it_matches(network):
    calls, queue = network
    queue.append(gemini_text('{"summary": "tóm tắt", "items": ["a"]}'))
    assert gateway.structured("sys", {"x": 1}, SCHEMA, task="test") == {"summary": "tóm tắt", "items": ["a"]}
    assert calls[0]["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert calls[0]["body"]["generationConfig"]["responseJsonSchema"] == SCHEMA


@pytest.mark.parametrize("text, code", [("không phải json", "AI_INVALID_JSON"), ('{"items": []}', "AI_INVALID_SCHEMA"), ('{"summary": 5}', "AI_INVALID_SCHEMA"), ('{"summary": "x", "extra": 1}', "AI_INVALID_SCHEMA"), ('{"summary": "x", "items": [1]}', "AI_INVALID_SCHEMA")])
def test_structured_output_with_the_wrong_shape_is_refused(network, text, code):
    _, queue = network
    queue.append(gemini_text(text))
    with pytest.raises(GatewayError) as caught:
        gateway.structured("sys", {}, SCHEMA, task="test")
    assert caught.value.code == code
    assert store.db.one("SELECT status, error FROM ai_usage_traces WHERE status = 'REJECTED'")["error"] == code


def test_a_timeout_is_retried_a_limited_number_of_times(network):
    calls, queue = network
    queue.extend([TimeoutError(), TimeoutError(), TimeoutError(), gemini_text("không tới")])
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test")
    assert caught.value.code == "AI_TIMEOUT" and len(calls) == 1 + config.LLM_MAX_RETRIES
    assert store.db.one("SELECT attempts, status FROM ai_usage_traces") == {"attempts": 3, "status": "FAILED"}


def test_a_temporary_failure_recovers_on_retry(network):
    calls, queue = network
    queue.extend([http_error(429), http_error(503), gemini_text("ok")])
    assert gateway.chat(simple_request(), task="test").text == "ok" and len(calls) == 3


@pytest.mark.parametrize("code, expected", [(400, "AI_BAD_REQUEST"), (401, "AI_AUTH"), (403, "AI_AUTH"), (404, "AI_MODEL_NOT_FOUND")])
def test_a_permanent_failure_is_not_retried_and_leaks_nothing(network, code, expected):
    calls, queue = network
    queue.append(http_error(code))
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test")
    assert caught.value.code == expected and len(calls) == 1 and KEY not in str(caught.value)


def test_network_failure_is_reported_as_unavailable(network):
    _, queue = network
    queue.extend([URLError("no route"), URLError("no route"), URLError("no route")])
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test")
    assert caught.value.code == "AI_UNAVAILABLE"


def test_a_passed_deadline_makes_no_call(network):
    calls, _ = network
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test", deadline=0)
    assert caught.value.code == "AI_TIMEOUT" and not calls


@pytest.mark.parametrize("body, code", [({"promptFeedback": {"blockReason": "SAFETY"}}, "AI_BLOCKED"), ({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}, "AI_BLOCKED")])
def test_a_blocked_prompt_is_a_clear_error(network, body, code):
    _, queue = network
    queue.append(body)
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test")
    assert caught.value.code == code


def test_usage_traces_hold_numbers_and_no_content(network):
    _, queue = network
    queue.append(gemini_text("nội dung bí mật của câu trả lời"))
    gateway.chat(ChatRequest(system="sys", messages=[Message("user", "câu hỏi riêng tư")]), task="test", user_id="u1")
    row = store.db.one("SELECT * FROM ai_usage_traces")
    assert (row["input_tokens"], row["output_tokens"], row["model"], row["provider"]) == (11, 9, "gemini-test", "gemini")
    assert "riêng tư" not in json.dumps(row, ensure_ascii=False) and "bí mật" not in json.dumps(row, ensure_ascii=False)


def test_embedding_keeps_one_vector_per_input_and_counts_an_estimate(network):
    calls, queue = network
    queue.append({"embeddings": [{"values": [1, 0]}, {"values": [0, 1]}]})
    assert gateway.embed(["a", "b"], purpose="document") == [[1, 0], [0, 1]]
    requests = calls[0]["body"]["requests"]
    assert len(requests) == 2 and requests[0]["content"]["parts"][0]["text"].startswith("title:") and requests[0]["outputDimensionality"] == gateway.EMBED_DIMENSIONS
    assert calls[0]["url"].endswith(":batchEmbedContents")


def test_a_missing_vector_is_an_error(network):
    _, queue = network
    queue.extend([{"embeddings": [{"values": [1]}]}] * 3)
    with pytest.raises(GatewayError):
        gateway.embed(["a", "b"], purpose="query")


def test_the_older_embedding_model_uses_task_types(network, monkeypatch):
    calls, queue = network
    monkeypatch.setattr(config, "AI_EMBEDDING_MODEL", "gemini-embedding-001")
    queue.append({"embeddings": [{"values": [1]}]})
    gateway.embed(["a"], purpose="query")
    assert calls[0]["body"]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


def test_grading_goes_through_the_gateway_with_one_attempt(network):
    calls, queue = network
    queue.extend([TimeoutError(), gemini_text("không tới")])
    with pytest.raises(AssessmentProviderError) as caught:
        assessment_provider._call_gemini("sys", {"x": 1}, SCHEMA)
    assert caught.value.code == "AI_TIMEOUT" and len(calls) == 1


def test_grading_output_with_the_wrong_shape_uses_the_existing_error_code(network):
    _, queue = network
    queue.append(gemini_text("không phải json"))
    with pytest.raises(AssessmentProviderError) as caught:
        assessment_provider._call_gemini("sys", {"x": 1}, SCHEMA)
    assert caught.value.code == "AI_INVALID_JSON"


def test_existing_llm_settings_still_drive_the_provider(network):
    assert assessment_provider.is_enabled() and assessment_provider.active_model() == "gemini-test"


def test_openai_setting_keeps_the_grading_path_but_has_no_assistant_adapter(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    assert assessment_provider.is_enabled() and not gateway.is_available()


def test_mock_provider_means_the_gateway_is_off(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "mock")
    assert not gateway.is_available()
    with pytest.raises(GatewayError) as caught:
        gateway.chat(simple_request(), task="test")
    assert caught.value.code == "AI_NOT_CONFIGURED"


def test_a_new_provider_only_needs_to_be_registered(monkeypatch):
    class Other:
        requires_key = False
        default_model = "m"
        default_embedding_model = "e"

        def __init__(self, key, model, embedding):
            self.model = model
            self.embedding_model = embedding

        def chat(self, request, timeout):
            return gateway.ChatResult(text="từ provider khác", tool_calls=[], model=self.model)

    store.reset()
    monkeypatch.setitem(gateway.PROVIDERS, "other", Other)
    monkeypatch.setattr(config, "LLM_PROVIDER", "other")
    assert gateway.chat(simple_request(), task="test").text == "từ provider khác"
    store.reset()


def test_an_attached_image_is_sent_as_inline_data_after_the_text(network):
    calls, queue = network
    queue.append(gemini_text("Thấy rồi"))
    request = ChatRequest(system="sys", messages=[Message("user", "ảnh gì?", images=[("image/jpeg", "QUJD")])])
    gateway.chat(request, task="test")
    assert calls[0]["body"]["contents"][0]["parts"] == [{"text": "ảnh gì?"}, {"inlineData": {"mimeType": "image/jpeg", "data": "QUJD"}}]
