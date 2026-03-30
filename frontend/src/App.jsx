import { useEffect, useMemo, useState } from "react";

import {
  anchorIncident,
  fetchIncidentAudit,
  fetchIncidentList,
  fetchIncidentSummary,
  verifyProofLocally,
} from "./lib/stellar";

const pageStyle = {
  minHeight: "100vh",
  background:
    "radial-gradient(circle at top left, rgba(110, 213, 255, 0.12), transparent 22%), radial-gradient(circle at 82% 8%, rgba(113, 126, 255, 0.1), transparent 20%), linear-gradient(180deg, #06111c 0%, #0a1726 48%, #0f2035 100%)",
  color: "#ecf5ff",
  padding: "1.25rem 1.25rem 2rem",
  fontFamily: 'Inter, "Segoe UI", system-ui, sans-serif',
};

const shellStyle = {
  width: "min(1680px, 100%)",
  margin: "0 auto",
  display: "grid",
  gap: "1rem",
};

const heroStyle = {
  display: "grid",
  gridTemplateColumns: "1.5fr 1fr",
  gap: "1rem",
  padding: "1.25rem 1.35rem",
  borderRadius: "26px",
  border: "1px solid rgba(123, 185, 255, 0.16)",
  background: "linear-gradient(155deg, rgba(7, 18, 32, 0.95), rgba(7, 16, 28, 0.88))",
  boxShadow: "0 20px 80px rgba(0, 0, 0, 0.26)",
};

const badgeStyle = (tone = "neutral") => ({
  display: "inline-flex",
  alignItems: "center",
  gap: "0.35rem",
  padding: "0.34rem 0.68rem",
  borderRadius: "999px",
  fontSize: "0.74rem",
  fontWeight: 700,
  letterSpacing: "0.04em",
  color:
    tone === "good"
      ? "#c5ffdd"
      : tone === "warn"
        ? "#ffe3a4"
        : tone === "danger"
          ? "#ffc9c9"
          : "#d8e7fb",
  background:
    tone === "good"
      ? "rgba(27, 158, 95, 0.15)"
      : tone === "warn"
        ? "rgba(255, 193, 7, 0.14)"
        : tone === "danger"
          ? "rgba(220, 53, 69, 0.14)"
          : "rgba(123, 185, 255, 0.12)",
  border:
    tone === "good"
      ? "1px solid rgba(27, 158, 95, 0.3)"
      : tone === "warn"
        ? "1px solid rgba(255, 193, 7, 0.26)"
        : tone === "danger"
          ? "1px solid rgba(220, 53, 69, 0.25)"
          : "1px solid rgba(123, 185, 255, 0.18)",
});

const boardStyle = {
  display: "grid",
  gridTemplateColumns: "360px minmax(0, 1.4fr) minmax(320px, 0.9fr)",
  gap: "1rem",
  alignItems: "start",
};

const panelStyle = {
  background: "rgba(7, 16, 28, 0.84)",
  border: "1px solid rgba(123, 185, 255, 0.12)",
  borderRadius: "22px",
  padding: "1rem",
  boxShadow: "0 12px 42px rgba(0, 0, 0, 0.18)",
  minWidth: 0,
};

const panelHeaderStyle = {
  display: "grid",
  gap: "0.3rem",
  marginBottom: "0.9rem",
};

const eyebrowStyle = {
  color: "#7de6ff",
  fontSize: "0.74rem",
  textTransform: "uppercase",
  letterSpacing: "0.12em",
};

const titleStyle = {
  margin: 0,
  fontSize: "1.1rem",
  fontWeight: 700,
};

const subtitleStyle = {
  color: "#bfd1e5",
  lineHeight: 1.6,
  fontSize: "0.92rem",
};

const inputStyle = {
  width: "100%",
  borderRadius: "14px",
  border: "1px solid rgba(123, 185, 255, 0.14)",
  background: "rgba(255, 255, 255, 0.035)",
  color: "#ecf5ff",
  padding: "0.82rem 0.92rem",
  outline: "none",
};

const selectStyle = {
  ...inputStyle,
  appearance: "none",
};

