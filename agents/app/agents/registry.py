"""All agents of the solution, by id."""
from __future__ import annotations

from .asset_analyst import AssetAnalyst
from .asset_curator import AssetCurator
from .brief import Brief
from .core import BaseAgent
from .document_reader import DocumentReader
from .evidence_extractor import EvidenceExtractor
from .feedback_interpreter import FeedbackInterpreter
from .interviewer import Interviewer
from .red_team import RedTeam
from .section_analyst import SectionAnalyst
from .slide_editor import SlideEditor
from .slide_writer import SlideWriter
from .source_planner import SourcePlanner
from .source_screener import SourceScreener
from .storyline_architect import StorylineArchitect
from .template_analyst import TemplateAnalyst
from .verifier import Verifier
from .web_researcher import WebResearcher
from .web_search import WebSearch

AGENT_CLASSES: list[type[BaseAgent]] = [
    Brief, TemplateAnalyst, DocumentReader, Interviewer, SourcePlanner, SourceScreener, WebSearch, WebResearcher, EvidenceExtractor,
    AssetAnalyst, AssetCurator, SectionAnalyst, Verifier, RedTeam, StorylineArchitect, SlideWriter, SlideEditor, FeedbackInterpreter,
]


def build_registry() -> dict[str, BaseAgent]:
    return {a.id: a for a in (cls() for cls in AGENT_CLASSES)}
