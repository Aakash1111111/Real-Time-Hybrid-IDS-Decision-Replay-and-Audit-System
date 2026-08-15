import { useEffect, useMemo, useState } from "react";

const API = "";

export default function ReplayInspector({ refreshKey, onReplayComplete }) {
  const [timeline, setTimeline] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [targetTimestamp, setTargetTimestamp] = useState("");
  const [deltas, setDeltas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      const res = await fetch(`${API}/audit-trail`);
      if (!res.ok) return;
      const data = await res.json();
      const state = data.current_state || {};
      const ids = state.timeline || [];
      const events = state.events || {};
      setTimeline(
        ids.map((id) => ({
          id,
          timestamp: events[id]?.timestamp,
          source: events[id]?.source,
          alert_level: events[id]?.alert_level,
        }))
      );
      if (!targetTimestamp && ids.length) {
        setTargetTimestamp(events[ids[ids.length - 1]]?.timestamp || "");
      }
    }
    load();
  }, [refreshKey, targetTimestamp]);

  const maxRank = useMemo(
    () =>
      Math.max(
        ...timeline.map((item) =>
          item.alert_level === "high" ? 3 : item.alert_level === "medium" ? 2 : 1
        ),
        1
      ),
    [timeline]
  );

  function toggleId(id) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function runReplay() {
    setLoading(true);
    setError("");
    setDeltas([]);
    try {
      const res = await fetch(`${API}/replay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_ids: selectedIds,
          target_timestamp: targetTimestamp,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "Replay failed");
      setDeltas(body.deltas || []);
      onReplayComplete?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Replay & Timeline Inspector</h2>
      <div className="controls">
        <input
          type="datetime-local"
          value={targetTimestamp ? targetTimestamp.slice(0, 16) : ""}
          onChange={(e) =>
            setTargetTimestamp(new Date(e.target.value).toISOString())
          }
        />
        <button type="button" disabled={loading || !selectedIds.length} onClick={runReplay}>
          {loading ? "Replaying..." : "Trigger Replay"}
        </button>
      </div>

      <div className="timeline-bar">
        {timeline.map((item) => {
          const rank =
            item.alert_level === "high" ? 3 : item.alert_level === "medium" ? 2 : 1;
          const height = `${(rank / maxRank) * 100}%`;
          const selected = selectedIds.includes(item.id);
          return (
            <button
              key={item.id}
              type="button"
              className={`timeline-point ${selected ? "selected" : ""}`}
              style={{ height }}
              onClick={() => toggleId(item.id)}
              title={item.id}
            >
              <span className="timeline-label">{item.id.slice(0, 8)}</span>
            </button>
          );
        })}
      </div>

      {error ? <p style={{ color: "#fca5a5" }}>{error}</p> : null}

      <div className="panel-body">
        {deltas.length === 0 ? (
          <p>Select events and run replay to see before/after deltas.</p>
        ) : (
          deltas.map((delta) => (
            <article key={delta.event_id} className="delta-card">
              <div className="delta-meta">
                <strong>{delta.event_id}</strong>
              </div>
              <p>Before Replay</p>
              <pre className="json-view">
                {JSON.stringify(delta.original, null, 2)}
              </pre>
              <p>After Replay</p>
              <pre className="json-view">
                {JSON.stringify(delta.revised, null, 2)}
              </pre>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