const buttonStyle = {
  border: 0,
  borderRadius: "14px",
  padding: "0.8rem 0.95rem",
  fontWeight: 700,
  cursor: "pointer",
  color: "#06111c",
  background: "linear-gradient(135deg, #79e7ff, #77a4ff)",
};

const secondaryButtonStyle = {
  ...buttonStyle,
  color: "#ecf5ff",
  background: "rgba(255, 255, 255, 0.06)",
  border: "1px solid rgba(123, 185, 255, 0.18)",
};

const copyButtonStyle = {
  ...secondaryButtonStyle,
  padding: "0.52rem 0.72rem",
  fontSize: "0.78rem",
};

const dataGridStyle = {
  display: "grid",
  gap: "0.75rem",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
};

const dataCardStyle = {
  background: "rgba(255, 255, 255, 0.035)",
  border: "1px solid rgba(123, 185, 255, 0.08)",
  borderRadius: "14px",
  padding: "0.8rem",
};

const dataLabelStyle = {
  fontSize: "0.74rem",
  color: "#8fa9cb",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  marginBottom: "0.35rem",
};

const dataValueStyle = {
  color: "#f6f9ff",
  lineHeight: 1.55,
  wordBreak: "break-word",
  fontSize: "0.93rem",
};

const incidentRowStyle = (selected) => ({
  display: "grid",
  gap: "0.55rem",
  width: "100%",
  padding: "0.85rem",
  textAlign: "left",
  borderRadius: "18px",
  border: selected ? "1px solid rgba(123, 231, 255, 0.45)" : "1px solid rgba(123, 185, 255, 0.08)",
  background: selected ? "rgba(10, 28, 45, 0.95)" : "rgba(255, 255, 255, 0.03)",
  cursor: "pointer",
});

const timelineStyle = {
  display: "grid",
  gap: "0.65rem",
};

const timelineItemStyle = {
  padding: "0.8rem 0.85rem",
  borderRadius: "14px",
  background: "rgba(255, 255, 255, 0.04)",
  border: "1px solid rgba(123, 185, 255, 0.08)",
};

const preStyle = {
  margin: 0,
  padding: "0.95rem",
  borderRadius: "16px",
  background: "rgba(2, 8, 16, 0.74)",
  border: "1px solid rgba(123, 185, 255, 0.1)",
  whiteSpace: "pre-wrap",
  overflowX: "auto",
  color: "#d9e7fb",
  fontSize: "0.84rem",
  lineHeight: 1.6,
  maxHeight: "220px",
  overflowY: "auto",
};

const desktopOnlyStyle = {
  display: "flex",
  gap: "0.5rem",
  flexWrap: "wrap",
};

function toneForStatus(status) {
  if (status === "completed") return "good";
  if (status === "awaiting_human") return "warn";
  if (status === "error") return "danger";
  return "neutral";
}

function toneForVerification(result) {
  if (!result) return "neutral";
  if (result.stub) return "warn";
  return result.verified ? "good" : "danger";
}

function Field({ label, value, copyValue, onCopy }) {
  return (
    <div style={dataCardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "start" }}>
        <div style={dataLabelStyle}>{label}</div>
        {copyValue ? (
          <button style={copyButtonStyle} onClick={() => onCopy(copyValue, label)}>
            Copy
          </button>
        ) : null}
      </div>
      <div style={dataValueStyle}>{value || "-"}</div>
    </div>
  );
}

