"""ExchangeRate-API open access endpoint (no API key).

Docs: https://www.exchangerate-api.com/docs/free
Endpoint: https://open.er-api.com/v6/latest/{BASE}

Conditions:
- No API key required.
- Updates once per 24h.
- Rate limited (HTTP 429 if too aggressive).
- Attribution required: "Rates By Exchange Rate API".
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from app.services.providers.base import (
    CurrencyProvider,
    ProviderError,
    ProviderUnsupportedPair,
    RateResult,
)

DEFAULT_BASE_URL = "https://open.er-api.com/v6"


class ExchangeRateOpenProvider(CurrencyProvider):
    name = "exchangerate_open"

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._http = http_client
        self._owns_client = http_client is None
        self.base_url = base_url.rstrip("/")

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0)
        return self._http

    async def get_rate(self, base: str, quote: str) -> RateResult:
        base = base.upper()
        quote = quote.upper()

        client = await self._client()
        url = f"{self.base_url}/latest/{base}"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(f"ExchangeRate-Open transport error: {exc}") from exc

        if resp.status_code == 404:
            raise ProviderUnsupportedPair(
                f"ExchangeRate-Open does not support base {base}"
            )
        if resp.status_code == 429:
            raise ProviderError("ExchangeRate-Open rate limited (HTTP 429)")
        try:
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"ExchangeRate-Open HTTP error: {exc}") from exc

        if data.get("result") != "success":
            err_type = data.get("error-type", "unknown")
            if err_type in ("unsupported-code", "malformed-request"):
                raise ProviderUnsupportedPair(
                    f"ExchangeRate-Open: {err_type} for {base}->{quote}"
                )
            raise ProviderError(f"ExchangeRate-Open error: {err_type}")

        rates = data.get("rates") or {}
        if quote not in rates:
            raise ProviderUnsupportedPair(
                f"ExchangeRate-Open: {quote} not in rates for base {base}"
            )

        try:
            rate = Decimal(str(rates[quote]))
        except (TypeError, ValueError) as exc:
            raise ProviderError(f"ExchangeRate-Open malformed rate: {exc}") from exc

        unix_ts = data.get("time_last_update_unix")
        if isinstance(unix_ts, (int, float)) and unix_ts > 0:
            rate_date = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).date()
        else:
            rate_date = date.today()

        return RateResult(
            base=base,
            quote=quote,
            rate=rate,
            rate_date=rate_date,
            provider=self.name,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None
