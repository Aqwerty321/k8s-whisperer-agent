# K8sWhisperer Problem Statement Notes

## Processing Status
- Source folder: `PS/`
- Total pages discovered: `10`
- Last processed page: `10`
- Remaining pages: `none`
- Workflow rule: before reading the next image page, read this file first and resume from `last processed page + 1`.

## High-Level Brief
- Project: `K8sWhisperer`
- Track: DevOps x Artificial Intelligence / Machine Learning
- Duration: 36 hours continuous
- Team size: 2 to 4 members
- Difficulty: Extreme, full pipeline required
- Core stack named in PS: LangGraph, LangChain, MCP Server, `kubectl`, Prometheus, Slack

## Problem Framing
- Kubernetes incident response is slow, manual, and stressful.
- Current human workflow is roughly: alert arrives, engineer inspects cluster state, reads logs, correlates metrics, forms a hypothesis, and applies a fix.
- The challenge is not inventing every tool from scratch, but integrating observability, reasoning, execution, safety, and explainability into one coherent system.
- The system must act autonomously when safe, escalate when uncertain, and avoid harming the cluster it is trying to protect.

## Goal
- Build an autonomous Kubernetes incident response agent.
- It should continuously monitor the cluster, detect anomalies, diagnose root causes, propose remediations, and execute fixes.
- Risky actions must go through a human-in-the-loop approval path.
- Every decision must be logged in plain English.

## Mandatory Pipeline
The PS defines a fixed 7-stage loop:

1. Observe
- Scan cluster state across namespaces on a regular polling interval.
- Inputs mentioned: events, pod phases, resource metrics, node states.
- Output is a normalized shared cluster state object.

2. Detect
- Use an LLM classifier over the raw event stream.
- Output typed anomaly objects with at least: anomaly type, severity, affected resource, and confidence score from `0` to `1`.

3. Diagnose
- A specialist sub-agent gathers `kubectl logs`, `kubectl describe`, and recent events for the affected workload.
- The LLM synthesizes a root-cause statement supported by evidence.

4. Plan
- Produce a `RemediationPlan` including: action type, target resource, parameters, confidence score, and blast-radius classification (`low`, `medium`, `high`).

5. Safety Gate
- Route by policy.
- Auto-execute only if confidence is greater than `0.8`, blast radius is `low`, and the action is not in a destructive-action denylist.
- Otherwise require HITL approval through Slack.

6. Execute
- Run the approved `kubectl` action.
- Wait about 30 seconds.
- Re-fetch pod or workload state to verify whether the issue resolved.
- Store the execution result back into shared state.

7. Explain and Log
- Generate a human-readable action summary.
- Post a structured Slack message.
- Append a persistent audit entry.
- Loop back to Observe.

## Shared LangGraph State
The PS explicitly requires one shared typed graph state. Nodes should not keep their own local state.

Recovered state fields from pages 2 to 6:
- `events: list[dict]`
  Raw `kubectl` events from the current observe cycle.
- `anomalies: list[Anomaly]`
  Detected anomalies with type, severity, resource, and confidence.
- `diagnosis: str`
  LLM-generated root cause with supporting evidence.
- `plan: RemediationPlan`
  Proposed action, target, params, confidence, and blast radius.
- `approved: bool`
  Human approval decision coming back from the HITL callback.
- `result: str`
  `kubectl` execution output and post-action pod state.
- `audit_log: list[LogEntry]`
  Persistent history of incidents, decisions, and actions.

## Anomaly Classification Matrix
The PS says implementing only `CrashLoopBackOff` is not enough. The first three anomaly types are the minimum required for a passing demo.

1. `CrashLoopBackOff`
- Trigger: restart count greater than `3`
- Expected action: fetch logs, diagnose, then auto-restart pod
- Severity: high

2. `OOMKilled`
- Trigger: `lastState.terminated.reason = OOMKilled`
- Expected action: inspect memory limits, patch memory upward by `+50%`, then restart
- Severity: high

