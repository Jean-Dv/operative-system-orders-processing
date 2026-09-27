import unittest

from src.load_test import run_load


class LoadTestValidationTests(unittest.TestCase):
    def test_requires_positive_order_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "orders"):
            run_load(host="127.0.0.1", port=5000, orders=0, concurrency=1)

    def test_requires_positive_concurrency(self) -> None:
        with self.assertRaisesRegex(ValueError, "concurrency"):
            run_load(host="127.0.0.1", port=5000, orders=1, concurrency=0)

    def test_rejects_unknown_product_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "product_mode"):
            run_load(
                host="127.0.0.1",
                port=5000,
                orders=1,
                concurrency=1,
                product_mode="unknown",
            )


if __name__ == "__main__":
    unittest.main()
