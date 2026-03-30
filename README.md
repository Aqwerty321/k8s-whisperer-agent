# K8sWhisperer

K8sWhisperer is an autonomous Kubernetes incident response scaffold for PS1 of the hackathon. It implements the required flow shape with a production-lean structure that can be wired incrementally without later tree surgery.

## What This Scaffold Includes
- FastAPI backend with health, status, incident run, Slack callback, and attestation endpoints
- LangGraph workflow for Observe -> Detect -> Diagnose -> Plan -> Safety Gate -> Execute -> Explain/Log
- Typed shared state model
- Slack Web API integration and inbound webhook signature verification
- Kubernetes client wrappers with pod-focused operations, optional read-only node observation, and optional multi-namespace scanning
- Append-only JSON Lines audit logging
- Disk-backed LangGraph checkpoint persistence for HITL resume across process restarts
- MCP servers for Kubernetes, Slack, and Prometheus tools
- Tightly scoped RBAC with namespace-scoped pod writes by default, optional read-only node access, and demo manifests for `CrashLoopBackOff`, `OOMKilled`, and `Pending Pod`
- Optional isolated Stellar bonus scaffold with backend attestation helpers, a Soroban contract skeleton, and a minimal frontend

## Implemented First-Pass Demo Path
- Real first-pass `CrashLoopBackOff` detection from pod restart counts and event signals
- Real first-pass remediation plan: restart the pod by delete request when the action is low blast-radius and above threshold
- Post-action verification loop that waits for the pod to return to a healthy running state
- Real first-pass `OOMKilled` path that generates a concrete HITL recommendation to raise memory on the owning workload; the default strict profile keeps that change recommendation-only
- Stronger `PendingPod` reasoning that turns scheduling-event evidence into a concrete operator recommendation only after the pod has remained pending for at least five minutes
- Optional Prometheus-backed `CPUThrottling` detection that recommends CPU review when per-pod throttling exceeds the configured threshold
- Optional read-only `NodeNotReady` detection that escalates with node evidence and never mutates nodes when node observation is enabled
- Optional multi-namespace observation through either an explicit namespace list or all-namespace scanning, while keeping single-namespace mode as the default demo profile
- Slack approval flow that pauses the graph, acknowledges the callback immediately, and resumes it through the FastAPI webhook in the background
- Slack incident messages now carry message correlation so follow-up explanations can update the same message when possible
- Slack approval callbacks now update the tracked incident message immediately on approve or reject
- Slack incident messages now use richer status blocks with summary, action, result, and timeline context
- Poller mode suppresses repeated incidents within a configurable dedup window instead of reopening the same alert every cycle
- Pod anomalies now carry lightweight owner/workload hints from pod metadata for better recommendations
- Diagnosis now carries structured evidence alongside the human-readable diagnosis string
- Incident and audit APIs now support lightweight filtering for faster demo inspection
- Persistent checkpoint store at `data/langgraph-checkpoints.pkl`
- Optional background polling loop that can be enabled from config or triggered from the API

## Repository Layout
- `backend/`: core backend app and workflow
- `k8s/`: RBAC and demo manifests
- `scripts/`: local demo helpers
- `tests/`: smoke tests
- `docs/`: scaffold plan and architecture notes
- `contracts/`: optional Soroban contract
- `frontend/`: optional attestation UI

## Quick Start

### 1. Install Python dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment
- Copy `.env.example` to `.env` if needed.
- Fill in Slack credentials, Gemini API key, kubeconfig path, and optional public callback URL.
- If you want checkpoint state somewhere else, set `CHECKPOINT_STORE_PATH`.
- Optional broader observation settings: `OBSERVE_ALL_NAMESPACES=true` scans the whole cluster, while `OBSERVED_NAMESPACES=default,payments` scans a fixed namespace list.

### 3. Run the API
```bash
uvicorn backend.main:app --reload
```

Or:
```bash
make run
```

### 4. Verify the app
```bash
curl http://localhost:8000/health
```

### 5. Prepare minikube demo assets
```bash
bash scripts/setup_minikube.sh
bash scripts/deploy_demo.sh
```

### 6. Start a callback tunnel
```bash
bash scripts/tunnel.sh
```

Use the resulting public URL in your Slack app interactive callback settings and `PUBLIC_BASE_URL`.

For a stable custom-domain setup, use the named tunnel workflow documented in `docs/stable-domain-tunnel.md`.

### 7. Run tests
```bash
make test
```

### 8. Run the Prometheus MCP server
```bash
make prometheus-mcp
```

This starts the typed Prometheus MCP server backed by `PROMETHEUS_URL`. If Prometheus is not configured or reachable, the server still starts but metric queries return explicit error payloads instead of silently failing.

### 8a. Run the kubectl MCP server
```bash
make kubectl-mcp
```

### 8b. Run the Slack MCP server
```bash
make slack-mcp
```

