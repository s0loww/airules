"""Runtime configuration, read from environment / .env.

All secrets (provider keys, bearer tokens) come from the environment so they never live in the
image or in source control. In Docker, docker-compose injects them from `.env`.

Two ways to run:
- **Several tenants** (the host service): `TENANTS_FILE` points at a YAML registry; each tenant
  is one 1C base with its own knowledge base, playbooks, profile and bearer token
  (`app/tenants.py`).
- **One tenant** (legacy / a project running its own copy): no `TENANTS_FILE`; `HELP_DIR`,
  `SKILLS_DIR`, `PROFILE` and `ASSISTANT_BEARER_TOKEN` describe the only tenant.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to agent-service/.env so the key is found regardless of the process CWD
# (uvicorn launched from anywhere, in-process tests, etc.). In Docker this path does not exist
# and is simply ignored — compose injects the values as real environment variables instead.
_ENV_FILE = str(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # --- Tenancy ---
    # YAML registry of tenants. Blank = single-tenant mode from the fields below.
    tenants_file: str = ""

    # --- LLM provider (OpenAI by default; set base_url for Azure OpenAI or a proxy) ---
    openai_api_key: str = ""
    openai_base_url: str = ""  # blank = api.openai.com; set for Azure/proxy
    # DeepSeek (OpenAI-compatible) — used for CHAT only when chat_model starts with
    # "deepseek". Put DEEPSEEK_API_KEY in .env yourself.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    chat_model: str = "gpt-4o-mini"
    # --- Two-tier model router (optional) ---
    # When MODEL_ROUTER_ENABLED is true AND chat_model_hard is set, a cheap pre-classifier
    # routes each turn: hard turns (multi-step reasoning, calculation, disambiguation,
    # cross-record comparison) go to chat_model_hard; everything else stays on chat_model.
    # Built for a deepseek-v4-flash (default) + deepseek-v4-pro (hard) hybrid. Off by default.
    model_router_enabled: bool = False
    chat_model_hard: str = ""
    # GPT-5 / o-series reasoning models only: minimal|low|medium|high. Ignored by
    # non-reasoning models and OpenAI-compatible providers (DeepSeek).
    reasoning_effort: str = "medium"
    request_timeout: float = 90.0  # reasoning models can be slower per call

    # --- Embeddings ---
    # Any OpenAI-compatible embeddings endpoint. Blank base URL and key = the OpenAI key above.
    # DeepSeek has no embeddings API: with a DeepSeek-only setup either point these at an
    # embeddings server or run RETRIEVAL=lexical.
    embed_model: str = "text-embedding-3-small"
    embed_base_url: str = ""
    embed_api_key: str = ""

    # --- Retrieval ---
    help_dir: str = str(Path(__file__).resolve().parent.parent.parent / "help")
    retrieval: str = "embeddings"  # "embeddings" | "lexical"
    # A tenant's QA sweep is calibrated at a given value; raising it means re-running it.
    top_k: int = 4

    # --- Agent skills (model-facing playbooks, injected when they match the question) ---
    skills_dir: str = str(Path(__file__).resolve().parent.parent.parent / "agent-skills")
    skills_top_k: int = 2

    # --- Profile: product, languages, prompt sections (app/prompt.py). Blank = generic. ---
    profile: str = ""

    # --- Service / behaviour ---
    # Shared secret; must equal the 1C constant TokenServicioAsistente. Blank disables auth
    # (single-tenant mode only).
    assistant_bearer_token: str = ""
    # Append a "Source: …" footer to answers (for clients that do not render citations).
    append_sources_to_text: bool = True

    @property
    def embed_available(self) -> bool:
        return bool(self.embed_api_key or self.openai_api_key)


def get_settings() -> Settings:
    return Settings()
