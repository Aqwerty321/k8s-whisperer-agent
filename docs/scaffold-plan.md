# K8sWhisperer Scaffold Plan

## Status
- This document captures the agreed scaffold plan before implementation.
- The goal is to preserve the build shape and decisions in-repo so future work can resume without relying on chat history.
- Current focus: build a runnable core scaffold for PS1 first, while keeping the optional Stellar bonus isolated.
- Progress update: the scaffold has now been implemented, including file-backed graph checkpoints, live `CrashLoopBackOff` remediation, a strict `OOMKilled` recommendation path, five-minute `PendingPod` gating, and a tested Slack callback resume flow.

## Fixed Constraints
- Development environment: WSL2
- Python: 3.11+
- Main orchestrator: LangGraph
- LangChain: lightweight helper only if needed
- Core LLM: cloud-hosted only
- Slack outbound: Slack Web API
- Slack inbound approvals: FastAPI webhook endpoints
- Public callback tunnel: one simple tunnel only, prefer `cloudflared`
- Demo cluster: `minikube`
- Kubernetes access: tightly scoped pod writes plus optional read-only node access
- Prometheus: optional and non-blocking
- Optional blockchain bonus: Stellar only, isolated from the remediation control loop

## Primary Build Goals
1. Scaffold runs immediately.
2. Slack callback path is obvious and testable.
3. LangGraph state model is explicit and typed.
4. Audit log is append-only and human-readable.
5. Every risky action goes through a safety gate.
6. Irreversible or high-risk actions are off by default.
7. Demoability is prioritized over completeness.

## Recommended Changes To The Suggested Repo Shape
- Use `backend/app/audit/` instead of `backend/app/logging/` to avoid shadowing Python's standard `logging` module.
- Add `backend/app/mcp/` because the PS explicitly scores MCP integration with typed tool definitions.
- Keep `backend/app/attestation/`, `contracts/`, and `frontend/` isolated so the core agent works even when Web3 is disabled.
- Keep the FastAPI entrypoint at `backend/main.py` so `uvicorn backend.main:app` is straightforward.

## Planned Repository Tree

```text
k8s-whisperer-agent/
├── .env
├── .env.example
├── .gitignore
├── LICENSE
├── PS.md
├── PS/
├── README.md
├── requirements.txt
├── backend/
│   ├── __init__.py
│   ├── main.py
│   └── app/
│       ├── __init__.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── models/
│       │   ├── __init__.py
│       │   └── state.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── graph.py
│       │   ├── nodes.py
│       │   └── safety.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── routes.py
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── slack/
│       │   │   ├── __init__.py
│       │   │   └── client.py
│       │   ├── k8s/
│       │   │   ├── __init__.py
│       │   │   └── client.py
│       │   └── llm/
│       │       ├── __init__.py
│       │       └── client.py
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── kubectl_server.py
│       │   └── slack_server.py
│       ├── audit/
│       │   ├── __init__.py
│       │   └── logger.py
│       └── attestation/
│           ├── __init__.py
│           ├── hasher.py
│           └── stellar.py
├── contracts/
│   └── incident-attestation/
│       ├── Cargo.toml
│       └── src/
│           └── lib.rs
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── lib/
│           └── stellar.js
├── k8s/
│   ├── rbac.yaml
│   └── demo/
│       ├── crashloop.yaml
│       ├── oomkill.yaml
│       └── pending.yaml
├── scripts/
│   ├── setup_minikube.sh
│   ├── deploy_demo.sh
│   └── tunnel.sh
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_safety.py
│   └── test_audit.py
└── docs/
    ├── scaffold-plan.md
    └── architecture.md
```

## Core Runtime Shape
- One FastAPI app process hosts the API, graph entrypoints, and Slack callback webhook.
- LangGraph owns the incident workflow state and routing.
- The graph compiles with `MemorySaver` first for demo simplicity.
- Slack callbacks resume paused runs using a correlation from `incident_id` to LangGraph thread/run context.
- Kubernetes access is wrapped in a small client layer and surfaced again through typed MCP tools.
- Audit logging is append-only and local-first.

## Shared State Model
The graph should use one explicit typed shared state. This should be the central contract between nodes.

Planned state fields:
- `incident_id`
- `namespace`
- `events: list[dict]`
- `anomalies: list[Anomaly]`
- `diagnosis: str`
- `plan: RemediationPlan | None`
- `approved: bool | None`
- `result: str`
- `audit_log: list[LogEntry]`
- `slack_channel: str | None`
- `awaiting_human: bool`
- `error: str | None`

