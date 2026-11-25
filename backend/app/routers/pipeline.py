"""The report workflow: files, outline, interview, research, findings, deck, feedback. All state lives in the ledger."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/reports/{rid}", tags=["workflow"])


def orch(request: Request):
    return request.app.state.orchestrator


class CaseIn(BaseModel):
    title: str | None = None
    topic: str | None = None
    description: str | None = None
    decision_requested: str | None = None
    lang: str | None = Field(default=None, pattern="^(de|en)$")
    links: list[str] | None = None
    use_web: bool | None = None
    committee_id: str | None = None


class SectionIn(BaseModel):
    key: str | None = None
    title: str
    purpose: str = ""
    layout: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    suggested_slides: int = 1
    included: bool = True


class TurnIn(BaseModel):
    text: str = Field("", max_length=8000)
    done: bool = False


class ClaimPatch(BaseModel):
    text: str | None = Field(default=None, max_length=1500)
    status: str | None = None


class FlagResolve(BaseModel):
    resolution: str
    note: str | None = Field(default=None, max_length=1000)


class SlidePatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    bullets: list[str] | None = None
    spec: dict | None = None  # the whole slide as the page shows it (see /api/v1/slide-layouts)


class ReviseIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)


class SlideAddIn(BaseModel):
    after: str | None = None
    layout: str = "bullets"


class SlideMoveIn(BaseModel):
    index: int = Field(ge=0)


class OrderIn(BaseModel):
    sections: list[str]


class FeedbackIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    selected_slide_id: str | None = None


class RerunIn(BaseModel):
    sections: list[str] | None = None


# --- case and files
@router.get("/case", summary="State, counts and the latest job of a report")
def get_case(rid: str, request: Request):
    return orch(request).case(rid)


@router.put("/case", summary="Brief: topic, description, decision requested, language, links")
def put_case(rid: str, body: CaseIn, request: Request):
    return orch(request).set_case(rid, body.model_dump())


@router.get("/files")
def files(rid: str, request: Request):
    return orch(request).files(rid)


@router.post("/files", status_code=201, summary="Upload the template (role=template), a source, or the previous report")
async def upload(rid: str, request: Request, file: UploadFile = File(...), role: str = Form("source")):
    data = await file.read()
    return orch(request).add_file(rid, role, file.filename or "file", data)


@router.delete("/files/{fid}", status_code=204)
def delete_file(rid: str, fid: str, request: Request):
    orch(request).delete_file(rid, fid)
    return Response(status_code=204)


@router.get("/sources", summary="What the research found, and what was selected or rejected")
def sources(rid: str, request: Request):
    return orch(request).sources(rid)


# --- checkpoint 1
@router.post("/outline/propose", summary="Template-analyst: propose the outline")
def propose(rid: str, request: Request):
    return orch(request).propose_outline(rid)


@router.get("/outline")
def get_outline(rid: str, request: Request):
    return orch(request).get_outline(rid)


@router.put("/outline", summary="Save the user's edited outline")
def put_outline(rid: str, sections: list[SectionIn], request: Request):
    return orch(request).update_outline(rid, [s.model_dump() for s in sections])


@router.get("/interview")
def get_interview(rid: str, request: Request):
    return orch(request).get_interview(rid)


@router.post("/interview/turn", summary="Interviewer: say or type something (empty text = ask the first question)")
def turn(rid: str, body: TurnIn, request: Request):
    return orch(request).interview(rid, body.text, body.done)


@router.post("/outline/approve", status_code=202, summary="Checkpoint 1: approve the outline; starts research and analysis")
def approve_outline(rid: str, request: Request):
    return {"job_id": orch(request).approve_outline(rid)}


@router.post("/research/rerun", status_code=202)
def rerun(rid: str, request: Request, body: RerunIn | None = None):
    return {"job_id": orch(request).rerun_research(rid, body.sections if body else None)}


@router.get("/jobs/{job_id}")
def job(rid: str, job_id: str, request: Request):
    return orch(request).job(rid, job_id)


# --- checkpoint 2
@router.get("/findings", summary="Sections with claims, evidence, calculations and flags")
def findings(rid: str, request: Request):
    return orch(request).findings(rid)


@router.patch("/claims/{claim_id}", summary="Edit (verified again), approve or reject a claim")
def patch_claim(rid: str, claim_id: str, body: ClaimPatch, request: Request):
    return orch(request).update_claim(rid, claim_id, body.text, body.status)


@router.post("/flags/{flag_id}/resolve")
def resolve(rid: str, flag_id: str, body: FlagResolve, request: Request):
    return orch(request).resolve_flag(rid, flag_id, body.resolution, body.note)


@router.post("/findings/approve", status_code=202, summary="Checkpoint 2: approve findings; blocked while blocker flags are open")
def approve_findings(rid: str, request: Request):
    return {"job_id": orch(request).approve_findings(rid)}


# --- checkpoint 3
@router.get("/deck")
def deck(rid: str, request: Request):
    return orch(request).deck(rid)


@router.patch("/deck/slides/{slide_id}")
def patch_slide(rid: str, slide_id: str, body: SlidePatch, request: Request):
    return orch(request).update_slide(rid, slide_id, body.title, body.bullets, body.spec)


@router.post("/deck/slides", status_code=201, summary="Add a slide after another one")
def add_slide(rid: str, body: SlideAddIn, request: Request):
    return orch(request).add_slide(rid, body.after, body.layout)


@router.post("/deck/slides/{slide_id}/revise", summary="Slide-editor: carry out a reviewer's comment on this slide")
def revise_slide(rid: str, slide_id: str, body: ReviseIn, request: Request):
    return orch(request).revise_slide(rid, slide_id, body.instruction)


@router.post("/deck/slides/{slide_id}/undo", summary="Back to the slide before its last change")
def undo_slide(rid: str, slide_id: str, request: Request):
    return orch(request).undo_slide(rid, slide_id)


@router.put("/deck/slides/{slide_id}/position", status_code=204, summary="Move a slide to position `index` (0-based)")
def move_slide(rid: str, slide_id: str, body: SlideMoveIn, request: Request):
    orch(request).move_slide(rid, slide_id, body.index)


@router.delete("/deck/slides/{slide_id}", status_code=204)
def delete_slide(rid: str, slide_id: str, request: Request):
    orch(request).delete_slide(rid, slide_id)


@router.get("/research-plan", summary="The research planner's decisions per round and what each round found")
def research_plan(rid: str, request: Request):
    return orch(request).research_plan(rid)


@router.get("/assets", summary="The asset library: all pictures, charts and tables found in the sources, with the analyst's description and the curator's choice")
def assets(rid: str, request: Request):
    return orch(request).asset_library(rid)


class AssetPatch(BaseModel):
    user_choice: str | None = None
    section_key: str | None = None
    caption: str | None = None


@router.patch("/assets/{asset_id}", summary="Use this asset (user_choice=use), never use it (skip), or hand the decision back to the curator (null)")
def patch_asset(rid: str, asset_id: str, body: AssetPatch, request: Request):
    return orch(request).patch_asset(rid, asset_id, body.model_dump(exclude_unset=True))


@router.get("/assets/{asset_id}", summary="An image of the report (used by slides)")
def asset(rid: str, asset_id: str, request: Request):
    data, mime = orch(request).asset_bytes(rid, asset_id)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@router.put("/deck/order")
def order(rid: str, body: OrderIn, request: Request):
    return {"sections": orch(request).reorder_slides(rid, body.sections)}


@router.get("/deck/download", summary="The PowerPoint file of the current version")
def download(rid: str, request: Request):
    name, data = orch(request).deck_file(rid)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/deck/finalize", summary="Checkpoint 3: the deck is final")
def finalize(rid: str, request: Request):
    return orch(request).finalize(rid)


# --- feedback -> next version
@router.post("/feedback", summary="Feedback-interpreter: turn free text into changes (nothing is changed yet)")
def feedback(rid: str, body: FeedbackIn, request: Request):
    return orch(request).submit_feedback(rid, body.text, body.selected_slide_id)


@router.post("/feedback/{feedback_id}/apply", status_code=202, summary="Start the next version with these changes")
def apply_feedback(rid: str, feedback_id: str, request: Request):
    return {"job_id": orch(request).apply_feedback(rid, feedback_id)}


# --- audit
@router.get("/events", summary="Decisions and state changes")
def events(rid: str, request: Request):
    return orch(request).events(rid)


@router.get("/agent-runs/summary", summary="Calls, tokens and time per agent, model vs. rules")
def agent_runs_summary(rid: str, request: Request):
    return orch(request).agent_summary(rid)


@router.get("/agent-runs", summary="Every agent call of this report (add io=true for inputs and outputs)")
def agent_runs(rid: str, request: Request, io: bool = Query(False)):
    return orch(request).agent_runs(rid, io)
