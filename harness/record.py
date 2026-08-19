"""The adapter record: what a target reports about one model run.

Validation is strict because a malformed record from one target is easy to notice
here and nearly impossible to notice on a finished site.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

STATUSES = ("ok", "failed", "not_applicable")


class RecordError(Exception):
    """An adapter wrote a record that does not satisfy the schema."""


@dataclasses.dataclass(frozen=True)
class AdapterRecord:
    target: str
    software: str
    version: str
    model: str
    status: str
    environment: dict
    timing: dict
    maps: tuple[dict, ...]
    error: str | None = None

    @classmethod
    def from_dict(cls, doc: dict) -> "AdapterRecord":
        for field in ("target", "software", "version", "model", "status"):
            if not doc.get(field):
                raise RecordError(f"missing required field {field!r}")

        status = doc["status"]
        if status not in STATUSES:
            raise RecordError(f"status must be one of {STATUSES}, got {status!r}")

        maps = tuple(doc.get("maps") or ())
        for m in maps:
            for field in ("name", "unit", "path"):
                if field not in m:
                    raise RecordError(f"map {m.get('name', '?')!r}: missing {field!r}")

        timing = dict(doc.get("timing") or {})
        if status == "ok":
            samples = timing.get("fit_seconds") or []
            if timing.get("repeats") != len(samples):
                raise RecordError(
                    f"timing.repeats ({timing.get('repeats')}) does not match "
                    f"{len(samples)} recorded fit_seconds"
                )

        error = doc.get("error")
        if status == "failed" and not error:
            raise RecordError("a failed record must carry an 'error' explaining why")

        return cls(
            target=doc["target"], software=doc["software"], version=doc["version"],
            model=doc["model"], status=status,
            environment=dict(doc.get("environment") or {}),
            timing=timing, maps=maps, error=error,
        )


def load_adapter_record(path: str | pathlib.Path) -> AdapterRecord:
    return AdapterRecord.from_dict(json.loads(pathlib.Path(path).read_text()))
