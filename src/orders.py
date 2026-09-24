"""Domain objects for the order-processing simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrderStatus(StrEnum):
    """Stages an order will cross during later phases."""

    PENDING = "pending"
    VALIDATED = "validated"
    INVENTORY_UPDATED = "inventory_updated"
    INVOICED = "invoiced"
    READY_FOR_DISPATCH = "ready_for_dispatch"


@dataclass(frozen=True, slots=True)
class Order:
    """An order registered by the main process."""

    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    status: OrderStatus = OrderStatus.PENDING

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id cannot be empty")
        if not self.customer_id.strip():
            raise ValueError("customer_id cannot be empty")
        if not self.product_id.strip():
            raise ValueError("product_id cannot be empty")
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")

