#!/usr/bin/env python3
"""Run reproducible load scenarios and capture Linux process metrics."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evidence" / "load-tests"
sys.path.insert(0, str(ROOT))

from src.load_test import run_load  # noqa: E402


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    system_scenario: str
    workers: int
    threads_per_worker: int
    product_mode: str
    explanation: str


SCENARIOS = (
    Scenario(
        "sequential",
        "normal",
        1,
        1,
        "mixed",
        "Referencia con un proceso consumidor y un hilo.",
    ),
    Scenario(
        "concurrent",
        "normal",
        2,
        4,
        "mixed",
        "Cola con dos procesos, cuatro hilos por proceso y mutex activo.",
    ),
    Scenario(
        "race",
        "race",
        2,
        4,
        "single",
        "Actualización de un mismo producto sin exclusión mutua.",
    ),
    Scenario(
        "mutex",
        "safe",
        2,
        4,
        "single",
        "Misma carga de carrera protegida por un Lock compartido.",
    ),
)


def _sample_processes(pids: list[int], elapsed: float) -> list[dict[str, Any]]:
    if not pids:
        return []
    command = [
        "ps",
        "-o",
        "pid=,ppid=,nlwp=,pcpu=,rss=,vsz=,stat=,comm=",
        "-p",
        ",".join(str(pid) for pid in pids),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    samples = []
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=7)
        if len(fields) != 8:
            continue
        pid = int(fields[0])
        task_dir = Path(f"/proc/{pid}/task")
        try:
            thread_ids = sorted(int(path.name) for path in task_dir.iterdir())
        except (FileNotFoundError, PermissionError):
            thread_ids = []
        samples.append(
            {
                "elapsed_seconds": round(elapsed, 3),
                "pid": pid,
                "ppid": int(fields[1]),
                "threads": int(fields[2]),
                "cpu_percent": float(fields[3]),
                "rss_kb": int(fields[4]),
                "vsz_kb": int(fields[5]),
                "state": fields[6],
                "command": fields[7],
                "thread_ids": thread_ids,
            }
        )
    return samples


def _monitor(
    process: subprocess.Popen[str],
    pids: list[int],
    started: float,
    output: list[dict[str, Any]],
) -> None:
    while process.poll() is None:
        output.extend(_sample_processes(pids, time.perf_counter() - started))
        time.sleep(0.05)


def _peak_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[float, list[dict[str, Any]]] = {}
    for sample in samples:
        grouped.setdefault(sample["elapsed_seconds"], []).append(sample)
    snapshots = []
    for elapsed, group in grouped.items():
        snapshots.append(
            {
                "elapsed_seconds": elapsed,
                "cpu_percent": round(sum(item["cpu_percent"] for item in group), 2),
                "rss_kb": sum(item["rss_kb"] for item in group),
                "vsz_kb": sum(item["vsz_kb"] for item in group),
                "threads": sum(item["threads"] for item in group),
                "processes": len(group),
            }
        )
    if not snapshots:
        return {
            "peak_cpu_percent": 0.0,
            "peak_rss_kb": 0,
            "peak_vsz_kb": 0,
            "peak_threads": 0,
            "processes": 0,
        }
    return {
        "peak_cpu_percent": max(item["cpu_percent"] for item in snapshots),
        "peak_rss_kb": max(item["rss_kb"] for item in snapshots),
        "peak_vsz_kb": max(item["vsz_kb"] for item in snapshots),
        "peak_threads": max(item["threads"] for item in snapshots),
        "processes": max(item["processes"] for item in snapshots),
    }


def _parse_last_json(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("system did not emit its final JSON summary")
    return json.loads(lines[-1])


def run_load_scenario(
    scenario: Scenario,
    orders: int,
    concurrency: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    initial_stock = orders + 100
    queue_capacity = max(200, concurrency * 2)
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--port",
        "0",
        "--max-orders",
        str(orders),
        "--workers",
        str(scenario.workers),
        "--threads-per-worker",
        str(scenario.threads_per_worker),
        "--queue-capacity",
        str(queue_capacity),
        "--initial-stock",
        str(initial_stock),
        "--processing-delay",
        "0.004",
        "--race-window",
        "0.002",
        "--scenario",
        scenario.system_scenario,
        "--json",
    ]

    with tempfile.TemporaryFile(mode="w+") as server_log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=server_log,
            text=True,
        )
        assert process.stdout is not None
        ready_line = process.stdout.readline()
        if not ready_line:
            process.wait(timeout=10)
            server_log.seek(0)
            raise RuntimeError(server_log.read())
        ready = json.loads(ready_line)
        pids = [ready["pid"], *(worker["pid"] for worker in ready["workers"])]

        samples: list[dict[str, Any]] = []
        started = time.perf_counter()
        monitor = threading.Thread(
            target=_monitor,
            args=(process, pids, started, samples),
            daemon=True,
        )
        monitor.start()
        load = run_load(
            host=ready["host"],
            port=ready["port"],
            orders=orders,
            concurrency=min(concurrency, orders),
            product_mode=scenario.product_mode,
            timeout=60,
            run_id=f"{scenario.name}-{orders}",
        )
        remaining_stdout, _ = process.communicate(timeout=180)
        monitor.join(timeout=2)
        total_seconds = time.perf_counter() - started
        server_log.seek(0)
        log_lines = server_log.read().splitlines()

    final = _parse_last_json(remaining_stdout)
    inventory = final["inventory"]
    lost_updates = sum(
        max(0, inventory["actual"][product] - expected)
        for product, expected in inventory["expected"].items()
    )
    row = {
        "scenario": scenario.name,
        "orders": orders,
        "client_concurrency": min(concurrency, orders),
        "workers": scenario.workers,
        "threads_per_worker": scenario.threads_per_worker,
        "accepted": load.accepted,
        "errors": load.errors,
        "request_seconds": load.request_seconds,
        "total_seconds": round(total_seconds, 3),
        "requests_per_second": load.requests_per_second,
        "completion_orders_per_second": round(orders / total_seconds, 2),
        "latency_p50_ms": load.latency_p50_ms,
        "latency_p95_ms": load.latency_p95_ms,
        "lost_updates": lost_updates,
        "race_detected": inventory["race_detected"],
        "lock_enabled": inventory["lock_enabled"],
        "system_pid": ready["pid"],
        "system_ppid": ready["ppid"],
        "worker_pids": ";".join(str(worker["pid"]) for worker in ready["workers"]),
        **_peak_metrics(samples),
    }
    trace = [
        line
        for line in log_lines
        if "Condicion de carrera" in line
        or "Exclusion mutua verificada" in line
        or "Pedido producido" in line
        or "Pedido consumido" in line
    ][:20]
    return row, samples, trace


def run_deadlock_scenario(name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--scenario",
        name,
        "--deadlock-timeout",
        "0.25",
        "--json",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    samples: list[dict[str, Any]] = []
    started = time.perf_counter()
    while process.poll() is None:
        samples.extend(_sample_processes([process.pid], time.perf_counter() - started))
        time.sleep(0.02)
    stdout, _ = process.communicate(timeout=5)
    result = _parse_last_json(stdout)
    row = {
        "scenario": name,
        "orders": 2,
        "system_pid": process.pid,
        "result": result,
        **_peak_metrics(samples),
    }
    return row, samples


def _write_report(
    rows: list[dict[str, Any]],
    deadlocks: list[dict[str, Any]],
    quantities: list[int],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with (EVIDENCE_DIR / "results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "quantities": quantities,
        "scenarios": [asdict(scenario) for scenario in SCENARIOS],
        "results": rows,
        "deadlock_results": deadlocks,
    }
    (EVIDENCE_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    headers = (
        "Escenario | Pedidos | Total s | Aceptación req/s | Completados/s | "
        "p95 ms | CPU pico % | RSS pico MB | Hilos pico | "
        "Actualizaciones perdidas"
    )
    table_rows = []
    for row in rows:
        table_rows.append(
            f"{row['scenario']} | {row['orders']} | {row['total_seconds']} | "
            f"{row['requests_per_second']} | "
            f"{row['completion_orders_per_second']} | "
            f"{row['latency_p95_ms']} | "
            f"{row['peak_cpu_percent']} | {row['peak_rss_kb'] / 1024:.1f} | "
            f"{row['peak_threads']} | {row['lost_updates']}"
        )
    report = f"""# Resultados de pruebas concurrentes

