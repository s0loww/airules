# Agent Service — the assistant's "brain"

The external service the 1C in-app assistant calls. It receives a turn from 1C
(`POST /agent/turn`), retrieves the relevant help topics from `../help`, asks an LLM to answer
**grounded in that help**, and returns the answer. 1C only ever makes an outbound call to it.

```
1C client (CommonModule.AsistenteIAServer)  ──POST /agent/turn──▶  this service  ──▶  OpenAI
        ▲                                                                 │
        └───────────────  {type:"message", text, citations}  ◀───────────┘
                                                                  grounded in ../help/*.md
```

Phase 1 is **help only**: the service explains and guides. It cannot act on the database — that
arrives in later phases via the tool catalogue (the request already carries a `tools[]` array).

---

## Run it (3 steps)

Prerequisites: Docker Desktop running, and an OpenAI API key.

1. **Configure.** Copy the example env file and fill it in:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env`:
   - `OPENAI_API_KEY` — your key.
   - `ASSISTANT_BEARER_TOKEN` — a shared secret you invent. Generate one with:
     ```powershell
     python -c "import secrets; print(secrets.token_urlsafe(24))"
     ```

2. **Start.**
   ```powershell
   docker compose up --build
   ```
   The KB in `../help` is mounted read-only; the service indexes it on startup.

3. **Point 1C at it.** Set two constants in your infobase (Main menu → All functions →
   Constants, or a settings form):
   - `DireccionServicioAsistente` = `http://localhost:8080`
   - `TokenServicioAsistente` = the same value as `ASSISTANT_BEARER_TOKEN`

   Ask the home-page assistant a question — it now answers for real.

> The 1C client is the only consumer, and it calls outbound over `http://localhost`. Nothing is
> exposed to the network. For a remote deployment, put it behind TLS and set the 1C constant to
> the `https://…` URL — `ParseServiceURL` in `AsistenteIAServer` already handles both.

---

## Verify without 1C

Once it's up, you can smoke-test the brain directly:

```powershell
# health
curl http://localhost:8080/health

# a turn (replace TOKEN)
curl -X POST http://localhost:8080/agent/turn `
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" `
  -d '{\"context\":{\"lang\":\"es\",\"user\":\"yo\"},\"messages\":[{\"role\":\"user\",\"content\":\"¿cómo registro una compra?\"}],\"tools\":[]}'
```

You should get `{"type":"message","text":"…","citations":["compras/orden-de-compra"]}`.

---

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI key. Required to generate answers. |
| `OPENAI_BASE_URL` | (blank) | Set to an **Azure OpenAI** or proxy endpoint to switch providers. Blank = OpenAI. |
| `CHAT_MODEL` | `gpt-4o-mini` | Chat model (or Azure deployment name). |
| `EMBED_MODEL` | `text-embedding-3-small` | Embedding model for retrieval. |
| `RETRIEVAL` | `embeddings` | `embeddings` (semantic) or `lexical` (BM25, no embedding calls). |
| `TOP_K` | `4` | How many help chunks to ground each answer on. |
| `ASSISTANT_BEARER_TOKEN` | (blank) | Shared secret; must equal the 1C `TokenServicioAsistente`. Blank disables auth. |
| `APPEND_SOURCES_TO_TEXT` | `true` | Append a "Fuente: …" line to answers (Phase-1 UI doesn't render citations yet). |

### Switching to Azure OpenAI later

No code change — set `OPENAI_BASE_URL` to your Azure endpoint, `CHAT_MODEL`/`EMBED_MODEL` to your
deployment names, and `OPENAI_API_KEY` to the Azure key. Restart.

---

## The contract (must match the 1C client)

`POST /agent/turn`, header `Authorization: Bearer <token>` (sent only when the token is set).

```jsonc
// request
{ "context": { "lang": "es", "user": "jdoe" },
  "messages": [ { "role": "user", "content": "¿cómo cierro el mes?" } ],
  "tools": [ { "name": "find_documents", "description": "…", "risk": "read" } ] }

// response — message
{ "type": "message", "text": "…", "citations": ["procesos/cierre-de-mes"] }
// response — tool calls (Phase 2+)
{ "type": "tool_calls", "calls": [ { "id": "c1", "name": "find_documents", "arguments": { } } ] }
```

`citations` are topic ids from `../help/index.yaml`. They are stringified by the 1C parser, so
they must stay plain strings.

---

## Editing the help

Content lives in `../help` (see `../help/README.md`). After editing topics, re-index without a
rebuild:

```powershell
curl -X POST http://localhost:8080/reload -H "Authorization: Bearer TOKEN"
```

---

## Develop / test

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH = (Get-Location)
.\.venv\Scripts\python.exe -m pytest tests -q
```

The contract tests mock the LLM and use lexical retrieval, so they need **no API key and no
network** — they assert wire-compatibility with the 1C client and bearer auth.

---

## Layout

```
agent-service/
  app/
    main.py       # FastAPI app + routes (create_app factory for tests)
    schemas.py    # the wire contract (Pydantic)
    config.py     # env-driven settings
    kb.py         # load ../help into bilingual chunks
    rag.py        # lexical (BM25) and embedding retrievers
    llm.py        # provider-agnostic LLM seam (OpenAI impl)
    prompt.py     # system prompt + localized strings
  tests/test_contract.py
  Dockerfile  docker-compose.yml  requirements*.txt  .env.example
```

This service is intentionally self-contained — it can be lifted into its own repository later;
only the `../help` volume mount in `docker-compose.yml` ties it to this tree.
