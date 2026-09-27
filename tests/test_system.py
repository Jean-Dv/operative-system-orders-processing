import json
import os
import subprocess
import sys
import time
import unittest

from src.orders import Order, OrderStatus
from src.processing import ProcessingResult
from src.system import ManagerState, SystemManager


class SystemManagerTests(unittest.TestCase):
    def test_manager_completes_its_lifecycle(self) -> None:
        manager = SystemManager()

        self.assertEqual(manager.state, ManagerState.CREATED)
        identity = manager.start()
        self.assertEqual(manager.state, ManagerState.RUNNING)
        self.assertEqual(identity.pid, os.getpid())
        self.assertEqual(identity.ppid, os.getppid())

        manager.stop()
        self.assertEqual(manager.state, ManagerState.STOPPED)

    def test_manager_cannot_start_twice(self) -> None:
        manager = SystemManager()
        manager.start()

        with self.assertRaisesRegex(RuntimeError, "cannot start"):
            manager.start()

        manager.stop()

    def test_manager_registers_and_summarizes_pending_orders(self) -> None:
        manager = SystemManager()
        manager.start()

        manager.register_order(
            Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 2)
        )
        manager.register_order(
            Order("ORD-0002", "CUSTOMER-0002", "PRODUCT-002", 1)
        )

        self.assertEqual(len(manager.orders), 2)
        self.assertTrue(
            all(order.status is OrderStatus.PENDING for order in manager.orders)
        )
        self.assertEqual(manager.summary(), {"total": 2, "pending": 2})
        manager.stop()

    def test_manager_rejects_duplicate_order_ids(self) -> None:
        manager = SystemManager()
        manager.start()
        order = Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 1)
        manager.register_order(order)

        with self.assertRaisesRegex(ValueError, "duplicate order_id"):
            manager.register_order(order)

        manager.stop()

    def test_manager_rejects_orders_when_not_running(self) -> None:
        manager = SystemManager()
        order = Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 1)

        with self.assertRaisesRegex(RuntimeError, "only be registered"):
            manager.register_order(order)

    def test_manager_consolidates_a_worker_result(self) -> None:
        manager = SystemManager()
        manager.start()
        manager.register_order(
            Order("ORD-0001", "CUSTOMER-0001", "PRODUCT-001", 1)
        )

        manager.record_result(
            ProcessingResult("ORD-0001", OrderStatus.READY_FOR_DISPATCH)
        )

        self.assertEqual(manager.summary(), {"total": 1, "ready_for_dispatch": 1})
        self.assertEqual(len(manager.results), 1)
        manager.stop()


class MainProcessIntegrationTests(unittest.TestCase):
    def test_system_accepts_orders_from_multiple_client_processes(self) -> None:
        system_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.main",
                "--port",
                "0",
                "--max-orders",
                "3",
                "--workers",
                "2",
                "--processing-delay",
                "0.30",
                "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._stop_process, system_process)
        self.assertIsNotNone(system_process.stdout)
        ready = json.loads(system_process.stdout.readline())

        processing_started_at = time.monotonic()
        clients = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "src.client",
                    "--port",
                    str(ready["port"]),
                    "--order-id",
                    f"ORD-{sequence:04d}",
                    "--customer-id",
                    f"CUSTOMER-{sequence:04d}",
                    "--product-id",
                    "PRODUCT-001",
                    "--quantity",
                    "1",
                    "--json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for sequence in range(1, 4)
        ]
        for client in clients:
            self.addCleanup(self._stop_process, client)
        responses = []
        for client in clients:
            stdout, stderr = client.communicate(timeout=15)
            self.assertEqual(client.returncode, 0, stderr)
            responses.append(json.loads(stdout))

        remaining_stdout, system_stderr = system_process.communicate(timeout=15)
        processing_elapsed = time.monotonic() - processing_started_at
        stopped = json.loads(remaining_stdout)

        self.assertEqual(system_process.returncode, 0, system_stderr)
        self.assertEqual(ready["role"], "system")
        self.assertEqual(ready["state"], "running")
        self.assertEqual(ready["pid"], system_process.pid)
        self.assertEqual(ready["ppid"], os.getpid())
        self.assertTrue(all(item["status"] == "accepted" for item in responses))
        self.assertEqual({item["worker_id"] for item in responses}, {1, 2})
        self.assertEqual(
            stopped["orders"],
            {"total": 3, "ready_for_dispatch": 3},
        )
        self.assertEqual(system_stderr.count("Pedido recibido"), 3)
        self.assertEqual(system_stderr.count("Procesamiento iniciado"), 3)
        self.assertEqual(system_stderr.count("Procesamiento finalizado"), 3)
        self.assertEqual(system_stderr.count("Etapa finalizada"), 12)
        self.assertEqual(system_stderr.count("etapa=validation"), 6)
        self.assertEqual(system_stderr.count("etapa=inventory_update"), 6)
        self.assertEqual(system_stderr.count("etapa=invoice_generation"), 6)
        self.assertEqual(system_stderr.count("etapa=dispatch_preparation"), 6)
        self.assertEqual(system_stderr.count("Trabajador iniciado"), 2)
        self.assertEqual(len(ready["workers"]), 2)
        self.assertEqual(
            len({worker["pid"] for worker in ready["workers"]}),
            2,
        )
        self.assertTrue(
            all(worker["pid"] != ready["pid"] for worker in ready["workers"])
        )
        self.assertGreaterEqual(processing_elapsed, 0.5)

        processing_events = [
            line
            for line in system_stderr.splitlines()
            if "Procesamiento iniciado" in line or "Procesamiento finalizado" in line
        ]
        first_finished = next(
            index
            for index, event in enumerate(processing_events)
            if "Procesamiento finalizado" in event
        )
        starts_before_first_finish = sum(
            "Procesamiento iniciado" in event
            for event in processing_events[:first_finished]
        )
        self.assertEqual(starts_before_first_finish, 2)

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
