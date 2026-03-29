from __future__ import annotations

from typing import Any


class StellarAttestor:
    def __init__(
        self,
        *,
        network: str,
        secret_key: str | None,
        rpc_url: str | None,
        contract_id: str | None,
    ) -> None:
        self.network = network
        self.secret_key = secret_key
        self.rpc_url = rpc_url
        self.contract_id = contract_id

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    def anchor_incident(self, *, incident_id: str, incident_hash: str) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "ok": False,
                "stub": True,
                "incident_id": incident_id,
                "incident_hash": incident_hash,
                "tx_id": None,
                "message": "Stellar attestation is not configured.",
            }

        if not self.contract_id:
            return {
                "ok": False,
                "stub": True,
                "incident_id": incident_id,
                "incident_hash": incident_hash,
                "tx_id": None,
                "message": "Contract ID is not configured. Deploy the Soroban contract first.",
            }

        # This scaffold keeps the blockchain path isolated. The concrete Soroban call
        # can be implemented later without changing the API surface or audit flow.
        return {
            "ok": False,
            "stub": True,
            "incident_id": incident_id,
            "incident_hash": incident_hash,
            "tx_id": None,
            "message": "Soroban contract invocation is not wired yet in the scaffold.",
        }

    def verify_incident(self, *, incident_id: str, incident_hash: str, tx_id: str | None) -> dict[str, Any]:
        return {
            "ok": bool(tx_id),
            "stub": True,
            "incident_id": incident_id,
            "incident_hash": incident_hash,
            "tx_id": tx_id,
            "verified": bool(tx_id),
            "message": "Verification is scaffolded; wire the Soroban read path later.",
        }
