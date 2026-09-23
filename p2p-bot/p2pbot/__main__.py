"""Entry point: python -m p2pbot"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import load_settings
from .engine import PricingEngine
from .exchanges import create_exchange
from .rules import RulesStore
from .telegram_bot import ControlBot


def setup_logging(log_dir) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    # The file log is a convenience; journald still has everything, so never crash over it.
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    except OSError as exc:
        root.warning("File logging disabled (%s); logging to journald only. Fix: chown -R p2pbot:p2pbot %s",
                     exc, log_dir)
    else:
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    # httpx logs every Telegram poll, including the bot token in the URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_dir)
    log = logging.getLogger("p2pbot")
    log.info("Starting: exchange=%s ad=%s dry_run=%s", settings.exchange, settings.ad_id, settings.dry_run)

    exchange = create_exchange(settings.exchange, settings.env)
    engine = PricingEngine(exchange, settings.ad_id, settings.price_decimals, settings.dry_run)
    store = RulesStore(settings.data_dir / "rules.json", settings.default_rules)
    ControlBot(settings.telegram_token, settings.telegram_chat_id, engine, store).run()


if __name__ == "__main__":
    main()
