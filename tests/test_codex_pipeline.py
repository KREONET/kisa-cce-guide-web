"""Regression tests for the hybrid code and Codex conversion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from conversion import codex_runner
from conversion.codex_result_importer import render_codex_candidate, validate_codex_result
from conversion.codex_task_builder import build_codex_task, load_codex_task
from conversion.common import JsonValue, as_mapping, as_sequence, repository_root

EXPECTED_U_03_PAGE_COUNT = 4


def _fake_result(task: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Build a schema-valid result that preserves all exported source evidence."""

    evidence_values = as_sequence(task["sourcePageEvidence"], location="task.sourcePageEvidence")
    evidence = [
        as_mapping(value, location="task.sourcePageEvidence[]") for value in evidence_values
    ]
    nodes: list[JsonValue] = [
        {
            "nodeIdentifier": "overview.heading",
            "nodeType": "heading",
            "semanticRole": "overview",
            "content": "개요",
            "headingLevel": 2,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "개요",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "overview.inspection-content.heading",
            "nodeType": "heading",
            "semanticRole": "inspectionContent",
            "content": "점검 내용",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "점검 내용",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "overview.inspection-purpose.heading",
            "nodeType": "heading",
            "semanticRole": "inspectionPurpose",
            "content": "점검 목적",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "점검 목적",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "overview.security-threat.heading",
            "nodeType": "heading",
            "semanticRole": "securityThreat",
            "content": "보안 위협",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "보안 위협",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "overview.reference.heading",
            "nodeType": "heading",
            "semanticRole": "reference",
            "content": "참고",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "참고",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "assessment.heading",
            "nodeType": "heading",
            "semanticRole": "assessment",
            "content": "점검 대상 및 판단 기준",
            "headingLevel": 2,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "점검 대상 및 판단 기준",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "assessment.target.heading",
            "nodeType": "heading",
            "semanticRole": "target",
            "content": "대상",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "대상",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "assessment.judgment.heading",
            "nodeType": "heading",
            "semanticRole": "judgment",
            "content": "판단 기준",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "판단 기준",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "assessment.remediation-method.heading",
            "nodeType": "heading",
            "semanticRole": "remediationMethod",
            "content": "조치 방법",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "조치 방법",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "assessment.remediation-impact.heading",
            "nodeType": "heading",
            "semanticRole": "remediationImpact",
            "content": "조치 시 영향",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "조치 시 영향",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "remediation.heading",
            "nodeType": "heading",
            "semanticRole": "remediation",
            "content": "점검 및 조치 사례",
            "headingLevel": 2,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "점검 및 조치 사례",
                }
            ],
            "publicationDisposition": "published",
        },
        {
            "nodeIdentifier": "remediation.solaris.heading",
            "nodeType": "heading",
            "semanticRole": "targetPlatform",
            "content": "SOLARIS",
            "headingLevel": 3,
            "sourceSpans": [
                {
                    "physicalPage": 21,
                    "pageRegionIdentifier": "p21-u-03",
                    "sourceTextExcerpt": "SOLARIS",
                }
            ],
            "publicationDisposition": "published",
        },
    ]
    for evidence_record in evidence:
        physical_page = cast("int", evidence_record["physicalPage"])
        transcript = cast("str", evidence_record["transcript"])
        nodes.append(
            {
                "nodeIdentifier": f"source.page-{physical_page}",
                "nodeType": "paragraph",
                "semanticRole": "sourceEvidence",
                "content": transcript,
                "sourceSpans": [
                    {
                        "physicalPage": physical_page,
                        "pageRegionIdentifier": evidence_record["pageRegionIdentifier"],
                        "sourceTextExcerpt": transcript.splitlines()[0],
                    }
                ],
                "publicationDisposition": "published",
            }
        )
    optional_node_fields = (
        "headingLevel",
        "listType",
        "listDepth",
        "sourceMarker",
        "codeLanguage",
        "codeContentType",
        "tableCaption",
        "tableHeaders",
        "tableRows",
        "noteType",
        "assetPath",
        "alternativeText",
    )
    for node_value in nodes:
        node = cast("dict[str, JsonValue]", node_value)
        for field_name in optional_node_fields:
            node.setdefault(field_name, None)
    return {
        "schemaVersion": 1,
        "taskIdentifier": task["taskIdentifier"],
        "taskChecksum": task["taskChecksum"],
        "criterionCode": task["criterionCode"],
        "criterionSlug": task["criterionSlug"],
        "sourceDocumentIdentifier": task["sourceDocumentIdentifier"],
        "sourceDocumentChecksum": task["sourceDocumentChecksum"],
        "sourcePageStart": task["sourcePageStart"],
        "sourcePageEnd": task["sourcePageEnd"],
        "analysisStatus": "complete",
        "contentModelRecommendation": "systemCriterion",
        "title": task["criterionTitle"],
        "targetScope": "nonExhaustive",
        "targetIdentifiers": ["unspecified"],
        "sourceTargetText": "SOLARIS, LINUX, AIX, HP-UX 등",
        "nodes": nodes,
        "sourceAnnotations": [],
        "quality": {
            "reviewedPhysicalPages": [
                cast("int", evidence_record["physicalPage"]) for evidence_record in evidence
            ],
            "preservedTechnicalLiterals": task["requiredTechnicalLiterals"],
            "unresolvedQuestions": [],
            "confidenceLevel": "high",
        },
    }


