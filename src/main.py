"""Command-line entry point for the main administrator process."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict

from src.orders import OrderStatus
from src.server import OrderServer, ServerAddress
from src.scenarios.deadlock_demo import (
    simulate_deadlock,
    simulate_deadlock_prevention,
)
from src.system import SystemManager
from src.workers import WorkerPool


def configure_logging() -> None:
    """Configure human-readable operational events for the system process."""
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | PID=%(process)d | "
            "THREAD=%(threadName)s | %(message)s"
        ),
        datefmt="%H:%M:%S",
    )


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
        "--workers",
        type=positive_int,
        default=2,
        help="number of worker processes (default: 2)",
    )
    parser.add_argument(
        "--threads-per-worker",
        type=positive_int,
        default=2,
        help="number of order-processing threads per worker (default: 2)",
    )
    parser.add_argument(
        "--queue-capacity",
        type=positive_int,
        default=100,
        help="maximum pending orders in the producer-consumer queue (default: 100)",
    )
    parser.add_argument(
        "--processing-delay",
        type=non_negative_float,
        default=2.0,
        help="seconds spent by a worker on each order (default: 2)",
    )
    parser.add_argument(
        "--scenario",
        choices=("normal", "race", "safe", "deadlock", "deadlock-safe"),
        default="normal",
        help="compare the unsafe 'race' and mutex-protected 'safe' scenarios",
    )
    parser.add_argument(
        "--deadlock-timeout",
        type=positive_float,
        default=0.25,
        help="seconds to wait before diagnosing the deadlock (default: 0.25)",
    )
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


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    if args.scenario in {"deadlock", "deadlock-safe"}:
        if args.scenario == "deadlock":
            report = simulate_deadlock(args.deadlock_timeout)
            payload = {"event": "deadlock_diagnosis", **asdict(report)}
            successful = report.detected
            logging.getLogger("order_system").warning(
                "Interbloqueo detectado=%s | hilos_bloqueados=%s",
                report.detected,
                len(report.blocked_threads),
            )
        else:
            report = simulate_deadlock_prevention(args.deadlock_timeout)
            payload = {"event": "deadlock_prevention", **asdict(report)}
            successful = report.prevented
            logging.getLogger("order_system").info(
                "Interbloqueo evitado=%s | estrategia=%s orden=%s",
                report.prevented,
                report.strategy,
                "->".join(report.acquisition_order),
            )
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if successful else 1

    manager = SystemManager()
    identity = manager.start()
    worker_pool = WorkerPool(
        args.workers,
        args.processing_delay,
        args.threads_per_worker,
        race_window=0.1 if args.scenario in {"race", "safe"} else 0.0,
        use_inventory_lock=args.scenario != "race",
        queue_capacity=args.queue_capacity,
    )
    worker_pool.start()
    server = OrderServer(
        manager,
        worker_pool.submit,
        args.host,
        args.port,
    )

    def announce_ready(address: ServerAddress) -> None:
        details = {
            "event": "ready",
            "role": "system",
            "pid": identity.pid,
            "ppid": identity.ppid,
            "state": manager.state.value,
            "host": address.host,
            "port": address.port,
            "workers": [
                {
                    "worker_id": worker.worker_id,
                    "pid": worker.pid,
                    "threads_per_worker": worker.threads_per_worker,
                }
                for worker in worker_pool.identities
            ],
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
        logging.getLogger("order_system").info(
            "Sistema preparado para recibir pedidos | direccion=%s:%s",
            address.host,
            address.port,
        )

    try:
        server.serve(max_orders=args.max_orders, on_ready=announce_ready)
    except KeyboardInterrupt:
        pass
    finally:
        for result in worker_pool.stop():
            manager.record_result(result)
        summary = manager.summary()
        manager.stop()

    actual_inventory = worker_pool.inventory_snapshot
    expected_inventory = worker_pool.initial_inventory_snapshot
    for order in manager.orders:
        if order.status is OrderStatus.READY_FOR_DISPATCH:
            expected_inventory[order.product_id] -= order.quantity
    race_detected = actual_inventory != expected_inventory
    if race_detected:
        logging.getLogger("order_system").warning(
            "Condicion de carrera detectada | esperado=%s real=%s",
            expected_inventory,
            actual_inventory,
        )
    elif worker_pool.inventory_lock_enabled:
        logging.getLogger("order_system").info(
            "Exclusion mutua verificada | esperado=%s real=%s",
            expected_inventory,
            actual_inventory,
        )

    stopped = {
        "event": "stopped",
        "orders": summary,
        "inventory": {
            "expected": expected_inventory,
            "actual": actual_inventory,
            "race_detected": race_detected,
            "lock_enabled": worker_pool.inventory_lock_enabled,
        },
    }
    logging.getLogger("order_system").info(
        "Sistema detenido | pedidos_registrados=%s",
        summary["total"],
    )
    if args.json:
        print(json.dumps(stopped, sort_keys=True), flush=True)
    else:
        print(f"System stopped; registered {summary['total']} orders")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