Fecha: {time.strftime('%Y-%m-%d')}

Se probaron {', '.join(map(str, quantities))} pedidos con hasta 100 clientes TCP
concurrentes. CPU y memoria corresponden a la suma del proceso principal y sus
procesos trabajadores en cada muestra.

| {headers} |
| {' | '.join(['---'] * 10)} |
""" + "\n".join(f"| {row} |" for row in table_rows) + "\n"
    report += """

## Interbloqueo

El interbloqueo usa dos pedidos porque esa es la cantidad mínima suficiente para
detener todo progreso. Se ejecutaron el escenario circular y la versión con
orden global de locks; los resultados estructurados están en `summary.json`.

## Reproducción

```bash
python scripts/run_experiments.py --quantities 100 500 1000 --concurrency 100
```
"""
    (EVIDENCE_DIR / "report.md").write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run all concurrent experiments.")
    parser.add_argument("--quantities", nargs="+", type=int, default=[100, 500, 1000])
    parser.add_argument("--concurrency", type=int, default=100)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows: list[dict[str, Any]] = []
    all_samples: dict[str, list[dict[str, Any]]] = {}
    traces: dict[str, list[str]] = {}
    for scenario in SCENARIOS:
        for orders in args.quantities:
            key = f"{scenario.name}-{orders}"
            print(f"Running {key}...", flush=True)
            row, samples, trace = run_load_scenario(
                scenario,
                orders,
                args.concurrency,
            )
            rows.append(row)
            all_samples[key] = samples
            traces[key] = trace

    deadlocks = []
    for name in ("deadlock", "deadlock-safe"):
        print(f"Running {name}...", flush=True)
        row, samples = run_deadlock_scenario(name)
        deadlocks.append(row)
        all_samples[name] = samples

    _write_report(rows, deadlocks, args.quantities)
    (EVIDENCE_DIR / "resource-samples.json").write_text(
        json.dumps(all_samples, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "trace-excerpts.json").write_text(
        json.dumps(traces, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Results written to {EVIDENCE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
