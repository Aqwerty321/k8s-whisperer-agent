# 60-Second Pitch

K8sWhisperer is an incident-response copilot for Kubernetes that turns raw cluster symptoms into safe, explainable actions.

It watches namespace-scoped pod signals plus read-only node state, diagnoses common failures like CrashLoopBackOff, OOMKilled, Pending pods, and NodeNotReady, and then routes each incident through a LangGraph workflow: observe, detect, diagnose, plan, safety gate, execute, and explain.

Low-blast-radius actions can be auto-remediated, but anything riskier pauses for human approval in Slack. When an operator clicks approve, the webhook acknowledges immediately, resumes the exact graph thread in the background, executes the approved step or recommendation path, and writes an audit record with the diagnosis, decision, and outcome.

The key idea is not just automation. It is safe automation: scoped RBAC, explicit human gates, persistent workflow state, and a clear audit trail that makes every action explainable.
