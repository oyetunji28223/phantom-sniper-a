"""Run one local paper-trading simulation from caller-supplied JSON snapshots."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auto_sell_bot import execute_exits
from phantom_wallet_rotator import PaperWalletRotator
from predictor_agent import Candidate, rank_candidates
from reinvest_bot import split_profit
from telegram_notifier import format_simulation_alert


@dataclass(frozen=True)
class SimulationConfig:
    starting_capital: float
    allocation_fraction: float
    fee_bps: float
    minimum_liquidity_units: float
    minimum_volume_liquidity_ratio: float
    maximum_candidates: int
    stop_loss_fraction: float
    profit_reserve_fraction: float
    virtual_wallets: list[str]
    take_profit_waves: list[dict[str, float]]

    @classmethod
    def from_dict(cls, raw: Any) -> SimulationConfig:
        if not isinstance(raw, dict):
            raise ValueError("configuration must be a JSON object")
        required = {
            "starting_capital",
            "allocation_fraction",
            "fee_bps",
            "minimum_liquidity_units",
            "minimum_volume_liquidity_ratio",
            "maximum_candidates",
            "stop_loss_fraction",
            "profit_reserve_fraction",
            "virtual_wallets",
            "take_profit_waves",
        }
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"configuration missing: {', '.join(sorted(missing))}")

        starting_capital = _number(raw["starting_capital"], "starting_capital")
        allocation = _number(raw["allocation_fraction"], "allocation_fraction")
        fee_bps = _number(raw["fee_bps"], "fee_bps", zero=True)
        minimum_liquidity = _number(
            raw["minimum_liquidity_units"], "minimum_liquidity_units", zero=True
        )
        minimum_ratio = _number(
            raw["minimum_volume_liquidity_ratio"],
            "minimum_volume_liquidity_ratio",
            zero=True,
        )
        reserve_fraction = _number(
            raw["profit_reserve_fraction"], "profit_reserve_fraction", zero=True
        )
        stop_loss = _number(raw["stop_loss_fraction"], "stop_loss_fraction")

        maximum_candidates = raw["maximum_candidates"]
        if (
            isinstance(maximum_candidates, bool)
            or not isinstance(maximum_candidates, int)
            or maximum_candidates < 1
        ):
            raise ValueError("maximum_candidates must be a positive integer")
        if allocation > 1:
            raise ValueError("allocation_fraction must be at most 1")
        if fee_bps >= 10_000:
            raise ValueError("fee_bps must be less than 10000")
        if stop_loss >= 1:
            raise ValueError("stop_loss_fraction must be less than 1")
        if reserve_fraction > 1:
            raise ValueError("profit_reserve_fraction must be at most 1")

        wallets = raw["virtual_wallets"]
        if not isinstance(wallets, list) or any(
            not isinstance(wallet, str) or not wallet.strip() for wallet in wallets
        ):
            raise ValueError("virtual_wallets must be an array of nonempty strings")
        if len(set(wallets)) != len(wallets):
            raise ValueError("virtual_wallets must contain unique names")
        if not wallets:
            raise ValueError("virtual_wallets must contain at least one name")

        raw_waves = raw["take_profit_waves"]
        if not isinstance(raw_waves, list):
            raise ValueError("take_profit_waves must be an array")
        waves: list[dict[str, float]] = []
        total_position_fraction = 0.0
        previous_gain = 0.0
        for index, raw_wave in enumerate(raw_waves):
            if not isinstance(raw_wave, dict):
                raise ValueError(f"take_profit_waves[{index}] must be an object")
            if "gain_fraction" not in raw_wave or "position_fraction" not in raw_wave:
                raise ValueError(
                    f"take_profit_waves[{index}] requires gain_fraction and "
                    "position_fraction"
                )
            gain = _number(
                raw_wave["gain_fraction"],
                f"take_profit_waves[{index}].gain_fraction",
            )
            position = _number(
                raw_wave["position_fraction"],
                f"take_profit_waves[{index}].position_fraction",
            )
            if position > 1 or gain <= previous_gain:
                raise ValueError(
                    "take-profit gains must be strictly increasing and position "
                    "fractions must be at most 1"
                )
            waves.append({"gain_fraction": gain, "position_fraction": position})
            previous_gain = gain
            total_position_fraction += position
        if total_position_fraction > 1:
            raise ValueError("take-profit position fractions must total at most 1")

        return cls(
            starting_capital=starting_capital,
            allocation_fraction=allocation,
            fee_bps=fee_bps,
            minimum_liquidity_units=minimum_liquidity,
            minimum_volume_liquidity_ratio=minimum_ratio,
            maximum_candidates=maximum_candidates,
            stop_loss_fraction=stop_loss,
            profit_reserve_fraction=reserve_fraction,
            virtual_wallets=wallets,
            take_profit_waves=waves,
        )


def _number(value: Any, field: str, *, zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (not zero and result == 0):
        qualifier = "nonnegative" if zero else "positive"
        raise ValueError(f"{field} must be finite and {qualifier}")
    return result


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as input_file:
        return json.load(input_file)


def simulate(
    raw_market_data: Any, config: SimulationConfig
) -> dict[str, Any]:
    candidates = rank_candidates(
        raw_market_data,
        minimum_liquidity_units=config.minimum_liquidity_units,
        minimum_volume_liquidity_ratio=config.minimum_volume_liquidity_ratio,
        maximum_candidates=config.maximum_candidates,
    )
    rotator = PaperWalletRotator(config.virtual_wallets)
    available = config.starting_capital
    reserve_balance = 0.0
    total_profit = 0.0
    trades: list[dict[str, Any]] = []
    fee_rate = config.fee_bps / 10_000.0

    for candidate in candidates:
        budget = available * config.allocation_fraction
        if budget <= 0:
            break
        available -= budget
        entry_price = candidate.price_path[0]
        initial_units = budget * (1.0 - fee_rate) / entry_price
        fills = execute_exits(
            candidate,
            entry_price=entry_price,
            initial_units=initial_units,
            fee_rate=fee_rate,
            stop_loss_fraction=config.stop_loss_fraction,
            take_profit_waves=config.take_profit_waves,
        )
        proceeds = sum(fill.net_proceeds for fill in fills)
        profit = proceeds - budget
        available += proceeds
        reinvested, reserved = split_profit(profit, config.profit_reserve_fraction)
        available -= reserved
        reserve_balance += reserved
        total_profit += profit
        trade = {
            "mint": candidate.mint,
            "symbol": candidate.symbol,
            "score": candidate.volume_liquidity_ratio,
            "virtual_wallet": rotator.next_wallet(),
            "budget": budget,
            "entry_price": entry_price,
            "units_bought": initial_units,
            "fills": [
                {
                    "price": fill.price,
                    "units_sold": fill.units_sold,
                    "net_proceeds": fill.net_proceeds,
                    "reason": fill.reason,
                }
                for fill in fills
            ],
            "proceeds": proceeds,
            "profit": profit,
            "reinvested_profit": reinvested,
            "reserved_profit": reserved,
        }
        trades.append(trade)

    return {
        "mode": "paper",
        "unit": "abstract",
        "screened_candidates": len(candidates),
        "trades": trades,
        "starting_capital": config.starting_capital,
        "available_capital": available,
        "reserve_balance": reserve_balance,
        "total_profit": total_profit,
        "alerts": [format_simulation_alert(trade) for trade in trades],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a local paper-trading simulation. No real trades are made."
    )
    parser.add_argument(
        "market_data",
        nargs="?",
        type=Path,
        default=Path("market_data.example.json"),
        help="JSON array of synthetic or user-supplied snapshots",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("paper_config.json"),
        help="simulator settings JSON (default: paper_config.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the JSON report to this file instead of standard output",
    )
    args = parser.parse_args(argv)

    try:
        config = SimulationConfig.from_dict(load_json(args.config))
        report = simulate(load_json(args.market_data), config)
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
