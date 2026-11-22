"""Brief agent (stage 1).

Reads what the user has said and attached so far and answers three things for the two cards on the Brief screen:
  1. Brief strength: a score, a label and two to three short lines on what is clear and what is missing.
  2. What would help most: at most three concrete hints.
  3. Quick questions: up to three optional cross-questions about what is still unclear.

The scoring is deliberately simple and transparent (see `breakdown` in the response). The implementation here
is rule based; the contract (BriefAssessRequest -> BriefAssessment) stays the same if a language model takes over.
"""
from __future__ import annotations

from datetime import date

from ..schemas import (
    AgentInfo,
    BreakdownItem,
    BriefAssessment,
    BriefAssessRequest,
    Lang,
    Option,
    Question,
    Strength,
    Understood,
)
from . import extract
from .texts import BREAKDOWN, HINTS, LABELS, PARTS, QUESTIONS, SUMMARY

# Points per signal. They add up to 100.
W_TOPIC, W_COMMITTEE, W_DATE = 15, 10, 8
W_DESCRIPTION = 17  # reaches full points at 80 words
W_MATERIAL = 28  # reaches full points at 6 documents or links
W_SOURCES = 6  # reaches full points at 5 connected sources
W_ANSWER = 16 / 3  # per answered quick question, three of them
MAX_QUESTIONS = 3

# Order in which questions are asked when several are open.
QUESTION_ORDER = ["decision", "favourite", "precedent", "time"]


