# KISA CCE 가이드 2026

한국인터넷진흥원(KISA)의 `주요정보통신기반시설 기술적 취약점 분석·평가 방법 상세가이드`를 검색·탐색 가능한 정적 웹 콘텐츠로 변환하는 저장소입니다.

현재 결과물은 전체 항목을 대상으로 생성한 초기 기계 전사본입니다. 공개 릴리스 또는 원문 대체 자료가 아닙니다.

변환 규칙과 승인 조건은 [문서 변환 정책](CONVERSION_POLICY.md)을 따릅니다.

## 원문 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 주요정보통신기반시설 기술적 취약점 분석·평가 방법 상세가이드 |
| 발행 기관 | 한국인터넷진흥원(KISA) AI기반보호팀 |
| 배포일 | 2025-12-24 |
| 원본 파일 | [kisa-cce-criteria-2026.pdf](kisa-cce-criteria-2026.pdf) |
| 원문 게시물 | <https://www.kisa.or.kr/2060204/form?postSeq=22&page=1> |
| PDF SHA-256 | `44fe393981b244147be6af7423d99dc15633c089fad0bcb296cbe2371dde812d` |
| 라이선스 검토 | 확인 중. 공개 배포 승인 전까지 재배포하지 않음 |

## 현재 상태

| 항목 | 현재 값 |
| --- | ---: |
| 원문 물리 페이지 | 873 |
| 분야 | 12 |
| 점검항목 | 382 |
| Canonical Markdown | 382 |
| Provenance sidecar | 382 |
| 완전 구조화 항목 | 2 |
| 페이지 단위 초기 전사 항목 | 380 |
| Page region | 2,521 |
| 공개 criterion region | 824 |
| 미분류 content block | 0 |
| 원문 영역 시각 자산 | 815 |
| Review record | 1,206 |
| 정규화 JSON | 382 |
| 검색 색인 record | 382 |
| 생성 HTML 페이지 | 469 |
| 전역 원문 이상 annotation | 32 |
| 항목별 원문 이상 annotation | 65 |
| 사람 검토 완료 record | 0 |

분야별 점검항목 수는 다음과 같습니다.

| 분야 | 코드 | 항목 수 |
| --- | --- | ---: |
| Unix 서버 | U-01~U-67 | 67 |
| Windows 서버 | W-01~W-64 | 64 |
| 웹 서비스 | WEB-01~WEB-26 | 26 |
| 보안 장비 | S-01~S-23 | 23 |
| 네트워크 장비 | N-01~N-38 | 38 |
| 제어시스템 | C-01~C-51 | 51 |
| PC | PC-01~PC-18 | 18 |
| DBMS | D-01~D-26 | 26 |
| 이동통신 | M-01~M-04 | 4 |
| Web Application | CI, SI, DI 등 | 21 |
| 가상화 장비 | HV-01~HV-25 | 25 |
| 클라우드 | CA-01~CA-19 | 19 |

## 콘텐츠 성숙도

`unix/u-01.md`가 이 저장소의 정본 서식 exemplar입니다. 변환을 완료한 모든 점검항목은 이 문서와 동일한
heading 구성, 섹션 본문 형식, 표기 규약을 따릅니다. 상세 규칙은 [문서 변환 정책](CONVERSION_POLICY.md)의
`정본 서식 계약` 절에 정의되어 있습니다.

현재 두 가지 content model이 존재합니다.

### `systemCriterion`

U-01과 U-02에 적용됩니다.

- 정본 서식 계약의 고정 heading 11개를 순서까지 일치하게 사용
- 개요, 판단 기준, 조치 사례를 의미 단위로 구조화
- 명령어, 설정, 출력, 표를 typed block으로 표현
- Leaf block 단위 provenance 제공
- 기술 literal을 별도 검색어로 추출

### `extractedCriterion`

나머지 380개 항목에 적용됩니다.

- 코드, 제목, 중요도, 분야, 분류, 원문 페이지 범위 제공
- 원문 페이지별 텍스트 전사 제공
- 페이지별 원문 영역 PNG와 crop provenance 제공
- 페이지 단위 provenance 제공
- 정규화 JSON과 검색 색인 생성 지원
- 대상 시스템은 `unspecified`로 등록
- 표, 목록, 명령어, 이미지 설명은 아직 의미 구조로 분리되지 않음

