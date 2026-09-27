import unittest

from src.scenarios.deadlock_demo import (
    simulate_deadlock,
    simulate_deadlock_prevention,
)


class DeadlockSimulationTests(unittest.TestCase):
    def test_detects_circular_wait_between_two_orders(self) -> None:
        report = simulate_deadlock(timeout=0.05)

        self.assertTrue(report.detected)
        self.assertTrue(report.mutual_exclusion)
        self.assertTrue(report.hold_and_wait)
        self.assertTrue(report.no_preemption)
        self.assertTrue(report.circular_wait)
        self.assertEqual(len(report.blocked_threads), 2)
        self.assertEqual(
            {
                (state.holds, state.waits_for)
                for state in report.blocked_threads
            },
            {
                ("inventory_lock", "invoice_lock"),
                ("invoice_lock", "inventory_lock"),
            },
        )

    def test_requires_a_positive_detection_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            simulate_deadlock(timeout=0)

    def test_global_lock_order_prevents_circular_wait(self) -> None:
        report = simulate_deadlock_prevention(timeout=0.10)

        self.assertTrue(report.prevented)
        self.assertEqual(report.strategy, "global_lock_order")
        self.assertEqual(
            report.acquisition_order,
            ("inventory_lock", "invoice_lock"),
        )
        self.assertEqual(report.completed_orders, ("ORDER-A", "ORDER-B"))
        self.assertFalse(report.deadlock_detected)
        self.assertFalse(report.circular_wait)

    def test_prevention_requires_a_positive_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            simulate_deadlock_prevention(timeout=0)


if __name__ == "__main__":
    unittest.main()
