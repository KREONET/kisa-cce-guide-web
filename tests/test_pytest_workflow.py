"""Regression tests for the pytest GitHub Actions workflow."""

from __future__ import annotations

from conversion.common import as_mapping, as_sequence, load_yaml, repository_root

SETUP_UV_ACTION = "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d"
PYTEST_TIMEOUT_MINUTES = 15


def test_pytest_workflow_runs_the_locked_full_suite() -> None:
    """Pull requests, main pushes, and manual runs must execute the locked pytest suite."""

    workflow_path = repository_root() / ".github" / "workflows" / "pytest.yml"
    workflow = load_yaml(workflow_path)
    triggers = as_mapping(workflow["on"], location="workflow.on")
    assert set(triggers) == {"pull_request", "push", "workflow_dispatch"}
    assert triggers["pull_request"] is None
    assert triggers["workflow_dispatch"] is None
    push_trigger = as_mapping(triggers["push"], location="workflow.on.push")
    assert push_trigger == {"branches": ["main"]}
    assert as_mapping(workflow["permissions"], location="workflow.permissions") == {
        "contents": "read"
    }
    assert as_mapping(workflow["concurrency"], location="workflow.concurrency") == {
        "group": "pytest-${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": True,
    }

    jobs = as_mapping(workflow["jobs"], location="workflow.jobs")
    assert set(jobs) == {"pytest"}
    pytest_job = as_mapping(jobs["pytest"], location="workflow.jobs.pytest")
    assert pytest_job["runs-on"] == "ubuntu-latest"
    assert pytest_job["timeout-minutes"] == PYTEST_TIMEOUT_MINUTES
    assert "permissions" not in pytest_job
    step_values = as_sequence(pytest_job["steps"], location="workflow.jobs.pytest.steps")
    steps = [as_mapping(value, location="workflow.jobs.pytest.steps[]") for value in step_values]
    assert [step.get("name") for step in steps] == [
        "Checkout repository",
        "Install uv and Python",
        "Verify lockfile",
        "Install development dependencies",
        "Run pytest",
    ]

    checkout_step = next(step for step in steps if step.get("name") == "Checkout repository")
    assert checkout_step.get("uses") == "actions/checkout@v6"
    setup_step = next(step for step in steps if step.get("name") == "Install uv and Python")
    assert setup_step.get("uses") == SETUP_UV_ACTION
    assert setup_step.get("with") == {
        "enable-cache": True,
        "cache-dependency-glob": "uv.lock",
        "python-version": "3.13",
    }
    assert next(step for step in steps if step.get("name") == "Verify lockfile").get("run") == (
        "uv lock --check"
    )
    assert (
        next(step for step in steps if step.get("name") == "Install development dependencies").get(
            "run"
        )
        == "uv sync --dev --locked"
    )
    assert next(step for step in steps if step.get("name") == "Run pytest").get("run") == (
        "uv run --locked pytest -q"
    )
