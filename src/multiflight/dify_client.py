"""Streaming client for the dedicated Dify Agent application API."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .settings import DIFY_API_KEY, DIFY_BASE_URL, DIFY_TIMEOUT_SECONDS


class DifyClient:
    def __init__(
        self,
        base_url: str = DIFY_BASE_URL,
        api_key: str = DIFY_API_KEY,
        timeout_seconds: float = DIFY_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def configured(self) -> bool:
        return bool(self.api_key)

    def run_agent(
        self,
        *,
        scene_prompt: str,
        query: str,
        user: str,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "DIFY_API_KEY is not configured. Create the key in the new Dify "
                "Agent and place it in E:\\Multi_flight_simulation\\.env."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": {"scene_prompt": scene_prompt},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": "",
            "user": user,
        }
        events: list[dict[str, Any]] = []
        answers: list[str] = []
        conversation_id = ""
        message_id = ""
        timeout = httpx.Timeout(self.timeout_seconds, connect=30.0)
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat-messages",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    events.append(_compact_event(event))
                    conversation_id = event.get("conversation_id", conversation_id)
                    message_id = event.get("message_id", message_id)
                    if event.get("event") in {"message", "agent_message"}:
                        answers.append(event.get("answer", ""))
                    if event.get("event") == "error":
                        raise RuntimeError(event.get("message", "Dify streaming error"))

        return {
            "answer": "".join(answers),
            "conversation_id": conversation_id,
            "message_id": message_id,
            "events": events,
        }


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep audit-relevant Dify fields without storing large opaque payloads."""

    allowed = {
        "event",
        "task_id",
        "message_id",
        "conversation_id",
        "answer",
        "position",
        "thought",
        "observation",
        "tool",
        "tool_input",
        "message",
        "code",
    }
    return {key: value for key, value in event.items() if key in allowed}