`extractedCriterion`은 원문 누락 방지와 후속 구조화 작업을 위한 초기 상태입니다. 정본 서식 계약을 적용하지 않으며, 접근성 검토와 내용 승인의 대상이 되는 최종 변환 상태가 아닙니다. 릴리스 검증은 `extractedCriterion`이 한 건이라도 존재하면 실패합니다.

구조화 작업은 이 상태의 문서를 정본 서식 계약을 충족하는 `systemCriterion` 또는 `webApplicationCriterion`으로
전환하는 과정입니다. Repository validator가 heading 구성, 판단 기준 표기, 참고 blockquote profile,
fenced code info string을 강제합니다.

## 변환 구조

```text
원본 PDF
  -> authoritative inventory
  -> canonical Markdown + provenance + source crops
  -> normalized JSON
  -> search index
  -> static HTML + public JSON dataset
```

주요 경로는 다음과 같습니다.

| 경로 | 용도 |
| --- | --- |
| `<domainIdentifier>/*.md` | Canonical criterion 콘텐츠 |
| `<domainIdentifier>/*.provenance.yaml` | Block 또는 페이지 단위 원문 추적 정보 |
| `assets/<criterionSlug>/` | 원문 영역 시각 자산 |
| `data/criteria-manifest.yaml` | 382개 점검항목 allowlist |
| `data/taxonomy.yaml` | 분야, 분류, 대상 taxonomy |
| `data/page-region-inventory.yaml` | 873쪽 page-region 분류 |
| `data/review-registry.yaml` | Criterion과 공개 region의 검토 상태 |
| `data/source-annotations.yaml` | 원문 이상과 확인 필요 항목 |
| `data/derived/` | PDF에서 파생된 inventory와 anomaly 자료 |
| `data/qa-reports/` | Corpus checksum과 test profile에 결합된 브라우저 QA 보고서 |
| `schemas/` | Canonical 및 생성 데이터 JSON Schema |
| `conversion/` | 전사, 검증, 정규화, 사이트 생성 도구 |
| `site_assets/` | 정적 사이트 CSS와 JavaScript |
| `tests/` | 변환, 결정성, 링크, HTML 구조 테스트 |
| `build/` | 생성 결과. Git에서 제외됨 |

## 요구사항

- Python 3.13 또는 3.14
- `uv`

프로덕션 Python 의존성은 없습니다. 변환과 검증 도구는 development dependency로 관리합니다.

## 설치

```bash
uv sync --dev
```

## 전체 초기 전사 재생성

다음 명령은 authoritative inventory와 PDF를 기준으로 초기 전사 corpus를 다시 생성합니다.

```bash
uv run python -m conversion.generate_corpus
```

이 명령은 380개 `extractedCriterion` 파일과 provenance, 815개 원문 영역 PNG, manifest, page-region inventory, review registry, source annotation을 다시 작성합니다.

현재 보존 목록은 U-01과 U-02뿐입니다. 추가 항목을 사람이 구조화한 후에는 해당 항목을 generator의 보존 대상으로 등록한 다음 생성기를 실행해야 합니다.

## Codex 의미 구조화

신규 변환의 권장 경로는 `conversion.codex_agent_pipeline`입니다. Codex가 content-addressed 격리 workspace에서 canonical-format Markdown과 provenance를 직접 작성하고, deterministic controller는 입력 경계와 결과의 안전성·정합성만 검증합니다.

```text
PDF evidence
  -> content-addressed isolated workspace
  -> Codex-owned Markdown + provenance conversion
  -> deterministic boundary and repository validation
  -> review-only candidate package
```

