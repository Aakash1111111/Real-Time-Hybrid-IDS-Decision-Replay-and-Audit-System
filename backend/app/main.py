from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.models import ProcessResponse, ReplayRequest, ReplayResponse, SecurityEvent
from app.replay import ingest_event, manual_replay
from app.storage import load_audit_log, load_state

app = FastAPI(
    title="Hybrid IDS Decision Replay and Audit System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/events", response_model=ProcessResponse)
async def post_event(request: Request) -> ProcessResponse:
    try:
        body = await request.json()
        event = SecurityEvent.model_validate(body)
    except ValidationError as exc:
        detail = _format_validation_error(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    decision, conflict = ingest_event(event)
    if conflict and conflict.get("type") == "duplicate_exact":
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate event payload for event_id={event.event_id}",
        )

    return ProcessResponse(status="processed", decision=decision)


@app.post("/replay", response_model=ReplayResponse)
async def post_replay(request: ReplayRequest) -> ReplayResponse:
    return manual_replay(request)


@app.get("/audit-trail")
async def get_audit_trail() -> dict[str, Any]:
    state = load_state()
    return {
        "audit_log": load_audit_log(),
        "current_state": state,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/decisions")
async def get_decisions() -> dict[str, Any]:
    state = load_state()
    return {"decisions": state.get("decisions", {}), "timeline": state.get("timeline", [])}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _format_validation_error(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        messages.append(f"{loc}: {error.get('msg')}")
    return "; ".join(messages)
