# Demo Runbook

This runbook keeps the demo sequence short, repeatable, and easy to recover during the hackathon.

## Start The System

### 1. Run the API
```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

Or run the backend inside minikube:

```bash
make deploy-backend
make public-bridge
```

### 2. Optionally expose a public callback URL
- Temporary: `bash scripts/tunnel.sh`
- Stable domain: follow `docs/stable-domain-tunnel.md`

If the backend runs in minikube, keep the tunnel pointed at the local forwarded port through `make public-bridge`.

### 3. Start or seed the demo cluster
```bash
bash scripts/setup_minikube.sh
bash scripts/deploy_demo.sh
```

`deploy_demo.sh` resets the crashloop demo state so the first pod starts unhealthy and the auto-remediation path has something real to fix.

### 4. Reset to a clean judge-ready state
```bash
make demo-reset
```

This clears persisted runtime state in the backend pod, redeploys the demo workloads, and gives you a clean incident/audit slate.

## Seed Walkthrough Incidents

### CrashLoopBackOff auto-remediation
```bash
bash scripts/demo_incident.sh crashloop | jq
```

Expected outcome:
- incident status `completed`
- plan action `restart_pod`
- restart outcome or replacement note in result

### OOMKilled approval flow
```bash
bash scripts/demo_incident.sh oomkill | jq
```

Expected outcome:
- incident status `awaiting_human`
- plan action `patch_pod`
- recommendation to increase memory on the owning workload
- approving in the default strict profile records the recommendation but does not patch the Deployment automatically
- Slack approval request sent if live Slack is configured

### PendingPod operator guidance
```bash
bash scripts/demo_incident.sh pending | jq
```

Expected outcome:
- incident status `awaiting_human`
- plan action `notify_only`
- scheduling recommendation based on event evidence

## Inspect State During Demo

### Runtime status
```bash
curl -sS http://localhost:8010/api/status | jq
```

### Incident list
```bash
curl -sS http://localhost:8010/api/incidents | jq
```

### Filter only awaiting-human incidents
```bash
curl -sS 'http://localhost:8010/api/incidents?status=awaiting_human' | jq
```

### Audit history
```bash
curl -sS http://localhost:8010/api/audit | jq
```

### Search audit records
```bash
curl -sS 'http://localhost:8010/api/audit?search=oomkill' | jq
```

## Live Slack Approval
When using a real Slack callback URL:
1. Trigger the OOMKilled scenario.
2. Wait for the approval message in `#alerts`.
3. Click `Approve` or `Reject`.
4. Verify the incident transitions from `awaiting_human` to `completed` after the background resume finishes.
5. Check the audit endpoint for the final record.

## Backup Local Approval
If Slack or Cloudflare is unavailable during a demo:

```bash
bash scripts/demo_incident.sh summary
bash scripts/approve_incident.sh
```

This sends a signed Slack-style callback directly to the local backend on `127.0.0.1:8010` for the newest pending incident.

If the backend is running in minikube without a local listener on `127.0.0.1:8010`, start `make public-bridge` first or use a temporary `kubectl port-forward svc/k8s-whisperer 8010:8010 -n default`.

## Export Incident Report
To show a markdown-style postmortem for the latest incident:

```bash
bash scripts/export_incident_report.sh
```

## Resetting OOMKilled Before A Demo
If you already approved an OOMKilled fix and want to show that flow again:

```bash
make demo-reset-oomkill
```

This restores the `demo-oomkill` Deployment memory limit to the failing baseline so the next approval can visibly patch it again.

## Pruning Old Demo Noise
If you want to keep the environment running but trim older incident and audit clutter:

```bash
make demo-prune
```

## Judge Flow
1. Run `make demo-ready`.
2. Run `make demo-snapshot`.
3. Show `curl -sS http://127.0.0.1:8010/health`.
4. Run `bash scripts/demo_incident.sh crashloop | jq` and show the completed restart outcome.
5. Run `bash scripts/demo_incident.sh oomkill | jq`, open Slack, and approve the newest card.
6. Run `make demo-snapshot` and show the scoreboard plus recent incidents.
7. Show `curl -sS http://127.0.0.1:8010/api/audit | jq`.
8. Run `bash scripts/demo_incident.sh pending | jq` and explain the recommendation-only safety path.

## If Something Breaks
- Check API health: `curl http://localhost:8010/health`
- Check runtime status: `curl http://localhost:8010/api/status | jq`
- Check recent incident summaries: `curl http://localhost:8010/api/incidents | jq`
- Check audit log tail through API: `curl http://localhost:8010/api/audit | jq`
- Re-run the scenario using `scripts/demo_incident.sh`
