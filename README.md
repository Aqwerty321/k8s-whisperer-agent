# K8sWhisperer

K8sWhisperer is an autonomous Kubernetes incident-response system built for the PS1 DevOps x AI/ML track. It turns live cluster symptoms into scoped, explainable actions through a LangGraph workflow that observes cluster state, detects anomalies, diagnoses likely causes, proposes remediation, applies safety policy, executes safe actions, and records every outcome.

The project is designed for a real `minikube` demo, not a mock-only prototype. Low-blast-radius actions can be executed automatically. Higher-risk actions pause for human approval in Slack and resume through a FastAPI webhook with persistent checkpoint state.

Live Soroban testnet contract ID: `CBTXP7ZFNGAZ5TK5CRFKRJUHRKPOBESZ6PWD4CC4ZDNYPI774642LQSN`

## Problem Statement Alignment

The PS requires an end-to-end incident response loop:

1. Observe
2. Detect
3. Diagnose
4. Plan
5. Safety Gate
6. Execute
7. Explain and Log

K8sWhisperer implements that loop directly in LangGraph and keeps the blockchain work isolated from the remediation control path so the core judged demo remains stable.

## Core Capabilities

- FastAPI backend with health, runtime, incident, audit, Slack callback, and attestation endpoints
- LangGraph workflow with typed shared state and persistent checkpoint recovery
- Namespace-scoped Kubernetes observation and pod-level remediation by default
- Slack approval flow with signed request verification and background graph resume
- Persistent JSONL audit trail with explanation, decision, diagnosis evidence, and result
- Repeatable demo helpers for `CrashLoopBackOff`, `OOMKilled`, and `PendingPod`
- Additional anomaly coverage for `ImagePullBackOff`, `CPUThrottling`, `EvictedPod`, `DeploymentStalled`, and optional `NodeNotReady`
- Typed MCP servers for Kubernetes, Slack, and Prometheus integrations
- Optional Soroban attestation flow for anchoring completed incident records on Stellar testnet
- Desktop-first attestation dashboard with Playwright end-to-end coverage

## Implemented Incident Paths

### Core judged paths
- `CrashLoopBackOff`
  Detects restart-heavy pods, collects logs and describe output, plans a pod restart, auto-approves only when the blast radius is low, and verifies recovery.
- `OOMKilled`
  Detects terminated containers, enriches them with workload resource context when available, gathers diagnosis evidence, produces a memory-increase recommendation, and routes through Slack approval. With workload patching enabled, approved incidents patch the owning `Deployment`, verify rollout, and surface before/after memory values. In the default strict profile, this remains recommendation-only.
- `PendingPod`
  Detects pods that remain pending for at least five minutes, synthesizes scheduling evidence, and produces operator guidance instead of unsafe mutation.

### Additional implemented coverage
- `ImagePullBackOff`
  Extracts image and pull context and routes to operator review.
- `CPUThrottling`
  Uses Prometheus metrics to recommend or optionally patch CPU limits when throttling exceeds the configured threshold.
- `EvictedPod`
  Detects evicted pods and supports low-blast-radius deletion.
- `DeploymentStalled`
  Detects stalled rollouts and escalates to a human.
- `NodeNotReady`
  Optional read-only node observation path that never mutates nodes.

## Architecture

### Workflow
1. `observe`
   Collects pod, deployment, event, optional node, and optional Prometheus metric snapshots.
2. `detect`
   Produces typed anomaly objects with severity, target resource, confidence, and evidence using a heuristic baseline plus a conservative LLM enrichment pass.
3. `diagnose`
   Pulls logs and describe-style context, then generates a short root-cause summary.
4. `plan`
   Produces a remediation plan with action, target, parameters, confidence, blast radius, and HITL requirement.
5. `safety_gate`
   Auto-approves only low-blast-radius, above-threshold, non-denylisted actions.
6. `execute` or `hitl`
   Executes safe actions immediately or pauses for Slack approval and resumes later.
7. `explain_log`
   Generates a plain-English explanation, updates Slack, and appends a persistent audit record.

### Runtime components
- `backend/`
  FastAPI application, LangGraph runtime, integrations, MCP servers, and attestation logic.
- `k8s/`
  RBAC manifests, backend deployment, and demo workloads.
- `scripts/`
  Cluster setup, demo reset, deployment, tunnel, approval fallback, and E2E helpers.
- `contracts/incident-attestation/`
  Soroban smart contract used by the optional attestation path.
- `frontend/`
  Desktop-first React operator console for browsing incidents and verifying attestations.
