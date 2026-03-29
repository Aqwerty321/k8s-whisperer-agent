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
- Slack button clicks resume a paused graph run using the `incident_id` as the LangGraph thread ID.
- The audit log persists every completed incident locally as JSON Lines.
- LangGraph checkpoints are persisted to a local file-backed saver so pending approvals survive process restarts.

## Key Modules
- `backend/app/models/state.py`: shared typed state and incident record types
- `backend/app/agent/nodes.py`: graph node implementations for the PS flow, including first-pass CrashLoopBackOff remediation
- `backend/app/agent/checkpointer.py`: disk-backed LangGraph checkpoint saver
- `backend/app/agent/safety.py`: threshold and denylist based routing
- `backend/app/integrations/*`: thin wrappers for Kubernetes, Slack, and Gemini
- `backend/app/mcp/*`: typed MCP servers for Kubernetes and Slack tools
- `backend/app/attestation/*`: optional Stellar bonus path, isolated from the core flow

## First Implemented Live Path
- Observe collects pod summaries and events.
- Detect converts restart-heavy pods and matching events into `CrashLoopBackOff` anomalies.
- Diagnose collects logs and describe-style context.
- Plan chooses `restart_pod` for the first-pass safe remediation.
- Safety auto-approves only when confidence and blast radius allow it.
- Execute deletes the pod and then verifies it returns to a healthy running state.
- Explain and log emits a human-readable summary and appends the audit entry.

## First Implemented HITL Path
- `OOMKilled` is detected from container termination state and related events.
- Diagnose gathers logs and describe-style pod context.
- Plan produces a concrete recommendation to raise memory by roughly 50 percent and then restart the workload.
- Safety routes the plan to HITL because the blast radius is not low.
- Slack approval pauses the graph until the callback resumes the exact graph thread.

## HITL Mechanics
- `hitl` sends an interactive Slack approval request.
- The graph pauses via `interrupt()`.
- FastAPI validates the Slack signature, parses the interactive payload, extracts `incident_id`, and resumes the exact graph thread.
- The runtime can recover pending incidents from the persisted checkpoint store even after a process restart.

## Polling Mode
- The app supports one-shot runs and an optional background polling loop.
- Startup polling is controlled by `ENABLE_BACKGROUND_POLLING`.
- The API exposes `POST /api/poller` to start or stop polling and `POST /api/poller/run-once` for manual cycles.

## Safety Principles
- Auto-remediation only for low blast-radius, above-threshold plans.
- Destructive actions are denylisted by default.
- Human approval is explicit and resumes the graph instead of bypassing it.
- Blockchain is not part of the live remediation loop.
