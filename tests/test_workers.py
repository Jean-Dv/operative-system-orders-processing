import unittest

from src.workers import WorkerPool


class WorkerPoolTests(unittest.TestCase):
    def test_requires_at_least_one_worker(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            WorkerPool(0)

    def test_rejects_negative_processing_delay(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            WorkerPool(1, processing_delay=-1)

    def test_requires_at_least_one_thread_per_worker(self) -> None:
        with self.assertRaisesRegex(ValueError, "threads_per_worker"):
            WorkerPool(1, threads_per_worker=0)

    def test_rejects_negative_race_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "race_window"):
            WorkerPool(1, race_window=-1)

    def test_requires_a_positive_queue_capacity(self) -> None:
        with self.assertRaisesRegex(ValueError, "queue_capacity"):
            WorkerPool(1, queue_capacity=0)

    def test_requires_positive_initial_stock(self) -> None:
        with self.assertRaisesRegex(ValueError, "initial_stock"):
            WorkerPool(1, initial_stock=0)


if __name__ == "__main__":
    unittest.main()
