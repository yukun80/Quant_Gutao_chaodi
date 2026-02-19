from __future__ import annotations

"""Realtime EastMoney snapshot fetcher with retry and concurrency controls."""

import asyncio
import json
import random
from datetime import datetime
from typing import Any, Iterable

import aiohttp
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed

from .config import Settings
from .models import StockSnapshot


class EastMoneyFetcher:
    """Fetch and normalize snapshots for a batch of stock codes."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sem = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self.timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT_SEC)
        self.extra_headers = self._build_extra_headers()

    def _build_extra_headers(self) -> dict[str, str]:
        """Build optional request headers from settings for future auth-compatible calls."""
        headers: dict[str, str] = {}
        if self.settings.EM_HEADERS_JSON:
            try:
                raw = json.loads(self.settings.EM_HEADERS_JSON)
            except json.JSONDecodeError as exc:
                raise ValueError("EM_HEADERS_JSON must be a valid JSON object string") from exc
            if not isinstance(raw, dict):
                raise ValueError("EM_HEADERS_JSON must decode to an object")
            headers.update({str(k): str(v) for k, v in raw.items()})

        if self.settings.EM_COOKIE:
            headers["Cookie"] = self.settings.EM_COOKIE
        return headers

    @staticmethod
    def to_secid(code: str) -> str:
        """Map local 6-digit code to EastMoney market-prefixed secid."""
        if code.startswith(("5", "6", "9")):
            return f"1.{code}"
        return f"0.{code}"

    def _build_url(self, code: str) -> str:
        """Build quote URL with requested field list."""
        secid = self.to_secid(code)
        return f"{self.settings.EM_API_BASE}?secid={secid}&fields={self.settings.EM_FIELDS}"

    async def _fetch_raw(self, session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
        """Fetch raw JSON with bounded retries for transient network failures."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.RETRY_ATTEMPTS),
            wait=wait_fixed(self.settings.RETRY_WAIT_SEC),
            reraise=True,
        ):
            with attempt:
                async with session.get(url, timeout=self.timeout, headers=self.extra_headers or None) as response:
                    response.raise_for_status()
                    return await response.json(content_type=None)
        raise RuntimeError("unreachable")

    async def _fetch_one(self, session: aiohttp.ClientSession, code: str) -> StockSnapshot | None:
        """Fetch and parse one symbol; return None for retriable/parse failures."""
        async with self.sem:
            # Jitter avoids fixed-interval request bursts that are easy to throttle.
            await asyncio.sleep(random.uniform(self.settings.JITTER_MIN_SEC, self.settings.JITTER_MAX_SEC))
            url = self._build_url(code)
            try:
                payload = await self._fetch_raw(session, url)
            except Exception:
                return None

        try:
            return self._to_snapshot(payload)
        except Exception:
            return None

    def _to_snapshot(self, payload: dict[str, Any]) -> StockSnapshot:
        """Map EastMoney payload into unified StockSnapshot model."""
        data = payload.get("data") or payload
        code = str(data.get("code") or data.get("f57") or "")
        name = str(data.get("name") or data.get("f58") or code)

        current_price = self._resolve_price(data, ["current_price", "f2"], scale_if_int=True)
        high_price = self._resolve_price(data, ["high_price", "f15"], scale_if_int=True)
        limit_down_price = self._resolve_price(data, ["limit_down_price", "f51"], scale_if_int=True)
        ask_v1 = self._resolve_int(data, ["ask_v1", "f31"])
        volume = self._resolve_int(data, ["volume", "f47"])

        return StockSnapshot(
            code=code,
            name=name,
            current_price=current_price,
            high_price=high_price,
            limit_down_price=limit_down_price,
            ask_v1=ask_v1,
            volume=volume,
            data_quality="tick_a1v",
            ts=datetime.now(),
        )

    @staticmethod
    def _resolve_price(data: dict[str, Any], keys: list[str], scale_if_int: bool = False) -> float:
        """Resolve first available price field and normalize textual numbers."""
        for key in keys:
            if key in data and data[key] not in (None, "", "-"):
                value = float(str(data[key]).replace(",", ""))
                # Some payloads send price in milli-units; normalize to price units.
                if scale_if_int and value > 10000:
                    return value / 1000.0
                return value
        return 0.0

    @staticmethod
    def _resolve_int(data: dict[str, Any], keys: list[str]) -> int:
        """Resolve first available integer-like field with missing-value fallback."""
        for key in keys:
            if key in data and data[key] not in (None, "", "-"):
                return int(float(str(data[key]).replace(",", "")))
        return 0

    async def fetch_snapshots(self, codes: Iterable[str]) -> list[StockSnapshot]:
        """Fetch snapshots concurrently for a batch of symbols."""
        codes = list(codes)
        if not codes:
            return []

        # Keep connector limit above semaphore to reduce queueing at TCP layer.
        connector = aiohttp.TCPConnector(limit=self.settings.MAX_CONCURRENCY * 2, keepalive_timeout=60)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self._fetch_one(session, code) for code in codes]
            items = await asyncio.gather(*tasks)

        return [item for item in items if item is not None]
