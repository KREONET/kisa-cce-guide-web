"""Tests for deterministic browser QA report scaffolding and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from conversion import qa_reports
from conversion.common import load_json, repository_root
from conversion.paths import WORK_DIRECTORY
from conversion.qa_reports import REPORT_TYPES, scaffold_reports, validate_report


def test_scaffold_reports_are_deterministic_pending_documents(tmp_path: Path) -> None:
    """Scaffolding binds current inputs without claiming browser execution."""

    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_paths = scaffold_reports(root=repository_root(), output_directory=first_directory)
    second_paths = scaffold_reports(root=repository_root(), output_directory=second_directory)

    assert [path.name for path in first_paths] == [f"{value}.json" for value in REPORT_TYPES]
    assert [path.read_bytes() for path in first_paths] == [
        path.read_bytes() for path in second_paths
    ]
    schema = load_json(repository_root() / "schemas/qa-report.schema.json")
    validator = Draft202012Validator(schema)
    for path in first_paths:
        report = json.loads(path.read_bytes())
        validator.validate(report)
        assert report["validationStatus"] == "pending"
        assert report["passed"] is False
        assert report["browserEngine"] is None
        assert report["browserVersion"] is None
        assert report["evidencePaths"] == []
        assert {
            issue.rule_identifier
            for issue in validate_report(
                root=repository_root(),
                report_path=path,
                expected_report_type=path.stem,
            )
        } == {"qa-report-result"}


def test_scaffold_parser_uses_the_shared_work_directory() -> None:
    """Pending browser reports must default to the consolidated artifact root."""

    arguments = qa_reports._argument_parser().parse_args(["scaffold"])  # noqa: SLF001

    assert arguments.output_directory == WORK_DIRECTORY / "qa-reports"


def test_scaffold_refuses_to_overwrite_existing_report(tmp_path: Path) -> None:
    """Regeneration cannot destroy browser evidence or a previous pending report."""

    scaffold_reports(root=repository_root(), output_directory=tmp_path)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        scaffold_reports(root=repository_root(), output_directory=tmp_path)


def test_validator_rejects_stale_binding_and_missing_evidence(tmp_path: Path) -> None:
    """A pass claim requires current bindings and repository evidence."""

    report_path = tmp_path / "accessibility.json"
    report_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "reportType": "accessibility",
                "canonicalCorpusChecksum": "0" * 64,
                "testProfileVersion": 999,
                "browserEngine": "chromium",
                "browserVersion": "1",
                "validationStatus": "passed",
                "passed": True,
                "evidencePaths": ["data/qa-evidence/missing.json"],
            }
        ),
        encoding="utf-8",
    )

    rule_identifiers = {
        issue.rule_identifier
        for issue in validate_report(
            root=repository_root(),
            report_path=report_path,
            expected_report_type="accessibility",
        )
    }

    assert rule_identifiers == {
        "qa-report-corpus-binding",
        "qa-report-profile-binding",
        "qa-report-evidence-missing",
    }


def test_schema_rejects_inconsistent_pending_and_passed_states() -> None:
    """The schema prevents a pending scaffold from being labeled as passed."""

    schema = load_json(repository_root() / "schemas/qa-report.schema.json")
    validator = Draft202012Validator(schema)
    pending_report = {
        "schemaVersion": 1,
        "reportType": "print",
        "canonicalCorpusChecksum": "0" * 64,
        "testProfileVersion": 1,
        "browserEngine": None,
        "browserVersion": None,
        "validationStatus": "pending",
        "passed": True,
        "evidencePaths": [],
    }
    passed_without_evidence = {
        **pending_report,
        "browserEngine": "chromium",
        "browserVersion": "1",
        "validationStatus": "passed",
    }

    assert list(validator.iter_errors(pending_report))
    assert list(validator.iter_errors(passed_without_evidence))
