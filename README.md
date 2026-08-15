# Real-Time Hybrid IDS Decision Replay and Audit System

Local hybrid intrusion-detection decision engine with deterministic conflict resolution, out-of-order replay, and a React audit dashboard. All state is persisted in JSON files under `data/`.

## Architecture

- **Backend**: Python 3.11+, FastAPI
- **Frontend**: React (Vite)
- **Persistence**: `data/state.json`, `data/audit_log.json`
- **No external databases, queues, or cloud dependencies**

## Project Structure

```
ids-replay-system/
├── backend/
│   ├── app/
│   │   ├── main.py          # REST API
│   │   ├── models.py        # Pydantic schemas
│   │   ├── engine.py        # Conflict resolution
│   │   ├── storage.py       # JSON persistence
│   │   └── replay.py        # Ingest + replay orchestration
│   └── tests/
├── data/
├── fixtures/
└── frontend/
```

## Zero-Configuration Setup

### 1. Backend

```bash
cd ids-replay-system/backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend

```bash
cd ids-replay-system/frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` for the audit dashboard. The Vite dev server proxies API calls to the backend.

### 3. Run Tests

```bash
cd ids-replay-system/backend
pytest -q
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events` | Ingest a `SecurityEvent` |
| POST | `/replay` | Force chronological reprocessing |
| GET | `/audit-trail` | Full audit timeline + current state |
| GET | `/decisions` | Current decision map |
| GET | `/health` | Health check |

### Example: Ingest Event

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-001",
    "timestamp": "2026-08-15T10:00:00Z",
    "source": "ai",
    "event_type": "anomaly_alert",
    "alert_level": "medium",
    "rule_id": "AI-100",
    "confidence": 0.82,
    "event_data": {"entity_id": "host-1", "session_id": "sess-1"}
  }'
```

### Example: Manual Replay

```bash
curl -X POST http://127.0.0.1:8000/replay \
  -H "Content-Type: application/json" \
  -d '{
    "event_ids": ["evt-001"],
    "target_timestamp": "2026-08-15T12:00:00Z"
  }'
```

## Conflict Resolution Rules

1. **Severity hierarchy**: `high (3) > medium (2) > low (1)`
2. **Agreement**: AI + signature agree → `ALERTED`
3. **Disagreement**:
   - Signature wins when severity is higher (AI confidence < 0.85)
   - AI wins when confidence ≥ 0.85 and severity is equal or higher
   - Low AI confidence (< 0.50) without signature support → `IGNORED`
4. **Replay retraction**: Prior `ALERTED` invalidated by new evidence → `RETRACTED`

## Edge Cases Covered

| Case | Scenario | Behavior |
|------|----------|----------|
| EC-1 | Duplicate event | Exact duplicate → HTTP 409; updated timestamp → in-place update |
| EC-2 | Late-arriving event | Timeline resort + replay from insertion point |
| EC-3 | AI vs signature conflict | Deterministic severity/confidence precedence |
| EC-4 | Malformed timestamp | HTTP 400 with field-level validation error |
| EC-5 | Retracted decision | Replay marks prior alerts as `RETRACTED` |

Fixtures for all cases live in `fixtures/edge_cases_sample.json`.

## Dashboard Panels

1. **Real-time Event Stream** — live feed with outcome badges
2. **Replay & Timeline Inspector** — select events, trigger `/replay`, view before/after deltas
3. **Audit Log Viewer** — filterable table/JSON view of `/audit-trail`

## Performance

Event evaluation is in-process with JSON file I/O and is designed to stay under 500ms for typical local workloads.
