import httpx

from app.ai import local_llm_client, rag_pipeline


def test_ollama_client_builds_chat_payload(monkeypatch):
    captured = {}

    class DummyResponse:
        text = '{"message":{"content":"Use hazard lights."}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "Use hazard lights."}}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(local_llm_client, "get_ollama_base_url", lambda: "http://ollama.test/")
    monkeypatch.setattr(local_llm_client, "get_ollama_model", lambda: "llama3.1:8b")
    monkeypatch.setattr(local_llm_client.httpx, "post", fake_post)

    reply = local_llm_client.generate_chat_response(
        prompt="What should I do?",
        context="Crash safety guidance",
        system_instruction="You are RoadSoS AI.",
    )

    assert reply == "Use hazard lights."
    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["timeout"] == local_llm_client.REQUEST_TIMEOUT_SECONDS
    assert captured["json"]["model"] == "llama3.1:8b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"][0] == {"role": "system", "content": "You are RoadSoS AI."}
    assert captured["json"]["messages"][1]["role"] == "user"
    assert "Context/Knowledge Base Reference" in captured["json"]["messages"][1]["content"]
    assert "User Question: What should I do?" in captured["json"]["messages"][1]["content"]


def test_ollama_client_returns_error_on_connection_failure(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(local_llm_client, "get_ollama_base_url", lambda: "http://ollama.test")
    monkeypatch.setattr(local_llm_client, "get_ollama_model", lambda: "llama3.1:8b")
    monkeypatch.setattr(local_llm_client.httpx, "post", fake_post)

    reply = local_llm_client.generate_chat_response("Help")

    assert reply.startswith("Error:")


def test_rag_pipeline_selects_ollama_without_gemini_key(monkeypatch):
    monkeypatch.setattr(rag_pipeline, "get_llm_provider", lambda: "ollama")
    monkeypatch.setattr(rag_pipeline, "get_gemini_api_key", lambda: "")

    assert rag_pipeline.get_llm_client() is rag_pipeline.local_llm_client
    assert rag_pipeline.should_attempt_llm() is True


def test_rag_pipeline_keeps_gemini_key_gate(monkeypatch):
    monkeypatch.setattr(rag_pipeline, "get_llm_provider", lambda: "gemini")
    monkeypatch.setattr(rag_pipeline, "get_gemini_api_key", lambda: "")

    assert rag_pipeline.get_llm_client() is rag_pipeline.gemini_client
    assert rag_pipeline.should_attempt_llm() is False
