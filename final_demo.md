# Final Demo Script

This is the shortest safe judge/demo script for the current repo state.

Use it exactly as written. Every command is a one-liner you can copy-paste.

Assumptions:
- backend is reachable on `http://127.0.0.1:8010`
- Slack callback health is reachable on `https://slack.aqwerty321.me/health`
- Slack `#alerts` is open
- minikube is already running

## Windows To Open

Open these before recording:
- Slack `#alerts`
- browser on the frontend console if you want to show attestation later
- Terminal 1: main command terminal
- Terminal 2: live incident watcher
- Terminal 3: live audit watcher

## Live Watchers

You already verified these, so keep them running during the whole recording.

Terminal 2:

```bash
watch -n 1 'curl -sS http://127.0.0.1:8010/api/incidents | jq'
```

Terminal 3:

```bash
watch -n 1 'curl -sS http://127.0.0.1:8010/api/audit | jq'
```

Say:
"I have live incident state and live audit state visible while the workflow runs."

What to do on screen:
- keep the watcher terminals visible when you trigger each incident
- after each command, pause for a second so the watchers visibly update
- for the Slack approval step, keep the incident watcher visible while you click `Approve`

## 0. Reset To Judge-Ready State

Run:

```bash
make demo-ready
```

Say:
"This resets the runtime state, redeploys the demo workloads if needed, and confirms the backend plus public Slack callback path are healthy."

Run:

```bash
curl -sS http://127.0.0.1:8010/health | jq && curl -sS https://slack.aqwerty321.me/health | jq
```

Say:
"The local backend is healthy, and the public callback path for Slack is healthy too."

Run:

```bash
make demo-snapshot
```

Say:
"This shows the current demo coverage, recent incidents, audit decisions, and whether anything is still waiting on a human."

## 1. CrashLoopBackOff Auto-Remediation

Run:

```bash
CRASH_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh crashloop | tee /tmp/final-demo-crashloop.json | jq -r '.incident_id') && printf 'CRASH_ID=%s\n' "$CRASH_ID"
```

Say:
"First, a low-blast-radius crashloop. K8sWhisperer can auto-approve this because restarting a single unhealthy pod is a scoped action."

What to point at:
- the incident watcher should show `completed`
- no Slack card is expected here because this path is auto-approved

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$CRASH_ID" | jq
```

Say:
"The incident already completed. The system observed the failure, diagnosed it, planned a restart, passed the safety gate, executed it, and logged the result."

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/audit/$CRASH_ID" | jq
```

Say:
"The audit trail records the diagnosis, the decision, and the final remediation result."

## 2. OOMKilled With Human Approval

Run:

```bash
OOM_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh oomkill | tee /tmp/final-demo-oomkill.json | jq -r '.incident_id') && printf 'APPROVE THIS IN SLACK: %s\n' "$OOM_ID"
```

Say:
"Next is an OOMKilled incident. This is higher risk than a simple restart, so K8sWhisperer pauses for explicit human approval in Slack."

What to point at:
- the incident watcher should flip to `awaiting_human`
- this is the path where a Slack card is expected

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$OOM_ID" | jq
```

Say:
"You can see the plan is `patch_pod`, but it is human-gated. The system also surfaces the recommended memory change and the owning workload context."

Action:
- switch to Slack `#alerts`
- open the newest card
- click `Approve`

Say while clicking:
"Slack acknowledges immediately, then the callback resumes the exact paused LangGraph thread in the background."

What to point at right after approval:
- the incident watcher should move from `awaiting_human` to `completed`
- the audit watcher should gain the decision and final result

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$OOM_ID" | jq
```

Say:
"After approval, the incident is resumed and finalized. In the default strict profile, OOMKilled remains human-controlled. When workload patching is enabled, the system can patch and verify the owning Deployment."

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/audit/$OOM_ID" | jq
```

Say:
"The result and decision are persisted, so the human approval path is fully auditable."

## 3. PendingPod Guidance Path

Run:

```bash
PENDING_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh pending | tee /tmp/final-demo-pending.json | jq -r '.incident_id') && printf 'PENDING_ID=%s\n' "$PENDING_ID"
```

Say:
"Finally, here is a path where mutation would be risky or unsupported. Instead of taking an unsafe action, K8sWhisperer gives operator guidance."