def test_task_builder_exports_deterministic_u_03_evidence(tmp_path: Path) -> None:
    """The task must preserve all U-03 transcripts, images, and exact literals."""

    first_path = build_codex_task("u-03", work_directory=tmp_path)
    first_bytes = first_path.read_bytes()
    second_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(second_path)
    assert second_path.read_bytes() == first_bytes
    evidence = as_sequence(task["sourcePageEvidence"], location="task.sourcePageEvidence")
    assert len(evidence) == EXPECTED_U_03_PAGE_COUNT
    assert [value["physicalPage"] for value in evidence if isinstance(value, dict)] == [
        21,
        22,
        23,
        24,
    ]
    literals = as_sequence(
        task["requiredTechnicalLiterals"],
        location="task.requiredTechnicalLiterals",
    )
    assert "/etc/pam.d/system-auth" in literals
    assert "pam_faillock.so" in literals
    assert "unlock_time" in literals


def test_runner_dry_run_uses_read_only_schema_and_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner plan must be ephemeral, read-only, schema-bound, and multimodal."""

    monkeypatch.setattr(codex_runner.shutil, "which", lambda _name: "/usr/bin/codex")
    run_path = codex_runner.run_codex_task(
        "u-03",
        work_directory=tmp_path,
        model="test-model",
        dry_run=True,
    )
    run_document = json.loads(run_path.read_text(encoding="utf-8"))
    command = run_document["command"]
    assert command[1:3] == ["exec", "--ephemeral"]
    assert "--ignore-user-config" in command
    sandbox_option_index = command.index("--sandbox")
    assert command[sandbox_option_index : sandbox_option_index + 2] == [
        "--sandbox",
        "read-only",
    ]
    assert "--output-schema" in command
    assert command.count("--image") == EXPECTED_U_03_PAGE_COUNT
    model_option_index = command.index("--model")
    assert command[model_option_index : model_option_index + 2] == ["--model", "test-model"]
    assert command[-1] == "-"


def test_importer_validates_and_renders_review_candidate(tmp_path: Path) -> None:
    """A valid Codex result must render only into the ignored review workspace."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result_path = tmp_path / "results" / "u-03" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(_fake_result(task), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validated = validate_codex_result(result_path, task_path)
    assert validated["analysisStatus"] == "complete"
    candidate_path = render_codex_candidate(
        result_path,
        task_path,
        work_directory=tmp_path,
    )
    candidate = candidate_path.read_text(encoding="utf-8")
    assert "# U-03 계정 잠금 임계값 설정" in candidate
    assert "Canonical 콘텐츠나 사람 승인 상태가 아닙니다" in candidate
    assert (candidate_path.parent / "validation.json").is_file()
    canonical_path = repository_root() / "unix" / "u-03.md"
    assert canonical_path.read_text(encoding="utf-8").startswith("---\nschemaVersion: 1")


def test_importer_rejects_missing_technical_literal(tmp_path: Path) -> None:
    """A result that drops one required literal must fail before candidate rendering."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    quality = as_mapping(result["quality"], location="result.quality")
    preserved = as_sequence(
        quality["preservedTechnicalLiterals"],
        location="result.quality.preservedTechnicalLiterals",
    )
    quality["preservedTechnicalLiterals"] = preserved[1:]
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="did not preserve every required technical literal"):
        validate_codex_result(result_path, task_path)
