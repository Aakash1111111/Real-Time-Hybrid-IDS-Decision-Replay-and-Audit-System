import { useEffect, useMemo, useState } from "react";

const API = "";

export default function AuditTrail({ refreshKey }) {
  const [auditLog, setAuditLog] = useState([]);
  const [filter, setFilter] = useState("all");
  const [viewMode, setViewMode] = useState("table");

  useEffect(() => {
    async function load() {
      const res = await fetch(`${API}/audit-trail`);
      if (!res.ok) return;
      const data = await res.json();
      setAuditLog(data.audit_log || []);
    }
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [refreshKey]);

  const filtered = useMemo(() => {
    if (filter === "all") return auditLog;
    return auditLog.filter((entry) => entry.operation === filter);
  }, [auditLog, filter]);

  return (
    <section className="panel">
      <h2>Audit Log Viewer</h2>
      <div className="controls">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All operations</option>
          <option value="ingest">Ingest</option>
          <option value="replay">Replay</option>
          <option value="manual_replay">Manual replay</option>
        </select>
        <select value={viewMode} onChange={(e) => setViewMode(e.target.value)}>
          <option value="table">Table</option>
          <option value="json">JSON</option>
        </select>
      </div>

      <div className="panel-body">
        {viewMode === "json" ? (
          <pre className="json-view">{JSON.stringify(filtered, null, 2)}</pre>
        ) : (
          filtered.map((entry, index) => (
            <article key={`${entry.timestamp}-${index}`} className="audit-row">
              <div className="event-meta">
                <strong>{entry.operation}</strong>
                <span>{entry.timestamp}</span>
                {entry.event_id ? <span>{entry.event_id}</span> : null}
              </div>
              <pre className="json-view">{JSON.stringify(entry.details, null, 2)}</pre>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
