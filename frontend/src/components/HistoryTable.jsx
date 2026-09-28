import { useState } from "react";

// The raw event history that Temporal stores for this workflow.
// "WORKFLOW_TASK_*" events are the worker running workflow code; hide them by default.
export default function HistoryTable({ events }) {
  const [showAll, setShowAll] = useState(false);
  if (!events) return <p className="hint">Loading history…</p>;
  const shown = showAll ? events : events.filter((e) => !e.type.startsWith("WORKFLOW_TASK"));

  return (
    <div>
      <label className="check">
        <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
        Show workflow-task events ({events.length} events total)
      </label>
      <table className="history">
        <thead>
          <tr><th>#</th><th>Time</th><th>Event</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {shown.map((e) => (
            <tr key={e.event_id} className={/FAILED|TIMED_OUT/.test(e.type) ? "row-bad" : ""}>
              <td>{e.event_id}</td>
              <td>{new Date(e.time + "Z").toLocaleTimeString()}</td>
              <td><code>{e.type}</code></td>
              <td>{e.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
