"""Committees and reports (the cases) on the database. Replaces the JSON store; same methods for the front end."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..db import Database
from ..models import Committee as CommitteeRow
from ..models import Report as ReportRow
from ..schemas import Committee, Report, ReportSummary
from ..seed import COMMITTEES, REPORTS


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y, %H:%M")


def _summary(r: ReportRow) -> dict:
    return dict(id=r.id, title=r.title, committee=r.committee, date=r.date, version=r.version, status=r.status, stage=r.stage, edited=_fmt(r.edited_at), people=r.people or [])


class ReportsService:
    def __init__(self, db: Database, on_delete=None):
        self.db = db
        self._on_delete = on_delete

    def seed(self) -> None:
        with self.db.session() as s:
            if s.query(CommitteeRow).count() == 0:
                for c in COMMITTEES:
                    s.add(CommitteeRow(id=c["id"], name=c["name"], date=c["date"], template=c["template"], has_report=c["has_report"]))
            if s.query(ReportRow).count() == 0:
                for r in REPORTS:
                    s.add(ReportRow(id=r["id"], title=r["title"], committee=r["committee"], committee_id=next((c["id"] for c in COMMITTEES if c["name"] == r["committee"]), None),
                                    date=r["date"], version=r["version"], version_no=int(r["version"].lstrip("v") or 1), status=r["status"], stage=r["stage"],
                                    state={1: "SETUP", 2: "FINDINGS_REVIEW", 3: "DECK_REVIEW"}.get(r["stage"], "SETUP"), people=r["people"], topic=r["title"]))

    def committees(self) -> list[Committee]:
        with self.db.session() as s:
            return [Committee(id=c.id, name=c.name, date=c.date, template=c.template, has_report=c.has_report) for c in s.query(CommitteeRow).all()]

    def committee(self, committee_id: str) -> Committee | None:
        return next((c for c in self.committees() if c.id == committee_id), None)

    def list_reports(self) -> list[ReportSummary]:
        with self.db.session() as s:
            return [ReportSummary(**_summary(r)) for r in s.query(ReportRow).order_by(ReportRow.created_at.desc(), ReportRow.id).all()]

    def get_report(self, report_id: str) -> Report | None:
        with self.db.session() as s:
            r = s.get(ReportRow, report_id)
            return Report(**_summary(r), workspace=r.workspace) if r else None

    def create_report(self, title: str, committee_id: str | None, lang: str = "de") -> Report:
        c = self.committee(committee_id) if committee_id else None
        rid = f"r-{uuid.uuid4().hex[:8]}"
        with self.db.session() as s:
            row = ReportRow(id=rid, title=title, committee_id=c.id if c else None, committee=c.name if c else "", date=c.date if c else "", people=["kw"], lang=lang, topic=title)
            s.add(row)
            s.flush()
            return Report(**_summary(row), workspace=None)

    def save_workspace(self, report_id: str, workspace: dict) -> Report | None:
        with self.db.session() as s:
            r = s.get(ReportRow, report_id)
            if not r:
                return None
            r.workspace = workspace
            r.edited_at = datetime.now(timezone.utc).replace(tzinfo=None)
            return Report(**_summary(r), workspace=r.workspace)

    def delete_report(self, report_id: str) -> bool:
        with self.db.session() as s:
            r = s.get(ReportRow, report_id)
            if not r:
                return False
            s.delete(r)
        if self._on_delete:
            self._on_delete(report_id)
        return True
