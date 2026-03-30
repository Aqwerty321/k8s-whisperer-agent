export async function verifyProofLocally({ incidentId, txId }) {
  const response = await fetch("/api/attest/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ incident_id: incidentId, tx_id: txId || null }),
  });

  return response.json();
}
