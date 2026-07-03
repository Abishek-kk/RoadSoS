from types import SimpleNamespace

import anyio
import httpx
import numpy as np

from app.ai import local_llm_client, rag_pipeline, retrieval
from app.routes import chat as chat_route


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


def test_chat_response_payload_includes_llm_provider():
    payload = chat_route.response_payload(
        reply="Use hazard lights.",
        intent="general",
        used_llm=True,
        llm_provider="ollama",
        lat=None,
        lng=None,
    )

    assert payload["used_llm"] is True
    assert payload["llm_provider"] == "ollama"


def test_chat_route_resolves_server_location_name(monkeypatch):
    captured = {}

    async def fake_reverse_geocode(lat, lng):
        captured["reverse_geocode_coords"] = (lat, lng)
        return "Madurai"

    def fake_run_rag_pipeline(*args, location_name=None, **kwargs):
        captured["location_name"] = location_name
        return SimpleNamespace(
            reply="You're near Madurai.",
            intent="general",
            used_llm=False,
            emergency=None,
        )

    monkeypatch.setattr(chat_route, "reverse_geocode", fake_reverse_geocode)
    monkeypatch.setattr(chat_route, "run_rag_pipeline", fake_run_rag_pipeline)

    payload = chat_route.ChatPayload(
        messages=[chat_route.ChatMessage(role="user", content="where am I")],
        lat=9.9252,
        lng=78.1198,
    )
    response = anyio.run(chat_route.chat, payload)

    assert response["reply"] == "You're near Madurai."
    assert captured["reverse_geocode_coords"] == (9.9252, 78.1198)
    assert captured["location_name"] == "Madurai"


def test_fallback_location_question_uses_location_name():
    reply = rag_pipeline.build_fallback_reply(
        "where am I",
        [],
        location_name="Madurai, Tamil Nadu",
    )

    assert "Madurai, Tamil Nadu" in reply


def test_live_context_location_question_answers_directly():
    result = rag_pipeline.run_rag_pipeline(
        "Where am I?",
        lat=9.9252,
        lng=78.1198,
        location_name="Madurai, Tamil Nadu, India",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        use_llm=False,
    )

    assert result.used_llm is False
    assert "Madurai, Tamil Nadu, India" in result.reply
    assert "9.92520" in result.reply


def test_live_context_time_question_uses_current_datetime():
    result = rag_pipeline.run_rag_pipeline(
        "what's today's date?",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        use_llm=False,
    )

    assert result.reply == "Today's date is Friday, July 03, 2026 at 10:30 AM IST."


def test_live_context_nearby_places_filter_by_category():
    result = rag_pipeline.run_rag_pipeline(
        "nearest hospital",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        nearby_places=[
            {
                "name": "Far Hospital",
                "category": "hospital",
                "distance_km": 3.4,
                "address": "Far Road",
            },
            {
                "name": "Central Police Station",
                "category": "police_station",
                "distance_km": 0.5,
                "address": "Station Road",
            },
            {
                "name": "Near Hospital",
                "category": "hospital",
                "distance_km": 1.2,
                "address": "Main Road",
            },
        ],
        use_llm=False,
    )

    assert result.reply.startswith("Nearest hospital:")
    assert "Near Hospital - 1.2 km, Main Road" in result.reply
    assert "Far Hospital" not in result.reply
    assert "Central Police Station" not in result.reply


def test_live_context_unsupported_nearby_category_does_not_fabricate():
    result = rag_pipeline.run_rag_pipeline(
        "ATMs nearby",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        nearby_places=[
            {
                "name": "Near Hospital",
                "category": "hospital",
                "distance_km": 1.2,
                "address": "Main Road",
            }
        ],
        use_llm=False,
    )

    assert "do not have any ATM entries" in result.reply


