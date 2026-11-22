"""Brief agent, language-model version.

Same contract as the rules agent (BriefAssessRequest -> BriefAssessment). What changes is who understands the text:

  * The model reads the brief and returns *signals*: topic, committee, date, how well the text explains the case,
    which questions are already settled, a 2-3 line summary, up to three hints and the questions worth asking.
  * The score itself is still computed here with the same transparent formula as the rules agent, so it is stable
    and explainable. The model only supplies the inputs (and the description quality, 0..1).
  * The rules agent runs first and stays the safety net: on a timeout, an error or an unusable answer the user gets
    the rules result (agent.mode = "rules", agent.note says why) instead of an error.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import date, datetime

from pydantic import BaseModel, Field, ValidationError

from ..llm import LlmClient, LlmError
from ..schemas import AgentInfo, BreakdownItem, BriefAssessment, BriefAssessRequest, Question, Strength, Understood
from . import extract
from .brief_agent import (
    MAX_QUESTIONS,
    QUESTION_ORDER,
    W_ANSWER,
    W_COMMITTEE,
    W_DATE,
    W_DESCRIPTION,
    W_MATERIAL,
    W_SOURCES,
    W_TOPIC,
    BriefAgent,
)
from .prompts import BRIEF_SYSTEM
from .texts import BREAKDOWN, LABELS

log = logging.getLogger("agents.brief")

MAX_TEXT_CHARS = 8000  # the model never sees more than this of the user's text
MAX_ITEMS = 40  # files and links listed to the model
LLM_COOLDOWN_SECONDS = 30  # after a failed model call, use the rules agent for a while instead of waiting again


class _LlmQuestion(BaseModel):
    key: str
    text: str | None = None


class LlmSignals(BaseModel):
    """What the model must return. Lenient on purpose: bad fields are dropped, not fatal."""

    topic: str | None = None
    committee: str | None = None
    date: str | None = None
    description_quality: float = 0.0
    decision_clear: bool = False
    favourite_clear: bool = False
    summary: str | None = None
    hints: list[str] = Field(default_factory=list)
    questions: list[_LlmQuestion] = Field(default_factory=list)


def _clean(text: str | None, limit: int) -> str | None:
    t = " ".join((text or "").split())
    if not t:
        return None
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _valid_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
    except ValueError:
        return None


def _committee_name(value: str | None, preset: str | None) -> str | None:
    v = _clean(value, 60)
    if v:
        by_id = extract.COMMITTEES.get(v.lower())
        if by_id:
            return by_id[0]
        return extract.detect_committee(v, None) or v
    return extract.detect_committee("", preset)


class LlmBriefAgent:
    name = "brief"
    description = "Reads the brief with a language model, scores it, says what is missing and asks up to three optional cross-questions."
    version = "0.2.0"

    def __init__(self, llm: LlmClient, rules: BriefAgent | None = None, today: date | None = None, cache_size: int = 128):
        self.llm = llm
        self.rules = rules or BriefAgent(today=today)
        self._today = today
        self._cache: OrderedDict[str, BriefAssessment] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._down_until = 0.0

    # ------------------------------------------------------------------ public
    def assess(self, req: BriefAssessRequest) -> BriefAssessment:
        base = self.rules.assess(req)  # cheap, and the fallback if anything below goes wrong
        key = hashlib.sha256(req.model_dump_json().encode()).hexdigest()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit.model_copy(deep=True)
        if time.monotonic() < self._down_until:
            return self._fallback(base, "model temporarily skipped after an earlier failure")
        try:
            signals = self._ask(req)
            result = self._merge(req, base, signals)
        except (LlmError, ValidationError) as e:
            self._down_until = time.monotonic() + LLM_COOLDOWN_SECONDS
            log.warning("LLM brief agent fell back to rules: %s", e)
            return self._fallback(base, str(e))
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result.model_copy(deep=True)

    # ------------------------------------------------------------------ model call
    def _ask(self, req: BriefAssessRequest) -> LlmSignals:
        today = self._today or date.today()
        payload = {
            "lang": req.lang,
            "today": today.strftime("%d.%m.%Y"),
            "brief": {
                "text": (req.text or "")[:MAX_TEXT_CHARS],
                "typed_by_user": {k: v for k, v in req.overrides.model_dump().items() if v},
                "committee_picked_on_home_screen": req.preset_committee,
                "files": [{"name": f.name, "kind": f.kind, "status": f.status} for f in req.files[:MAX_ITEMS]],
                "links": req.links[:MAX_ITEMS],
                "search_also_in": [k for k, on in req.connectors.items() if on],
                "answers_given": {k: v for k, v in req.answers.items() if v},
            },
        }
        data = self.llm.complete_json(BRIEF_SYSTEM, json.dumps(payload, ensure_ascii=False))
        return LlmSignals.model_validate(data)

    # ------------------------------------------------------------------ combine model signals with the formula
    def _merge(self, req: BriefAssessRequest, base: BriefAssessment, sig: LlmSignals) -> BriefAssessment:
        lang = req.lang
        o = req.overrides  # what the user typed always wins
        topic = o.topic or _clean(sig.topic, 90)
        committee = o.committee or _committee_name(sig.committee, req.preset_committee)
        when = o.date or _valid_date(sig.date)

        ready = [f for f in req.files if f.status == "ready"]
        items = len(ready) + len(req.links)
        sources = sum(1 for on in req.connectors.values() if on)
        words = extract.word_count(req.text or "")
        quality = 0.0 if words < 4 else min(1.0, max(0.0, float(sig.description_quality)))

        questions = self._questions(req, base, sig)
        answered = sum(1 for q in questions if q.answer)
        unanswered = len(questions) - answered

        def item(key: str, points: float, max_: float) -> BreakdownItem:
            return BreakdownItem(key=key, label=BREAKDOWN[key][lang], points=round(points, 2), max=round(max_, 2))

        breakdown = [
            item("topic", W_TOPIC if topic else 0, W_TOPIC),
            item("committee", W_COMMITTEE if committee else 0, W_COMMITTEE),
            item("date", W_DATE if when else 0, W_DATE),
            item("description", quality * W_DESCRIPTION, W_DESCRIPTION),
            item("material", min(items, 6) / 6 * W_MATERIAL, W_MATERIAL),
            item("sources", min(sources, 5) / 5 * W_SOURCES, W_SOURCES),
            item("answers", min(answered, 3) * W_ANSWER, 3 * W_ANSWER),
        ]
        score = round(min(100, sum(b.points for b in breakdown)))
        label_key = BriefAgent._label_key(score)

        # "description" counts as missing while the model finds the case thinly explained.
        missing = BriefAgent._missing(topic, committee, when, 40 if quality < 0.5 else 80, items, req.connectors.get("outlook", False), unanswered)
        rule_hints = [BriefAgent._hint(lang, k, unanswered) for k in missing][:3]
        hints = [h for h in (_clean(h, 140) for h in sig.hints) if h][:3] or rule_hints
        summary = _clean(sig.summary, 420) or base.strength.summary

        already_clear = [k for k, v in (("decision", sig.decision_clear), ("favourite", sig.favourite_clear)) if v and not req.answers.get(BriefAgent._qid(k))]
        return BriefAssessment(
            agent=AgentInfo(name=self.name, version=self.version, mode="llm", model=self.llm.model),
            lang=lang,
            strength=Strength(score=score, label_key=label_key, label=LABELS[label_key][lang], summary=summary,
                              hints=hints, missing=missing, breakdown=breakdown),
            understood=Understood(topic=topic, committee=committee, date=when),
            questions=questions,
            already_clear=already_clear,
            can_start=bool(topic) or len(req.files) > 0,
        )

    def _questions(self, req: BriefAssessRequest, base: BriefAssessment, sig: LlmSignals) -> list[Question]:
        """Answered questions always stay. The model's picks follow, then rules questions top up to at least two."""
        text = req.text or ""
        precedent_file = extract.find_precedent_file(req.files)
        asked: dict[str, str | None] = {}  # key -> model's wording
        for q in sig.questions:
            if q.key in QUESTION_ORDER and q.key not in asked:
                asked[q.key] = _clean(q.text, 160)
        answered_keys = [k for k in QUESTION_ORDER if req.answers.get(BriefAgent._qid(k))]
        picked = answered_keys + [k for k in asked if k not in answered_keys]
        picked = picked[:MAX_QUESTIONS]
        if len(picked) < 2:  # never leave the card (almost) empty
            qid_to_key = {BriefAgent._qid(k): k for k in QUESTION_ORDER}
            for q in base.questions:
                k = qid_to_key[q.id]
                if k not in picked and len(picked) < 2:
                    picked.append(k)
        picked.sort(key=QUESTION_ORDER.index)

        out: list[Question] = []
        for k in picked:
            q = self.rules._question(k, req.lang, req, precedent_file, text)
            if asked.get(k) and not q.answer:
                q = q.model_copy(update={"text": asked[k]})
            out.append(q)
        return out

    # ------------------------------------------------------------------ fallback
    def _fallback(self, base: BriefAssessment, reason: str) -> BriefAssessment:
        info = AgentInfo(name=self.name, version=self.rules.version, mode="rules", note=_clean(f"model not used: {reason}", 200))
        return base.model_copy(update={"agent": info})
