"""Exchange-neutral data types shared by the pricing engine and every exchange client."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class Side(str, Enum):
    """Which side the *advertiser* is on.

    BUY  = the advertiser buys crypto (pays fiat). A higher price is better for the counterparty.
    SELL = the advertiser sells crypto (receives fiat). A lower price is better for the counterparty.
    """

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Ad:
    """One advertisement, normalised from whatever the exchange returns."""

    ad_id: str
    user_id: str
    nickname: str
    side: Side
    token: str
    fiat: str
    price: Decimal
    min_amount: Decimal
    max_amount: Decimal
    completion_rate: Decimal  # percent, 0-100
    order_count: int
    # Untouched exchange payload, needed when writing the ad back (e.g. Bybit's update requires every field).
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
