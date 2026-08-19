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

        maps_raw = doc.get("maps") or ()
        if not isinstance(maps_raw, (list, tuple)):
            raise RecordError(f"'maps' must be a list, got {type(maps_raw).__name__}")
        maps = tuple(maps_raw)
        for i, m in enumerate(maps):
            if not isinstance(m, dict):
                raise RecordError(f"maps[{i}]: must be an object, got {type(m).__name__}")
            for field in ("name", "unit", "path"):
                if field not in m:
                    raise RecordError(f"maps[{i}] ({m.get('name', '?')!r}): missing {field!r}")

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

        # An 'ok' record that produced nothing is not ok, and a hole or a failure that
        # carries maps is telling two different stories about the same run.
        if status == "ok" and not maps:
            raise RecordError("an 'ok' record must carry at least one map")
        if status in ("failed", "not_applicable") and maps:
            raise RecordError(f"a {status!r} record must not carry maps")

        return cls(
            target=doc["target"], software=doc["software"], version=doc["version"],
            model=doc["model"], status=status,
            environment=dict(doc.get("environment") or {}),
            timing=timing, maps=maps, error=error,
        )


def load_adapter_record(path: str | pathlib.Path) -> AdapterRecord:
    return AdapterRecord.from_dict(json.loads(pathlib.Path(path).read_text()))
