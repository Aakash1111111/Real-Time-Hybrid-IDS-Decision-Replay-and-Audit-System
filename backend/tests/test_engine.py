from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.engine import resolve_conflict, severity_rank
from app.models import DecisionOutcome, SecurityEvent


def _event(
    event_id: str,
    source: str,
    alert_level: str,
    confidence: float,
    entity_id: str = "entity-1",
) -> SecurityEvent:
    return SecurityEvent(
        event_id=event_id,
        timestamp=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        source=source,
        event_type="anomaly_alert" if source == "ai" else "network_alert",
        alert_level=alert_level,
        rule_id=f"{source.upper()}-1",
        confidence=confidence,
        event_data={"entity_id": entity_id},
    )


def test_agreement_alerted():
    ai = _event("ai-1", "ai", "high", 0.9)
    sig = _event("sig-1", "signature", "high", 0.85)
    decision = resolve_conflict([ai, sig], ai)
    assert decision.outcome == DecisionOutcome.ALERTED
    assert decision.reasoning == "AI and signature agreed"


def test_signature_higher_severity():
    ai = _event("ai-1", "ai", "low", 0.75)
    sig = _event("sig-1", "signature", "high", 0.4)
    decision = resolve_conflict([ai, sig], ai)
    assert decision.outcome == DecisionOutcome.ALERTED
    assert decision.reasoning == "signature higher severity"


def test_ai_higher_confidence_when_above_threshold():
    ai = _event("ai-1", "ai", "high", 0.9)
    sig = _event("sig-1", "signature", "medium", 0.5)
    decision = resolve_conflict([ai, sig], ai)
    assert decision.outcome == DecisionOutcome.ALERTED
    assert decision.reasoning == "AI higher confidence"


def test_low_ai_confidence_ignored():
    ai = _event("ai-1", "ai", "medium", 0.3)
    decision = resolve_conflict([ai], ai)
    assert decision.outcome == DecisionOutcome.IGNORED
    assert "Low AI confidence" in decision.reasoning


def test_severity_rank_order():
    assert severity_rank("high") > severity_rank("medium") > severity_rank("low")
