# Judge Demo Checklist

For a spoken walkthrough with exact commands and judge-facing lines, use `docs/judge-rehearsal-script.md`.

## Before Judges Arrive
- Run `make demo-ready`
- Confirm `curl -sS http://127.0.0.1:8010/health | jq`
- Confirm `curl -sS https://slack.aqwerty321.me/health | jq`
- Run `make demo-snapshot`
- If you need to re-show the OOMKilled fix, run `make demo-reset-oomkill`
- If the lists get noisy, run `make demo-prune`
- Open Slack `#alerts`
- Open one terminal for `curl -sS http://127.0.0.1:8010/api/incidents | jq`
- Open one terminal for `curl -sS http://127.0.0.1:8010/api/audit | jq`

## Demo Flow
1. CrashLoopBackOff
   Run `bash scripts/demo_incident.sh crashloop | jq`
   Explain that K8sWhisperer auto-approves only low-blast-radius actions.

2. OOMKilled with human approval
   Run `bash scripts/demo_incident.sh oomkill | jq`
   Switch to Slack and click `Approve` on the newest card.
   Explain that the public callback resumes the paused LangGraph thread.

3. Audit proof
   Run `curl -sS http://127.0.0.1:8010/api/audit | jq`
   Point out the explanation, decision, and result trail.
   If useful, run `bash scripts/export_incident_report.sh` for a compact markdown report.
   Use `make demo-snapshot` to show the live scoreboard of completed, awaiting, approved, and rejected outcomes.

4. PendingPod recommendation-only path
   Run `bash scripts/demo_incident.sh pending | jq`
   Explain that K8sWhisperer stops short of unsafe mutation and gives operator guidance.

5. Prometheus MCP bonus proof if asked
   Run `make prometheus-up` and then `make prometheus-mcp` in a separate terminal.
   Explain that the same repo now exposes a typed Prometheus MCP server and can query real minikube metrics through a local Prometheus instance.
   Be explicit that the main judged demo remains the proven cluster/Slack/audit flow, while Prometheus is shown as bonus depth.

## Backup Path
- If Slack or Cloudflare misbehaves, keep the incident visible in `/api/incidents`
- Run `bash scripts/approve_incident.sh`
- Use the audit output and runtime state to show the same resume path locally
- Do not improvise new features during the demo
