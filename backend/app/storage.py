from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models import DecisionState, SecurityEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "state.json"
AUDIT_FILE = DATA_DIR / "audit_log.json"

_lock = threading.Lock()


def _default_state() -> dict[str, Any]:
    return {"events": {}, "decisions": {}, "timeline": []}


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        STATE_FILE.write_text(json.dumps(_default_state(), indent=2), encoding="utf-8")
    if not AUDIT_FILE.exists():
        AUDIT_FILE.write_text("[]", encoding="utf-8")


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump(mode="json"))
    if hasattr(obj, "value"):
        return obj.value
    return obj


def load_state() -> dict[str, Any]:
    _ensure_data_files()
    with _lock:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    _ensure_data_files()
    with _lock:
        STATE_FILE.write_text(json.dumps(_serialize(state), indent=2), encoding="utf-8")


def load_audit_log() -> list[dict[str, Any]]:
    _ensure_data_files()
    with _lock:
        return json.loads(AUDIT_FILE.read_text(encoding="utf-8"))


def append_audit(entry: dict[str, Any]) -> None:
    _ensure_data_files()
    with _lock:
        log = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
        log.append(_serialize(entry))
        AUDIT_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")


def get_events_from_state(state: dict[str, Any]) -> dict[str, SecurityEvent]:
    events: dict[str, SecurityEvent] = {}
    for event_id, payload in state.get("events", {}).items():
        events[event_id] = SecurityEvent.model_validate(payload)
    return events


def get_decisions_from_state(state: dict[str, Any]) -> dict[str, DecisionState]:
    decisions: dict[str, DecisionState] = {}
    for event_id, payload in state.get("decisions", {}).items():
        decisions[event_id] = DecisionState.model_validate(payload)
    return decisions


def ordered_events(state: dict[str, Any]) -> list[SecurityEvent]:
    events = get_events_from_state(state)
    timeline = state.get("timeline", [])
    return [events[event_id] for event_id in timeline if event_id in events]


def persist_evaluation(
    state: dict[str, Any],
    decisions: dict[str, DecisionState],
    audit_entries: list[dict[str, Any]],
) -> None:
    state["decisions"] = {
        event_id: decision.model_dump(mode="json")
        for event_id, decision in decisions.items()
    }
    save_state(state)
    for entry in audit_entries:
        append_audit(entry)