export default function App() {
  const [filters, setFilters] = useState({ search: "", status: "", anomalyType: "" });
  const [incidentList, setIncidentList] = useState([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState("");
  const [txIdOverride, setTxIdOverride] = useState("");
  const [summaryPayload, setSummaryPayload] = useState(null);
  const [auditPayload, setAuditPayload] = useState(null);
  const [anchorPayload, setAnchorPayload] = useState(null);
  const [verifyPayload, setVerifyPayload] = useState(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);

  const selectedSummary = summaryPayload?.incident;
  const latestAudit = summaryPayload?.latest_audit;
  const anchorResult = anchorPayload?.attestation;
  const verificationResult = verifyPayload?.verification;

  const metrics = useMemo(
    () => ({
      total: incidentList.length,
      completed: incidentList.filter((incident) => incident.status === "completed").length,
      awaitingHuman: incidentList.filter((incident) => incident.status === "awaiting_human").length,
    }),
    [incidentList],
  );

  const copyValue = async (value, label) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopyMessage(`${label} copied.`);
    } catch (_err) {
      setCopyMessage(`Copy ${label} manually.`);
    }
    window.setTimeout(() => setCopyMessage(""), 1800);
  };

  const loadIncidentList = async (nextFilters = filters) => {
    setLoading("Loading incidents...");
    setError("");
    try {
      const payload = await fetchIncidentList(nextFilters);
      setIncidentList(payload.incidents || []);
      if (!selectedIncidentId && payload.incidents?.length) {
        setSelectedIncidentId(payload.incidents[0].incident_id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  };

  useEffect(() => {
    loadIncidentList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = window.setInterval(() => {
      loadIncidentList();
    }, 10000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, filters]);

  useEffect(() => {
    if (!selectedIncidentId) return;
    let cancelled = false;

    async function loadDetails() {
      setLoading(`Loading ${selectedIncidentId}...`);
      setError("");
      try {
        const [summary, audit] = await Promise.all([
          fetchIncidentSummary(selectedIncidentId),
          fetchIncidentAudit(selectedIncidentId),
        ]);
        if (cancelled) return;
        setSummaryPayload(summary);
        setAuditPayload(audit);
        setAnchorPayload(null);
        setVerifyPayload(null);
        const latestTx = audit.entries?.find((entry) => entry.tx_id)?.tx_id || "";
        setTxIdOverride(latestTx);
      } catch (err) {
        if (cancelled) return;
        setSummaryPayload(null);
        setAuditPayload(null);
        setError(err.message);
      } finally {
        if (!cancelled) setLoading("");
      }
    }

    loadDetails();
    return () => {
      cancelled = true;
    };
  }, [selectedIncidentId]);

  const handleAnchor = async () => {
    if (!selectedIncidentId) {
      setError("Select an incident first.");
      return;
    }
    setLoading(`Anchoring ${selectedIncidentId} on Soroban...`);
    setError("");
    try {
      const payload = await anchorIncident({ incidentId: selectedIncidentId });
      setAnchorPayload(payload);
      const txId = payload?.attestation?.tx_id || "";
      if (txId) setTxIdOverride(txId);
      const [summary, audit] = await Promise.all([
        fetchIncidentSummary(selectedIncidentId),
        fetchIncidentAudit(selectedIncidentId),
      ]);
      setSummaryPayload(summary);
      setAuditPayload(audit);
      setVerifyPayload(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  };

  const handleVerify = async () => {
    if (!selectedIncidentId) {
      setError("Select an incident first.");
      return;
    }
    setLoading(`Verifying ${selectedIncidentId} against the contract...`);
    setError("");
    try {
      const payload = await verifyProofLocally({ incidentId: selectedIncidentId, txId: txIdOverride });
      setVerifyPayload(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  };

  return (
    <div style={pageStyle}>
      <div style={shellStyle}>
        <section style={heroStyle}>
          <div style={{ display: "grid", gap: "0.75rem" }}>
            <div style={badgeStyle("good")}>Desktop Soroban Operations</div>
            <h1 style={{ margin: 0, fontSize: "clamp(2.2rem, 4vw, 3.8rem)", lineHeight: 1.05 }}>Incident Proof Desk</h1>
            <div style={{ color: "#d0deef", lineHeight: 1.75, maxWidth: "860px" }}>
              A desktop-first operations surface for browsing incidents, anchoring canonical proof records on Soroban,
              and verifying on-chain hashes without touching the remediation control loop.
            </div>
          </div>
          <div style={{ display: "grid", gap: "0.8rem", alignContent: "start", justifyItems: "start" }}>
            <div style={desktopOnlyStyle}>
              <div style={badgeStyle("neutral")}>Incidents: {metrics.total}</div>
              <div style={badgeStyle("good")}>Completed: {metrics.completed}</div>
              <div style={badgeStyle("warn")}>Awaiting Human: {metrics.awaitingHuman}</div>
            </div>
            {loading ? <div style={badgeStyle("neutral")}>{loading}</div> : null}
            {error ? <div style={badgeStyle("danger")}>{error}</div> : null}
            {copyMessage ? <div style={badgeStyle("good")}>{copyMessage}</div> : null}
          </div>
        </section>

        <div style={boardStyle}>
          <aside style={{ ...panelStyle, maxHeight: "calc(100vh - 170px)", overflow: "hidden", display: "grid", gridTemplateRows: "auto auto 1fr" }}>
            <div style={panelHeaderStyle}>
              <div style={eyebrowStyle}>Incident Browser</div>
              <h2 style={titleStyle}>Filters & Queue</h2>
              <div style={subtitleStyle}>Use search and narrow filters, then select the incident you want to inspect.</div>
            </div>

            <div style={{ display: "grid", gap: "0.75rem", marginBottom: "0.9rem" }}>
              <input
                style={inputStyle}
                value={filters.search}
                onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
                placeholder="Search incident payloads"
              />
              <div style={{ display: "grid", gap: "0.75rem", gridTemplateColumns: "1fr 1fr" }}>
                <select
                  style={selectStyle}
                  value={filters.status}
                  onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
                >
                  <option value="">All statuses</option>
                  <option value="completed">completed</option>
                  <option value="awaiting_human">awaiting_human</option>
                  <option value="error">error</option>
                  <option value="suppressed">suppressed</option>
                </select>
                <select
                  style={selectStyle}
                  value={filters.anomalyType}
                  onChange={(event) => setFilters((prev) => ({ ...prev, anomalyType: event.target.value }))}
                >
                  <option value="">All anomalies</option>
                  <option value="CrashLoopBackOff">CrashLoopBackOff</option>
                  <option value="OOMKilled">OOMKilled</option>
                  <option value="PendingPod">PendingPod</option>
                  <option value="CPUThrottling">CPUThrottling</option>
                  <option value="DeploymentStalled">DeploymentStalled</option>
                </select>
              </div>
              <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap" }}>
                <button style={buttonStyle} onClick={() => loadIncidentList(filters)}>Apply</button>
                <button
                  style={secondaryButtonStyle}
                  onClick={() => {
                    const next = { search: "", status: "", anomalyType: "" };
                    setFilters(next);
                    loadIncidentList(next);
                  }}
                >
                  Clear
                </button>
                <button style={secondaryButtonStyle} onClick={() => setAutoRefresh((value) => !value)}>
                  {autoRefresh ? "Auto Refresh On" : "Auto Refresh Off"}
                </button>
              </div>
            </div>

            <div style={{ display: "grid", gap: "0.7rem", overflowY: "auto", paddingRight: "0.15rem" }}>
              {incidentList.length ? (
                incidentList.map((incident) => (
                  <button
                    key={incident.incident_id}
                    type="button"
                    style={incidentRowStyle(incident.incident_id === selectedIncidentId)}
                    onClick={() => setSelectedIncidentId(incident.incident_id)}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "start" }}>
                      <div style={{ fontWeight: 700, lineHeight: 1.45, wordBreak: "break-word" }}>{incident.incident_id}</div>
                      <div style={badgeStyle(toneForStatus(incident.status))}>{incident.status}</div>
                    </div>
                    <div style={{ color: "#cadeef", lineHeight: 1.55, fontSize: "0.92rem" }}>
                      {incident.anomaly_type || "Unknown anomaly"}
                    </div>
                    <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                      <div style={badgeStyle("neutral")}>{incident.resource_name || "unknown resource"}</div>
                      <div style={badgeStyle("neutral")}>{incident.plan_action || "no action"}</div>
                    </div>
                  </button>
                ))
              ) : (
                <div style={{ color: "#9ab4d4", lineHeight: 1.7 }}>No incidents match the current filters.</div>
              )}
            </div>
          </aside>

          <section style={{ display: "grid", gap: "1rem" }}>
            <div style={panelStyle}>
              <div style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "1.1fr auto", alignItems: "start", marginBottom: "1rem" }}>
                <div style={panelHeaderStyle}>
                  <div style={eyebrowStyle}>Selected Incident</div>
                  <h2 style={titleStyle}>{selectedSummary?.incident_id || selectedIncidentId || "No Incident Selected"}</h2>
                  <div style={subtitleStyle}>Primary operator workspace for summary inspection, proof anchoring, and contract verification.</div>
                </div>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <button style={copyButtonStyle} onClick={() => copyValue(selectedIncidentId, "Incident ID")}>Copy Incident</button>
                  <button style={copyButtonStyle} onClick={() => copyValue(anchorResult?.tx_id || txIdOverride, "Transaction ID")}>Copy Tx</button>
                  <button style={copyButtonStyle} onClick={() => copyValue(anchorPayload?.contract_key || verifyPayload?.contract_key, "Contract Key")}>Copy Key</button>
                </div>
              </div>

              {selectedSummary ? (
                <>
                  <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", marginBottom: "1rem" }}>
                    <div data-testid="selected-incident-status" style={badgeStyle(toneForStatus(selectedSummary.status))}>{selectedSummary.status}</div>
                    <div style={badgeStyle(toneForVerification(verificationResult))}>
                      {verificationResult ? (verificationResult.verified ? "Verified" : verificationResult.stub ? "Verify Stubbed" : "Mismatch") : "Not Verified"}
                    </div>
                    <div style={badgeStyle("neutral")}>{selectedSummary.anomaly_type || "unknown anomaly"}</div>
                    <div style={badgeStyle("neutral")}>{selectedSummary.namespace || "default"}</div>
                  </div>

                  <div style={dataGridStyle}>
                    <Field label="Resource" value={selectedSummary.resource_name} />
                    <Field label="Action" value={selectedSummary.plan_action} />
                    <Field label="Approved" value={String(selectedSummary.approved)} />
                    <Field label="Audit Entries" value={String(summaryPayload?.audit_count || 0)} />
                  </div>

                  <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem", gridTemplateColumns: "minmax(220px, 280px) auto auto" }}>
                    <input
                      style={inputStyle}
                      value={txIdOverride}
                      onChange={(event) => setTxIdOverride(event.target.value)}
                      placeholder="Optional tx override"
                    />
                    <button style={buttonStyle} onClick={handleAnchor}>Anchor Incident</button>
                    <button style={secondaryButtonStyle} onClick={handleVerify}>Verify Proof</button>
                  </div>

                  <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem", gridTemplateColumns: "1fr 1fr" }}>
                    <div style={dataCardStyle}>
                      <div style={dataLabelStyle}>Latest Audit Result</div>
                      <div style={dataValueStyle}>{latestAudit?.result || "No audit result loaded."}</div>
                    </div>
                    <div style={dataCardStyle}>
                      <div style={dataLabelStyle}>Latest Audit Decision</div>
                      <div style={dataValueStyle}>{latestAudit?.decision || "No decision recorded."}</div>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ color: "#9ab4d4", lineHeight: 1.7 }}>Pick an incident from the left rail to populate the workspace.</div>
              )}
            </div>

            <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "1fr 1fr" }}>
              <div style={panelStyle}>
                <div style={panelHeaderStyle}>
                  <div style={eyebrowStyle}>Anchor</div>
                  <h2 style={titleStyle}>Attestation Record</h2>
                  <div style={subtitleStyle}>The canonical hash and Soroban transaction returned by the backend anchor flow.</div>
                </div>
                {anchorPayload ? (
                  <div style={{ display: "grid", gap: "0.75rem" }}>
                    <div style={badgeStyle(anchorResult?.ok ? "good" : anchorResult?.stub ? "warn" : "danger")}>
                      {anchorResult?.ok ? "Anchored on Soroban" : anchorResult?.stub ? "Stubbed" : "Anchor Failed"}
                    </div>
                    <Field label="Contract Key" value={anchorPayload.contract_key} copyValue={anchorPayload.contract_key} onCopy={copyValue} />
                    <Field label="Transaction ID" value={anchorResult?.tx_id} copyValue={anchorResult?.tx_id} onCopy={copyValue} />
                    <Field label="Incident Hash" value={anchorPayload.incident_hash} copyValue={anchorPayload.incident_hash} onCopy={copyValue} />
                    <div style={dataCardStyle}>
                      <div style={dataLabelStyle}>Message</div>
                      <div style={dataValueStyle}>{anchorResult?.message}</div>
                    </div>
                  </div>
                ) : (
                  <div style={{ color: "#9ab4d4", lineHeight: 1.7 }}>Anchor the selected incident to populate this pane.</div>
                )}
              </div>

              <div style={panelStyle}>
                <div style={panelHeaderStyle}>
                  <div style={eyebrowStyle}>Verify</div>
                  <h2 style={titleStyle}>Contract Verification</h2>
                  <div style={subtitleStyle}>Compares the backend’s canonical incident hash with the on-chain value returned by the contract.</div>
                </div>
                {verifyPayload ? (
                  <div style={{ display: "grid", gap: "0.75rem" }}>
                    <div style={badgeStyle(toneForVerification(verificationResult))}>
                      {verificationResult?.verified ? "Proof Verified" : verificationResult?.stub ? "Verify Stubbed" : "Verification Failed"}
                    </div>
                    <Field label="Transaction ID" value={verificationResult?.tx_id} copyValue={verificationResult?.tx_id} onCopy={copyValue} />
                    <Field label="Expected Hash" value={verifyPayload.incident_hash} copyValue={verifyPayload.incident_hash} onCopy={copyValue} />
                    <Field label="On-Chain Hash" value={verificationResult?.on_chain_hash} copyValue={verificationResult?.on_chain_hash} onCopy={copyValue} />
                    <div style={dataCardStyle}>
                      <div style={dataLabelStyle}>Message</div>
                      <div style={dataValueStyle}>{verificationResult?.message}</div>
                    </div>
                  </div>
                ) : (
                  <div style={{ color: "#9ab4d4", lineHeight: 1.7 }}>Verify the selected incident to populate this pane.</div>
                )}
              </div>
            </div>
          </section>

          <aside style={{ display: "grid", gap: "1rem", alignContent: "start", minWidth: 0 }}>
            <div style={{ ...panelStyle, minWidth: 0 }}>
              <div style={panelHeaderStyle}>
                <div style={eyebrowStyle}>Audit Trail</div>
                <h2 style={titleStyle}>Timeline</h2>
                <div style={subtitleStyle}>Recent audit entries for the selected incident, including attestation events and transaction IDs.</div>
              </div>
              <div style={{ ...timelineStyle, maxHeight: "540px", overflowY: "auto", paddingRight: "0.15rem" }}>
                {auditPayload?.entries?.length ? (
                  auditPayload.entries.map((entry, index) => (
                    <div key={`${entry.timestamp || index}-${entry.decision || 'entry'}`} style={timelineItemStyle}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.45rem" }}>
                        <div style={badgeStyle(entry.decision === "attested" ? "good" : entry.decision === "approved" ? "warn" : "neutral")}>
                          {entry.decision || "pending"}
                        </div>
                        <div style={{ color: "#8fa9cb", fontSize: "0.82rem" }}>{entry.timestamp || "no timestamp"}</div>
                      </div>
                      <div style={{ color: "#edf5ff", lineHeight: 1.6 }}>{entry.result || entry.explanation || "No result recorded."}</div>
                      {entry.tx_id ? (
                        <div style={{ marginTop: "0.55rem" }}>
                          <button style={copyButtonStyle} onClick={() => copyValue(entry.tx_id, "Timeline transaction ID")}>Copy Tx</button>
                        </div>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div style={{ color: "#9ab4d4", lineHeight: 1.7 }}>No audit entries loaded yet.</div>
                )}
              </div>
            </div>

            <div style={{ ...panelStyle, minWidth: 0 }}>
              <div style={panelHeaderStyle}>
                <div style={eyebrowStyle}>Debug</div>
                <h2 style={titleStyle}>Backend Payloads</h2>
                <div style={subtitleStyle}>Keep the raw API payloads accessible without making them the main view.</div>
              </div>
              <div style={{ display: "grid", gap: "0.85rem", minWidth: 0 }}>
                <pre style={preStyle}>{anchorPayload ? JSON.stringify(anchorPayload, null, 2) : "No attestation response yet."}</pre>
                <pre style={preStyle}>{verifyPayload ? JSON.stringify(verifyPayload, null, 2) : "No verification response yet."}</pre>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