Planned typed records:
- `Anomaly`
- `RemediationPlan`
- `LogEntry`

## Graph Topology

```text
START -> observe -> detect
detect -> observe          if no actionable anomalies
detect -> diagnose         if anomaly found
diagnose -> plan
plan -> safety_gate
safety_gate -> execute     if auto-approved
safety_gate -> hitl        if approval required
hitl -> execute            if approved by Slack callback
hitl -> explain_log        if rejected
execute -> explain_log
explain_log -> observe
```

## Node Responsibilities

### `observe_node`
- Collect cluster events, pod summaries, node summaries, and lightweight workload context.
- Normalize data into shared state.
- Keep first implementation simple: namespace-scoped pod operations with optional read-only node observation.

### `detect_node`
- Convert observed signals into typed anomalies.
- Start with a stubbed Gemini-backed classification path and a deterministic fallback for smoke testing.

### `diagnose_node`
- Pull logs, `describe` data, and recent events for the affected workload.
- Produce a concise diagnosis string with evidence references.

### `plan_node`
- Build a `RemediationPlan` with action, parameters, confidence, and blast radius.
- Prefer a small plan schema that is easy to route and test.

### `safety_gate_node`
- Apply confidence threshold, blast-radius checks, and destructive-action denylist rules.
- Decide between auto-execute and HITL.

### `hitl_node`
- Send Slack approval request with `Approve` and `Reject` buttons.
- Pause the graph cleanly for later resume.

### `execute_node`
- Run approved action through the Kubernetes tool layer.
- Re-check workload state after a short delay.
- Capture raw outcome and a normalized result summary.

### `explain_log_node`
- Generate the plain-English explanation.
- Send/update Slack message.
- Append the audit log entry.

## Safety Model
- Auto-execution is allowed only when confidence is above the configured threshold, blast radius is `low`, and the action is not denylisted.
- High-risk or destructive actions are off by default.
- Node actions involving deployments, nodes, rollbacks, drains, or broad patches should route to HITL unless explicitly added later.
- `Node NotReady` must never auto-drain.
- Restart alone is not considered success; verify step is required.

## Slack Integration Plan
- Load bot token, signing secret, default channel, and public base URL from env.
- Use Slack Web API for outbound messages.
- Use FastAPI webhook endpoint for interactive button callbacks.
- Verify Slack signing secret on every inbound callback.
- Include `incident_id` and decision metadata in button payloads for correlation.
- Keep callback handling explicit and easy to trace from request to graph resume.

## Kubernetes Integration Plan
- Use the Python Kubernetes client instead of shelling out to `kubectl` for the default path.
- Keep tool wrappers narrow and typed.
- Support initial operations needed for the first demo path:
  - list/read pods
  - list/read events
  - get pod logs
  - describe-equivalent summary fetch
  - delete pod
  - patch targeted pod or workload fields only where explicitly allowed
- RBAC keeps pod writes namespace-scoped by default; optional node observation can be enabled separately with read-only node access.

## MCP Plan
- Add proper MCP server modules for `kubectl` and Slack to satisfy the rubric expectation.
- Each MCP tool should have a typed interface and map to a concrete integration method.
- The rest of the app can import the underlying integration clients directly; MCP should not force a separate runtime architecture.

## Audit Logging Plan
- Use append-only local storage first.
- Prefer JSON Lines for durable, machine-readable incident history.
- Each entry should capture:
  - timestamp
  - incident ID
  - anomaly summary
  - diagnosis
  - plan
  - approval outcome
  - execution result
  - human-readable explanation
  - optional attestation transaction ID

## Optional Stellar Bonus Plan
Keep the blockchain path separate from the live incident loop.

Intended flow:
1. Incident resolves locally.
2. Backend computes canonical hash of the incident record.
3. Backend or isolated UI triggers Stellar attestation.
4. Transaction ID is stored back into the local audit record.
5. Optional frontend verifies that the on-chain proof matches the local record hash.

Rules for inclusion:
- No chain dependency inside the safety gate or execution path.
- No "random hash storage" with no relation to the incident output.
- Bonus repo must still contain frontend, contract, and integration logic together.

## Planned Backend Attestation Files
- `backend/app/attestation/hasher.py`
  Compute stable SHA-256 incident hashes from canonical JSON.
