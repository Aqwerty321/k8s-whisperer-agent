async function parseJson(response) {
  const rawText = await response.text();
  let payload;
  try {
    payload = rawText ? JSON.parse(rawText) : {};
  } catch (_err) {
    payload = { detail: rawText || "Request failed." };
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || "Request failed.";
    throw new Error(detail);
  }
  return payload;
}

export async function fetchIncidentSummary(incidentId) {
  const response = await fetch(`/api/incidents/${incidentId}/summary`);
  return parseJson(response);
}

export async function fetchIncidentList({ search = "", status = "", anomalyType = "" } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  if (anomalyType) params.set("anomaly_type", anomalyType);
  const response = await fetch(`/api/incidents?${params.toString()}`);
  return parseJson(response);
}

export async function fetchIncidentAudit(incidentId) {
  const response = await fetch(`/api/audit/${incidentId}`);
  return parseJson(response);
}

export async function anchorIncident({ incidentId }) {
  const response = await fetch("/api/attest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ incident_id: incidentId }),
  });

  return parseJson(response);
}

export async function verifyProofLocally({ incidentId, txId }) {
  const response = await fetch("/api/attest/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ incident_id: incidentId, tx_id: txId || null }),
  });

  return parseJson(response);
}
