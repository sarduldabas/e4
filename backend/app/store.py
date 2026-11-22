"""Report storage: a JSON file with a lock. Good enough for the prototype and for a single instance.
Replace with a database (Postgres / Cosmos DB) behind the same four methods when the product grows.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .schemas import Committee, Report, ReportSummary
from .seed import COMMITTEES, REPORTS


class Store:
    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "reports.json"
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({r["id"]: r for r in REPORTS})

    # -- file helpers
    def _read(self) -> dict[str, dict]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, dict]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._path)

    # -- committees (static for now; later from the calendar / committee master data)
    def committees(self) -> list[Committee]:
        return [Committee(**c) for c in COMMITTEES]

    def committee(self, committee_id: str) -> Committee | None:
        return next((c for c in self.committees() if c.id == committee_id), None)

    # -- reports
    def list_reports(self) -> list[ReportSummary]:
        with self._lock:
            return [ReportSummary(**{k: v for k, v in r.items() if k != "workspace"}) for r in self._read().values()]

    def get_report(self, report_id: str) -> Report | None:
        with self._lock:
            r = self._read().get(report_id)
        return Report(**r) if r else None

    def create_report(self, title: str, committee_id: str | None) -> Report:
        c = self.committee(committee_id) if committee_id else None
        r = Report(
            id=f"r-{uuid.uuid4().hex[:8]}", title=title, committee=c.name if c else "", date=c.date if c else "",
            version="v1", status="Draft", stage=1, edited=_now(), people=["kw"], workspace=None,
        )
        with self._lock:
            data = self._read()
            data[r.id] = r.model_dump()
            self._write(data)
        return r

    def save_workspace(self, report_id: str, workspace: dict) -> Report | None:
        with self._lock:
            data = self._read()
            if report_id not in data:
                return None
            data[report_id]["workspace"] = workspace
            data[report_id]["edited"] = _now()
            self._write(data)
            return Report(**data[report_id])

    def delete_report(self, report_id: str) -> bool:
        with self._lock:
            data = self._read()
            if report_id not in data:
                return False
            del data[report_id]
            self._write(data)
            return True


def _now() -> str:
    return datetime.now().strftime("%d.%m.%Y, %H:%M")
