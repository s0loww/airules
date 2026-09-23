"""Tenants: one 1C base each — its knowledge base, playbooks, profile, token and models.

The 1C client already sends a bearer token (the constant TokenServicioAsistente), so the token
is what tells tenants apart: no change on the 1C side is needed to share one service between
bases. The registry is YAML (`TENANTS_FILE`):

    tenants:
      ec:
        token_env: EC_ASSISTANT_TOKEN          # the token itself stays in the environment
        help_dir: /tenants/ec/help
        skills_dir: /tenants/ec/agent-skills
        profile: /tenants/ec/assistant-profile.md
        settings:                              # optional per-tenant overrides of Settings
          chat_model: deepseek-v4-flash
          chat_model_hard: deepseek-v4-pro
          model_router_enabled: true

Without a registry the service runs one tenant, "default", from the plain settings — the
behaviour a project's own copy of the service always had.
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from .config import Settings
from .kb import Chunk, load_chunks, load_skills
from .llm import LLM
from .prompt import Profile, load_profile
from .rag import EmbeddingRetriever, LexicalRetriever, Retriever, SkillsLexicalRetriever

log = logging.getLogger("assistant")

DEFAULT = "default"

# Settings a tenant may override. Provider keys and endpoints are host-wide on purpose:
# a registry file names models, it does not carry secrets.
_OVERRIDABLE = {
    "chat_model", "chat_model_hard", "model_router_enabled", "reasoning_effort",
    "request_timeout", "retrieval", "top_k", "skills_top_k", "append_sources_to_text",
    "embed_model",
}


@dataclass
class Tenant:
    name: str
    settings: Settings
    profile: Profile
    token: str = ""
    llm: Any = None
    chunks: List[Chunk] = field(default_factory=list)
    retriever: Optional[Retriever] = None
    known_ids: set = field(default_factory=set)
    skills: List[Chunk] = field(default_factory=list)
    skills_retriever: Optional[Retriever] = None

    def index(self, chunks: Optional[List[Chunk]] = None, skills: Optional[List[Chunk]] = None,
              retriever: Optional[Retriever] = None) -> "Tenant":
        """(Re)build the knowledge base and playbook indexes."""
        s = self.settings
        self.chunks = chunks if chunks is not None else load_chunks(
            s.help_dir, self.profile.primary_lang)
        self.skills = skills if skills is not None else load_skills(s.skills_dir)
        self.retriever = retriever or build_retriever(s, self.chunks, self.llm)
        self.known_ids = {c.topic_id for c in self.chunks}
        self.skills_retriever = (build_skills_retriever(s, self.skills, self.llm)
                                 if self.skills else None)
        log.info("tenant %s: %d help chunks, %d skills (retrieval=%s)",
                 self.name, len(self.chunks), len(self.skills), s.retrieval)
        return self


def build_retriever(settings: Settings, chunks: List[Chunk], llm) -> Retriever:
    if settings.retrieval == "lexical":
        return LexicalRetriever(chunks)
    if not getattr(llm, "embed_available", getattr(llm, "available", False)):
        log.warning("No embeddings key set; falling back to lexical retrieval.")
        return LexicalRetriever(chunks)
    try:
        return EmbeddingRetriever(chunks, llm.embed)
    except Exception:  # pragma: no cover - network/credential failure at startup
        log.exception("Embedding index failed; falling back to lexical retrieval.")
        return LexicalRetriever(chunks)


def build_skills_retriever(settings: Settings, skills: List[Chunk], llm) -> Retriever:
    # The skills corpus is tiny, so the lexical path uses the trigger-weighted scorer
    # (BM25 yields negative idf on 2-3 documents); embeddings behave fine when available.
    if settings.retrieval == "lexical" or not getattr(
            llm, "embed_available", getattr(llm, "available", False)):
        return SkillsLexicalRetriever(skills)
    try:
        return EmbeddingRetriever(skills, llm.embed)
    except Exception:  # pragma: no cover - network/credential failure at startup
        log.exception("Skills embedding index failed; falling back to trigger matching.")
        return SkillsLexicalRetriever(skills)


def single_tenant(settings: Settings, llm=None) -> Tenant:
    profile = load_profile(settings.profile)
    return Tenant(name=DEFAULT, settings=settings, profile=profile,
                  token=settings.assistant_bearer_token,
                  llm=llm or LLM(settings, profile))


def load_registry(settings: Settings) -> List[Tenant]:
    """Tenants from `settings.tenants_file`. A tenant without a token is refused: in a
    shared service an open tenant would answer anyone who can reach the port."""
    with open(settings.tenants_file, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    tenants: List[Tenant] = []
    for name, spec in (raw.get("tenants") or {}).items():
        spec = spec or {}
        overrides = {k: v for k, v in (spec.get("settings") or {}).items()
                     if k in _OVERRIDABLE}
        unknown = set(spec.get("settings") or {}) - _OVERRIDABLE
        if unknown:
            raise ValueError("tenant %s: settings not overridable per tenant: %s"
                             % (name, ", ".join(sorted(unknown))))
        overrides["help_dir"] = spec.get("help_dir") or settings.help_dir
        overrides["skills_dir"] = spec.get("skills_dir") or ""
        overrides["profile"] = spec.get("profile") or ""
        tenant_settings = settings.model_copy(update=overrides)
        token = spec.get("token") or (os.environ.get(spec["token_env"], "")
                                      if spec.get("token_env") else "")
        if not token:
            raise ValueError("tenant %s has no token (set token_env and the variable)" % name)
        profile = load_profile(tenant_settings.profile)
        tenants.append(Tenant(name=str(name), settings=tenant_settings, profile=profile,
                              token=token, llm=LLM(tenant_settings, profile)))
    if not tenants:
        raise ValueError("tenant registry %s lists no tenants" % settings.tenants_file)
    tokens = [t.token for t in tenants]
    if len(set(tokens)) != len(tokens):
        raise ValueError("two tenants share a token: the service could not tell them apart")
    return tenants


def pick(tenants: Dict[str, Tenant], authorization: str) -> Optional[Tenant]:
    """The tenant a request belongs to, or None when the token matches none.

    A single tenant with a blank token is the legacy open mode: it takes every request.
    Comparison is constant-time -- tokens are the only thing guarding a tenant's data.
    """
    presented = authorization[7:] if authorization.startswith("Bearer ") else ""
    if len(tenants) == 1:
        only = next(iter(tenants.values()))
        if not only.token:
            return only
    for tenant in tenants.values():
        if tenant.token and hmac.compare_digest(presented.encode(), tenant.token.encode()):
            return tenant
    return None
