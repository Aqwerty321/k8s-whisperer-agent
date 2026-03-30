from __future__ import annotations

from binascii import unhexlify
from typing import Any

from stellar_sdk import Keypair, Network, SorobanServer, TransactionBuilder, scval

from .hasher import contract_incident_key


NETWORK_PASSPHRASES = {
    "testnet": Network.TESTNET_NETWORK_PASSPHRASE,
    "public": Network.PUBLIC_NETWORK_PASSPHRASE,
    "mainnet": Network.PUBLIC_NETWORK_PASSPHRASE,
    "futurenet": Network.FUTURENET_NETWORK_PASSPHRASE,
}


def network_passphrase_for(network: str) -> str:
    return NETWORK_PASSPHRASES.get(str(network).lower(), network)


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
        return bool(self.secret_key and self.rpc_url)

    def anchor_incident(self, *, incident_id: str, incident_hash: str) -> dict[str, Any]:
        contract_key = contract_incident_key(incident_id)
        if not self.is_configured():
            return {
                "ok": False,
                "stub": True,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": None,
                "message": "Stellar attestation is not configured.",
            }

        if not self.contract_id:
            return {
                "ok": False,
                "stub": True,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": None,
                "message": "Contract ID is not configured. Deploy the Soroban contract first.",
            }

        try:
            server = SorobanServer(self.rpc_url)
            keypair = Keypair.from_secret(self.secret_key)
            source_account = server.load_account(keypair.public_key)
            tx = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self._network_passphrase(),
                    base_fee=100,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="anchor",
                    parameters=[
                        scval.to_symbol(contract_key),
                        scval.to_bytes(unhexlify(incident_hash)),
                    ],
                )
                .set_timeout(60)
                .build()
            )
            prepared = server.prepare_transaction(tx)
            prepared.sign(keypair)
            send_response = server.send_transaction(prepared)
            tx_hash = getattr(send_response, "hash", None)
            poll_response = server.poll_transaction(tx_hash)
            status = str(getattr(poll_response, "status", "UNKNOWN"))
            if not status.endswith("SUCCESS"):
                return {
                    "ok": False,
                    "stub": False,
                    "incident_id": incident_id,
                    "contract_key": contract_key,
                    "incident_hash": incident_hash,
                    "tx_id": tx_hash,
                    "message": f"Soroban transaction failed with status {status}.",
                }
            return {
                "ok": True,
                "stub": False,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": tx_hash,
                "message": "Incident hash anchored on Soroban.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "stub": False,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": None,
                "message": f"Soroban anchor failed: {exc}",
            }

    def verify_incident(self, *, incident_id: str, incident_hash: str, tx_id: str | None) -> dict[str, Any]:
        contract_key = contract_incident_key(incident_id)

        if not self.contract_id or not self.rpc_url:
            return {
                "ok": False,
                "stub": True,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": tx_id,
                "verified": False,
                "message": "Stellar verification is not configured.",
            }

        try:
            server = SorobanServer(self.rpc_url)
            source_account = server.load_account(Keypair.from_secret(self.secret_key).public_key) if self.secret_key else None
            tx = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self._network_passphrase(),
                    base_fee=100,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="get",
                    parameters=[scval.to_symbol(contract_key)],
                )
                .set_timeout(60)
                .build()
            )
            simulation = server.simulate_transaction(tx)
            results = getattr(simulation, "results", None) or []
            if not results:
                return {
                    "ok": False,
                    "stub": False,
                    "incident_id": incident_id,
                    "contract_key": contract_key,
                    "incident_hash": incident_hash,
                    "tx_id": tx_id,
                    "verified": False,
                    "message": "No on-chain incident hash found for this contract key.",
                }

            on_chain_value = scval.to_native(results[0].xdr)
            if isinstance(on_chain_value, bytes):
                on_chain_value = on_chain_value.hex()
            elif on_chain_value is None:
                return {
                    "ok": False,
                    "stub": False,
                    "incident_id": incident_id,
                    "contract_key": contract_key,
                    "incident_hash": incident_hash,
                    "tx_id": tx_id,
                    "verified": False,
                    "message": "No on-chain incident hash found for this contract key.",
                }
            verified = on_chain_value.lower() == incident_hash.lower()
            return {
                "ok": verified,
                "stub": False,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": tx_id,
                "verified": verified,
                "on_chain_hash": on_chain_value,
                "message": "On-chain incident hash matches." if verified else "On-chain incident hash does not match.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "stub": False,
                "incident_id": incident_id,
                "contract_key": contract_key,
                "incident_hash": incident_hash,
                "tx_id": tx_id,
                "verified": False,
                "message": f"Soroban verification failed: {exc}",
            }

    def _network_passphrase(self) -> str:
        return network_passphrase_for(self.network)
