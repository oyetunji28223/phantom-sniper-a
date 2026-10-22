"""Create TikTok caption drafts for paper reports; this module never posts."""

from typing import Any


def format_paper_post_drafts(report: dict[str, Any]) -> list[str]:
    if not report["trades"]:
        return ["Paper-trading simulation: no eligible tokens in this run. No live trades."]
    return [
        (
            f"Paper-trading simulation for {trade['symbol']}: "
            f"{trade['profit']:+.8f} abstract units. "
            "Synthetic simulation only; no live trade executed. #PaperTrading"
        )
        for trade in report["trades"]
    ]
