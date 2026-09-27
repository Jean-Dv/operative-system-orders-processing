"""Persistent worker processes used to handle orders."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from multiprocessing.connection import Connection

from src.orders import Order, OrderStatus
from src.processing import (
    DEFAULT_PRODUCTS,
    OrderProcessor,
    ProcessingResult,
    SharedInventory,
    StageEvent,
)


LOGGER = logging.getLogger("order_system.workers")


def _configure_worker_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | PID=%(process)d | "
            "THREAD=%(threadName)s | %(message)s"
        ),
        datefmt="%H:%M:%S",
    )


def _worker_main(
    worker_id: int,
    connection: Connection,
    task_queue: object,
    processing_delay: float,
    threads_per_worker: int,
    inventory: SharedInventory,
) -> None:
    """Receive and process orders inside a child process."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _configure_worker_logging()
    connection.send(
        {
            "event": "ready",
            "pid": os.getpid(),
            "threads_per_worker": threads_per_worker,
        }
    )
    LOGGER.info(
        "Trabajador iniciado | worker=%s ppid=%s",
        worker_id,
        os.getppid(),
    )
    processor = OrderProcessor(inventory, processing_delay)
    futures: list[Future[ProcessingResult]] = []

    with ThreadPoolExecutor(
        max_workers=threads_per_worker,
        thread_name_prefix=f"worker-{worker_id}-thread",
    ) as executor:
        pending: set[Future[ProcessingResult]] = set()
        while True:
            if len(pending) >= threads_per_worker:
                _, pending = wait(pending, return_when=FIRST_COMPLETED)

            order = task_queue.get()
            if order is None:
                task_queue.task_done()
                break
            LOGGER.info(
                "Pedido consumido | worker=%s pedido=%s",
                worker_id,
                order.order_id,
            )
            future = executor.submit(
                _process_order_and_ack,
                worker_id,
                processor,
                order,
                processing_delay,
                task_queue,
            )
            futures.append(future)
            pending.add(future)

    results = [future.result() for future in futures]
    connection.send({"event": "stopped", "results": results})
    connection.close()
    LOGGER.info("Trabajador detenido | worker=%s", worker_id)


def _process_order_and_ack(
    worker_id: int,
    processor: OrderProcessor,
    order: Order,
    processing_delay: float,
    task_queue: object,
) -> ProcessingResult:
    try:
        return _process_order(worker_id, processor, order, processing_delay)
    finally:
        task_queue.task_done()


def _process_order(
    worker_id: int,
    processor: OrderProcessor,
    order: Order,
    processing_delay: float,
) -> ProcessingResult:
    """Process one order in a thread owned by a worker process."""
    thread_name = threading.current_thread().name
    thread_id = threading.get_ident()

    def log_stage(event: StageEvent) -> None:
        details = " ".join(f"{key}={value}" for key, value in event.details.items())
        outcome_labels = {
            "started": "iniciada",
            "completed": "finalizada",
            "failed": "fallida",
        }
        LOGGER.info(
            "Etapa %s | worker=%s hilo=%s pedido=%s etapa=%s%s",
            outcome_labels[event.outcome],
            worker_id,
            thread_name,
            order.order_id,
            event.stage.value,
            f" {details}" if details else "",
        )

    LOGGER.info(
        "Procesamiento iniciado | worker=%s hilo=%s hilo_id=%s "
        "pedido=%s demora_simulada=%.2fs",
        worker_id,
        thread_name,
        thread_id,
        order.order_id,
        processing_delay,
    )
    result = processor.process(order, on_event=log_stage)
    if result.status is OrderStatus.REJECTED:
        LOGGER.warning(
            "Procesamiento rechazado | worker=%s hilo=%s pedido=%s motivo=%s",
            worker_id,
            thread_name,
            order.order_id,
            result.failure_reason,
        )
    else:
        LOGGER.info(
            "Procesamiento finalizado | worker=%s hilo=%s pedido=%s "
            "estado=%s factura=%s despacho=%s",
            worker_id,
            thread_name,
            order.order_id,
            result.status.value,
            result.invoice.invoice_id if result.invoice else "none",
            result.dispatch.dispatch_id if result.dispatch else "none",
        )
    return result


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    worker_id: int
    pid: int
    threads_per_worker: int


@dataclass(slots=True)
class _WorkerHandle:
    identity: WorkerIdentity
    process: mp.Process
    connection: Connection


class WorkerPool:
    """Manage child processes that consume orders from one shared queue."""

    def __init__(
        self,
        worker_count: int,
        processing_delay: float = 2.0,
        threads_per_worker: int = 2,
        race_window: float = 0.0,
        use_inventory_lock: bool = True,
        queue_capacity: int = 100,
    ) -> None:
        if worker_count <= 0:
            raise ValueError("worker_count must be greater than zero")
        if processing_delay < 0:
            raise ValueError("processing_delay cannot be negative")
        if threads_per_worker <= 0:
            raise ValueError("threads_per_worker must be greater than zero")
        if race_window < 0:
            raise ValueError("race_window cannot be negative")
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be greater than zero")

        self._worker_count = worker_count
        self._processing_delay = processing_delay
        self._threads_per_worker = threads_per_worker
        self._context = mp.get_context("spawn")
        self._task_queue = self._context.JoinableQueue(maxsize=queue_capacity)
        shared_stock = self._context.Array(
            "i",
            [product.initial_stock for product in DEFAULT_PRODUCTS],
            lock=False,
        )
        inventory_lock = self._context.Lock() if use_inventory_lock else None
        self._inventory = SharedInventory(
            shared_stock,
            race_window=race_window,
            lock=inventory_lock,
        )
        self._inventory_lock_enabled = use_inventory_lock
        self._workers: list[_WorkerHandle] = []

    @property
    def identities(self) -> tuple[WorkerIdentity, ...]:
        return tuple(worker.identity for worker in self._workers)

    @property
    def inventory_snapshot(self) -> dict[str, int]:
        return self._inventory.snapshot()

    @property
    def initial_inventory_snapshot(self) -> dict[str, int]:
        return self._inventory.initial_snapshot()

    @property
    def inventory_lock_enabled(self) -> bool:
        return self._inventory_lock_enabled

    def start(self) -> None:
        if self._workers:
            raise RuntimeError("worker pool is already running")

        for worker_id in range(1, self._worker_count + 1):
            parent_connection, child_connection = self._context.Pipe(duplex=True)
            process = self._context.Process(
                target=_worker_main,
                args=(
                    worker_id,
                    child_connection,
                    self._task_queue,
                    self._processing_delay,
                    self._threads_per_worker,
                    self._inventory,
                ),
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
            identity = WorkerIdentity(
                worker_id=worker_id,
                pid=ready["pid"],
                threads_per_worker=ready["threads_per_worker"],
            )
            self._workers.append(_WorkerHandle(identity, process, parent_connection))

    def submit(self, order: Order) -> None:
        if not self._workers:
            raise RuntimeError("worker pool is not running")

        self._task_queue.put(order)

    def stop(self) -> tuple[ProcessingResult, ...]:
        if not self._workers:
            return ()

        workers, self._workers = self._workers, []
        self._task_queue.join()
        for _ in workers:
            self._task_queue.put(None)
        self._task_queue.join()

        results: list[ProcessingResult] = []
        for worker in workers:
            report = worker.connection.recv()
            results.extend(report["results"])
            worker.connection.close()
        for worker in workers:
            worker.process.join()
        self._task_queue.close()
        self._task_queue.join_thread()
        return tuple(results)
