from backend.app.integrations.slack import SlackClient


def test_update_message_falls_back_to_send_when_ts_missing() -> None:
    client = SlackClient(
        bot_token="",
        signing_secret="",
        default_channel="#alerts",
        public_base_url="http://localhost:8000",
    )

    response = client.update_message(channel="#alerts", ts=None, text="hello")

    assert response["channel"] == "#alerts"
    assert response["stub"] is True
    assert response["ts"] is None


def test_parse_interaction_payload_returns_channel_and_decision() -> None:
    client = SlackClient(
        bot_token="",
        signing_secret="",
        default_channel="#alerts",
        public_base_url="http://localhost:8000",
    )

    body = (
        b'payload={"channel":{"id":"C123"},"container":{"message_ts":"171234.5678"},'
        b'"actions":[{"action_id":"approve_incident","value":"{\\"incident_id\\":\\"incident-123\\"}"}]}'
    )
    payload = client.parse_interaction_payload(body)

    assert payload["incident_id"] == "incident-123"
    assert payload["approved"] is True
    assert payload["channel"] == "C123"
    assert payload["message_ts"] == "171234.5678"


def test_render_decision_text_mentions_outcome() -> None:
    client = SlackClient(
        bot_token="",
        signing_secret="",
        default_channel="#alerts",
        public_base_url="http://localhost:8000",
    )

    text = client.render_decision_text(incident_id="incident-123", approved=False)

    assert "incident-123" in text
    assert "rejected" in text


def test_render_status_blocks_contains_timeline_section() -> None:
    client = SlackClient(
        bot_token="",
        signing_secret="",
        default_channel="#alerts",
        public_base_url="http://localhost:8000",
    )

    blocks = client.render_status_blocks(
        incident_id="incident-123",
        title="K8sWhisperer incident update",
        status="completed",
        anomaly_summary="CrashLoop detected",
        diagnosis="Container exits immediately",
        action="restart_pod",
        result="Pod recovered",
        timeline=["observe completed", "detect completed", "execute completed"],
    )

    assert any(block.get("type") == "header" for block in blocks)
    assert any("Timeline" in block.get("text", {}).get("text", "") for block in blocks if block.get("type") == "section")
