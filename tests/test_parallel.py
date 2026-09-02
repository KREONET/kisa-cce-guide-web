"""Tests for deterministic bounded worker configuration."""

from __future__ import annotations

import argparse

import pytest

from conversion.parallel import (
    DEFAULT_WORKER_LIMIT,
    MAXIMUM_WORKERS,
    default_worker_count,
    parse_worker_count,
    validate_worker_count,
)


def test_default_worker_count_is_positive_and_conservative() -> None:
    """Automatic concurrency must stay inside the documented resource bound."""

    assert 1 <= default_worker_count() <= DEFAULT_WORKER_LIMIT


@pytest.mark.parametrize("workers", [0, MAXIMUM_WORKERS + 1, True, 1.5, "2", None])
def test_worker_count_rejects_values_outside_the_hard_bound(workers: object) -> None:
    """Library callers must not create empty or excessive worker pools."""

    with pytest.raises(ValueError, match=rf"workers must be between 1 and {MAXIMUM_WORKERS}"):
        validate_worker_count(workers)


@pytest.mark.parametrize("value", ["0", str(MAXIMUM_WORKERS + 1), "many"])
def test_worker_argument_rejects_invalid_values(value: str) -> None:
    """Command-line parsing must report invalid worker counts consistently."""

    with pytest.raises(argparse.ArgumentTypeError):
        parse_worker_count(value)
