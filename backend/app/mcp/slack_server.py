from __future__ import annotations

from typing import Any

from ..integrations.slack import SlackClient


def build_slack_mcp_server(slack_client: SlackClient):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError("The MCP SDK is not available. Install dependencies first.") from exc

    server = FastMCP("k8s-whisperer-slack")

    @server.tool()
    def send_message(channel: str, text: str) -> dict[str, Any]:
        """Send a plain Slack message."""
        return slack_client.send_message(channel=channel, text=text)

    @server.tool()
    def request_approval(channel: str, incident_id: str, summary: str, plan: dict[str, Any]) -> dict[str, Any]:
        """Send an approval request with interactive buttons."""
        return slack_client.send_approval_request(
            channel=channel,
            incident_id=incident_id,
            summary=summary,
            plan=plan,
        )

    return server


def main() -> None:
    from ..config import get_settings

    settings = get_settings()
    client = SlackClient(
        bot_token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
        default_channel=settings.slack_default_channel,
        public_base_url=settings.public_base_url,
        request_tolerance_seconds=settings.slack_request_tolerance_seconds,
    )
    server = build_slack_mcp_server(client)
    server.run()


if __name__ == "__main__":
    main()
