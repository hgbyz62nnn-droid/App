from .base import Exchange, ExchangeError


def create_exchange(name: str, env: dict[str, str]) -> Exchange:
    name = name.lower()
    if name == "bybit":
        from .bybit import Bybit

        return Bybit(
            api_key=env.get("BYBIT_API_KEY", ""),
            api_secret=env.get("BYBIT_API_SECRET", ""),
            base_url=env.get("BYBIT_BASE_URL") or "https://api.bybit.com",
        )
    raise ValueError(f"Unsupported exchange: {name!r} (supported: bybit)")


__all__ = ["Exchange", "ExchangeError", "create_exchange"]
