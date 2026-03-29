# K8sWhisperer

K8sWhisperer is an autonomous Kubernetes incident response scaffold for PS1 of the hackathon. It implements the required flow shape with a production-lean structure that can be wired incrementally without later tree surgery.

## What This Scaffold Includes
- FastAPI backend with health, status, incident run, Slack callback, and attestation endpoints
- LangGraph workflow for Observe -> Detect -> Diagnose -> Plan -> Safety Gate -> Execute -> Explain/Log
- Typed shared state model
- Slack Web API integration and inbound webhook signature verification
- Kubernetes client wrappers with pod-focused operations
- Append-only JSON Lines audit logging
- Disk-backed LangGraph checkpoint persistence for HITL resume across process restarts
- MCP servers for Kubernetes and Slack tools
- Namespace-scoped RBAC and demo manifests for `CrashLoopBackOff`, `OOMKilled`, and `Pending Pod`
- Optional isolated Stellar bonus scaffold with backend attestation helpers, a Soroban contract skeleton, and a minimal frontend

## Implemented First-Pass Demo Path
- Real first-pass `CrashLoopBackOff` detection from pod restart counts and event signals
- Real first-pass remediation plan: restart the pod by delete request when the action is low blast-radius and above threshold
- Post-action verification loop that waits for the pod to return to a healthy running state
- Real first-pass `OOMKilled` path that generates a concrete HITL recommendation to raise memory and then restart the workload
- Slack approval flow that pauses the graph and resumes it through the FastAPI webhook
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

### 7. Run tests
```bash
make test
```

## Core API Endpoints
- `GET /health`
- `GET /api/status`
- `GET /api/incidents/{incident_id}`
- `POST /api/incidents/run-once`
- `POST /api/poller/run-once`
- `POST /api/poller`
- `POST /api/slack/actions`
- `POST /api/attest`

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

## Useful Make Targets
- `make install`
- `make run`
- `make test`
- `make demo-setup`
- `make demo-deploy`
- `make tunnel`
- `make poll-once`

## Why This Structure Fits PS1
- The full required pipeline is present as explicit graph nodes.
- The shared state is typed and centrally defined.
- The Slack callback path is visible end-to-end instead of being hidden inside framework magic.
- Kubernetes access is narrowly wrapped and paired with RBAC-limited manifests.
- MCP integration is scaffolded as dedicated typed tool servers, matching the PS rubric.
- The optional Stellar bonus is isolated so it cannot destabilize the remediation loop.

## Optional Stellar Bonus Path
The bonus path is intentionally decoupled from live remediation:

1. Resolve incident locally.
2. Hash the incident record.
3. Anchor the hash via the backend attestation path.
4. Store transaction metadata back into the local record.
5. Verify proof through the isolated frontend.

This prevents the blockchain bonus from becoming a control-path dependency.

## Assumptions
- Python 3.11+ is installed.
- `minikube`, `kubectl`, and `cloudflared` are available locally.
- Slack app credentials and Gemini API credentials are supplied through `.env`.
- The Soroban bonus path may need extra tooling later for actual on-chain deployment.

## Current Scaffold Boundaries
- Prometheus is not wired yet.
- The Gemini path includes deterministic fallbacks for local smoke testing.
- The Soroban contract invocation is intentionally stubbed until the bonus path is activated.
- The checkpoint store is local file-backed, not a shared database-backed runtime store.
- `OOMKilled` now has a real HITL recommendation path, but the actual workload memory patch remains intentionally manual in the first pass.
- `Pending Pod` still routes through a lighter placeholder path.
