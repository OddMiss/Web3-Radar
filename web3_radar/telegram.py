from __future__ import annotations

from .http import HttpClient


class TelegramClient:
    def __init__(self, http: HttpClient, bot_token: str, chat_id: str) -> None:
        self.http = http
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        payload = self.http.post_form_json(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
        )
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description") or "Telegram send failed")
