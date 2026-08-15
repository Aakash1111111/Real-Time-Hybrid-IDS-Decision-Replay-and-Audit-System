import { useEffect, useState } from "react";

const API = "";

function OutcomeBadge({ outcome, isReplayed }) {
  const cls = `badge badge-${outcome || "ignored"}`;
  return (
    <span>
      <span className={cls}>{outcome || "unknown"}</span>
      {isReplayed ? <span className="badge badge-replayed">replayed</span> : null}
    </span>
  );
}

export default function EventStream({ refreshKey }) {
  const [events, setEvents] = useState([]);
  const [decisions, setDecisions] = useState({});

  useEffect(() => {
    let active = true;
    async function load() {
      const res = await fetch(`${API}/audit-trail`);
      if (!res.ok) return;
      const data = await res.json();
      if (!active) return;
      const state = data.current_state || {};
      const timeline = state.timeline || [];
      const eventMap = state.events || {};
      const ordered = timeline.map((id) => ({
        ...eventMap[id],
        event_id: id,
        decision: (state.decisions || {})[id],
      }));
      setEvents(ordered.reverse());
      setDecisions(state.decisions || {});
    }
    load();
    const timer = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [refreshKey]);

  return (
    <section className="panel">
      <h2>Real-time Event Stream</h2>
      <div className="panel-body">
        {events.length === 0 ? (
          <p>No events ingested yet.</p>
        ) : (
          events.map((event) => {
            const decision = event.decision || decisions[event.event_id];
            return (
              <article key={event.event_id} className="event-card">
                <div className="event-meta">
                  <strong>{event.event_id}</strong>
                  <span>{event.source}</span>
                  <span>{event.alert_level}</span>
                  <span>conf: {(event.confidence ?? 0).toFixed(2)}</span>
                  {decision ? (
                    <OutcomeBadge
                      outcome={decision.outcome}
                      isReplayed={decision.is_replayed}
                    />
                  ) : null}
                </div>
                <div>{event.event_type}</div>
                <div className="event-meta">{event.timestamp}</div>
                {decision ? (
                  <div className="json-view">{decision.reasoning}</div>
                ) : null}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
