from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

from app.config import get_settings
from app.services.providers.base import (
    CurrencyProvider,
    ProviderError,
    ProviderUnsupportedPair,
    RateResult,
)

# Frankfurter v2 supports a fixed set of currencies (ECB-based).
# https://api.frankfurter.dev/v1/currencies
# This snapshot lets us short-circuit unsupported pairs without an HTTP call.
FRANKFURTER_SUPPORTED = frozenset(
    {
        "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR",
        "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW",
        "MXN", "MYR", "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD",
        "THB", "TRY", "USD", "ZAR",
    }
)


class FrankfurterProvider(CurrencyProvider):
    name = "frankfurter"

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.settings = get_settings()
        self._http = http_client
        self._owns_client = http_client is None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0)
        return self._http

    async def get_rate(self, base: str, quote: str) -> RateResult:
        base = base.upper()
        quote = quote.upper()
        if base not in FRANKFURTER_SUPPORTED or quote not in FRANKFURTER_SUPPORTED:
            raise ProviderUnsupportedPair(
                f"Frankfurter does not support {base}->{quote}"
            )

        client = await self._client()
        url = f"{self.settings.frankfurter_base_url.rstrip('/')}/latest"
        try:
            resp = await client.get(url, params={"base": base, "symbols": quote})
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            # 422 у Frankfurter обычно = unsupported currency
            if exc.response is not None and exc.response.status_code in (404, 422):
                raise ProviderUnsupportedPair(
                    f"Frankfurter rejected {base}->{quote}: {exc.response.status_code}"
                ) from exc
            raise ProviderError(f"Frankfurter HTTP error: {exc}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Frankfurter transport error: {exc}") from exc

        rates = data.get("rates") or {}
        if quote not in rates:
            raise ProviderUnsupportedPair(
                f"Frankfurter response missing {quote} for base {base}"
            )

        try:
            rate = Decimal(str(rates[quote]))
            rate_date = date.fromisoformat(data["date"])
        except (KeyError, ValueError) as exc:
            raise ProviderError(f"Frankfurter response malformed: {exc}") from exc

        return RateResult(
            base=base, quote=quote, rate=rate, rate_date=rate_date, provider=self.name
        )

    async def aclose(self) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None
