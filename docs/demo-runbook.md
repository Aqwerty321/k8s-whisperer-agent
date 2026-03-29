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
2. Wait for the approval message in `#alert`.
3. Click `Approve` or `Reject`.
4. Verify the incident transitions from `awaiting_human` to `completed`.
5. Check the audit endpoint for the final record.

## If Something Breaks
- Check API health: `curl http://localhost:8010/health`
- Check runtime status: `curl http://localhost:8010/api/status | jq`
- Check recent incident summaries: `curl http://localhost:8010/api/incidents | jq`
- Check audit log tail through API: `curl http://localhost:8010/api/audit | jq`
- Re-run the scenario using `scripts/demo_incident.sh`
