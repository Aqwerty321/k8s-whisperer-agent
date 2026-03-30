from types import SimpleNamespace

from backend.app.attestation.stellar import StellarAttestor


VALID_TEST_SECRET = "SAITNR5552OEYASNNV3ND4PCHP4R4RGVLFEO6ESY4THPO224IT5L3CTA"


class FakePreparedTransaction:
    def __init__(self) -> None:
        self.signed = False

    def sign(self, _keypair) -> None:
        self.signed = True


class FakeBuilder:
    def __init__(self, *args, **kwargs) -> None:
        self.contract_call = None

    def append_invoke_contract_function_op(self, *, contract_id, function_name, parameters, auth=None, source=None):
        self.contract_call = {
            "contract_id": contract_id,
            "function_name": function_name,
            "parameters": parameters,
        }
        return self

    def set_timeout(self, _seconds: int):
        return self

    def build(self):
        return self


class FakeSorobanServer:
    def __init__(self, _rpc_url: str) -> None:
        self.loaded_account = SimpleNamespace(account_id="GTEST")
        self.prepared = FakePreparedTransaction()
        self.sent = SimpleNamespace(hash="tx-hash-123")
        self.polled = SimpleNamespace(status="SUCCESS")
        self.simulated = SimpleNamespace(results=[SimpleNamespace(xdr="result-xdr")])

    def load_account(self, _account_id: str):
        return self.loaded_account

    def prepare_transaction(self, tx):
        return self.prepared

    def send_transaction(self, tx):
        return self.sent

    def poll_transaction(self, tx_hash: str):
        return self.polled

    def simulate_transaction(self, tx):
        return self.simulated


def test_anchor_incident_returns_real_tx_id(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.attestation.stellar.SorobanServer", FakeSorobanServer)
    monkeypatch.setattr("backend.app.attestation.stellar.TransactionBuilder", FakeBuilder)

    attestor = StellarAttestor(
        network="testnet",
        secret_key=VALID_TEST_SECRET,
        rpc_url="https://soroban-testnet.stellar.org",
        contract_id="CBTXP7ZFNGAZ5TK5CRFKRJUHRKPOBESZ6PWD4CC4ZDNYPI774642LQSN",
    )

    result = attestor.anchor_incident(
        incident_id="incident-123",
        incident_hash="00" * 32,
    )

    assert result["ok"] is True
    assert result["stub"] is False
    assert result["tx_id"] == "tx-hash-123"
    assert result["contract_key"].startswith("incident_")


def test_verify_incident_matches_on_chain_hash(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.attestation.stellar.SorobanServer", FakeSorobanServer)
    monkeypatch.setattr("backend.app.attestation.stellar.TransactionBuilder", FakeBuilder)
    monkeypatch.setattr("backend.app.attestation.stellar.scval.to_native", lambda _xdr: bytes.fromhex("11" * 32))

    attestor = StellarAttestor(
        network="testnet",
        secret_key=VALID_TEST_SECRET,
        rpc_url="https://soroban-testnet.stellar.org",
        contract_id="CBTXP7ZFNGAZ5TK5CRFKRJUHRKPOBESZ6PWD4CC4ZDNYPI774642LQSN",
    )

    result = attestor.verify_incident(
        incident_id="incident-123",
        incident_hash="11" * 32,
        tx_id="tx-hash-123",
    )

    assert result["ok"] is True
    assert result["stub"] is False
    assert result["verified"] is True
    assert result["on_chain_hash"] == "11" * 32
