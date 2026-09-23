"""Runtime-tunable pricing rules, editable from Telegram and persisted to disk."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from pathlib import Path

log = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 15


@dataclass
class Rules:
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    step: Decimal = Decimal("0.01")
    # Skip the update when |target - current| is below this, to save the exchange's edit quota.
    min_change: Decimal = Decimal("0.01")
    interval_seconds: int = 60
    # Competitor filters
    min_completion_rate: Decimal = Decimal("0")  # percent
    min_orders: int = 0
    min_ad_amount: Decimal = Decimal("0")  # competitor ad's max order amount (fiat) must be >= this
    paused: bool = False

    def validate(self) -> None:
        if self.step <= 0:
            raise ValueError("step must be > 0")
        if self.min_change < 0:
            raise ValueError("min_change must be >= 0")
        if self.interval_seconds < MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval must be >= {MIN_INTERVAL_SECONDS} seconds")
        if not (0 <= self.min_completion_rate <= 100):
            raise ValueError("completion rate must be between 0 and 100")
        if self.min_orders < 0 or self.min_ad_amount < 0:
            raise ValueError("filters must be >= 0")
        for name in ("min_price", "max_price"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be > 0")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min price must be <= max price")

    # --- persistence -----------------------------------------------------------------------------

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict) -> "Rules":
        kwargs = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            if value is None:
                kwargs[f.name] = None
            elif f.name in ("interval_seconds", "min_orders"):
                kwargs[f.name] = int(value)
            elif f.name == "paused":
                kwargs[f.name] = bool(value)
            else:
                kwargs[f.name] = Decimal(str(value))
        rules = cls(**kwargs)
        rules.validate()
        return rules


class RulesStore:
    def __init__(self, path: Path, defaults: Rules):
        self.path = path
        self.defaults = defaults

    def load(self) -> Rules:
        if not self.path.exists():
            log.info("No rules file at %s, using defaults from .env", self.path)
            return self.defaults
        try:
            rules = Rules.from_json(json.loads(self.path.read_text(encoding="utf-8")))
            log.info("Loaded rules from %s", self.path)
            return rules
        except (ValueError, TypeError, ArithmeticError) as exc:
            log.error("Rules file %s is invalid (%s); using defaults from .env", self.path, exc)
            return self.defaults

    def save(self, rules: Rules) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".rules-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rules.to_json(), fh, indent=2)
        os.replace(tmp, self.path)
        log.info("Saved rules: %s", rules.to_json())
