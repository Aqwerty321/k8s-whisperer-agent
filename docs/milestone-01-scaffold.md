# Milestone 01: Scaffold Baseline

## Snapshot
This milestone captures the first runnable baseline of K8sWhisperer after the initial scaffold and first operational passes were completed.

## Delivered
- FastAPI app with health, incident, Slack callback, poller, and attestation endpoints
- LangGraph workflow covering Observe -> Detect -> Diagnose -> Plan -> Safety Gate -> Execute -> Explain/Log
- Typed shared state in `backend/app/models/state.py`
- Disk-backed LangGraph checkpoint persistence for HITL recovery
- Append-only JSONL audit logging
- Pod-focused Kubernetes integration wrappers, optional read-only node observation, and tightly scoped RBAC manifests
- Slack outbound messaging and inbound approval webhook verification/parsing
- First working auto-remediation path for `CrashLoopBackOff`
- First working HITL recommendation path for `OOMKilled`
- Optional isolated Stellar bonus scaffold
- Demo manifests, helper scripts, tests, and local Makefile targets

## Current Working Paths

### Auto path
- `CrashLoopBackOff`
- detection from pod restart count and related signals
- plan: restart pod
- execute: delete pod
- verify: wait for healthy running state

### HITL path
- `OOMKilled`
- detection from container termination reason and events
- plan: recommend increasing memory and then restarting
- default strict profile keeps the workload change recommendation-only
- safety: requires human approval
- resume: Slack callback resumes persisted graph thread

### Guidance path
- `PendingPod`
- detection from `FailedScheduling` evidence once the pod has been pending for at least five minutes
- plan: recommendation-only operator guidance

### Read-only escalation path
- `NodeNotReady`
- detection from node `Ready=False`
- plan: escalate only, never mutate the node

## Operational Characteristics
- Poller can run in one-shot mode or optional background mode
- Pending approvals survive process restarts through the checkpoint store
- Slack callbacks acknowledge immediately and resume the graph in the background
- Audit records are appended locally and are suitable for later attestation
- MCP tool servers are scaffolded for rubric coverage and later extension

## Known Gaps After This Milestone
- Prometheus-backed `CPUThrottling` is now wired as an optional metric-driven recommendation path
- Multi-namespace observation is not implemented yet
- Background polling still picks one primary anomaly per cycle instead of surfacing every concurrent issue
- Full owner-chain resolution beyond pod owner references is still limited
- Prometheus remains optional and unwired

## Suggested Next Build Slice
1. Improve `PendingPod` diagnosis from scheduling events
2. Add Slack message update capability tied to incident lifecycle
3. Add owner/workload context for safer recommendations
