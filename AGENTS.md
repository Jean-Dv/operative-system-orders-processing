# Repository Guidelines

## Project Structure & Module Organization

This repository currently contains the assignment specification in `project.pdf`. As implementation is added, keep executable code in `src/`, automated tests in `tests/`, architecture diagrams and the technical report in `docs/`, and reproducible logs or screenshots in `evidence/`. Separate the intentionally unsafe race/deadlock demonstrations from the corrected implementation, for example `src/scenarios/race_demo.py` and `src/scenarios/safe_demo.py`. Do not commit generated caches, virtual environments, or large temporary traces.

## Build, Test, and Development Commands

The brief recommends Python on Linux; no build system is configured yet. When adding Python code, document the exact supported version and entry point in `README.md`. Prefer a small, reproducible command set:

- `python -m src.main --orders 100` runs the simulator.
- `python -m unittest discover -s tests -v` runs all tests.
- `python -m src.main --scenario race --orders 1000` reproduces the unsafe case.
- `ps -eLf` and `pstree -p` capture process/thread evidence during a run.

If the instructor selects another language, replace these examples and commit the corresponding build configuration.

## Coding Style & Naming Conventions

For Python, use four-space indentation, UTF-8, PEP 8, `snake_case` for functions/modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep shared-state access explicit and narrow; name synchronization objects by protected resource, such as `inventory_lock`. Add type hints and short docstrings where concurrency behavior is not obvious. If formatters or linters are introduced, pin and document them before enforcing them.

## Testing Guidelines

Use deterministic unit tests where possible and stress tests for concurrency behavior. Name files `test_*.py` and test methods `test_<behavior>`. Cover normal processing, duplicate prevention, inventory consistency, queue shutdown, lock ordering, and multiple workloads (for example 10, 100, and 1,000 orders). Preserve before/after evidence and explain what each trace demonstrates; screenshots alone are insufficient.

## Commit & Pull Request Guidelines

No usable Git history is present, so adopt concise imperative commits such as `Add producer-consumer queue` or `Fix inventory race with lock`. Keep each commit focused. Pull requests should summarize the change, identify the tested scenario, list commands and results, link any issue, and include relevant evidence when process trees, CPU/memory behavior, races, or deadlocks change.
