# 60-Second Pitch

K8sWhisperer is an incident-response copilot for Kubernetes that turns raw cluster symptoms into safe, explainable actions.

It watches namespace-scoped pod signals, diagnoses common failures like CrashLoopBackOff, OOMKilled, and scheduling issues, and then routes each incident through a LangGraph workflow: observe, detect, diagnose, plan, safety gate, execute, and explain.

Low-blast-radius actions can be auto-remediated, but anything riskier pauses for human approval in Slack. When an operator clicks approve, the exact graph thread resumes through a verified webhook callback, executes the approved step, and writes an audit record with the diagnosis, decision, and outcome.

The key idea is not just automation. It is safe automation: scoped RBAC, explicit human gates, persistent workflow state, and a clear audit trail that makes every action explainable.
