import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000/api/v1";

function formatPaise(paise) {
  const amount = Math.abs(paise) / 100;
  return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2 });
}

function StatusBadge({ status }) {
  const config = {
    pending:    { bg: "#FEF9C3", color: "#854D0E", dot: "#EAB308" },
    processing: { bg: "#DBEAFE", color: "#1E40AF", dot: "#3B82F6" },
    completed:  { bg: "#DCFCE7", color: "#166534", dot: "#22C55E" },
    failed:     { bg: "#FEE2E2", color: "#991B1B", dot: "#EF4444" },
  };
  const c = config[status] || { bg: "#F3F4F6", color: "#374151", dot: "#9CA3AF" };
  return (
    <span style={{
      background: c.bg, color: c.color,
      padding: "3px 10px", borderRadius: 20,
      fontSize: 12, fontWeight: 600,
      display: "inline-flex", alignItems: "center", gap: 5
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot, display: "inline-block" }} />
      {status}
    </span>
  );
}

function PayoutForm({ merchant, onSuccess }) {
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const handleSubmit = async () => {
    if (!amount || isNaN(amount) || Number(amount) <= 0) {
      setMessage({ type: "error", text: "Enter a valid amount in rupees" });
      return;
    }
    const amountPaise = Math.round(Number(amount) * 100);
    const idempotencyKey = crypto.randomUUID();
    setLoading(true);
    setMessage(null);
    try {
      const res = await axios.post(
        `${API}/payouts/`,
        { amount_paise: amountPaise, bank_account_id: merchant.bank_account_number },
        { headers: { "Content-Type": "application/json", "Merchant-Id": merchant.id, "Idempotency-Key": idempotencyKey } }
      );
      setMessage({ type: "success", text: `✅ Payout of ${formatPaise(amountPaise)} initiated! ID #${res.data.payout_id}` });
      setAmount("");
      onSuccess();
    } catch (err) {
      setMessage({ type: "error", text: err.response?.data?.error || "Something went wrong" });
    }
    setLoading(false);
  };

  return (
    <div style={{ background: "white", borderRadius: 16, padding: 24, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)" }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#111827" }}>Withdraw Funds</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6B7280" }}>Transfer to your registered bank account</p>
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#6B7280", fontWeight: 600, fontSize: 15 }}>₹</span>
          <input
            type="number"
            placeholder="0.00"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "12px 14px 12px 30px",
              border: "1.5px solid #E5E7EB", borderRadius: 10,
              fontSize: 15, outline: "none", fontFamily: "inherit",
              transition: "border-color 0.2s",
            }}
            onFocus={e => e.target.style.borderColor = "#2563EB"}
            onBlur={e => e.target.style.borderColor = "#E5E7EB"}
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{
            background: loading ? "#93C5FD" : "linear-gradient(135deg, #2563EB, #1D4ED8)",
            color: "white", border: "none",
            padding: "12px 24px", borderRadius: 10,
            fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
            whiteSpace: "nowrap", transition: "all 0.2s",
            boxShadow: loading ? "none" : "0 2px 8px rgba(37,99,235,0.4)"
          }}
        >
          {loading ? "Processing..." : "Withdraw →"}
        </button>
      </div>
      {message && (
        <div style={{
          marginTop: 12, padding: "10px 14px", borderRadius: 8, fontSize: 13, fontWeight: 500,
          background: message.type === "error" ? "#FEF2F2" : "#F0FDF4",
          color: message.type === "error" ? "#DC2626" : "#16A34A",
          border: `1px solid ${message.type === "error" ? "#FECACA" : "#BBF7D0"}`
        }}>
          {message.text}
        </div>
      )}
    </div>
  );
}

function BalanceCard({ label, amount, color, icon }) {
  return (
    <div style={{
      background: "white", borderRadius: 16, padding: 24,
      boxShadow: "0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)",
      borderTop: `3px solid ${color}`, flex: 1
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: 1 }}>{label}</p>
          <p style={{ margin: "8px 0 0", fontSize: 28, fontWeight: 800, color: "#111827", letterSpacing: -1 }}>{formatPaise(amount)}</p>
        </div>
        <div style={{ fontSize: 24, background: color + "15", padding: 10, borderRadius: 12 }}>{icon}</div>
      </div>
    </div>
  );
}

