"""A scripted model for AI tests. It records every request, so tests can read what left the server."""
from backend.ai_service import gateway
from backend.ai_service.gateway import ChatResult, GatewayError, ToolCall


class FakeProvider:
    name = "fake"
    requires_key = False
    default_model = "fake-model"
    default_embedding_model = "fake-embedding"
    script = []
    requests = []
    embed_error = None
    embed_calls = 0

    def __init__(self, api_key, model, embedding_model):
        self.model = model
        self.embedding_model = embedding_model

    def chat(self, request, timeout):
        FakeProvider.requests.append(request)
        step = FakeProvider.script.pop(0) if FakeProvider.script else "Xin chào [[CHAT]]"
        if isinstance(step, Exception):
            raise step
        if isinstance(step, list):
            return ChatResult(text="", tool_calls=step, model=self.model, input_tokens=100, output_tokens=20, raw={"role": "model", "parts": []})
        return ChatResult(text=step, tool_calls=[], model=self.model, input_tokens=100, output_tokens=20)

    def embed(self, texts, purpose, timeout):
        FakeProvider.embed_calls += 1
        if FakeProvider.embed_error:
            raise FakeProvider.embed_error
        return [[float("sql" in text.lower()), float("python" in text.lower()), 1.0] for text in texts]


def use_fake(monkeypatch, script=()):
    monkeypatch.setitem(gateway.PROVIDERS, "fake", FakeProvider)
    monkeypatch.setattr(gateway.config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(gateway, "_sleep", lambda seconds: None)
    FakeProvider.script = list(script)
    FakeProvider.requests = []
    FakeProvider.embed_error = None
    FakeProvider.embed_calls = 0
    return FakeProvider


def call(name, **arguments):
    return ToolCall(name, arguments, f"call-{name}")


def sent_text(provider=FakeProvider) -> str:
    """Everything the model was given across all recorded requests."""
    parts = []
    for request in provider.requests:
        parts.append(request.system)
        for message in request.messages:
            parts.append(message.text)
            parts.extend(str(result["data"]) for result in message.tool_results)
    return "\n".join(parts)


__all__ = ["FakeProvider", "GatewayError", "call", "sent_text", "use_fake"]
