"""Agent: web-search. Searches the public web with the Foundry web search tool and returns a briefing per query plus the pages it cites."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from ..llm import LlmError
from .core import BaseAgent
from .source_planner import PlanSection

Lang = Literal["de", "en"]


class WebQuery(BaseModel):
    id: str
    query: str
    section_keys: list[str] = Field(default_factory=list)
    why: str = ""


class WebSearchInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    committee: str | None = None
    sections: list[PlanSection] = Field(default_factory=list)
    queries: list[WebQuery] = Field(default_factory=list, max_length=12)


class WebSource(BaseModel):
    url: str
    title: str = ""


class WebResult(BaseModel):
    query_id: str
    section_keys: list[str] = Field(default_factory=list)
    briefing: str  # the model's factual summary of what the pages say, with dates and figures
    sources: list[WebSource] = Field(default_factory=list)
    searched: list[str] = Field(default_factory=list)  # the queries the search tool actually ran


class WebSearchOutput(BaseModel):
    results: list[WebResult] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)  # query ids that returned nothing, with the reason in notes
    notes: str | None = None


class WebSearch(BaseAgent[WebSearchInput, WebSearchOutput]):
    id = "web-search"
    name = "Web search"
    stage = 2
    tier = "standard"
    description = "Searches the public web (Foundry web search tool) for external facts: market, suppliers, regulation, prices."
    input_model = WebSearchInput
    output_model = WebSearchOutput
    system = "Uses the model's web search tool, one search per query."  # not a JSON prompt: see run_model

    INSTRUCTIONS = {
        "de": ("Du recherchierst für einen Bericht an das Top-Management eines Automobilkonzerns. Suche im öffentlichen Web und antworte in sachlichem, "
               "formellem Deutsch (Sie-Form wo nötig) mit einem kompakten Briefing: konkrete Zahlen mit Einheit, Jahr und Quelle, Namen von Unternehmen und Produkten, "
               "Rechtsstand mit Datum. Gib an, was unsicher, widersprüchlich oder veraltet ist. Keine Spekulation, keine Werbung, keine Zahl ohne Quelle. "
               "Höchstens 280 Wörter. Nutze nur Ergebnisse, die zur Frage passen."),
        "en": ("You research for a report to the top management of an automotive group. Search the public web and answer in a factual, formal tone with a compact briefing: "
               "concrete figures with unit, year and source, company and product names, legal status with date. State what is uncertain, conflicting or outdated. "
               "No speculation, no advertising, no figure without a source. At most 280 words. Use only results that fit the question."),
    }

    def prompt(self, inp: WebSearchInput, q: WebQuery) -> str:
        titles = [s.title for s in inp.sections if s.key in q.section_keys]
        ctx = f"Thema des Berichts: {inp.topic}." if inp.lang == "de" else f"Topic of the report: {inp.topic}."
        sec = (" Betrifft die Abschnitte: " + "; ".join(titles) + ".") if inp.lang == "de" and titles else (" Relevant for the sections: " + "; ".join(titles) + ".") if titles else ""
        ask = "Recherchiere: " if inp.lang == "de" else "Research: "
        return f"{ctx}{sec}\n{ask}{q.query}" + (f" ({q.why})" if q.why else "")

    def run_model(self, inp: WebSearchInput, llm):
        if not hasattr(llm, "web_search") or not inp.queries:
            return None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        def one(q: WebQuery):
            try:
                res = llm.web_search(self.prompt(inp, q), instructions=self.INSTRUCTIONS[inp.lang], tier=self.tier)
                u = getattr(llm, "last_usage", None) or {}
                return q, res, u, None
            except LlmError as e:
                return q, None, {}, str(e)

        with ThreadPoolExecutor(max_workers=min(4, len(inp.queries))) as pool:
            done = list(pool.map(one, inp.queries))
        results, failed, errors = [], [], []
        for q, res, u, err in done:
            for k in usage:
                usage[k] += int(u.get(k, 0) or 0)
            if res is None:
                failed.append(q.id)
                errors.append(f"{q.id}: {err}")
                continue
            results.append(WebResult(query_id=q.id, section_keys=q.section_keys, briefing=res["text"], sources=[WebSource(**s) for s in res["sources"]], searched=res["queries"]))
        if not results and errors:
            raise LlmError("; ".join(errors)[:300])  # every search failed: let the runner report it (and fall back)
        return WebSearchOutput(results=results, failed=failed, notes="; ".join(errors)[:300] or None), usage

    def rules(self, inp: WebSearchInput) -> WebSearchOutput:
        return WebSearchOutput(results=[], failed=[q.id for q in inp.queries], notes="Web search needs the language model; nothing was searched.")

    def clean(self, inp: WebSearchInput, out: WebSearchOutput) -> WebSearchOutput:
        qs = {q.id: q for q in inp.queries}
        keys = {s.key for s in inp.sections}
        good = []
        for r in out.results:
            if r.query_id not in qs or not r.briefing.strip():
                continue
            seen, srcs = set(), []
            for s in r.sources:
                if s.url.lower().startswith(("http://", "https://")) and s.url not in seen:
                    seen.add(s.url)
                    srcs.append(s.model_copy(update={"title": s.title.strip()[:200]}))
            good.append(r.model_copy(update={"sources": srcs[:12], "section_keys": [k for k in r.section_keys if k in keys] or sorted(keys)}))
        return out.model_copy(update={"results": good, "failed": [i for i in out.failed if i in qs]})
