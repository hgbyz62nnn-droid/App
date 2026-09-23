"""Interface every exchange client implements.

To add Binance / OKX / Bitget: subclass `Exchange`, implement the methods, and register it in
`exchanges/__init__.py`. The pricing engine and Telegram bot only talk to this interface.

Order handling (e.g. releasing crypto) is deliberately *not* part of this interface yet. When it is
added, put it on a separate `OrderDesk` interface so a pricing-only deployment never gets an API key
with order permissions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from ..models import Ad, Side


class ExchangeError(Exception):
    """Raised for any API/transport failure; the engine logs it and retries next cycle."""


class Exchange(ABC):
    name: str

    @abstractmethod
    def get_my_user_id(self) -> str: ...

    @abstractmethod
    def get_my_ad(self, ad_id: str) -> Ad: ...

    @abstractmethod
    def get_competitor_ads(self, token: str, fiat: str, side: Side) -> list[Ad]: ...

    @abstractmethod
    def update_ad_price(self, ad: Ad, new_price: Decimal) -> None:
        """Change only the price of `ad`; every other ad setting must stay as it is."""
