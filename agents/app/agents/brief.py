"""Agent: brief. Rates how well the author's brief is understood and what to ask next.

The engine (rules version, or the model version that falls back to it) lives in brief_agent.py / brief_llm.py and keeps its own
contract (BriefAssessRequest -> BriefAssessment, endpoint /v1/brief/assess). This class puts it into the registry next to the other agents, so it has the same
envelope (/v1/agents/brief/run), shows up in the same list and is audited the same way.
"""
from __future__ import annotations

from ..llm import LlmError
from ..schemas import BriefAssessment, BriefAssessRequest
from .brief_agent import BriefAgent
from .brief_llm import LlmBriefAgent
from .core import BaseAgent


class Brief(BaseAgent[BriefAssessRequest, BriefAssessment]):
    id = "brief"
    name = "Brief agent"
    stage = 1
    tier = "small"
    description = BriefAgent.description
    version = BriefAgent.version
    input_model = BriefAssessRequest
    output_model = BriefAssessment
    system = "Rates the brief. The model version is implemented in brief_llm.py (signals from the model, score computed in code)."

    def __init__(self) -> None:
        self._rules = BriefAgent()
        self._engine: BriefAgent | LlmBriefAgent = self._rules

    def bind(self, engine: "BriefAgent | LlmBriefAgent") -> None:
        """main.py hands over the engine it built from the settings (model version or rules version)."""
        self._engine = engine

    def rules(self, inp: BriefAssessRequest) -> BriefAssessment:
        return self._rules.assess(inp)

    def run_model(self, inp: BriefAssessRequest, llm):
        eng = self._engine
        if not isinstance(eng, LlmBriefAgent):
            return None if llm is None else (self._rules.assess(inp), {})
        out = eng.assess(inp)
        if out.agent.mode == "rules":  # the engine fell back by itself: report it like every other agent does
            raise LlmError(out.agent.note or "model not used")
        return out, dict(getattr(llm, "last_usage", None) or {})
