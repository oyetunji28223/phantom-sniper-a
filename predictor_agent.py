"""Deterministic, rule-based screening for synthetic paper-trading inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candidate:
    mint: str
    symbol: str
    liquidity_units: float
    volume_units: float
    price_path: tuple[float, ...]

    @property
    def volume_liquidity_ratio(self) -> float:
        return self.volume_units / self.liquidity_units


def _finite_number(value: Any, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not allow_zero and number == 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{field} must be finite and {qualifier}")
    return number


def parse_candidate(raw: Any) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError("each market-data item must be an object")

    mint = raw.get("mint")
    symbol = raw.get("symbol")
    if not isinstance(mint, str) or not mint.strip():
        raise ValueError("mint must be a nonempty string")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError(f"{mint}: symbol must be a nonempty string")

    liquidity = _finite_number(raw.get("liquidity_units"), f"{mint}: liquidity_units")
    volume = _finite_number(
        raw.get("volume_units"), f"{mint}: volume_units", allow_zero=True
    )
    raw_path = raw.get("price_path")
    if not isinstance(raw_path, list) or not raw_path:
        raise ValueError(f"{mint}: price_path must be a nonempty array")
    price_path = tuple(
        _finite_number(price, f"{mint}: price_path[{index}]")
        for index, price in enumerate(raw_path)
    )

    return Candidate(
        mint=mint.strip(),
        symbol=symbol.strip(),
        liquidity_units=liquidity,
        volume_units=volume,
        price_path=price_path,
    )


def rank_candidates(
    raw_candidates: Any,
    *,
    minimum_liquidity_units: float,
    minimum_volume_liquidity_ratio: float,
    maximum_candidates: int,
) -> list[Candidate]:
    if not isinstance(raw_candidates, list):
        raise ValueError("market data must be a JSON array")

    candidates = [parse_candidate(raw) for raw in raw_candidates]
    seen_mints: set[str] = set()
    for candidate in candidates:
        if candidate.mint in seen_mints:
            raise ValueError(f"duplicate mint: {candidate.mint}")
        seen_mints.add(candidate.mint)

    eligible = (
        candidate
        for candidate in candidates
        if candidate.liquidity_units >= minimum_liquidity_units
        and candidate.volume_liquidity_ratio >= minimum_volume_liquidity_ratio
    )
    return sorted(
        eligible,
        key=lambda candidate: (-candidate.volume_liquidity_ratio, candidate.mint),
    )[:maximum_candidates]
