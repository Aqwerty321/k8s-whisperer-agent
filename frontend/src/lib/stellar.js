export async function verifyProofLocally({ incidentId }) {
  return {
    incidentId,
    verified: false,
    message: "Frontend verification is scaffolded. Wire the Soroban read path when the bonus is activated.",
  };
}
