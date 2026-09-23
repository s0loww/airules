"""LLM client — provider-agnostic seam, OpenAI implementation.

Switching to Azure OpenAI or a proxy is a config change only (set OPENAI_BASE_URL and the
model/deployment names); the rest of the service is unchanged.

Two call shapes:
  - answer_message(...)   : help-only. Forces a JSON reply {"text", "used_topics"}.
  - answer_with_tools(...): tool calling. Returns either a message or tool_calls.

History arrives in the wire shape (see schemas.py): plain user/assistant text plus, for an
in-flight agent turn, assistant tool_calls echoes and "tool" result messages. to_openai_messages
converts that into the provider-native format (arguments dict -> JSON string).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .config import Settings


def _is_openai_reasoning(model: str) -> bool:
    """OpenAI reasoning models (GPT-5 family, o-series). They take `reasoning_effort`,
    reject `temperature` other than the default, and cap output with
    `max_completion_tokens` (not `max_tokens`). Non-reasoning OpenAI models and
    OpenAI-compatible providers (e.g. DeepSeek) keep the classic params instead."""
    m = (model or "").lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _is_deepseek(model: str) -> bool:
    """DeepSeek (OpenAI-compatible) chat models route to the DeepSeek endpoint/key."""
    return (model or "").lower().startswith("deepseek")


def to_openai_messages(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert wire-shaped history into OpenAI chat messages.

    - {"role": "tool", "tool_call_id", "content"} passes through as a tool message.
    - An assistant message with tool_calls becomes the native shape (function + JSON-string
      arguments); empty content becomes None, as the API expects.
    - Anything else is a plain {role, content} message.
    """
    converted: List[Dict[str, Any]] = []
    for m in history:
        role = m.get("role", "user")
        if role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": m.get("content", "") or "",
                }
            )
            continue
        tool_calls = m.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(
                                    tc.get("arguments") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            continue
        converted.append({"role": role, "content": m.get("content", "")})
    return converted


def text_only(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The user/assistant text exchanges of a history — tool plumbing stripped.

    Used by the topic classifier, which reasons about what the user is talking about and
    must not be distracted by tool-call JSON.
    """
    return [
        {"role": m.get("role", ""), "content": m.get("content", "")}
        for m in history
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]


class LLM:
    def __init__(self, settings: Settings, profile=None) -> None:
        self.settings = settings
        # The tenant's profile supplies the classifier prompts (they name the product's
        # domain); None = the generic template.
        self.profile = profile
        self._openai_client = None
        self._deepseek_client = None
        self._embed_client = None

    @property
    def _chat_is_deepseek(self) -> bool:
        return _is_deepseek(self.settings.chat_model)

    @property
    def available(self) -> bool:
        # The default CHAT provider's key gates availability (embeddings always need OpenAI).
        # The two-tier router keeps both tiers on the same provider (flash+pro = DeepSeek), so
        # this single check covers them; a mixed-provider router would also need the other key.
        if self._chat_is_deepseek:
            return bool(self.settings.deepseek_api_key)
        return bool(self.settings.openai_api_key)

    def _make_client(self, api_key: str, base_url: str):
        from openai import OpenAI

        kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": self.settings.request_timeout}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    def _client_for(self, model: str):
        """Provider-aware, cached per provider: the DeepSeek endpoint for deepseek-* chat
        models, OpenAI for everything else (including all embeddings)."""
        if _is_deepseek(model):
            if self._deepseek_client is None:
                self._deepseek_client = self._make_client(
                    self.settings.deepseek_api_key, self.settings.deepseek_base_url)
            return self._deepseek_client
        if self._openai_client is None:
            self._openai_client = self._make_client(
                self.settings.openai_api_key, self.settings.openai_base_url)
        return self._openai_client

    @property
    def embed_available(self) -> bool:
        return self.settings.embed_available

    @property
    def embed_client(self):
        # Index and query vectors must come from the same provider and model to be
        # comparable, so embeddings have one client of their own: an explicit
        # OpenAI-compatible endpoint when configured, the OpenAI key otherwise --
        # never the chat provider by accident.
        if self.settings.embed_base_url or self.settings.embed_api_key:
            if self._embed_client is None:
                self._embed_client = self._make_client(
                    self.settings.embed_api_key or self.settings.openai_api_key,
                    self.settings.embed_base_url)
            return self._embed_client
        return self._client_for(self.settings.embed_model)

    def _chat_kwargs(self, model: str, *, classifier: bool = False,
                     with_tools: bool = False) -> Dict[str, Any]:
        """Per-model-family create() params: reasoning models get `reasoning_effort` and no
        `temperature`; everything else keeps `temperature`. The classifier is a cheap
        routing call, so it runs at minimal effort / temperature 0.

        Note: on /v1/chat/completions OpenAI rejects `reasoning_effort` together with
        function tools ("use /v1/responses instead"), so we omit it on the tools path and
        let the model use its default effort there. A future Responses-API migration would
        restore effort control on tool calls."""
        kwargs: Dict[str, Any] = {"model": model}
        if _is_openai_reasoning(model):
            if not with_tools:
                kwargs["reasoning_effort"] = "minimal" if classifier else self.settings.reasoning_effort
        else:
            kwargs["temperature"] = 0.0 if classifier else 0.2
        return kwargs

    def _classifier_cap(self, model: str) -> Dict[str, Any]:
        """Output-token budget for a short-JSON classifier call. Models that reason internally
        (OpenAI gpt-5/o-series AND DeepSeek V4) emit hidden reasoning before the visible JSON,
        so a tight cap returns EMPTY content (finish_reason=length). Give them room — they stop
        as soon as the short JSON is produced, so a high cap costs nothing extra. Plain models
        (gpt-4o, gpt-4.1) need only a few tokens."""
        if _is_openai_reasoning(model):
            return {"max_completion_tokens": 2048}
        if _is_deepseek(model):
            return {"max_tokens": 2048}
        return {"max_tokens": 16}

    def routed_model(self, history: List[Dict[str, Any]]) -> str:
        """Two-tier router: chat_model_hard for hard turns, else chat_model. Disabled
        (returns chat_model with no extra call) unless model_router_enabled AND a hard model
        are set — so the default single-model path pays nothing."""
        if not (self.settings.model_router_enabled and self.settings.chat_model_hard):
            return self.settings.chat_model
        try:
            hard = self.classify_hard(history)
        except Exception:
            # Classifier failed (rare — it runs on the cheap model): favour quality and send
            # the turn to the stronger model rather than risk a hard miss on the cheap one.
            return self.settings.chat_model_hard
        return self.settings.chat_model_hard if hard else self.settings.chat_model

    def classify_hard(self, history: List[Dict[str, Any]]) -> bool:
        """Cheap pre-classifier (runs on the light chat_model): is the latest user turn HARD
        enough to deserve the strong model? Looks only at the user/assistant text, never the
        tool plumbing, so the verdict is stable across the sub-turns of one agent loop."""
        from .prompt import difficulty_classifier

        exchanges = text_only(history)
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in exchanges[-6:])
        model = self.settings.chat_model
        kwargs = self._chat_kwargs(model, classifier=True)
        kwargs.update(self._classifier_cap(model))
        resp = self._client_for(model).chat.completions.create(
            messages=[
                {"role": "system", "content": difficulty_classifier(self.profile)},
                {"role": "user",
                 "content": f"Conversación:\n{convo}\n\n¿La ÚLTIMA pregunta del usuario es DIFÍCIL?"},
            ],
            response_format={"type": "json_object"},
            **kwargs,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return bool(json.loads(content).get("hard", False))
        except (json.JSONDecodeError, TypeError):
            return False

    # --- embeddings (for EmbeddingRetriever) ---
    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self.embed_client.embeddings.create(model=self.settings.embed_model, input=texts)
        return [d.embedding for d in resp.data]

    # --- help-only: grounded answer as strict JSON ---
    def answer_message(
        self, system: str, history: List[Dict[str, Any]], context_block: str
    ) -> Dict[str, Any]:
        messages = [{"role": "system", "content": system}]
        if context_block:
            messages.append({"role": "system", "content": context_block})
        messages.extend(to_openai_messages(history))
        model = self.routed_model(history)
        resp = self._client_for(model).chat.completions.create(
            messages=messages,
            response_format={"type": "json_object"},
            **self._chat_kwargs(model),
        )
        content = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"text": content.strip(), "used_topics": []}
        used = data.get("used_topics") or []
        if not isinstance(used, list):
            used = []
        return {"text": str(data.get("text", "")).strip(), "used_topics": [str(u) for u in used]}

    # --- Topic-change router: a focused, cheap call (no answer, no retrieved docs) that decides
    # whether the LAST user message continues the chat or starts a new one. Returns True for a new
    # topic. The conversation is passed as plain text so the model reasons about it as data. ---
    def classify_new_topic(self, history: List[Dict[str, Any]]) -> bool:
        from .prompt import topic_classifier

        exchanges = text_only(history)
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in exchanges[-8:])
        model = self.settings.chat_model  # topic routing always runs on the light/default model
        kwargs = self._chat_kwargs(model, classifier=True)
        kwargs.update(self._classifier_cap(model))
        resp = self._client_for(model).chat.completions.create(
            messages=[
                {"role": "system", "content": topic_classifier(self.profile)},
                {"role": "user", "content": f"Conversation:\n{convo}\n\nDoes the LAST user message start a new topic?"},
            ],
            response_format={"type": "json_object"},
            **kwargs,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return bool(json.loads(content).get("new_topic", False))
        except (json.JSONDecodeError, TypeError):
            return False

    # --- tool calling (one round trip of the 1C-driven agent loop) ---
    def answer_with_tools(
        self,
        system: str,
        history: List[Dict[str, Any]],
        context_block: str,
        tools: List[Any],
    ) -> Dict[str, Any]:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    # Use the schema the 1C client sent; fall back to a free-form object.
                    "parameters": t.parameters or {"type": "object", "additionalProperties": True},
                },
            }
            for t in tools
        ]
        messages = [{"role": "system", "content": system}]
        if context_block:
            messages.append({"role": "system", "content": context_block})
        messages.extend(to_openai_messages(history))
        model = self.routed_model(history)
        resp = self._client_for(model).chat.completions.create(
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            **self._chat_kwargs(model, with_tools=True),
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            calls = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
            return {"type": "tool_calls", "calls": calls}
        return {"type": "message", "text": (msg.content or "").strip(), "used_topics": []}
