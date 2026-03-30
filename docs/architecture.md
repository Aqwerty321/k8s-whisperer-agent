# K8sWhisperer Architecture

## Core Flow
The scaffold follows the PS1 control loop directly:

1. `observe`
2. `detect`
3. `diagnose`
4. `plan`
5. `safety_gate`
6. `execute` or `hitl`
7. `explain_log`

## Runtime Shape
- FastAPI hosts the health endpoint, incident endpoints, Slack callback webhook, and optional attestation endpoint.
- LangGraph owns the workflow state and pause/resume behavior.
- Slack button clicks are acknowledged immediately and resume a paused graph run in the background using the `incident_id` as the LangGraph thread ID.
- The audit log persists every completed incident locally as JSON Lines.
- LangGraph checkpoints are persisted to a local file-backed saver so pending approvals survive process restarts.

## Key Modules
- `backend/app/models/state.py`: shared typed state and incident record types
- `backend/app/agent/nodes.py`: graph node implementations for the PS flow, including first-pass CrashLoopBackOff remediation
- `backend/app/agent/checkpointer.py`: disk-backed LangGraph checkpoint saver
- `backend/app/agent/safety.py`: threshold and denylist based routing
- `backend/app/integrations/*`: thin wrappers for Kubernetes, Slack, and Gemini
- `backend/app/mcp/*`: typed MCP servers for Kubernetes, Slack, and Prometheus tools
- `backend/app/attestation/*`: optional Stellar bonus path, isolated from the core flow

## First Implemented Live Path
- Observe collects pod summaries, node summaries, and namespace events.
- By default, observation stays scoped to the configured namespace for a safer demo profile.
- Optional settings can widen observation to an explicit namespace list or all namespaces without changing the downstream state shape.
- Detect converts restart-heavy pods and matching events into `CrashLoopBackOff` anomalies.
- Diagnose collects logs and describe-style context.
- Plan chooses `restart_pod` for the first-pass safe remediation.
- Safety auto-approves only when confidence and blast radius allow it.
- Execute deletes the pod and then verifies that the pod, or a healthy replacement from the same Deployment, returns to a healthy running state.
- Explain and log emits a human-readable summary and appends the audit entry.

## First Implemented HITL Path
- `OOMKilled` is detected from container termination state and related events.
- Diagnose gathers logs and describe-style pod context.
- Plan produces a concrete recommendation to raise memory by roughly 50 percent on the owning workload.
- In the default strict profile, approval records the recommendation but does not patch the workload automatically.
- Safety routes the plan to HITL because the blast radius is not low.
- Slack approval pauses the graph until the callback acknowledges and resumes the exact graph thread in the background.

## Improved Pending Path
- `PendingPod` uses `FailedScheduling` events and pod status context together.
- Detection only triggers once the pod has remained pending for at least five minutes.
- The evidence is merged into the anomaly record rather than being lost between nodes.
- The plan now gives a concrete operator recommendation based on the scheduling reason, such as insufficient memory, CPU pressure, selectors, or taints.

## Optional Read-Only Node Path
- `NodeNotReady` can be detected from the observed node snapshot when the `Ready` condition is `False`.
- This path is gated behind optional node-read observation so the default manifest can stay pod-scoped.
- Diagnose uses serialized node condition evidence instead of pod logs.
- Plan is escalation-only and never mutates nodes.

## Deduplication
- Background polling uses a runtime incident tracker to suppress repeated detections for the same anomaly signature.
- Suppression is keyed by namespace, anomaly type, resource kind, and resource name.
- Open incidents are suppressed immediately on repeat, and recently resolved incidents are suppressed until the dedup window expires.

## Workload Hints
- Pod-derived anomalies now carry `workload_kind` and `workload_name` hints from pod owner references when present.
- ReplicaSet owner names are normalized into Deployment hints when the naming pattern clearly indicates a deployment-generated ReplicaSet.
- This stays within the current RBAC model because the data comes from the pod object already being read.

## Structured Diagnosis
- Diagnosis is stored as both a human-readable `diagnosis` string and a `diagnosis_evidence` list.
- Evidence is assembled from anomaly evidence, the first useful log line, and related describe-style events.
- The audit log persists both the diagnosis string and the evidence list.

## Demo Inspection Surface
- Runtime incident listing supports lightweight filtering by status, anomaly type, and search text.
- Audit history supports filtering by incident ID, anomaly type, decision, and free-text search.
- This keeps demo inspection simple without introducing a database or separate dashboard.

## HITL Mechanics
- `hitl` sends an interactive Slack approval request.
- The graph pauses via `interrupt()`.
- FastAPI validates the Slack signature, parses the interactive payload, updates the Slack incident message immediately, and returns an acknowledgment to Slack.
- The actual `resume_incident` call runs in the background using the same `incident_id` to thread mapping.
- The runtime can recover pending incidents from the persisted checkpoint store even after a process restart.
- Slack message timestamps are carried in graph state so follow-up updates can target the same incident message when available.

## Audit Query Surface
- The append-only JSONL audit log remains the source of truth for completed incidents.
- FastAPI exposes recent-history and per-incident read endpoints directly over that log for demoability.

## Incident Query Surface
- FastAPI also exposes runtime-backed incident list and summary endpoints.
- These summary views merge current graph state with audit history so operators can inspect active and completed incidents without reading raw checkpoint data.

## Polling Mode
- The app supports one-shot runs and an optional background polling loop.
- Startup polling is controlled by `ENABLE_BACKGROUND_POLLING`.
- The API exposes `POST /api/poller` to start or stop polling and `POST /api/poller/run-once` for manual cycles.
- Broader observation is controlled by `OBSERVE_ALL_NAMESPACES` or `OBSERVED_NAMESPACES`.

## Safety Principles
- Auto-remediation only for low blast-radius, above-threshold plans.
- Destructive actions are denylisted by default.
- Human approval is explicit and resumes the graph instead of bypassing it.
- Pod writes remain namespace-scoped by default. Optional node access is read-only when explicitly enabled.
- Blockchain is not part of the live remediation loop.