- Controller는 항목별 현재 Markdown과 provenance에서 criterion-bound evidence task를 만들고, U-01 Markdown reference, compact provenance example, 관련 PDF page image, transcript navigation aid, technical literal, target taxonomy slice만 workspace에 배치합니다. 원본 Markdown과 provenance를 중복 복사하지 않습니다.
- Workspace 경로는 `work/codex-agent/jobs/<criterionSlug>/<taskChecksum>/`입니다. Task checksum은 prompt contract, status schema, compact references, 현재 criterion package checksum, evidence image와 task 내용을 결합한 content address입니다.
- Codex는 [`codex_prompts/criterion-agent-v1.md`](codex_prompts/criterion-agent-v1.md)를 따릅니다. 모든 첨부 이미지를 vision으로 검사하고, `workspace-write` sandbox 안의 `output/criterion.md`, `output/provenance.yaml`, `output/status.json`을 직접 작성합니다. 종료 전 격리 workspace의 `validate_candidate.py`로 같은 production validator를 실행합니다.
- Controller는 Codex가 작성한 내용, 구조, taxonomy 선택과 provenance를 다시 쓰거나 추론하지 않습니다. Workspace file allowlist와 immutable input checksum, status schema, metadata와 provenance schema, canonical Markdown 구조, technical literal, taxonomy identifier, block reference 순서, source page coverage를 검증합니다.
- Agent contract version 1은 source-page crop을 candidate asset으로 게시하지 않으며 provenance의 `assets`를 비워 둡니다.
- 생성물은 사람이 검토해야 하는 candidate입니다. Canonical Markdown, registry, review status를 자동으로 적용하거나 승인하지 않습니다.

### Codex-native 실행

U-03만 변환합니다. 재현 가능한 실행에서는 model identifier를 고정합니다.

```bash
uv run python -m conversion.codex_agent_pipeline u-03 \
  --model <model-identifier>
```

실제 Codex 요청 없이 content-addressed workspace와 실행 계획을 확인합니다.

```bash
uv run python -m conversion.codex_agent_pipeline u-03 --dry-run
```

전체 `extractedCriterion` corpus를 manifest 순서로 변환합니다. 기본 worker 수는 4이며, 1부터 16까지 지정할 수 있습니다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --workers 4 \
  --model <model-identifier>
```

OpenCodeX를 통해 Claude를 사용할 때는 OpenCodeX를 먼저 시작하고, Codex 사용자 설정을 명시적으로 로드합니다. OpenCodeX의 namespaced model identifier를 사용해야 공급자 선택이 명확합니다.

```bash
ocx start
uv run python -m conversion.codex_agent_pipeline u-03 \
  --use-user-config \
  --model anthropic/claude-opus-5
```

중단된 실행은 동일한 model routing과 content address로 재개합니다.

```bash
uv run python -m conversion.codex_agent_pipeline \
  --model <model-identifier> \
  --resume
```

주요 artifact는 다음과 같습니다.

| 경로 | 역할 |
| --- | --- |
| `work/codex-agent/jobs/<slug>/<taskChecksum>/workspace/` | Immutable task, contract, status schema, compact references, page evidence와 격리된 output 경계 |
| `workspace/output/criterion.md` | Codex가 직접 작성한 complete review candidate Markdown |
| `workspace/output/provenance.yaml` | Codex가 직접 작성한 complete block-level provenance sidecar |
| `workspace/output/status.json` | [`schemas/codex-agent-status.schema.json`](schemas/codex-agent-status.schema.json)으로 제한된 최종 상태 |
| `work/codex-agent/jobs/<slug>/<taskChecksum>/events.jsonl` | Content-bearing raw Codex event stream |
| `work/codex-agent/jobs/<slug>/<taskChecksum>/run.json` | Model routing, duration, exit status, event aggregate와 validation checksum |
| `work/codex-agent/summary.json` | Manifest 순서의 corpus 결과와 `completed`, `skipped`, `dryRun`, `validationFailed`, `failed` 집계 |

Status schema version 1은 task identifier와 checksum, `candidateWritten`, `complete` 또는 `needsSourceReview`, 모든 검토 page, unresolved question만 허용합니다. Validation report는 candidate, provenance, status checksum과 `validationStatus: passed`, `canonicalApplied: false`를 run manifest에 기록합니다.

`--resume`은 같은 task checksum, model identifier, 사용자 설정 로드 여부를 가진 완료 run을 찾은 뒤 candidate 전체를 다시 검증합니다. 현재 파일의 validation 결과가 run manifest와 정확히 일치할 때만 `skipped`로 처리합니다. 이전 model 실행은 성공했지만 validator가 실패한 `validationFailed` run도 먼저 로컬에서 재검증하므로, validator 수정만으로 Codex를 다시 호출하지 않습니다. Candidate가 없거나 변경됐거나 재검증에 실패한 경우에만 같은 workspace에서 Codex 변환을 다시 실행합니다.

| 옵션 | 동작 |
| --- | --- |
| `<slug>...` | 선택적인 `extractedCriterion` allowlist. 입력 순서와 관계없이 manifest 순서로 실행 |
| `--workers <1-16>` | 병렬 worker 수 지정. 기본값은 `4` |
| `--model <identifier>` | 모든 Codex agent run의 model 고정 |
| `--use-user-config` | OpenCodeX 같은 사용자 정의 provider를 위해 Codex 사용자 설정 로드 |
| `--dry-run` | Workspace와 summary만 생성하고 Codex를 실행하지 않음 |
| `--resume` | 현재 routing과 전체 재검증 결과가 일치하는 완료 candidate만 건너뜀 |
| `--work-directory <path>` | 기본 `work/codex-agent/` 대신 사용할 격리된 artifact root 지정 |

기본 실행은 재현성과 격리를 위해 Codex 사용자 설정을 무시합니다. `--use-user-config`를 지정하면 사용자 설정의 provider, MCP server, 기타 실행 옵션도 함께 로드되므로, 신뢰할 수 있는 설정에서만 사용해야 합니다. 항목별 sandbox는 content-addressed workspace만 쓸 수 있습니다.

한 항목의 실패는 다른 항목의 workspace와 상태를 변경하지 않습니다. 전체 corpus는 나머지 항목을 계속 처리하고, 실패가 하나라도 있으면 summary를 `completedWithFailures`로 기록하며 command는 non-zero exit code를 반환합니다.

### Legacy structured-JSON migration pipeline

다음 pipeline은 schema version 2 node JSON을 거쳐 review Markdown을 렌더링하는 기존 migration 경로입니다. 기존 `work/codex/` artifact를 재검증하거나 점진적으로 이전할 때만 사용합니다. 신규 변환은 Codex-native pipeline을 사용합니다.

자동 전사 항목은 구현 코드가 만든 immutable evidence task와 Codex read-only 분석을 결합해 review candidate로 변환할 수 있습니다.

```text
PDF evidence
  -> deterministic task builder
  -> Codex read-only structured output
  -> deterministic importer validation
  -> review-only Markdown candidate
