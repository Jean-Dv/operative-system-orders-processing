"""Reproducible circular-wait deadlock involving two orders and two resources."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection


@dataclass(frozen=True, slots=True)
class WaitState:
    order_id: str
    thread_name: str
    holds: str
    waits_for: str


@dataclass(frozen=True, slots=True)
class DeadlockReport:
    detected: bool
    timeout_seconds: float
    blocked_threads: tuple[WaitState, ...]
    mutual_exclusion: bool
    hold_and_wait: bool
    no_preemption: bool
    circular_wait: bool


def _deadlock_child(connection: Connection, timeout: float) -> None:
    inventory_lock = threading.Lock()
    invoice_lock = threading.Lock()
    first_locks_acquired = threading.Barrier(2)
    wait_states: list[WaitState] = []

    def process_order(
        order_id: str,
        first_lock: threading.Lock,
        first_resource: str,
        second_lock: threading.Lock,
        second_resource: str,
    ) -> None:
        first_lock.acquire()
        first_locks_acquired.wait()
        wait_states.append(
            WaitState(
                order_id=order_id,
                thread_name=threading.current_thread().name,
                holds=first_resource,
                waits_for=second_resource,
            )
        )
        second_lock.acquire()

    threads = (
        threading.Thread(
            target=process_order,
            args=(
                "ORDER-A",
                inventory_lock,
                "inventory_lock",
                invoice_lock,
                "invoice_lock",
            ),
            name="deadlock-order-a",
            daemon=True,
        ),
        threading.Thread(
            target=process_order,
            args=(
                "ORDER-B",
                invoice_lock,
                "invoice_lock",
                inventory_lock,
                "inventory_lock",
            ),
            name="deadlock-order-b",
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)

    detected = all(thread.is_alive() for thread in threads)
    connection.send(
        DeadlockReport(
            detected=detected,
            timeout_seconds=timeout,
            blocked_threads=tuple(sorted(wait_states, key=lambda item: item.order_id)),
            mutual_exclusion=True,
            hold_and_wait=detected,
            no_preemption=detected,
            circular_wait=detected,
        )
    )
    connection.close()


def simulate_deadlock(timeout: float = 0.25) -> DeadlockReport:
    """Run the real deadlock in an isolated process and return its diagnosis."""
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    context = mp.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_deadlock_child,
        args=(child_connection, timeout),
        name="deadlock-simulation",
    )
    process.start()
    child_connection.close()

    if not parent_connection.poll(timeout * 4 + 2):
        process.terminate()
        process.join()
        parent_connection.close()
        raise RuntimeError("deadlock simulation did not report a result")

    report = parent_connection.recv()
    parent_connection.close()
    process.join(timeout=1)
    if process.is_alive():
        process.terminate()
        process.join()
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate a circular-wait deadlock.")
    parser.add_argument("--timeout", type=float, default=0.25)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = simulate_deadlock(args.timeout)
    if args.json:
        print(json.dumps(asdict(report), sort_keys=True))
    else:
        print("Deadlock detected:" if report.detected else "No deadlock detected:")
        for state in report.blocked_threads:
            print(
                f"- {state.order_id} ({state.thread_name}) holds {state.holds} "
                f"and waits for {state.waits_for}"
            )
    return 0 if report.detected else 1


if __name__ == "__main__":
    raise SystemExit(main())

