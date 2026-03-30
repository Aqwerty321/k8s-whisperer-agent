# Judge Rehearsal Script

Use this when you want the shortest reliable end-to-end demo on the current repo state.

Assumption:
- backend is running through the local bridge on `http://127.0.0.1:8010`
- real Slack cards are arriving in `#alerts`

## Open Before You Start
- Slack `#alerts`
- one terminal for commands
- one optional terminal for live incident state:

```bash
watch -n 1 'curl -sS http://127.0.0.1:8010/api/incidents | jq'
```

## Setup
1. Run:

```bash
make demo-ready
```

Say:
"Everything here is running against a real minikube cluster. This resets the runtime state, redeploys the backend and demo workloads, and verifies the public Slack callback path."

2. Run:

```bash
curl -sS http://127.0.0.1:8010/health | jq && curl -sS https://slack.aqwerty321.me/health | jq
```

Say:
"The backend is healthy, and the public Slack callback endpoint is healthy too."

## Flow 1: CrashLoopBackOff Auto-Remediation
1. Run:

```bash
CRASH_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh crashloop | tee /tmp/judge-crashloop.json | jq -r '.incident_id')
```

Say:
"K8sWhisperer only auto-remediates when the blast radius is low. A crashloop restart is low-blast-radius, so this path completes automatically."

2. Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$CRASH_ID" | jq && curl -sS "http://127.0.0.1:8010/api/audit/$CRASH_ID" | jq
```

Say:
"The incident is completed, and the audit trail shows the diagnosis, action, and final result."

## Flow 2: OOMKilled With Real Slack Approval
1. Run:

```bash
OOM_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh oomkill | tee /tmp/judge-oom.json | jq -r '.incident_id') && printf 'Approve this in Slack: %s\n' "$OOM_ID"
```

Say:
"This one is medium blast radius. K8sWhisperer diagnoses the OOM, proposes a memory increase on the owning Deployment, and pauses for human approval in Slack."

2. Action:
- Open the newest Slack card in `#alerts`
- Click `Approve`

Say while doing it:
"The Slack callback acknowledges immediately, resumes the exact LangGraph thread in the background, and records the final outcome."

3. Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$OOM_ID" | jq && curl -sS "http://127.0.0.1:8010/api/audit/$OOM_ID" | jq
```

Say:
"In the default strict profile, approval records a concrete recommendation but does not patch the Deployment automatically. The human stays in control."

## Flow 3: PendingPod Guidance Path
1. Run:

```bash
PENDING_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh pending | tee /tmp/judge-pending.json | jq -r '.incident_id')
```

Say:
"When mutation would be risky or unsupported, K8sWhisperer stops short and gives operator guidance. Pending pods are only surfaced once they have been pending long enough to be meaningful."

2. Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$PENDING_ID" | jq
```

Say:
"This path stays recommendation-only. It explains the scheduling problem without taking an unsafe action."

## Optional Rehearsal: Real Slack Reject Path
Use this when practicing, not necessarily in the judge flow.

1. Run:

```bash
REJECT_ID=$(BASE_URL=http://127.0.0.1:8010 bash scripts/demo_incident.sh oomkill | tee /tmp/judge-reject.json | jq -r '.incident_id') && printf 'Reject this in Slack: %s\n' "$REJECT_ID"
```

2. Action:
- Click `Reject` on the newest Slack card

3. Run:

```bash
curl -sS "http://127.0.0.1:8010/api/incidents/$REJECT_ID" | jq && curl -sS "http://127.0.0.1:8010/api/audit/$REJECT_ID" | jq
```

Say:
"A rejected action is also auditable. The operator decision is recorded, and no cluster mutation is executed."

## Optional Bonus: Prometheus MCP Proof
Use this only if judges ask about Prometheus or MCP depth.

1. Run:

```bash
make prometheus-up && make prometheus-mcp
```

Say:
"Beyond kubectl and Slack MCP servers, we also expose a typed Prometheus MCP server and connect it to a real local Prometheus instance scraping minikube metrics."

2. If they ask why it is not in the main live demo, say:

"We prioritized the fully proven end-to-end judge flow first. Prometheus is a bonus depth path, so we keep it isolated from the main demo instead of risking the core flow on extra metrics infrastructure."

## Optional Bonus: kubectl And Slack MCP Proof
Use this only if judges ask about explicit MCP tooling.

1. Run:

```bash
make kubectl-mcp
```

2. In another terminal run:

```bash
make slack-mcp
```

Say:
"The repo exposes separate typed MCP servers for Kubernetes actions, Slack actions, and Prometheus metrics. That matches the PS requirement to keep tool boundaries explicit instead of hiding everything in one backend function."

## Key Lines To Emphasize
- "This is a real cluster, not mocked output."
- "Only low-blast-radius actions are auto-remediated."
- "Riskier actions pause for explicit human approval in Slack."
- "The default strict profile keeps the OOM fix recommendation-only."
- "Every path writes an audit trail with diagnosis, decision, and result."
- "Node observation is read-only; we never auto-drain or mutate nodes."

## Things Not To Say
- Do not say OOMKilled is auto-fixed.
- Do not say NodeNotReady is auto-remediated.
- Do not say the system mutates Deployments by default.

## If Something Breaks
1. Rebuild the public callback bridge:

```bash
make public-bridge
```

2. Recheck health:

```bash
curl -sS http://127.0.0.1:8010/health | jq && curl -sS https://slack.aqwerty321.me/health | jq
```

3. If you need local fallback approval instead of real Slack:

```bash
bash scripts/approve_incident.sh
```

4. If you need to reset the full demo:

```bash
make demo-ready
```
