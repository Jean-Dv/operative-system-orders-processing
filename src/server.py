"""TCP boundary owned by the main system process."""

from __future__ import annotations

import time
import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.orders import Order
from src.protocol import ProtocolError, receive_message, send_message
from src.system import SystemManager


LOGGER = logging.getLogger("order_system.server")


@dataclass(frozen=True, slots=True)
class ServerAddress:
    host: str
    port: int


def order_from_message(message: dict[str, Any]) -> Order:
    """Validate a client request and convert it to an order."""
    if message.get("action") != "submit_order":
        raise ProtocolError("unsupported action")

    required_fields = ("order_id", "customer_id", "product_id", "quantity")
    if any(field not in message for field in required_fields):
        raise ProtocolError("order fields are incomplete")
    if not all(isinstance(message[field], str) for field in required_fields[:3]):
        raise ProtocolError("order identifiers must be strings")
    if not isinstance(message["quantity"], int) or isinstance(
        message["quantity"], bool
    ):
        raise ProtocolError("quantity must be an integer")

    return Order(
        order_id=message["order_id"],
        customer_id=message["customer_id"],
        product_id=message["product_id"],
        quantity=message["quantity"],
    )


class OrderServer:
    """Accept client orders and hand them to the main-process manager."""

    def __init__(
        self,
        manager: SystemManager,
        host: str = "127.0.0.1",
        port: int = 5000,
        processing_delay: float = 2.0,
    ) -> None:
        self._manager = manager
        self._host = host
        self._port = port
        self._processing_delay = processing_delay

    def serve(
        self,
        *,
        max_orders: int | None = None,
        on_ready: Callable[[ServerAddress], None] | None = None,
    ) -> None:
        """Serve sequentially until interrupted or max_orders are accepted."""
        accepted_orders = 0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self._host, self._port))
            listener.listen()
            bound_host, bound_port = listener.getsockname()
            if on_ready is not None:
                on_ready(ServerAddress(bound_host, bound_port))

            while max_orders is None or accepted_orders < max_orders:
                connection, client_address = listener.accept()
                with connection:
                    LOGGER.info(
                        "Cliente conectado | ip=%s puerto=%s",
                        client_address[0],
                        client_address[1],
                    )
                    if self._handle_client(connection):
                        accepted_orders += 1

    def _handle_client(self, connection: socket.socket) -> bool:
        try:
            order = order_from_message(receive_message(connection))
            LOGGER.info(
                "Pedido recibido | id=%s cliente=%s producto=%s cantidad=%s",
                order.order_id,
                order.customer_id,
                order.product_id,
                order.quantity,
            )
            LOGGER.info(
                "Procesamiento iniciado | id=%s demora_simulada=%.2fs",
                order.order_id,
                self._processing_delay,
            )
            time.sleep(self._processing_delay)
            LOGGER.info(
                "Validacion completada | id=%s resultado=correcto",
                order.order_id,
            )
            self._manager.register_order(order)
        except (ProtocolError, ValueError) as error:
            LOGGER.warning("Pedido rechazado | motivo=%s", error)
            send_message(connection, {"status": "error", "message": str(error)})
            return False

        summary = self._manager.summary()
        LOGGER.info(
            "Procesamiento finalizado | id=%s estado=%s total_pendientes=%s",
            order.order_id,
            order.status.value,
            summary.get("pending", 0),
        )
        send_message(
            connection,
            {"status": "accepted", "order_id": order.order_id},
        )
        return True