3. `Pending Pod`
- Trigger: pod stays `Pending` for more than `5 min`
- Expected action: describe pod, inspect node capacity, then recommend
- Severity: medium

4. `ImagePullBackOff`
- Trigger: waiting reason is `ImagePullBackOff`
- Expected action: extract image details and alert a human
- Severity: medium

5. `CPU Throttling`
- Trigger: Prometheus metric indicates throttling above `0.5`
- Expected action: patch CPU limit upward and verify throttling drops
- Severity: medium

6. `Evicted Pod`
- Trigger: pod status reason is `Evicted`
- Expected action: inspect node pressure, then delete the evicted pod
- Severity: low

7. `Deployment Stalled`
- Trigger: `updatedReplicas != replicas` for more than `10 min`
- Expected action: inspect events; HITL for rollback or forced rollout
- Severity: high

8. `Node NotReady`
- Trigger: node `Ready` condition is `False`
- Expected action: log metrics and escalate to HITL only
- Severity: critical
- Important explicit safety note: never auto-drain a node

## Important Constraints Recovered So Far
- The pipeline must be end-to-end, not a narrow single-anomaly demo.
- Safety routing is a core requirement, not a nice-to-have.
- The audit trail is mandatory and persistent.
- Human-readable explanations are required.
- Prometheus is part of the PS, at least for metrics-driven anomaly cases such as CPU throttling.

## Hidden Traps
Page 7 starts the explicit "what breaks naive implementations" section.

1. Race conditions
- Two anomalies can fire at the same time on the same pod.
- The system must handle concurrent state updates without corrupting shared graph state.

2. False positives
- A rolling update can legitimately restart pods.
- The agent must distinguish planned restarts from actual crash loops.

3. RBAC footgun
- If the tool has broad cluster-admin access, a hallucinated command can be catastrophic.
- The PS explicitly warns that correctly restricting operations to pod-level scope is non-trivial and important.

4. Verify loop
- Restarting a pod is not enough.
- Verification should poll with backoff because workloads may need more than 60 seconds to become healthy.

5. Slack webhook latency
- Human approval can take minutes.
- The graph must pause cleanly and resume from callback, not busy-wait and not time out early.

6. Log noise
- Raw `kubectl logs` output can be very large.
- The system needs chunking and summarization before sending evidence to the LLM.

## Required Deliverables
Page 7 defines concrete demo and submission expectations.

1. Live agent demo
- Must run against a real `minikube` cluster.
- Must cover at least 3 anomaly scenarios:
  - `CrashLoopBackOff` with auto-fix
  - `OOMKilled` with HITL
  - `Pending Pod` with explanation

2. HITL Slack flow
- Slack message with `Approve` and `Reject` buttons.
- FastAPI webhook resumes the LangGraph run.
- Full flow should be demoed live, including a judge clicking approve.

3. Audit trail
- Persistent JSON audit log.
- Must show every decision, every action, and a plain-English explanation.
- Must include at least 3 complete incident records.

4. RBAC YAML
- Must provide `ServiceAccount`, `Role`, and `RoleBinding` manifests.
- Permissions must be limited to pod-level operations only.
- Judges will inspect for absence of cluster-admin privileges.

5. Architecture presentation
- 5-minute presentation covering:
  - problem statement
  - LangGraph node graph
  - MCP tool design
  - safety gate logic
  - live demo

## Scoring Rubric
Pages 7 and 8 together complete the visible 100-mark scoring rubric.

1. Autonomous remediation: `30`
- Judges look for correct automated fixes for cases such as `CrashLoopBackOff`, `OOMKilled`, and `Evicted` pods.
- Speed and accuracy of the verify step matter.

2. Safety gate and HITL: `25`
- Judges look for correct routing of high-risk actions to HITL.
- Slack approval flow must work end to end.
- RBAC must be enforced.
- No destructive auto-executions.

