import unittest

from src.workers import WorkerPool


class WorkerPoolTests(unittest.TestCase):
    def test_requires_at_least_one_worker(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            WorkerPool(0)

    def test_rejects_negative_processing_delay(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            WorkerPool(1, processing_delay=-1)


if __name__ == "__main__":
    unittest.main()
