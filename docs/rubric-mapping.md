# Rubric Mapping

## Problem Relevance
- Kubernetes incidents are noisy, repetitive, and risky to automate blindly.
- K8sWhisperer turns raw pod and event signals into scoped, explainable actions.

## Technical Depth
- FastAPI backend with LangGraph orchestration
- persistent checkpointing for paused/resumed incident threads
- hybrid anomaly detection that keeps heuristic classification as the stable baseline and adds validated LLM enrichment when available
- tightly scoped Kubernetes integration with namespace-scoped pod writes by default and optional read-only node access
- optional multi-namespace observation without changing the default single-namespace demo profile
- Slack interactive approval callbacks with signed request verification
- optional Prometheus-backed CPU throttling detection plus a typed Prometheus MCP server

## Safety And Reliability
- low-blast-radius actions can be auto-approved
- medium/high-risk actions pause for human approval
- every incident produces an explanation and audit record
- every incident can also be exported as a compact markdown report for review
- approved `OOMKilled` incidents can patch and verify the owning deployment when workload patching is enabled, while the default strict profile keeps that path recommendation-only
- public ingress is restricted to health and Slack callback only
- fallback local approval path exists if Slack or Cloudflare fails

## Demoability
- `make demo-ready` resets the environment into a clean judge-ready state
- `make demo-reset-oomkill` restores the OOMKilled scenario so the approved fix can be shown repeatedly
- `make demo-prune` trims old incident and audit noise without rebuilding the whole environment
- repeatable CrashLoopBackOff auto-remediation story
- repeatable OOMKilled human-approval story
- repeatable PendingPod recommendation-only story
- `make demo-snapshot` shows live runtime status, incidents, audit, tracker state, and a simple outcome scoreboard

## Practicality
- single backend service, not over-engineered microservices
- minikube deployment path for demo realism
- cloudflared named tunnel for stable callback URL

## Stretch / Future Work
- broader workload-aware remediation beyond the current deployment-focused patch support
- broader remediation catalog
- optional on-chain attestation after incident completion
- lightweight operator UI after the core demo path is locked