def test_live_context_emergency_surfaces_hospital_and_police_first():
    result = rag_pipeline.run_rag_pipeline(
        "I had an accident and someone is bleeding",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        nearby_places=[
            {
                "name": "Near Police Station",
                "category": "police_station",
                "distance_km": 1.8,
                "address": "Station Road",
            },
            {
                "name": "Near Hospital",
                "category": "hospital",
                "distance_km": 1.2,
                "address": "Main Road",
            },
        ],
        use_llm=False,
    )

    lines = result.reply.splitlines()
    assert lines[0] == "Nearest hospital: Near Hospital - 1.2 km, Main Road"
    assert lines[1] == "Nearest police station: Near Police Station - 1.8 km, Station Road"
    assert "call 112/108" in result.reply


def test_llm_context_includes_location_name_and_safety_snapshot():
    context = rag_pipeline.build_llm_context(
        "Road safety guidance.",
        location_name="Madurai",
        safety_snapshot="Nearest hospital: Apollo, 2.3 km away, phone 108.",
    )

    assert "User's approximate location: Madurai." in context
    assert "Always-available nearby safety info" in context
    assert "Nearest hospital: Apollo" in context
    assert "Retrieved context" in context


def test_llm_context_includes_structured_live_context():
    live_context = rag_pipeline.build_live_context(
        lat=1.0,
        lng=2.0,
        location_name="Madurai, Tamil Nadu, India",
        current_datetime="Friday, July 03, 2026 at 10:30 AM IST",
        nearby_places=[
            {
                "name": "Near Hospital",
                "category": "hospital",
                "distance_km": 1.2,
                "address": "Main Road",
            }
        ],
    )

    context = rag_pipeline.build_llm_context("Road safety guidance.", live_context=live_context)

    assert "LIVE CONTEXT" in context
    assert "Friday, July 03, 2026" in context
    assert '"category": "hospital"' in context
    assert "Retrieved context" in context


def test_nearby_safety_snapshot_formats_nearest_services(monkeypatch):
    datasets = {
        "hospitals.json": [{"id": "h1", "name": "Apollo Hospital", "lat": 0.01, "lng": 0.0, "phone": ""}],
        "police_stations.json": [{"id": "p1", "name": "Anna Nagar PS", "lat": 0.02, "lng": 0.0, "phone": ""}],
        "towing.json": [{"id": "t1", "name": "XYZ Recovery", "lat": 0.03, "lng": 0.0, "phone": ""}],
    }

    monkeypatch.setattr(retrieval, "load_json", lambda filename: datasets[filename])

    snapshot = retrieval.nearby_safety_snapshot(0.0, 0.0)

    assert "Nearest hospital: Apollo Hospital" in snapshot
    assert "phone 108" in snapshot
    assert "Nearest police station: Anna Nagar PS" in snapshot
    assert "phone 100" in snapshot
    assert "Nearest towing service: XYZ Recovery" in snapshot
    assert "phone 112" in snapshot


def test_semantic_retrieval_query_encoding_has_numpy_available(monkeypatch):
    class DummyEncoder:
        def encode(self, texts, normalize_embeddings):
            return np.array([[1.0, 0.0]], dtype="float32")

    class DummyIndex:
        ntotal = 1

        def search(self, query_embedding, k):
            return (
                np.array([[0.75]], dtype="float32"),
                np.array([[0]], dtype="int64"),
            )

    monkeypatch.setattr(retrieval, "init_embedding_index", lambda: None)
    monkeypatch.setattr(
        retrieval,
        "_chunks",
        [
            retrieval.ContextChunk(
                title="Emergency Guide",
                body="For a road accident, call 112 or 108 and move away from traffic if safe.",
            )
        ],
    )
    monkeypatch.setattr(retrieval, "_semantic_search_available", True)
    monkeypatch.setattr(retrieval, "_encoder", DummyEncoder())
    monkeypatch.setattr(retrieval, "_faiss_index", DummyIndex())

    chunks = retrieval.retrieve_context("What should I do after a road accident?", limit=1)

    assert chunks[0].title == "Emergency Guide"
