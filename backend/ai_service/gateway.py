"""AI Model Gateway: the one door between CareerAdapt and any model provider.

Business code speaks in ``ChatRequest`` and ``ChatResult``. A provider is an adapter class in
``PROVIDERS``, so adding one touches nothing else. The gateway owns what every call needs: retries
with a limit, a deadline, safe errors and a usage trace. Provider bodies, headers and keys never
reach an error message, a log or a trace, and traces hold no prompt or reply text.
"""
from __future__ import annotations

import json
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from backend import config
from backend.clock import utcnow
from backend.store import store

GENERATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_BACKOFF_SECONDS = 4.0
EMBED_BATCH_SIZE = 50
EMBED_DIMENSIONS = 768


class GatewayError(RuntimeError):
    def __init__(self, message: str, code: str = "AI_UNAVAILABLE", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: Optional[str] = None


@dataclass
class Message:
    """role is user, assistant or tool. ``raw`` keeps a provider turn that must be echoed verbatim."""
    role: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    raw: Any = None
    # (mime type, base64 data) of images attached to a user turn; sent only to the provider, never stored.
    images: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ChatRequest:
    system: str
    messages: list[Message]
    tools: list[dict] = field(default_factory=list)
    json_schema: Optional[dict] = None
    max_output_tokens: int = 1500
    temperature: float = 0.2


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""
    raw: Any = None


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """One HTTP attempt, turned into a GatewayError that is safe to show or store."""
    request = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        code = error.code
        error.close()
        if code == 429:
            raise GatewayError("Dịch vụ AI đang giới hạn tần suất.", "AI_RATE_LIMITED", True) from None
        if code >= 500:
            raise GatewayError("Dịch vụ AI đang gặp sự cố.", "AI_UNAVAILABLE", True) from None
        if code in {401, 403}:
            raise GatewayError("Khóa dịch vụ AI không hợp lệ hoặc không có quyền.", "AI_AUTH") from None
        if code == 404:
            raise GatewayError("Không tìm thấy mô hình AI đã cấu hình.", "AI_MODEL_NOT_FOUND") from None
        raise GatewayError("Dịch vụ AI từ chối yêu cầu.", "AI_BAD_REQUEST") from None
    except (TimeoutError, socket.timeout):
        raise GatewayError("Dịch vụ AI phản hồi quá lâu.", "AI_TIMEOUT", True) from None
    except URLError as error:
        timed_out = "timed out" in str(error).lower()
        raise GatewayError("Dịch vụ AI phản hồi quá lâu." if timed_out else "Không kết nối được dịch vụ AI.", "AI_TIMEOUT" if timed_out else "AI_UNAVAILABLE", True) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise GatewayError("Dịch vụ AI trả về dữ liệu không đọc được.", "AI_INVALID_JSON", True) from None
    except OSError:
        raise GatewayError("Không kết nối được dịch vụ AI.", "AI_UNAVAILABLE", True) from None


class GeminiProvider:
    name = "gemini"
    requires_key = True
    default_model = "gemini-3.5-flash-lite"
    default_embedding_model = "gemini-embedding-2"

    def __init__(self, api_key: str, model: str, embedding_model: str):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key}

    @staticmethod
    def _content(message: Message) -> dict:
        if message.role == "tool":
            parts = []
            for result in message.tool_results:
                reply = {"name": result["name"], "response": result["data"]}
                if result.get("call_id"):
                    reply["id"] = result["call_id"]
                parts.append({"functionResponse": reply})
            return {"role": "user", "parts": parts}
        if message.raw is not None:
            # Model turns carry thought signatures that have to come back unchanged.
            return message.raw
        parts: list[dict] = [{"text": message.text}]
        if message.role == "user":
            parts += [{"inlineData": {"mimeType": mime, "data": data}} for mime, data in message.images]
        return {"role": "model" if message.role == "assistant" else "user", "parts": parts}

    def _body(self, request: ChatRequest) -> dict:
        generation: dict[str, Any] = {"temperature": request.temperature, "maxOutputTokens": request.max_output_tokens}
        if request.json_schema is not None:
            generation.update(responseMimeType="application/json", responseJsonSchema=request.json_schema)
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [self._content(message) for message in request.messages],
            "generationConfig": generation,
        }
        if request.tools:
            body["tools"] = [{"functionDeclarations": [self._declaration(tool) for tool in request.tools]}]
        return body

    @staticmethod
    def _declaration(tool: dict) -> dict:
        declaration = {"name": tool["name"], "description": tool["description"]}
        parameters = tool.get("parameters") or {}
        # Gemini refuses an object with no properties, and its schema subset has no additionalProperties.
        if parameters.get("properties"):
            declaration["parameters"] = {key: value for key, value in parameters.items() if key != "additionalProperties"}
        return declaration

    def chat(self, request: ChatRequest, timeout: float) -> ChatResult:
        url = f"{GENERATIVE_BASE}/{quote(self.model, safe='-._')}:generateContent"
        data = _post(url, self._body(request), self._headers(), timeout)
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise GatewayError("Dịch vụ AI từ chối xử lý nội dung này.", "AI_BLOCKED")
        candidates = data.get("candidates") or []
        if not candidates:
            raise GatewayError("AI không trả về nội dung.", "AI_EMPTY", True)
        candidate = candidates[0]
        reason = str(candidate.get("finishReason") or "")
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        calls = [ToolCall(part["functionCall"].get("name", ""), part["functionCall"].get("args") or {}, part["functionCall"].get("id")) for part in parts if part.get("functionCall")]
        if reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}:
            raise GatewayError("Dịch vụ AI từ chối xử lý nội dung này.", "AI_BLOCKED")
        if not text and not calls:
            raise GatewayError("AI không trả về nội dung.", "AI_EMPTY", True)
        usage = data.get("usageMetadata") or {}
        return ChatResult(text=text, tool_calls=calls, model=self.model, input_tokens=int(usage.get("promptTokenCount") or 0) + int(usage.get("toolUsePromptTokenCount") or 0),
                          output_tokens=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0), finish_reason=reason, raw={"role": "model", "parts": parts})

    def _embedding_request(self, text: str, purpose: str) -> dict:
        request: dict[str, Any] = {"model": f"models/{self.embedding_model}", "outputDimensionality": EMBED_DIMENSIONS}
        if "embedding-001" in self.embedding_model:
            request["taskType"] = "RETRIEVAL_QUERY" if purpose == "query" else "RETRIEVAL_DOCUMENT"
        else:
            text = f"task: search result | query: {text}" if purpose == "query" else f"title: none | text: {text}"
        request["content"] = {"parts": [{"text": text}]}
        return request

    def embed(self, texts: list[str], purpose: str, timeout: float) -> list[list[float]]:
        url = f"{GENERATIVE_BASE}/{quote(self.embedding_model, safe='-._')}:batchEmbedContents"
        data = _post(url, {"requests": [self._embedding_request(text, purpose) for text in texts]}, self._headers(), timeout)
        vectors = [item.get("values") for item in data.get("embeddings") or []]
        if len(vectors) != len(texts) or not all(vectors):
            raise GatewayError("AI không trả về đủ vector.", "AI_EMPTY", True)
        return vectors


