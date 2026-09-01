"""Backend liveness, index freshness and container lifecycle.

Three states look identical to a caller today: the object does not exist, the
index is stale, the server is switched off. That ambiguity is what puts
"CodeMetadata does not see fresh extension files" into a memory file when the
real cause was a stopped container. Everything here exists to keep those three
apart and to say so in the envelope.

Container lifecycle is deliberate, not automatic. Per-project indexes are cheap
(a few hundred MB) while the graph stacks behind them are not, so keeping only
the active projects hot is a sensible policy -- and since the index lives in a
named volume, a restart is an incremental catch-up rather than a rebuild. The
facade automates that only for backends explicitly marked `cold_ok`.
"""
import io
import json
import os
import subprocess
import time

STATE_PATH = os.environ.get(
    "FACADE_STATE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "facade-state.json"))

UP = "up"
COLD = "cold"          # container exists but is not running
DOWN = "down"          # no container, or start refused
UNKNOWN = "unknown"    # docker unavailable, so we cannot tell cold from down


class BackendStatus(object):
    __slots__ = ("kind", "state", "ms", "index_age_s", "detail")

    def __init__(self, kind, state, ms=None, index_age_s=None, detail=None):
        self.kind = kind
        self.state = state
        self.ms = ms
        self.index_age_s = index_age_s
        self.detail = detail

    @property
    def usable(self):
        return self.state == UP

    def as_dict(self):
        out = {"name": self.kind, "state": self.state}
        if self.ms is not None:
            out["ms"] = int(self.ms)
        if self.index_age_s is not None:
            out["index_age_s"] = int(self.index_age_s)
        if self.detail:
            out["detail"] = self.detail
        return out


def _docker(*args, **kwargs):
    """Run a docker command. Returns (ok, stdout). Never raises."""
    timeout = kwargs.get("timeout", 30)
    try:
        proc = subprocess.run(("docker",) + args, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return proc.returncode == 0, (proc.stdout or "").strip()


def container_state(name):
    """running | exited | absent | unknown"""
    if not name:
        return "absent"
    ok, out = _docker("inspect", "-f", "{{.State.Status}}", name)
    if not ok:
        # distinguish "docker is not there" from "container is not there"
        alive, _ = _docker("version", "-f", "{{.Server.Version}}", timeout=10)
        return "absent" if alive else "unknown"
    return out or "unknown"


class Health(object):
    """Probes backends and, where allowed, brings them up."""

    def __init__(self, client_factory, state_path=STATE_PATH):
        # client_factory(url) -> object with .call(tool, args) -> (s, status, text)
        self.client_factory = client_factory
        self.state_path = state_path

    # -- probing ----------------------------------------------------------

    def probe(self, backend, deadline=8.0):
        """One backend: is it answering, and how old is its index?"""
        started = time.time()
        try:
            client = self.client_factory(backend.url)
        except Exception as exc:                     # noqa: BLE001 - probe
            state = container_state(backend.container)
            if state == "exited":
                return BackendStatus(backend.kind, COLD, detail="container stopped")
            if state == "unknown":
                return BackendStatus(backend.kind, UNKNOWN, detail=type(exc).__name__)
            return BackendStatus(backend.kind, DOWN, detail=type(exc).__name__)
        elapsed = (time.time() - started) * 1000
        age = self._index_age(client, backend)
        return BackendStatus(backend.kind, UP, ms=elapsed, index_age_s=age)

    def _index_age(self, client, backend):
        """Seconds since the last incremental pass, when the backend says."""
        tool = "stats" if backend.kind == "code" else "get_indexing_status"
        try:
            _, status, text = client.call(tool, {})
        except Exception:                            # noqa: BLE001 - optional
            return None
        if status != "OK":
            return None
        stamp = _find_timestamp(text)
        if stamp is None:
            return None
        return max(0.0, time.time() - stamp)

    # -- lifecycle --------------------------------------------------------

    def ensure(self, backend, wait_s=90.0, poll_s=3.0):
        """Bring a cold backend up, if the registry allows it.

        Returns a BackendStatus. A backend not marked `cold_ok` is never
        started: waking containers is a side effect, and the registry is where
        that consent is recorded.
        """
        status = self.probe(backend)
        if status.usable or status.state != COLD:
            return status
        if not (backend.cold_ok and backend.container):
            status.detail = "container stopped; cold_ok not set for this backend"
            return status
        ok, _ = _docker("start", backend.container, timeout=60)
        if not ok:
            status.detail = "docker start failed"
            return status
        deadline = time.time() + wait_s
        while time.time() < deadline:
            time.sleep(poll_s)
            status = self.probe(backend)
            if status.usable:
                self.touch(backend.container)
                status.detail = "started on demand"
                return status
        status.detail = "started but not answering within %ds" % int(wait_s)
        return status

    def evict(self, registry, keep=2, dry_run=True):
        """Stop the least recently used managed containers beyond `keep`.

        Defaults to a dry run: this stops other people's work if the policy is
        wrong, so the caller has to ask for it explicitly.
        """
        used = self._load_state().get("last_used", {})
        managed = []
        for name in registry.names():
            for backend in registry.get(name).backends.values():
                if backend.container and backend.cold_ok:
                    managed.append((used.get(backend.container, 0.0), backend.container))
        managed.sort(reverse=True)
        victims = [name for _stamp, name in managed[keep:]
                   if container_state(name) == "running"]
        if not dry_run:
            for name in victims:
                _docker("stop", name, timeout=60)
        return {"kept": keep, "stopped": victims, "dry_run": dry_run}

    # -- last-use bookkeeping --------------------------------------------

    def touch(self, container):
        if not container:
            return
        state = self._load_state()
        state.setdefault("last_used", {})[container] = time.time()
        try:
            with io.open(self.state_path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=1, sort_keys=True)
        except OSError:
            pass

    def _load_state(self):
        try:
            with io.open(self.state_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}


_TS_KEYS = ("last_incremental_at", "last_indexed_at", "updated_at", "completed_at")


def _find_timestamp(text):
    """Pull the freshest ISO timestamp a backend reports, as epoch seconds."""
    import re
    from datetime import datetime
    best = None
    for key in _TS_KEYS:
        for raw in re.findall(key + r'"?\s*[:=]\s*"([^"]+)"', text):
            value = raw.strip()
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            try:
                stamp = datetime.fromisoformat(value)
            except ValueError:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
            epoch = stamp.timestamp()
            if best is None or epoch > best:
                best = epoch
    return best
