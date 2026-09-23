"""FastAPI app exposing POST /agent/turn for the 1C client.

create_app() builds each tenant's KB index, LLM client and retriever at startup (see
app/tenants.py). Tests inject fakes via create_app(settings=..., llm=..., chunks=...), which
configure the single default tenant, so the contract can be exercised offline.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request

from .config import Settings, get_settings
from .kb import Chunk, title_map
from .llm import LLM
from .prompt import (
    build_context_block,
    build_skills_block,
    build_skills_catalog,
    build_system_prompt,
    normalize_lang,
    sources_footer,
)
from .rag import Retriever
from .schemas import MessageResponse, ToolCall, ToolCallsResponse, TurnRequest
from .tenants import Tenant, load_registry, pick, single_tenant

log = logging.getLogger("assistant")


def create_app(
    settings: Optional[Settings] = None,
    llm: Optional[LLM] = None,
    chunks: Optional[List[Chunk]] = None,
    retriever: Optional[Retriever] = None,
    skills: Optional[List[Chunk]] = None,
    tenants: Optional[List[Tenant]] = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or get_settings()
        if tenants is not None:
            built = [t.index() if t.retriever is None else t for t in tenants]
        elif s.tenants_file:
            built = [t.index() for t in load_registry(s)]
        else:
            built = [single_tenant(s, llm).index(chunks=chunks, skills=skills,
                                                 retriever=retriever)]
        app.state.tenants: Dict[str, Tenant] = {t.name: t for t in built}
        yield

    app = FastAPI(title="1C AI assistant", version="0.2.0", lifespan=lifespan)

    def tenant_of(request: Request, authorization: str) -> Tenant:
        tenant = pick(request.app.state.tenants, authorization)
        if tenant is None:
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")
        return tenant

    @app.get("/health")
    def health(request: Request) -> dict:
        states = {
            name: {
                "chunks": len(t.chunks),
                "skills": len(t.skills),
                "retrieval": t.settings.retrieval,
                "llm_available": t.llm.available,
                "product": t.profile.product,
            }
            for name, t in request.app.state.tenants.items()
        }
        body = {"status": "ok", "tenants": states}
        if len(states) == 1:
            # a single tenant also reports at the top level, as the service always did
            body.update({k: v for k, v in next(iter(states.values())).items() if k != "product"})
        return body

    @app.post("/reload")
    def reload(request: Request, authorization: str = Header(default="")) -> dict:
        # Re-index the caller's own tenant only: a token grants access to one base.
        tenant = tenant_of(request, authorization)
        tenant.index()
        return {"status": "reloaded", "tenant": tenant.name,
                "chunks": len(tenant.chunks), "skills": len(tenant.skills)}

    @app.post("/agent/turn")
    def turn(req: TurnRequest, request: Request, authorization: str = Header(default="")):
        t = tenant_of(request, authorization)
        profile = t.profile
        lang = normalize_lang(req.context.lang, profile)

        # A request ending in a tool result resumes an in-flight agent turn: the 1C loop executed
        # the calls and is sending the results back. Such a POST is never an empty query, never a
        # topic change, and must keep the full history (the tool plumbing anchors the context).
        is_resume = bool(req.messages) and req.messages[-1].role == "tool"

        user_msgs = [m for m in req.messages if m.role == "user"]
        last = user_msgs[-1] if user_msgs else (req.messages[-1] if req.messages else None)
        query = (last.content if last else "").strip()
        if not query and not is_resume:
            return MessageResponse(text=profile.string("empty_query", lang))
        if not t.llm.available:
            return MessageResponse(text=profile.string("not_configured", lang))

        full_history = [m.model_dump() for m in req.messages]

        # Decide continue-vs-new-topic with a dedicated, focused call — but only on the first POST
        # of a turn and when there is a prior exchange to continue from. A new topic is answered on
        # its own (history trimmed to the latest message) so the fresh chat the 1C client opens
        # starts clean; a follow-up keeps the full history and a little extra retrieval context.
        new_topic = False
        if not is_resume and len(user_msgs) >= 2:
            try:
                new_topic = t.llm.classify_new_topic(full_history)
            except Exception:
                log.exception("topic classification failed")
                new_topic = False

        if new_topic:
            history = [{"role": "user", "content": query}]
            retrieval_query = query
        else:
            history = full_history
            recent = [m.content for m in user_msgs[-2:]] or [query]
            retrieval_query = "\n".join(recent)

        hits = t.retriever.retrieve(retrieval_query, lang, t.settings.top_k)
        context_block = build_context_block(hits, lang, profile)
        system = build_system_prompt(lang, with_tools=bool(req.tools), today=req.context.today,
                                     profile=profile)

        # Tools mode: the skills catalog always rides along; the bodies of the playbooks that
        # match this question are injected as binding instructions.
        if req.tools and t.skills:
            catalog = build_skills_catalog(t.skills)
            if catalog:
                system = system + "\n\n" + catalog
            skill_hits = (
                t.skills_retriever.retrieve(retrieval_query, lang, t.settings.skills_top_k)
                if t.skills_retriever
                else []
            )
            block = build_skills_block(skill_hits)
            if block:
                system = system + "\n\n" + block

        try:
            if req.tools:
                result = t.llm.answer_with_tools(system, history, context_block, req.tools)
                if result.get("type") == "tool_calls":
                    return ToolCallsResponse(
                        calls=[ToolCall(**c) for c in result["calls"]], new_topic=new_topic
                    )
                text, used = result.get("text", ""), []
            else:
                result = t.llm.answer_message(system, history, context_block)
                text, used = result.get("text", ""), result.get("used_topics", [])
        except Exception:
            log.exception("LLM call failed")
            raise HTTPException(status_code=502, detail="llm_error")

        seen = set()
        citations = []
        for c in used:
            if c in t.known_ids and c not in seen:
                seen.add(c)
                citations.append(c)
        if t.settings.append_sources_to_text and citations:
            text = text + sources_footer(citations, title_map(t.chunks, lang), lang, profile)
        return MessageResponse(text=text, citations=citations, new_topic=new_topic)

    return app


app = create_app()