# Further providers register here and need no change elsewhere.
PROVIDERS: dict[str, type] = {"gemini": GeminiProvider}


def provider_name() -> str:
    return config.LLM_PROVIDER.strip().lower()


def is_available() -> bool:
    adapter = PROVIDERS.get(provider_name())
    return bool(adapter) and (bool(config.LLM_API_KEY.strip()) or not adapter.requires_key)


def default_model(name: str) -> str:
    adapter = PROVIDERS.get(name)
    return adapter.default_model if adapter else ""


def _provider():
    if not is_available():
        raise GatewayError("Chưa cấu hình dịch vụ AI.", "AI_NOT_CONFIGURED")
    adapter = PROVIDERS[provider_name()]
    return adapter(config.LLM_API_KEY.strip(), config.LLM_MODEL or adapter.default_model, config.AI_EMBEDDING_MODEL or adapter.default_embedding_model)


def embedding_model() -> str:
    adapter = PROVIDERS.get(provider_name())
    return (config.AI_EMBEDDING_MODEL or adapter.default_embedding_model) if adapter else ""


def trace(task: str, status: str, *, model: Optional[str] = None, user_id: Any = None, conversation_id: Optional[str] = None, error: Optional[str] = None,
          input_tokens: int = 0, output_tokens: int = 0, latency_ms: int = 0, attempts: int = 1, detail: Any = None, provider: Optional[str] = None) -> None:
    store.db.execute(
        """INSERT INTO ai_usage_traces(trace_id, user_id, conversation_id, task, provider, model, status, error, input_tokens, output_tokens, latency_ms, attempts, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), str(user_id) if user_id else None, conversation_id, task, provider or provider_name(), model, status, error, input_tokens, output_tokens, latency_ms,
         attempts, json.dumps(detail, ensure_ascii=False) if detail is not None else None, utcnow().isoformat()),
    )


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _with_retries(action, task: str, retries: Optional[int], deadline: Optional[float], model: str, user_id: Any, conversation_id: Optional[str]):
    limit = config.LLM_MAX_RETRIES if retries is None else retries
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        remaining = config.LLM_TIMEOUT_SECONDS if deadline is None else min(config.LLM_TIMEOUT_SECONDS, deadline - time.monotonic())
        try:
            if remaining <= 0:
                raise GatewayError("Yêu cầu AI đã quá thời gian cho phép.", "AI_TIMEOUT")
            return action(remaining), attempt, int((time.monotonic() - started) * 1000)
        except GatewayError as error:
            if error.retryable and attempt <= limit:
                _sleep(min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** (attempt - 1)))
                continue
            trace(task, "FAILED", model=model, user_id=user_id, conversation_id=conversation_id, error=error.code, attempts=attempt, latency_ms=int((time.monotonic() - started) * 1000))
            raise


def chat(request: ChatRequest, *, task: str, user_id: Any = None, conversation_id: Optional[str] = None, retries: Optional[int] = None, deadline: Optional[float] = None) -> ChatResult:
    provider = _provider()
    result, attempts, latency = _with_retries(lambda timeout: provider.chat(request, timeout), task, retries, deadline, provider.model, user_id, conversation_id)
    trace(task, "OK", model=result.model, user_id=user_id, conversation_id=conversation_id, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
          latency_ms=latency, attempts=attempts, detail={"tools": [call.name for call in result.tool_calls]} if result.tool_calls else None)
    return result


def check_schema(value: Any, schema: dict, path: str = "$") -> Optional[str]:
    """The part of JSON Schema we use. Returns the first problem, or None."""
    kind = schema.get("type")
    checks = {"object": dict, "array": list, "string": str, "boolean": bool}
    if kind in checks and not isinstance(value, checks[kind]):
        return f"{path} phải là {kind}"
    if kind in {"integer", "number"} and (isinstance(value, bool) or not isinstance(value, int if kind == "integer" else (int, float))):
        return f"{path} phải là {kind}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} ngoài danh sách cho phép"
    if kind == "string" and "maxLength" in schema and len(value) > schema["maxLength"]:
        return f"{path} quá dài"
    if kind == "array":
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{path} quá nhiều phần tử"
        for index, item in enumerate(value):
            problem = check_schema(item, schema.get("items", {}), f"{path}[{index}]")
            if problem:
                return problem
    if kind == "object":
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                return f"{path}.{name} bị thiếu"
        for name, item in value.items():
            if name not in properties:
                if schema.get("additionalProperties", True) is False:
                    return f"{path}.{name} không được phép"
                continue
            problem = check_schema(item, properties[name], f"{path}.{name}")
            if problem:
                return problem
    return None


def structured(system: str, payload: Any, schema: dict, *, task: str, user_id: Any = None, conversation_id: Optional[str] = None, retries: Optional[int] = None,
               deadline: Optional[float] = None, max_output_tokens: int = 1800, temperature: float = 0) -> dict:
    """JSON that matches ``schema``, or a GatewayError. Nothing unchecked reaches the caller."""
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    request = ChatRequest(system=system, messages=[Message("user", text)], json_schema=schema, max_output_tokens=max_output_tokens, temperature=temperature)
    result = chat(request, task=task, user_id=user_id, conversation_id=conversation_id, retries=retries, deadline=deadline)
    try:
        data = json.loads(result.text)
    except json.JSONDecodeError:
        trace(task, "REJECTED", model=result.model, user_id=user_id, conversation_id=conversation_id, error="AI_INVALID_JSON")
        raise GatewayError("AI trả về JSON không hợp lệ.", "AI_INVALID_JSON") from None
    problem = check_schema(data, schema)
    if problem:
        trace(task, "REJECTED", model=result.model, user_id=user_id, conversation_id=conversation_id, error="AI_INVALID_SCHEMA")
        raise GatewayError("AI trả về cấu trúc không hợp lệ.", "AI_INVALID_SCHEMA")
    return data


def embed(texts: list[str], *, purpose: str, task: str = "embedding", user_id: Any = None, retries: Optional[int] = None, deadline: Optional[float] = None) -> list[list[float]]:
    provider = _provider()
    vectors: list[list[float]] = []
    started = time.monotonic()
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        result, _, _ = _with_retries(lambda timeout: provider.embed(batch, purpose, timeout), task, retries, deadline, provider.embedding_model, user_id, None)
        vectors.extend(result)
    # The embedding endpoint reports no tokens, so the budget counts an estimate.
    trace(task, "OK", model=provider.embedding_model, user_id=user_id, input_tokens=sum(len(text) for text in texts) // 4, latency_ms=int((time.monotonic() - started) * 1000))
    return vectors
