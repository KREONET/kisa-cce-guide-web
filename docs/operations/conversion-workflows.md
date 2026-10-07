# 변환 워크플로

정본 점검항목 콘텐츠를 생성하고 Codex-native 변환으로 검토 후보를 만드는 절차를 다룬다. 콘텐츠 형식과 승인 조건은 [문서 변환 정책](../../CONVERSION_POLICY.md)이 기준이다. 설계 근거는 [Codex-native 변환 아키텍처](../architecture/codex-native-conversion.md)를 참조한다.

## 요구사항과 설치

- Python 3.13 또는 3.14
- `uv`

```bash
uv sync --dev
```

## 입력과 출력

| 경로 | 역할 |
| --- | --- |
| `content/source/kisa-cce-criteria-2026.pdf` | 체크섬으로 고정한 기준 원문 |
| `content/criteria/<domainIdentifier>/` | 정본 Markdown과 원문 추적 정보(provenance)를 담은 보조 파일 |
| `content/assets/<criterionSlug>/` | 항목에 필요한 원문 영역 이미지 |
| `data/` | 매니페스트, 분류 체계, 원문 레지스트리, 검토와 주석 데이터 |
| `schemas/` | 입력, 정본 콘텐츠와 생성 산출물의 JSON Schema |
| `conversion/prompts/` | Codex-native와 기존 변환 경로의 모델 계약 |
| `.artifacts/work/` | 실행 작업 공간, 이벤트, 검토 후보와 로그 |

현재 정본 콘텐츠는 382개 항목이다. Front matter의 유형별로 361개는 `systemCriterion`, 21개는 `webApplicationCriterion`이며 `extractedCriterion`은 없다.

## 초기 전사 corpus 재생성

```bash
uv run python -m conversion.generate_corpus
```

이 명령은 항목별 Markdown, 원문 추적 정보, 원문 영역 자산, 매니페스트, 페이지 영역 목록, 검토 레지스트리와 원문 주석을 다시 작성할 수 있다. 현재 생성기가 보존하는 항목은 U-01과 U-02뿐이며 나머지 구조화된 380개 항목은 덮어쓸 수 있다. 실행 전에 보존 목록과 변경 범위를 수정하고 검증해야 한다.

## Codex-native 의미 구조화

권장 변환 경로는 `conversion.codex_agent_pipeline`이다. Codex는 콘텐츠 주소 기반으로 격리된 작업 공간에서 정본 형식의 Markdown과 원문 추적 정보를 직접 작성한다. 컨트롤러는 결정적인 절차로 입력 경계, 스키마, 정본 구조와 원문 반영 범위를 검증한다.

```text
PDF evidence
  -> content-addressed isolated workspace
  -> Codex-owned Markdown + provenance conversion
  -> deterministic boundary and repository validation
  -> review-only candidate package
```

Codex는 `conversion/prompts/criterion-agent-v1.md`에 따라 첨부된 모든 페이지 이미지를 비전으로 검사한다. 작업 공간에서는 `output/criterion.md`, `output/provenance.yaml`, `output/status.json`만 작성하며 종료 전에 `validate_candidate.py`를 실행한다. 컨트롤러는 생성 내용, 분류 체계 선택 또는 원문 추적 정보를 다시 쓰지 않는다.

생성물은 검토용 후보이며 정본 Markdown, 레지스트리 또는 검토 상태에 자동으로 반영하거나 승인하지 않는다.

## 실행

하나 이상의 `extractedCriterion`을 변환한다.

```bash
uv run python -m conversion.codex_agent_pipeline <criterion-slug> \
  --model <model-identifier>
```

현재 정본 콘텐츠에는 `extractedCriterion`이 없다. 향후 초기 전사 항목이 생기거나 이전할 대상을 명시적으로 준비했을 때 사용한다.

실제 Codex 요청 없이 계획을 확인한다.

```bash
uv run python -m conversion.codex_agent_pipeline <criterion-slug> --dry-run
```

전체 대상은 매니페스트 순서로 처리한다. 작업자 수는 1부터 16까지 지정할 수 있고 기본값은 4다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --workers 4 \
  --model <model-identifier>
```

OpenCodeX 같은 사용자 지정 제공자를 사용할 때만 사용자 설정을 명시적으로 불러온다.

```bash
ocx start
uv run python -m conversion.codex_agent_pipeline <criterion-slug> \
  --use-user-config \
  --model <provider>/<model-identifier>
```

중단된 실행을 재개할 때는 모델 라우팅과 콘텐츠 주소를 동일하게 유지한다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --model <model-identifier> \
  --resume
```

`--resume`은 작업 체크섬, 모델 식별자, 사용자 설정 로드 여부와 후보 재검증 결과가 일치하는 완료 실행만 건너뛴다.

## Artifact

| 경로 | 역할 |
| --- | --- |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/workspace/` | 변경 불가 작업 정의, 계약, 참고 자료, 근거와 출력 경계 |
| `workspace/output/criterion.md` | 완전한 검토 후보 Markdown |
| `workspace/output/provenance.yaml` | 전체 블록의 원문 추적 정보(provenance)를 담은 보조 파일 |
| `workspace/output/status.json` | 크기와 형식이 제한된 최종 상태 |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/events.jsonl` | 콘텐츠가 포함된 Codex 원시 이벤트 스트림 |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/run.json` | 모델 라우팅, 종료 상태와 검증 체크섬 |
| `.artifacts/work/codex-agent/summary.json` | 매니페스트 순서로 정렬한 전체 항목 결과와 집계 |

한 항목이 실패해도 다른 항목의 작업 공간은 바뀌지 않으며 나머지 항목을 계속 처리한다. 실패가 있으면 요약 상태를 `completedWithFailures`로 기록하고 0이 아닌 종료 코드를 반환한다. 원시 `events.jsonl`은 공개 산출물에 포함하면 안 된다.
