"""Order-processing stages executed by each worker process."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.orders import Order, OrderStatus


class ProcessingStage(StrEnum):
    VALIDATION = "validation"
    INVENTORY = "inventory_update"
    INVOICE = "invoice_generation"
    DISPATCH = "dispatch_preparation"


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    unit_price_cents: int
    initial_stock: int


@dataclass(frozen=True, slots=True)
class InventoryUpdate:
    product_id: str
    previous_stock: int
    current_stock: int


@dataclass(frozen=True, slots=True)
class Invoice:
    invoice_id: str
    order_id: str
    total_cents: int


@dataclass(frozen=True, slots=True)
class DispatchPreparation:
    dispatch_id: str
    order_id: str
    status: str = "ready_for_dispatch"


@dataclass(frozen=True, slots=True)
class StageEvent:
    stage: ProcessingStage
    outcome: str
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    order_id: str
    status: OrderStatus
    inventory_update: InventoryUpdate | None = None
    invoice: Invoice | None = None
    dispatch: DispatchPreparation | None = None
    failure_reason: str | None = None


class ProcessingError(RuntimeError):
    def __init__(self, stage: ProcessingStage, message: str) -> None:
        super().__init__(message)
        self.stage = stage


DEFAULT_PRODUCTS = (
    Product("PRODUCT-001", unit_price_cents=19_900, initial_stock=100),
    Product("PRODUCT-002", unit_price_cents=35_500, initial_stock=100),
    Product("PRODUCT-003", unit_price_cents=12_000, initial_stock=100),
)


class Inventory:
    """Inventory owned locally by one worker during phase 2."""

    def __init__(self, products: tuple[Product, ...] = DEFAULT_PRODUCTS) -> None:
        self._products = {product.product_id: product for product in products}
        self._stock = {
            product.product_id: product.initial_stock for product in products
        }

    def product(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def stock_for(self, product_id: str) -> int:
        if product_id not in self._stock:
            raise KeyError(product_id)
        return self._stock[product_id]

    def deduct(self, order: Order) -> InventoryUpdate:
        previous_stock = self.stock_for(order.product_id)
        if previous_stock < order.quantity:
            raise ProcessingError(
                ProcessingStage.INVENTORY,
                f"insufficient stock for {order.product_id}",
            )
        current_stock = previous_stock - order.quantity
        self._stock[order.product_id] = current_stock
        return InventoryUpdate(order.product_id, previous_stock, current_stock)


class OrderProcessor:
    """Execute the e-commerce stages for one order."""

    def __init__(
        self,
        inventory: Inventory,
        total_processing_delay: float = 2.0,
    ) -> None:
        if total_processing_delay < 0:
            raise ValueError("total_processing_delay cannot be negative")
        self._inventory = inventory
        self._stage_delay = total_processing_delay / len(ProcessingStage)

    def process(
        self,
        order: Order,
        on_event: Callable[[StageEvent], None] | None = None,
    ) -> ProcessingResult:
        emit = on_event or (lambda event: None)
        inventory_update: InventoryUpdate | None = None
        invoice: Invoice | None = None
        dispatch: DispatchPreparation | None = None

        try:
            self._stage(ProcessingStage.VALIDATION, emit)
            product = self._validate(order)
            emit(
                StageEvent(
                    ProcessingStage.VALIDATION,
                    "completed",
                    {"result": "valid"},
                )
            )

            self._stage(ProcessingStage.INVENTORY, emit)
            inventory_update = self._inventory.deduct(order)
            emit(
                StageEvent(
                    ProcessingStage.INVENTORY,
                    "completed",
                    {
                        "previous_stock": inventory_update.previous_stock,
                        "current_stock": inventory_update.current_stock,
                    },
                )
            )

            self._stage(ProcessingStage.INVOICE, emit)
            invoice = Invoice(
                invoice_id=f"INV-{order.order_id}",
                order_id=order.order_id,
                total_cents=product.unit_price_cents * order.quantity,
            )
            emit(
                StageEvent(
                    ProcessingStage.INVOICE,
                    "completed",
                    {
                        "invoice_id": invoice.invoice_id,
                        "total_cents": invoice.total_cents,
                    },
                )
            )

            self._stage(ProcessingStage.DISPATCH, emit)
            dispatch = DispatchPreparation(
                dispatch_id=f"DSP-{order.order_id}",
                order_id=order.order_id,
            )
            emit(
                StageEvent(
                    ProcessingStage.DISPATCH,
                    "completed",
                    {
                        "dispatch_id": dispatch.dispatch_id,
                        "status": dispatch.status,
                    },
                )
            )
        except ProcessingError as error:
            emit(StageEvent(error.stage, "failed", {"reason": str(error)}))
            return ProcessingResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                inventory_update=inventory_update,
                failure_reason=str(error),
            )

        return ProcessingResult(
            order_id=order.order_id,
            status=OrderStatus.READY_FOR_DISPATCH,
            inventory_update=inventory_update,
            invoice=invoice,
            dispatch=dispatch,
        )

    def _stage(
        self,
        stage: ProcessingStage,
        emit: Callable[[StageEvent], None],
    ) -> None:
        emit(StageEvent(stage, "started", {}))
        time.sleep(self._stage_delay)

    def _validate(self, order: Order) -> Product:
        product = self._inventory.product(order.product_id)
        if product is None:
            raise ProcessingError(
                ProcessingStage.VALIDATION,
                f"unknown product: {order.product_id}",
            )
        return product
