"""Pure pricing logic: no I/O, so it is fully unit-testable."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import Enum

from .models import Ad, Side
from .rules import Rules


class Clamp(str, Enum):
    NONE = "none"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True)
class Decision:
    current_price: Decimal
    target_price: Decimal | None  # None -> nothing to follow
    best_competitor: Ad | None
    competitors_considered: int
    clamp: Clamp
    should_update: bool
    reason: str


def is_better(side: Side, a: Decimal, b: Decimal) -> bool:
    """True if price `a` is more attractive to counterparties than `b` for an ad on `side`."""
    return a > b if side is Side.BUY else a < b


def filter_competitors(ads: list[Ad], my_ad: Ad, my_user_id: str, rules: Rules) -> list[Ad]:
    result = []
    for ad in ads:
        if ad.user_id == my_user_id or ad.ad_id == my_ad.ad_id:
            continue
        if ad.side is not my_ad.side or ad.token != my_ad.token or ad.fiat != my_ad.fiat:
            continue
        if ad.completion_rate < rules.min_completion_rate:
            continue
        if ad.order_count < rules.min_orders:
            continue
        if ad.max_amount < rules.min_ad_amount:
            continue
        result.append(ad)
    return result


def best_ad(side: Side, ads: list[Ad]) -> Ad | None:
    best = None
    for ad in ads:
        if best is None or is_better(side, ad.price, best.price):
            best = ad
    return best


def quantize(price: Decimal, decimals: int, side: Side) -> Decimal:
    """Round to the exchange's tick, always in the direction that keeps us ahead of the competitor."""
    exp = Decimal(1).scaleb(-decimals)
    rounding = ROUND_CEILING if side is Side.BUY else ROUND_FLOOR
    return price.quantize(exp, rounding=rounding)


def clamp(price: Decimal, rules: Rules) -> tuple[Decimal, Clamp]:
    if rules.min_price is not None and price < rules.min_price:
        return rules.min_price, Clamp.MIN
    if rules.max_price is not None and price > rules.max_price:
        return rules.max_price, Clamp.MAX
    return price, Clamp.NONE


def decide(my_ad: Ad, my_user_id: str, competitors: list[Ad], rules: Rules, price_decimals: int) -> Decision:
    side = my_ad.side
    current = my_ad.price
    eligible = filter_competitors(competitors, my_ad, my_user_id, rules)
    best = best_ad(side, eligible)

    if best is None:
        return Decision(current, None, None, 0, Clamp.NONE, False, "no competitor passed the filters")

    raw_target = best.price + rules.step if side is Side.BUY else best.price - rules.step
    target, clamped = clamp(quantize(raw_target, price_decimals, side), rules)

    current_out_of_bounds = clamp(current, rules)[1] is not Clamp.NONE
    diff = abs(target - current)

    if target == current:
        should, reason = False, "already at target"
    elif current_out_of_bounds:
        should, reason = True, "current price is outside min/max bounds"
    elif diff < rules.min_change:
        should, reason = False, f"change {diff} below min_change {rules.min_change}"
    else:
        should, reason = True, f"beat best competitor {best.nickname} @ {best.price} by step {rules.step}"

    if clamped is not Clamp.NONE:
        reason += f" (clamped to {clamped.value} {target}; wanted {raw_target})"

    return Decision(current, target, best, len(eligible), clamped, should, reason)
