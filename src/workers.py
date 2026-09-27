"""Persistent worker processes used to handle orders."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
from dataclasses import dataclass
from multiprocessing.connection import Connection

from src.orders import Order, OrderStatus
from src.processing import Inventory, OrderProcessor, ProcessingResult, StageEvent


LOGGER = logging.getLogger("order_system.workers")


def _configure_worker_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | PID=%(process)d | %(message)s",
        datefmt="%H:%M:%S",
    )


def _worker_main(
    worker_id: int,
    connection: Connection,
    processing_delay: float,
) -> None:
    """Receive and process orders inside a child process."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _configure_worker_logging()
    connection.send({"event": "ready", "pid": os.getpid()})
    LOGGER.info(
        "Trabajador iniciado | worker=%s ppid=%s",
        worker_id,
        os.getppid(),
    )
    processor = OrderProcessor(Inventory(), processing_delay)
    results: list[ProcessingResult] = []

    def log_stage(event: StageEvent) -> None:
        details = " ".join(f"{key}={value}" for key, value in event.details.items())
        outcome_labels = {
            "started": "iniciada",
            "completed": "finalizada",
            "failed": "fallida",
        }
        LOGGER.info(
            "Etapa %s | worker=%s etapa=%s%s",
            outcome_labels[event.outcome],
            worker_id,
            event.stage.value,
            f" {details}" if details else "",
        )

    try:
        while True:
            try:
                order = connection.recv()
            except EOFError:
                break
            if order is None:
                break

            LOGGER.info(
                "Procesamiento iniciado | worker=%s pedido=%s demora_simulada=%.2fs",
                worker_id,
                order.order_id,
                processing_delay,
            )
            result = processor.process(order, on_event=log_stage)
            results.append(result)
            if result.status is OrderStatus.REJECTED:
                LOGGER.warning(
                    "Procesamiento rechazado | worker=%s pedido=%s motivo=%s",
                    worker_id,
                    order.order_id,
                    result.failure_reason,
                )
            else:
                LOGGER.info(
                    "Procesamiento finalizado | worker=%s pedido=%s "
                    "estado=%s factura=%s despacho=%s",
                    worker_id,
                    order.order_id,
                    result.status.value,
                    result.invoice.invoice_id if result.invoice else "none",
                    result.dispatch.dispatch_id if result.dispatch else "none",
                )
    finally:
        connection.send({"event": "stopped", "results": results})
        connection.close()
        LOGGER.info("Trabajador detenido | worker=%s", worker_id)


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    worker_id: int
    pid: int


@dataclass(slots=True)
class _WorkerHandle:
    identity: WorkerIdentity
    process: mp.Process
    connection: Connection


class WorkerPool:
    """Manage child processes and distribute orders round-robin over pipes."""

    def __init__(self, worker_count: int, processing_delay: float = 2.0) -> None:
        if worker_count <= 0:
            raise ValueError("worker_count must be greater than zero")
        if processing_delay < 0:
            raise ValueError("processing_delay cannot be negative")

        self._worker_count = worker_count
        self._processing_delay = processing_delay
        self._context = mp.get_context("spawn")
        self._workers: list[_WorkerHandle] = []
        self._next_worker = 0

    @property
    def identities(self) -> tuple[WorkerIdentity, ...]:
        return tuple(worker.identity for worker in self._workers)

    def start(self) -> None:
        if self._workers:
            raise RuntimeError("worker pool is already running")

        for worker_id in range(1, self._worker_count + 1):
            parent_connection, child_connection = self._context.Pipe(duplex=True)
            process = self._context.Process(
                target=_worker_main,
                args=(worker_id, child_connection, self._processing_delay),
                name=f"order-worker-{worker_id}",
            )
            process.start()
            child_connection.close()

            if not parent_connection.poll(5):
                process.terminate()
                process.join()
                parent_connection.close()
                raise RuntimeError(f"worker {worker_id} did not start")
            ready = parent_connection.recv()
            identity = WorkerIdentity(worker_id=worker_id, pid=ready["pid"])
            self._workers.append(_WorkerHandle(identity, process, parent_connection))

    def submit(self, order: Order) -> WorkerIdentity:
        if not self._workers:
            raise RuntimeError("worker pool is not running")

        worker = self._workers[self._next_worker]
        self._next_worker = (self._next_worker + 1) % len(self._workers)
        worker.connection.send(order)
        return worker.identity

    def stop(self) -> tuple[ProcessingResult, ...]:
        if not self._workers:
            return ()

        workers, self._workers = self._workers, []
        for worker in workers:
            worker.connection.send(None)

        results: list[ProcessingResult] = []
        for worker in workers:
            report = worker.connection.recv()
            results.extend(report["results"])
            worker.connection.close()
        for worker in workers:
            worker.process.join()
        return tuple(results)
