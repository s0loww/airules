"""Contract tests for POST /agent/turn — offline (mocked LLM, lexical retrieval).

These assert wire-compatibility with the 1C client (CommonModule.AsistenteIAServer): the exact
request shape it sends and the response shape it parses, plus bearer auth. No API key or
network needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

HELP_DIR = str(Path(__file__).resolve().parents[2] / "help")


class FakeLLM:
    """Deterministic stand-in for the OpenAI-backed LLM."""

    available = True

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def answer_message(self, system, history, context_block):
        return {"text": "Respuesta de prueba.", "used_topics": ["compras/orden-de-compra"]}

    def answer_with_tools(self, system, history, context_block, tools):
        t = tools[0]
        return {"type": "tool_calls", "calls": [{"id": "c1", "name": t.name, "arguments": {"q": "x"}}]}

    def classify_new_topic(self, history):
        return False


def _settings(**overrides) -> Settings:
    base = dict(
        retrieval="lexical",
        help_dir=HELP_DIR,
        assistant_bearer_token="secret",
        append_sources_to_text=False,
        openai_api_key="",
    )
    base.update(overrides)
    return Settings(**base)


def _client(**overrides) -> TestClient:
    return TestClient(create_app(settings=_settings(**overrides), llm=FakeLLM()))


AUTH = {"Authorization": "Bearer secret"}
TURN = {
    "context": {"lang": "es", "user": "tester"},
    "messages": [{"role": "user", "content": "¿cómo registro una compra?"}],
    "tools": [],
}


def test_health_reports_indexed_chunks():
    with _client() as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["chunks"] >= 8  # 4 topics x 2 languages
        assert body["skills"] >= 2  # data-map + document-search


def test_load_skills_parses_frontmatter():
    from pathlib import Path

    from app.kb import load_skills

    skills = load_skills(str(Path(__file__).resolve().parents[2] / "agent-skills"))
    by_name = {s.topic_id: s for s in skills}
    assert "data-map" in by_name and "document-search" in by_name
    data_map = by_name["data-map"]
    assert "iva0" in data_map.tags  # triggers boost retrieval for the misspellable forms
    assert "NEVER" in data_map.text  # the honesty protocol is the point of this skill
    assert data_map.title  # description doubles as the catalog line


def test_skills_injected_for_tax_question_in_tools_mode():
    class CapturingLLM(FakeLLM):
        def __init__(self):
            self.last_system = ""

        def answer_with_tools(self, system, history, context_block, tools):
            self.last_system = system
            return {"type": "message", "text": "ok", "used_topics": []}

        def answer_message(self, system, history, context_block):
            self.last_system = system
            return {"text": "ok", "used_topics": []}

    payload = {
        "context": {"lang": "es", "user": "tester"},
        "messages": [{"role": "user", "content": "hay compras con IVA 0?"}],
        "tools": [{"name": "find_documents", "description": "Busca", "risk": "read"}],
    }
    cap = CapturingLLM()
    app = create_app(settings=_settings(), llm=cap)
    with TestClient(app) as client:
        r = client.post("/agent/turn", json=payload, headers=AUTH)
        assert r.status_code == 200
    # The catalog names every playbook; the matching ones are injected as instructions.
    assert "TASK PLAYBOOKS" in cap.last_system
    assert "data-map" in cap.last_system
    assert "PLAYBOOK INSTRUCTIONS" in cap.last_system
    assert "NEVER" in cap.last_system  # the honesty protocol reached the model

    # Help-only mode (no tools) stays lean: no playbook plumbing.
    help_payload = dict(payload)
    help_payload["tools"] = []
    cap2 = CapturingLLM()
    app2 = create_app(settings=_settings(), llm=cap2)
    with TestClient(app2) as client:
        r = client.post("/agent/turn", json=help_payload, headers=AUTH)
        assert r.status_code == 200
    assert "TASK PLAYBOOKS" not in cap2.last_system


def test_turn_message_shape_matches_1c_contract():
    with _client() as client:
        r = client.post("/agent/turn", json=TURN, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "message"
        assert isinstance(body["text"], str) and body["text"]
        assert isinstance(body["citations"], list)
        assert all(isinstance(c, str) for c in body["citations"])
        assert body["citations"] == ["compras/orden-de-compra"]


def test_turn_message_defaults_new_topic_false():
    with _client() as client:
        r = client.post("/agent/turn", json=TURN, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["new_topic"] is False


def test_turn_message_propagates_new_topic_true():
    # The dedicated classifier decides a new topic; it only runs when there's a prior exchange.
    class TopicLLM(FakeLLM):
        def classify_new_topic(self, history):
            return True

    payload = {
        "context": {"lang": "es", "user": "tester"},
        "messages": [
            {"role": "user", "content": "¿cómo registro una compra?"},
            {"role": "assistant", "content": "Usa el documento Compra."},
            {"role": "user", "content": "¿cómo hago el cierre de mes?"},
        ],
        "tools": [],
    }
    app = create_app(settings=_settings(), llm=TopicLLM())
    with TestClient(app) as client:
        r = client.post("/agent/turn", json=payload, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "message"
        assert body["new_topic"] is True


def test_turn_tolerates_extra_context_keys():
    payload = dict(TURN)
    payload["context"] = {"lang": "en", "user": "tester", "empresa": "ACME"}
    with _client() as client:
        r = client.post("/agent/turn", json=payload, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["type"] == "message"


def test_turn_with_tools_returns_tool_calls():
    payload = dict(TURN)
    payload["tools"] = [{"name": "find_documents", "description": "Busca", "risk": "read"}]
    with _client() as client:
        r = client.post("/agent/turn", json=payload, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "tool_calls"
        assert body["calls"][0]["name"] == "find_documents"
        assert isinstance(body["calls"][0]["arguments"], dict)


def test_auth_required_when_token_set():
    with _client() as client:
        assert client.post("/agent/turn", json=TURN).status_code == 401
        assert client.post(
            "/agent/turn", json=TURN, headers={"Authorization": "Bearer wrong"}
        ).status_code == 401


def test_auth_open_when_token_blank():
    with _client(assistant_bearer_token="") as client:
        r = client.post("/agent/turn", json=TURN)
        assert r.status_code == 200


def test_not_configured_message_when_no_key():
    class NoKeyLLM(FakeLLM):
        available = False

    app = create_app(settings=_settings(), llm=NoKeyLLM())
    with TestClient(app) as client:
        r = client.post("/agent/turn", json=TURN, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "message"
        assert "administrador" in body["text"].lower()


def test_system_prompt_includes_today_when_provided():
    from app.prompt import build_system_prompt

    with_today = build_system_prompt("es", with_tools=True, today="2026-06-08")
    assert "2026-06-08" in with_today
    without = build_system_prompt("es", with_tools=True)
    assert "2026-06-08" not in without


def test_tool_prompt_is_generic_not_per_tool():
    from app.prompt import build_system_prompt

    with_tools = build_system_prompt("es", with_tools=True)
    # Teaches the generic result statuses every tool reports through...
    assert "ambiguous_counterparty" in with_tools
    assert "counterparty_code" in with_tools
    assert "declined_by_user" in with_tools
    # Identifiers shown to the model/user are catalog codes — never UUIDs.
    assert "counterparty_id" not in with_tools
    # The accounting arithmetic mandate: the model never computes numbers itself.
    assert "NEVER compute numbers yourself" in with_tools
    assert "sum_total" in with_tools
    # ...but no per-tool routing: that guidance lives in the tool descriptions 1C sends,
    # so registering a new tool in 1C never requires a service prompt edit.
    assert "find_unpaid_purchases" not in with_tools
    assert "financial_snapshot" not in with_tools

    # Help-only mode stays lean: no tool mechanics leak in.
    help_only = build_system_prompt("es", with_tools=False)
    assert "ambiguous_counterparty" not in help_only


def test_to_openai_messages_converts_tool_plumbing():
    from app.llm import to_openai_messages

    wire = [
        {"role": "user", "content": "compras de mayo", "tool_calls": [], "tool_call_id": ""},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "find_documents", "arguments": {"limit": 5}}],
            "tool_call_id": "",
        },
        {"role": "tool", "content": '{"status":"ok"}', "tool_calls": [], "tool_call_id": "c1"},
    ]
    native = to_openai_messages(wire)

    assert native[0] == {"role": "user", "content": "compras de mayo"}
    assistant = native[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] is None  # empty content must become None for the API
    fn = assistant["tool_calls"][0]
    assert fn["id"] == "c1" and fn["type"] == "function"
    assert fn["function"]["name"] == "find_documents"
    assert fn["function"]["arguments"] == '{"limit": 5}'  # dict -> JSON string
    assert native[2] == {"role": "tool", "tool_call_id": "c1", "content": '{"status":"ok"}'}


RESUME_TURN = {
    "context": {"lang": "es", "user": "tester"},
    "messages": [
        {"role": "user", "content": "compras de kywi"},
        {"role": "user", "content": "ahora las de mayo"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "find_documents", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"status":"ok","total":0,"items":[]}'},
    ],
    "tools": [{"name": "find_documents", "description": "Busca", "risk": "read"}],
}


def test_resume_post_skips_topic_classification():
    class SpyLLM(FakeLLM):
        def __init__(self):
            self.classified = False

        def classify_new_topic(self, history):
            self.classified = True
            return True

        def answer_with_tools(self, system, history, context_block, tools):
            return {"type": "message", "text": "listo", "used_topics": []}

    spy = SpyLLM()
    app = create_app(settings=_settings(), llm=spy)
    with TestClient(app) as client:
        r = client.post("/agent/turn", json=RESUME_TURN, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "message"
        assert body["new_topic"] is False
    assert spy.classified is False  # a resume POST must never re-classify (nor trim) history


def test_router_disabled_returns_default_without_classifying():
    from app.llm import LLM

    llm = LLM(_settings(chat_model="deepseek-v4-flash", chat_model_hard="deepseek-v4-pro",
                        model_router_enabled=False, deepseek_api_key="x"))

    def boom(history):
        raise AssertionError("classifier must not run when the router is disabled")

    llm.classify_hard = boom  # the default single-model path must pay no classifier call
    assert llm.routed_model([{"role": "user", "content": "hola"}]) == "deepseek-v4-flash"


def test_router_picks_hard_model_for_hard_turn_and_light_otherwise():
    from app.llm import LLM

    llm = LLM(_settings(chat_model="deepseek-v4-flash", chat_model_hard="deepseek-v4-pro",
                        model_router_enabled=True, deepseek_api_key="x"))
    llm.classify_hard = lambda history: True
    assert llm.routed_model([{"role": "user", "content": "x"}]) == "deepseek-v4-pro"
    llm.classify_hard = lambda history: False
    assert llm.routed_model([{"role": "user", "content": "x"}]) == "deepseek-v4-flash"


def test_router_without_hard_model_stays_on_default():
    from app.llm import LLM

    llm = LLM(_settings(chat_model="deepseek-v4-flash", chat_model_hard="",
                        model_router_enabled=True, deepseek_api_key="x"))
    llm.classify_hard = lambda history: True  # irrelevant: no hard model configured
    assert llm.routed_model([{"role": "user", "content": "x"}]) == "deepseek-v4-flash"


def test_router_favours_strong_model_when_classifier_fails():
    from app.llm import LLM

    llm = LLM(_settings(chat_model="deepseek-v4-flash", chat_model_hard="deepseek-v4-pro",
                        model_router_enabled=True, deepseek_api_key="x"))

    def boom(history):
        raise RuntimeError("classifier down")

    llm.classify_hard = boom
    assert llm.routed_model([{"role": "user", "content": "x"}]) == "deepseek-v4-pro"


def test_tool_calls_response_carries_new_topic():
    class TopicLLM(FakeLLM):
        def classify_new_topic(self, history):
            return True

    payload = {
        "context": {"lang": "es", "user": "tester"},
        "messages": [
            {"role": "user", "content": "¿cómo registro una compra?"},
            {"role": "assistant", "content": "Usa el documento Compra."},
            {"role": "user", "content": "muéstrame los pedidos de cliente"},
        ],
        "tools": [{"name": "find_documents", "description": "Busca", "risk": "read"}],
    }
    app = create_app(settings=_settings(), llm=TopicLLM())
    with TestClient(app) as client:
        r = client.post("/agent/turn", json=payload, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "tool_calls"
        assert body["new_topic"] is True
