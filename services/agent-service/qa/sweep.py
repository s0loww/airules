"""KB QA sweep — runs the curated question sets against the LIVE agent service and scores
the answers. Reads the bearer token from agent-service/.env itself (never printed).

Usage (from agent-service/):
  .venv/Scripts/python.exe qa/sweep.py                # everything
  .venv/Scripts/python.exe qa/sweep.py --only s001,m02
  .venv/Scripts/python.exe qa/sweep.py --mode kb      # restrict to one mode
  .venv/Scripts/python.exe qa/sweep.py --check        # offline: coverage + expectation lint

Outputs qa/out/results.jsonl (full transcripts) and qa/out/report.md (summary + failures).

Checks per step:
  behavior   "message" | "tool:NAME" | list of those     (tools mode)
  cite       topic id (or list) that must appear in citations  (kb mode only)
  terms/any  folded substring checks on the answer text
  rx         regexes that must match the folded answer
  not_terms  folded substrings that must NOT appear
  args       {arg: regex} checks on the first tool call's arguments
  new_topic  expected boolean from the response
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SERVICE_DIR = ROOT.parent
sys.path.insert(0, str(SERVICE_DIR))
from app.kb import load_chunks  # noqa: E402

BASE_URL = "http://127.0.0.1:8080"
HELP_DIR = str(SERVICE_DIR.parent / "help")
TODAY = "2026-06-11"
OUT_DIR = ROOT / "out"

_print_lock = threading.Lock()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def read_token() -> str:
    env = SERVICE_DIR / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ASSISTANT_BEARER_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def post_turn(payload: dict, token: str, timeout: float = 120.0) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/agent/turn",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last_err = f"HTTP {e.code}: {detail}"
            if e.code < 500:
                break
        except Exception as e:  # noqa: BLE001 - report any transport error
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(last_err or "request failed")


def load_cases(only: set[str] | None) -> list[dict]:
    cases = []
    for path in sorted((ROOT / "questions").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        defaults = doc.get("defaults", {})
        for case in doc.get("cases", []):
            merged = {**defaults, **case}
            merged["_file"] = path.stem
            if not merged.get("steps"):
                # single-shot case -> one user step carrying the case-level expectations
                expect = {
                    k: merged[k]
                    for k in ("terms", "any", "rx", "not_terms", "new_topic", "behavior", "args")
                    if k in merged
                }
                merged["steps"] = [{"user": merged["q"], "expect": expect}]
                merged["_single"] = True
            if only and merged["id"] not in only:
                continue
            cases.append(merged)
    return cases


# ---------------------------------------------------------------- expectation checks


def check_step(case: dict, step: dict, mode: str, resp: dict, failures: list[str]) -> None:
    expect = dict(step.get("expect") or {})
    if case.get("record_only"):
        return

    # Behavior: single-shot cases expect message in kb mode and case-level tools_behavior
    # (default message) in tools mode; scripted cases say it per step.
    behavior = expect.get("behavior")
    if behavior is None and case.get("_single"):
        behavior = case.get("tools_behavior", "message") if mode == "tools" else "message"
    if behavior is not None:
        allowed = behavior if isinstance(behavior, list) else [behavior]
        got = (
            "message"
            if resp.get("type") == "message"
            else "tool:" + (resp.get("calls") or [{}])[0].get("name", "?")
        )
        if got not in allowed:
            failures.append(f"behavior: expected {allowed}, got {got}")

    if resp.get("type") == "tool_calls":
        args = (resp.get("calls") or [{}])[0].get("arguments") or {}
        for key, pattern in (expect.get("args") or {}).items():
            value = str(args.get(key, ""))
            if not re.search(pattern, value):
                failures.append(f"args.{key}: {pattern!r} !~ {value!r}")
        return  # text checks apply to messages only

    text = fold(resp.get("text", ""))
    for term in expect.get("terms") or []:
        if fold(term) not in text:
            failures.append(f"missing term {term!r}")
    any_terms = expect.get("any") or []
    if any_terms and not any(fold(t) in text for t in any_terms):
        failures.append(f"none of any-terms {any_terms}")
    for pattern in expect.get("rx") or []:
        if not re.search(pattern, text):
            failures.append(f"rx {pattern!r} no match")
    for term in expect.get("not_terms") or []:
        if fold(term) in text:
            failures.append(f"forbidden term {term!r} present")

    if mode == "kb" and (expect.get("cite") or case.get("_single")):
        cite = expect.get("cite") or case.get("cite") or case.get("topic")
        if cite:
            wanted = cite if isinstance(cite, list) else [cite]
            got_citations = resp.get("citations") or []
            if not any(w in got_citations for w in wanted):
                failures.append(f"cite: none of {wanted} in {got_citations}")

    if "new_topic" in expect and bool(resp.get("new_topic")) != bool(expect["new_topic"]):
        failures.append(f"new_topic: expected {expect['new_topic']}, got {resp.get('new_topic')}")


# ---------------------------------------------------------------- conversation engine


def run_case_mode(case: dict, mode: str, tools: list[dict], token: str) -> dict:
    messages: list[dict] = []
    transcript: list[dict] = []
    failures: list[str] = []
    started = time.time()

    for step in case["steps"]:
        if "user" in step:
            messages.append({"role": "user", "content": step["user"]})
        elif "tool_result" in step:
            last_calls = next(
                (m["tool_calls"] for m in reversed(messages) if m.get("tool_calls")), None
            )
            if not last_calls:
                failures.append("scripted tool_result but the model made no tool call")
                break
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": last_calls[0]["id"],
                    "content": step["tool_result"],
                }
            )
            for extra in last_calls[1:]:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": extra["id"],
                        "content": '{"status":"error","error":"not_executed"}',
                    }
                )
            if len(last_calls) > 1:
                failures.append(f"model made {len(last_calls)} parallel calls; scripted only 1")

        payload = {
            "context": {"lang": case.get("lang", "es"), "user": "QA", "today": TODAY},
            "messages": messages,
            "tools": tools if mode == "tools" else [],
        }
        try:
            resp = post_turn(payload, token)
        except RuntimeError as e:
            return {
                "id": case["id"],
                "mode": mode,
                "status": "ERROR",
                "error": str(e),
                "transcript": transcript,
                "elapsed": round(time.time() - started, 1),
            }

        transcript.append({"step": step.get("user") or "<tool_result>", "response": resp})
        check_step(case, step, mode, resp, failures)

        if resp.get("type") == "tool_calls":
            messages.append(
                {"role": "assistant", "content": "", "tool_calls": resp.get("calls") or []}
            )
        else:
            messages.append({"role": "assistant", "content": resp.get("text", "")})

    status = "PASS" if not failures else "FAIL"
    if case.get("record_only"):
        status = "REVIEW"
    return {
        "id": case["id"],
        "file": case["_file"],
        "mode": mode,
        "topic": case.get("topic", ""),
        "name": case.get("name", ""),
        "q": case["steps"][0].get("user", ""),
        "status": status,
        "failures": failures,
        "transcript": transcript,
        "elapsed": round(time.time() - started, 1),
    }


# ---------------------------------------------------------------- offline lint


def lint(cases: list[dict]) -> tuple[list[str], list[str]]:
    chunks = load_chunks(HELP_DIR)
    es_topics = {c.topic_id for c in chunks if c.lang == "es"}
    covered = {c.get("topic") for c in cases if c.get("topic")}
    missing = sorted(es_topics - covered)

    source = {}
    for c in chunks:
        if c.lang == "es":
            source[c.topic_id] = fold(c.search_text)
    warnings = []
    for case in cases:
        topic = case.get("topic")
        if not topic or topic not in source:
            continue
        for term in case.get("terms") or []:
            if fold(term) not in source[topic]:
                warnings.append(f"{case['id']}: term {term!r} not in source {topic}")
        any_terms = case.get("any") or []
        if any_terms and not any(fold(t) in source[topic] for t in any_terms):
            warnings.append(f"{case['id']}: no any-term {any_terms} in source {topic}")
    return missing, warnings


# ---------------------------------------------------------------- reporting


def write_report(results: list[dict], missing: list[str], warnings: list[str]) -> str:
    lines = ["# KB QA sweep report", ""]
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    total = len(results)
    lines.append(
        f"**{total} runs** — "
        + ", ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))
    )
    lines.append("")
    if missing:
        lines.append(f"## Coverage gaps ({len(missing)} topics without a question)")
        lines.extend(f"- {t}" for t in missing)
        lines.append("")
    if warnings:
        lines.append(f"## Expectation lint warnings ({len(warnings)})")
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")

    bad = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if bad:
        lines.append(f"## Failures ({len(bad)})")
        for r in bad:
            lines.append(f"### {r['id']} [{r['mode']}] {r.get('topic') or r.get('name', '')}")
            lines.append(f"Q: {r.get('q', '')}")
            for f in r.get("failures", []):
                lines.append(f"- {f}")
            if r.get("error"):
                lines.append(f"- ERROR: {r['error']}")
            last = (r.get("transcript") or [{}])[-1].get("response", {})
            if last.get("type") == "message":
                lines.append(f"- answer: {last.get('text', '')[:600]}")
            elif last.get("type") == "tool_calls":
                lines.append(f"- tool_calls: {json.dumps(last.get('calls'), ensure_ascii=False)[:400]}")
            lines.append("")

    review = [r for r in results if r["status"] == "REVIEW"]
    if review:
        lines.append(f"## Manual review ({len(review)})")
        for r in review:
            last = (r.get("transcript") or [{}])[-1].get("response", {})
            lines.append(f"### {r['id']} {r.get('name', '')}")
            lines.append(f"Q: {r.get('q', '')}")
            lines.append(f"A: {last.get('text', '')[:600]}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="comma-separated case ids")
    parser.add_argument("--mode", default="", choices=["", "kb", "tools"])
    parser.add_argument("--check", action="store_true", help="offline lint only")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    cases = load_cases(only)
    missing, warnings = lint(load_cases(None))

    if args.check:
        print(f"{len(cases)} cases loaded")
        print(f"coverage gaps: {len(missing)}")
        for t in missing:
            print(f"  MISSING {t}")
        print(f"lint warnings: {len(warnings)}")
        for w in warnings:
            print(f"  WARN {w}")
        return 0 if not missing else 1

    token = read_token()
    tools = json.loads((ROOT / "tools_catalog.json").read_text(encoding="utf-8"))["tools"]

    jobs = []
    for case in cases:
        for mode in case.get("modes", ["kb"]):
            if args.mode and mode != args.mode:
                continue
            jobs.append((case, mode))

    print(f"running {len(jobs)} jobs ({len(cases)} cases) against {BASE_URL} ...")
    results = []
    done = 0

    def run(job):
        nonlocal done
        case, mode = job
        r = run_case_mode(case, mode, tools, token)
        with _print_lock:
            done += 1
            tag = r["status"]
            print(f"[{done}/{len(jobs)}] {tag:7} {r['id']} ({mode}) {r['elapsed']}s")
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, jobs))

    OUT_DIR.mkdir(exist_ok=True)
    with (OUT_DIR / "results.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = write_report(results, missing, warnings)
    (OUT_DIR / "report.md").write_text(report, encoding="utf-8")

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("done:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"report: {OUT_DIR / 'report.md'}")
    return 0 if counts.get("FAIL", 0) + counts.get("ERROR", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
