"""Command-line client that submits one order to the system."""

from __future__ import annotations

import argparse
import json
import socket
import uuid
from collections.abc import Sequence

from src.protocol import receive_message, send_message


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit an order to the system.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--order-id", default=None)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--quantity", type=positive_int, required=True)
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=30,
        help="seconds to wait for the sequential server (default: 30)",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    order_id = args.order_id or f"ORD-{uuid.uuid4().hex[:12].upper()}"
    request = {
        "action": "submit_order",
        "order_id": order_id,
        "customer_id": args.customer_id,
        "product_id": args.product_id,
        "quantity": args.quantity,
    }

    with socket.create_connection(
        (args.host, args.port), timeout=args.timeout
    ) as connection:
        send_message(connection, request)
        response = receive_message(connection)

    if args.json:
        print(json.dumps(response, sort_keys=True))
    elif response["status"] == "accepted":
        print(f"Order {response['order_id']} accepted by the system")
    else:
        print(f"Order rejected: {response['message']}")
    return 0 if response["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
