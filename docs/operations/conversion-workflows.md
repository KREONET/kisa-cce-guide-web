# 변환 워크플로

이 문서는 canonical criterion 콘텐츠를 생성하고 Codex-native candidate를 만드는 운영 절차를 설명한다. 콘텐츠 형식과 승인 조건은 [문서 변환 정책](../../CONVERSION_POLICY.md)이 기준이다. 설계 근거는 [Codex-native 변환 아키텍처](../architecture/codex-native-conversion.md)를 참조한다.

## 요구사항과 설치

- Python 3.13 또는 3.14
- `uv`

```bash
uv sync --dev
```

## 입력과 출력

| 경로 | 역할 |
| --- | --- |
| `content/source/kisa-cce-criteria-2026.pdf` | checksum으로 고정된 기준 원문 |
| `content/criteria/<domainIdentifier>/` | Canonical Markdown과 provenance sidecar |
| `content/assets/<criterionSlug>/` | 필요한 원문 영역 시각 자산 |
| `data/` | Manifest, taxonomy, source registry, review와 annotation 데이터 |
| `schemas/` | 입력, canonical, 생성 artifact JSON Schema |
| `conversion/prompts/` | Codex-native와 legacy 모델 계약 |
| `.artifacts/work/` | 실행 workspace, event, candidate와 로그 |

현재 canonical corpus는 382개 항목이다. Front matter 기준으로 361개는 `systemCriterion`, 21개는 `webApplicationCriterion`이며, `extractedCriterion`은 없다.

## 초기 전사 corpus 재생성

```bash
uv run python -m conversion.generate_corpus
```

이 작업은 criterion Markdown, provenance, 원문 영역 자산, manifest, page-region inventory, review registry와 source annotation을 다시 작성할 수 있다. 현재 generator의 보존 목록은 U-01과 U-02뿐이므로, 나머지 380개 구조화 항목을 덮어쓸 수 있다. 보존 목록과 변경 범위를 먼저 수정·검증하지 않은 상태에서는 실행하면 안 된다.

## Codex-native 의미 구조화

권장 경로는 `conversion.codex_agent_pipeline`이다. Codex가 content-addressed 격리 workspace에서 canonical-format Markdown과 provenance를 직접 작성하고, deterministic controller가 입력 경계, schema, canonical 구조와 원문 coverage를 검증한다.

```text
PDF evidence
  -> content-addressed isolated workspace
  -> Codex-owned Markdown + provenance conversion
  -> deterministic boundary and repository validation
  -> review-only candidate package
```

Codex는 `conversion/prompts/criterion-agent-v1.md`를 따르고, 모든 첨부 page image를 vision으로 검사한다. Workspace의 `output/criterion.md`, `output/provenance.yaml`, `output/status.json`만 작성하며, 종료 전 `validate_candidate.py`를 실행한다. Controller는 생성 내용, taxonomy 선택 또는 provenance를 다시 쓰지 않는다.

생성물은 review-only candidate다. Canonical Markdown, registry 또는 review status를 자동으로 적용하거나 승인하지 않는다.

## 실행

하나 이상의 `extractedCriterion`을 변환한다.

```bash
uv run python -m conversion.codex_agent_pipeline <criterion-slug> \
  --model <model-identifier>
```

현재 canonical corpus에는 `extractedCriterion`이 없으므로, 향후 초기 전사 항목이나 명시적으로 준비한 migration 대상에 사용한다.

실제 Codex 요청 없이 계획을 확인한다.

```bash
uv run python -m conversion.codex_agent_pipeline <criterion-slug> --dry-run
```

전체 대상은 manifest 순서로 처리한다. Worker 수는 1부터 16까지 지정할 수 있고 기본값은 4다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --workers 4 \
  --model <model-identifier>
```

OpenCodeX 같은 사용자 provider를 사용할 때만 사용자 설정을 명시적으로 로드한다.

```bash
ocx start
uv run python -m conversion.codex_agent_pipeline <criterion-slug> \
  --use-user-config \
  --model <provider>/<model-identifier>
```

중단된 실행은 같은 model routing과 content address로 재개한다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --model <model-identifier> \
  --resume
```

`--resume`은 task checksum, model identifier, 사용자 설정 로드 여부와 candidate 재검증 결과가 일치하는 완료 run만 건너뛴다.

## Artifact

| 경로 | 역할 |
| --- | --- |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/workspace/` | Immutable task, contract, reference, evidence와 output 경계 |
| `workspace/output/criterion.md` | Complete review candidate Markdown |
| `workspace/output/provenance.yaml` | Complete block-level provenance sidecar |
| `workspace/output/status.json` | Bounded final status |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/events.jsonl` | Content-bearing raw Codex event stream |
| `.artifacts/work/codex-agent/jobs/<slug>/<taskChecksum>/run.json` | Model routing, 종료 상태와 validation checksum |
| `.artifacts/work/codex-agent/summary.json` | Manifest 순서의 corpus 결과와 outcome 집계 |

한 항목의 실패는 다른 항목의 workspace를 변경하지 않는다. 전체 실행은 나머지 항목을 계속 처리하고, 실패가 있으면 summary를 `completedWithFailures`로 기록한 뒤 non-zero exit code를 반환한다. Raw `events.jsonl`은 공개 artifact에 포함하면 안 된다.
