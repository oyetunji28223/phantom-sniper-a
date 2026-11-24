"""Run the paper-trading simulator on a recurring cadence.

This is a scheduling wrapper around daily_loop.run_once. It is paper-only:
it never connects to a blockchain, signs transactions, uses credentials,
calls a network API, or posts messages. Any target is expressed in abstract
simulation units, not USD, and reaching it does not represent real profit.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from daily_loop import run_once


class LoopLock:
    """Prevent two loop processes from writing to the same run directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._acquired = False

    def acquire(self, *, force: bool = False) -> None:
        if force:
            self.path.unlink(missing_ok=True)
        try:
            descriptor = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            raise RuntimeError(
                f"another loop appears to be running (lock: {self.path}). "
                "Use --force only if you know it is stale."
            ) from error
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
        finally:
            os.close(descriptor)
        self._acquired = True

    def release(self) -> None:
        if self._acquired:
            self.path.unlink(missing_ok=True)
            self._acquired = False


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_loop(
    *,
    market_data_path: Path,
    config_path: Path,
    output_dir: Path,
    interval: float,
    runs: int = 0,
    target_units: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, object]:
    """Run scheduled paper simulations until runs/target/stop signal.

    ``runs=0`` means run until interrupted or the target is reached.
    ``sleep`` is injectable so tests never wait in real time.
    """
    if interval <= 0:
        raise ValueError("interval must be positive")
    if runs < 0:
        raise ValueError("runs must be zero or positive")
    if target_units is not None and target_units <= 0:
        raise ValueError("target_units must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "loop.log"
    lock = LoopLock(output_dir / ".loop.lock")
    lock.acquire(force=force)

    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_handler = None
    if hasattr(signal, "SIGTERM"):
        previous_handler = signal.signal(signal.SIGTERM, request_stop)

    iterations = 0
    cumulative_profit = 0.0
    target_reached = False

    def emit(message: str) -> None:
        line = f"[{_timestamp()}] {message}"
        log(line)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    try:
        emit(
            "loop started (paper-only): "
            f"interval={interval}s runs={runs or 'unlimited'} "
            f"target={target_units if target_units is not None else 'none'} abstract units"
        )
        while not stop_requested:
            iterations += 1
            paths = run_once(market_data_path, config_path, output_dir)
            report = json.loads(paths["report"].read_text(encoding="utf-8"))
            profit = float(report.get("total_profit", 0.0))
            cumulative_profit += profit
            emit(
                f"run {iterations}: profit={profit:.6f} cumulative={cumulative_profit:.6f} "
                f"report={paths['report'].name}"
            )

            if target_units is not None and cumulative_profit >= target_units:
                target_reached = True
                emit(
                    f"target reached: {cumulative_profit:.6f} >= {target_units:.6f} "
                    "abstract units (not USD)"
                )
                break
            if runs and iterations >= runs:
                emit(f"completed {iterations} scheduled run(s)")
                break
            if stop_requested:
                break
            sleep(interval)

        if stop_requested and not target_reached:
            emit("stop requested; loop ended")
    except KeyboardInterrupt:
        emit("interrupted by user; loop ended")
    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGTERM, previous_handler)
        lock.release()

    return {
        "iterations": iterations,
        "cumulative_profit": cumulative_profit,
        "target_units": target_units,
        "target_reached": target_reached,
        "log_path": log_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run paper simulations on a cadence. Paper-only: no live trades, "
            "credentials, network calls, or posts."
        )
    )
    parser.add_argument("--market-data", type=Path, default=Path("market_data.example.json"))
    parser.add_argument("--config", type=Path, default=Path("paper_config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("paper_runs"))
    parser.add_argument(
        "--interval", type=float, default=3600.0,
        help="seconds between runs (default: 3600)",
    )
    parser.add_argument(
        "--runs", type=int, default=0,
        help="number of runs before stopping; 0 means unlimited (default: 0)",
    )
    parser.add_argument(
        "--target-units", type=float, default=None,
        help="optional stop target in abstract simulation units, not USD",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="remove an existing lock file before starting (only if stale)",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_loop(
            market_data_path=args.market_data,
            config_path=args.config,
            output_dir=args.output_dir,
            interval=args.interval,
            runs=args.runs,
            target_units=args.target_units,
            force=args.force,
        )
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(
        f"summary: iterations={summary['iterations']} "
        f"cumulative_profit={summary['cumulative_profit']:.6f} abstract units "
        f"log={summary['log_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
