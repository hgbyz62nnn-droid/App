from decimal import Decimal as D

import pytest

from p2pbot.models import Ad, Side
from p2pbot.pricing import Clamp, decide, filter_competitors, quantize
from p2pbot.rules import Rules

ME = "me"


def ad(price, side=Side.SELL, user="u1", ad_id=None, rate="100", orders=500, max_amount="50000",
       token="USDT", fiat="EGP"):
    return Ad(ad_id=ad_id or f"ad-{user}-{price}", user_id=user, nickname=user, side=side, token=token,
              fiat=fiat, price=D(str(price)), min_amount=D("100"), max_amount=D(max_amount),
              completion_rate=D(rate), order_count=orders)


def my_ad(price, side=Side.SELL):
    return ad(price, side=side, user=ME, ad_id="mine")


def rules(**kw):
    base = dict(min_price=D("1"), max_price=D("1000"), step=D("0.01"), min_change=D("0.01"))
    base.update(kw)
    return Rules(**base)


# --- direction -----------------------------------------------------------------------------------

def test_sell_ad_undercuts_lowest_competitor():
    d = decide(my_ad("51.00"), ME, [ad("50.50", user="a"), ad("50.20", user="b")], rules(), 2)
    assert d.best_competitor.user_id == "b"
    assert d.target_price == D("50.19")
    assert d.should_update


def test_buy_ad_outbids_highest_competitor():
    comps = [ad("49.80", Side.BUY, "a"), ad("50.10", Side.BUY, "b")]
    d = decide(my_ad("49.00", Side.BUY), ME, comps, rules(), 2)
    assert d.best_competitor.user_id == "b"
    assert d.target_price == D("50.11")
    assert d.should_update


def test_custom_step():
    d = decide(my_ad("51"), ME, [ad("50.00")], rules(step=D("0.25")), 2)
    assert d.target_price == D("49.75")


# --- exclusion & filters -------------------------------------------------------------------------

def test_excludes_my_own_ads_by_user_and_ad_id():
    comps = [ad("40.00", user=ME), ad("41.00", user="x", ad_id="mine"), ad("50.00", user="a")]
    d = decide(my_ad("51"), ME, comps, rules(), 2)
    assert d.best_competitor.user_id == "a"


def test_ignores_other_side_token_and_fiat():
    comps = [ad("40", Side.BUY, "a"), ad("40", user="b", token="BTC"), ad("40", user="c", fiat="USD"),
             ad("50", user="d")]
    assert [a.user_id for a in filter_competitors(comps, my_ad("51"), ME, rules())] == ["d"]


@pytest.mark.parametrize("field,value,bad_kw", [
    ("min_completion_rate", D("95"), {"rate": "90"}),
    ("min_orders", 100, {"orders": 20}),
    ("min_ad_amount", D("5000"), {"max_amount": "1000"}),
])
def test_filters_drop_weak_ads(field, value, bad_kw):
    fake = ad("45.00", user="fake", **bad_kw)
    real = ad("50.00", user="real")
    d = decide(my_ad("51"), ME, [fake, real], rules(**{field: value}), 2)
    assert d.best_competitor.user_id == "real"
    assert d.target_price == D("49.99")


def test_filter_boundaries_are_inclusive():
    comp = ad("50", rate="95", orders=100, max_amount="5000")
    r = rules(min_completion_rate=D("95"), min_orders=100, min_ad_amount=D("5000"))
    assert filter_competitors([comp], my_ad("51"), ME, r) == [comp]


def test_no_competitors_keeps_price():
    d = decide(my_ad("51"), ME, [ad("40", rate="10")], rules(min_completion_rate=D("90")), 2)
    assert d.target_price is None
    assert d.best_competitor is None
    assert not d.should_update


# --- bounds --------------------------------------------------------------------------------------

def test_sell_target_below_min_is_clamped_to_min():
    d = decide(my_ad("51"), ME, [ad("45.00")], rules(min_price=D("48")), 2)
    assert d.target_price == D("48")
    assert d.clamp is Clamp.MIN
    assert d.should_update


def test_buy_target_above_max_is_clamped_to_max():
    d = decide(my_ad("49", Side.BUY), ME, [ad("55", Side.BUY)], rules(max_price=D("52")), 2)
    assert d.target_price == D("52")
    assert d.clamp is Clamp.MAX


def test_already_at_bound_does_not_update():
    d = decide(my_ad("48"), ME, [ad("45")], rules(min_price=D("48")), 2)
    assert d.clamp is Clamp.MIN
    assert not d.should_update


def test_no_bounds_set_does_not_clamp():
    d = decide(my_ad("51"), ME, [ad("0.50")], rules(min_price=None, max_price=None), 2)
    assert d.target_price == D("0.49")
    assert d.clamp is Clamp.NONE


# --- min change threshold ------------------------------------------------------------------------

def test_small_change_is_skipped():
    d = decide(my_ad("50.00"), ME, [ad("50.04")], rules(min_change=D("0.05")), 2)
    assert d.target_price == D("50.03")
    assert not d.should_update


def test_change_equal_to_threshold_updates():
    d = decide(my_ad("50.00"), ME, [ad("50.06")], rules(min_change=D("0.05")), 2)
    assert d.target_price == D("50.05")
    assert d.should_update


def test_out_of_bounds_current_price_updates_even_if_change_small():
    # User raised min to 50.02 while the ad sits at 50.00; fix it regardless of threshold.
    d = decide(my_ad("50.00"), ME, [ad("49.00")], rules(min_price=D("50.02"), min_change=D("1")), 2)
    assert d.target_price == D("50.02")
    assert d.should_update


def test_already_at_target():
    d = decide(my_ad("49.99"), ME, [ad("50.00")], rules(), 2)
    assert not d.should_update


def test_follows_competitor_upward_when_they_raise():
    # Sell ad: competitor moved up, we should raise too (less underpricing), not stay cheap.
    d = decide(my_ad("49.00"), ME, [ad("50.00")], rules(), 2)
    assert d.target_price == D("49.99")
    assert d.should_update


# --- rounding ------------------------------------------------------------------------------------

def test_quantize_keeps_us_ahead():
    assert quantize(D("50.1234"), 2, Side.SELL) == D("50.12")  # lower is better
    assert quantize(D("50.1234"), 2, Side.BUY) == D("50.13")   # higher is better
    assert quantize(D("50.5"), 0, Side.SELL) == D("50")


def test_step_smaller_than_tick_still_beats_competitor():
    d = decide(my_ad("51"), ME, [ad("50.00")], rules(step=D("0.001")), 2)
    assert d.target_price == D("49.99")
