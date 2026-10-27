"""The answer envelope.

Records alone are not enough. "Nothing found", "the index is two days old" and
"the server is switched off" all produce an empty record list, and a caller
that cannot tell them apart will happily report the wrong conclusion. The
`coverage` block carries what the records cannot: which id was actually asked
for after resolution, which backends answered, how stale they were, and where
an answer came from when it did not come from an index.
"""
from record import prune


class Coverage(object):
    __slots__ = ("asked", "resolved_id", "candidates", "backends", "index_age_s",
                 "degraded", "notes", "not_found")

    def __init__(self, asked):
        self.asked = asked
        self.resolved_id = None
        self.candidates = []
        self.backends = []
        self.index_age_s = None
        self.degraded = False
        self.notes = []
        # every backend answered and none has the thing: absence, not silence
        self.not_found = False

    def add_backend(self, name, state, ms=None, index_age_s=None, detail=None):
        entry = {"name": name, "state": state}
        if ms is not None:
            entry["ms"] = int(ms)
        if detail:
            entry["detail"] = detail
        self.backends.append(entry)
        if index_age_s is not None:
            if self.index_age_s is None or index_age_s > self.index_age_s:
                self.index_age_s = int(index_age_s)
        if state != "up":
            self.degraded = True

    def note(self, text):
        if text and text not in self.notes:
            self.notes.append(text)

    def as_dict(self):
        out = {"asked": self.asked, "degraded": self.degraded}
        if self.not_found:
            out["not_found"] = True
        if self.resolved_id:
            out["resolved_id"] = self.resolved_id
        if self.candidates:
            out["ambiguous"] = self.candidates
        if self.backends:
            out["backends"] = self.backends
        if self.index_age_s is not None:
            out["index_age_s"] = self.index_age_s
        if self.notes:
            out["notes"] = self.notes
        return out


class Envelope(object):
    def __init__(self, asked):
        self.records = []
        self.coverage = Coverage(asked)
        # Set on the per-unit envelopes of a base-plus-extensions fan-out: there
        # a unit that simply does not have the object is not a degraded answer.
        self.absent_ok = False

    def extend(self, records):
        self.records.extend(records)
        return self

    def merge(self, parse_result, backend_name=None):
        """Absorb a ParseResult, carrying its drift and status into coverage."""
        if parse_result is None:
            return self
        if parse_result.status == "unparsed":
            self.coverage.note("unparsed reply from %s: %s"
                               % (backend_name or "backend", parse_result.note or "?"))
            self.coverage.degraded = True
        elif parse_result.status == "not_found" and self.absent_ok:
            pass
        elif parse_result.note and (parse_result.status == "not_found"
                                    or "in progress" in parse_result.note):
            # a refusal ("Module not found") or a fallback layer answering while
            # the index builds: both change how an empty answer must be read.
            # Other parser notes are trivia (which ranker ran) and stay out.
            self.coverage.note("%s: %s" % (backend_name or "backend", parse_result.note))
            self.coverage.degraded = True
        if parse_result.drift:
            self.coverage.note("format drift: " + "; ".join(parse_result.drift))
            self.coverage.degraded = True
        self.records.extend(parse_result.records)
        return self

    MERGEABLE = ("owner", "loc", "sig", "text")

    def dedupe(self):
        """Collapse identical ids, merging field by field.

        Picking a winner would throw away whatever the loser knew that the
        winner did not -- and the two backends are complementary precisely at
        the field level (one carries a file location, the other a signature).
        So duplicates fill each other's gaps, and the first record's provenance
        is kept as primary.

        Merging is only sound once ids are canonical, which is why the resolver
        runs before any backend is called rather than after.
        """
        kept = {}
        order = []
        for record in self.records:
            # the scope is part of identity: the same routine in the base and in
            # an extension are two records, and merging them would hide exactly
            # the difference the caller asked about
            key = (record.id, record.rel.type if record.rel else None,
                   record.rel.to if record.rel else None, record.scope)
            if key not in kept:
                kept[key] = record
                order.append(key)
                continue
            target = kept[key]
            for field in self.MERGEABLE:
                if getattr(target, field, None) is None and getattr(record, field, None):
                    setattr(target, field, getattr(record, field))
        self.records = [kept[k] for k in order]
        return self

    def as_dict(self):
        return {"records": [prune(r) for r in self.records],
                "coverage": self.coverage.as_dict()}
