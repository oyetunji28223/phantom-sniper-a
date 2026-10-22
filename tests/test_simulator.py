import json
import tempfile
import unittest
from pathlib import Path

from auto_sell_bot import execute_exits
from phantom_wallet_rotator import PaperWalletRotator
from predictor_agent import Candidate, rank_candidates
from reinvest_bot import split_profit
from sniper_ai import SimulationConfig, main, simulate
from daily_loop import run_once
from tiktok_poster import format_paper_post_drafts


def example_config():
    return {
        "starting_capital": 1.0,
        "allocation_fraction": 0.5,
        "fee_bps": 0,
        "minimum_liquidity_units": 100,
        "minimum_volume_liquidity_ratio": 0.05,
        "maximum_candidates": 5,
        "stop_loss_fraction": 0.1,
        "profit_reserve_fraction": 0.1,
        "virtual_wallets": ["paper-a", "paper-b"],
        "take_profit_waves": [
            {"gain_fraction": 0.1, "position_fraction": 0.25},
            {"gain_fraction": 0.2, "position_fraction": 0.25},
        ],
    }


def candidate(path):
    return Candidate(
        mint="synthetic-mint",
        symbol="TEST",
        liquidity_units=1000,
        volume_units=100,
        price_path=tuple(path),
    )


class CandidateTests(unittest.TestCase):
    def test_filters_by_liquidity_and_ranks_by_turnover(self):
        data = [
            {
                "mint": "lower",
                "symbol": "LOW",
                "liquidity_units": 100,
                "volume_units": 10,
                "price_path": [1],
            },
            {
                "mint": "higher",
                "symbol": "HIGH",
                "liquidity_units": 100,
                "volume_units": 25,
                "price_path": [2],
            },
            {
                "mint": "illiquid",
                "symbol": "NO",
                "liquidity_units": 99,
                "volume_units": 100,
                "price_path": [1],
            },
        ]

        selected = rank_candidates(
            data,
            minimum_liquidity_units=100,
            minimum_volume_liquidity_ratio=0.05,
            maximum_candidates=1,
        )

        self.assertEqual([item.mint for item in selected], ["higher"])

    def test_rejects_duplicate_mints_and_invalid_prices(self):
        item = {
            "mint": "duplicate",
            "symbol": "DUP",
            "liquidity_units": 1,
            "volume_units": 1,
            "price_path": [1],
        }
        with self.assertRaisesRegex(ValueError, "duplicate mint"):
            rank_candidates(
                [item, item],
                minimum_liquidity_units=0,
                minimum_volume_liquidity_ratio=0,
                maximum_candidates=5,
            )
        item["price_path"] = [0]
        with self.assertRaisesRegex(ValueError, "price_path"):
            rank_candidates(
                [item],
                minimum_liquidity_units=0,
                minimum_volume_liquidity_ratio=0,
                maximum_candidates=5,
            )


class ExitTests(unittest.TestCase):
    def test_executes_staged_sales_and_closes_remainder(self):
        fills = execute_exits(
            candidate([1.0, 1.11, 1.21]),
            entry_price=1.0,
            initial_units=10,
            fee_rate=0,
            stop_loss_fraction=0.1,
            take_profit_waves=[
                {"gain_fraction": 0.1, "position_fraction": 0.25},
                {"gain_fraction": 0.2, "position_fraction": 0.25},
            ],
        )

        self.assertEqual([fill.reason for fill in fills], ["take_profit"] * 2 + ["final_price"])
        self.assertAlmostEqual(sum(fill.units_sold for fill in fills), 10)
        self.assertAlmostEqual(sum(fill.net_proceeds for fill in fills), 11.85)

    def test_stop_loss_sells_remaining_position(self):
        fills = execute_exits(
            candidate([1.0, 0.89, 1.2]),
            entry_price=1.0,
            initial_units=4,
            fee_rate=0,
            stop_loss_fraction=0.1,
            take_profit_waves=[
                {"gain_fraction": 0.1, "position_fraction": 0.5}
            ],
        )

        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].reason, "stop_loss")
        self.assertEqual(fills[0].units_sold, 4)


class SimulatorTests(unittest.TestCase):
    def test_config_rejects_invalid_wave_allocations(self):
        config = example_config()
        config["take_profit_waves"][1]["position_fraction"] = 0.9
        with self.assertRaisesRegex(ValueError, "total at most 1"):
            SimulationConfig.from_dict(config)

    def test_simulates_profit_reserve_and_wallet_rotation(self):
        config = example_config()
        market_data = [
            {
                "mint": "first",
                "symbol": "ONE",
                "liquidity_units": 1000,
                "volume_units": 200,
                "price_path": [1.0, 1.3],
            },
            {
                "mint": "second",
                "symbol": "TWO",
                "liquidity_units": 1000,
                "volume_units": 100,
                "price_path": [1.0, 1.0],
            },
        ]

        report = simulate(market_data, SimulationConfig.from_dict(config))

        self.assertEqual(report["mode"], "paper")
        self.assertEqual([trade["virtual_wallet"] for trade in report["trades"]], ["paper-a", "paper-b"])
        self.assertAlmostEqual(report["total_profit"], 0.15)
        self.assertAlmostEqual(report["reserve_balance"], 0.015)
        self.assertAlmostEqual(
            report["available_capital"] + report["reserve_balance"],
            report["starting_capital"] + report["total_profit"],
        )
        self.assertTrue(all("[PAPER ONLY]" in alert for alert in report["alerts"]))

    def test_wallets_rotate_round_robin(self):
        rotator = PaperWalletRotator(["one", "two"])
        self.assertEqual(
            [rotator.next_wallet() for _ in range(3)],
            ["one", "two", "one"],
        )

    def test_reserve_split_does_not_replenish_losses(self):
        self.assertEqual(split_profit(-2, 0.1), (0.0, 0.0))
        self.assertEqual(split_profit(10, 0.1), (9.0, 1.0))

    def test_cli_writes_json_output(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            result = main(
                [
                    str(root / "market_data.example.json"),
                    "--config",
                    str(root / "paper_config.json"),
                    "--output",
                    str(report_path),
                ]
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(report["mode"], "paper")
        self.assertEqual(report["screened_candidates"], 2)

    def test_social_post_generator_only_creates_disclosed_drafts(self):
        report = {
            "trades": [
                {"symbol": "TEST", "profit": 0.25},
            ]
        }

        drafts = format_paper_post_drafts(report)

        self.assertEqual(len(drafts), 1)
        self.assertIn("Paper-trading simulation", drafts[0])
        self.assertIn("abstract units", drafts[0])
        self.assertIn("no live trade executed", drafts[0])
        self.assertNotIn("synthetic-mint", drafts[0])

    def test_scheduled_run_writes_report_and_local_message_drafts(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "runs"
            paths = run_once(
                root / "market_data.example.json",
                root / "paper_config.json",
                output_dir,
            )

            self.assertTrue(all(path.is_file() for path in paths.values()))
            report = json.loads(paths["report"].read_text(encoding="utf-8"))
            telegram_draft = paths["telegram_draft"].read_text(encoding="utf-8")
            tiktok_drafts = paths["tiktok_drafts"].read_text(encoding="utf-8")

        self.assertEqual(report["mode"], "paper")
        self.assertTrue(report["generated_at_utc"].endswith("Z"))
        self.assertIn("[PAPER ONLY]", telegram_draft)
        self.assertIn("no live trade executed", tiktok_drafts)


if __name__ == "__main__":
    unittest.main()
