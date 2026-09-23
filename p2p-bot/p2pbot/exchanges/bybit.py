"""Bybit P2P client (https://bybit-exchange.github.io/docs/p2p/guide).

Endpoints used (all POST, HMAC-SHA256 signed):
  /v5/p2p/user/personal/info  - my userId (to exclude my own ads)
  /v5/p2p/item/info           - my ad's full settings
  /v5/p2p/item/online         - competitors' online ads
  /v5/p2p/item/update         - modify my ad (actionType=MODIFY)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from ..models import Ad, Side
from .base import Exchange, ExchangeError

log = logging.getLogger(__name__)

# Bybit P2P "side": 0 = buy ad, 1 = sell ad (from the advertiser's point of view).
_SIDE_TO_BYBIT = {Side.BUY: "0", Side.SELL: "1"}
_BYBIT_TO_SIDE = {"0": Side.BUY, "1": Side.SELL}

PAGE_SIZE = 100
MAX_PAGES = 3


def _dec(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal(default)
    except InvalidOperation:
        return Decimal(default)


def _int(value: Any) -> int:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def sign(secret: str, timestamp: str, api_key: str, recv_window: str, payload: str) -> str:
    message = f"{timestamp}{api_key}{recv_window}{payload}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def parse_ad(item: dict[str, Any]) -> Ad:
    return Ad(
        ad_id=str(item["id"]),
        user_id=str(item.get("userId", "")),
        nickname=str(item.get("nickName", "")),
        side=_BYBIT_TO_SIDE[str(item["side"])],
        token=str(item["tokenId"]),
        fiat=str(item["currencyId"]),
        price=_dec(item["price"]),
        min_amount=_dec(item.get("minAmount")),
        max_amount=_dec(item.get("maxAmount")),
        completion_rate=_dec(item.get("recentExecuteRate")),
        order_count=_int(item.get("recentOrderNum")),
        raw=item,
    )


def build_update_body(raw: dict[str, Any], new_price: Decimal) -> dict[str, Any]:
    """Build a MODIFY request that keeps every setting of the ad except the price."""
    payment_ids = [str(t["id"]) for t in raw.get("paymentTerms") or [] if t.get("id") is not None]
    if not payment_ids:
        payment_ids = [str(p) for p in raw.get("payments") or []]
    if not payment_ids:
        raise ExchangeError("ad has no payment methods in /v5/p2p/item/info; refusing to update")
    if str(raw.get("priceType", "0")) != "0":
        raise ExchangeError("ad uses floating pricing (priceType=1); only fixed-price ads are supported")
    return {
        "id": str(raw["id"]),
        "priceType": "0",
        "premium": str(raw.get("premium") or ""),
        "price": str(new_price),
        "minAmount": str(raw["minAmount"]),
        "maxAmount": str(raw["maxAmount"]),
        "remark": str(raw.get("remark") or ""),
        "tradingPreferenceSet": raw.get("tradingPreferenceSet") or {},
        "paymentIds": payment_ids,
        # Remaining quantity: re-submitting the original total would re-add already-sold coins.
        "quantity": str(raw.get("lastQuantity") or raw["quantity"]),
        "paymentPeriod": str(raw["paymentPeriod"]),
        "actionType": "MODIFY",
    }


class Bybit(Exchange):
    name = "bybit"

    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.bybit.com",
                 recv_window: int = 5000, timeout: float = 10.0):
        if not api_key or not api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")
        self._key = api_key
        self._secret = api_secret
        self._base = base_url.rstrip("/")
        self._recv = str(recv_window)
        self._timeout = timeout
        self._http = requests.Session()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        payload = json.dumps(body, separators=(",", ":"))
        ts = str(int(time.time() * 1000))
        headers = {
            "X-BAPI-API-KEY": self._key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": self._recv,
            "X-BAPI-SIGN": sign(self._secret, ts, self._key, self._recv, payload),
            "Content-Type": "application/json",
        }
        log.debug("POST %s %s", path, payload)
        try:
            resp = self._http.post(self._base + path, data=payload, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise ExchangeError(f"{path}: network error: {exc}") from exc
        if resp.status_code != 200:
            raise ExchangeError(f"{path}: HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExchangeError(f"{path}: invalid JSON: {resp.text[:300]}") from exc
        # P2P endpoints answer with ret_code/ret_msg; the rest of v5 with retCode/retMsg.
        code = data.get("ret_code", data.get("retCode"))
        if code != 0:
            msg = data.get("ret_msg", data.get("retMsg"))
            raise ExchangeError(f"{path}: error {code}: {msg}")
        return data.get("result")

    def get_my_user_id(self) -> str:
        result = self._post("/v5/p2p/user/personal/info", {})
        user_id = str(result.get("userId", "")) if result else ""
        if not user_id:
            raise ExchangeError("personal/info returned no userId")
        return user_id

    def get_my_ad(self, ad_id: str) -> Ad:
        return parse_ad(self._post("/v5/p2p/item/info", {"itemId": ad_id}))

    def get_competitor_ads(self, token: str, fiat: str, side: Side) -> list[Ad]:
        ads: list[Ad] = []
        for page in range(1, MAX_PAGES + 1):
            result = self._post("/v5/p2p/item/online", {
                "tokenId": token, "currencyId": fiat, "side": _SIDE_TO_BYBIT[side],
                "page": str(page), "size": str(PAGE_SIZE),
            }) or {}
            items = result.get("items") or []
            for item in items:
                try:
                    ads.append(parse_ad(item))
                except (KeyError, ValueError) as exc:
                    log.warning("Skipping unparseable ad %s: %s", item.get("id"), exc)
            if len(items) < PAGE_SIZE:
                break
        return ads

    def update_ad_price(self, ad: Ad, new_price: Decimal) -> None:
        result = self._post("/v5/p2p/item/update", build_update_body(ad.raw, new_price)) or {}
        if result.get("needSecurityRisk"):
            raise ExchangeError("Bybit requires a security verification for this update; do it in the app")
