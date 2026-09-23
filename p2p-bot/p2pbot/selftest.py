"""Connectivity check: python -m p2pbot.selftest

Verifies .env loads, Bybit answers with this key, the ad is readable, and Telegram can deliver a message.
Prints only OK/FAIL lines; secrets are scrubbed from any error text.
"""
from __future__ import annotations

import asyncio
import sys

from telegram import Bot

from .config import load_settings
from .exchanges import create_exchange

SECRET_KEYS = ("BYBIT_API_KEY", "BYBIT_API_SECRET", "TELEGRAM_BOT_TOKEN")


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if len(s) >= 6:  # real keys/tokens are long; short values would garble the message
            text = text.replace(s, "***")
    return text


def main() -> int:
    settings = load_settings()
    secrets = [settings.env.get(k, "") for k in SECRET_KEYS]
    failed = False

    def report(name: str, fn):
        nonlocal failed
        try:
            detail = fn()
            print(f"OK    {name}{': ' + detail if detail else ''}")
        except Exception as exc:  # report and continue with the other checks
            failed = True
            print(f"FAIL  {name}: {scrub(f'{type(exc).__name__}: {exc}', secrets)}")

    print(f"mode: {'dry-run' if settings.dry_run else 'LIVE'}")
    exchange = create_exchange(settings.exchange, settings.env)
    report("bybit auth", lambda: f"userId {exchange.get_my_user_id()}")

    def ad():
        a = exchange.get_my_ad(settings.ad_id)
        return f"{a.token}/{a.fiat} {a.side.value} @ {a.price}"
    report("bybit ad", ad)

    async def telegram():
        async with Bot(settings.telegram_token) as bot:
            me = await bot.get_me()
            await bot.send_message(settings.telegram_chat_id,
                                   "🧪 رسالة تجربة من p2p-bot: الاتصال بتليجرام شغال.")
            return f"@{me.username} -> message sent"
    report("telegram", lambda: asyncio.run(telegram()))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
