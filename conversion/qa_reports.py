"""Scaffold and validate browser QA reports without executing a browser."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker

from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    canonical_corpus_checksum,
    load_json,
    load_yaml,
    repository_root,
)
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging

REPORT_TYPES = ("accessibility", "responsive", "print")


@dataclass(frozen=True)
class QaReportIssue:
    """One stable QA report validation failure."""

    rule_identifier: str
    location: str
    message: str


def _json_path(parts: list[object]) -> str:
    """Render a JSON Schema error path."""

    if not parts:
        return "$"
    return "$." + ".".join(str(part) for part in parts)


def _qa_context(root: Path) -> tuple[str, int, dict[str, JsonValue]]:
    """Load the checksum, profile version, and QA report schema for a repository."""

    manifest = load_yaml(root / "data/criteria-manifest.yaml")
    manifest_records = [
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
    ]
    test_profile = load_yaml(root / "data/test-profile.yaml")
    profile_version = test_profile.get("profileVersion")
    if not isinstance(profile_version, int) or isinstance(profile_version, bool):
        msg = "data/test-profile.yaml: profileVersion must be an integer"
        raise ValueError(msg)
    return (
        canonical_corpus_checksum(manifest_records, root=root),
        profile_version,
        load_json(root / "schemas/qa-report.schema.json"),
    )


def pending_report(
    *,
    report_type: str,
    canonical_checksum: str,
    profile_version: int,
) -> dict[str, JsonValue]:
    """Build a deterministic pending report that cannot represent a browser pass."""

    if report_type not in REPORT_TYPES:
        msg = f"unsupported QA report type: {report_type}"
        raise ValueError(msg)
    return {
        "schemaVersion": 1,
        "reportType": report_type,
        "canonicalCorpusChecksum": canonical_checksum,
        "testProfileVersion": profile_version,
        "browserEngine": None,
        "browserVersion": None,
        "validationStatus": "pending",
        "passed": False,
        "evidencePaths": [],
    }


def scaffold_reports(*, root: Path, output_directory: Path) -> list[Path]:
    """Write one pending report per browser QA category without overwriting evidence."""

    canonical_checksum, profile_version, schema = _qa_context(root)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output_directory.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    for report_type in REPORT_TYPES:
        output_path = output_directory / f"{report_type}.json"
        if output_path.exists():
            msg = f"refusing to overwrite existing QA report: {output_path}"
            raise FileExistsError(msg)
        report = pending_report(
            report_type=report_type,
            canonical_checksum=canonical_checksum,
            profile_version=profile_version,
        )
        validator.validate(report)
        output_path.write_bytes(rfc8785.dumps(report))
        output_paths.append(output_path)
    return output_paths


def validate_report(  # noqa: C901
    *,
    root: Path,
    report_path: Path,
    expected_report_type: str | None = None,
) -> list[QaReportIssue]:
    """Validate schema, corpus binding, profile binding, outcome, and evidence paths."""

    canonical_checksum, profile_version, schema = _qa_context(root)
    location = (
        report_path.relative_to(root).as_posix()
        if report_path.is_relative_to(root)
        else str(report_path)
    )
    try:
        report = load_json(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [QaReportIssue("qa-report-readable", location, str(error))]

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = [
        QaReportIssue(
            "qa-report-schema",
            f"{location}:{_json_path(list(error.absolute_path))}",
            error.message,
        )
        for error in sorted(validator.iter_errors(report), key=lambda item: list(item.path))
    ]
    report_type = report.get("reportType")
    if expected_report_type is not None and report_type != expected_report_type:
        issues.append(
            QaReportIssue(
                "qa-report-type",
                location,
                f"expected {expected_report_type} report, got {report_type!r}",
            )
        )
    if report.get("canonicalCorpusChecksum") != canonical_checksum:
        issues.append(
            QaReportIssue(
                "qa-report-corpus-binding",
                location,
                "canonical corpus checksum is stale or incorrect",
            )
        )
    if report.get("testProfileVersion") != profile_version:
        issues.append(
            QaReportIssue(
                "qa-report-profile-binding",
                location,
                "test profile version is stale or incorrect",
            )
        )

    validation_status = report.get("validationStatus")
    if validation_status != "passed" or report.get("passed") is not True:
        issues.append(
            QaReportIssue(
                "qa-report-result",
                location,
                f"browser validation has not passed: {validation_status!r}",
            )
        )

    evidence_paths = report.get("evidencePaths")
    if isinstance(evidence_paths, list):
        for evidence_path_value in evidence_paths:
            if not isinstance(evidence_path_value, str):
                continue
            evidence_path = PurePosixPath(evidence_path_value)
            if evidence_path.is_absolute() or ".." in evidence_path.parts:
                issues.append(
                    QaReportIssue(
                        "qa-report-evidence-path",
                        location,
                        f"evidence path must be repository-relative: {evidence_path_value}",
                    )
                )
                continue
            if not (root / Path(*evidence_path.parts)).is_file():
                issues.append(
                    QaReportIssue(
                        "qa-report-evidence-missing",
                        location,
                        f"evidence file does not exist: {evidence_path_value}",
                    )
                )
    return issues


def _argument_parser() -> argparse.ArgumentParser:
    """Build the QA report command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scaffold_parser = subparsers.add_parser("scaffold", help="write pending report templates")
    scaffold_parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("work/qa-reports"),
        help="output directory; existing reports are never overwritten",
    )
    add_logging_arguments(scaffold_parser)
    validate_parser = subparsers.add_parser("validate", help="validate browser QA reports")
    validate_parser.add_argument("report_paths", nargs="*", type=Path)
    add_logging_arguments(validate_parser)
    return parser


def _run(arguments: argparse.Namespace) -> int:
    """Execute the selected QA report operation."""
    root = repository_root()
    if arguments.command == "scaffold":
        output_directory = arguments.output_directory
        if not output_directory.is_absolute():
            output_directory = root / output_directory
        try:
            paths = scaffold_reports(root=root, output_directory=output_directory)
        except (FileExistsError, OSError, ValueError) as error:
            sys.stderr.write(f"{error}\n")
            return 1
        for path in paths:
            sys.stdout.write(f"{path}\n")
        return 0

    report_paths = arguments.report_paths or [
        Path("data/qa-reports") / f"{report_type}.json" for report_type in REPORT_TYPES
    ]
    issues: list[QaReportIssue] = []
    for report_path_argument in report_paths:
        report_path = report_path_argument
        if not report_path.is_absolute():
            report_path = root / report_path
        expected_type = report_path.stem if report_path.stem in REPORT_TYPES else None
        issues.extend(
            validate_report(
                root=root,
                report_path=report_path,
                expected_report_type=expected_type,
            )
        )
    for issue in issues:
        sys.stderr.write(f"{issue.rule_identifier}: {issue.location}: {issue.message}\n")
    if issues:
        return 1
    sys.stdout.write(f"validated {len(report_paths)} browser QA reports\n")
    return 0


def main() -> int:
    """Scaffold pending reports or validate completed browser reports."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "qa_reports",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
    ) as logger:
        logger.info(
            "QA report command started",
            event="command.started",
            command=arguments.command,
        )
        result = _run(arguments)
        log_result = logger.info if result == 0 else logger.error
        log_result(
            "QA report command completed" if result == 0 else "QA report command failed",
            event="command.completed" if result == 0 else "command.failed",
            command=arguments.command,
        )
        return result


if __name__ == "__main__":
    raise SystemExit(main())
