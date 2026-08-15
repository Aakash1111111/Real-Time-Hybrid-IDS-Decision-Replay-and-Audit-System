import { useState } from "react";
import EventStream from "./components/EventStream";
import ReplayInspector from "./components/ReplayInspector";
import AuditTrail from "./components/AuditTrail";

const SAMPLE_EVENT = {
  event_id: `live-${Date.now()}`,
  timestamp: new Date().toISOString(),
  source: "ai",
  event_type: "anomaly_alert",
  alert_level: "medium",
  rule_id: "AI-DEMO",
  confidence: 0.78,
  event_data: { entity_id: "demo-host", session_id: "demo-session" },
};

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [injectStatus, setInjectStatus] = useState("");

  async function injectSampleEvent() {
    setInjectStatus("");
    const payload = {
      ...SAMPLE_EVENT,
      event_id: `live-${Date.now()}`,
      timestamp: new Date().toISOString(),
    };
    const res = await fetch("/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) {
      setInjectStatus(body.detail || "Injection failed");
      return;
    }
    setInjectStatus(`Processed: ${body.decision.outcome}`);
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Hybrid IDS Decision Replay & Audit Dashboard</h1>
        <p>
          Local JSON-backed audit system with deterministic conflict resolution and replay.
        </p>
        <div className="controls" style={{ marginTop: "0.75rem", maxWidth: "320px" }}>
          <button type="button" onClick={injectSampleEvent}>
            Inject Sample Event
          </button>
          {injectStatus ? <span>{injectStatus}</span> : null}
        </div>
      </header>

      <main className="dashboard-grid">
        <EventStream refreshKey={refreshKey} />
        <ReplayInspector
          refreshKey={refreshKey}
          onReplayComplete={() => setRefreshKey((k) => k + 1)}
        />
        <AuditTrail refreshKey={refreshKey} />
      </main>
    </div>
  );
}
