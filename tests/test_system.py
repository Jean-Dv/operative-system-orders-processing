import json
import os
import subprocess
import sys
import unittest

from src.orders import Order, OrderStatus
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
                "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._stop_process, system_process)
        self.assertIsNotNone(system_process.stdout)
        ready = json.loads(system_process.stdout.readline())

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
        responses = []
        for client in clients:
            stdout, stderr = client.communicate(timeout=5)
            self.assertEqual(client.returncode, 0, stderr)
            responses.append(json.loads(stdout))

        remaining_stdout, system_stderr = system_process.communicate(timeout=5)
        stopped = json.loads(remaining_stdout)

        self.assertEqual(system_process.returncode, 0, system_stderr)
        self.assertEqual(ready["role"], "system")
        self.assertEqual(ready["state"], "running")
        self.assertEqual(ready["pid"], system_process.pid)
        self.assertEqual(ready["ppid"], os.getpid())
        self.assertTrue(all(item["status"] == "accepted" for item in responses))
        self.assertEqual(stopped["orders"], {"total": 3, "pending": 3})

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
