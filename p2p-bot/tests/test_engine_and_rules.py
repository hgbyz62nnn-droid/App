from decimal import Decimal as D

import pytest

from p2pbot.config import dry_run_from
from p2pbot.engine import PricingEngine
from p2pbot.exchanges.base import Exchange, ExchangeError
from p2pbot.exchanges.bybit import build_update_body, parse_ad, sign
from p2pbot.models import Side
from p2pbot.rules import Rules, RulesStore

from .test_pricing import ad, my_ad


class FakeExchange(Exchange):
    name = "fake"

    def __init__(self, mine, competitors, fail=None):
        self.mine, self.competitors, self.fail = mine, competitors, fail
        self.updates = []

    def get_my_user_id(self):
        return "me"

    def get_my_ad(self, ad_id):
        if self.fail:
            raise ExchangeError(self.fail)
        return self.mine

    def get_competitor_ads(self, token, fiat, side):
        return self.competitors

    def update_ad_price(self, ad, new_price):
        self.updates.append(new_price)


def rules(**kw):
    return Rules(**{"min_price": D("1"), "max_price": D("100"), **kw})


# --- dry-run safety ------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("true", True), ("no", True), ("0", True), ("False", False), ("false", False),
])
def test_dry_run_is_on_unless_explicitly_false(value, expected):
    assert dry_run_from(value) is expected


def test_dry_run_never_calls_update():
    ex = FakeExchange(my_ad("51"), [ad("50")])
    res = PricingEngine(ex, "mine", 2, dry_run=True).run_cycle(rules())
    assert ex.updates == []
    assert any("dry-run" in m and "49.99" in m for m in res.messages)


def test_live_mode_updates():
    ex = FakeExchange(my_ad("51"), [ad("50")])
    PricingEngine(ex, "mine", 2, dry_run=False).run_cycle(rules())
    assert ex.updates == [D("49.99")]


def test_live_mode_refuses_without_bounds():
    ex = FakeExchange(my_ad("51"), [ad("50")])
    res = PricingEngine(ex, "mine", 2, dry_run=False).run_cycle(Rules())
    assert ex.updates == []
    assert res.messages


def test_clamp_alert_sent_once():
    ex = FakeExchange(my_ad("51"), [ad("10")])
    eng = PricingEngine(ex, "mine", 2, dry_run=True)
    r = rules(min_price=D("40"))
    first = eng.run_cycle(r).messages
    second = eng.run_cycle(r).messages
    assert any("🚧" in m for m in first)
    assert not any("🚧" in m for m in second)


def test_error_alert_once_then_recovery():
    ex = FakeExchange(my_ad("51"), [ad("50")], fail="boom")
    eng = PricingEngine(ex, "mine", 2, dry_run=True)
    assert len(eng.run_cycle(rules()).messages) == 1
    assert eng.run_cycle(rules()).messages == []
    ex.fail = None
    assert any("رجع" in m for m in eng.run_cycle(rules()).messages)


# --- rules persistence ---------------------------------------------------------------------------

def test_rules_roundtrip(tmp_path):
    store = RulesStore(tmp_path / "rules.json", Rules())
    r = Rules(min_price=D("48.5"), max_price=None, step=D("0.05"), interval_seconds=30, min_orders=7, paused=True)
    store.save(r)
    assert store.load() == r


def test_invalid_rules_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('{"step": "-1"}')
    defaults = Rules(step=D("0.02"))
    assert RulesStore(path, defaults).load() == defaults


@pytest.mark.parametrize("kw", [
    {"step": D("0")}, {"interval_seconds": 5}, {"min_price": D("10"), "max_price": D("5")},
    {"min_completion_rate": D("101")}, {"min_price": D("-1")},
])
def test_rules_validation(kw):
    with pytest.raises(ValueError):
        Rules(**kw).validate()


# --- bybit helpers -------------------------------------------------------------------------------

def test_sign_matches_hmac_sha256_hex():
    # timestamp + key + recv_window + body, HMAC-SHA256 lowercase hex
    import hashlib, hmac
    expected = hmac.new(b"secret", b"1700000000000key5000{}", hashlib.sha256).hexdigest()
    assert sign("secret", "1700000000000", "key", "5000", "{}") == expected


BYBIT_AD = {
    "id": "1898988222063644672", "userId": "1448939", "nickName": "me", "tokenId": "USDT",
    "currencyId": "EGP", "side": 1, "priceType": 0, "price": "50.10", "premium": "0",
    "quantity": "5000", "lastQuantity": "3200", "minAmount": "500", "maxAmount": "100000",
    "paymentPeriod": 15, "remark": "hi", "payments": ["14"],
    "paymentTerms": [{"id": "777", "paymentType": 14}],
    "tradingPreferenceSet": {"isKyc": 1},
    "recentExecuteRate": 98, "recentOrderNum": 250,
}


def test_parse_ad():
    a = parse_ad(BYBIT_AD)
    assert a.side is Side.SELL and a.price == D("50.10") and a.completion_rate == D("98")
    assert a.order_count == 250 and a.max_amount == D("100000")


def test_update_body_changes_only_price():
    body = build_update_body(BYBIT_AD, D("49.99"))
    assert body["price"] == "49.99"
    assert body["actionType"] == "MODIFY"
    assert body["paymentIds"] == ["777"]
    assert body["quantity"] == "3200"
    assert body["minAmount"] == "500" and body["maxAmount"] == "100000"
    assert body["remark"] == "hi" and body["tradingPreferenceSet"] == {"isKyc": 1}


def test_update_body_rejects_floating_ads():
    with pytest.raises(ExchangeError):
        build_update_body({**BYBIT_AD, "priceType": 1}, D("1"))


def test_selftest_scrubs_secrets():
    from p2pbot.selftest import scrub
    assert scrub("bad token 123:ABC in url, sss", ["123:ABC", "", "s"]) == "bad token *** in url, sss"
