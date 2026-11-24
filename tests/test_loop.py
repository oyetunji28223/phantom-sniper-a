import tempfile
import unittest
from pathlib import Path

from run_loop import LoopLock, run_loop

ROOT = Path(__file__).resolve().parents[1]
MARKET_DATA = ROOT / "market_data.example.json"
CONFIG = ROOT / "paper_config.json"


def no_sleep(seconds):
    assert seconds >= 0


def no_log(message):
    pass


class LoopTests(unittest.TestCase):
    def test_runs_bounded_cadence_and_accumulates(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "runs"
            summary = run_loop(
                market_data_path=MARKET_DATA,
                config_path=CONFIG,
                output_dir=output_dir,
                interval=1,
                runs=3,
                sleep=no_sleep,
                log=no_log,
            )

            self.assertEqual(summary["iterations"], 3)
            self.assertGreater(summary["cumulative_profit"], 0)
            self.assertEqual(len(list(output_dir.glob("paper-report-*.json"))), 3)
            self.assertIn("loop started", (output_dir / "loop.log").read_text(encoding="utf-8"))
            self.assertFalse((output_dir / ".loop.lock").exists())

    def test_stops_when_target_reached(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "runs"
            summary = run_loop(
                market_data_path=MARKET_DATA,
                config_path=CONFIG,
                output_dir=output_dir,
                interval=1,
                runs=0,
                target_units=0.001,
                sleep=no_sleep,
                log=no_log,
            )

            self.assertEqual(summary["iterations"], 1)
            self.assertTrue(summary["target_reached"])
            self.assertGreaterEqual(summary["cumulative_profit"], 0.001)

    def test_lock_prevents_overlapping_loops_and_force_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "runs"
            output_dir.mkdir(parents=True)
            lock = LoopLock(output_dir / ".loop.lock")
            lock.acquire()
            try:
                with self.assertRaisesRegex(RuntimeError, "another loop"):
                    run_loop(
                        market_data_path=MARKET_DATA,
                        config_path=CONFIG,
                        output_dir=output_dir,
                        interval=1,
                        runs=1,
                        sleep=no_sleep,
                        log=no_log,
                    )
            finally:
                lock.release()

            summary = run_loop(
                market_data_path=MARKET_DATA,
                config_path=CONFIG,
                output_dir=output_dir,
                interval=1,
                runs=1,
                force=True,
                sleep=no_sleep,
                log=no_log,
            )
            self.assertEqual(summary["iterations"], 1)

    def test_rejects_invalid_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "interval"):
                run_loop(
                    market_data_path=MARKET_DATA,
                    config_path=CONFIG,
                    output_dir=Path(directory) / "runs",
                    interval=0,
                    runs=1,
                    sleep=no_sleep,
                    log=no_log,
                )


if __name__ == "__main__":
    unittest.main()
