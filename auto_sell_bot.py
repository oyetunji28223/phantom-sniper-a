"""Execute configured staged exits against an observed synthetic price path."""

from __future__ import annotations

from dataclasses import dataclass

from predictor_agent import Candidate


@dataclass(frozen=True)
class SellFill:
    price: float
    units_sold: float
    net_proceeds: float
    reason: str


def execute_exits(
    candidate: Candidate,
    *,
    entry_price: float,
    initial_units: float,
    fee_rate: float,
    stop_loss_fraction: float,
    take_profit_waves: list[dict[str, float]],
) -> list[SellFill]:
    remaining_units = initial_units
    fills: list[SellFill] = []
    next_wave = 0

    def sell(units: float, price: float, reason: str) -> None:
        nonlocal remaining_units
        sold_units = min(units, remaining_units)
        if sold_units <= 0:
            return
        fills.append(
            SellFill(
                price=price,
                units_sold=sold_units,
                net_proceeds=sold_units * price * (1.0 - fee_rate),
                reason=reason,
            )
        )
        remaining_units -= sold_units

    for price in candidate.price_path[1:]:
        if price <= entry_price * (1.0 - stop_loss_fraction):
            sell(remaining_units, price, "stop_loss")
            break
        while (
            next_wave < len(take_profit_waves)
            and price
            >= entry_price * (1.0 + take_profit_waves[next_wave]["gain_fraction"])
        ):
            wave = take_profit_waves[next_wave]
            sell(initial_units * wave["position_fraction"], price, "take_profit")
            next_wave += 1
            if remaining_units <= 0:
                break
        if remaining_units <= 0:
            break

    if remaining_units > 0:
        sell(remaining_units, candidate.price_path[-1], "final_price")
    return fills