```

이 단계의 기준은 단순 전사문이 아니라, 가독성과 머신 리더블 요구사항을 함께 충족하는 의미 구조입니다.

- Task builder는 항목과 관련된 모든 PDF 페이지 이미지를 첨부해야 하며, Codex는 각 이미지를 vision으로 직접 검사해야 합니다.
- `transcript`는 페이지 탐색, 검색, 원문 위치 확인을 돕는 보조 자료이며 판정 근거가 아닙니다. OCR 범위에는 스크린샷, 도표, 표 등 PDF 내부 이미지에 포함된 문자도 들어가야 합니다.
- 제목, 문단, 목록, note, 이미지는 의미 역할에 맞는 node로 변환합니다. 코드, 명령어, 설정, 출력은 언어와 content type을 지정한 fenced code block으로 분리합니다.
- 원문의 표는 header, caption, cell 관계를 가진 semantic table로 변환합니다. 구조가 불확실하면 추정하지 않고 원문 이미지, provenance, `quality.unresolvedQuestions`를 보존합니다.
- 같은 의미 구조에서 semantic HTML과 항목별 공개 JSON dataset을 생성합니다.
- 현재 Codex task와 result contract는 schema version 2이며, 페이지별 vision inspection과 node별 image provenance를 필수로 검증합니다.

U-03 task를 생성합니다.

```bash
uv run python -m conversion.codex_task_builder u-03
```

생성된 task를 읽어 JSON Schema 결과를 생성합니다.

```bash
uv run python -m conversion.codex_runner u-03
```

모델을 고정해야 하는 재현 가능한 실행에서는 `--model`을 지정합니다.

```bash
uv run python -m conversion.codex_runner u-03 --model <model-identifier>
```

OpenCodeX를 통해 Claude를 사용할 때는 OpenCodeX를 먼저 시작하고, Codex 사용자 설정을 명시적으로 로드합니다. OpenCodeX의 namespaced model identifier를 사용해야 공급자 선택이 명확합니다.

```bash
ocx start
uv run python -m conversion.codex_runner u-03 \
  --use-user-config \
  --model anthropic/claude-opus-5
