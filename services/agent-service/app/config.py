"""Runtime configuration, read from environment / .env.

All secrets (the OpenAI key, the bearer token) come from the environment so they never
live in the image or in source control. In Docker, docker-compose injects them from `.env`.
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

    # --- LLM provider (OpenAI by default; set base_url for Azure OpenAI or a proxy) ---
    openai_api_key: str = ""
    openai_base_url: str = ""  # blank = api.openai.com; set for Azure/proxy
    # DeepSeek (OpenAI-compatible) — used for CHAT only when chat_model starts with
    # "deepseek". Embeddings always stay on OpenAI. Put DEEPSEEK_API_KEY in .env yourself.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    chat_model: str = "gpt-4o-mini"
    # --- Two-tier model router (optional) ---
    # When MODEL_ROUTER_ENABLED is true AND chat_model_hard is set, a cheap pre-classifier
    # routes each turn: hard turns (multi-step reasoning, calculation, disambiguation,
    # cross-record comparison) go to chat_model_hard; everything else stays on chat_model.
    # Built for a deepseek-v4-flash (default) + deepseek-v4-pro (hard) hybrid: top-tier
    # quality on the hard minority, flash cost on the easy majority. Off by default — the
    # single chat_model path is unchanged. The classifier always runs on chat_model (cheap).
    model_router_enabled: bool = False
    chat_model_hard: str = ""
    # GPT-5 / o-series reasoning models only: minimal|low|medium|high. Ignored by
    # non-reasoning models (gpt-4o, gpt-4.1) and OpenAI-compatible providers (DeepSeek),
    # which take `temperature` instead. Override per run with REASONING_EFFORT.
    reasoning_effort: str = "medium"
    embed_model: str = "text-embedding-3-small"
    request_timeout: float = 90.0  # reasoning models can be slower per call

    # --- Retrieval ---
    # Defaults to the repo's help/ for local runs; the Docker image overrides with /app/help.
    help_dir: str = str(Path(__file__).resolve().parent.parent.parent / "help")
    retrieval: str = "embeddings"  # "embeddings" | "lexical"
    # The QA sweep (qa/) is green at 4; raising this means re-running the sweep first.
    top_k: int = 4

    # --- Agent skills (model-facing playbooks, injected when they match the question) ---
    skills_dir: str = str(Path(__file__).resolve().parent.parent.parent / "agent-skills")
    skills_top_k: int = 2

    # --- Service / behaviour ---
    # Shared secret; must equal the 1C constant TokenServicioAsistente. Blank disables auth.
    assistant_bearer_token: str = ""
    # Append a "Fuente: …" footer to answers (the Phase-1 1C UI does not render citations yet).
    append_sources_to_text: bool = True


def get_settings() -> Settings:
    return Settings()
