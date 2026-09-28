import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import PaymentPage from "./pages/PaymentPage";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <header>
        <h1>Temporal Payment POC</h1>
        <span className="hint">React → FastAPI → Temporal Client → Temporal Server → Worker → Workflow → Activities</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/payments/:workflowId" element={<PaymentPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
