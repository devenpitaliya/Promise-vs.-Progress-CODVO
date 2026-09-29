"""Slack notifier: post briefings and reminders to a channel.

Two ways to connect, whichever the workspace allows:
- Incoming webhook URL (simplest; the channel is chosen when the webhook is created).
- Bot token (xoxb-...) with the chat:write scope, plus a channel name or ID.
"""

import logging
from typing import Any, Dict, List

import httpx

from app.config import settings
from app.services.connectors.base import (
    ConnectionTest,
    ConnectorConfigError,
    FieldSpec,
    Message,
    NotifierConnector,
    validate_url,
)
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"
MAX_TEXT = 2900  # Slack section blocks accept up to 3000 characters


def escape(text: str) -> str:
    """Slack mrkdwn control characters; also stops meeting text from triggering @channel-style mentions."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def blocks_for(message: Message) -> List[Dict[str, Any]]:
    body = "\n".join(message.lines)[:MAX_TEXT] or " "
    blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": message.title[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    if message.link:
        blocks.append(
            {
                "type": "actions",
                "elements": [{"type": "button", "text": {"type": "plain_text", "text": message.link_label or "Open"}, "url": message.link}],
            }
        )
    return blocks


class SlackConnector(NotifierConnector):
    kind = "slack"
    label = "Slack"
    fields = [
        FieldSpec(
            "webhook_url",
            "Incoming webhook URL",
            secret=True,
            placeholder="https://hooks.slack.com/services/...",
            help="Slack app > Incoming Webhooks > Add to a channel. Either this, or a bot token and channel.",
        ),
        FieldSpec(
            "bot_token", "Bot token", secret=True, placeholder="xoxb-...", help="Needs the chat:write scope; invite the bot to the channel."
        ),
        FieldSpec("channel", "Channel", placeholder="#eng-leads or C0123456789", help="Required with a bot token."),
    ]

    @staticmethod
    def validate(config: Dict[str, Any]) -> Dict[str, Any]:
        if config.get("webhook_url"):
            config["webhook_url"] = validate_url(config["webhook_url"], allowed_suffixes=["hooks.slack.com"], what="Webhook URL")
        if config.get("bot_token") and not str(config["bot_token"]).startswith("xoxb-"):
            raise ConnectorConfigError("A Slack bot token starts with xoxb-.")
        return config

    def is_configured(self) -> bool:
        return bool(self.config.get("webhook_url") or (self.config.get("bot_token") and self.config.get("channel")))

    @property
    def target(self) -> str:
        return self.config.get("channel") or "the webhook's channel"

    def _client(self) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.config['bot_token']}"} if self.config.get("bot_token") else {}
        return httpx.AsyncClient(headers=headers, timeout=settings.SLACK_TIMEOUT_SECONDS)

    @observe("slack-send", as_type="tool")
    async def send(self, message: Message) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(False, "Slack is not connected. Add it in Settings > Integrations.")
        payload = {"text": message.title, "blocks": blocks_for(message)}
        try:
            async with self.session():
                if self.config.get("bot_token") and self.config.get("channel"):
                    response = await self.http.post(f"{SLACK_API}/chat.postMessage", json={"channel": self.config["channel"], **payload})
                    data = response.json() if response.status_code == 200 else {}
                    if not data.get("ok"):
                        error = data.get("error") or f"HTTP {response.status_code}"
                        hint = " Invite the bot to the channel (/invite @your-bot)." if error == "not_in_channel" else ""
                        return ConnectionTest(False, f"Slack refused the message: {error}.{hint}")
                else:
                    response = await self.http.post(self.config["webhook_url"], json=payload)
                    if response.status_code != 200:
                        return ConnectionTest(False, f"Slack refused the message: {response.text[:100] or response.status_code}.")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Slack delivery failed: %s", exc.__class__.__name__)
            return ConnectionTest(False, f"Could not reach Slack ({exc.__class__.__name__}).")
        tracing.update_span(metadata={"channel": self.target})
        return ConnectionTest(True, f"Posted to {self.target}.")

    async def test(self) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(False, "Add an incoming webhook URL, or a bot token and a channel.")
        result = await self.send(
            Message(
                title="Promise vs. Progress is connected",
                lines=["Pre-meeting briefings and due-date reminders will be posted here."],
            )
        )
        return ConnectionTest(result.ok, f"{result.message} A test message was sent." if result.ok else result.message)
