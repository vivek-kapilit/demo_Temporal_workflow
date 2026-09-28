import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, inr, temporalUiLink } from "../services/api";
import { usePolling } from "../services/usePolling";
import StepTimeline from "./StepTimeline";
import HistoryTable from "./HistoryTable";

// Live view of one payment workflow. Polls FastAPI every second.
export default function PaymentDetails({ workflowId, showHistory = true, compact = false }) {
  const { data: detail, error, refresh } = usePolling(() => api.getPayment(workflowId), 1000, [workflowId]);
  const { data: history } = usePolling(
    () => (showHistory ? api.getHistory(workflowId) : Promise.resolve(null)),
    2000,
    [workflowId, showHistory]
  );
  const [actionMsg, setActionMsg] = useState(null);

  // When the worker is offline the query cannot be answered; keep showing the
  // last state we saw so the demo makes sense.
  const lastState = useRef(null);
  if (detail?.state) lastState.current = detail.state;
  const view = detail ? { ...detail, state: detail.state || lastState.current } : null;

  if (error && !detail) return <div className="card error">{error}</div>;
  if (!view) return <div className="card">Loading {workflowId}…</div>;

  const s = view.state || {};
  const waiting = s.approval_status === "PENDING";

  const decide = async (kind) => {
    try {
      const res = kind === "approve"
        ? await api.approve(workflowId)
        : await api.reject(workflowId, "Rejected from dashboard");
      setActionMsg(`${res.signal} signal sent – ${res.note}`);
      refresh();
    } catch (e) {
      setActionMsg(e.message);
    }
  };

  return (
    <div className="card">
      <div className="row between">
        <h2>Payment {s.payment_id || ""}</h2>
        <div className="row">
          {compact && <Link to={`/payments/${workflowId}`}>Full details →</Link>}
          <a href={temporalUiLink(workflowId)} target="_blank" rel="noreferrer">Open in Temporal UI ↗</a>
        </div>
      </div>

      {!view.worker_online && view.workflow_status === "RUNNING" && (
        <div className="banner warn">
          Worker offline – Temporal still holds this workflow's state. Start the worker again and it
          will continue exactly where it stopped.
        </div>
      )}

      <dl className="facts">
        <dt>Workflow ID</dt><dd><code>{view.workflow_id}</code></dd>
        <dt>Temporal status</dt><dd><span className={`badge ${view.workflow_status}`}>{view.workflow_status}</span></dd>
        <dt>Payment status</dt><dd><span className={`badge ${s.status}`}>{s.status || "?"}</span></dd>
        <dt>Amount</dt><dd>{inr(s.amount)}</dd>
        <dt>From → To</dt><dd>{s.sender} → {s.receiver}</dd>
        <dt>Transaction ID</dt><dd>{s.transaction_id ? <code>{s.transaction_id}</code> : "-"}</dd>
        <dt>Current activity</dt><dd>{s.current_step || "-"}</dd>
        <dt>Approval status</dt><dd><span className={`badge ${s.approval_status}`}>{s.approval_status || "-"}</span></dd>
        {(s.error || view.workflow_failure) && (
          <><dt>Error</dt><dd className="error">{s.error || view.workflow_failure}</dd></>
        )}
      </dl>

      <div className="row">
        <button onClick={() => decide("approve")} disabled={!waiting} className="approve">Approve Payment</button>
        <button onClick={() => decide("reject")} disabled={!waiting} className="reject">Reject Payment</button>
        {actionMsg && <span className="hint">{actionMsg}</span>}
      </div>

      <h3>Workflow progression</h3>
      <StepTimeline detail={view} />

      {showHistory && (
        <>
          <h3>Workflow history <span className="hint">(stored by the Temporal Server)</span></h3>
          <HistoryTable events={history} />
        </>
      )}
    </div>
  );
}