function MerchantDashboard({ merchant, onRefresh }) {
  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <BalanceCard label="Available Balance" amount={merchant.available_balance} color="#2563EB" icon="💰" />
        <BalanceCard label="Held Balance" amount={merchant.held_balance} color="#F59E0B" icon="⏳" />
      </div>

      <PayoutForm merchant={merchant} onSuccess={onRefresh} />

      {/* Payout History */}
      <div style={{ background: "white", borderRadius: 16, padding: 24, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "#111827" }}>Payout History</h2>
        {merchant.payouts.length === 0 ? (
          <div style={{ textAlign: "center", padding: "32px 0", color: "#9CA3AF" }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
            <p style={{ margin: 0, fontSize: 14 }}>No payouts yet</p>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #F3F4F6" }}>
                {["ID", "Amount", "Status", "Date"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "0 0 10px", color: "#6B7280", fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {merchant.payouts.map(p => (
                <tr key={p.id} style={{ borderBottom: "1px solid #F9FAFB" }}>
                  <td style={{ padding: "12px 0", color: "#6B7280", fontWeight: 500 }}>#{p.id}</td>
                  <td style={{ padding: "12px 0", fontWeight: 700, color: "#111827" }}>{formatPaise(p.amount_paise)}</td>
                  <td style={{ padding: "12px 0" }}><StatusBadge status={p.status} /></td>
                  <td style={{ padding: "12px 0", color: "#6B7280" }}>{new Date(p.created_at).toLocaleDateString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Recent Transactions */}
      <div style={{ background: "white", borderRadius: 16, padding: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "#111827" }}>Recent Transactions</h2>
        {merchant.recent_entries.length === 0 ? (
          <p style={{ color: "#9CA3AF", fontSize: 14, margin: 0 }}>No transactions yet</p>
        ) : (
          <div>
            {merchant.recent_entries.map(entry => (
              <div key={entry.id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 0", borderBottom: "1px solid #F9FAFB"
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: "50%",
                    background: entry.amount > 0 ? "#DCFCE7" : "#FEE2E2",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16
                  }}>
                    {entry.amount > 0 ? "⬆️" : "⬇️"}
                  </div>
                  <div>
                    <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "#111827" }}>{entry.description}</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, color: "#9CA3AF" }}>{new Date(entry.created_at).toLocaleDateString("en-IN")}</p>
                  </div>
                </div>
                <span style={{ fontWeight: 700, fontSize: 14, color: entry.amount > 0 ? "#16A34A" : "#DC2626" }}>
                  {entry.amount > 0 ? "+" : "-"}{formatPaise(entry.amount)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMerchants = async () => {
    try {
      const res = await axios.get(`${API}/merchants/`);
      setMerchants(res.data);
      if (!selectedId && res.data.length > 0) setSelectedId(res.data[0].id);
    } catch (err) {
      console.error("Failed to fetch merchants", err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchMerchants();
    const interval = setInterval(fetchMerchants, 5000);
    return () => clearInterval(interval);
  }, []);

  const selectedMerchant = merchants.find(m => m.id === selectedId);

  if (loading) return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#F8FAFC" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>💸</div>
        <p style={{ color: "#6B7280", margin: 0 }}>Loading dashboard...</p>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: "#F8FAFC", fontFamily: "'DM Sans', 'Segoe UI', sans-serif" }}>
      {/* Header */}
      <div style={{
        background: "linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%)",
        padding: "0 32px", boxShadow: "0 4px 20px rgba(37,99,235,0.3)"
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "white", letterSpacing: -0.5 }}>
              💸 Playto Pay
            </h1>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: "rgba(255,255,255,0.7)" }}>Merchant Payout Dashboard</p>
          </div>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", background: "rgba(255,255,255,0.1)", padding: "6px 12px", borderRadius: 20 }}>
            🟢 Live • Auto-refreshes every 5s
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 32px" }}>
        {/* Merchant Selector */}
        <div style={{ background: "white", borderRadius: 16, padding: "16px 20px", marginBottom: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04)" }}>
          <p style={{ margin: "0 0 10px", fontSize: 12, fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: 1 }}>Select Merchant</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {merchants.map(m => (
              <button
                key={m.id}
                onClick={() => setSelectedId(m.id)}
                style={{
                  padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  cursor: "pointer", transition: "all 0.15s", border: "1.5px solid",
                  borderColor: selectedId === m.id ? "#2563EB" : "#E5E7EB",
                  background: selectedId === m.id ? "#EFF6FF" : "white",
                  color: selectedId === m.id ? "#2563EB" : "#374151",
                  boxShadow: selectedId === m.id ? "0 0 0 3px rgba(37,99,235,0.1)" : "none"
                }}
              >
                {m.name}
              </button>
            ))}
          </div>
        </div>

        {selectedMerchant && (
          <MerchantDashboard merchant={selectedMerchant} onRefresh={fetchMerchants} />
        )}
      </div>
    </div>
  );
}
