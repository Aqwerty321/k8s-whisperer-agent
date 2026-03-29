# Milestone 01: Scaffold Baseline

## Snapshot
This milestone captures the first runnable baseline of K8sWhisperer after the initial scaffold and first operational passes were completed.

## Delivered
- FastAPI app with health, incident, Slack callback, poller, and attestation endpoints
- LangGraph workflow covering Observe -> Detect -> Diagnose -> Plan -> Safety Gate -> Execute -> Explain/Log
- Typed shared state in `backend/app/models/state.py`
- Disk-backed LangGraph checkpoint persistence for HITL recovery
- Append-only JSONL audit logging
- Pod-focused Kubernetes integration wrappers and RBAC manifests
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
- safety: requires human approval
- resume: Slack callback resumes persisted graph thread

## Operational Characteristics
- Poller can run in one-shot mode or optional background mode
- Pending approvals survive process restarts through the checkpoint store
- Audit records are appended locally and are suitable for later attestation
- MCP tool servers are scaffolded for rubric coverage and later extension

## Known Gaps After This Milestone
- `PendingPod` still needs more specific diagnosis and recommendation quality
- Slack currently posts/update flow can be made more operator-friendly
- Background polling does not yet de-duplicate repeated incidents aggressively
- Owner-workload discovery is not yet implemented for safe workload patch suggestions
- Prometheus remains optional and unwired

## Suggested Next Build Slice
1. Improve `PendingPod` diagnosis from scheduling events
2. Add Slack message update capability tied to incident lifecycle
3. Add owner/workload context for safer recommendations
