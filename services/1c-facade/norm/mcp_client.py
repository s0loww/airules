"""Minimal MCP-over-HTTP client -- enough to capture fixtures.

Not a general client: it speaks just the initialize / tools/list / tools/call
subset, over JSON-RPC with the streamable-HTTP transport, and unwraps an
SSE-framed reply when the server sends one. Standard library only.
"""
import itertools
import json
import threading
import time
import urllib.error
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

    def __init__(self, url, timeout=120):
        self.url = url
        # Read per call, so the facade can tighten it after construction from
        # the registry entry without the factory having to know about it.
        self.timeout = timeout
        self._lock = threading.Lock()
        # JSON-RPC id must be unique per in-flight request within a session.
        # A fixed id let two concurrent calls to one backend collide: the
        # backend answered one of them and left the other stream open forever
        # (keep-alive, so the read timeout never fired). Agents that issue tool
        # calls in parallel (Grok Build does by default) hung on it for good.
        self._ids = itertools.count(1)
        self._ids_lock = threading.Lock()
        self.session_id = None
        self._open(None)

    def _next_id(self):
        with self._ids_lock:
            return next(self._ids)

    def _open(self, stale):
        """Open a session -- unless another thread already replaced `stale`."""
        with self._lock:
            if self.session_id is not None and self.session_id != stale:
                return
            self.session_id, _ = _post(self.url, {
                "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
                "params": {"protocolVersion": self.PROTOCOL, "capabilities": {},
                           "clientInfo": {"name": "facade-capture", "version": "1"}}},
                                       timeout=min(self.timeout, 30))

    def _session_post(self, payload, timeout):
        """POST within the session, reopening it once if the server forgot it.

        The comol images of 27.09.2026 drop a session idle for 30 minutes
        (`idle_ttl=1800s`) and answer its id with 404, as the MCP transport
        prescribes; the client is then to initialize again. A facade keeps one
        session per backend for days, so without this every backend fell silent
        half an hour after the facade last used it."""
        session = self.session_id
        try:
            return _post(self.url, payload, session, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        self._open(session)
        return _post(self.url, payload, self.session_id, timeout=timeout)

    def tools(self):
        _, reply = self._session_post({"jsonrpc": "2.0", "id": self._next_id(),
                                       "method": "tools/list", "params": {}}, self.timeout)
        return reply.get("result", {}).get("tools", [])

    def call(self, name, arguments):
        """Returns (seconds, status, text). Never raises on a server-side error."""
        started = time.time()
        try:
            _, reply = self._session_post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
                                           "params": {"name": name, "arguments": arguments}},
                                          self.timeout)
        except Exception as exc:                     # noqa: BLE001 - capture tool
            return time.time() - started, "FAIL", type(exc).__name__ + ": " + str(exc)
        elapsed = time.time() - started
        if "error" in reply:
            return elapsed, "ERR", json.dumps(reply["error"], ensure_ascii=False)
        text = "\n".join(part.get("text", "")
                         for part in reply.get("result", {}).get("content", []))
        # A tool-level failure (bad arguments, a raised exception) comes back as
        # a normal result flagged isError; reading it as OK hands the error text
        # to a parser as if it were data.
        if reply.get("result", {}).get("isError"):
            return elapsed, "ERR", text
        return elapsed, ("EMPTY" if not text.strip() else "OK"), text
