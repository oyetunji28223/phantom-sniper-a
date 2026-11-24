"""Format a local-only simulation notification; this module never sends messages."""

from typing import Any


def format_simulation_alert(trade: dict[str, Any]) -> str:
    return (
        f"[PAPER ONLY] {trade['symbol']} on {trade['virtual_wallet']}: "
        f"realized P/L {trade['profit']:.8f} abstract units"
    )