```

결과를 검증하고 review-only Markdown candidate를 생성합니다.

```bash
uv run python -m conversion.codex_result_importer u-03
```

Task, JSONL event, structured result, run manifest, candidate는 `work/codex/` 아래에 생성되며 Git에서 제외됩니다. Importer는 page coverage, page-region reference, source excerpt, technical literal, heading hierarchy, annotation target을 검사합니다. Canonical Markdown과 review registry는 자동으로 변경하지 않습니다.

#### Legacy 전체 corpus 병렬 변환

전체 실행은 `data/criteria-manifest.yaml`의 record 순서대로 모든 `extractedCriterion` 항목을 선택합니다. Positional slug를 지정하면 해당 allowlist만 선택하되 manifest 순서를 유지합니다. Worker가 완료되는 순서는 실행 순서와 summary 순서에 영향을 주지 않습니다.

각 항목은 다음 세 단계를 독립적으로 수행합니다.

| Summary stage | 항목별 경로 | 역할 |
| --- | --- | --- |
| `taskBuild` | `work/codex/tasks/<criterionSlug>/task.json` | 현재 원문, 정책, prompt, schema checksum에 결합된 immutable evidence task 생성 |
| `visionRun` | `work/codex/results/<criterionSlug>/` | 모든 관련 PDF page image를 첨부한 read-only Codex 분석과 structured result 생성 |
| `importer` | `work/codex/candidates/<criterionSlug>/` | Result 검증, review-only Markdown candidate와 validation report 생성 |

실제 Codex 요청 없이 전체 실행 계획과 task를 확인합니다. Dry run은 필요한 `visionRun` 계획을 기록하지만 importer를 실행하지 않습니다.

```bash
uv run python -m conversion.codex_bulk_runner --dry-run
```

전체 corpus를 변환합니다. 재현 가능한 실행은 모델 identifier를 고정합니다.

```bash
uv run python -m conversion.codex_bulk_runner --model <model-identifier>
```

OpenCodeX의 Claude 모델로 전체 corpus를 변환합니다.

```bash
ocx start
uv run python -m conversion.codex_bulk_runner \
  --use-user-config \
  --model anthropic/claude-opus-5
```

중단되었거나 일부 항목이 실패한 실행을 검증된 artifact부터 재개합니다.

```bash
uv run python -m conversion.codex_bulk_runner \
  --model <model-identifier> \
  --resume
