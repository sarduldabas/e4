"""Agent 10: red-team. Looks at the whole report like a sceptical committee member."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .knowledge import COMMITTEE_QUESTIONS, classify, i
from .section_analyst import Claim
from .util import clip, find_numbers, overlap, tokens

Lang = Literal["de", "en"]


class DraftSection(BaseModel):
    key: str
    title: str
    headline: str = ""
    claims: list[Claim] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    verified: bool = True


class RedTeamInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    committee: str | None = None
    decision_requested: str | None = None
    sections: list[DraftSection] = Field(default_factory=list)


class Challenge(BaseModel):
    section_key: str | None = None
    claim_id: str | None = None
    kind: Literal["question", "inconsistency", "gap", "weak_claim"]
    text: str
    severity: Literal["blocker", "warning", "info"] = "warning"


class RedTeamOutput(BaseModel):
    challenges: list[Challenge] = Field(default_factory=list)
    verdict: str = ""


class RedTeam(BaseAgent[RedTeamInput, RedTeamOutput]):
    id = "red-team"
    name = "Red team"
    stage = 2
    tier = "strong"
    description = "Reads the whole draft like a sceptical committee member: hard questions, gaps, inconsistencies."
    input_model = RedTeamInput
    output_model = RedTeamOutput
    system = """
You are a sceptical member of the committee reading this report before the meeting. Find what would embarrass the presenter.
- "question": the hard questions the committee will ask that the draft does not answer (max 6, the sharpest first).
- "inconsistency": two claims that contradict each other (different numbers for the same thing, a recommendation that does not follow
  from the analysis); name the claim ids in the text and set "claim_id" to one of them, with a "blocker" severity if the conflict is real.
- "gap": a section that is empty, thin, or lacks the decision, the cost, the risk owner or the timeline.
- "weak_claim": a claim with low confidence or without a figure where one is needed.
Use only the draft in the request. Be specific and brief; no praise. "verdict": one sentence on whether the report is ready for
the committee. Use "blocker" only for things that make the report misleading or unusable; the user can overrule everything else."""

    def rules(self, inp: RedTeamInput) -> RedTeamOutput:
        lang = inp.lang
        ch: list[Challenge] = []
        # 1. gaps
        for s in inp.sections:
            if not s.claims:
                ch.append(Challenge(section_key=s.key, kind="gap", severity="warning", text=(f"„{s.title}“ ist leer." if lang == "de" else f"“{s.title}” is empty.")))
            elif len(s.claims) == 1:
                ch.append(Challenge(section_key=s.key, kind="gap", severity="info", text=(f"„{s.title}“ stützt sich nur auf eine Aussage." if lang == "de" else f"“{s.title}” rests on a single claim.")))
            for c in s.claims:
                if c.confidence < 0.5:
                    ch.append(Challenge(section_key=s.key, claim_id=c.id, kind="weak_claim", severity="warning", text=(f"Geringe Sicherheit: {clip(c.text, 100)}" if lang == "de" else f"Low confidence: {clip(c.text, 100)}")))
        # 2. inconsistencies: same words, different number+unit
        facts = [(s, c, n) for s in inp.sections for c in s.claims for n in find_numbers(c.text) if n.unit]
        seen = set()
        for a in range(len(facts)):
            for b in range(a + 1, len(facts)):
                (s1, c1, n1), (s2, c2, n2) = facts[a], facts[b]
                if c1.id == c2.id and s1.key == s2.key or n1.unit != n2.unit or abs(n1.value - n2.value) < 1e-9:
                    continue
                t1, t2 = tokens(c1.text), tokens(c2.text)
                if overlap(t1, t2) >= 0.7 and overlap(t2, t1) >= 0.7 and (c1.id, c2.id, s1.key, s2.key) not in seen:
                    seen.add((c1.id, c2.id, s1.key, s2.key))
                    ch.append(Challenge(section_key=s2.key, claim_id=c2.id, kind="inconsistency", severity="warning",
                                        text=(f"Widerspruch: „{clip(c1.text, 70)}“ ({s1.title}) vs. „{clip(c2.text, 70)}“ ({s2.title})." if lang == "de" else f"Conflict: “{clip(c1.text, 70)}” ({s1.title}) vs. “{clip(c2.text, 70)}” ({s2.title}).")))
        # 3. committee questions for the topics present
        q = 0
        for s in inp.sections:
            tp = classify(s.title)
            if tp and tp[0] in COMMITTEE_QUESTIONS and q < 5:
                q += 1
                ch.append(Challenge(section_key=s.key, kind="question", severity="info", text=i(lang, COMMITTEE_QUESTIONS[tp[0]])))
        if not inp.decision_requested:
            ch.append(Challenge(kind="gap", severity="warning", text="Die gewünschte Entscheidung des Gremiums ist nicht genannt." if lang == "de" else "The decision requested from the committee is not stated."))
        unver = [s.title for s in inp.sections if not s.verified]
        if unver:
            ch.append(Challenge(kind="gap", severity="blocker", text=(f"Nicht geprüfte Abschnitte: {', '.join(unver)}." if lang == "de" else f"Sections not verified: {', '.join(unver)}.")))
        blockers = sum(1 for c in ch if c.severity == "blocker")
        verdict = ("Nicht bereit für das Gremium." if lang == "de" else "Not ready for the committee.") if blockers else ("Bereit, mit offenen Fragen." if lang == "de" else "Ready, with open questions.")
        return RedTeamOutput(challenges=ch, verdict=verdict)

    def clean(self, inp: RedTeamInput, out: RedTeamOutput) -> RedTeamOutput:
        keys = {s.key for s in inp.sections}
        claims = {(s.key, c.id) for s in inp.sections for c in s.claims}
        good = []
        for c in out.challenges:
            sk = c.section_key if c.section_key in keys else None
            cid = c.claim_id if (sk, c.claim_id) in claims else None
            if not c.text.strip():
                continue
            good.append(c.model_copy(update={"section_key": sk, "claim_id": cid, "text": clip(c.text, 300)}))
        # an unverified section is always a blocker, whatever the model thinks
        for s in inp.sections:
            if not s.verified and not any(c.section_key == s.key and c.severity == "blocker" for c in good):
                good.append(Challenge(section_key=s.key, kind="gap", severity="blocker", text=("Abschnitt nicht geprüft." if inp.lang == "de" else "Section not verified.")))
        return RedTeamOutput(challenges=good[:30], verdict=clip(out.verdict, 200))
