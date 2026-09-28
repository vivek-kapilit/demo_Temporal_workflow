import { useState } from "react";
import { Link } from "react-router-dom";
import { api, inr } from "../services/api";
import { usePolling } from "../services/usePolling";
import CreatePaymentForm from "../components/CreatePaymentForm";
import PaymentDetails from "../components/PaymentDetails";

export default function Dashboard() {
  const { data: accounts } = usePolling(api.accounts, 2000);
  const { data: payments, error } = usePolling(api.listPayments, 2000);
  const [selected, setSelected] = useState(null);

  return (
    <div className="grid">
      <div className="col">
        <CreatePaymentForm accounts={accounts} onCreated={setSelected} />

        <div className="card">
          <h2>Accounts <span className="hint">(fake bank, SQLite)</span></h2>
          <table>
            <tbody>
              {(accounts || []).map((a) => (
                <tr key={a.account_id}>
                  <td>{a.account_id}</td><td>{a.owner}</td><td className="num">{inr(a.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="col wide">
        {selected
          ? <PaymentDetails workflowId={selected} showHistory={false} compact />
          : <div className="card hint">Create a payment (or pick one below) to watch its workflow live.</div>}

        <div className="card">
          <h2>Recent payment workflows <span className="hint">(from Temporal visibility)</span></h2>
          {error && <p className="error">{error}</p>}
          <table>
            <thead>
              <tr><th>Workflow ID</th><th>Amount</th><th>From → To</th><th>Temporal status</th><th>Started</th></tr>
            </thead>
            <tbody>
              {(payments || []).map((p) => (
                <tr key={p.workflow_id} className={p.workflow_id === selected ? "selected" : ""}
                    onClick={() => setSelected(p.workflow_id)}>
                  <td><Link to={`/payments/${p.workflow_id}`} onClick={(e) => e.stopPropagation()}>{p.workflow_id}</Link></td>
                  <td className="num">{inr(p.amount)}</td>
                  <td>{p.sender} → {p.receiver}</td>
                  <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                  <td>{p.start_time ? new Date(p.start_time).toLocaleTimeString() : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
