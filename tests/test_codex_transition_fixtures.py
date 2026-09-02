"""Regression tests for portable extracted-to-structured transition fixtures."""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

import pytest

from conversion.common import criterion_source_checksum, repository_root
from conversion.paths import CANONICAL_ASSET_DIRECTORY, SOURCE_DOCUMENT_PATH
from tests.codex_transition_fixtures import (
    EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS,
    TRANSITION_FIXTURE_DIRECTORY,
    TRANSITION_FIXTURE_DOMAIN_IDENTIFIERS,
    create_codex_transition_repository,
)

EXPECTED_TRANSITION_ASSET_COUNT = 8


def _link_or_copy(source: str, destination: str) -> str:
    """Keep test setup fast while allowing a cross-filesystem temporary directory."""

    try:
        os.link(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(source, destination)
    return destination


def _copy_source_repository(destination: Path) -> Path:
    """Copy the repository inputs without local environments or generated artifacts."""

    ignored = shutil.ignore_patterns(
        ".git",
        ".artifacts",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    )
    return Path(
        shutil.copytree(
            repository_root(),
            destination,
            copy_function=_link_or_copy,
            ignore=ignored,
        )
    )


def test_transition_repository_uses_checksum_pinned_snapshots_without_pdf(
    tmp_path: Path,
) -> None:
    """Transition tests must not regenerate platform-dependent source crops."""

    source = _copy_source_repository(tmp_path / "source")
    (source / SOURCE_DOCUMENT_PATH).unlink()
    slugs = tuple(EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS)

    repository = create_codex_transition_repository(
        source,
        tmp_path / "repository",
        slugs=slugs,
    )

    assert not (repository / SOURCE_DOCUMENT_PATH).exists()
    assert (
        sum(
            1
            for slug in slugs
            for path in (repository / CANONICAL_ASSET_DIRECTORY / slug).glob("*.png")
            if path.is_file()
        )
        == EXPECTED_TRANSITION_ASSET_COUNT
    )
    for slug, expected_checksum in EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS.items():
        assert (
            criterion_source_checksum(
                slug,
                TRANSITION_FIXTURE_DOMAIN_IDENTIFIERS[slug],
                root=repository,
            )
            == expected_checksum
        )


def test_transition_repository_rejects_fixture_drift(tmp_path: Path) -> None:
    """A changed snapshot must fail before pipeline tests use the transition repository."""

    source = _copy_source_repository(tmp_path / "source")
    fixture_path = source / TRANSITION_FIXTURE_DIRECTORY / "criteria" / "unix" / "u-03.md"
    changed_content = fixture_path.read_bytes() + b"\n"
    # The source copy can contain hard links, so replace the entry before changing bytes.
    fixture_path.unlink()
    fixture_path.write_bytes(changed_content)

    with pytest.raises(
        RuntimeError,
        match=r"transition fixture checksum differs for u-03: expected .+, got .+",
    ):
        create_codex_transition_repository(
            source,
            tmp_path / "repository",
            slugs=("u-03",),
        )