```

주요 옵션은 다음과 같습니다.

| 옵션 | 동작 |
| --- | --- |
| `<slug>...` | 선택적인 `extractedCriterion` allowlist. 입력 순서와 관계없이 manifest 순서로 실행 |
| `--workers <1-16>` | 병렬 worker 수 지정. 기본값은 `min(2, max(1, logicalCpuCount))` |
| `--model <identifier>` | 모든 Codex vision run의 model 고정 |
| `--use-user-config` | OpenCodeX 같은 사용자 정의 provider를 위해 Codex 사용자 설정 로드 |
| `--dry-run` | Task와 vision run plan만 기록하고 importer 생략 |
| `--resume` | 현재 checksum으로 검증된 result 또는 candidate만 재사용 |
| `--fail-fast` | 첫 실패 후 새 항목 scheduling 중단. 실행 중인 worker는 완료를 기다리고, 시작하지 않은 항목은 `cancelled`로 기록 |
| `--retries <0-5>` | 첫 vision run 실패 후 명시적 재시도 횟수. 기본값은 `0` |
| `--retry-backoff-seconds <0-300>` | 재시도의 deterministic exponential backoff base. 각 대기 시간도 최대 300초이며, 기본값은 `0` |
| `--work-directory <path>` | 기본 `work/codex/` 대신 사용할 격리된 artifact root 지정 |
| `--summary-path <path>` | 기본 `<work-directory>/bulk-summary.json` 대신 summary 경로 지정 |

기본 worker 수는 최대 2인 보수적인 값이며, 설정 가능한 절대 상한은 16입니다. 전체 corpus의 첫 실행에는 작은 기본값을 권장합니다. 항목마다 여러 page image와 별도 Codex process를 사용하므로, 큰 병렬값은 API rate limit, 동시 요청 한도, input token 사용량, model context, 메모리 압박을 키울 수 있습니다. 제한에 도달하면 `--workers 1`로 낮추고 `--resume`으로 이어서 실행합니다.

기본 실행은 재현성과 격리를 위해 Codex 사용자 설정을 무시합니다. `--use-user-config`를 지정하면 사용자 설정의 provider, MCP server, 기타 실행 옵션도 함께 로드되므로, 신뢰할 수 있는 설정에서만 사용해야 합니다. Read-only sandbox와 schema 검증은 그대로 유지됩니다.

재개 실행도 현재 입력에서 task를 다시 생성합니다. Run manifest의 task identifier와 checksum, result checksum, model, 사용자 설정 로드 여부가 현재 요청과 일치해야 합니다. Candidate의 checksum, `validationStatus: passed`, `canonicalApplied: false`까지 모두 일치하면 `skipped`로 기록합니다. 현재 task와 실행 설정에 유효한 result만 있으면 importer부터 재개하고 `resumedImport`로 기록합니다. 누락되거나 오래된 artifact는 vision 단계부터 다시 처리합니다.

한 항목의 실패는 다른 항목의 artifact를 손상시키지 않습니다. 기본 실행은 나머지 항목을 계속 처리하고 `work/codex/bulk-summary.json`에 `taskBuild`, `visionRun`, `importer`의 상태, 오류, `completed`, `resumedImport`, `skipped`, `dryRun`, `failed`, `cancelled` outcome을 manifest 순서로 기록합니다. Schema version 1 summary는 `schemas/codex-bulk-summary.schema.json` 검증을 통과한 뒤 원자적으로 교체됩니다. 실패 또는 취소가 하나라도 있으면 command는 non-zero exit code를 반환합니다.

전체 실행도 canonical Markdown, provenance, review registry를 적용하거나 승인하지 않습니다. `work/codex/candidates/`의 결과는 별도 사람 검토와 명시적 적용 작업이 필요한 review-only artifact입니다.

## 검증 및 빌드

Canonical 콘텐츠, registry, asset 경로·해시·크기를 검증합니다.

```bash
uv run python -m conversion.validate_content
```

정규화 JSON, 검색 색인, 정적 사이트를 생성합니다.

```bash
uv run python -m conversion.build_content
```

하위 경로에 배포할 URL을 생성하려면 base path를 지정합니다. GitHub Pages 프로젝트 사이트의 기본 경로는 저장소 이름입니다.

```bash
uv run python -m conversion.build_content --base-path /kisa-cce-guide-web
```

로컬 서버는 canonical 검증과 사이트 빌드를 실행한 다음, loopback 주소에서 결과를 제공합니다.

```bash
uv run python -m conversion.serve_site
```

브라우저에서 <http://localhost:8000/>에 접속합니다.

기존 빌드를 즉시 다시 열려면 다음 명령을 사용합니다.

```bash
uv run python -m conversion.serve_site --no-build
```

GitHub Pages 하위 경로를 로컬에서 확인할 수도 있습니다.

```bash
uv run python -m conversion.serve_site --base-path /kisa-cce-guide-web
```

기본 listen 주소는 `127.0.0.1`입니다. 같은 네트워크의 다른 장치에서 접근해야 하는 경우에만 `--host 0.0.0.0`을 명시합니다.

## 정적 사이트 구성

빌드는 다음 결과를 생성합니다.

- 홈과 12개 분야 페이지
- 71개 분류 페이지
- 382개 점검항목 상세 페이지
- 코드, 제목, 본문, 설정값 검색
- 분야, 분류, 중요도, 대상 필터
- 이전·다음 항목 탐색
- 원문 이상 목록
- 404 페이지
- 항목별 정규화 JSON
- 검색 색인과 taxonomy JSON
- 원문 게시물 링크
- 반응형 및 인쇄용 CSS

생성된 사이트는 469개 HTML 페이지를 포함합니다. 모든 HTML 페이지의 언어, 단일 H1, landmark, skip link, 고유 anchor, 내부 링크, 이미지, 표, 검색 anchor는 정적 검사 대상입니다.

라이선스 승인 전에는 원본 PDF를 사이트 산출물에 복사하지 않습니다. 상세 페이지는 KISA 원문 게시물로 연결됩니다.

## GitHub Pages

`.github/workflows/pages-build.yaml`은 수동 실행에서 GitHub Pages용 사이트를 빌드하고 검토 artifact로 저장합니다.

- 실행 입력의 `base_path`를 빌드에 전달
- 프로젝트 사이트는 `/kisa-cce-guide-web`, 커스텀 도메인은 빈 경로를 사용
- Canonical 검증과 회귀 테스트 후 검토 artifact 생성
- `.nojekyll`을 포함해 생성 파일을 그대로 게시
- GitHub Pages 공개 권한 없이 검토 artifact만 생성

현재 라이선스와 사람 검토가 완료되지 않았으므로 공개 배포 job은 구성하지 않습니다. GitHub Pages 공개 배포를 추가하려면 공개 범위와 라이선스 위험을 별도로 승인해야 합니다.

## 품질 검사

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run ty check conversion tests
uv run pytest -q
git diff --check
```

