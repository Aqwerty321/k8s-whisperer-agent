# LangGraph State Schema

This document is a cleaned reconstruction of the LangGraph state-schema page from the problem statement. The original OCR export contained PDF rendering artifacts, so only the recoverable schema content is preserved here.

## Design Rule
All agent nodes read from and write to a shared `ClusterState` `TypedDict`.

Nodes must not maintain local state. All workflow data flows through the shared graph state.

## Core Schema

| Field | Type | Description |
| --- | --- | --- |
| `events` | `list[dict]` | Raw `kubectl` events from the current observe cycle. |
| `anomalies` | `list[Anomaly]` | Detected anomalies with type, severity, affected resource, and confidence. |
| `diagnosis` | `str` | LLM-generated root-cause string with supporting evidence. |
| `plan` | `RemediationPlan` | Proposed action, target, parameters, confidence, and blast radius. |
| `approved` | `bool` | Human approval decision returned by the HITL webhook callback. |
| `result` | `str` | `kubectl` execution output and post-action workload or pod state. |
| `audit_log` | `list[LogEntry]` | Persistent history of incidents, decisions, and actions. |

## Notes
- `ClusterState` is the shared top-level LangGraph state container described in the PS.
- `Anomaly`, `RemediationPlan`, and `LogEntry` are nested typed records referenced by the shared state.
- The current repo implementation uses additional operational fields, but the table above reflects the PS-required core schema.