### 9. Start a local Prometheus bonus path
```bash
make prometheus-up
```

This starts a local Prometheus container on `http://127.0.0.1:9090` and scrapes real minikube cAdvisor metrics through `kubectl proxy`. It is intended as an optional bonus/demo path for Prometheus MCP rather than part of the main judge flow.

Together, the repo now exposes typed MCP servers for Kubernetes, Slack, and Prometheus.

## Containerized Backend

### Build the API image locally
```bash
make docker-build
```

### Build and deploy into minikube
```bash
make deploy-backend
```

This uses the existing tightly scoped RBAC and deploys the backend as `Deployment/k8s-whisperer` with `Service/k8s-whisperer` on port `8010`.

If you need live Slack or Gemini credentials in-cluster, create a secret first:

```bash
kubectl create secret generic k8s-whisperer-secrets \
  --from-literal=slack_bot_token="$SLACK_BOT_TOKEN" \
  --from-literal=slack_signing_secret="$SLACK_SIGNING_SECRET" \
  --from-literal=gemini_api_key="$GEMINI_API_KEY"
```

Or start from the checked-in template at `k8s/backend-secret.template.yaml` and replace the placeholder values before applying it.

If you want live Soroban attestation in-cluster, add the Stellar values to the same secret:

```bash
kubectl create secret generic k8s-whisperer-secrets \
  -n default \
  --from-literal=slack_bot_token="$SLACK_BOT_TOKEN" \
  --from-literal=slack_signing_secret="$SLACK_SIGNING_SECRET" \
  --from-literal=gemini_api_key="$GEMINI_API_KEY" \
  --from-literal=stellar_rpc_url="https://soroban-testnet.stellar.org" \
  --from-literal=stellar_secret_key="$STELLAR_SECRET_KEY" \
  --from-literal=stellar_contract_id="$STELLAR_CONTRACT_ID" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Route the public callback URL into the in-cluster backend
```bash
make public-bridge
```

This keeps Cloudflare pointed at local port `8010`, but serves that port from `svc/k8s-whisperer` via `kubectl port-forward`.

### Reset the demo state
```bash
make demo-reset
```

### Fully prepare the demo environment
```bash
make demo-ready
```

### Show a live demo snapshot
```bash
make demo-snapshot
```

### Reset OOMKilled demo back to the failing baseline
```bash
make demo-reset-oomkill
```

### Prune old demo incidents and audit noise
```bash
make demo-prune
```

### Backup local approval path
```bash
bash scripts/approve_incident.sh
```

This simulates a signed Slack callback against the local backend for the newest pending incident and is intended only as a demo fallback if Slack or Cloudflare is unavailable.

If you are running the API through `make run` or default `uvicorn` on port `8000`, invoke it as `BASE_URL=http://127.0.0.1:8000 bash scripts/approve_incident.sh`.

### Export the latest incident report
```bash
bash scripts/export_incident_report.sh
```

## Core API Endpoints
- `GET /health`
- `GET /api/status`
- `GET /api/incidents/{incident_id}`
- `GET /api/incidents`
- `GET /api/incidents/{incident_id}/summary`
- `GET /api/audit`
- `GET /api/audit/{incident_id}`
- `POST /api/incidents/run-once`
- `POST /api/poller/run-once`
- `POST /api/poller`
- `POST /api/slack/actions`
- `POST /api/attest`
- `POST /api/attest/verify`

## Demo Flow
1. Start the FastAPI app.
2. Start minikube and apply RBAC.
3. Deploy one or more demo workloads from `k8s/demo/`.
4. Call `POST /api/incidents/run-once` to run a single observe/detect cycle.
5. `CrashLoopBackOff` should auto-route to a pod restart in the first pass when confidence and blast-radius checks pass.
6. `OOMKilled` should route to HITL with a concrete recommendation to increase memory on the owning workload and then restart.
7. If a plan needs approval, K8sWhisperer sends a Slack approval request and waits.
8. Clicking `Approve` or `Reject` resumes the graph via the FastAPI webhook.
9. The result is explained and appended to `audit_log/audit.jsonl`.

## Demo Helpers
- Seed a CrashLoopBackOff incident: `bash scripts/demo_incident.sh crashloop | jq`
- Seed an OOMKilled incident: `bash scripts/demo_incident.sh oomkill | jq`
- Seed a PendingPod incident: `bash scripts/demo_incident.sh pending | jq`
- Full operator runbook: `docs/demo-runbook.md`

## Slack Workflow Status
- The repo includes an automated end-to-end simulated Slack workflow test covering incident creation, HITL pause, webhook callback approval, graph resume, and final audit entry.
- A signed local callback helper at `scripts/approve_incident.sh` exercises the same callback and resume path against the deployed backend for rehearsal and fallback demos.
- The Slack callback endpoint now acknowledges immediately and resumes the incident in the background so slower execution paths do not hold the webhook open.
- Real live Slack still depends on operational setup rather than missing backend pieces:
- configure the Slack app interactive callback URL to the public FastAPI endpoint
- supply live bot token and signing secret
- confirm the bot is invited to the target channel

