import { useState } from "react";
import { api, inr } from "../services/api";

export default function CreatePaymentForm({ accounts, onCreated }) {
  const [form, setForm] = useState({
    sender: "ACC-1001",
    receiver: "ACC-1002",
    amount: 1500,
    simulate_fraud_failure: false,
    simulate_fraud_timeout: false,
    simulate_payment_failure: false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (e) =>
    setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.createPayment({ ...form, amount: Number(form.amount) });
      onCreated(res.workflow_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const accountOptions = (accounts || []).map((a) => (
    <option key={a.account_id} value={a.account_id}>
      {a.account_id} – {a.owner} ({inr(a.balance)})
    </option>
  ));

  return (
    <form className="card" onSubmit={submit}>
      <h2>Create Payment</h2>
      <label>
        Sender account
        <select value={form.sender} onChange={set("sender")}>{accountOptions}</select>
      </label>
      <label>
        Receiver account
        <select value={form.receiver} onChange={set("receiver")}>{accountOptions}</select>
      </label>
      <label>
        Amount (₹)
        <input type="number" min="1" step="any" value={form.amount} onChange={set("amount")} />
      </label>
      <p className="hint">Amounts above ₹50,000 wait for approval. Above ₹5,00,000 are flagged as fraud.</p>

      <fieldset>
        <legend>Simulate failures</legend>
        <label className="check">
          <input type="checkbox" checked={form.simulate_fraud_failure} onChange={set("simulate_fraud_failure")} />
          Simulate Fraud Check Failure <span className="hint">(fails twice, then Temporal's retry succeeds)</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.simulate_fraud_timeout} onChange={set("simulate_fraud_timeout")} />
          Simulate Fraud Check Timeout <span className="hint">(attempt 1 exceeds the 5s timeout)</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.simulate_payment_failure} onChange={set("simulate_payment_failure")} />
          Simulate Payment Failure <span className="hint">(all 3 attempts fail → workflow fails)</span>
        </label>
      </fieldset>

      <button type="submit" disabled={busy}>{busy ? "Starting workflow…" : "Create Payment"}</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
