"""Static settings, read only from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from .rules import Rules

ROOT = Path(__file__).resolve().parent.parent


def _dec(env: dict, key: str, default: str | None) -> Decimal | None:
    value = (env.get(key) or "").strip()
    if not value:
        return Decimal(default) if default is not None else None
    return Decimal(value)


def _int(env: dict, key: str, default: int) -> int:
    value = (env.get(key) or "").strip()
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    exchange: str
    ad_id: str
    telegram_token: str
    telegram_chat_id: int
    dry_run: bool
    price_decimals: int
    data_dir: Path
    log_dir: Path
    env: dict[str, str]
    default_rules: Rules


def dry_run_from(value: str | None) -> bool:
    # Anything other than an explicit "false" keeps dry-run on.
    return (value or "").strip().lower() != "false"


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env")
    env = dict(os.environ)

    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "AD_ID") if not env.get(k, "").strip()]
    if missing:
        raise SystemExit(f"Missing required settings in .env: {', '.join(missing)}")

    rules = Rules(
        min_price=_dec(env, "MIN_PRICE", None),
        max_price=_dec(env, "MAX_PRICE", None),
        step=_dec(env, "STEP", "0.01"),
        min_change=_dec(env, "MIN_CHANGE", "0.01"),
        interval_seconds=_int(env, "INTERVAL_SECONDS", 60),
        min_completion_rate=_dec(env, "FILTER_MIN_COMPLETION_RATE", "0"),
        min_orders=_int(env, "FILTER_MIN_ORDERS", 0),
        min_ad_amount=_dec(env, "FILTER_MIN_AD_AMOUNT", "0"),
    )
    rules.validate()

    return Settings(
        exchange=(env.get("EXCHANGE") or "bybit").strip(),
        ad_id=env["AD_ID"].strip(),
        telegram_token=env["TELEGRAM_BOT_TOKEN"].strip(),
        telegram_chat_id=int(env["TELEGRAM_CHAT_ID"].strip()),
        dry_run=dry_run_from(env.get("DRY_RUN")),
        price_decimals=_int(env, "PRICE_DECIMALS", 2),
        data_dir=ROOT / "data",
        log_dir=ROOT / "logs",
        env=env,
        default_rules=rules,
    )