## Useful Make Targets
- `make install`
- `make run`
- `make test`
- `make demo-setup`
- `make demo-deploy`
- `make tunnel`
- `make poll-once`

## Stable Domain Option
If you control a domain and move DNS to Cloudflare, you can expose the app on a stable hostname instead of a temporary `trycloudflare.com` URL.

- Setup guide: `docs/stable-domain-tunnel.md`
- Named tunnel runner: `bash scripts/tunnel_named.sh`

## Why This Structure Fits PS1
- The full required pipeline is present as explicit graph nodes.
- The shared state is typed and centrally defined.
- The Slack callback path is visible end-to-end instead of being hidden inside framework magic.
- Incident message correlation is explicit in shared state rather than hidden in the Slack client.
- Kubernetes access is narrowly wrapped and paired with RBAC-limited manifests.
- Observation can stay single-namespace for the strict demo profile or expand to optional multi-namespace scans when explicitly configured.
- MCP integration is scaffolded as dedicated typed tool servers, matching the PS rubric.
- The optional Stellar bonus is isolated so it cannot destabilize the remediation loop.

## Optional Stellar Bonus Path
The bonus path is intentionally decoupled from live remediation:

1. Resolve incident locally.
2. Build a stable attestation record from runtime or audit state.
3. Hash the canonical incident record.
4. Anchor the hash on Soroban via the backend attestation path.
5. Persist the resulting transaction ID back into runtime and audit state.
6. Verify the proof through the isolated frontend or `POST /api/attest/verify`.

This prevents the blockchain bonus from becoming a control-path dependency.

### Stellar Setup
Use testnet for all development.

1. Install Soroban CLI

```bash
cargo install --locked soroban-cli
```

2. Generate a local testnet identity

```bash
soroban keys generate dev-admin
soroban keys address dev-admin
soroban keys secret dev-admin
```

3. Fund the account on testnet

```bash
curl "https://friendbot.stellar.org/?addr=$(soroban keys address dev-admin)"
```

4. Add the Soroban testnet network

```bash
soroban network add testnet \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```

5. Build the contract

```bash
rustup target add wasm32v1-none
soroban contract build --manifest-path contracts/incident-attestation/Cargo.toml
```

6. Deploy the contract

```bash
soroban contract deploy \
  --wasm contracts/incident-attestation/target/wasm32v1-none/release/incident_attestation.wasm \
  --source dev-admin \
  --network testnet
```

7. Set local backend env values

```env
STELLAR_NETWORK=testnet
STELLAR_RPC_URL=https://soroban-testnet.stellar.org
STELLAR_SECRET_KEY=<secret from `soroban keys secret dev-admin`>
STELLAR_CONTRACT_ID=<contract id from `soroban contract deploy`>
```

8. Redeploy the backend after updating the Kubernetes secret

```bash
bash scripts/deploy_backend.sh
```

### Proven Live Attestation Flow
The current repo has been validated end-to-end against a deployed Soroban testnet contract:

1. Seed or resolve an incident with `POST /api/incidents/run-once`
2. Anchor it with `POST /api/attest`
3. Confirm a real Soroban transaction ID is returned
4. Verify it with `POST /api/attest/verify`
5. Confirm the on-chain hash matches the backend-computed incident hash

## Assumptions
- Python 3.11+ is installed.
- `minikube`, `kubectl`, and `cloudflared` are available locally.
- Slack app credentials and Gemini API credentials are supplied through `.env`.
- The Soroban bonus path now requires Soroban CLI plus a funded Stellar testnet account and deployed contract.

## Current Scaffold Boundaries
- Prometheus is not wired yet.
- The Gemini path includes deterministic fallbacks for local smoke testing.
- The Soroban backend path is wired for testnet anchoring and verification, but the frontend is still a lightweight operator console rather than a polished audit product.
- The checkpoint store is local file-backed, not a shared database-backed runtime store.
- `OOMKilled` now has a real HITL recommendation path, but the actual workload memory patch remains intentionally manual in the first pass.
- `Pending Pod` now has a better recommendation path, but still does not mutate cluster resources automatically.
- `CPUThrottling` now depends on a reachable Prometheus endpoint exposing container throttling metrics; without Prometheus configured, that anomaly path stays inactive.
- Workload ownership is inferred only from pod owner references in the current namespace-scoped view; full owner-chain resolution is not implemented yet.
- Audit history is exposed through simple file-backed read endpoints, not a database-backed query service.
- Live Slack E2E still depends on real workspace credentials and a reachable callback URL, although the same callback and resume path is now covered by automated tests and signed local rehearsal.
