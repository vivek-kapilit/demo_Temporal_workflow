// Shows the workflow progression, e.g.
//   Payment Created     ✓
//   Validation          ✓
//   Payment Processing  ⟳
const STEPS = [
  ["validate_payment", "Validation"],
  ["check_balance", "Balance Check"],
  ["fraud_check", "Fraud Check"],
  ["approval", "Approval"],
  ["process_payment", "Payment Processing"],
  ["save_transaction", "Save Transaction"],
  ["send_notification", "Notification"],
];

const ICONS = {
  completed: "✓",
  running: "⟳",
  waiting: "⏸",
  failed: "✗",
  skipped: "–",
  pending: "-",
};

export default function StepTimeline({ detail }) {
  const steps = detail.state?.steps || {};
  const pendingByName = Object.fromEntries(
    (detail.pending_activities || []).map((p) => [p.activity, p])
  );

  return (
    <table className="steps">
      <thead>
        <tr><th>Step</th><th>Status</th><th>Attempts</th><th>Info</th></tr>
      </thead>
      <tbody>
        <tr className="step-completed">
          <td>Payment Created</td><td><span className="icon">✓</span> completed</td><td></td>
          <td className="hint">workflow started</td>
        </tr>
        {STEPS.map(([key, label]) => {
          const status = steps[key] || "pending";
          const attempts = detail.attempts?.[key];
          const pending = pendingByName[key];
          const lastFailure = pending?.last_failure || detail.last_failures?.[key];
          let info = "";
          if (key === "approval" && status === "skipped") info = "not required (≤ ₹50,000)";
          else if (key === "approval" && detail.state?.approval_note) info = detail.state.approval_note;
          else if (status === "waiting") info = "waiting for approve/reject signal";
          if (pending && pending.attempt > 1 && status === "running") {
            info = `retrying (attempt ${pending.attempt})`;
          }
          return (
            <tr key={key} className={`step-${status}`}>
              <td>{label}</td>
              <td>
                <span className={`icon ${status === "running" ? "spin" : ""}`}>{ICONS[status]}</span> {status}
              </td>
              <td>
                {attempts || ""}
                {attempts > 1 && <span className="retry-badge">{attempts - 1} retr{attempts > 2 ? "ies" : "y"}</span>}
              </td>
              <td>
                {info}
                {lastFailure && <div className="failure">last error: {lastFailure}</div>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