class BriefAgent:
    name = "brief"
    description = "Scores the brief, says what is missing and asks up to three optional cross-questions."
    version = "0.1.0"

    def __init__(self, today: date | None = None):
        self._today = today

    # ------------------------------------------------------------------ public
    def assess(self, req: BriefAssessRequest) -> BriefAssessment:
        lang: Lang = req.lang
        today = self._today or date.today()
        text = req.text or ""
        o = req.overrides

        topic = o.topic or extract.infer_topic(text)
        committee = o.committee or extract.detect_committee(text, req.preset_committee)
        when = o.date or extract.parse_date(text, today)
        understood = Understood(topic=topic, committee=committee, date=when)

        ready_files = [f for f in req.files if f.status == "ready"]
        reading = len(req.files) - len(ready_files)
        items = len(ready_files) + len(req.links)
        sources = sum(1 for on in req.connectors.values() if on)
        words = extract.word_count(text)

        questions, already_clear = self._questions(req, lang)
        answered = [q for q in questions if q.answer]
        unanswered = [q for q in questions if not q.answer]

        breakdown = self._breakdown(lang, topic, committee, when, words, items, sources, len(answered))
        score = round(min(100, sum(b.points for b in breakdown)))
        label_key = self._label_key(score)

        missing = self._missing(topic, committee, when, words, items, req.connectors.get("outlook", False), len(unanswered))
        hints = [self._hint(lang, key, len(unanswered)) for key in missing][:3]

        strength = Strength(
            score=score,
            label_key=label_key,
            label=LABELS[label_key][lang],
            summary=self._summary(lang, topic, committee, when, items, reading, sources, hints),
            hints=hints,
            missing=missing,
            breakdown=breakdown,
        )
        return BriefAssessment(
            agent=AgentInfo(name=self.name, version=self.version, mode="rules"),
            lang=lang,
            strength=strength,
            understood=understood,
            questions=questions,
            already_clear=already_clear,
            can_start=bool(topic) or len(req.files) > 0,
        )

    # ------------------------------------------------------------------ scoring
    @staticmethod
    def _label_key(score: int) -> str:
        if score < 40:
            return "getting_started"
        if score < 70:
            return "good_basis"
        if score < 90:
            return "strong_brief"
        return "excellent_brief"

    @staticmethod
    def _breakdown(lang, topic, committee, when, words, items, sources, n_answered) -> list[BreakdownItem]:
        def item(key, points, max_):
            return BreakdownItem(key=key, label=BREAKDOWN[key][lang], points=round(points, 2), max=round(max_, 2))

        return [
            item("topic", W_TOPIC if topic else 0, W_TOPIC),
            item("committee", W_COMMITTEE if committee else 0, W_COMMITTEE),
            item("date", W_DATE if when else 0, W_DATE),
            item("description", min(words, 80) / 80 * W_DESCRIPTION, W_DESCRIPTION),
            item("material", min(items, 6) / 6 * W_MATERIAL, W_MATERIAL),
            item("sources", min(sources, 5) / 5 * W_SOURCES, W_SOURCES),
            item("answers", min(n_answered, 3) * W_ANSWER, 3 * W_ANSWER),
        ]

    # ------------------------------------------------------------------ what is missing
    @staticmethod
    def _missing(topic, committee, when, words, items, outlook_on, n_unanswered) -> list[str]:
        """Keys of what would help, most useful first."""
        out: list[str] = []
        if not topic:
            out.append("topic")
        if not committee and not when:
            out.append("committee_date")
        elif not committee:
            out.append("committee")
        elif not when:
            out.append("date")
        if words < 40:
            out.append("description")
        if items < 3:
            out.append("material")
        if n_unanswered:
            out.append("answers")
        if not outlook_on:
            out.append("outlook")
        return out

    @staticmethod
    def _hint(lang: Lang, key: str, n_unanswered: int) -> str:
        if key == "answers":
            return HINTS["answers_one" if n_unanswered == 1 else "answers_many"][lang].format(n=n_unanswered)
        return HINTS[key][lang]

    # ------------------------------------------------------------------ the 2-3 lines
    @staticmethod
    def _summary(lang: Lang, topic, committee, when, items, reading, sources, hints) -> str:
        have = [PARTS[k][lang] for k, v in (("topic", topic), ("committee", committee), ("date", when)) if v]
        lack = [PARTS[k][lang] for k, v in (("topic", topic), ("committee", committee), ("date", when)) if not v]
        if not lack:
            line1 = SUMMARY["clear_all"][lang]
        elif not have:
            line1 = SUMMARY["clear_none"][lang]
        else:
            line1 = SUMMARY["clear_some"][lang].format(have=", ".join(have), missing=", ".join(lack))

        if items == 0 and reading == 0:
            line2 = SUMMARY["material_none"][lang]
        elif reading:
            line2 = SUMMARY["material_reading"][lang].format(n=items)
        else:
            src = "" if sources == 0 else (SUMMARY["material_src_one"][lang] if sources == 1 else SUMMARY["material_src"][lang].format(c=sources))
            line2 = SUMMARY["material_one" if items == 1 else "material_many"][lang].format(n=items, src=src)

        line3 = SUMMARY["next"][lang].format(hint=hints[0]) if hints else SUMMARY["ready"][lang]
        return " ".join([line1, line2, line3])

    # ------------------------------------------------------------------ cross-questions
    def _questions(self, req: BriefAssessRequest, lang: Lang) -> tuple[list[Question], list[str]]:
        text = req.text or ""
        precedent_file = extract.find_precedent_file(req.files)
        clear: dict[str, bool] = {
            # Things the user's own words already settle: no need to ask.
            "decision": extract.infer_decision(text) is not None,
            "favourite": extract.states_favourite(text),
        }
        already_clear = [k for k, v in clear.items() if v and not req.answers.get(self._qid(k))]

        def relevant(key: str) -> bool:
            if req.answers.get(self._qid(key)):
                return True  # answered questions never disappear
            if clear.get(key):
                return False
            if key == "precedent":
                return True
            if key == "time":
                return True
            return True

        chosen = [k for k in QUESTION_ORDER if relevant(k)]
        # Answered ones first (they must stay), then the rest by priority, capped at three.
        answered_first = [k for k in chosen if req.answers.get(self._qid(k))]
        rest = [k for k in chosen if k not in answered_first]
        picked = (answered_first + rest)[:MAX_QUESTIONS]
        picked.sort(key=QUESTION_ORDER.index)

        questions = [self._question(k, lang, req, precedent_file, text) for k in picked]
        return questions, already_clear

    @staticmethod
    def _qid(key: str) -> str:
        return {"decision": "q1", "favourite": "q2", "precedent": "q3", "time": "q4"}[key]

    def _question(self, key: str, lang: Lang, req: BriefAssessRequest, precedent_file: str | None, text: str) -> Question:
        spec = QUESTIONS[key]
        qtext = spec["text"][lang]
        if key == "precedent":
            if precedent_file:
                qtext = spec["text_file"][lang].format(name=precedent_file)
            elif extract.mentions_precedent(text):
                qtext = spec["text_mention"][lang]
        qid = self._qid(key)
        valid = {oid for oid, _ in spec["options"]}
        answer = req.answers.get(qid)
        return Question(
            id=qid,
            text=qtext,
            options=[Option(id=oid, label=label[lang]) for oid, label in spec["options"]],
            answer=answer if answer in valid else None,
        )
