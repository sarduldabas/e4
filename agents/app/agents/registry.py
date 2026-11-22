"""All agents of the solution, by id."""
from __future__ import annotations

from .asset_curator import AssetCurator
from .core import BaseAgent
from .evidence_extractor import EvidenceExtractor
from .feedback_interpreter import FeedbackInterpreter
from .interviewer import Interviewer
from .red_team import RedTeam
from .section_analyst import SectionAnalyst
from .slide_writer import SlideWriter
from .source_planner import SourcePlanner
from .source_screener import SourceScreener
from .template_analyst import TemplateAnalyst
from .verifier import Verifier
from .web_researcher import WebResearcher

AGENT_CLASSES: list[type[BaseAgent]] = [
    TemplateAnalyst, Interviewer, SourcePlanner, SourceScreener, WebResearcher, EvidenceExtractor,
    AssetCurator, SectionAnalyst, Verifier, RedTeam, SlideWriter, FeedbackInterpreter,
]


def build_registry() -> dict[str, BaseAgent]:
    return {a.id: a for a in (cls() for cls in AGENT_CLASSES)}