What to point at:
- the incident watcher should show another human-reviewed or recommendation-only record
- explain that this one is intentionally not auto-remediated

Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$PENDING_ID" | jq
```

Say:
"This stays recommendation-only. The system surfaces the scheduling evidence and stops short of destructive automation."

## 4. Show Overall Demo State

Run:

```bash
make demo-snapshot
```

Say:
"This is the live scoreboard after the three paths: one auto-remediation, one human-approved path, and one recommendation-only path."

Run:

```bash
curl -sS http://127.0.0.1:8010/api/audit | jq
```

Say:
"Every incident path writes a durable audit trail with explanation, decision, and outcome."

## 5. Optional Incident Report Proof

Run:

```bash
bash scripts/export_incident_report.sh "$OOM_ID"
```

Say:
"The same incident can also be exported as a compact markdown-style report for handoff or review."

## 6. Optional Frontend Attestation Flow

Use this only if you want to show the bonus frontend and Soroban proof flow.

Start the frontend if it is not already running:

```bash
bash scripts/run_frontend_e2e_stack.sh
```

Then in the browser:
- open `http://127.0.0.1:4173`
- search for `CRASH_ID` or `OOM_ID`
- click the incident
- click `Anchor Incident`
- click `Verify Proof`

Say:
"This bonus UI anchors the incident record and verifies the proof without touching the remediation control loop."

If you want a backend proof command instead of the UI:

```bash
curl -sS -X POST http://127.0.0.1:8010/api/attest -H 'Content-Type: application/json' -d "{\"incident_id\":\"$CRASH_ID\"}" | jq
```

Then:

```bash
curl -sS -X POST http://127.0.0.1:8010/api/attest/verify -H 'Content-Type: application/json' -d "{\"incident_id\":\"$CRASH_ID\"}" | jq
```

Say:
"Attestation is optional bonus depth. It is intentionally isolated from detection, approval, and remediation so the main demo stays stable."

## 7. Proof Of Real Minikube Usage

Run:

```bash
bash scripts/proof_minikube.sh
```

Say:
"This is the actual minikube cluster, the real Kubernetes nodes, the deployed backend service, and the live demo workloads."

What to point at:
- `minikube profile list`
- `kubectl cluster-info`
- backend deployment and service
- demo workloads in `default`
- the live OOM memory limit line

## 8. Proof Of Soroban Usage

Run:

```bash
bash scripts/proof_soroban.sh "$CRASH_ID"
```

Say:
"This shows the canonical proof payload, the attestation record, the verification response, and the live Stellar configuration used by the backend."

What to point at:
- `incident_hash`
- `contract_key`
- `tx_id`
- verification result
- `STELLAR_NETWORK`, `STELLAR_RPC_URL`, and `STELLAR_CONTRACT_ID`

## 9. Fast Backup If Slack Misbehaves

If the Slack card does not arrive or the callback path is flaky, use local signed fallback approval.

Run:

```bash
bash scripts/approve_incident.sh "$OOM_ID" approve
```

Say:
"This simulates the same signed Slack approval path locally, so the paused workflow can still resume without changing the core behavior."

## 10. Fast Recovery Commands

If the demo gets noisy:

```bash
make demo-prune
```

If you need to replay the OOMKilled story:

```bash
make demo-reset-oomkill
```

If you need the repo to tell you the next best step:

```bash
bash scripts/judge_next.sh
```

If you need a full reset:

```bash
make demo-ready
```

## Short Version

If you need the absolute shortest recording flow, use only these commands:

```bash
make demo-ready
```

```bash
CRASH_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh crashloop | jq -r '.incident_id')
```

```bash
OOM_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh oomkill | jq -r '.incident_id') && printf 'Approve in Slack: %s\n' "$OOM_ID"
```

```bash
PENDING_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh pending | jq -r '.incident_id')
```

```bash
make demo-snapshot
```

```bash
curl -sS http://127.0.0.1:8010/api/audit | jq
```

```bash
bash scripts/proof_minikube.sh
```

```bash
bash scripts/proof_soroban.sh "$CRASH_ID"
```

## Key Lines To Say

- "This is running against a real minikube cluster, not mocked output."
- "Only low-blast-radius actions are auto-approved."
- "Riskier actions pause for explicit human approval in Slack."
- "When mutation would be unsafe, the system stops and gives operator guidance instead."
- "Every path produces an audit trail with diagnosis, decision, and result."
- "The Soroban attestation path is bonus depth and is isolated from the remediation control loop."

## Lines To Avoid

- Do not say OOMKilled is auto-fixed by default.
- Do not say the system mutates Deployments by default.
- Do not say node issues are auto-remediated.
- Do not improvise extra features during the recording.
