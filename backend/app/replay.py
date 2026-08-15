from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.engine import evaluate_entity_decisions
from app.models import DecisionState, ReplayDecisionDelta, ReplayRequest, ReplayResponse, SecurityEvent
from app.storage import (
    append_audit,
    get_decisions_from_state,
    get_events_from_state,
    load_state,
    ordered_events,
    persist_evaluation,
    save_state,
)


def _sort_timeline(state: dict[str, Any]) -> None:
    events = get_events_from_state(state)
    state["timeline"] = sorted(
        events.keys(),
        key=lambda event_id: events[event_id].timestamp,
    )


def ingest_event(event: SecurityEvent) -> tuple[DecisionState, dict[str, Any] | None]:
    """
    Ingest a security event. Returns (decision, conflict_info).
    conflict_info is set when exact duplicate content is detected (HTTP 409).
    """
    state = load_state()
    events_map = state.setdefault("events", {})
    existing_raw = events_map.get(event.event_id)

    if existing_raw is not None:
        existing = SecurityEvent.model_validate(existing_raw)
        if existing.model_dump(mode="json") == event.model_dump(mode="json"):
            return get_decisions_from_state(state)[event.event_id], {"type": "duplicate_exact"}
        events_map[event.event_id] = event.model_dump(mode="json")
        _sort_timeline(state)
    else:
        events_map[event.event_id] = event.model_dump(mode="json")
        timeline = state.setdefault("timeline", [])
        if event.event_id not in timeline:
            timeline.append(event.event_id)
        _sort_timeline(state)

    previous_decisions = get_decisions_from_state(state)
    ordered = ordered_events(state)
    is_late = existing_raw is not None and SecurityEvent.model_validate(existing_raw).timestamp != event.timestamp
    is_replay = is_late or _is_out_of_order(ordered, event)

    decisions = evaluate_entity_decisions(
        ordered,
        previous_decisions=previous_decisions,
        is_replay=is_replay,
    )

    audit_entries: list[dict[str, Any]] = [
        {
            "operation": "ingest",
            "event_id": event.event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "source": event.source,
                "is_replay": is_replay,
                "outcome": decisions[event.event_id].outcome.value,
            },
        }
    ]

    if is_replay:
        audit_entries.append(
            {
                "operation": "replay",
                "event_id": event.event_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "reason": "late_arrival_or_timeline_reorder",
                    "affected_events": list(decisions.keys()),
                },
            }
        )

    persist_evaluation(state, decisions, audit_entries)
    return decisions[event.event_id], None


def _is_out_of_order(ordered: list[SecurityEvent], incoming: SecurityEvent) -> bool:
    others = [event for event in ordered if event.event_id != incoming.event_id]
    if not others:
        return False
    latest = max(event.timestamp for event in others)
    return incoming.timestamp < latest


def manual_replay(request: ReplayRequest) -> ReplayResponse:
    state = load_state()
    events = get_events_from_state(state)
    previous = get_decisions_from_state(state)

    selected = [events[event_id] for event_id in request.event_ids if event_id in events]
    if not selected:
        return ReplayResponse(status="no_events", replayed_count=0, deltas=[])

    ordered = ordered_events(state)
    decisions = evaluate_entity_decisions(
        ordered,
        as_of=request.target_timestamp,
        previous_decisions=previous,
        is_replay=True,
    )

    deltas: list[ReplayDecisionDelta] = []
    for event_id in request.event_ids:
        if event_id not in decisions:
            continue
        revised = decisions[event_id]
        original = previous.get(event_id)
        if original is None or original.model_dump() != revised.model_dump():
            deltas.append(
                ReplayDecisionDelta(
                    event_id=event_id,
                    original=original,
                    revised=revised,
                )
            )

    audit_entry = {
        "operation": "manual_replay",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": {
            "event_ids": request.event_ids,
            "target_timestamp": request.target_timestamp.isoformat(),
            "delta_count": len(deltas),
        },
    }
    persist_evaluation(state, decisions, [audit_entry])
    return ReplayResponse(
        status="processed",
        replayed_count=len(deltas),
        deltas=deltas,
    )


def reset_storage() -> None:
    state = {"events": {}, "decisions": {}, "timeline": []}
    save_state(state)
    from app.storage import AUDIT_FILE

    AUDIT_FILE.write_text("[]", encoding="utf-8")
