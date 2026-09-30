"""Concurrent TCP load generator for the order-processing system."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import statistics
import threading
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from src.protocol import receive_message, send_message


@dataclass(frozen=True, slots=True)
class LoadResult:
    orders: int
    concurrency: int
    accepted: int
    errors: int
    request_seconds: float
    requests_per_second: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_max_ms: float
    statuses: dict[str, int]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, index)]


def run_load(
    *,
    host: str,
    port: int,
    orders: int,
    concurrency: int,
    product_mode: str = "mixed",
    timeout: float = 30,
    run_id: str | None = None,
) -> LoadResult:
    if orders <= 0:
        raise ValueError("orders must be greater than zero")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")
    if product_mode not in {"mixed", "single"}:
        raise ValueError("product_mode must be 'mixed' or 'single'")

    worker_count = min(orders, concurrency)
    start_gate = threading.Event()
    run_id = run_id or f"{os.getpid()}-{time.time_ns()}"

    def submit_order(sequence: int) -> tuple[str, float]:
        product_number = 1 if product_mode == "single" else ((sequence - 1) % 3) + 1
        request = {
            "action": "submit_order",
            "order_id": f"LOAD-{run_id}-{sequence:06d}",
            "customer_id": f"CUSTOMER-{sequence:06d}",
            "product_id": f"PRODUCT-{product_number:03d}",
            "quantity": 1,
        }
        start_gate.wait()
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout) as connection:
                send_message(connection, request)
                response = receive_message(connection)
            status = str(response.get("status", "invalid_response"))
        except (OSError, ValueError) as error:
            status = f"error:{type(error).__name__}"
        return status, (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(submit_order, sequence) for sequence in range(1, orders + 1)]
        start_gate.set()
        outcomes = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started

    statuses = Counter(status for status, _ in outcomes)
    latencies = [latency for _, latency in outcomes]
    accepted = statuses.get("accepted", 0)
    return LoadResult(
        orders=orders,
        concurrency=worker_count,
        accepted=accepted,
        errors=orders - accepted,
        request_seconds=round(elapsed, 6),
        requests_per_second=round(orders / elapsed, 2),
        latency_p50_ms=round(statistics.median(latencies), 3),
        latency_p95_ms=round(_percentile(latencies, 0.95), 3),
        latency_max_ms=round(max(latencies), 3),
        statuses=dict(statuses),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send concurrent order requests.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--orders", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--product-mode", choices=("mixed", "single"), default="mixed")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--run-id", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_load(
        host=args.host,
        port=args.port,
        orders=args.orders,
        concurrency=args.concurrency,
        product_mode=args.product_mode,
        timeout=args.timeout,
        run_id=args.run_id,
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