- `tests/`
  Backend, runtime, Kubernetes, settings, attestation, and deployment-readiness tests.

## Safety Model

- Auto-remediation is limited to low-blast-radius actions above the configured confidence threshold.
- Destructive actions are denylisted by policy.
- Human approval is explicit and resumable through Slack.
- Default RBAC remains namespace-scoped and avoids cluster-admin privileges.
- Optional node observation is read-only.
- The Stellar bonus path is not part of the remediation control loop.

## Repository Layout

```text
backend/     FastAPI app, LangGraph workflow, integrations, MCP servers
contracts/   Soroban smart contract for incident attestation
docs/        Architecture, demo, rubric, and rehearsal notes
frontend/    React attestation dashboard and Playwright tests
k8s/         Backend manifests, RBAC, and demo workloads
scripts/     Setup, deployment, demo, tunnel, and E2E helpers
tests/       Automated backend and integration-oriented tests
```

## Quick Start

### 1. Install Python dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment
- Copy `.env.example` to `.env` if needed.
- Supply Slack credentials, Gemini API key, and Kubernetes access.
- Optional observation settings:
  - `OBSERVE_ALL_NAMESPACES=true`
  - `OBSERVED_NAMESPACES=default,payments`
- Optional strictness and execution settings:
  - `ALLOW_WORKLOAD_PATCHES=false`
  - `ENABLE_NODE_READ_OBSERVATION=false`

### 3. Run the API locally
```bash
uvicorn backend.main:app --reload
```

Or:

```bash
make run
```

### 4. Verify health
```bash
curl http://127.0.0.1:8000/health
```

### 5. Run automated backend tests
```bash
make test
```

## Minikube Deployment

### Prepare the demo cluster
```bash
make demo-setup
make demo-deploy
```

### Build and deploy the backend into minikube
```bash
make deploy-backend
```

This deploys `Deployment/k8s-whisperer` and `Service/k8s-whisperer` on port `8010`.

### Create the backend secret
If you need live Slack, Gemini, or Stellar values in-cluster, create the shared secret first:

```bash
bash scripts/sync_cluster_secrets.sh
```

You can also start from `k8s/backend-secret.template.yaml` and replace placeholder values before applying it.

The sync script preserves existing non-empty cluster values when your local `.env` leaves a field blank, which prevents accidental loss of working Slack or Soroban configuration.

### Bridge the in-cluster service to a local callback port
```bash
make public-bridge
```

This keeps the public callback path pointed at a stable local port while serving traffic from the in-cluster backend.

## Demo Workflow

### Prepare a clean judge-ready state
```bash
make demo-ready
```

### Show a runtime snapshot
```bash
make demo-snapshot
```

### Seed the main demo scenarios
```bash
bash scripts/demo_incident.sh crashloop | jq
bash scripts/demo_incident.sh oomkill | jq
bash scripts/demo_incident.sh pending | jq
```

### Reset the OOMKilled demo to the failing baseline
```bash
make demo-reset-oomkill
```

### Prune old incident and audit noise
```bash
make demo-prune
```

### Local approval fallback
```bash
bash scripts/approve_incident.sh
```

Use this if Slack or the public callback path is unavailable during rehearsal.

## Public Callback Tunnel

### Temporary tunnel
```bash
make tunnel
```

### Stable-domain tunnel
See `docs/stable-domain-tunnel.md` and `scripts/tunnel_named.sh`.

## API Surface

### Runtime and incidents
- `GET /health`
- `GET /api/status`
- `GET /api/incidents`
- `GET /api/incidents/{incident_id}`
- `GET /api/incidents/{incident_id}/summary`
- `GET /api/incidents/{incident_id}/report`

### Audit and demo utilities
- `GET /api/audit`
- `GET /api/audit/{incident_id}`
- `POST /api/incidents/run-once`
- `POST /api/poller/run-once`
- `POST /api/poller`
- `POST /api/demo/prune`
- `POST /api/demo/reset`

### Slack and attestation
- `POST /api/slack/actions`
- `POST /api/attest`
- `POST /api/attest/verify`

## MCP Servers

Run the typed MCP servers directly from the repo:

```bash
make kubectl-mcp
make slack-mcp
make prometheus-mcp
```

The Prometheus bonus path can also be backed by a local Prometheus instance:

```bash
make prometheus-up
```

## Frontend Attestation Console

The frontend is a desktop-first operator surface for browsing incidents, anchoring incident records through the backend attestation API, and verifying on-chain hashes against Soroban from the browser with `stellar-sdk`.