3. Diagnosis quality: `20`
- Root-cause explanation must be accurate and actionable.
- Evidence should be cited from real `kubectl` output.
- Plain-English explanation should be understandable to a non-expert.

4. LangGraph architecture: `15`
- Judges look for clean node definitions and proper conditional edges.
- A working checkpointer is explicitly expected.
- The shared state schema should be typed (`TypedDict` is named directly).
- Code quality and overall graph structure are reviewed.

5. MCP integration: `10`
- Judges look for a proper MCP server with typed tool definitions.
- `kubectl` and Slack MCP tools must be functional.
- RBAC `ServiceAccount` scope is part of the evaluation.

6. Total: `100`

## Bonus Opportunities
Page 8 lists optional bonus areas worth up to 5 marks each.

- Prometheus MCP for metric-driven detection.
- Multi-namespace support.
- Predictive alerting before pod crashes.
- Auto-generated GitHub PR for permanent configuration fixes.

## Recommended Tech Stack In PS
Page 8 includes a concrete recommended stack and what each piece is expected to do.

- `LangGraph`
  StateGraph orchestration, conditional edges, MemorySaver checkpointer, HITL interrupt.
- `LangChain`
  Tool wrappers, ReAct-style diagnosis sub-agent, structured output parsing.
- `LLM API`
  The PS examples mention GPT-4o or Claude Sonnet for classifier, planner, and explainer nodes.
- `kubectl MCP Server`
  Python MCP SDK exposing `kubectl` as typed tools with RBAC-scoped service account permissions.
- `Slack MCP`
  Block Kit messages with `Approve` and `Reject` interactive buttons.
- `FastAPI`
  HITL webhook server receiving Slack callbacks and resuming the LangGraph run.
- `Prometheus MCP`
  Optional integration for CPU throttling and memory pressure anomaly detection.
- `minikube`
  Local single-node Kubernetes cluster for demo speed and quick resets.

## Repo Interpretation Of Page 8
- The PS names GPT-4o / Claude as examples for the LLM slot; in this repo the user has already chosen Gemini, which still fits the same cloud-LLM role.
- The PS strongly emphasizes typed tool boundaries for `kubectl` and Slack. Even if the implementation is lightweight, these integrations should remain explicit and narrowly scoped.
- FastAPI is not optional in the PS flow; it is the webhook bridge that resumes approval-paused graph runs.

## 24-Hour Build Timeline From Page 8
Page 8 provides a suggested build order that is useful as an implementation sequence.

1. `00-02h` Setup and scaffold
- Bring up `minikube`.
- Create a `kubectl` MCP skeleton.
- Create a LangGraph `StateGraph` with 8 empty nodes.
- Install dependencies.

2. `02-05h` Observe and detect
- Build the polling `observe_node`.
- Add read-only `kubectl` tools.
- Build the LLM-backed `detect_node` classifier.

3. `05-09h` Diagnose and plan
- Build `diagnose_node` as a sub-agent over logs and describe output.
- Build `plan_node` around a typed `RemediationPlan` schema.

4. `09-13h` Safety gate and execute
- Add a `safety_router` conditional edge.
- Add `kubectl` action tools.
- Build `execute_node` with a 30-second verify step.
- Write RBAC YAML.

5. `13-17h` HITL and Slack
- Build `hitl_node` plus FastAPI webhook.
- Add Slack Block Kit messages with `Approve` and `Reject` buttons.
- Wire the audit trail.

6. `17-20h` Demo scenarios
- Prepare `crashloop.yaml`, `oomkill.yaml`, and `pending.yaml` demo inputs.
- Add Prometheus MCP if time allows.
- Rehearse the demo flow.

7. `20-22h` Stress test
- Run all 3 scenarios multiple times.
- Fix flaky graph edges.
- Add retry logic.
- Verify HITL end-to-end.
- Freeze code.

8. `22-24h` Presentation prep
- Prepare the architecture slide.
- Prepare a 5-minute script.
- Record a fallback demo.
- Practice judge Q&A.

