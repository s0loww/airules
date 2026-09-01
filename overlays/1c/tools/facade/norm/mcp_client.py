"""Minimal MCP-over-HTTP client -- enough to capture fixtures.

Not a general client: it speaks just the initialize / tools/list / tools/call
subset, over JSON-RPC with the streamable-HTTP transport, and unwraps an
SSE-framed reply when the server sends one. Standard library only.
"""
import json
import time
import urllib.request


def _post(url, payload, session_id=None, timeout=120):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["mcp-session-id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers)
    response = urllib.request.urlopen(request, timeout=timeout)
    raw = response.read().decode("utf-8", "replace")
    # some servers frame the reply as SSE even for a plain POST
    if raw.lstrip().startswith(("event:", "data:")) or "\ndata:" in raw:
        for line in raw.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                break
    return response.headers.get("mcp-session-id"), json.loads(raw)


class Client(object):
    """One MCP endpoint. Opens a session on construction."""

    PROTOCOL = "2025-03-26"

    def __init__(self, url):
        self.url = url
        self.session_id, _ = _post(url, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": self.PROTOCOL, "capabilities": {},
                       "clientInfo": {"name": "facade-capture", "version": "1"}}})

    def tools(self):
        _, reply = _post(self.url, {"jsonrpc": "2.0", "id": 2,
                                    "method": "tools/list", "params": {}}, self.session_id)
        return reply.get("result", {}).get("tools", [])

    def call(self, name, arguments):
        """Returns (seconds, status, text). Never raises on a server-side error."""
        started = time.time()
        try:
            _, reply = _post(self.url, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                        "params": {"name": name, "arguments": arguments}},
                             self.session_id)
        except Exception as exc:                     # noqa: BLE001 - capture tool
            return time.time() - started, "FAIL", type(exc).__name__ + ": " + str(exc)
        elapsed = time.time() - started
        if "error" in reply:
            return elapsed, "ERR", json.dumps(reply["error"], ensure_ascii=False)
        text = "\n".join(part.get("text", "")
                         for part in reply.get("result", {}).get("content", []))
        return elapsed, ("EMPTY" if not text.strip() else "OK"), text
