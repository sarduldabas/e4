"""The ledger: every table of the case workspace.

A report IS a case. Everything an agent ever saw or produced about it lives in these tables or in the file store
(uploads, parsed text, images, decks), keyed by the report id. Agents hold no state.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _id(prefix: str):
    return mapped_column(String(32), primary_key=True, default=lambda: new_id(prefix))


class Committee(Base):
    __tablename__ = "committees"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[str] = mapped_column(String(10), default="")
    template: Mapped[str] = mapped_column(String(200), default="")
    has_report: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    committee_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    committee: Mapped[str] = mapped_column(String(200), default="")
    date: Mapped[str] = mapped_column(String(10), default="")
    version: Mapped[str] = mapped_column(String(10), default="v1")  # label shown to users
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    stage: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="SETUP")
    lang: Mapped[str] = mapped_column(String(2), default="de")
    topic: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    decision_requested: Mapped[str | None] = mapped_column(Text, nullable=True)
    people: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[list] = mapped_column(JSON, default=list)  # public web links named in the brief
    use_web: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)  # web research is on for every report; the author may switch it off
    workspace: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the front end's own autosaved state
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FileRow(Base):
    __tablename__ = "files"
    id: Mapped[str] = _id("f")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # template | source | prior_report
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16), default="")
    key: Mapped[str] = mapped_column(String(400))  # storage key
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    info: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # what the reader found: pages, warnings, quality (filled when read)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Source(Base):
    """A document or web page the report may draw on (found by a connector, uploaded, or fetched)."""
    __tablename__ = "sources"
    id: Mapped[str] = _id("s")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="files")  # connector kind
    title: Mapped[str] = mapped_column(String(300))
    ref: Mapped[str] = mapped_column(String(600), default="")  # path or url
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modified: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="candidate")  # candidate|selected|rejected|parsed|failed
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    section_keys: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(String(200), default="")
    duplicate_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parsed_key: Mapped[str | None] = mapped_column(String(400), nullable=True)  # parsed text in the file store
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    info: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # reading result: quality, warnings, stats, document properties, profile
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class OutlineSection(Base):
    __tablename__ = "outline_sections"
    __table_args__ = (UniqueConstraint("report_id", "key"),)
    id: Mapped[str] = _id("o")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(400), default="")
    layout: Mapped[str | None] = mapped_column(String(120), nullable=True)
    required_inputs: Mapped[list] = mapped_column(JSON, default=list)
    suggested_slides: Mapped[int] = mapped_column(Integer, default=1)
    origin: Mapped[str] = mapped_column(String(10), default="agent")  # agent | user
    included: Mapped[bool] = mapped_column(Boolean, default=True)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    id: Mapped[str] = _id("t")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(6))
    text: Mapped[str] = mapped_column(Text)
    section_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Evidence(Base):
    """One finding with its quote and locator. Origin 'user' = said by the report author in the interview."""
    __tablename__ = "evidence"
    id: Mapped[str] = _id("e")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(60), index=True)
    origin: Mapped[str] = mapped_column(String(10), default="document")  # document | web | user | analysis
    source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="fact")
    statement: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text, default="")
    locator: Mapped[str] = mapped_column(String(300), default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity: Mapped[str | None] = mapped_column(String(120), nullable=True)  # what the figure belongs to: an option, a supplier, a plant
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)  # when it applies: 2026, Q3 2026, "per year"
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Calculation(Base):
    __tablename__ = "calculations"
    id: Mapped[str] = _id("c")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(60))
    ref: Mapped[str] = mapped_column(String(20))  # the analyst's id ("c1"), unique per section and run
    label: Mapped[str] = mapped_column(String(200))
    formula: Mapped[str] = mapped_column(String(300))
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)  # variable -> evidence id
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = _id("k")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(60), index=True)
    ref: Mapped[str] = mapped_column(String(20))  # the analyst's id ("k1")
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="fact")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)  # evidence.id
    calc_ids: Mapped[list] = mapped_column(JSON, default=list)  # calculations.id
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft|verified|flagged|approved|rejected
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    carried_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SectionDraft(Base):
    __tablename__ = "section_drafts"
    __table_args__ = (UniqueConstraint("report_id", "section_key", "version_no"),)
    id: Mapped[str] = _id("d")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(60))
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    headline: Mapped[str] = mapped_column(Text, default="")
    charts: Mapped[list] = mapped_column(JSON, default=list)
    open_points: Mapped[list] = mapped_column(JSON, default=list)
    rounds: Mapped[int] = mapped_column(Integer, default=1)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = _id("a")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(8))  # image | table | chart
    caption: Mapped[str] = mapped_column(String(300), default="")
    key: Mapped[str | None] = mapped_column(String(400), nullable=True)  # image file in the store
    table: Mapped[list | None] = mapped_column(JSON, nullable=True)  # rows, for tables
    context: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)
    # asset library (filled when the picture is looked at by the asset-analyst)
    origin: Mapped[str | None] = mapped_column(String(12), nullable=True)  # document | web | crop
    locator: Mapped[str | None] = mapped_column(String(200), nullable=True)  # page / slide / picture number in the source
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the picture this one was cropped from
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # chart | diagram | photo | screenshot | table_image | scan | logo | decorative | other
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    legibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(10), nullable=True)  # use | redraw | discard (the analyst's advice)
    chart: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # data read from a chart: type, title, unit, labels, series
    section_hints: Mapped[list | None] = mapped_column(JSON, nullable=True)
    analysed: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    user_choice: Mapped[str | None] = mapped_column(String(6), nullable=True)  # use | skip: what the user decided, wins over the curator
    sha: Mapped[str | None] = mapped_column(String(40), nullable=True)  # content hash, so the same picture is stored once
    rights: Mapped[str | None] = mapped_column(String(200), nullable=True)  # origin note for web pictures (check the right to use before publishing)


class Flag(Base):
    __tablename__ = "flags"
    id: Mapped[str] = _id("g")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    claim_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    origin: Mapped[str] = mapped_column(String(12))  # verifier | red_team | system
    kind: Mapped[str] = mapped_column(String(14), default="issue")
    severity: Mapped[str] = mapped_column(String(8), default="warning")  # blocker | warning | info
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | resolved
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # fixed | rejected | accepted | dismissed
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Slide(Base):
    __tablename__ = "slides"
    id: Mapped[str] = _id("sl")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    section_key: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    bullets: Mapped[list] = mapped_column(JSON, default=list)  # [{text, claim_ids}]  (claims.id)
    chart: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    layout: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the slide as shown AND exported: layout, title, blocks (see core/slides)
    history: Mapped[list | None] = mapped_column(JSON, nullable=True)  # earlier specs of this slide, newest last (undo)
    kind: Mapped[str] = mapped_column(String(12), default="content")  # title | summary | content | decision | sources | changes


class Deck(Base):
    __tablename__ = "decks"
    id: Mapped[str] = _id("dk")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    key: Mapped[str] = mapped_column(String(400))
    slide_count: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[list] = mapped_column(JSON, default=list)  # "changes since previous version"
    storyline: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the executive storyline the deck follows
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DeckSnapshot(Base):
    """What a section-level AI change replaced (slides, claims, calculations, drafts of the sections), so that it can be undone."""
    __tablename__ = "deck_snapshots"
    id: Mapped[str] = _id("sn")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = _id("j")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # outline | collect | analyse | generate | feedback
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued|running|done|failed
    progress: Mapped[dict] = mapped_column(JSON, default=dict)  # {"step": "...", "done": 3, "total": 7, "log": [...]}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentRun(Base):
    """Audit trail of every agent call: what went in, what came out, how, how long."""
    __tablename__ = "agent_runs"
    id: Mapped[str] = _id("ar")
    report_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(40), index=True)
    mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(8), default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Event(Base):
    """Decisions and state changes: who approved what, when. Never edited."""
    __tablename__ = "events"
    id: Mapped[str] = _id("ev")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = _id("fb")
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    selected_slide_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    interpreted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="new")  # new | planned | applied
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
