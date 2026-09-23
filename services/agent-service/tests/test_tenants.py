"""Several 1C bases behind one service: the token picks the tenant, and nothing leaks across.

Two fixed tenants: `ec` (the product the service was built for, with its profile) and `ru`
(a generic tenant — no profile, one Russian topic without language markers).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tenants import load_registry

FIX = Path(__file__).resolve().parent / "fixtures"


class FakeLLM:
    available = True

    def __init__(self, settings=None, profile=None):
        self.settings, self.profile = settings, profile

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def answer_message(self, system, history, context_block):
        # always claims the ec topic: a tenant that does not have it must drop the citation
        self.last_system, self.last_context = system, context_block
        return {"text": "ok", "used_topics": ["compras/orden-de-compra", "sklad/postuplenie"]}

    def answer_with_tools(self, system, history, context_block, tools):
        return {"type": "message", "text": "ok"}

    def classify_new_topic(self, history):
        return False


def _registry(tmp_path, monkeypatch, extra=""):
    monkeypatch.setenv("EC_TOKEN", "tok-ec")
    monkeypatch.setenv("RU_TOKEN", "tok-ru")
    path = tmp_path / "tenants.yaml"
    path.write_text(f"""
tenants:
  ec:
    token_env: EC_TOKEN
    help_dir: {FIX / 'tenant_ec' / 'help'}
    skills_dir: {FIX / 'tenant_ec' / 'agent-skills'}
    profile: {FIX / 'tenant_ec' / 'assistant-profile.md'}
    settings:
      chat_model: deepseek-v4-flash
  ru:
    token_env: RU_TOKEN
    help_dir: {FIX / 'tenant_ru' / 'help'}
{extra}""", encoding="utf-8")
    return Settings(tenants_file=str(path), retrieval="lexical", openai_api_key="",
                    append_sources_to_text=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = _registry(tmp_path, monkeypatch)
    tenants = load_registry(settings)
    for t in tenants:
        t.llm = FakeLLM(t.settings, t.profile)
    with TestClient(create_app(settings=settings, tenants=tenants)) as c:
        yield c, {t.name: t for t in tenants}


def _turn(text, lang):
    return {"context": {"lang": lang}, "messages": [{"role": "user", "content": text}],
            "tools": []}


def test_token_picks_the_tenant(client):
    c, _ = client
    ec = c.post("/agent/turn", json=_turn("", "es"), headers={"Authorization": "Bearer tok-ec"})
    ru = c.post("/agent/turn", json=_turn("", "ru"), headers={"Authorization": "Bearer tok-ru"})
    assert ec.json()["text"].startswith("¿En qué puedo ayudarle")
    assert ru.json()["text"].startswith("Чем помочь")


def test_unknown_or_missing_token_is_refused(client):
    c, _ = client
    assert c.post("/agent/turn", json=_turn("x", "es"),
                  headers={"Authorization": "Bearer nope"}).status_code == 401
    # several tenants: there is no open default to fall back to
    assert c.post("/agent/turn", json=_turn("x", "es")).status_code == 401


def test_knowledge_bases_do_not_leak(client):
    c, tenants = client
    r = c.post("/agent/turn", json=_turn("как оприходовать товар на склад", "ru"),
               headers={"Authorization": "Bearer tok-ru"})
    assert r.json()["citations"] == ["sklad/postuplenie"]
    assert "orden-de-compra" not in tenants["ru"].llm.last_context
    r = c.post("/agent/turn", json=_turn("¿cómo registro una orden de compra?", "es"),
               headers={"Authorization": "Bearer tok-ec"})
    assert r.json()["citations"] == ["compras/orden-de-compra"]


def test_each_tenant_speaks_its_profile(client):
    c, tenants = client
    c.post("/agent/turn", json=_turn("¿cómo registro una compra?", "es"),
           headers={"Authorization": "Bearer tok-ec"})
    c.post("/agent/turn", json=_turn("как провести поступление", "ru"),
           headers={"Authorization": "Bearer tok-ru"})
    assert "Contabilidad" in tenants["ec"].llm.last_system
    assert "Contabilidad" not in tenants["ru"].llm.last_system
    assert "Reply in Russian" in tenants["ru"].llm.last_system


def test_a_body_without_markers_is_in_the_primary_language(client):
    _, tenants = client
    assert {ch.lang for ch in tenants["ru"].chunks} == {"ru"}


def test_per_tenant_settings_apply(client):
    _, tenants = client
    assert tenants["ec"].settings.chat_model == "deepseek-v4-flash"
    assert tenants["ru"].settings.chat_model == Settings().chat_model


def test_health_lists_tenants_and_reload_is_scoped(client):
    c, tenants = client
    body = c.get("/health").json()
    assert set(body["tenants"]) == {"ec", "ru"}
    assert body["tenants"]["ec"]["product"] == "Contabilidad"
    assert body["tenants"]["ec"]["retrieval"] == "lexical"
    r = c.post("/reload", headers={"Authorization": "Bearer tok-ru"})
    assert r.json()["tenant"] == "ru"
    assert c.post("/reload").status_code == 401


def test_registry_refuses_a_tenant_without_token(tmp_path, monkeypatch):
    settings = _registry(tmp_path, monkeypatch, extra=f"""  open:
    help_dir: {FIX / 'tenant_ru' / 'help'}
""")
    with pytest.raises(ValueError, match="no token"):
        load_registry(settings)


def test_registry_refuses_shared_tokens(tmp_path, monkeypatch):
    settings = _registry(tmp_path, monkeypatch, extra=f"""  twin:
    token_env: RU_TOKEN
    help_dir: {FIX / 'tenant_ru' / 'help'}
""")
    with pytest.raises(ValueError, match="share a token"):
        load_registry(settings)


def test_registry_refuses_secrets_in_overrides(tmp_path, monkeypatch):
    settings = _registry(tmp_path, monkeypatch, extra=f"""  keyed:
    token_env: EC_TOKEN_2
    help_dir: {FIX / 'tenant_ru' / 'help'}
    settings:
      openai_api_key: sk-nope
""")
    monkeypatch.setenv("EC_TOKEN_2", "tok-2")
    with pytest.raises(ValueError, match="not overridable"):
        load_registry(settings)
