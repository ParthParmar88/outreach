"""
The endpoints the web app calls: briefs, plans, runs, results.

Thin. Every one of these parses, delegates to `services.flow`, and
serialises. Business logic that creeps in here becomes untestable without
HTTP, which is why there is none.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from outreach import keywords as keyword_service
from outreach.schemas.web import (
    AmendIn,
    BriefIn,
    BriefOut,
    FeedbackIn,
    PlanOut,
    ReplyDraftIn,
    ReplyDraftOut,
    ResultOut,
    RunOut,
)
from outreach.services import flow

router = APIRouter(tags=["app"])


class SuggestIn(BaseModel):
    description: str = ""


@router.post("/keywords/suggest", response_model=list[str])
async def suggest_keywords(payload: SuggestIn) -> list[str]:
    """
    Keywords for what the user just described.

    Replaces the checked-in list the form used to ship with, which was
    correct for exactly one product. Returns an empty list rather than
    failing - an autocomplete that breaks the form is worse than one that
    offers nothing.
    """
    return await keyword_service.suggest(payload.description)


def _guard(exc: flow.FlowError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ---------------------------------------------------------------- briefs


@router.post("/briefs", response_model=BriefOut, status_code=status.HTTP_201_CREATED)
async def create_brief(payload: BriefIn) -> BriefOut:
    return flow.create_brief(payload)


@router.get("/briefs", response_model=list[BriefOut])
async def list_briefs() -> list[BriefOut]:
    return flow.list_briefs()


@router.post("/briefs/{brief_id}/plan", response_model=PlanOut)
async def compile_plan(brief_id: str) -> PlanOut:
    """
    Compile a brief into a plan, expanding its keywords.

    One LLM call, roughly two seconds. Every added term comes back marked
    `origin: "expansion"` with a reason, so the review screen can show what
    was added and why before anything is fetched.
    """
    try:
        return await flow.compile_plan(brief_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc


# ---------------------------------------------------------------- plans


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: str) -> PlanOut:
    try:
        return flow.get_plan(plan_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc


@router.post("/plans/{plan_id}/amend", response_model=PlanOut)
async def amend_plan(plan_id: str, payload: AmendIn) -> PlanOut:
    try:
        return flow.amend_plan(plan_id, payload.terms)
    except flow.FlowError as exc:
        raise _guard(exc) from exc


@router.post("/plans/{plan_id}/runs", response_model=RunOut, status_code=202)
async def start_run(plan_id: str, background: BackgroundTasks) -> RunOut:
    """
    Start a run and return immediately.

    202, not 200: the work has been accepted, not finished. Poll
    GET /runs/{id} or subscribe to its events.
    """
    try:
        run = flow.start_run(plan_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc

    background.add_task(flow.execute, run.id)
    return run


# ---------------------------------------------------------------- runs


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: str) -> RunOut:
    try:
        return flow.get_run(run_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc


@router.get("/runs/{run_id}/results", response_model=list[ResultOut])
async def get_results(run_id: str) -> list[ResultOut]:
    try:
        return flow.get_results(run_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """
    Server-sent events for live progress.

    Polls the in-memory run and pushes it on change. Crude, and correct for
    this stage: the frontend needs a stream, not a particular implementation
    of one, and this can become a Redis subscription without the client
    noticing.
    """

    async def stream():
        last = None
        for _ in range(600):  # ~5 minutes at 0.5s
            try:
                run = flow.get_run(run_id)
            except flow.FlowError:
                yield 'event: error\ndata: {"detail":"unknown run"}\n\n'
                return

            payload = run.model_dump(by_alias=True, mode="json")
            current = json.dumps(payload)
            if current != last:
                yield f"data: {current}\n\n"
                last = current

            if run.state in ("succeeded", "failed", "cancelled"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/export.csv")
async def export_csv(run_id: str) -> Response:
    try:
        results = flow.get_results(run_id)
    except flow.FlowError as exc:
        raise _guard(exc) from exc

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["rank", "score", "band", "intent", "domain", "title", "author",
         "url", "problem", "evidence", "created"]
    )
    for r in results:
        writer.writerow(
            [r.rank, r.score, r.band, r.intent or "", r.domain or "",
             r.conversation.title, r.conversation.author, r.conversation.url,
             r.problem, r.evidence_quote, r.conversation.created_at.date()]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}.csv"'},
    )


# ---------------------------------------------------------------- results


@router.post("/results/{result_id}/feedback", status_code=204)
async def feedback(result_id: str, payload: FeedbackIn) -> None:
    flow.record_feedback(result_id, payload.useful)


@router.post("/results/{result_id}/reply-draft", response_model=ReplyDraftOut)
async def reply_draft(result_id: str, payload: ReplyDraftIn) -> ReplyDraftOut:
    """Drafts only. A person edits and posts it themselves, always."""
    text, mentions = await flow.draft_reply(result_id, payload.allow_mention)
    return ReplyDraftOut(text=text, mentions_product=mentions)
