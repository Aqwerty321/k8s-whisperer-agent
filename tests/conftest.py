import pytest

from backend.app.integrations.slack.client import SlackClient


@pytest.fixture(autouse=True)
def stub_live_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_send_message(self: SlackClient, *, channel=None, text: str, blocks=None, thread_ts=None):
        return {
            "ok": True,
            "stub": True,
            "channel": channel or self.default_channel,
            "text": text,
            "blocks": blocks,
            "thread_ts": thread_ts,
            "ts": "stub-message-ts",
        }

    def fake_update_message(self: SlackClient, *, channel=None, ts=None, text: str, blocks=None):
        return {
            "ok": True,
            "stub": True,
            "channel": channel or self.default_channel,
            "ts": ts,
            "text": text,
            "blocks": blocks,
        }

    monkeypatch.setattr(SlackClient, "send_message", fake_send_message)
    monkeypatch.setattr(SlackClient, "update_message", fake_update_message)
