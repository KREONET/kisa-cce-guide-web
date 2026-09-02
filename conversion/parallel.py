"""Provide bounded process workers for CPU-heavy deterministic pipelines."""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

MAXIMUM_WORKERS = 16
DEFAULT_WORKER_LIMIT = 8


def default_worker_count() -> int:
    """Return a conservative worker count bounded by available CPUs."""

    available_cpus = os.process_cpu_count() or 1
    return max(1, min(available_cpus, DEFAULT_WORKER_LIMIT))


def parse_worker_count(value: str) -> int:
    """Parse a bounded positive worker count for command-line interfaces."""

    try:
        workers = int(value)
    except ValueError as error:
        message = "workers must be an integer"
        raise argparse.ArgumentTypeError(message) from error
    try:
        return validate_worker_count(workers)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def validate_worker_count(workers: object) -> int:
    """Return a worker count after enforcing the shared hard bound."""

    if (
        isinstance(workers, bool)
        or not isinstance(workers, int)
        or not 1 <= workers <= MAXIMUM_WORKERS
    ):
        message = f"workers must be between 1 and {MAXIMUM_WORKERS}"
        raise ValueError(message)
    return workers


def process_executor(workers: int) -> ProcessPoolExecutor:
    """Create an isolated process pool with consistent cross-version semantics."""

    validate_worker_count(workers)
    return ProcessPoolExecutor(
        max_workers=workers,
        mp_context=get_context("spawn"),
    )
