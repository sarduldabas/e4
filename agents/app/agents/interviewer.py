"""Agent 2: interviewer. Captures what the user says, checks what is still missing, asks the next question."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .util import clip, find_numbers, norm, overlap, pick, sentences, tokens

Lang = Literal["de", "en"]
DECISION_WORDS = ("approve", "decid", "recommend", "genehmig", "entscheid", "empfehl", "beschluss", "freigabe", "wir sollten", "we should")
RISK_WORDS = ("risk", "risiko", "delay", "verzug", "problem", "gefahr", "issue", "engpass", "shortage")


class InterviewSection(BaseModel):
    key: str
    title: str
    required_inputs: list[str] = Field(default_factory=list)


class Turn(BaseModel):
    role: Literal["user", "agent"]
    text: str


class KnownEvidence(BaseModel):
    label: str = ""
    statement: str
    section_key: str | None = None


class InterviewerInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    description: str = ""
    sections: list[InterviewSection] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)  # earlier turns, oldest first
    user_text: str = ""  # what the user just said or typed
    known_evidence: list[KnownEvidence] = Field(default_factory=list)  # what the sources already provide
    questions_asked: int = 0
    user_done: bool = False
    max_questions: int = 12


class Statement(BaseModel):
    kind: Literal["fact", "number", "decision", "preference", "risk"] = "fact"
    label: str
    statement: str
    value: float | None = None
    unit: str | None = None
    section_key: str | None = None


class Coverage(BaseModel):
    section_key: str
    required_input: str
    covered: bool


class NextQuestion(BaseModel):
    text: str
    section_key: str | None = None
    required_input: str | None = None


class InterviewerOutput(BaseModel):
    statements: list[Statement] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)
    next_question: NextQuestion | None = None
    done: bool = False
    done_reason: Literal["all_covered", "user_done", "question_limit"] | None = None
    open_points: list[str] = Field(default_factory=list)


class Interviewer(BaseAgent[InterviewerInput, InterviewerOutput]):
    id = "interviewer"
    name = "Interviewer"
    stage = 1
    tier = "strong"
    description = "Captures what the user says, judges what is still missing per section, asks the next question."
    input_model = InterviewerInput
    output_model = InterviewerOutput
    system = """
You interview a colleague who is preparing a committee report. They talk or type freely; you listen, record, and ask only
what is still missing.
1. "statements": every concrete fact, number, decision, preference or risk in "user_text" (not in earlier turns), one
   statement each, close to the user's words. "label" = 2-5 words naming it. Fill "value" and "unit" when it is a number.
   "section_key": the section it belongs to, or null.
2. "coverage": for EVERY required input of EVERY section: covered = true only if the description, the user's turns or
   "known_evidence" already contain a concrete answer to it.
3. "next_question": the single most useful open question, one short sentence in the user's language, for the first section
   with an uncovered required input. Do not repeat a question that was already asked and answered. Null when done.
4. Stop ("done": true) when every required input is covered ("all_covered"), when "user_done" is true ("user_done"), or when
   "questions_asked" has reached "max_questions" ("question_limit"). Missing inputs then become "open_points": short
   phrases ("Section: what is missing"). They are visible to the user and do not block anything.
Be brief and kind. One question at a time. Never ask for something already in known_evidence."""

    def rules(self, inp: InterviewerInput) -> InterviewerOutput:
        lang = inp.lang
        statements: list[Statement] = []
        sec_tokens = {s.key: tokens(" ".join([s.title, *s.required_inputs])) for s in inp.sections}
        for sent in sentences(inp.user_text):
            if len(sent) < 15:
                continue
            nums = find_numbers(sent)
            low = sent.lower()
            kind = "number" if nums else "decision" if any(w in low for w in DECISION_WORDS) else "risk" if any(w in low for w in RISK_WORDS) else "fact"
            st = tokens(sent)
            best = max(sec_tokens.items(), key=lambda kv: overlap(kv[1], st), default=(None, set()))
            statements.append(Statement(
                kind=kind, label=clip(" ".join(sent.split()[:5]), 40), statement=sent,
                value=nums[0].value if nums else None, unit=nums[0].unit if nums else None,
                section_key=best[0] if best[0] and overlap(best[1], st) > 0.1 else None))

        corpus = tokens(" ".join([inp.description, inp.user_text, *(t.text for t in inp.turns if t.role == "user"), *(e.statement for e in inp.known_evidence)]))
        coverage = [Coverage(section_key=s.key, required_input=r, covered=overlap(tokens(r), corpus) >= 0.5) for s in inp.sections for r in s.required_inputs]
        open_ = [c for c in coverage if not c.covered]
        title = {s.key: s.title for s in inp.sections}

        done_reason = ("user_done" if inp.user_done else "all_covered" if not open_ else "question_limit" if inp.questions_asked >= inp.max_questions else None)
        nq = None
        if not done_reason and open_:
            c = open_[0]
            nq = NextQuestion(
                text=pick(lang, f"Zu „{title[c.section_key]}“ fehlt noch: {c.required_input}. Was können Sie dazu sagen?",
                          f"For “{title[c.section_key]}” I still need: {c.required_input}. What can you tell me?"),
                section_key=c.section_key, required_input=c.required_input)
        return InterviewerOutput(
            statements=statements, coverage=coverage, next_question=nq, done=bool(done_reason), done_reason=done_reason,
            open_points=[f"{title[c.section_key]}: {c.required_input}" for c in open_] if done_reason else [])

    def clean(self, inp: InterviewerInput, out: InterviewerOutput) -> InterviewerOutput:
        keys = {s.key for s in inp.sections}
        valid = {(s.key, r) for s in inp.sections for r in s.required_inputs}
        title = {s.key: s.title for s in inp.sections}
        statements = [s.model_copy(update={"section_key": s.section_key if s.section_key in keys else None, "label": clip(s.label, 60), "statement": norm(s.statement)})
                      for s in out.statements if norm(s.statement)]
        got = {(c.section_key, c.required_input): c.covered for c in out.coverage if (c.section_key, c.required_input) in valid}
        coverage = [Coverage(section_key=k, required_input=r, covered=got.get((k, r), False)) for k, r in sorted(valid, key=lambda x: [(s.key, r) for s in inp.sections for r in s.required_inputs].index(x))]
        open_ = [c for c in coverage if not c.covered]
        reason = ("user_done" if inp.user_done else "question_limit" if inp.questions_asked >= inp.max_questions else "all_covered" if not open_ else None)
        nq = out.next_question if not reason else None
        if nq and nq.section_key not in keys:
            nq = nq.model_copy(update={"section_key": None, "required_input": None})
        if not reason and not nq and open_:  # the model forgot to ask: fall back to the rules question
            nq = self.rules(inp).next_question
        points = out.open_points if reason and out.open_points else ([f"{title[c.section_key]}: {c.required_input}" for c in open_] if reason else [])
        return InterviewerOutput(statements=statements, coverage=coverage, next_question=nq, done=bool(reason), done_reason=reason, open_points=points[:12])
