"""Apply the configured virtual reserve split to realized paper-trade profits."""


def split_profit(
    profit: float, reserve_fraction: float
) -> tuple[float, float]:
    if profit <= 0:
        return 0.0, 0.0
    reserve = profit * reserve_fraction
    return profit - reserve, reserve
