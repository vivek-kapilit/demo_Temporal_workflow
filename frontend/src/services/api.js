// All calls go to FastAPI (/api is proxied by Vite). The browser never talks
// to Temporal directly - FastAPI does, through the Temporal Client.

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  accounts: () => request("GET", "/accounts"),
  transactions: () => request("GET", "/transactions"),
  listPayments: () => request("GET", "/payments"),
  createPayment: (payment) => request("POST", "/payments", payment),
  getPayment: (workflowId) => request("GET", `/payments/${workflowId}`),
  getHistory: (workflowId) => request("GET", `/payments/${workflowId}/history`),
  approve: (workflowId) => request("POST", `/payments/${workflowId}/approve`, { approver: "dashboard-user" }),
  reject: (workflowId, reason) => request("POST", `/payments/${workflowId}/reject`, { reason }),
};

const TEMPORAL_UI = import.meta.env.VITE_TEMPORAL_UI_URL || "http://localhost:8233";
const NAMESPACE = import.meta.env.VITE_TEMPORAL_NAMESPACE || "default";

export const temporalUiLink = (workflowId) =>
  `${TEMPORAL_UI}/namespaces/${NAMESPACE}/workflows/${encodeURIComponent(workflowId)}`;

export const inr = (n) =>
  typeof n === "number" ? "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "-";
