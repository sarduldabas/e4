from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import Committee, Report, ReportCreate, ReportSummary

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/committees", response_model=list[Committee])
def committees(request: Request):
    return request.app.state.store.committees()


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(request: Request):
    return request.app.state.store.list_reports()


@router.post("/reports", response_model=Report, status_code=201)
def create_report(body: ReportCreate, request: Request):
    store = request.app.state.store
    if body.committee_id and not store.committee(body.committee_id):
        raise HTTPException(422, f"Unknown committee '{body.committee_id}'")
    return store.create_report(body.title, body.committee_id)


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, request: Request):
    r = request.app.state.store.get_report(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.put("/reports/{report_id}/workspace", response_model=Report,
            summary="Save the front end's brief / analysis / deck state (autosave)")
def save_workspace(report_id: str, workspace: dict, request: Request):
    r = request.app.state.store.save_workspace(report_id, workspace)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: str, request: Request):
    if not request.app.state.store.delete_report(report_id):
        raise HTTPException(404, "Report not found")
    return Response(status_code=204)
