"""Unit tests for fmb_feature/dh_wait.py — no Mac, no network, no filesystem.

Run either way:

    python3 -m unittest discover -s fmb_feature -p 'test_*.py' -v
    python3 fmb_feature/test_dh_wait.py

Every test injects a fake clock, so the suite never actually sleeps.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dh_wait  # noqa: E402
from dh_wait import (  # noqa: E402
    Deadline,
    WaitResult,
    wait_for,
    wait_for_change,
    wait_stable,
    wait_until,
    wait_until_gone,
)


class FakeClock:
    """Deterministic monotonic clock + sleep recorder."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += max(0.0, seconds)


def fake_now(clock: FakeClock) -> float:
    return clock.t


class WaitUntilTests(unittest.TestCase):
    def test_immediate_success_costs_zero_sleeps(self):
        clock = FakeClock()
        res = wait_until(
            lambda: "hit",
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertFalse(res.timed_out)
        self.assertEqual(res.value, "hit")
        self.assertEqual(res.attempts, 1)
        self.assertEqual(res.elapsed, 0.0)
        self.assertEqual(clock.sleeps, [])
        self.assertIsNone(res.last_error)

    def test_success_after_two_polls_respects_interval(self):
        clock = FakeClock()
        seq = iter([None, None, "hit"])

        def pred():
            return next(seq, "hit")

        res = wait_until(
            pred,
            timeout=5.0,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value, "hit")
        self.assertEqual(res.attempts, 3)
        self.assertAlmostEqual(res.elapsed, 0.2, delta=1e-9)
        self.assertEqual(len(clock.sleeps), 2)
        for slept in clock.sleeps:
            self.assertAlmostEqual(slept, 0.1, delta=1e-9)

    def test_timeout_reports_failure_and_never_oversleeps(self):
        clock = FakeClock()
        res = wait_until(
            lambda: None,
            timeout=0.5,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)
        self.assertTrue(res.timed_out)
        self.assertIsNone(res.value)
        self.assertGreaterEqual(res.attempts, 5)
        self.assertAlmostEqual(res.elapsed, 0.5, delta=0.02)
        self.assertLessEqual(fake_now(clock), 0.5 + 1e-9)

    def test_backoff_grows_then_caps(self):
        clock = FakeClock()
        wait_until(
            lambda: None,
            timeout=5.0,
            interval=0.1,
            backoff=2.0,
            max_interval=0.3,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertGreaterEqual(len(clock.sleeps), 4)
        for got, want in zip(clock.sleeps[:4], [0.1, 0.2, 0.3, 0.3]):
            self.assertAlmostEqual(got, want, delta=1e-9)
        self.assertLessEqual(max(clock.sleeps), 0.3 + 1e-9)

    def test_zero_timeout_makes_exactly_one_attempt(self):
        clock = FakeClock()
        res = wait_until(
            lambda: None,
            timeout=0.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.attempts, 1)
        self.assertEqual(clock.sleeps, [])

    def test_zero_interval_is_clamped_not_busy_looped(self):
        clock = FakeClock()
        wait_until(
            lambda: None,
            timeout=0.05,
            interval=0.0,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(clock.sleeps)
        self.assertGreaterEqual(min(clock.sleeps), dh_wait.MIN_INTERVAL - 1e-12)

    def test_bad_arguments_rejected(self):
        for kwargs in (
            {"timeout": -1},
            {"interval": -1},
            {"max_interval": -1},
            {"backoff": 0.5},
        ):
            with self.assertRaises(ValueError):
                wait_until(lambda: True, **kwargs)

    def test_transient_exception_is_retried(self):
        clock = FakeClock()
        calls = {"n": 0}

        def pred():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("AX not ready")
            return 42

        res = wait_until(
            pred,
            timeout=5.0,
            interval=0.01,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value, 42)
        self.assertEqual(res.attempts, 3)
        self.assertIsNone(res.last_error)

    def test_persistent_exception_is_reported_not_raised(self):
        clock = FakeClock()

        def pred():
            raise RuntimeError("boom")

        res = wait_until(
            pred,
            timeout=0.3,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)
        self.assertIsInstance(res.last_error, RuntimeError)
        self.assertEqual(str(res.last_error), "boom")
        self.assertGreaterEqual(res.attempts, 2)

    def test_errors_filter_lets_other_exceptions_propagate(self):
        clock = FakeClock()

        def pred():
            raise RuntimeError("not caught")

        with self.assertRaises(RuntimeError):
            wait_until(
                pred,
                timeout=0.3,
                interval=0.1,
                errors=(ValueError,),
                clock=clock.monotonic,
                sleep=clock.sleep,
            )


class WaitForTests(unittest.TestCase):
    def test_wait_for_is_node_finder_alias(self):
        clock = FakeClock()
        seq = iter([None, {"title": "Save"}])

        def find():
            return next(seq, {"title": "Save"})

        res = wait_for(
            find,
            timeout=1.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res)
        self.assertEqual(res.value, {"title": "Save"})
        self.assertEqual(res.attempts, 2)

    def test_unwrap_returns_value_on_success(self):
        clock = FakeClock()
        res = wait_until(
            lambda: "node",
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertEqual(res.unwrap(), "node")

    def test_unwrap_raises_timeout_with_details(self):
        clock = FakeClock()
        res = wait_until(
            lambda: None,
            timeout=0.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        with self.assertRaises(TimeoutError) as ctx:
            res.unwrap()
        self.assertIn("attempts=1", str(ctx.exception))


class WaitUntilGoneTests(unittest.TestCase):
    def test_gone_success(self):
        clock = FakeClock()
        seq = iter([{"title": "Spinner"}, None])

        def pred():
            return next(seq, None)

        res = wait_until_gone(
            pred,
            timeout=1.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertIsNone(res.value)
        self.assertEqual(res.attempts, 2)

    def test_gone_timeout_keeps_last_seen(self):
        clock = FakeClock()
        res = wait_until_gone(
            lambda: {"title": "Spinner"},
            timeout=0.2,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.value, {"title": "Spinner"})
        self.assertGreaterEqual(res.attempts, 2)


class WaitForChangeTests(unittest.TestCase):
    def test_change_detected(self):
        clock = FakeClock()
        seq = iter(["A", "A", "B"])

        def snap():
            return next(seq, "B")

        res = wait_for_change(
            snap,
            "A",
            timeout=1.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value, "B")
        self.assertEqual(res.attempts, 3)

    def test_unchanged_times_out(self):
        clock = FakeClock()
        res = wait_for_change(
            lambda: "A",
            "A",
            timeout=0.2,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.value, "A")

    def test_key_ignores_volatile_fields(self):
        clock = FakeClock()
        seq = iter([
            {"pane": "General", "ts": 1},
            {"pane": "Privacy", "ts": 2},
        ])

        def snap():
            return next(seq, {"pane": "Privacy", "ts": 2})

        res = wait_for_change(
            snap,
            {"pane": "General", "ts": 0},
            key=lambda d: d["pane"],
            timeout=1.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value["pane"], "Privacy")
        self.assertEqual(res.attempts, 2)


class WaitStableTests(unittest.TestCase):
    def test_requires_settle_consecutive_reads(self):
        clock = FakeClock()
        seq = iter([1, 1, 2, 2, 2])

        def snap():
            return next(seq, 2)

        res = wait_stable(
            snap,
            settle=3,
            timeout=5.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value, 2)
        self.assertEqual(res.attempts, 5)

    def test_settle_one_accepts_first_read(self):
        clock = FakeClock()
        res = wait_stable(
            lambda: 7,
            settle=1,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value, 7)
        self.assertEqual(res.attempts, 1)
        self.assertEqual(clock.sleeps, [])

    def test_flapping_value_times_out(self):
        clock = FakeClock()
        values = iter([1, 2, 1, 2, 1, 2, 1, 2])

        def snap():
            return next(values, 1)

        res = wait_stable(
            snap,
            settle=2,
            timeout=0.5,
            interval=0.1,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertFalse(res.ok)

    def test_key_on_dict_snapshot(self):
        clock = FakeClock()
        seq = iter([
            {"title": "Save", "ts": 1},
            {"title": "Save", "ts": 2},
        ])

        def snap():
            return next(seq, {"title": "Save", "ts": 3})

        res = wait_stable(
            snap,
            settle=2,
            key=lambda d: d["title"],
            timeout=1.0,
            interval=0.05,
            backoff=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.value["ts"], 2)
        self.assertEqual(res.attempts, 2)

    def test_bad_settle_rejected(self):
        with self.assertRaises(ValueError):
            wait_stable(lambda: 1, settle=0)


class DeadlineTests(unittest.TestCase):
    def test_remaining_clamp_and_expiry(self):
        clock = FakeClock()
        deadline = Deadline(1.0, clock=clock.monotonic)
        self.assertAlmostEqual(deadline.remaining(), 1.0, delta=1e-9)
        self.assertFalse(deadline.expired())

        clock.sleep(0.4)
        self.assertAlmostEqual(deadline.remaining(), 0.6, delta=1e-9)
        self.assertAlmostEqual(deadline.clamp(2.0), 0.6, delta=1e-9)
        self.assertAlmostEqual(deadline.clamp(0.2), 0.2, delta=1e-9)

        clock.sleep(0.7)
        self.assertTrue(deadline.expired())
        self.assertEqual(deadline.remaining(), 0.0)
        self.assertEqual(deadline.clamp(0.2), 0.0)

    def test_negative_timeout_rejected(self):
        with self.assertRaises(ValueError):
            Deadline(-1.0)


class RealClockSmokeTest(unittest.TestCase):
    """Exercises the default time.monotonic / time.sleep path once."""

    def test_succeeds_on_third_call_with_real_clock(self):
        calls = {"n": 0}

        def pred():
            calls["n"] += 1
            if calls["n"] < 3:
                return None
            return "ok"

        res = wait_until(pred, timeout=2.0, interval=0.01, backoff=1.0)
        self.assertTrue(res.ok)
        self.assertEqual(res.value, "ok")
        self.assertEqual(res.attempts, 3)
        self.assertGreater(res.elapsed, 0.0)
        self.assertIsInstance(res, WaitResult)


if __name__ == "__main__":
    unittest.main(verbosity=2)
