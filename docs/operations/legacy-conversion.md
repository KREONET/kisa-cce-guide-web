# Legacy structured-JSON 변환 워크플로

기존 변환 경로는 스키마 버전 2의 노드 JSON을 거쳐 검토용 Markdown을 렌더링한다. 이 경로는 `.artifacts/work/codex/`에 남아 있는 산출물의 재검증과 점진적 이전에만 사용한다. 신규 변환은 [Codex-native 워크플로](conversion-workflows.md)를 따른다.

## 경계

```text
PDF evidence
  -> deterministic task builder
  -> Codex read-only structured output
  -> deterministic importer validation
  -> review-only Markdown candidate
```

- 관련 PDF 페이지 이미지를 모두 작업에 첨부하고 비전으로 검사한다.
- 전사문은 페이지를 찾는 보조 자료로만 사용하며 판정 근거로 삼지 않는다.
- 제목, 문단, 목록, 참고, 코드와 표를 각각 유형이 지정된 노드로 변환한다.
- 원문 범위와 불확실성을 보존한다. 구조가 불확실하면 추정하지 않는다.
- Importer는 페이지 반영 범위, 원문 발췌, 기술 리터럴, 제목 계층과 주석 대상을 검증한다.
- 결과는 검토용 산출물이며 정본 콘텐츠나 검토 레지스트리를 자동으로 변경하지 않는다.

## 단일 항목

```bash
uv run python -m conversion.codex_task_builder <criterion-slug>
uv run python -m conversion.codex_runner <criterion-slug> \
  --model <model-identifier>
uv run python -m conversion.codex_result_importer <criterion-slug>
```

OpenCodeX를 사용할 때는 사용자 설정과 제공자 네임스페이스가 포함된 모델 식별자를 명시한다.

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

현재 정본 콘텐츠에는 `extractedCriterion`이 없다. 향후 이전할 입력을 준비해야 전체 실행으로 처리할 대상이 생긴다.

## Stage와 artifact

| 단계 | 경로 | 역할 |
| --- | --- | --- |
| `taskBuild` | `.artifacts/work/codex/tasks/<criterionSlug>/task.json` | 원문, 정책, 프롬프트와 스키마의 체크섬에 연결된 변경 불가 작업 정의 |
| `visionRun` | `.artifacts/work/codex/results/<criterionSlug>/` | 페이지 이미지를 첨부한 Codex 분석과 구조화된 결과 |
| `importer` | `.artifacts/work/codex/candidates/<criterionSlug>/` | 검증 보고서와 검토용 후보 |
| summary | `.artifacts/work/codex/bulk-summary.json` | 매니페스트 순서로 정렬한 단계별 상태와 결과 |

## 주요 옵션

| 옵션 | 동작 |
| --- | --- |
| `<slug>...` | 선택적으로 처리 대상을 제한하며 매니페스트 순서로 실행 |
| `--workers <1-16>` | 병렬 작업자 수 지정 |
| `--model <identifier>` | 모든 비전 실행에 사용할 모델 고정 |
| `--use-user-config` | 사용자 지정 제공자와 실행 설정 로드 |
| `--dry-run` | 작업 정의와 계획만 기록하고 importer 생략 |
| `--resume` | 현재 체크섬으로 검증된 산출물 재사용 |
| `--fail-fast` | 첫 실패 뒤 새 작업 배정 중단 |
| `--retries <0-5>` | 비전 실행 재시도 횟수 |
| `--retry-backoff-seconds <0-300>` | 결정적 재시도 대기 시간의 기준값 |
| `--work-directory <path>` | 기본 `.artifacts/work/codex/` 대신 사용할 산출물 루트 |
| `--summary-path <path>` | 기본 요약 파일 대신 사용할 JSON 경로 |

요청 한도에 걸리거나 컨텍스트 또는 메모리가 부족하면 `--workers 1`과 `--resume`을 사용한다. 요약 파일은 `schemas/codex-bulk-summary.schema.json`으로 검증한 뒤 원자적으로 교체한다. 실패나 취소가 있으면 0이 아닌 종료 코드를 반환한다.
