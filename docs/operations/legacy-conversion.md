# Legacy structured-JSON 변환 워크플로

이 문서는 schema version 2 node JSON을 거쳐 review Markdown을 렌더링하는 기존 migration 경로를 설명한다. 신규 변환은 [Codex-native 워크플로](conversion-workflows.md)를 사용한다. Legacy 경로는 기존 `.artifacts/work/codex/` artifact 재검증과 점진적 이전에만 사용한다.

## 경계

```text
PDF evidence
  -> deterministic task builder
  -> Codex read-only structured output
  -> deterministic importer validation
  -> review-only Markdown candidate
```

- 모든 관련 PDF page image를 task에 첨부하고 vision으로 검사한다.
- Transcript는 페이지 탐색용 navigation aid이며 판정 근거가 아니다.
- 제목, 문단, 목록, note, code와 table을 typed node로 변환한다.
- Source span과 uncertainty를 보존하며, 구조가 불확실하면 추정하지 않는다.
- Importer는 page coverage, source excerpt, technical literal, heading hierarchy와 annotation target을 검증한다.
- 결과는 review-only artifact이며 canonical 콘텐츠나 review registry를 자동으로 변경하지 않는다.

## 단일 항목

```bash
uv run python -m conversion.codex_task_builder <criterion-slug>
uv run python -m conversion.codex_runner <criterion-slug> \
  --model <model-identifier>
uv run python -m conversion.codex_result_importer <criterion-slug>
```

OpenCodeX를 사용할 때는 사용자 설정과 namespaced model identifier를 명시한다.

```bash
ocx start
uv run python -m conversion.codex_runner <criterion-slug> \
  --use-user-config \
  --model <provider>/<model-identifier>
```

## 전체 corpus

```bash
uv run python -m conversion.codex_bulk_runner --dry-run
uv run python -m conversion.codex_bulk_runner \
  --model <model-identifier>
uv run python -m conversion.codex_bulk_runner \
  --model <model-identifier> \
  --resume
```

현재 canonical corpus에는 `extractedCriterion`이 없다. 전체 실행은 향후 migration 입력이 생긴 경우에만 대상이 있다.

## Stage와 artifact

| Stage | 경로 | 역할 |
| --- | --- | --- |
| `taskBuild` | `.artifacts/work/codex/tasks/<criterionSlug>/task.json` | 원문, 정책, prompt와 schema checksum에 결합된 immutable task |
| `visionRun` | `.artifacts/work/codex/results/<criterionSlug>/` | Page image를 첨부한 Codex 분석과 structured result |
| `importer` | `.artifacts/work/codex/candidates/<criterionSlug>/` | 검증 report와 review-only candidate |
| summary | `.artifacts/work/codex/bulk-summary.json` | Manifest 순서의 단계 상태와 outcome |

## 주요 옵션

| 옵션 | 동작 |
| --- | --- |
| `<slug>...` | 선택적인 allowlist. Manifest 순서로 실행 |
| `--workers <1-16>` | 병렬 worker 수 지정 |
| `--model <identifier>` | 모든 vision run의 model 고정 |
| `--use-user-config` | 사용자 provider와 실행 설정 로드 |
| `--dry-run` | Task와 계획만 기록하고 importer 생략 |
| `--resume` | 현재 checksum으로 검증된 artifact 재사용 |
| `--fail-fast` | 첫 실패 뒤 새 scheduling 중단 |
| `--retries <0-5>` | Vision run 재시도 횟수 |
| `--retry-backoff-seconds <0-300>` | Deterministic backoff base |
| `--work-directory <path>` | 기본 `.artifacts/work/codex/` 대신 사용할 artifact root |
| `--summary-path <path>` | 기본 summary 대신 사용할 JSON 경로 |

Rate limit, context 또는 memory 압박이 발생하면 `--workers 1`과 `--resume`을 사용한다. Summary는 `schemas/codex-bulk-summary.schema.json`으로 검증한 뒤 원자적으로 교체하며, 실패나 취소가 있으면 non-zero exit code를 반환한다.
