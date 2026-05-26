from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

TRAVEL_INTENT_TOOL_NAME = "extract_travel_intent"

TRAVEL_INTENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TRAVEL_INTENT_TOOL_NAME,
        "description": "Extract structured intent and parameters from a Russian Telegram travel bot message.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["weather", "expense", "travel_advice", "casual_chat", "unknown"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "weather": {
                    "type": "object",
                    "properties": {
                        "location": {"type": ["string", "null"]},
                        "location_surface": {"type": ["string", "null"]},
                        "period_type": {
                            "type": ["string", "null"],
                            "enum": ["today", "tomorrow", "exact_date", "days", "week", "weekend", None],
                        },
                        "date_text": {"type": ["string", "null"]},
                        "days": {"type": ["number", "null"]},
                        "asks_rain": {"type": ["boolean", "null"]},
                    },
                    "required": [
                        "location",
                        "location_surface",
                        "period_type",
                        "date_text",
                        "days",
                        "asks_rain",
                    ],
                },
                "expense": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "participants_text": {"type": ["string", "null"]},
                    },
                    "required": ["amount", "currency", "description", "participants_text"],
                },
            },
            "required": ["intent", "confidence", "weather", "expense"],
        },
    },
}


@dataclass
class MimoProviderError(Exception):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"{self.status_code} {self.message}"


class MimoProvider:
    """MiMo API client (OpenAI-compatible endpoints)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 5,
        retry_count: int = 0,
        auth_header: str = "api-key",
        extraction_mode: str = "tool_call",
        max_completion_tokens: int = 512,
        temperature: float = 0.3,
        top_p: float = 0.95,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.model = (model or "").strip()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.retry_count = max(0, int(retry_count))
        self.auth_header = (auth_header or "api-key").strip().lower()
        self.extraction_mode = (extraction_mode or "tool_call").strip().lower()
        self.max_completion_tokens = max(1, int(max_completion_tokens))
        self.temperature = float(temperature)
        self.top_p = float(top_p)

    async def generate_json(self, *, system_instruction: str, prompt: str) -> str:
        if not self.api_key:
            raise MimoProviderError("MIMO_API_KEY is empty")
        if not self.base_url:
            raise MimoProviderError("MIMO_BASE_URL is empty")
        if not self.model:
            raise MimoProviderError("MIMO_MODEL is empty")

        payload = self._build_payload(
            system_instruction=system_instruction,
            prompt=prompt,
            mode=self.extraction_mode,
        )

        try:
            return await self._post_chat_completions(payload)
        except MimoProviderError as exc:
            if self.extraction_mode == "tool_call" and exc.status_code in (400, 422):
                fallback_payload = self._build_payload(
                    system_instruction=system_instruction,
                    prompt=prompt,
                    mode="tool_call_auto",
                )
                return await self._post_chat_completions(fallback_payload)
            raise

    async def generate_text(self, *, system_instruction: str, prompt: str) -> str:
        if not self.api_key:
            raise MimoProviderError("MIMO_API_KEY is empty")
        if not self.base_url:
            raise MimoProviderError("MIMO_BASE_URL is empty")
        if not self.model:
            raise MimoProviderError("MIMO_MODEL is empty")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self.max_completion_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        return await self._post_chat_completions(payload)

    def _build_payload(self, *, system_instruction: str, prompt: str, mode: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self.max_completion_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        if mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif mode in {"tool_call", "tool_call_auto"}:
            payload["tools"] = [TRAVEL_INTENT_TOOL]
            payload["tool_choice"] = (
                {
                    "type": "function",
                    "function": {"name": TRAVEL_INTENT_TOOL_NAME},
                }
                if mode == "tool_call"
                else "auto"
            )
        else:
            raise MimoProviderError(f"unsupported extraction mode: {mode}")
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_header in {"bearer", "authorization"}:
            headers["Authorization"] = f"Bearer {self.api_key}"
            return headers
        headers["api-key"] = self.api_key
        return headers

    async def _post_chat_completions(self, payload: dict[str, Any]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()

        attempts = max(1, self.retry_count + 1)
        last_error: MimoProviderError | None = None
        for _ in range(attempts):
            started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    snippet = response.text[:240]
                    raise MimoProviderError(
                        message=f"HTTP error: {snippet}",
                        status_code=response.status_code,
                    )
                data = response.json()
                content = self._extract_tool_arguments(data) or self._extract_content(data)
                if not content:
                    raise MimoProviderError("empty content in response")
                return content
            except asyncio.TimeoutError:
                last_error = MimoProviderError("timeout")
            except httpx.TimeoutException:
                last_error = MimoProviderError("timeout")
            except httpx.RequestError as exc:
                last_error = MimoProviderError(f"request error: {exc}")
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                last_error = MimoProviderError(f"invalid response: {exc}")
            except MimoProviderError as exc:
                last_error = exc
                if exc.status_code in (429, 503):
                    break
            finally:
                _ = int((time.monotonic() - started) * 1000)

        raise last_error or MimoProviderError("unknown MiMo provider error")

    @staticmethod
    def _extract_tool_arguments(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not (isinstance(choices, list) and choices):
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        msg = first.get("message")
        if not isinstance(msg, dict):
            return ""
        tool_calls = msg.get("tool_calls")
        if not (isinstance(tool_calls, list) and tool_calls):
            return ""
        call = tool_calls[0]
        if not isinstance(call, dict):
            return ""
        fn = call.get("function")
        if not isinstance(fn, dict):
            return ""
        name = fn.get("name")
        args = fn.get("arguments")
        if name and name != TRAVEL_INTENT_TOOL_NAME:
            return ""
        if isinstance(args, str):
            return args.strip()
        if isinstance(args, dict):
            return json.dumps(args, ensure_ascii=False)
        return ""

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str):
                        return content.strip()
                    if isinstance(content, list):
                        parts: list[str] = []
                        for item in content:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                parts.append(item["text"])
                        return "".join(parts).strip()
        return ""
