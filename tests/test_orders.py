import unittest

from src.orders import Order, OrderStatus


class OrderTests(unittest.TestCase):
    def test_new_order_is_pending(self) -> None:
        order = Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 2)

        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_order_requires_a_positive_quantity(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 0)


if __name__ == "__main__":
    unittest.main()

