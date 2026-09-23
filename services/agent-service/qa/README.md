# QA harness — live answer-quality sweep for the assistant

Asks the RUNNING agent service (`http://127.0.0.1:8080`) every curated question and scores
the answers. Complements the offline contract tests (`tests/`): those pin the wire protocol
with a fake LLM; this exercises the real model + real retrieval + real KB, costing real
(small) OpenAI usage per run.

## Files

- `questions/sweep.yaml` — one operator question per help topic. A coverage guard fails the
  lint when a topic in `help/index.yaml` has no question. Runs in BOTH modes: `kb`
  (no tools — citations checked against the expected topic) and `tools` (production shape —
  the full tool catalogue attached; help questions must NOT trigger tools).
- `questions/behavior.yaml` — tools-mode behavior: right tool, right arguments, honesty
  where no tool exists (sales totals, stock, IVA rates, AR, ledger balances).
- `questions/multistep.yaml` — multi-turn conversations: the 1C agent loop with scripted
  tool results (disambiguation, calc chains, declined/zero/no-match results), follow-ups,
  topic switches, relative-date resolution.
- `tools_catalog.json` — the production tool catalogue, transcribed from
  `AsistenteIATools.BuildToolRegistry()`. KEEP IN SYNC when the BSL changes.
- `sweep.py` — the runner. Reads the bearer token from `../.env` itself (never printed).
- `diagnose.py` — prints the embedding retriever's ranking for ad-hoc queries (the first
  debugging step for a wrong/missing citation).
- `digest.py` — regenerates `digest.md` (topic id + tags + headings + lead) for authoring
  new questions against what topics actually say.

## Running (from `agent-service/`)

```powershell
.venv/Scripts/python.exe qa/sweep.py --check        # offline: coverage + expectation lint
.venv/Scripts/python.exe qa/sweep.py                # full live sweep (~245 calls, ~12 min)
.venv/Scripts/python.exe qa/sweep.py --only s020,m01
.venv/Scripts/python.exe qa/sweep.py --mode tools
```

Outputs: `out/results.jsonl` (full transcripts) and `out/report.md` (summary + failures +
manual-review answers). Exit code 1 when anything FAILed.

## Scoring model

Each step checks any of: `behavior` (message vs `tool:<name>`), `args` (regex per argument),
`terms` (all must appear, accent-folded), `any` (at least one), `rx` (regexes), `not_terms`,
`cite` (kb mode; defaults to the case's `topic`, override with a list when several topics
legitimately answer), `new_topic`. The lint cross-checks every expected term against the
source topic so a failing expectation is distinguishable from a failing answer
(`record_only: true` skips scoring for manual-review cases).

## Interpreting failures

1. Wrong/missing citation in kb mode → `diagnose.py` the query. Below top-5 → tags/content
   fix in `help/`; in top-5 but mis-cited → generation/attribution, usually content
   cross-links or prompt.
2. Tool called when prose expected (or vice versa) → tool DESCRIPTIONS in the BSL are the
   strongest lever (then `agent-skills/`, then the system prompt). Sync `tools_catalog.json`.
3. Wrong argument shapes → schema property descriptions in the BSL.

The 2026-06-11 baseline run: 244 jobs, 218 PASS on first try; fixes raised it to full pass
(see git history of this directory for what each failure taught).
