import unittest

from src.scenarios.deadlock_demo import simulate_deadlock


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


if __name__ == "__main__":
    unittest.main()
