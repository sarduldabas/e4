"""Shared plumbing of the orchestrator: context, state machine, ledger helpers, payload builders."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import Settings
from ..core.connectors import KINDS, LocalFolderConnector, WebFetcher
from ..core.storage import FileStore
from ..db import Database
from ..models import Calculation, Claim, Event, Evidence, Flag, OutlineSection, Report, SectionDraft, Source
from .jobs import JobRunner
from .runner import AgentsRunner

# ---------------------------------------------------------------- state machine
STATES = ["SETUP", "OUTLINE_REVIEW", "COLLECTING", "ANALYSING", "FINDINGS_REVIEW", "GENERATING", "DECK_REVIEW", "FINAL", "FEEDBACK"]
STAGE_OF = {"SETUP": 1, "OUTLINE_REVIEW": 1, "COLLECTING": 2, "ANALYSING": 2, "FINDINGS_REVIEW": 2, "GENERATING": 3, "DECK_REVIEW": 3, "FINAL": 3, "FEEDBACK": 3}
TRANSITIONS = {
    "SETUP": {"OUTLINE_REVIEW"},
    "OUTLINE_REVIEW": {"OUTLINE_REVIEW", "COLLECTING"},
    "COLLECTING": {"ANALYSING", "OUTLINE_REVIEW"},  # a failed collection goes back so the user can retry
    "ANALYSING": {"FINDINGS_REVIEW", "COLLECTING"},
    "FINDINGS_REVIEW": {"FINDINGS_REVIEW", "GENERATING", "COLLECTING", "ANALYSING"},
    "GENERATING": {"DECK_REVIEW", "FINDINGS_REVIEW"},
    "DECK_REVIEW": {"DECK_REVIEW", "FINAL", "FEEDBACK", "GENERATING"},
    "FINAL": {"FEEDBACK"},
    "FEEDBACK": {"FEEDBACK", "COLLECTING", "ANALYSING", "FINDINGS_REVIEW", "GENERATING", "DECK_REVIEW"},
}


class StateError(Exception):
    """The requested step is not allowed in the report's current state."""


class NotFound(Exception):
    pass


class Blocked(Exception):
    """Something the user must resolve first (for example open blocker flags)."""

    def __init__(self, message: str, items: list[dict] | None = None):
        super().__init__(message)
        self.items = items or []


@dataclass
class Context:
    db: Database
    store: FileStore
    runner: AgentsRunner
    jobs: JobRunner
    settings: Settings
    connectors: dict[str, LocalFolderConnector] = field(default_factory=dict)
    web: WebFetcher | None = None

    @classmethod
    def build(cls, db, store, runner, jobs, settings) -> "Context":
        root = Path(settings.data_dir) / "connectors"
        conns = {k: LocalFolderConnector(k, root / k) for k in KINDS}
        for k in KINDS:
            conns[k].root.mkdir(parents=True, exist_ok=True)
        return cls(db, store, runner, jobs, settings, conns, WebFetcher(settings.allow_web))


def get_report(s: Session, rid: str) -> Report:
    r = s.get(Report, rid)
    if not r:
        raise NotFound(rid)
    return r


def set_state(s: Session, r: Report, new: str, **why) -> None:
    if new != r.state and new not in TRANSITIONS[r.state]:
        raise StateError(f"cannot go from {r.state} to {new}")
    old = r.state
    r.state, r.stage = new, STAGE_OF[new]
    if old != new:
        log_event(s, r.id, "state", **{"from": old, "to": new, **why})


def require_state(r: Report, *allowed: str) -> None:
    if r.state not in allowed:
        raise StateError(f"this step is not possible in state {r.state} (allowed: {', '.join(allowed)})")


def log_event(s: Session, rid: str, kind: str, **payload) -> None:
    s.add(Event(report_id=rid, kind=kind, payload=payload))


# ---------------------------------------------------------------- ledger readers
def outline(s: Session, rid: str, included_only: bool = True) -> list[OutlineSection]:
    q = s.query(OutlineSection).filter(OutlineSection.report_id == rid)
    if included_only:
        q = q.filter(OutlineSection.included.is_(True))
    return q.order_by(OutlineSection.position).all()


def open_blockers(s: Session, rid: str, version_no: int) -> list[Flag]:
    return s.query(Flag).filter(Flag.report_id == rid, Flag.version_no == version_no, Flag.status == "open", Flag.severity == "blocker").all()


def source_label(src: Source | None, locator: str = "") -> str:
    if not src:
        return ""
    return f"{src.title}, {locator}" if locator else src.title


def evidence_refs(s: Session, rid: str, section_key: str, limit: int = 40) -> list[dict]:
    rows = (s.query(Evidence).filter(Evidence.report_id == rid, Evidence.status == "active", Evidence.section_key.in_([section_key, "_general"]))
            .all())
    rows.sort(key=lambda e: (e.origin != "user", e.value is None, -e.confidence))
    srcs = {x.id: x for x in s.query(Source).filter(Source.report_id == rid).all()}
    out = []
    for e in rows[:limit]:
        label = "Ihre Angabe" if e.origin == "user" else source_label(srcs.get(e.source_id), e.locator)
        out.append({"id": e.id, "kind": e.kind, "statement": e.statement, "quote": e.quote, "value": e.value, "unit": e.unit, "entity": e.entity, "period": e.period, "source": label, "user_provided": e.origin == "user"})
    return out


def claim_payload(c: Claim) -> dict:
    return {"id": c.id, "text": c.text, "kind": c.kind, "evidence_ids": c.evidence_ids, "calc_ids": c.calc_ids, "confidence": c.confidence}


def calc_payload(c: Calculation) -> dict:
    return {"id": c.id, "label": c.label, "formula": c.formula, "value": c.value if c.value is not None else 0.0, "unit": c.unit, "inputs": c.inputs}


def current_claims(s: Session, rid: str, version_no: int, section_key: str | None = None, statuses: tuple[str, ...] | None = None) -> list[Claim]:
    q = s.query(Claim).filter(Claim.report_id == rid, Claim.version_no == version_no)
    if section_key:
        q = q.filter(Claim.section_key == section_key)
    if statuses:
        q = q.filter(Claim.status.in_(statuses))
    return q.order_by(Claim.section_key, Claim.position).all()


def draft_of(s: Session, rid: str, section_key: str, version_no: int) -> SectionDraft | None:
    return s.query(SectionDraft).filter_by(report_id=rid, section_key=section_key, version_no=version_no).first()


_NUM = re.compile(r"\d[\d.,]*")


def numbers_in(text: str) -> set[str]:
    return {re.sub(r"[.,]+$", "", m) for m in _NUM.findall(text or "")}