## Web3 / Blockchain Bonus
Page 9 shifts away from the main K8s agent and describes an optional `25`-mark Web3 bonus for `PS 1`.

- Teams pursuing the bonus must build a valid full-stack Stellar blockchain project integrated with their main pipeline.
- The bonus is judged against repository structure and submission-guideline compliance.
- A separate submission link is provided specifically for the Stellar/Web3 bonus track.

## Web3 Bonus Repo Requirements From Page 9
Page 9 starts the concrete repository requirements for the optional bonus project.

1. Single well-organized repository
- The repo must contain frontend code, smart contract code, and integration logic together in one repository.
- The example structure shows a frontend app alongside a contract workspace.

2. Frontend stack example is illustrative, not mandatory
- The example uses `React.js` and `Tailwind CSS`.
- The PS explicitly says the frontend framework may vary, so exact folder names can differ.

3. Smart contract source must be present in the same repo
- The contract portion is not optional for bonus eligibility.
- The example contract layout includes standard Rust/Stellar contract files such as `Cargo.toml` and `Cargo.lock`.

4. Cleanliness matters
- The repository should be clean and well organized.
- It should not contain unnecessary files or folders.
- It must clearly show frontend, smart contract, and integration layers.

## README Requirements For Web3 Bonus
Pages 9 and 10 together define the README expectations for the optional Web3 bonus project.

- `Project Title`
- `Project Description`
- `Project Vision`
- `Key Features`
- `Deployed Smartcontract Details`
- Contract ID
- Screenshot from the block explorer showing deployed contract details
- UI screenshots
- Live app demo link (optional)
- Demo video showing dApp features (optional)
- Project setup guide
- Future scope

## README Authenticity Note
- The PS explicitly says AI use is allowed.
- However, the README should not read like obviously AI-generated content.

## Integration Logic Requirement
Page 10 says bonus eligibility requires actual frontend-to-contract integration using `Stellar-SDK`.

- Teams must show real integration logic that calls deployed smart-contract functions from the frontend.
- Deploying a contract without frontend integration does not qualify for the bonus.

## Reference Repositories
Page 10 gives example repositories for what a valid full-stack Stellar repo can look like.

- `Anonymous Feedback dApp`: `https://github.com/bhupendra-chouhan/Stellar-Journey-to-Mastery`
- `CratePass`: `https://github.com/bhupendra-chouhan/CratePass-Soroban`

## Web3 Bonus Scoring Breakdown
Page 10 provides the full `25`-mark breakdown for the optional bonus.

1. Valid repository structure: `10`
- Frontend + smart contract + integration must all be present.

2. Meaningful use: `10`
- The blockchain addition must add real value to the main pipeline.

3. Demo and explanation quality: `5`
- Judges evaluate how clearly the bonus is demonstrated and explained.

4. Total: `25`

## Repo Interpretation Of Page 9
- This page is about an optional bonus track, not the core K8sWhisperer judging path.
- The user has already chosen to skip Stellar in the first pass, so page 9 should be preserved as reference only and not drive the initial scaffold.
- The only near-term value here is avoiding accidental repo-structure conflicts if the bonus is attempted later.

## Repo Interpretation Of Page 10
- Page 10 confirms the Web3 section is strictly a submission appendix for the optional Stellar bonus.
- None of the page 10 requirements should block the initial K8sWhisperer scaffold.
- If the bonus is attempted later, the most important extra work is not contract deployment alone but end-to-end frontend integration plus a credible README.

## Known Extraction Gaps
- Pages 2 to 6 contain rendering noise from the original PDF export.
- The key state fields and descriptions were still recoverable and are summarized above.
- Pages 7 and 8 appear sufficiently captured for the rubric, stack, and timeline content visible in the export.
- Pages 9 and 10 are now fully summarized at the level needed for implementation planning.
- All discovered PS pages have been processed.
