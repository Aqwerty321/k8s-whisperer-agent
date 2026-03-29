from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs
from typing import Any, Mapping


class SlackClient:
    def __init__(
        self,
        *,
        bot_token: str,
        signing_secret: str,
        default_channel: str,
        public_base_url: str,
        request_tolerance_seconds: int = 300,
    ) -> None:
        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.default_channel = default_channel
        self.public_base_url = public_base_url
        self.request_tolerance_seconds = request_tolerance_seconds
        self._client: Any | None = None

    def _ensure_client(self) -> None:
        if self._client is not None or not self.bot_token:
            return

        try:
            from slack_sdk import WebClient

            self._client = WebClient(token=self.bot_token)
        except Exception:
            self._client = None

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.signing_secret)

    def send_message(
        self,
        *,
        channel: str | None = None,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        target_channel = channel or self.default_channel
        self._ensure_client()
        if self._client is None:
            return {
                "ok": False,
                "stub": True,
                "channel": target_channel,
                "ts": None,
                "message": "Slack client is not configured.",
            }

        try:
            response = self._client.chat_postMessage(
                channel=target_channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
            return dict(response.data)
        except Exception as exc:
            return {
                "ok": False,
                "stub": False,
                "channel": target_channel,
                "ts": None,
                "message": str(exc),
            }

    def update_message(
        self,
        *,
        channel: str | None,
        ts: str | None,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        target_channel = channel or self.default_channel
        if not ts:
            return self.send_message(channel=target_channel, text=text, blocks=blocks)

        self._ensure_client()
        if self._client is None:
            return {
                "ok": False,
                "stub": True,
                "channel": target_channel,
                "ts": ts,
                "message": "Slack client is not configured.",
            }

        try:
            response = self._client.chat_update(
                channel=target_channel,
                ts=ts,
                text=text,
                blocks=blocks,
            )
            return dict(response.data)
        except Exception as exc:
            return {
                "ok": False,
                "stub": False,
                "channel": target_channel,
                "ts": ts,
                "message": str(exc),
            }

    def render_decision_text(self, *, incident_id: str, approved: bool) -> str:
        decision = "approved" if approved else "rejected"
        return f"Incident `{incident_id}` was {decision} by the human approval flow."

    def render_status_blocks(
        self,
        *,
        incident_id: str,
        title: str,
        status: str,
        anomaly_summary: str | None = None,
        diagnosis: str | None = None,
        action: str | None = None,
        result: str | None = None,
        timeline: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title[:150]},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident*\n`{incident_id}`"},
                    {"type": "mrkdwn", "text": f"*Status*\n`{status}`"},
                ],
            },
        ]

        if anomaly_summary:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Summary*\n{anomaly_summary}"},
                }
            )
        if diagnosis:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Diagnosis*\n{diagnosis[:2800]}"},
                }
            )
        if action or result:
            fields: list[dict[str, str]] = []
            if action:
                fields.append({"type": "mrkdwn", "text": f"*Action*\n`{action}`"})
            if result:
                fields.append({"type": "mrkdwn", "text": f"*Result*\n{result[:1000]}"})
            blocks.append({"type": "section", "fields": fields})
        if timeline:
            timeline_text = "\n".join(f"- {item}" for item in timeline[:8])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Timeline*\n{timeline_text}"},
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"K8sWhisperer callback base: `{self.public_base_url}`"}
                ],
            }
        )
        return blocks

    def send_approval_request(
        self,
        *,
        channel: str | None,
        incident_id: str,
        summary: str,
        plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        approval_text = f"Incident `{incident_id}` requires approval."
        return self.send_message(
            channel=channel,
            text=approval_text,
            blocks=self._approval_blocks(incident_id=incident_id, summary=summary, plan=plan),
        )

    def verify_request_signature(self, headers: Mapping[str, str], body: bytes) -> bool:
        if not self.signing_secret:
            # Local scaffold/testing mode: allow callbacks when no secret is configured.
            return True

        if not body:
            return False

        timestamp = headers.get("x-slack-request-timestamp") or headers.get("X-Slack-Request-Timestamp")
        signature = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")
        if not timestamp or not signature:
            return False

        try:
            request_age = abs(time.time() - int(timestamp))
        except ValueError:
            return False

        if request_age > self.request_tolerance_seconds:
            return False

        base_string = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
        expected = "v0=" + hmac.new(
            self.signing_secret.encode("utf-8"),
            base_string,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_interaction_payload(self, body: bytes) -> dict[str, Any]:
        form_data = parse_qs(body.decode("utf-8"))
        payload_raw = form_data.get("payload", [None])[0]
        if payload_raw is None:
            raise ValueError("Missing Slack payload.")

        payload = json.loads(payload_raw)
        actions = payload.get("actions", [])
        if not actions:
            raise ValueError("Slack payload did not contain any actions.")

        action = actions[0]
        action_value = json.loads(action.get("value", "{}"))
        incident_id = action_value.get("incident_id")
        if not incident_id:
            raise ValueError("Slack action payload is missing incident_id.")

        channel = ((payload.get("channel") or {}).get("id")) or self.default_channel
        message_ts = ((payload.get("container") or {}).get("message_ts")) or ((payload.get("message") or {}).get("ts"))
        return {
            "incident_id": incident_id,
            "approved": action.get("action_id") == "approve_incident",
            "channel": channel,
            "message_ts": message_ts,
            "action_id": action.get("action_id"),
            "raw_payload": payload,
        }

    def _approval_blocks(
        self,
        *,
        incident_id: str,
        summary: str,
        plan: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        action_name = str(plan.get("action", "notify_only"))
        reason = str(plan.get("reason", "No rationale provided."))
        plan_json = json.dumps({"incident_id": incident_id})
        blocks = self.render_status_blocks(
            incident_id=incident_id,
            title="K8sWhisperer approval required",
            status="awaiting_human",
            anomaly_summary=summary,
            diagnosis=reason,
            action=action_name,
            timeline=[
                "observe completed",
                "detect completed",
                "diagnose completed",
                "plan completed",
                "waiting for human approval",
            ],
        )
        blocks.extend([
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "approve_incident",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "value": plan_json,
                    },
                    {
                        "type": "button",
                        "action_id": "reject_incident",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "value": plan_json,
                    },
                ],
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Blast Radius*\n`{plan.get('blast_radius', 'unknown')}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence*\n`{plan.get('confidence', 'n/a')}`",
                    },
                ],
            },
        ])
        return blocks
