import unittest

from src.orders import Order, OrderStatus
from src.processing import Inventory, OrderProcessor, ProcessingStage, Product


class OrderProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory((Product("PRODUCT-001", 2_500, 5),))
        self.processor = OrderProcessor(self.inventory, total_processing_delay=0)

    def test_order_crosses_all_stages_and_produces_artifacts(self) -> None:
        events = []
        order = Order("ORD-0001", "CUSTOMER-001", "PRODUCT-001", 2)

        result = self.processor.process(order, on_event=events.append)

        self.assertEqual(result.status, OrderStatus.READY_FOR_DISPATCH)
        self.assertEqual(self.inventory.stock_for("PRODUCT-001"), 3)
        self.assertIsNotNone(result.inventory_update)
        self.assertEqual(result.inventory_update.previous_stock, 5)
        self.assertEqual(result.inventory_update.current_stock, 3)
        self.assertIsNotNone(result.invoice)
        self.assertEqual(result.invoice.invoice_id, "INV-ORD-0001")
        self.assertEqual(result.invoice.total_cents, 5_000)
        self.assertIsNotNone(result.dispatch)
        self.assertEqual(result.dispatch.dispatch_id, "DSP-ORD-0001")
        self.assertEqual(
            [event.stage for event in events if event.outcome == "completed"],
            list(ProcessingStage),
        )

    def test_unknown_product_is_rejected_without_changing_inventory(self) -> None:
        order = Order("ORD-0001", "CUSTOMER-001", "UNKNOWN", 1)

        result = self.processor.process(order)

        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("unknown product", result.failure_reason)
        self.assertEqual(self.inventory.stock_for("PRODUCT-001"), 5)

    def test_insufficient_stock_prevents_invoice_and_dispatch(self) -> None:
        order = Order("ORD-0001", "CUSTOMER-001", "PRODUCT-001", 6)

        result = self.processor.process(order)

        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("insufficient stock", result.failure_reason)
        self.assertIsNone(result.invoice)
        self.assertIsNone(result.dispatch)
        self.assertEqual(self.inventory.stock_for("PRODUCT-001"), 5)


if __name__ == "__main__":
    unittest.main()
