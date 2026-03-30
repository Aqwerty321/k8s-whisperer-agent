import { Client as SorobanContractClient } from "stellar-sdk/contract";

const NETWORK_PASSPHRASES = {
  testnet: "Test SDF Network ; September 2015",
  public: "Public Global Stellar Network ; September 2015",
  mainnet: "Public Global Stellar Network ; September 2015",
  futurenet: "Test SDF Future Network ; October 2022",
};

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

function sorobanNetworkPassphrase(network, explicitPassphrase) {
  if (explicitPassphrase) return explicitPassphrase;
  return NETWORK_PASSPHRASES[String(network || "").toLowerCase()] || String(network || "");
}

function asHex(value) {
  if (value == null) return null;
  if (typeof value === "string") return value;
  if (value instanceof Uint8Array) {
    return Array.from(value, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  if (Array.isArray(value)) {
    return Array.from(value, (byte) => Number(byte).toString(16).padStart(2, "0")).join("");
  }
  if (typeof Buffer !== "undefined" && Buffer.isBuffer?.(value)) {
    return value.toString("hex");
  }
  return String(value);
}

async function readOnChainIncidentHash({ contractId, contractKey, rpcUrl, networkPassphrase }) {
  const client = await SorobanContractClient.from({
    contractId,
    rpcUrl,
    networkPassphrase,
    allowHttp: rpcUrl.startsWith("http://"),
  });
  const tx = await client.get({ incident_id: contractKey });
  const result = tx?.result;
  if (!result) {
    throw new Error("No on-chain incident hash found for this contract key.");
  }
  return asHex(result);
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

export async function fetchIncidentProof(incidentId) {
  const response = await fetch(`/api/attest/${incidentId}/proof`);
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

async function verifyProofViaBackend({ incidentId, txId }) {
  const response = await fetch("/api/attest/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ incident_id: incidentId, tx_id: txId || null }),
  });
  return parseJson(response);
}

export async function verifyProofLocally({ incidentId, txId }) {
  const proof = await fetchIncidentProof(incidentId);
  const soroban = proof?.soroban || {};
  const rpcUrl = soroban.rpc_url;
  const contractId = soroban.contract_id;
  const contractKey = proof.contract_key;
  const networkPassphrase = sorobanNetworkPassphrase(soroban.network, soroban.network_passphrase);

  if (!rpcUrl || !contractId || !contractKey || !soroban.verify_enabled) {
    return {
      incident_id: incidentId,
      incident_hash: proof.incident_hash,
      contract_key: contractKey,
      source: proof.source,
      record: proof.record,
      verification: {
        ok: false,
        stub: true,
        incident_id: incidentId,
        contract_key: contractKey,
        incident_hash: proof.incident_hash,
        tx_id: txId || proof.tx_id || null,
        verified: false,
        message: "Stellar verification is not configured.",
      },
    };
  }

  try {
    const onChainHash = await readOnChainIncidentHash({
      contractId,
      contractKey,
      rpcUrl,
      networkPassphrase,
    });
    const verified = String(onChainHash || "").toLowerCase() === String(proof.incident_hash || "").toLowerCase();

    return {
      incident_id: incidentId,
      incident_hash: proof.incident_hash,
      contract_key: contractKey,
      source: proof.source,
      record: proof.record,
      verification: {
        ok: verified,
        stub: false,
        incident_id: incidentId,
        contract_key: contractKey,
        incident_hash: proof.incident_hash,
        tx_id: txId || proof.tx_id || null,
        verified,
        on_chain_hash: onChainHash,
        message: verified ? "On-chain incident hash matches." : "On-chain incident hash does not match.",
      },
    };
  } catch (error) {
    try {
      const fallbackPayload = await verifyProofViaBackend({
        incidentId,
        txId: txId || proof.tx_id || null,
      });
      if (fallbackPayload?.verification) {
        return fallbackPayload;
      }
    } catch (_fallbackError) {
      // Preserve the original browser-side error below.
    }
    return {
      incident_id: incidentId,
      incident_hash: proof.incident_hash,
      contract_key: contractKey,
      source: proof.source,
      record: proof.record,
      verification: {
        ok: false,
        stub: false,
        incident_id: incidentId,
        contract_key: contractKey,
        incident_hash: proof.incident_hash,
        tx_id: txId || proof.tx_id || null,
        verified: false,
        message: `Soroban verification failed: ${error instanceof Error ? error.message : String(error)}`,
      },
    };
  }
}
