"""Telegram control panel. Only answers the configured chat_id."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from .engine import PricingEngine
from .rules import RulesStore

log = logging.getLogger(__name__)

JOB_NAME = "pricing"

HELP = """الأوامر:
/status - الحالة والقواعد وآخر دورة
/pause - إيقاف التسعير
/resume - تشغيل التسعير
/check - شغّل دورة دلوقتي
/min <سعر|off> - الحد الأدنى
/max <سعر|off> - الحد الأقصى
/step <قيمة> - الفرق عن أفضل منافس
/threshold <قيمة> - أقل تغيير يستاهل تعديل
/interval <ثواني> - كل قد إيه يشتغل
/filters - عرض فلاتر المنافسين
/filters rate <نسبة> - أقل نسبة إتمام %
/filters orders <عدد> - أقل عدد أوردرات
/filters amount <مبلغ> - أقل حد أقصى للإعلان (بالعملة المحلية)"""


FILTERS_HELP = "\n".join(line for line in HELP.splitlines() if line.startswith("/filters "))


class ControlBot:
    def __init__(self, token: str, chat_id: int, engine: PricingEngine, store: RulesStore):
        self.chat_id = chat_id
        self.engine = engine
        self.store = store
        self.rules = store.load()
        self._cycle_lock = asyncio.Lock()
        self.app = Application.builder().token(token).build()

        only_me = filters.Chat(chat_id=chat_id)
        for name, handler in {
            "start": self.cmd_help, "help": self.cmd_help, "status": self.cmd_status,
            "pause": self.cmd_pause, "resume": self.cmd_resume, "check": self.cmd_check,
            "min": self.cmd_min, "max": self.cmd_max, "step": self.cmd_step,
            "threshold": self.cmd_threshold, "interval": self.cmd_interval, "filters": self.cmd_filters,
        }.items():
            self.app.add_handler(CommandHandler(name, handler, filters=only_me))
        self.app.post_init = self._on_start

    def run(self) -> None:
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    # --- scheduling -------------------------------------------------------------------------------

    async def _on_start(self, app: Application) -> None:
        self._schedule()
        mode = "🧪 dry-run (مش هيغيّر حاجة فعلًا)" if self.engine.dry_run else "🔴 LIVE (هيغيّر الأسعار فعلًا)"
        await self.notify(f"🤖 البوت اشتغل على {self.engine.exchange.name}\nالوضع: {mode}\n\n{self._rules_text()}")

    def _schedule(self) -> None:
        for job in self.app.job_queue.get_jobs_by_name(JOB_NAME):
            job.schedule_removal()
        self.app.job_queue.run_repeating(self._tick, interval=self.rules.interval_seconds, first=1, name=JOB_NAME)
        log.info("Pricing job scheduled every %ss", self.rules.interval_seconds)

    async def _tick(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.rules.paused:
            return
        await self._cycle()

    async def _cycle(self) -> None:
        if self._cycle_lock.locked():
            log.info("Previous cycle still running; skipping")
            return
        async with self._cycle_lock:
            try:
                result = await asyncio.to_thread(self.engine.run_cycle, self.rules)
            except Exception:  # never let one bad cycle kill the scheduler
                log.exception("Unexpected error in pricing cycle")
                await self.notify("⚠️ خطأ غير متوقع في دورة التسعير، راجع اللوج.")
                return
        for msg in result.messages:
            await self.notify(msg)

    async def notify(self, text: str) -> None:
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception:
            log.exception("Failed to send Telegram message")

    # --- rules ------------------------------------------------------------------------------------

    async def _update_rules(self, update: Update, **changes) -> bool:
        new = dataclasses.replace(self.rules, **changes)
        try:
            new.validate()
        except ValueError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return False
        self.rules = new
        self.store.save(new)
        log.info("Rules changed via Telegram: %s", changes)
        await update.message.reply_text(f"✅ اتحفظ.\n\n{self._rules_text()}")
        return True

    def _rules_text(self) -> str:
        r = self.rules
        return (
            f"الحد الأدنى: {r.min_price if r.min_price is not None else 'مفيش'}\n"
            f"الحد الأقصى: {r.max_price if r.max_price is not None else 'مفيش'}\n"
            f"step: {r.step}\n"
            f"threshold: {r.min_change}\n"
            f"interval: {r.interval_seconds}s\n"
            f"فلاتر: إتمام ≥ {r.min_completion_rate}% · أوردرات ≥ {r.min_orders} · حد الإعلان ≥ {r.min_ad_amount}\n"
            f"الحالة: {'⏸ موقوف' if r.paused else '▶️ شغال'}"
        )

    # --- commands ---------------------------------------------------------------------------------

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        s = self.engine.state
        mode = "🧪 dry-run" if self.engine.dry_run else "🔴 LIVE"
        lines = [f"المنصة: {self.engine.exchange.name} · الإعلان: {self.engine.ad_id} · {mode}", self._rules_text(), ""]
        if s.last_run:
            lines.append(f"آخر دورة: {datetime.fromtimestamp(s.last_run):%Y-%m-%d %H:%M:%S}")
        d = s.last_decision
        if d:
            lines.append(f"سعري: {d.current_price} · الهدف: {d.target_price if d.target_price is not None else '-'}")
            if d.best_competitor:
                lines.append(f"أفضل منافس: {d.best_competitor.nickname} @ {d.best_competitor.price} "
                             f"(من {d.competitors_considered} بعد الفلترة)")
            lines.append(f"السبب: {d.reason}")
        if s.last_error:
            lines.append(f"⚠️ آخر خطأ: {s.last_error}")
        lines.append(f"تعديلات فعلية من ساعة التشغيل: {s.updates_done}")
        await update.message.reply_text("\n".join(lines))

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._update_rules(update, paused=True)

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._update_rules(update, paused=False)

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.rules.paused:
            await update.message.reply_text("⏸ البوت موقوف. استخدم /resume الأول.")
            return
        await update.message.reply_text("⏳ بشغّل دورة...")
        await self._cycle()
        await self.cmd_status(update, context)

    async def _set_decimal(self, update: Update, args: list[str], field: str, allow_off: bool = False) -> None:
        if len(args) != 1:
            await update.message.reply_text(f"الاستخدام: /{update.message.text.split()[0][1:]} <قيمة>"
                                            + (" أو off" if allow_off else ""))
            return
        if allow_off and args[0].lower() == "off":
            await self._update_rules(update, **{field: None})
            return
        value = parse_decimal(args[0])
        if value is None:
            await update.message.reply_text("❌ رقم مش صحيح")
            return
        await self._update_rules(update, **{field: value})

    async def cmd_min(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_decimal(update, context.args, "min_price", allow_off=True)

    async def cmd_max(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_decimal(update, context.args, "max_price", allow_off=True)

    async def cmd_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_decimal(update, context.args, "step")

    async def cmd_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_decimal(update, context.args, "min_change")

    async def cmd_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 1 or not context.args[0].isdigit():
            await update.message.reply_text("الاستخدام: /interval <ثواني>")
            return
        if await self._update_rules(update, interval_seconds=int(context.args[0])):
            self._schedule()

    async def cmd_filters(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if not args:
            await update.message.reply_text(self._rules_text() + "\n\n" + FILTERS_HELP)
            return
        if len(args) != 2 or args[0] not in ("rate", "orders", "amount"):
            await update.message.reply_text("الاستخدام: /filters rate|orders|amount <قيمة>")
            return
        key, raw = args
        if key == "orders":
            if not raw.isdigit():
                await update.message.reply_text("❌ لازم رقم صحيح")
                return
            await self._update_rules(update, min_orders=int(raw))
            return
        value = parse_decimal(raw)
        if value is None:
            await update.message.reply_text("❌ رقم مش صحيح")
            return
        field = "min_completion_rate" if key == "rate" else "min_ad_amount"
        await self._update_rules(update, **{field: value})


def parse_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None
