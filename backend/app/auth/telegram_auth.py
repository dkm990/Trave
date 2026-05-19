from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    pass


@dataclass
class TelegramInitData:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    raw: dict


def parse_init_data(init_data: str) -> TelegramInitData:
    if not init_data:
        raise TelegramAuthError("empty init data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    user_raw = pairs.get("user")
    if not user_raw:
        raise TelegramAuthError("user not provided in init data")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError(f"failed to parse user: {exc}") from exc

    if "id" not in user:
        raise TelegramAuthError("user.id missing")

    return TelegramInitData(
        user_id=int(user["id"]),
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        raw=pairs,
    )


def validate_init_data(init_data: str, bot_token: str) -> TelegramInitData:
    """Полноценная HMAC проверка по docs Telegram Mini Apps.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not bot_token:
        raise TelegramAuthError("bot token is not configured")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("hash missing")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramAuthError("invalid hash")

    return parse_init_data(init_data)