### Install frontend dependencies
```bash
npm --prefix frontend install
```

### Run the frontend locally
```bash
npm --prefix frontend run dev
```

### Run frontend E2E coverage
```bash
npm --prefix frontend run test:e2e
```

The Playwright suite uses `scripts/run_frontend_e2e_stack.sh` to start the local Vite app, port-forward the in-cluster backend, seed an incident, and verify anchor plus verify behavior in the UI.

## Optional Soroban Attestation

The blockchain path is an optional post-incident proof layer. It does not participate in detection, diagnosis, planning, approval, or execution.

### What the attestation path does
1. Builds a canonical incident record from runtime or audit state.
2. Hashes the canonical record in a stable format.
3. Anchors the hash on a Soroban contract.
4. Persists the transaction ID into runtime and audit state.
5. Verifies the on-chain value against the backend-computed hash.

### Soroban setup
Use testnet for development.

1. Install Soroban CLI

```bash
cargo install --locked soroban-cli
```

2. Create a local identity

```bash
soroban keys generate dev-admin
soroban keys address dev-admin
soroban keys secret dev-admin
```

3. Fund the account

```bash
curl "https://friendbot.stellar.org/?addr=$(soroban keys address dev-admin)"
```

4. Add the testnet network

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

7. Configure backend values

```env
STELLAR_NETWORK=testnet
STELLAR_RPC_URL=https://soroban-testnet.stellar.org
STELLAR_SECRET_KEY=<soroban secret>
STELLAR_CONTRACT_ID=<contract id>
```

8. Redeploy the backend

```bash
make deploy-backend
```

### Proven attestation flow
The attestation path has already been validated against a real Soroban testnet contract:

1. Resolve or seed an incident.
2. Call `POST /api/attest`.
3. Confirm a real transaction ID is returned.
4. Verify through either the frontend browser flow or `POST /api/attest/verify`.
5. Confirm the on-chain hash matches the canonical incident hash.

### Web3 bonus submission checklist
- Frontend: `frontend/`
  - React operator console
  - browser-side Stellar integration in `frontend/src/lib/stellar.js`
- Smart contract: `contracts/incident-attestation/`
  - Soroban contract source in `contracts/incident-attestation/src/lib.rs`
  - contract methods: `anchor(...)` and `get(...)`
- Integration logic:
  - backend anchor/verify flow in `backend/app/attestation/stellar.py`
  - attestation API in `backend/app/api/routes.py`
  - frontend verification path using `stellar-sdk/contract` in `frontend/src/lib/stellar.js`
- Network: Stellar testnet
- Current demo contract ID: `CBTXP7ZFNGAZ5TK5CRFKRJUHRKPOBESZ6PWD4CC4ZDNYPI774642LQSN`
- End-to-end proof command:

```bash
bash scripts/proof_soroban.sh
```

## Documentation

- `docs/architecture.md`
- `docs/demo-runbook.md`
- `docs/judge-demo.md`
- `docs/judge-rehearsal-script.md`
- `docs/rubric-mapping.md`
- `docs/Langgraph_state_schema.md`

## Current Status

### Strongly implemented
- Core LangGraph workflow with checkpointed pause and resume
- Stable `CrashLoopBackOff`, `OOMKilled`, and `PendingPod` demo stories
- Hybrid anomaly detection with heuristic baseline, validated LLM enrichment, and safe fallback behavior
- Slack HITL approval and audit logging
- Strict default safety posture and RBAC
- Optional Prometheus-backed CPU throttling support
- Optional multi-namespace observation
- Deployment-aware `OOMKilled` patch generation with explicit before/after memory evidence when patching is enabled
- Optional Soroban attestation with backend anchoring and direct frontend verification
- Desktop-first frontend with Playwright E2E coverage

### Known boundaries
- Detection is intentionally heuristic-led for demo stability; the LLM path is additive, validated, and allowed to enrich or add only supported anomalies.
- The default `OOMKilled` path remains recommendation-only unless workload patching is explicitly enabled.
- `PendingPod`, `ImagePullBackOff`, `DeploymentStalled`, and `NodeNotReady` are intentionally non-destructive guidance or escalation paths.
- Workload patch support is still limited and deployment-focused rather than a fully general workload remediation engine.
- The frontend currently performs browser-side direct contract reads for verification, but anchoring still runs through the backend rather than a wallet-signed browser transaction flow.
- The audit log is file-backed JSONL rather than a database-backed service.

## License

No license file is currently included in this repository.
