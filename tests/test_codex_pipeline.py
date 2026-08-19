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
EXPECTED_CODEX_SCHEMA_VERSION = 2


def _fake_result(task: dict[str, JsonValue]) -> dict[str, JsonValue]:  # noqa: C901
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
            "sourceMarker": "1.",
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
    evidence_by_page = {
        cast("int", evidence_record["physicalPage"]): evidence_record
        for evidence_record in evidence
    }

    def source_span(physical_page: int, excerpt: str) -> dict[str, JsonValue]:
        """Build clear page-image provenance for one fixture node."""

        return {
            "physicalPage": physical_page,
            "pageRegionIdentifier": evidence_by_page[physical_page]["pageRegionIdentifier"],
            "sourceTextExcerpt": excerpt,
            "evidenceOrigin": "pageImage",
            "transcriptAlignment": "exact",
            "recognitionStatus": "clear",
            "uncertaintyDescription": None,
        }

    nodes.extend(
        [
            {
                "nodeIdentifier": "assessment.target.matrix",
                "nodeType": "table",
                "sourceContentType": "pageText",
                "semanticRole": "targetMatrix",
                "content": "",
                "tableCaption": "점검 대상",
                "tableHeaders": ["대상"],
                "tableRows": [["SOLARIS, LINUX, AIX, HP-UX 등"]],
                "sourceSpans": [source_span(21, "대상 SOLARIS, LINUX, AIX, HP-UX 등")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.solaris.step-1",
                "nodeType": "listItem",
                "sourceContentType": "pageText",
                "semanticRole": "step",
                "content": (
                    "`/etc/default/login` 파일의 `RETRIES` 값과 "
                    "`/etc/security/policy.conf` 파일의 `LOCK_AFTER_RETRIES` 값을 수정"
                ),
                "listType": "ordered",
                "listDepth": 1,
                "sourceMarker": "Step 1)",
                "sourceSpans": [
                    source_span(21, "Step 1) /etc/default/login 파일에 RETRIES 값 수정")
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.solaris.configuration",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "configuration",
                "content": "RETRIES=10",
                "codeLanguage": "ini",
                "codeContentType": "configuration",
                "sourceSpans": [source_span(21, "RETRIES=10")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.linux.step-1",
                "nodeType": "listItem",
                "sourceContentType": "pageText",
                "semanticRole": "step",
                "content": (
                    "`/etc/pam.d/system-auth`와 `etc/securiy/faillock.conf`의 정책 값을 수정"
                ),
                "listType": "ordered",
                "listDepth": 1,
                "sourceMarker": "Step 1)",
                "sourceSpans": [
                    source_span(22, "Step 1) /etc/pam.d/system-auth 파일에 deny 값 수정")
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.linux.command",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "command",
                "content": "# authselect enable-feature with-faillock\n# authselect current",
                "codeLanguage": "shell",
                "codeContentType": "command",
                "sourceSpans": [source_span(22, "# authselect current")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.linux.output",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "output",
                "content": (
                    "Profile ID: sssd\nEnabled features:\n- with-fingerprint\n"
                    "- with-silent-lastlog\n- with-faillock"
                ),
                "codeLanguage": "text",
                "codeContentType": "output",
                "sourceSpans": [source_span(22, "Profile ID: sssd")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.linux.configuration",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "configuration",
                "content": (
                    "LOCK_AFTER_RETRIES=YES\nUNLOCK_AFTER =2m\n"
                    "auth required /lib/security/pam_tally.so 또는 "
                    "/lib/security/pam_tally2.so deny=10 unlock_time=120 no_magic_root\n"
                    "account required /lib/security/pam_tally.so 또는 "
                    "/lib/security/pam_tally2.so no_magic_root reset\n"
                    "silent\ndeny = 10\nunlock_time = 120"
                ),
                "codeLanguage": "text",
                "codeContentType": "configuration",
                "sourceSpans": [source_span(22, "LOCK_AFTER_RETRIES=YES")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.linux.options",
                "nodeType": "table",
                "sourceContentType": "pageText",
                "semanticRole": "optionTable",
                "content": "",
                "tableCaption": "옵션 설명",
                "tableHeaders": ["옵션", "설명"],
                "tableRows": [
                    ["RETRIES", "로그인 시도 횟수"],
                    ["LOCK_AFTER_RETRIES", "로그인 시도 횟수와 같거나 초과되면 잠금"],
                    ["UNLOCK_AFTER", "잠금시간"],
                ],
                "sourceSpans": [source_span(22, "옵션 설명")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.debian.step-1",
                "nodeType": "listItem",
                "sourceContentType": "pageText",
                "semanticRole": "step",
                "content": (
                    "`/etc/pam.d/password-auth`, `/etc/pam.d/common-auth`, "
                    "`/etc/pam.d/common-account`, `etc/pam.d/common-account` 파일의 모듈 값을 수정"
                ),
                "listType": "ordered",
                "listDepth": 1,
                "sourceMarker": "Step 1)",
                "sourceSpans": [
                    source_span(
                        23,
                        "Step 1) /etc/pam.d/common-auth 파일에 모듈 값 수정",
                    )
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.debian.configuration",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "configuration",
                "content": (
                    "auth required pam_faillock.so preauth silent audit deny=10 unlock_time=120\n"
                    "auth required /lib/security/pam_tally.so 또는 "
                    "/lib/security/pam_tally2.so deny=10 unlock_time=120\n"
                    "no_magic_root\nreset"
                ),
                "codeLanguage": "text",
                "codeContentType": "configuration",
                "sourceSpans": [
                    source_span(
                        23,
                        "auth required pam_faillock.so preauth silent audit "
                        "deny=10 unlock_time=120",
                    )
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.debian.reference",
                "nodeType": "note",
                "sourceContentType": "pageText",
                "semanticRole": "reference",
                "content": "RHEL 8 이상부터 authselect 명령어 사용을 권장함",
                "noteType": "참고",
                "sourceSpans": [
                    source_span(
                        23,
                        "RHEL 8 이상부터 authselect 명령어를 이용하여 설정하는 것을 권장함",
                    )
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.aix-hpux.step-1",
                "nodeType": "listItem",
                "sourceContentType": "pageText",
                "semanticRole": "step",
                "content": (
                    "`/etc/security/user`, `/tcb/files/auth/system/default`, "
                    "`/etc/default/security` 파일의 값을 수정"
                ),
                "listType": "ordered",
                "listDepth": 1,
                "sourceMarker": "Step 1)",
                "sourceSpans": [
                    source_span(
                        24,
                        "Step 1) /etc/security/user 파일에 loginretries 값 수정",
                    )
                ],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.aix-hpux.configuration",
                "nodeType": "codeBlock",
                "sourceContentType": "pageText",
                "semanticRole": "configuration",
                "content": "loginretries = 3\nu_maxtries#3\nAUTH_MAXTRIES=3",
                "codeLanguage": "text",
                "codeContentType": "configuration",
                "sourceSpans": [source_span(24, "loginretries = 3")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.aix-hpux.options",
                "nodeType": "table",
                "sourceContentType": "pageText",
                "semanticRole": "optionTable",
                "content": "",
                "tableCaption": "옵션 설명",
                "tableHeaders": ["옵션", "설명"],
                "tableRows": [
                    ["no_magic_root", "root 계정은 잠금 설정을 적용하지 않음"],
                    ["deny=N", "N회 입력 실패 시 계정 잠금"],
                    ["unlock_time", "설정된 시간 뒤 잠금 해제"],
                    ["reset", "접속 성공 시 실패 횟수 초기화"],
                ],
                "sourceSpans": [source_span(24, "옵션 설명")],
                "publicationDisposition": "published",
            },
            {
                "nodeIdentifier": "remediation.pam.warning",
                "nodeType": "note",
                "sourceContentType": "pageText",
                "semanticRole": "warning",
                "content": "PAM 모듈과 `/etc/pam.d/*` 파일 경로를 확인해야 함",
                "noteType": "주의",
                "sourceSpans": [source_span(24, "※ /etc/pam.d/* 파일 수정 시")],
                "publicationDisposition": "published",
            },
        ]
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
        node.setdefault("sourceContentType", "pageText")
        for field_name in optional_node_fields:
            node.setdefault(field_name, None)
        for span_value in as_sequence(node["sourceSpans"], location="node.sourceSpans"):
            span = as_mapping(span_value, location="node.sourceSpans[]")
            span.setdefault("evidenceOrigin", "pageImage")
            span.setdefault("transcriptAlignment", "exact")
            span.setdefault("recognitionStatus", "clear")
            span.setdefault("uncertaintyDescription", None)

    def observed_types(node: dict[str, JsonValue]) -> set[str]:
        """Return the inspection content types represented by a fixture node."""

        node_type = node["nodeType"]
        if node_type == "heading":
            values = {"heading"}
        elif node_type == "listItem":
            values = {"procedure"}
        elif node_type == "codeBlock":
            values = {cast("str", node["codeContentType"])}
        elif node_type == "table":
            values = {"table"}
        elif node_type == "image":
            values = {"meaningfulVisual"}
        else:
            values = {"prose"}
        if node["sourceContentType"] == "embeddedImageText":
            values.add("embeddedImageText")
        return values

    source_page_inspections: list[JsonValue] = []
    for evidence_record in evidence:
        physical_page = cast("int", evidence_record["physicalPage"])
        page_nodes = [
            cast("dict[str, JsonValue]", node_value)
            for node_value in nodes
            if physical_page
            in {
                cast("int", span["physicalPage"])
                for span in as_sequence(
                    cast("dict[str, JsonValue]", node_value)["sourceSpans"],
                    location="node.sourceSpans",
                )
                if isinstance(span, dict)
            }
        ]
        content_types: set[str] = set()
        for node in page_nodes:
            content_types.update(observed_types(node))
        inspection: dict[str, JsonValue] = {
            "physicalPage": physical_page,
            "pageRegionIdentifier": evidence_record["pageRegionIdentifier"],
            "imagePath": evidence_record["imagePath"],
            "imageChecksum": evidence_record["imageChecksum"],
            "inspectionStatus": "visionInspected",
            "transcriptRole": "navigationAid",
            "observedContentTypes": cast("list[JsonValue]", sorted(content_types)),
            "observedNodeIdentifiers": [node["nodeIdentifier"] for node in page_nodes],
            "uncertaintyDescription": None,
        }
        source_page_inspections.append(inspection)
    return {
        "schemaVersion": 2,
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
        "sourcePageInspections": source_page_inspections,
        "nodes": nodes,
        "sourceAnnotations": [],
        "quality": {
            "reviewedPhysicalPages": [
                cast("int", evidence_record["physicalPage"]) for evidence_record in evidence
            ],
            "preservedTechnicalLiterals": task["requiredTechnicalLiterals"],
            "unresolvedQuestions": [],
            "semanticCoverageStatus": "complete",
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
    assert task["schemaVersion"] == EXPECTED_CODEX_SCHEMA_VERSION
    assert task["promptVersion"] == EXPECTED_CODEX_SCHEMA_VERSION
    assert task["taskIdentifier"] == "u-03-codex-structure-v2"
    evidence_contract = as_mapping(task["evidenceContract"], location="task.evidenceContract")
    assert evidence_contract == {
        "provenanceMustBePreserved": True,
        "transcriptOnlyResultAllowed": False,
        "transcriptRole": "navigationAid",
        "typedSemanticNodesRequired": True,
        "uncertaintyMustBePreserved": True,
        "visionInspectionRequired": True,
        "visualAuthority": "sourcePageImages",
    }
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


def test_importer_accepts_visual_text_absent_from_navigation_transcript(
    tmp_path: Path,
) -> None:
    """Page-image OCR provenance must not require transcript substring membership."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    nodes = as_sequence(result["nodes"], location="result.nodes")
    node = as_mapping(nodes[0], location="result.nodes[0]")
    span = as_mapping(
        as_sequence(node["sourceSpans"], location="node.sourceSpans")[0],
        location="node.sourceSpans[0]",
    )
    span["sourceTextExcerpt"] = "이미지에서만 판독된 제목"
    span["transcriptAlignment"] = "notPresent"
    result_path = tmp_path / "visual-only-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert validate_codex_result(result_path, task_path)["analysisStatus"] == "complete"


def test_importer_rejects_missing_page_image_inspection(tmp_path: Path) -> None:
    """Every immutable source image must have one checksum-bound vision inspection."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    inspections = as_sequence(
        result["sourcePageInspections"],
        location="result.sourcePageInspections",
    )
    result["sourcePageInspections"] = inspections[:-1]
    result_path = tmp_path / "missing-inspection-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="one vision inspection for every source page image"):
        validate_codex_result(result_path, task_path)


def test_importer_rejects_plain_transcript_catch_all(tmp_path: Path) -> None:
    """A transcript catch-all cannot masquerade as visually structured content."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    node = as_mapping(
        as_sequence(result["nodes"], location="result.nodes")[-1],
        location="result.nodes[-1]",
    )
    node["semanticRole"] = "sourceEvidence"
    result_path = tmp_path / "transcript-catch-all-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden transcript catch-all role"):
        validate_codex_result(result_path, task_path)


def test_importer_rejects_configuration_flattened_into_paragraph(tmp_path: Path) -> None:
    """Configuration-shaped source text must remain a typed code block."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    nodes = [
        as_mapping(value, location="result.nodes[]")
        for value in as_sequence(result["nodes"], location="result.nodes")
    ]
    node = next(
        value for value in nodes if value["nodeIdentifier"] == "remediation.solaris.configuration"
    )
    node["nodeType"] = "paragraph"
    node["codeLanguage"] = None
    node["codeContentType"] = None
    result_path = tmp_path / "flattened-configuration-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires codeBlock"):
        validate_codex_result(result_path, task_path)


def test_importer_rejects_non_rectangular_semantic_table(tmp_path: Path) -> None:
    """Visual table content must retain a rectangular semantic table shape."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    nodes = [
        as_mapping(value, location="result.nodes[]")
        for value in as_sequence(result["nodes"], location="result.nodes")
    ]
    node = next(value for value in nodes if value["nodeIdentifier"] == "remediation.linux.options")
    table_rows = as_sequence(node["tableRows"], location="node.tableRows")
    table_rows[0] = ["RETRIES"]
    result_path = tmp_path / "non-rectangular-table-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="same column count"):
        validate_codex_result(result_path, task_path)


def test_importer_rejects_unreported_ocr_uncertainty(tmp_path: Path) -> None:
    """Uncertain OCR must propagate to page, coverage, and review status."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    node = as_mapping(
        as_sequence(result["nodes"], location="result.nodes")[0],
        location="result.nodes[0]",
    )
    span = as_mapping(
        as_sequence(node["sourceSpans"], location="node.sourceSpans")[0],
        location="node.sourceSpans[0]",
    )
    span["recognitionStatus"] = "uncertain"
    span["uncertaintyDescription"] = "The final glyph is visually ambiguous."
    result_path = tmp_path / "unreported-uncertainty-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="need uncertain vision inspections"):
        validate_codex_result(result_path, task_path)


def test_importer_accepts_explicit_ocr_uncertainty(tmp_path: Path) -> None:
    """Explicit OCR uncertainty must remain reviewable without guessing source text."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    node = as_mapping(
        as_sequence(result["nodes"], location="result.nodes")[0],
        location="result.nodes[0]",
    )
    span = as_mapping(
        as_sequence(node["sourceSpans"], location="node.sourceSpans")[0],
        location="node.sourceSpans[0]",
    )
    span["recognitionStatus"] = "uncertain"
    span["uncertaintyDescription"] = "The final glyph is visually ambiguous."
    inspection = as_mapping(
        as_sequence(
            result["sourcePageInspections"],
            location="result.sourcePageInspections",
        )[0],
        location="result.sourcePageInspections[0]",
    )
    inspection["inspectionStatus"] = "visionInspectedWithUncertainty"
    inspection["uncertaintyDescription"] = "The page contains one ambiguous glyph."
    result["analysisStatus"] = "needsSourceReview"
    quality = as_mapping(result["quality"], location="result.quality")
    quality["unresolvedQuestions"] = ["Confirm the ambiguous glyph on physical page 21."]
    quality["semanticCoverageStatus"] = "completeWithUncertainty"
    quality["confidenceLevel"] = "medium"
    result_path = tmp_path / "explicit-uncertainty-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert validate_codex_result(result_path, task_path)["analysisStatus"] == "needsSourceReview"


def test_importer_rejects_embedded_image_text_without_embedded_provenance(
    tmp_path: Path,
) -> None:
    """Embedded-image OCR text must be a typed node with matching visual provenance."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    nodes = [
        as_mapping(value, location="result.nodes[]")
        for value in as_sequence(result["nodes"], location="result.nodes")
    ]
    node = next(value for value in nodes if value["nodeIdentifier"] == "remediation.pam.warning")
    node["sourceContentType"] = "embeddedImageText"
    result_path = tmp_path / "embedded-image-provenance-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lacks embedded-image provenance"):
        validate_codex_result(result_path, task_path)


def test_importer_keeps_clear_source_anomaly_separate_from_vision_uncertainty(
    tmp_path: Path,
) -> None:
    """A clearly read source typo must require review without claiming OCR uncertainty."""

    task_path = build_codex_task("u-03", work_directory=tmp_path)
    task = load_codex_task(task_path)
    result = _fake_result(task)
    result["analysisStatus"] = "needsSourceReview"
    result["sourceAnnotations"] = [
        {
            "annotationIdentifier": "u-03-source-001",
            "annotationType": "sourceTypo",
            "targetReference": "remediation.linux.step-1",
            "physicalPages": [22],
            "sourceText": "etc/securiy/faillock.conf",
            "explanation": "The visibly preserved source spelling requires human review.",
            "disposition": "reviewRequired",
        }
    ]
    quality = as_mapping(result["quality"], location="result.quality")
    quality["semanticCoverageStatus"] = "completeWithUncertainty"
    quality["confidenceLevel"] = "medium"
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    validated = validate_codex_result(result_path, task_path)
    inspections = as_sequence(
        validated["sourcePageInspections"],
        location="result.sourcePageInspections",
    )
    assert all(
        isinstance(inspection, dict) and inspection["inspectionStatus"] == "visionInspected"
        for inspection in inspections
    )
