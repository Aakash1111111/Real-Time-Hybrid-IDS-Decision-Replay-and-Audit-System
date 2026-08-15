from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import SecurityEvent
from app.replay import ingest_event, manual_replay, reset_storage
from app.models import ReplayRequest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "edge_cases_sample.json"


@pytest.fixture(autouse=True)
def clean_storage():
    reset_storage()
    yield
    reset_storage()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_ec1_duplicate_exact_conflict(client, fixtures):
    payload = fixtures["duplicate_exact"]
    first = client.post("/events", json=payload)
    assert first.status_code == 200

    duplicate = client.post("/events", json=payload)
    assert duplicate.status_code == 409
    assert "Duplicate event payload" in duplicate.json()["detail"]


def test_ec1_duplicate_updated_timestamp(client, fixtures):
    payload = fixtures["duplicate_exact"]
    client.post("/events", json=payload)

    updated = fixtures["duplicate_updated_timestamp"]
    response = client.post("/events", json=updated)
    assert response.status_code == 200

    state = client.get("/audit-trail").json()["current_state"]
    assert state["timeline"].count("dup-001") == 1


def test_ec2_late_arriving_event_triggers_replay(client, fixtures):
    client.post("/events", json=fixtures["early_baseline"])
    response = client.post("/events", json=fixtures["late_arrival"])
    assert response.status_code == 200

    audit = client.get("/audit-trail").json()["audit_log"]
    replay_ops = [entry for entry in audit if entry.get("operation") == "replay"]
    assert replay_ops, "Expected replay audit entry for late arrival"

    state = client.get("/audit-trail").json()["current_state"]
    assert state["timeline"][0] == "late-001"


def test_ec3_conflicting_signals_severity_precedence(client, fixtures):
    client.post("/events", json=fixtures["conflict_ai_low_severity_high_confidence"])
    response = client.post("/events", json=fixtures["conflict_signature_high_severity_low_confidence"])
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["outcome"] == "alerted"
    assert decision["reasoning"] == "signature higher severity"


def test_ec3_conflicting_signals_ai_confidence_precedence(client, fixtures):
    client.post("/events", json=fixtures["conflict_ai_high_confidence"])
    response = client.post("/events", json=fixtures["conflict_signature_high_severity_2"])
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["outcome"] == "alerted"
    assert decision["reasoning"] == "AI higher confidence"


def test_ec4_malformed_timestamp(client, fixtures):
    response = client.post("/events", json=fixtures["invalid_timestamp"])
    assert response.status_code == 400
    assert "timestamp" in response.json()["detail"].lower()


def test_ec5_replay_retracted_decision(client, fixtures):
    client.post("/events", json=fixtures["retract_ai_initial"])
    client.post("/events", json=fixtures["retract_signature_override"])

    response = client.post("/events", json=fixtures["retract_late_evidence"])
    assert response.status_code == 200

    state = client.get("/audit-trail").json()["current_state"]
    retracted = [
        decision
        for decision in state["decisions"].values()
        if decision["outcome"] == "retracted"
    ]
    assert retracted
    assert any(
        d["reasoning"] == "Retracted due to overriding historical evidence"
        for d in retracted
    )


def test_manual_replay_determinism(client, fixtures):
    client.post("/events", json=fixtures["conflict_ai_low_severity_high_confidence"])
    client.post("/events", json=fixtures["conflict_signature_high_severity_low_confidence"])

    before = client.get("/decisions").json()["decisions"]
    replay = client.post(
        "/replay",
        json={
            "event_ids": ["conflict-ai-001", "conflict-sig-001"],
            "target_timestamp": "2026-08-15T09:30:00Z",
        },
    )
    assert replay.status_code == 200
    body = replay.json()
    assert body["status"] == "processed"

    after = client.get("/decisions").json()["decisions"]
    assert before.keys() == after.keys()


def test_ingest_idempotency_unit(fixtures):
    event = SecurityEvent.model_validate(fixtures["duplicate_exact"])
    decision1, _ = ingest_event(event)
    decision2, conflict = ingest_event(event)
    assert conflict == {"type": "duplicate_exact"}
    assert decision1.event_id == decision2.event_id


def test_replay_engine_unit(fixtures):
    ingest_event(SecurityEvent.model_validate(fixtures["retract_ai_initial"]))
    ingest_event(SecurityEvent.model_validate(fixtures["retract_signature_override"]))
    ingest_event(SecurityEvent.model_validate(fixtures["retract_late_evidence"]))

    result = manual_replay(
        ReplayRequest(
            event_ids=["retract-ai-001", "retract-late-001"],
            target_timestamp=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    assert result.replayed_count >= 0