테스트 범위는 다음을 포함합니다.

- Canonical schema와 registry 검증
- Markdown image와 provenance asset의 1:1 대응
- Asset 경로, SHA-256, PNG profile, pixel dimensions, crop 검증
- 382개 route와 JSON dataset 생성
- 469개 HTML 구조와 내부 링크 검사
- 하위 경로 URL 생성
- 정규화 JSON과 정적 사이트 결정성
- 검색 색인의 코드와 기술 literal
- U-01·U-02 typed AST와 provenance

## 릴리스 검증

전체 릴리스 조건은 다음 명령으로 검사합니다.

```bash
uv run python -m conversion.validate_content \
  --release \
  --report build/reports/release-validation.json
```

현재 릴리스 검증은 실패해야 합니다. 초기 전사본의 존재와 공개 릴리스 승인은 별도 상태입니다.

현재 차단 조건은 다음과 같습니다.

- 1,206개 review record가 모두 사람 승인 전 상태
- 자동 검증 결과가 review registry에 반영되지 않음
- 231개 항목별 source annotation이 미검토 상태
- 라이선스 유형, 허용 이용 범위, 필수 출처 문구가 미승인 상태
- 시각·접근성 test profile이 미완성 상태
- 접근성, 반응형, 인쇄 브라우저 QA 보고서가 없음
- 공개 배포 구성이 승인되지 않음

382개 항목은 분야별 `systemCriterion` 또는 `webApplicationCriterion`으로 구조화되었습니다.
변환 중 사용한 815개 원문 영역 crop은 canonical asset에서 제거하고, 비공개 작업 증거로 보존했습니다.

브라우저 QA 보고서는 `schemas/qa-report.schema.json`을 따라야 합니다. 보고서는 현재 canonical corpus checksum과 test profile version을 참조해야 하며, 빌드 과정에서 자동 생성하거나 덮어쓰지 않습니다.

## 범위와 한계

- 원본 PDF가 점검·감사·법적 판단의 기준입니다.
- 자동 구조화에는 줄 분리, 표 구조 손실, 특수문자 손상 가능성이 있습니다.
- 380개 자동 구조화 항목의 명령어, 경로, 표, 판단 기준은 사람의 원문 대조를 완료하지 않았습니다.
- 비공개 작업 증거로 보존한 원문 영역 PNG는 사람의 검토 완료를 의미하지 않습니다.
- 원문 내부의 코드, 중요도, 제목, 분류 차이는 자동 수정하지 않고 annotation으로 보존합니다.
- 대상 시스템 metadata는 구조화 후보의 taxonomy 검증을 통과했지만, 사람 검토 전 상태입니다.
- 검색 결과는 미검토 전사문을 포함합니다.
- 이 저장소는 KISA가 운영하거나 승인한 저장소가 아닙니다.

## 저작권 및 배포 제한

원문의 저작권은 한국인터넷진흥원에 있습니다.

현재 `data/source-registry.yaml`의 라이선스 승인 상태는 `pending`입니다. 라이선스 유형, 허용 이용 범위, 필수 출처 표시문이 승인되기 전에는 생성 사이트와 변환 자산을 공개 배포하지 않습니다.

## 기여

콘텐츠 변경은 [문서 변환 정책](CONVERSION_POLICY.md)을 따라야 합니다.

- 변환 오류: Markdown, metadata, provenance, 검색 색인 또는 HTML이 원문과 다른 경우
- 원문 이상: PDF 내부의 코드, 중요도, 제목, 분류 또는 기술 표기가 서로 충돌하는 경우
- 구조화 작업: `extractedCriterion`을 분야별 content model로 전환하는 경우
- 접근성 작업: 키보드 탐색, landmark, heading, 표, 코드, 대비, reflow, 인쇄 결과를 검증하는 경우

Generated output인 `build/` 파일은 직접 수정하지 않습니다.
