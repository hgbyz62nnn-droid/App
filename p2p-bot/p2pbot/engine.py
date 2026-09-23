"""One pricing cycle: fetch -> decide -> (maybe) update -> report."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .exchanges import Exchange, ExchangeError
from .pricing import Clamp, Decision, decide
from .rules import Rules

log = logging.getLogger(__name__)


@dataclass
class EngineState:
    last_run: float | None = None
    last_decision: Decision | None = None
    last_error: str | None = None
    last_clamp: Clamp = Clamp.NONE
    no_competitors_alerted: bool = False
    bounds_missing_alerted: bool = False
    updates_done: int = 0


@dataclass
class CycleResult:
    decision: Decision | None
    messages: list[str] = field(default_factory=list)  # Telegram notifications to send


class PricingEngine:
    def __init__(self, exchange: Exchange, ad_id: str, price_decimals: int, dry_run: bool):
        self.exchange = exchange
        self.ad_id = ad_id
        self.price_decimals = price_decimals
        self.dry_run = dry_run
        self.state = EngineState()
        self._my_user_id: str | None = None

    def _user_id(self) -> str:
        if self._my_user_id is None:
            self._my_user_id = self.exchange.get_my_user_id()
            log.info("My %s userId: %s", self.exchange.name, self._my_user_id)
        return self._my_user_id

    def run_cycle(self, rules: Rules) -> CycleResult:
        self.state.last_run = time.time()
        try:
            result = self._run(rules)
        except ExchangeError as exc:
            log.error("Cycle failed: %s", exc)
            msgs = []
            if self.state.last_error != str(exc):  # alert on new errors only, not every cycle
                msgs.append(f"⚠️ خطأ من {self.exchange.name}: {exc}")
            self.state.last_error = str(exc)
            return CycleResult(None, msgs)
        if self.state.last_error:
            result.messages.insert(0, "✅ رجع يشتغل بعد الخطأ.")
            self.state.last_error = None
        return result

    def _run(self, rules: Rules) -> CycleResult:
        messages: list[str] = []

        my_ad = self.exchange.get_my_ad(self.ad_id)
        competitors = self.exchange.get_competitor_ads(my_ad.token, my_ad.fiat, my_ad.side)
        decision = decide(my_ad, self._user_id(), competitors, rules, self.price_decimals)
        self.state.last_decision = decision
        log.info(
            "ad=%s side=%s %s/%s current=%s target=%s best=%s(%s) eligible=%d/%d update=%s reason=%s",
            my_ad.ad_id, my_ad.side.value, my_ad.token, my_ad.fiat, decision.current_price,
            decision.target_price, decision.best_competitor.nickname if decision.best_competitor else None,
            decision.best_competitor.price if decision.best_competitor else None,
            decision.competitors_considered, len(competitors), decision.should_update, decision.reason,
        )

        if decision.best_competitor is None:
            if not self.state.no_competitors_alerted:
                messages.append("ℹ️ مفيش منافس عدّى الفلاتر، السعر ثابت. راجع /filters.")
                self.state.no_competitors_alerted = True
            return CycleResult(decision, messages)
        self.state.no_competitors_alerted = False

        if decision.clamp is not Clamp.NONE and decision.clamp is not self.state.last_clamp:
            bound = "الحد الأدنى" if decision.clamp is Clamp.MIN else "الحد الأقصى"
            messages.append(
                f"🚧 السعر المطلوب برا الحدود، ثابت على {bound}: {decision.target_price} "
                f"(أفضل منافس {decision.best_competitor.nickname} @ {decision.best_competitor.price})"
            )
        self.state.last_clamp = decision.clamp

        if not decision.should_update:
            return CycleResult(decision, messages)

        summary = (
            f"{my_ad.token}/{my_ad.fiat} {'شراء' if my_ad.side.value == 'buy' else 'بيع'}: "
            f"{decision.current_price} ← {decision.target_price}\n"
            f"أفضل منافس: {decision.best_competitor.nickname} @ {decision.best_competitor.price}"
        )
        if not self.dry_run and (rules.min_price is None or rules.max_price is None):
            log.warning("Live update blocked: min/max price not set")
            if not self.state.bounds_missing_alerted:
                messages.append("⛔️ مش هغيّر السعر فعلًا من غير حد أدنى وأقصى. استخدم /min و /max.")
                self.state.bounds_missing_alerted = True
            return CycleResult(decision, messages)
        self.state.bounds_missing_alerted = False

        if self.dry_run:
            log.info("DRY-RUN: would update ad %s to %s", my_ad.ad_id, decision.target_price)
            messages.append(f"🧪 [dry-run] كنت هغيّره لـ {decision.target_price}\n{summary}")
        else:
            self.exchange.update_ad_price(my_ad, decision.target_price)
            self.state.updates_done += 1
            log.info("UPDATED ad %s: %s -> %s", my_ad.ad_id, decision.current_price, decision.target_price)
            messages.append(f"✏️ غيّرت السعر\n{summary}")
        return CycleResult(decision, messages)