- `backend/app/attestation/stellar.py`
  Minimal Stellar testnet client wrapper for anchoring and verification helpers.

## Planned Bonus Contract
- One small Soroban contract for storing and checking incident hashes.
- Keep the contract surface intentionally minimal.
- Contract should support anchoring a hash and reading it back for verification.

## Planned Bonus Frontend
- Minimal Vite React app.
- Show anchored incidents and proof status.
- Allow a user to trigger anchoring for a resolved incident and verify stored proof.
- Keep the UI intentionally small and isolated from the core backend.

## Requirements Plan
Planned `requirements.txt` groups:
- FastAPI + Uvicorn
- Pydantic + settings support
- LangGraph
- LangChain core helpers
- Gemini integration package
- Kubernetes client
- Slack SDK
- MCP SDK
- HTTP client
- Pytest for smoke tests
- Stellar SDK as optional but included dependency for scaffold completeness

## Environment Plan
Do not change `.env`.

Potential `.env.example` additions only if needed by the scaffold:
- `STELLAR_NETWORK=testnet`
- `STELLAR_SECRET_KEY=your-stellar-secret`
- `STELLAR_RPC_URL=` or equivalent only if the chosen integration requires it
- `AUDIT_LOG_PATH=` if the logger needs a configurable file path

Existing keys should continue to cover:
- app env and port
- Slack tokens/secrets/channel
- Gemini API key
- kubeconfig and namespace
- poll interval and auto-approve threshold
- optional Prometheus URL
- public callback base URL

## RBAC Plan
Create a minimal `k8s/rbac.yaml` containing:
- `ServiceAccount`
- `Role`
- `RoleBinding`

Planned scope:
- pods: `get`, `list`, `watch`, `delete`, and only narrowly justified patch support
- pods/log: `get`
- events: `get`, `list`, `watch`
- nodes: `get`, `list`, `watch` through a read-only `ClusterRole`

Explicit non-goals for first pass:
- no cluster-admin
- no cluster-wide write permissions
- no node drain permissions
- no broad deployment mutation by default

## Demo Assets Plan
Add namespace-scoped manifests for:
- `crashloop.yaml`
- `oomkill.yaml`
- `pending.yaml`

Add utility scripts for:
- starting `minikube`
- applying RBAC and demo manifests
- starting `cloudflared` tunnel to the FastAPI app

## Test Plan
Add lightweight smoke tests first:
- state model serialization and defaults
- safety routing behavior
- audit log append-only behavior
- optional API health route smoke test if setup stays simple

The first test pass should prove the scaffold is wired correctly without needing a live cluster or live Slack.

## Assumptions
- Python 3.11+ is available in WSL2.
- `minikube` and `kubectl` are installed locally.
- `cloudflared` can be installed separately for callbacks.
- Slack app credentials will be provided through local env.
- Gemini credentials will be provided through local env.
- Soroban/Stellar tooling can be installed later if the bonus path is exercised.

## Non-Goals For The First Scaffold Pass
- Full production persistence for paused graph runs
- Full Prometheus wiring
- Fully tuned prompts
- Complete remediation catalog for every anomaly type
- Deep blockchain workflow integration into the core agent loop

## Phased Implementation Order
1. Foundation files
   Create `requirements.txt`, expand `.gitignore`, and verify `.env.example` keys.
2. Config and models
   Add settings loader and typed graph state models.
3. Audit layer
   Add append-only audit logger.
4. Integration clients
   Add Kubernetes, Slack, and Gemini client wrappers.
5. Safety and nodes
   Add routing policy and placeholder graph node implementations.
6. Graph wiring
   Build and compile the LangGraph flow with conditional edges.
7. API layer
   Add health, status, and Slack callback endpoints.
8. App entrypoint
   Wire FastAPI startup and background loop placeholders.
9. MCP layer
   Add typed MCP server modules for Kubernetes and Slack.
10. Cluster and demo assets
    Add RBAC and demo manifests plus helper scripts.
11. Tests
    Add smoke tests for models, safety logic, and audit behavior.
12. Bonus isolation
    Add attestation backend, Soroban contract skeleton, and minimal frontend.
13. Docs
    Write `README.md` and `docs/architecture.md` after code shape is real.

## Immediate Next Step
Begin implementation with Phase 1 and Phase 2 so the repo becomes runnable as early as possible.
