"""Inject demo events into the running IDS backend."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "demo_injection.json"


def post_event(event: dict) -> tuple[int, dict]:
    data = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/events",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"detail": body}
        return exc.code, payload


def main() -> int:
    samples = json.loads(FIXTURE.read_text(encoding="utf-8"))
    print(f"Injecting {len(samples)} demo events into {API}\n")

    for item in samples:
        name = item["name"]
        event = item["event"]
        status, body = post_event(event)
        if status == 200:
            decision = body["decision"]
            print(
                f"[OK] {name}\n"
                f"     event_id={event['event_id']} -> {decision['outcome'].upper()} "
                f"({decision['reasoning']})"
                f"{' [REPLAYED]' if decision.get('is_replayed') else ''}\n"
            )
        else:
            print(f"[ERR {status}] {name}\n     {body}\n")

    with urllib.request.urlopen(f"{API}/audit-trail", timeout=5) as resp:
        audit = json.loads(resp.read().decode())

    timeline = audit["current_state"].get("timeline", [])
    decisions = audit["current_state"].get("decisions", {})
    print("=" * 60)
    print(f"Timeline ({len(timeline)} events):")
    for event_id in timeline:
        d = decisions.get(event_id, {})
        print(f"  {event_id:30} -> {d.get('outcome', '?'):10} | {d.get('reasoning', '')}")

    print(f"\nAudit log entries: {len(audit['audit_log'])}")
    print(f"Dashboard: http://localhost:5173/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
