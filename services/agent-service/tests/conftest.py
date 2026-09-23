"""Keep the tests hermetic.

Settings read the service's `.env` and the process environment. On a machine where the
service is deployed that file names a tenant registry inside the container and a default
chat model -- a test run must not pick either up, or it tests the deployment instead of
the code. Found when the first local `.env` switched the whole suite into registry mode.
"""

import pytest

from app.config import Settings

Settings.model_config["env_file"] = None

_SERVICE_VARS = (
    "TENANTS_FILE", "CHAT_MODEL", "CHAT_MODEL_HARD", "MODEL_ROUTER_ENABLED", "RETRIEVAL",
    "TOP_K", "HELP_DIR", "SKILLS_DIR", "PROFILE", "ASSISTANT_BEARER_TOKEN",
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "DEEPSEEK_API_KEY", "EMBED_BASE_URL",
    "EMBED_API_KEY", "EMBED_MODEL", "APPEND_SOURCES_TO_TEXT",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in _SERVICE_VARS:
        monkeypatch.delenv(name, raising=False)
