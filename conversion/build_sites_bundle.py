"""Build the static guide into the deployment layout required by Sites."""

from __future__ import annotations

import shutil
from pathlib import Path

from conversion.build_content import build
from conversion.common import repository_root


def build_sites_bundle(*, root: Path | None = None) -> list[Path]:
    """Build and stage the validated static site and Worker entry point."""

    repository = root or repository_root()
    build(root=repository)
    distribution_directory = repository / "dist"
    shutil.rmtree(distribution_directory, ignore_errors=True)
    client_directory = distribution_directory / "client"
    server_directory = distribution_directory / "server"
    shutil.copytree(repository / "build" / "site", client_directory)
    server_directory.mkdir(parents=True)
    worker_source = repository / "site_hosting" / "worker.js"
    worker_target = server_directory / "index.js"
    shutil.copy2(worker_source, worker_target)
    return [
        worker_target,
        *sorted(path for path in client_directory.rglob("*") if path.is_file()),
    ]


def main() -> int:
    """Build the Sites deployment bundle."""

    generated_paths = build_sites_bundle()
    print(f"generated {len(generated_paths)} Sites deployment artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
