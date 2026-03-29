import { useState } from "react";

import { verifyProofLocally } from "./lib/stellar";

const containerStyle = {
  minHeight: "100vh",
  background: "linear-gradient(135deg, #07121f, #13304b)",
  color: "#f3f8ff",
  padding: "2rem",
  fontFamily: "Inter, system-ui, sans-serif",
};

const panelStyle = {
  maxWidth: "880px",
  margin: "0 auto",
  background: "rgba(8, 15, 29, 0.75)",
  border: "1px solid rgba(126, 180, 255, 0.2)",
  borderRadius: "20px",
  padding: "1.5rem",
  boxShadow: "0 24px 80px rgba(0, 0, 0, 0.35)",
};

const inputStyle = {
  width: "100%",
  padding: "0.8rem 1rem",
  borderRadius: "12px",
  border: "1px solid rgba(126, 180, 255, 0.25)",
  background: "rgba(255, 255, 255, 0.05)",
  color: "#f3f8ff",
};

export default function App() {
  const [incidentId, setIncidentId] = useState("");
  const [message, setMessage] = useState("Pick a resolved incident ID, then anchor or verify its proof.");

  const handleAnchor = async () => {
    if (!incidentId) {
      setMessage("Enter an incident ID before anchoring.");
      return;
    }

    const response = await fetch("/api/attest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident_id: incidentId }),
    });
    const payload = await response.json();
    setMessage(JSON.stringify(payload, null, 2));
  };

  const handleVerify = async () => {
    if (!incidentId) {
      setMessage("Enter an incident ID before verification.");
      return;
    }

    const result = await verifyProofLocally({ incidentId });
    setMessage(JSON.stringify(result, null, 2));
  };

  return (
    <div style={containerStyle}>
      <div style={panelStyle}>
        <p style={{ color: "#6be3ff", letterSpacing: "0.1em", textTransform: "uppercase" }}>
          Optional Stellar Bonus
        </p>
        <h1 style={{ fontSize: "clamp(2rem, 5vw, 3.5rem)", marginTop: 0 }}>
          Incident Attestation Console
        </h1>
        <p style={{ lineHeight: 1.7, color: "#d3def0" }}>
          This UI is intentionally isolated from the live remediation loop. It takes a resolved incident,
          requests an attestation from the backend, and gives you a clean place to verify the resulting proof.
        </p>

        <div style={{ display: "grid", gap: "1rem", marginTop: "1.5rem" }}>
          <label>
            <span style={{ display: "block", marginBottom: "0.5rem" }}>Incident ID</span>
            <input
              style={inputStyle}
              value={incidentId}
              onChange={(event) => setIncidentId(event.target.value)}
              placeholder="incident-abc123"
            />
          </label>

          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            <button onClick={handleAnchor} style={{ padding: "0.9rem 1.2rem", borderRadius: "12px" }}>
              Anchor Incident
            </button>
            <button onClick={handleVerify} style={{ padding: "0.9rem 1.2rem", borderRadius: "12px" }}>
              Verify Proof
            </button>
          </div>

          <pre
            style={{
              margin: 0,
              padding: "1rem",
              borderRadius: "14px",
              background: "rgba(255, 255, 255, 0.04)",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {message}
          </pre>
        </div>
      </div>
    </div>
  );
}
