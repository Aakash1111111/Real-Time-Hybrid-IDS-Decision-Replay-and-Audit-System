from __future__ import annotations

from datetime import datetime, timezone

from app.models import DecisionOutcome, DecisionState, SecurityEvent

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
AI_CONFIDENCE_THRESHOLD = 0.70
LOW_AI_CONFIDENCE = 0.50
HIGH_AI_CONFIDENCE = 0.85


def severity_rank(level: str) -> int:
    return SEVERITY_RANK[level]


def _best_event(events: list[SecurityEvent], source: str) -> SecurityEvent | None:
    matches = [event for event in events if event.source == source]
    if not matches:
        return None
    return max(
        matches,
        key=lambda event: (severity_rank(event.alert_level), event.confidence),
    )


def _would_alert(event: SecurityEvent) -> bool:
    if event.source == "ai" and event.confidence < LOW_AI_CONFIDENCE:
        return False
    return severity_rank(event.alert_level) >= 1


def _has_invalidating_evidence(entity_events: list[SecurityEvent]) -> bool:
    for event in entity_events:
        if event.event_data.get("benign"):
            return True
        if event.event_data.get("override") and event.source == "signature" and event.alert_level == "low":
            return True
    return False


def resolve_conflict(
    entity_events: list[SecurityEvent],
    primary_event: SecurityEvent,
    decision_timestamp: datetime | None = None,
) -> DecisionState:
    """Deterministic conflict resolution for a single entity/session cluster."""
    ai_event = _best_event(entity_events, "ai")
    signature_event = _best_event(entity_events, "signature")
    timestamp = decision_timestamp or primary_event.timestamp

    if _has_invalidating_evidence(entity_events):
        rank = severity_rank(primary_event.alert_level)
        return DecisionState(
            event_id=primary_event.event_id,
            decision_timestamp=timestamp,
            outcome=DecisionOutcome.IGNORED,
            reasoning="Retracted due to overriding historical evidence",
            confidence_score=primary_event.confidence,
            severity_rank=rank,
        )

    if ai_event and signature_event:
        ai_rank = severity_rank(ai_event.alert_level)
        sig_rank = severity_rank(signature_event.alert_level)

        ai_agrees = _would_alert(ai_event)
        sig_agrees = _would_alert(signature_event)

        if ai_agrees and sig_agrees and ai_event.alert_level == signature_event.alert_level:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.ALERTED,
                reasoning="AI and signature agreed",
                confidence_score=max(ai_event.confidence, signature_event.confidence),
                severity_rank=max(ai_rank, sig_rank),
            )

        if ai_event.confidence >= HIGH_AI_CONFIDENCE:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.ALERTED,
                reasoning="AI higher confidence",
                confidence_score=ai_event.confidence,
                severity_rank=max(ai_rank, sig_rank),
            )

        if sig_rank > ai_rank:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.ALERTED,
                reasoning="signature higher severity",
                confidence_score=signature_event.confidence,
                severity_rank=sig_rank,
            )

        if ai_event.confidence >= signature_event.confidence or ai_event.confidence >= AI_CONFIDENCE_THRESHOLD:
            if ai_rank >= sig_rank:
                return DecisionState(
                    event_id=primary_event.event_id,
                    decision_timestamp=timestamp,
                    outcome=DecisionOutcome.ALERTED,
                    reasoning="AI higher confidence",
                    confidence_score=ai_event.confidence,
                    severity_rank=ai_rank,
                )

        if ai_event.confidence < LOW_AI_CONFIDENCE:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.IGNORED,
                reasoning="Low AI confidence without signature support",
                confidence_score=ai_event.confidence,
                severity_rank=ai_rank,
            )

        return DecisionState(
            event_id=primary_event.event_id,
            decision_timestamp=timestamp,
            outcome=DecisionOutcome.ALERTED,
            reasoning="signature higher severity",
            confidence_score=signature_event.confidence,
            severity_rank=sig_rank,
        )

    if signature_event:
        return DecisionState(
            event_id=primary_event.event_id,
            decision_timestamp=timestamp,
            outcome=DecisionOutcome.ALERTED,
            reasoning="signature higher severity",
            confidence_score=signature_event.confidence,
            severity_rank=severity_rank(signature_event.alert_level),
        )

    if ai_event:
        ai_rank = severity_rank(ai_event.alert_level)
        if ai_event.confidence < LOW_AI_CONFIDENCE:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.IGNORED,
                reasoning="Low AI confidence without signature support",
                confidence_score=ai_event.confidence,
                severity_rank=ai_rank,
            )
        if ai_event.confidence >= AI_CONFIDENCE_THRESHOLD or ai_rank >= 2:
            return DecisionState(
                event_id=primary_event.event_id,
                decision_timestamp=timestamp,
                outcome=DecisionOutcome.ALERTED,
                reasoning="AI higher confidence",
                confidence_score=ai_event.confidence,
                severity_rank=ai_rank,
            )
        return DecisionState(
            event_id=primary_event.event_id,
            decision_timestamp=timestamp,
            outcome=DecisionOutcome.IGNORED,
            reasoning="Low AI confidence without signature support",
            confidence_score=ai_event.confidence,
            severity_rank=ai_rank,
        )

    suricata_event = _best_event(entity_events, "suricata")
    if suricata_event:
        rank = severity_rank(suricata_event.alert_level)
        outcome = DecisionOutcome.ALERTED if rank >= 2 else DecisionOutcome.IGNORED
        return DecisionState(
            event_id=primary_event.event_id,
            decision_timestamp=timestamp,
            outcome=outcome,
            reasoning="signature higher severity" if outcome == DecisionOutcome.ALERTED else "Low AI confidence without signature support",
            confidence_score=suricata_event.confidence,
            severity_rank=rank,
        )

    return DecisionState(
        event_id=primary_event.event_id,
        decision_timestamp=timestamp,
        outcome=DecisionOutcome.IGNORED,
        reasoning="Low AI confidence without signature support",
        confidence_score=primary_event.confidence,
        severity_rank=severity_rank(primary_event.alert_level),
    )


def apply_retraction(
    previous: DecisionState | None,
    current: DecisionState,
    is_replay: bool,
) -> DecisionState:
    if (
        is_replay
        and previous is not None
        and previous.outcome == DecisionOutcome.ALERTED
        and current.outcome == DecisionOutcome.IGNORED
    ):
        return DecisionState(
            event_id=current.event_id,
            decision_timestamp=current.decision_timestamp,
            outcome=DecisionOutcome.RETRACTED,
            reasoning="Retracted due to overriding historical evidence",
            confidence_score=current.confidence_score,
            severity_rank=current.severity_rank,
            is_replayed=True,
        )
    if is_replay:
        current.is_replayed = True
    return current


def evaluate_entity_decisions(
    ordered_events: list[SecurityEvent],
    as_of: datetime | None = None,
    previous_decisions: dict[str, DecisionState] | None = None,
    is_replay: bool = False,
) -> dict[str, DecisionState]:
    """Evaluate decisions for each event based on entity-scoped evidence available at each step."""
    previous_decisions = previous_decisions or {}
    decisions: dict[str, DecisionState] = {}
    entity_pools: dict[str, list[SecurityEvent]] = {}

    cutoff = as_of or datetime.max.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    for event in ordered_events:
        event_ts = event.timestamp
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        if event_ts > cutoff:
            continue

        entity = event.entity_key()
        entity_pools.setdefault(entity, []).append(event)

        raw = resolve_conflict(entity_pools[entity], event, event_ts)
        final = apply_retraction(previous_decisions.get(event.event_id), raw, is_replay)
        decisions[event.event_id] = final

    return decisions
