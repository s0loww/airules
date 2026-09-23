"""Which endpoint and key a model goes to — no network, the client constructor is recorded.

The trap this pins: aggregators spell models `vendor/name`. `deepseek/deepseek-v4-flash` on
OpenRouter must go to OPENAI_BASE_URL with that key, not to DeepSeek's own endpoint with
DeepSeek's key, even though the name starts with "deepseek".
"""

import pytest

from app.config import Settings
from app.llm import LLM

ROUTER = "https://openrouter.ai/api/v1"


def _llm(**overrides):
    s = Settings(openai_api_key="or-key", openai_base_url=ROUTER,
                 deepseek_api_key="ds-key", **overrides)
    llm = LLM(s)
    made = []
    llm._make_client = lambda key, url: made.append((key, url)) or (key, url)
    return llm, made


@pytest.mark.parametrize("model, want", [
    ("deepseek-v4-flash", ("ds-key", "https://api.deepseek.com")),
    ("deepseek/deepseek-v4-flash", ("or-key", ROUTER)),
    ("openai/gpt-5-mini", ("or-key", ROUTER)),
    ("gpt-4o-mini", ("or-key", ROUTER)),
])
def test_chat_endpoint_by_name(model, want):
    llm, _ = _llm()
    assert llm._client_for(model) == want


def test_availability_follows_the_chat_endpoint():
    assert LLM(Settings(chat_model="deepseek/deepseek-v4-flash", openai_api_key="or",
                        deepseek_api_key="")).available
    assert not LLM(Settings(chat_model="deepseek-v4-flash", openai_api_key="or",
                            deepseek_api_key="")).available


def test_embeddings_through_the_router_by_default():
    llm, _ = _llm(embed_model="openai/text-embedding-3-small")
    assert llm.embed_client == ("or-key", ROUTER)


def test_explicit_embeddings_endpoint_wins():
    llm, _ = _llm(embed_base_url="https://emb.example/v1", embed_api_key="emb-key")
    assert llm.embed_client == ("emb-key", "https://emb.example/v1")


@pytest.mark.parametrize("model, cap", [
    ("deepseek/deepseek-v4-pro", {"max_tokens": 2048}),       # reasons, wherever served
    ("openai/gpt-5-mini", {"max_completion_tokens": 2048}),
    ("openai/gpt-4o-mini", {"max_tokens": 16}),
])
def test_classifier_cap_by_family_not_by_router(model, cap):
    llm, _ = _llm()
    assert llm._classifier_cap(model) == cap
