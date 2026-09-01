"""End-to-end gate: the MCP server, spoken to as a real client would.

The server is started on an ephemeral port over the replaying facade, then
driven through `mcp_client.Client` -- the same class used to talk to the real
backends. So the protocol is exercised for real; only the backends are fakes.

    python test_server.py
"""
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

from mcp_client import Client                       # noqa: E402
import server as server_mod                         # noqa: E402
from test_facade import CANON, build_facade         # noqa: E402

# Measured surface of the fleet the facade stands in front of: eight servers,
# 72 100 characters of tool schemas in every session.
FLEET_SCHEMA_CHARS = 72100


def start():
    dispatcher = server_mod.Dispatcher(build_facade())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                server_mod.make_handler(dispatcher, "/mcp"))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, "http://127.0.0.1:%d/mcp" % httpd.server_address[1]


def checks(url):
    out = []

    def eq(label, got, want):
        out.append((got == want, label + ": got " + repr(got) + ", want " + repr(want)))

    def ok(label, condition, detail=""):
        out.append((bool(condition), label + (": " + detail if detail else "")))

    client = Client(url)
    ok("initialize completes", True)

    tools = client.tools()
    eq("six verbs are published", sorted(t["name"] for t in tools),
       ["calls", "check", "describe", "find", "status", "usages"])
    ok("every verb documents itself",
       all(t.get("description") and t.get("inputSchema") for t in tools))

    surface = len(json.dumps(tools, ensure_ascii=False))
    ok("the surface is a fraction of the fleet's",
       surface < FLEET_SCHEMA_CHARS // 8,
       "%d chars vs %d across eight servers (%.0f%%)"
       % (surface, FLEET_SCHEMA_CHARS, 100.0 * surface / FLEET_SCHEMA_CHARS))

    _, status, text = client.call("calls", {"id": "ОтправкаПочты"})
    eq("calls answers over the wire", status, "OK")
    payload = json.loads(text)
    eq("callers survive the round trip", len(payload["records"]), 8)
    eq("the canonical id is reported", payload["coverage"]["resolved_id"], CANON)
    ok("provenance survives the round trip",
       all(r["src"]["backend"] == "graph" for r in payload["records"]))

    _, status, text = client.call("usages", {"id": "Справочники.ДоговорыКонтрагентов",
                                             "where": "code"})
    payload = json.loads(text)
    eq("grep tier survives the round trip",
       {r["src"]["tier"] for r in payload["records"]}, {"grep"})

    _, status, text = client.call("status", {})
    payload = json.loads(text)
    ok("status reports the fleet", payload["coverage"]["backends"],
       json.dumps(payload["coverage"]["backends"], ensure_ascii=False))

    # a caller's mistake must come back as data, not as a dead connection
    _, _status, text = client.call("calls", {"id": "ОтправкаПочты", "project": "нет-такого"})
    ok("unknown project is a tool error", "нет-такого" in text, text[:120])
    _, _status, text = client.call("нетТакогоГлагола", {})
    ok("unknown verb is refused", "unknown tool" in text or "нетТакогоГлагола" in text,
       text[:120])
    _, _status, text = client.call("find", {})
    ok("missing required argument is a tool error", "argument" in text.lower(), text[:120])

    # the server must still be alive after all of that
    eq("server survives caller errors", client.call("status", {})[1], "OK")
    return out


def main():
    httpd, url = start()
    try:
        results = checks(url)
    finally:
        httpd.shutdown()
        httpd.server_close()
    failures = []
    for good, message in results:
        print(("  ok   " if good else "  FAIL ") + message)
        if not good:
            failures.append(message)
    print()
    print(("FAILED: " + str(len(failures))) if failures else "все проверки зелёные")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
