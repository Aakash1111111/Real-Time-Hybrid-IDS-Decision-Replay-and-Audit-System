from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SecurityEvent(BaseModel):
    event_id: str
    timestamp: datetime
    source: Literal["suricata", "ai", "signature"]
    event_type: Literal["network_alert", "anomaly_alert"]
    alert_level: Literal["low", "medium", "high"]
    rule_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    event_data: dict

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("timestamp must be an ISO 8601 string")
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid ISO 8601 timestamp: {value!r}. Expected format like 2026-01-15T10:30:00Z"
            ) from exc

    def entity_key(self) -> str:
        return str(
            self.event_data.get("entity_id")
            or self.event_data.get("session_id")
            or self.event_id
        )

    def content_fingerprint(self) -> str:
        return self.model_dump_json(exclude={"timestamp"})


class DecisionOutcome(str, Enum):
    ALERTED = "alerted"
    IGNORED = "ignored"
    RETRACTED = "retracted"


class DecisionState(BaseModel):
    event_id: str
    decision_timestamp: datetime
    outcome: DecisionOutcome
    reasoning: str
    confidence_score: float
    severity_rank: int
    is_replayed: bool = False


class ProcessResponse(BaseModel):
    status: str
    decision: DecisionState


class ReplayRequest(BaseModel):
    event_ids: list[str]
    target_timestamp: datetime

    @field_validator("target_timestamp", mode="before")
    @classmethod
    def parse_target_timestamp(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("target_timestamp must be an ISO 8601 string")
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid ISO 8601 target_timestamp: {value!r}"
            ) from exc


class ReplayDecisionDelta(BaseModel):
    event_id: str
    original: DecisionState | None
    revised: DecisionState


class ReplayResponse(BaseModel):
    status: str
    replayed_count: int
    deltas: list[ReplayDecisionDelta]
