"""Command-line entry point for the main administrator process."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from src.server import OrderServer, ServerAddress
from src.system import SystemManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the main order-processing administrator."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print process information as JSON",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface on which to accept clients (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument(
        "--max-orders",
        type=positive_int,
        default=None,
        help="stop after accepting this many orders; unlimited by default",
    )
    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = SystemManager()
    identity = manager.start()
    server = OrderServer(manager, args.host, args.port)

    def announce_ready(address: ServerAddress) -> None:
        details = {
            "event": "ready",
            "role": "system",
            "pid": identity.pid,
            "ppid": identity.ppid,
            "state": manager.state.value,
            "host": address.host,
            "port": address.port,
        }
        if args.json:
            print(json.dumps(details, sort_keys=True), flush=True)
        else:
            print(
                "System ready "
                f"(PID={identity.pid}, PPID={identity.ppid}) at "
                f"{address.host}:{address.port}",
                flush=True,
            )

    try:
        server.serve(max_orders=args.max_orders, on_ready=announce_ready)
    except KeyboardInterrupt:
        pass
    finally:
        summary = manager.summary()
        manager.stop()

    stopped = {"event": "stopped", "orders": summary}
    if args.json:
        print(json.dumps(stopped, sort_keys=True), flush=True)
    else:
        print(f"System stopped; registered {summary['total']} orders")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
