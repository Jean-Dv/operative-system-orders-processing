"""Lifecycle for the process that administers the order processing system."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from src.orders import Order


class ManagerState(StrEnum):
    """Valid lifecycle states for the main process."""

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """Operating-system identity of the main process."""

    pid: int
    ppid: int


class SystemManager:
    """Coordinate the system from the process in which it was created."""

    def __init__(self) -> None:
        self._owner_pid = os.getpid()
        self._state = ManagerState.CREATED
        self._orders: dict[str, Order] = {}

    @property
    def state(self) -> ManagerState:
        return self._state

    @property
    def identity(self) -> ProcessIdentity:
        return ProcessIdentity(pid=self._owner_pid, ppid=os.getppid())

    @property
    def orders(self) -> tuple[Order, ...]:
        """Return an immutable view of orders in registration order."""
        return tuple(self._orders.values())

    def start(self) -> ProcessIdentity:
        """Start the administrator in its owning process."""
        if os.getpid() != self._owner_pid:
            raise RuntimeError("the system manager must run in its owning process")
        if self._state is not ManagerState.CREATED:
            raise RuntimeError(f"cannot start manager from state {self._state}")

        self._state = ManagerState.RUNNING
        return self.identity

    def register_order(self, order: Order) -> None:
        """Register a new order for processing in a later phase."""
        if self._state is not ManagerState.RUNNING:
            raise RuntimeError("orders can only be registered while the manager is running")
        if order.order_id in self._orders:
            raise ValueError(f"duplicate order_id: {order.order_id}")
        self._orders[order.order_id] = order

    def summary(self) -> dict[str, int]:
        """Summarize the orders currently administered by status."""
        status_counts = Counter(order.status.value for order in self._orders.values())
        return {
            "total": len(self._orders),
            **{status: count for status, count in sorted(status_counts.items())},
        }

    def stop(self) -> None:
        """Stop a running administrator."""
        if self._state is not ManagerState.RUNNING:
            raise RuntimeError(f"cannot stop manager from state {self._state}")
        self._state = ManagerState.STOPPED
