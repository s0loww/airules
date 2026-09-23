"""FastAPI app exposing POST /agent/turn for the 1C client.

create_app() builds the KB index, LLM client and retriever at startup. Tests inject fakes via
create_app(settings=..., llm=..., chunks=...), so the contract can be exercised offline.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .config import Settings, get_settings
from .kb import Chunk, load_chunks, load_skills, title_map
from .llm import LLM
from .prompt import (
    EMPTY_QUERY,
    NOT_CONFIGURED,
    build_context_block,
    build_skills_block,
    build_skills_catalog,
    build_system_prompt,
    normalize_lang,
    sources_footer,
)
from .rag import EmbeddingRetriever, LexicalRetriever, Retriever, SkillsLexicalRetriever
from .schemas import MessageResponse, ToolCall, ToolCallsResponse, TurnRequest

log = logging.getLogger("assistant")


def build_retriever(settings: Settings, chunks: List[Chunk], llm: LLM) -> Retriever:
    if settings.retrieval == "lexical":
        return LexicalRetriever(chunks)
    if not llm.available:
        log.warning("No API key set; falling back to lexical retrieval.")
        return LexicalRetriever(chunks)
    try:
        return EmbeddingRetriever(chunks, llm.embed)
    except Exception:  # pragma: no cover - network/credential failure at startup
        log.exception("Embedding index failed; falling back to lexical retrieval.")
        return LexicalRetriever(chunks)


def build_skills_retriever(settings: Settings, skills: List[Chunk], llm: LLM) -> Retriever:
    # The skills corpus is tiny, so the lexical path uses the trigger-weighted scorer
    # (BM25 yields negative idf on 2-3 documents); embeddings behave fine when available.
    if settings.retrieval == "lexical" or not llm.available:
        return SkillsLexicalRetriever(skills)
    try:
        return EmbeddingRetriever(skills, llm.embed)
    except Exception:  # pragma: no cover - network/credential failure at startup
        log.exception("Skills embedding index failed; falling back to trigger matching.")
        return SkillsLexicalRetriever(skills)


def create_app(
    settings: Optional[Settings] = None,
    llm: Optional[LLM] = None,
    chunks: Optional[List[Chunk]] = None,
    retriever: Optional[Retriever] = None,
    skills: Optional[List[Chunk]] = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or get_settings()
        ch = chunks if chunks is not None else load_chunks(s.help_dir)
        sk = skills if skills is not None else load_skills(s.skills_dir)
        ll = llm or LLM(s)
        rt = retriever or build_retriever(s, ch, ll)
        app.state.settings = s
        app.state.chunks = ch
        app.state.llm = ll
        app.state.retriever = rt
        app.state.known_ids = {c.topic_id for c in ch}
        app.state.skills = sk
        app.state.skills_retriever = build_skills_retriever(s, sk, ll) if sk else None
        log.info(
            "Indexed %d help chunks, %d skills (retrieval=%s).", len(ch), len(sk), s.retrieval
        )
        yield

    app = FastAPI(title="Contabilidad AI assistant", version="0.1.0", lifespan=lifespan)

    def require_auth(request: Request, authorization: str = Header(default="")) -> None:
        token = request.app.state.settings.assistant_bearer_token
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    @app.get("/health")
    def health(request: Request) -> dict:
        st = request.app.state
        return {
            "status": "ok",
            "chunks": len(st.chunks),
            "skills": len(st.skills),
            "retrieval": st.settings.retrieval,
            "llm_available": st.llm.available,
        }

    @app.post("/reload", dependencies=[Depends(require_auth)])
    def reload(request: Request) -> dict:
        st = request.app.state
        st.chunks = load_chunks(st.settings.help_dir)
        st.retriever = build_retriever(st.settings, st.chunks, st.llm)
        st.known_ids = {c.topic_id for c in st.chunks}
        st.skills = load_skills(st.settings.skills_dir)
        st.skills_retriever = (
            build_skills_retriever(st.settings, st.skills, st.llm) if st.skills else None
        )
        return {"status": "reloaded", "chunks": len(st.chunks), "skills": len(st.skills)}

    @app.post("/agent/turn", dependencies=[Depends(require_auth)])
    def turn(req: TurnRequest, request: Request):
        st = request.app.state
        lang = normalize_lang(req.context.lang)

        # A request ending in a tool result resumes an in-flight agent turn: the 1C loop executed
        # the calls and is sending the results back. Such a POST is never an empty query, never a
        # topic change, and must keep the full history (the tool plumbing anchors the context).
        is_resume = bool(req.messages) and req.messages[-1].role == "tool"

        user_msgs = [m for m in req.messages if m.role == "user"]
        last = user_msgs[-1] if user_msgs else (req.messages[-1] if req.messages else None)
        query = (last.content if last else "").strip()
        if not query and not is_resume:
            return MessageResponse(text=EMPTY_QUERY[lang])
        if not st.llm.available:
            return MessageResponse(text=NOT_CONFIGURED[lang])

        full_history = [m.model_dump() for m in req.messages]

        # Decide continue-vs-new-topic with a dedicated, focused call — but only on the first POST
        # of a turn and when there is a prior exchange to continue from. A new topic is answered on
        # its own (history trimmed to the latest message) so the fresh chat the 1C client opens
        # starts clean; a follow-up keeps the full history and a little extra retrieval context.
        new_topic = False
        if not is_resume and len(user_msgs) >= 2:
            try:
                new_topic = st.llm.classify_new_topic(full_history)
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

        hits = st.retriever.retrieve(retrieval_query, lang, st.settings.top_k)
        context_block = build_context_block(hits, lang)
        system = build_system_prompt(lang, with_tools=bool(req.tools), today=req.context.today)

        # Tools mode: the skills catalog always rides along; the bodies of the playbooks that
        # match this question are injected as binding instructions.
        if req.tools and st.skills:
            catalog = build_skills_catalog(st.skills)
            if catalog:
                system = system + "\n\n" + catalog
            skill_hits = (
                st.skills_retriever.retrieve(retrieval_query, lang, st.settings.skills_top_k)
                if st.skills_retriever
                else []
            )
            block = build_skills_block(skill_hits)
            if block:
                system = system + "\n\n" + block

        try:
            if req.tools:
                result = st.llm.answer_with_tools(system, history, context_block, req.tools)
                if result.get("type") == "tool_calls":
                    return ToolCallsResponse(
                        calls=[ToolCall(**c) for c in result["calls"]], new_topic=new_topic
                    )
                text, used = result.get("text", ""), []
            else:
                result = st.llm.answer_message(system, history, context_block)
                text, used = result.get("text", ""), result.get("used_topics", [])
        except Exception:
            log.exception("LLM call failed")
            raise HTTPException(status_code=502, detail="llm_error")

        seen = set()
        citations = []
        for c in used:
            if c in st.known_ids and c not in seen:
                seen.add(c)
                citations.append(c)
        if st.settings.append_sources_to_text and citations:
            text = text + sources_footer(citations, title_map(st.chunks, lang), lang)
        return MessageResponse(text=text, citations=citations, new_topic=new_topic)

    return app


app = create_app()
