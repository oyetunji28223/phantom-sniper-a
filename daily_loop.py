"""Run one scheduled paper simulation and save a local report and message drafts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sniper_ai import SimulationConfig, load_json, simulate
from tiktok_poster import format_paper_post_drafts


def _write_atomic(path: Path, contents: str) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(contents, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def run_once(
    market_data_path: Path,
    config_path: Path,
    output_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Path]:
    config = SimulationConfig.from_dict(load_json(config_path))
    market_data = load_json(market_data_path)
    report = simulate(market_data, config)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")
    report["generated_at_utc"] = timestamp

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": output_dir / f"paper-report-{timestamp}.json",
        "telegram_draft": output_dir / f"telegram-draft-{timestamp}.txt",
        "tiktok_drafts": output_dir / f"tiktok-drafts-{timestamp}.txt",
    }
    report_text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    telegram_text = "\n".join(report["alerts"]) + ("\n" if report["alerts"] else "")
    tiktok_text = "\n".join(format_paper_post_drafts(report)) + "\n"

    for key, contents in (
        ("report", report_text),
        ("telegram_draft", telegram_text),
        ("tiktok_drafts", tiktok_text),
    ):
        _write_atomic(paths[key], contents)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one scheduled paper simulation and write local report and "
            "message drafts. No real trades or messages are sent."
        )
    )
    parser.add_argument(
        "market_data",
        nargs="?",
        type=Path,
        default=Path("market_data.example.json"),
    )
    parser.add_argument("--config", type=Path, default=Path("paper_config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("paper_runs"))
    args = parser.parse_args(argv)

    try:
        paths = run_once(args.market_data, args.config, args.output_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
