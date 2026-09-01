"""Regression tests for the non-publishing GitHub Pages build workflow."""

from __future__ import annotations

from conversion.common import as_mapping, as_sequence, load_yaml, repository_root


def test_github_pages_workflow_builds_without_public_deployment() -> None:
    """The workflow must create a review artifact without Pages write access."""

    workflow_path = repository_root() / ".github" / "workflows" / "pages-build.yaml"
    workflow = load_yaml(workflow_path)
    permissions = as_mapping(workflow["permissions"], location="workflow.permissions")
    assert permissions == {"contents": "read"}
    jobs = as_mapping(workflow["jobs"], location="workflow.jobs")
    assert set(jobs) == {"build"}
    build_job = as_mapping(jobs["build"], location="workflow.jobs.build")
    step_values = as_sequence(build_job["steps"], location="workflow.jobs.build.steps")
    steps = [as_mapping(value, location="workflow.jobs.build.steps[]") for value in step_values]
    action_identifiers = {
        action_identifier
        for step in steps
        if isinstance((action_identifier := step.get("uses")), str)
    }
    assert "actions/checkout@v6" in action_identifiers
    assert "actions/upload-artifact@v5" in action_identifiers
    assert not any("deploy-pages" in identifier for identifier in action_identifiers)
    build_step = next(step for step in steps if step.get("name") == "Build GitHub Pages artifact")
    build_command = build_step.get("run")
    assert isinstance(build_command, str)
    assert "--base-path" in build_command
    assert "inputs.base_path" in build_command
    upload_step = next(step for step in steps if step.get("name") == "Upload GitHub Pages artifact")
    assert upload_step.get("with") == {
        "path": ".artifacts/build/site",
        "include-hidden-files": True,
    }
