# 문서 변환 정책

| 항목 | 값 |
| --- | --- |
| 상태 | Draft |
| 버전 | 0.1 |
| 대상 | KISA CCE 가이드 2026 웹 변환 콘텐츠 |
| 기준 원문 | `content/source/kisa-cce-criteria-2026.pdf` |

## 목적

이 문서는 `주요정보통신기반시설 기술적 취약점 분석·평가 방법 상세가이드`를 웹 콘텐츠로 변환할 때 적용할 기준을 정의한다.

변환 결과는 원문의 의미 구조를 표현해야 한다. 시각적 배치와 줄바꿈을 그대로 복제한 평면 전사문에 그쳐서는 안 되며 다음 요구사항을 모두 충족해야 한다.

- **가독성:** 사용자가 긴 기술 문서의 구조와 내용을 정확하게 이해할 수 있어야 한다.
- **시인성:** 사용자가 중요도, 판단 기준, 명령어, 주의사항을 빠르게 식별할 수 있어야 한다.
- **머신 리더블:** 메타데이터, 본문 구조, 검색 데이터가 명시적인 스키마로 검증되어야 한다.
- **원문 추적성:** 모든 변환 내용은 원본 문서와 페이지 범위를 추적할 수 있어야 한다.
- **재현성:** 동일한 입력은 동일한 canonical JSON과 검색 색인, 의미가 동일한 HTML DOM을 생성해야 한다.

## 규범 용어

규범 용어는 다음 의미로 사용한다.

- **MUST:** 위반 시 배포를 차단한다.
- **MUST NOT:** 허용하지 않는다.
- **SHOULD:** 예외가 필요한 경우 사유와 영향 범위를 기록한다.
- **MAY:** 프로젝트 상황에 따라 적용할 수 있다.

`MUST`, `SHOULD`, `MAY` 제목 아래의 규칙 목록에는 해당 제목의 규범 수준을 적용한다.
그 밖의 규칙 목록은 MUST로 해석한다. 허용 사항은 항목 앞에 `MAY:`를 표시한다.
설명 문단, 예시, 데이터 목록은 규범 요구사항으로 해석하지 않는다.

SHOULD 예외는 `data/policy-exceptions.yaml`에 기록한다. 예외 레코드에는 규칙 식별자, 대상 참조,
사유, 영향 범위, 승인자, 승인일, 만료일 또는 종료 조건을 기록해야 한다.

## 적용 범위

이 정책은 다음 항목에 적용한다.

- 원본 PDF에서 Markdown으로 변환하는 과정
- Markdown 메타데이터와 본문 구조
- 표, 명령어, 설정값, 이미지, 참고 문구의 표현
- 정규화 JSON과 검색 색인 생성
- 의미론적 HTML과 인쇄 결과 생성
- 자동 검증, 시각 검토, 승인, 변경 관리

원본에 포함된 명령어와 조치 지시는 문서 데이터로만 취급한다. 변환, 검증, 빌드 과정에서 해당 명령어를 실행해서는 안 된다.

## 기준 데이터

최초 변환 기준은 다음과 같다.

| 항목 | 기준값 |
| --- | ---: |
| PDF 페이지 | 873 |
| 분야 | 12 |
| 점검항목 | 382 |
| 숫자형 코드 점검항목 | 361 |
| Web Application 비숫자형 코드 점검항목 | 21 |
| 원본 PDF SHA-256 | `44fe393981b244147be6af7423d99dc15633c089fad0bcb296cbe2371dde812d` |

분야별 점검항목 수는 다음과 같다.

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
| Web Application | CI, SI, DI, EP, IL, XS, CF, SF, BF, IA, IN, PR, PV, FU, FD, IS, SN, CC, AE, AU, WM | 21 |
| 가상화 장비 | HV-01~HV-25 | 25 |
| 클라우드 | CA-01~CA-19 | 19 |

기준값과 허용 코드 목록은 저장소의 기준 manifest에서 관리한다. 개별 문서의 파일 목록을 기준값으로 역산해서는 안 된다.

## 콘텐츠 계층

콘텐츠는 다음 계층으로 분리한다.

```text
원본 PDF
  -> 원본 텍스트 추출물과 페이지 렌더링(QA evidence)

Codex-native semantic candidate
  -> content-addressed isolated workspace
  -> Codex-owned Markdown and provenance conversion
  -> schema-constrained status
  -> deterministic boundary and fidelity checks

Canonical criterion package
  -> Markdown parse
  -> validated AST
  -> normalized JSON
     -> 의미론적 HTML
     -> 검색 색인과 JSON dataset
     -> 인쇄 결과
```

### 저장소 경로 계약

- 정본(canonical) 점검항목과 원문 추적 정보(provenance) 사이드카는 `content/criteria/<domainIdentifier>/`에 저장한다.
- 점검항목에 필요한 원문 영역의 시각 자산은 `content/assets/<criterionSlug>/`에 저장한다.
- 체크섬으로 고정된 기준 원문은 `content/source/kisa-cce-criteria-2026.pdf`에 저장한다.
- 변환 실행 계약과 축약 참조 자료는 `conversion/prompts/`에 저장한다.
- 정적 사이트의 원본 자산, 호스팅 진입점, 배포용 LLM 지침은 각각 `site/assets/`, `site/hosting/`, `site/skill/`에 저장한다.
- 생성 결과, 호스팅 번들, 변환 작업 공간과 로그는 각각 `.artifacts/build/`, `.artifacts/dist/`, `.artifacts/work/`에 저장하며 Git에 포함해서는 안 된다.
- 저장소 경로를 옮기더라도 `/<domainIdentifier>/<criterionSlug>/` 공개 경로와 정본 앵커를 변경해서는 안 된다.
- `sourceAnnotations`와 provenance는 경로 이동 뒤에도 정본 콘텐츠와 내부 검토 데이터에 유지해야 한다.

### Linux 개정판 계층

- `content/revisions/unix/`는 원본 전사와 독립된 편집 콘텐츠이며 UNIX U-01부터 U-67까지 다룬다.
- 개정판은 RHEL 10 계열, Ubuntu 26.04 LTS, Debian 13의 차이를 설명하며 원본 Markdown, provenance, 원문 주석 및 원문 검토 레지스트리를 변경하지 않는다.
- 각 개정 문서는 원본 항목 코드, 제목, 대상 플랫폼, 편집 상태 `final`과 공식 참고 문헌 URL을 기록한다.
- 개정 본문은 원본과 같은 `개요`, `점검 대상 및 판단 기준`, `점검 및 조치 사례` 구성을 사용한다. 점검 내용, 점검 목적, 보안 위협, 대상, 양호·취약 판단 기준, 조치 방법과 조치 시 영향을 포함하고 RHEL 10, Ubuntu 26.04 LTS, Debian 13별 번호가 있는 절차를 제공한다.
- 설명은 원본의 명사형 점검·조치 문장 형식을 따른다. 원문에서 현재도 유효한 목적과 위협 설명은 보존하되 최신 배포판과 맞지 않는 절차를 재사용해서는 안 된다.
- 공식 배포판 문서는 개정 내용의 근거다. 원본 PDF의 원문 범위를 개정 내용의 근거로 재사용해서는 안 된다.
- 개정판은 `/revised/` 아래에 별도 HTML과 데이터셋을 생성한다. 원본 공개 경로, 382개 정본 점검항목과 원본 검색 데이터셋 계약은 유지한다.
- 개정 페이지는 원본과 같은 항목·목록·검색 템플릿, 목차, 판단 기준, 코드 블록, 구문 강조와 이전·다음 탐색을 사용한다. 별도 초안 화면이나 검토용 안내문을 본문에 삽입하지 않는다.
- `final`은 편집이 완성된 판본을 뜻하며 실제 배포판 실행 검증 또는 사람 승인을 나타내지 않는다. 비공식 판본의 범위와 운영 검증 상태는 운영 문서에서 관리한다.
- 원문 릴리스 승인과 개정판 검토는 별개다. 개정판 작성으로 원문 검토 상태를 승격해서는 안 된다.

### 원본 계층

- 원본 PDF는 변경하지 않는다.
- 원본 파일의 SHA-256 체크섬, 파일 크기, 페이지 수, 발행일, 원문 URL을 원문 레지스트리에 기록한다.
- 원본 텍스트 레이어 추출물, OCR 전사본, 페이지 렌더링은 원문 위치 탐색, 검색, 감사, QA에 사용한다.
- OCR 범위에는 스크린샷, 도표, 표를 포함해 PDF 내부 이미지에 시각적으로 포함된 모든 관련 문자가 들어가야 한다.
- 전사본은 원문 위치를 찾는 보조 자료이며 내용 판정의 기준이 되는 원문이 아니다. 전사본 또는 텍스트 레이어 추출 결과만으로 내용을 판정해서는 안 된다.
- 최종 내용과 구조는 체크섬이 고정된 원본 PDF와 해당 PDF에서 생성한 관련 페이지 이미지를 시각 대조해 판정한다.

### Codex semantic candidate 계층

권장 변환 경로에는 다음 규칙을 적용한다.

- 권장 변환 경로는 `conversion.codex_agent_pipeline`의 Codex-native 파이프라인이다. 구조화된 노드 JSON과 결정론적 변환 후보 렌더러를 사용하는 기존 파이프라인은 레거시 마이그레이션 경로로만 유지한다.
- 컨트롤러는 항목별 현재 Markdown과 provenance에서 원문 페이지, 전사본, 관련된 모든 PDF 페이지 이미지, 체크섬, 해당 대상의 taxonomy 부분을 결합한 작업을 만든다. 이를 축약 정본 참조 자료, 프롬프트 계약, status 스키마와 함께 변경 불가 작업 공간에 저장한다. 원본 Markdown과 provenance를 작업 공간에 중복 복사해서는 안 된다.
- 작업 공간은 `.artifacts/work/codex-agent/jobs/<criterionSlug>/<taskChecksum>/workspace/`에 생성한다. 작업 체크섬은 작업 공간 입력과 변환 계약을 결합한 콘텐츠 주소여야 한다.
- Codex는 항목별 작업 공간만 쓰기 가능한 루트로 사용해야 하며 저장소를 쓰기 가능한 루트로 지정해서는 안 된다. `workspace-write` 샌드박스와 일회성 세션을 유지하고 관련된 모든 PDF 페이지 이미지를 시각적으로 직접 검사해야 한다. 전사본만 검사하거나 페이지 이미지를 표본 추출해서는 안 된다.
- Codex CLI는 사용자 설정을 기본적으로 무시해야 한다. OpenCodeX를 통해 Claude 같은 사용자 정의 provider를 사용하는 경우에만 명시적 옵션으로 사용자 설정을 로드하고 provider를 명시한 모델 식별자를 지정해야 한다.
- 사용자 설정을 로드해도 항목별 작업 공간 샌드박스, 일회성 세션, JSONL 이벤트 저장, status 출력 스키마 검증을 유지해야 한다. 사용자 설정은 provider 외에 MCP 서버와 기타 실행 설정도 포함할 수 있으므로 신뢰할 수 있는 설정만 사용해야 한다.
- Codex는 `conversion/prompts/criterion-agent-v1.md` 계약에 따라 `output/criterion.md`, `output/provenance.yaml`, `output/status.json`을 직접 작성하고 종료 전에 격리된 작업 공간의 운영 검증기를 실행해야 한다. 컨트롤러는 Codex가 작성한 내용, 구조, taxonomy 선택, 원문 주석 또는 provenance를 다시 작성하거나 추론해서는 안 된다.
- `output/criterion.md`는 YAML front matter와 의미 구조를 갖춘 본문을 포함하는 완전한 정본 형식의 변환 후보여야 한다. `output/provenance.yaml`은 파싱한 모든 Markdown 리프를 문서 순서대로 연결하는 완전한 provenance 사이드카여야 한다.
- 에이전트 계약 버전 1은 원문 페이지에서 잘라낸 이미지를 변환 후보 자산으로 게시해서는 안 되며 provenance의 `assets`는 빈 배열이어야 한다.
- Codex의 마지막 응답은 `schemas/codex-agent-status.schema.json` 버전 1을 만족하는 선언 범위가 제한된 status JSON이어야 한다. Status는 작업 식별자와 체크섬, `candidateWritten`, `complete` 또는 `needsSourceReview`, 검토한 모든 실제 페이지, 미해결 질문만 선언할 수 있다.
- 판독이나 구조가 불확실하면 내용을 추정하지 말고 변환 후보 front matter의 `sourceAnnotations`, status의 `analysisStatus`와 `unresolvedQuestions`에 불확실성을 보존해야 한다.
- 결정론적 컨트롤러는 작업 공간의 파일 허용 목록, 심볼릭 링크 부재, 변경 불가 입력 체크섬, status 식별 정보, 메타데이터와 provenance 스키마, 정본 Markdown 구조, 기술 리터럴, taxonomy 식별자, Markdown-provenance 블록 참조 일치, 원문 페이지 영역 범위와 페이지 포함 범위를 검증해야 한다.
- 스키마, 격리 경계, 의미 구조 또는 provenance 검증에 실패한 결과는 검증을 통과한 변환 후보로 취급하거나 정본 콘텐츠에 반영해서는 안 된다.
- 검증 결과는 변환 후보, provenance, status 체크섬, `validationStatus: passed`, `canonicalApplied: false`를 실행 manifest에 기록해야 한다.
- Codex 결과는 `structured`, `visuallyReviewed`, `approved` 상태를 자동으로 부여해서는 안 된다.
- 변환 후보를 정본 점검항목 패키지로 반영하는 단계는 별도의 사람 검토와 명시적 적용 작업이 필요하다.

#### Legacy structured-JSON migration 경계

- 변환 코드는 항목별 원문 페이지, 전사본, 관련된 모든 PDF 페이지 이미지, 체크섬, 정책 버전, 스키마 버전을 변경 불가 작업으로 생성한다.
- Codex는 읽기 전용 샌드박스에서 관련된 모든 PDF 페이지 이미지를 시각적으로 직접 검사하고 스키마로 제약한 JSON만 생성한다. 전사본만 검사하거나 페이지 이미지를 표본 추출해서는 안 된다.
- Codex CLI는 사용자 설정을 기본적으로 무시해야 한다. OpenCodeX를 통해 Claude 같은 사용자 정의 provider를 사용하는 경우에만 명시적 옵션으로 사용자 설정을 로드하고 provider를 명시한 모델 식별자를 지정해야 한다.
- 사용자 설정을 로드해도 읽기 전용 샌드박스, 일회성 세션, JSONL 이벤트 저장, 출력 스키마 검증을 유지해야 한다. 사용자 설정은 provider 외에 MCP 서버와 기타 실행 설정도 포함할 수 있으므로 신뢰할 수 있는 설정만 사용해야 한다.
- Codex 결과는 사람과 기계의 가독성을 모두 충족하도록 제목, 문단, 목록, 참고 문구, 유형을 지정한 코드 블록, 의미론적 표, 이미지를 명시적인 의미 노드로 표현해야 한다. 유형을 지정한 코드 블록과 의미론적 표에는 이 정책의 `절차와 명령어` 및 `표` 규칙을 적용한다.
- 모든 노드에 provenance인 원문 범위를 기록한다. 판독이나 구조가 불확실하면 내용을 추정하지 말고 `analysisStatus`, `sourceAnnotations`, `quality.unresolvedQuestions`에 불확실성을 보존한다.
- Codex는 정본 Markdown, provenance, 레지스트리, 검토 상태를 직접 수정해서는 안 된다.
- Codex 결과의 원문 페이지 포함 범위, 원문 발췌문, 기술 리터럴, 제목 계층, 주석 대상을 결정론적 importer가 검증한다.
- 스키마 또는 의미 검증에 실패한 결과는 변환 후보로 렌더링하거나 정본 콘텐츠에 반영해서는 안 된다.
- 검증된 결과는 `.artifacts/work/codex/candidates/<criterionSlug>/` 아래의 검토 전용 산출물로 생성한다.
- Codex 결과는 `structured`, `visuallyReviewed`, `approved` 상태를 자동으로 부여해서는 안 된다.
- 변환 후보를 정본 점검항목 패키지로 반영하는 단계는 별도의 사람 검토와 명시적 적용 작업이 필요하다.

### Codex-native 전체 corpus 병렬 변환

- 전체 변환 대상은 `data/criteria-manifest.yaml`의 레코드 순서대로 선택한 모든 `extractedCriterion` 항목이다. 일부 slug만 담은 허용 목록을 지정해도 대상과 summary 항목은 manifest 순서를 유지해야 하며 워커의 완료 순서에 의존해서는 안 된다.
- 각 항목은 콘텐츠 주소 기반 작업 공간을 독립적으로 생성하고 실행해야 한다. 병렬 워커 수는 1부터 16까지 설정할 수 있어야 하며 기본값은 4이다.
- 병렬 실행은 항목별 Codex 작업 공간만 변경할 수 있고 정본 Markdown, 레지스트리 또는 검토 상태에 변경을 적용해서는 안 된다.
- `--dry-run`은 작업 공간과 summary를 생성하되 Codex를 실행해서는 안 된다.
- 재개 실행은 현재 입력에서 같은 콘텐츠 주소를 다시 계산해야 한다. 기존 실행의 성공 상태, 작업 체크섬, 모델 식별자, 사용자 설정 로드 여부가 현재 요청과 일치하고, 변환 후보 패키지 전체를 현재 검증기로 재검증한 결과가 실행 manifest의 검증 레코드와 정확히 일치하는 경우에만 `skipped`로 기록해야 한다.
- 변환 후보, provenance 또는 status가 누락·변경됐거나 재검증에 실패하면 완료 산출물을 재사용해서는 안 된다. 이전 모델 실행이 변환 후보를 작성했지만 검증만 실패한 경우에는 현재 검증기로 먼저 재검증해야 하며, 재검증을 통과하면 Codex를 다시 실행해서는 안 된다.
- 한 항목의 실패는 다른 항목의 작업 공간과 상태를 변경해서는 안 된다. 기본 실행은 독립 항목을 계속 처리하고 `.artifacts/work/codex-agent/summary.json`에 `completed`, `skipped`, `dryRun`, `validationFailed`, `failed` 건수와 manifest 순서의 항목을 기록해야 한다. 하나라도 실패하면 summary 상태는 `completedWithFailures`이고 명령은 0이 아닌 종료 코드를 반환해야 한다.
- 워커 수를 늘리기 전에 Codex 서비스의 요청 빈도 제한, 동시 요청 한도, 항목별 PDF 페이지 이미지 수, 모델 컨텍스트와 입력 토큰 사용량, 프로세스별 메모리 사용량을 확인해야 한다. 요청 빈도 제한에 도달하거나 자원이 부족해지면 워커 수를 줄이고 체크섬 기반 재개를 사용해야 한다.

### Legacy structured-JSON 전체 corpus 병렬 변환

- 전체 변환 대상은 `data/criteria-manifest.yaml`의 레코드 순서대로 선택한 모든 `extractedCriterion` 항목이다. 일부 slug만 담은 허용 목록을 지정해도 대상은 manifest 순서로 필터링해야 한다. 실행 순서와 summary 항목 순서는 이 순서를 유지해야 하며, 워커의 완료 순서에 의존해서는 안 된다.
- 각 항목은 `taskBuild`, `visionRun`, `importer`의 세 단계를 순서대로 실행한다. 한 항목의 단계별 산출물은 `.artifacts/work/codex/tasks/<criterionSlug>/`, `.artifacts/work/codex/results/<criterionSlug>/`, `.artifacts/work/codex/candidates/<criterionSlug>/`에 격리해야 한다.
- 병렬 워커 수는 1부터 16까지 설정할 수 있어야 한다. 기본값은 `min(2, max(1, logicalCpuCount))`로 계산하고, 전체 문서 실행에는 이 작은 기본값을 사용해야 한다.
- 병렬 실행은 항목별 읽기 전용 Codex 분석만 동시에 수행해야 한다. 변환 후보를 정본 Markdown, provenance, 레지스트리에 적용하거나 검토 상태를 변경하는 작업을 포함해서는 안 된다.
- 재개 실행도 각 작업을 현재 입력에서 다시 생성해야 한다. 실행 manifest의 `schemaVersion`, 작업 식별자와 체크섬, 결과 체크섬, 모델, 사용자 설정 로드 여부, 성공 상태를 현재 요청과 대조해야 한다. 변환 후보의 결과와 변환 후보 체크섬, `validationStatus: passed`, `canonicalApplied: false`도 모두 검증한 경우에만 건너뛸 수 있다. 결과만 현재 작업과 실행 설정에 유효하면 importer부터 재개하고, 검증이 누락되거나 불일치하면 Codex 시각 분석부터 다시 처리해야 한다.
- 한 항목의 실패는 다른 항목의 산출물과 상태를 변경해서는 안 된다. 기본 실행은 독립 항목을 계속 처리하고, 최종 summary에 `taskBuild`, `visionRun`, `importer` 상태, 항목별 결과, 오류를 manifest 순서로 기록해야 한다. Summary는 `schemas/codex-bulk-summary.schema.json`으로 검증한 뒤 원자적으로 교체해야 한다. Fail-fast 실행도 이미 실행 중인 워커의 처리를 정리하고 아직 시작하지 않은 항목을 `cancelled`로 기록해야 한다.
- Codex 재시도 기본값은 0이어야 하며 명시적인 재시도만 허용한다. 재시도 횟수는 최대 5, 결정론적 지수 백오프의 기준 대기 시간과 각 대기 시간은 0초부터 300초까지로 제한해야 한다.
- 워커 수를 늘리기 전에 Codex 서비스의 요청 빈도 제한, 동시 요청 한도, 항목별 PDF 페이지 이미지 수, 모델 컨텍스트와 입력 토큰 사용량, 프로세스별 메모리 사용량을 확인해야 한다. 요청 빈도 제한에 도달하거나 자원이 부족해지면 워커 수를 줄이고 체크섬 기반 재개를 사용해야 한다.

### 실행 로그와 진행률

- 공통 런타임 로거를 사용하는 `conversion/` 실행 도구는 시작, 완료, 실패와 주요 단계 상태를 기록해야 한다. Codex-native 파이프라인은 항목별 `run.json`, 원시 `events.jsonl`, `stderr.log`와 전체 문서의 `summary.json`을 실행 기록으로 사용한다.
- 기존 명령 결과와 산출물 경로의 stdout 계약을 변경해서는 안 된다. 사용자용 콘솔 로그와 진행률은 stderr로 출력해야 한다.
- 파일 로그는 UTF-8 JSON Lines를 사용하고 UTC 타임스탬프, 로그 수준, 도구, 이벤트, 프로세스 식별자, 스레드 식별자, 컨텍스트를 포함해야 한다.
- 병렬 워커는 프로세스별 로그 파일을 사용해야 한다. 여러 프로세스가 같은 파일에 직접 기록해서는 안 된다.
- API 키, 인증 값, 토큰, 비밀번호, 자격 증명이 포함된 URL과 알려진 자격 증명 형식은 콘솔과 파일 로그 양쪽에서 제거해야 한다.
- 일괄 처리 진행률은 부모 프로세스만 갱신하고 완료 수, 전체 수, 백분율, 경과 시간, 처리율, 결과별 건수를 제공해야 한다.
- TTY에서는 한 줄을 갱신하고 종료 시 줄바꿈을 기록해야 한다. CI와 non-TTY에서는 캐리지 리턴 없이 완전한 줄을 기록해야 한다.
- 공통 런타임 로거 기반 실행 도구는 `--log-level`, `--log-directory`를 지원해야 한다. 레거시 일괄 실행 도구는 진행률을 비활성화하는 `--no-progress`를 추가로 지원해야 한다.
- 기본 파일 로그 경로인 `.artifacts/work/logs/`와 변환 작업 경로인 `.artifacts/work/codex-agent/`, `.artifacts/work/codex/`는 생성 산출물이며 Git에 포함해서는 안 된다.

#### Codex 통신 로그

- `codex exec --json`의 stdout은 Codex-native 파이프라인에서 `.artifacts/work/codex-agent/jobs/<criterionSlug>/<taskChecksum>/events.jsonl`, legacy 파이프라인에서 `.artifacts/work/codex/results/<criterionSlug>/events.jsonl`에 변형 없이 저장해야 한다. 이 원시 산출물은 런타임 JSONL이 아니며 민감 정보 제거 또는 콘텐츠 필터링을 거친 운영 로그로 취급해서는 안 된다.
- Codex가 반환한 이벤트의 `type`은 `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*`, `error`를 포함한다. 이벤트 유형이 추가되더라도 본문을 런타임 JSONL로 전달해서는 안 된다.
- `thread.started.thread_id`, 이벤트와 `item.type`별 건수, JSON 객체 수와 유효하지 않은 JSON 줄 수, `turn.completed.usage`의 0 이상의 정수 `*_tokens` 필드만 원시 이벤트 스트림에서 런타임 집계값으로 추출해야 한다.
- `item_type_counts`는 `item.type`이 있는 이벤트 수를 세어야 한다. 에이전트 메시지, 추론, 명령 실행 등 item의 본문을 읽거나 저장해서는 안 된다.
- `events.jsonl`은 에이전트 메시지, 추론, 명령, 파일 변경, 도구 호출 등 본문을 담은 item을 포함할 수 있으므로 생성 작업 산출물과 같은 접근·보존 정책을 적용해야 한다.

레거시 런타임 로거가 기록하는 Codex 통신 이벤트와 통신 전용 컨텍스트 필드는 다음 허용 목록으로 제한한다. 일괄 처리 워커의 공통 컨텍스트인 `process_role`은 추가로 포함할 수 있다.

| 런타임 이벤트 | 필수 컨텍스트 필드 | 추가 컨텍스트 필드 |
| --- | --- | --- |
| `codex.request.prepared` | `slug`, `model`, `user_config_loaded`, `codex_version`, `image_count`, `schema_path`, `task_identifier`, `task_checksum`, `output_paths` | 없음 |
| `codex.request.planned` | `slug`, `model`, `user_config_loaded`, `codex_version`, `image_count`, `schema_path`, `task_identifier`, `task_checksum`, `output_paths` | 없음 |
| `codex.request.started` | `slug`, `model`, `user_config_loaded`, `codex_version`, `image_count`, `schema_path`, `task_identifier`, `task_checksum`, `output_paths` | 없음 |
| `codex.response.completed` | 공통 요청 필드, `exit_code`, `duration_seconds`, `result_checksum`, `schema_validation`, `thread_id`, `total_event_count`, `invalid_json_line_count`, `event_type_counts`, `item_type_counts`, `usage` | 없음 |
| `codex.response.failed` | 공통 요청 필드, `exit_code`, `duration_seconds`, `result_checksum`, `schema_validation`, `thread_id`, `total_event_count`, `invalid_json_line_count`, `event_type_counts`, `item_type_counts`, `usage` | `error_type` |

레거시 런타임 로거의 `output_paths`는 `events`, `result`, `run`, `stderr` 경로만 포함해야 한다. `schema_validation`은 `passed`, `failed`, `not_run` 중 하나여야 한다. `usage`는 모든 `turn.completed` 이벤트에서 검증한 `*_tokens` 값을 합산해야 한다. 런타임 레코드의 공통 구조는 기존 `schema_version`, `timestamp`, `level`, `tool`, `event`, `message`, `process_id`, `run_id`, `thread`, `context` 계약을 유지해야 한다. `message`는 고정된 수명 주기 설명만 포함해야 하며 상위 도구가 반환한 콘텐츠를 포함해서는 안 된다.

- 런타임 JSONL은 프롬프트, 작업 또는 원문 콘텐츠, 상위 에이전트나 오류 메시지 본문, 추론 또는 추론 요약, 명령·인자·stdout·stderr 본문, 파일 변경이나 패치 본문, 도구 입출력, 원시 이벤트나 item을 포함해서는 안 된다.
- 런타임 JSONL은 API 키, 인증 값, 토큰, 비밀번호, 자격 증명이 포함된 URL 또는 알려진 자격 증명 형식을 포함해서는 안 된다. 민감 정보를 제거하더라도 허용 목록 밖의 Codex 콘텐츠 필드를 기록해서는 안 된다.
- Codex 실패를 상위 명령, 재시도, 단계 또는 워커 이벤트에 전달할 때도 본문을 담은 오류 세부 정보를 복제해서는 안 된다. 일반 실패 상태, 오류 유형, 종료 코드, 집계값과 원시 산출물 위치만 기록해야 한다.

### Canonical 콘텐츠 계층

- 각 점검항목의 패키지를 사람이 편집하는 정본 콘텐츠로 사용한다.
- 점검항목 패키지는 Markdown, YAML front matter, 필수 provenance 사이드카, 선택적인 표 사이드카, 원본 자산으로 구성한다.
- 기본 파일은 `content/criteria/<domainIdentifier>/<criterionSlug>.md` 형식을 사용한다.
- 복잡한 표는 `content/criteria/<domainIdentifier>/<criterionSlug>.tables.yaml`에 저장한다.
- 블록 단위 provenance와 자산 메타데이터는 `content/criteria/<domainIdentifier>/<criterionSlug>.provenance.yaml`에 저장해야 한다.
- 원본 자산은 `content/assets/<criterionSlug>/` 아래에 저장한다.
- Markdown은 CommonMark 문법을 기본으로 사용한다.
- 허용 확장은 YAML front matter와 GFM 표로 제한한다.
- 유형별 참고 문구는 이 문서에서 정의한 CommonMark blockquote 작성 규칙으로 표현한다.
- 명령, 설정, 출력, 리터럴은 이 문서에서 정의한 코드 펜스 정보 문자열로 구분한다.
- 원시 HTML과 MDX 실행 코드는 기본적으로 허용하지 않는다.
- 예외 문법을 추가하기 전에 전체 PDF의 콘텐츠 유형과 파서 영향을 검토해야 한다.

### 정규화 데이터 계층

- 빌드 과정은 `criterion package -> Markdown first-pass AST -> sidecar reference 병합 -> validated AST -> normalized JSON`
  단일 경로를 사용한다.
- 렌더러, 검색 색인 생성기, 인쇄 생성기는 Markdown을 직접 읽지 않고 정규화 JSON만 사용한다.
- 메타데이터와 정규화 JSON은 JSON Schema Draft 2020-12로 검증한다.
- 정규화 JSON은 본문 의미 구조와 원문 출처 정보를 포함해야 한다.
- 정규화 JSON을 직접 수정해서는 안 된다.

### 표시 계층

- 의미론적 HTML, 항목별 공개 JSON 데이터셋, 검색 색인, 최적화 이미지, 인쇄 결과는 정규화 JSON과 정본 자산에서 생성한다.
- 표시 계층은 원문의 의미와 순서를 변경해서는 안 된다.
- 생성 파일을 직접 수정해서는 안 된다.

### Canonical registry

다음 레지스트리와 스키마를 정본 입력으로 관리한다.

- `data/source-registry.yaml`
- `data/taxonomy.yaml`
- `data/criteria-manifest.yaml`
- `data/page-region-inventory.yaml`
- `data/review-registry.yaml`
- `data/source-annotations.yaml`
- `data/policy-exceptions.yaml`
- `data/test-profile.yaml`
- `schemas/source-registry.schema.json`
- `schemas/taxonomy.schema.json`
- `schemas/criteria-manifest.schema.json`
- `schemas/page-region-inventory.schema.json`
- `schemas/review-registry.schema.json`
- `schemas/source-annotations.schema.json`
- `schemas/policy-exceptions.schema.json`
- `schemas/test-profile.schema.json`
- `schemas/criterion-metadata.schema.json`
- `schemas/table-sidecar.schema.json`
- `schemas/provenance-sidecar.schema.json`
- `schemas/normalized-criterion.schema.json`
- `schemas/search-index.schema.json`

모든 YAML과 JSON 속성 이름은 축약하지 않은 영단어를 lower camel case로 표기한다.

### YAML profile

- YAML 1.2 Core Schema를 사용한다.
- UTF-8과 LF 줄바꿈을 사용하고 파일 끝에도 줄바꿈을 둔다.
- 중복 키, 앵커, alias, merge key를 허용하지 않는다.
- 날짜, 숫자, boolean으로 오인될 수 있는 문자열은 따옴표로 감싼다.
- YAML 1.2 Core Schema의 표준 스칼라 자료형 결정 규칙을 적용한다.
- JSON Schema가 요구하는 자료형과 다르게 해석된 결과는 검증 오류로 처리한다.
- 메타데이터 키와 일반 산문은 Unicode NFC로 정규화한다.
- 명령어, 경로, 설정값 같은 기술 리터럴은 Unicode 정규화 대상에서 제외한다.

## Source registry

원문 레지스트리는 원본 문서별로 다음 정보를 한 번만 보관한다.

- 문서 식별자
- 원문 제목
- 발행 기관
- 발행일
- 원문 게시 URL
- 저장소 내 파일 경로
- 파일 크기
- 전체 실제 페이지 수
- 체크섬 알고리즘
- 체크섬 값
- 공개 라이선스 표시문

원문 레지스트리는 스키마 버전을 가져야 한다. 문서 식별자와 체크섬은 저장소 전체에서 유일해야 한다.
공개 사이트는 `license` 값을 `라이선스: <value>` 형식으로 모든 HTML의 공통 푸터에 표시한다.
라이선스는 별도 승인 조건으로 사용하지 않는다. 원본 PDF는 생성 사이트 산출물에 복사하지 않고 원문 게시물 URL만 제공한다.

Taxonomy 레지스트리는 분야, 분류, 대상의 식별자, 표시 레이블, 원문 레이블, 순서를 관리한다.
점검항목 메타데이터는 taxonomy 식별자만 저장하고, 표시 레이블과 순서는 레지스트리에서 생성한다.

점검항목 manifest는 각 점검항목에 대해 다음 기준값을 저장한다.

- 원문 코드와 제목
- 원문 중요도
- 분야와 분류 식별자
- 콘텐츠 모델과 콘텐츠 모델 버전
- 원문의 시작·종료 페이지 영역
- 기대 경로
- 예상 기술 리터럴 목록의 위치

`data/source-annotations.yaml`은 문서, 탐색, 페이지 영역 수준의 원문 이상을 저장한다.
점검항목 본문 또는 메타데이터에 한정된 원문 이상은 해당 점검항목 front matter의 `sourceAnnotations`에 저장한다.
공개 원문 이상 목록은 두 정본 주석 원천에서 생성한다.

## Canonical metadata

모든 점검항목은 다음 구조와 동등한 메타데이터를 포함해야 한다.

```yaml
---
schemaVersion: 1
contentModel: systemCriterion
contentModelVersion: 1

criterion:
  code: U-01
  slug: u-01
  title: root 계정 원격 접속 제한
  severity:
    level: high
    sourceLabel: 상

classification:
  domainIdentifier: unix
  categoryIdentifier: account-management

targetScope: nonExhaustive
targetIdentifiers:
  - solaris
  - linux
  - aix
  - hp-ux
sourceTargetText: "SOLARIS, LINUX, AIX, HP-UX 등"

provenance:
  sourceDocumentIdentifier: kisa-cce-criteria-2026
  sourcePageRanges:
    - physicalPageStart: 12
      physicalPageEnd: 14
      printedPageStart: "12"
      printedPageEnd: "14"

sourceAnnotations:
  - annotationIdentifier: u-01-source-001
    annotationType: sourceInconsistency
    targetType: astNode
    targetReference: "u-01:remediation.hp-ux.telnet.step:1"
    sourceLocation:
      physicalPage: 14
      printedPage: "14"
      pageRegionIdentifier: p14-u-01
    sourceText: "etc/securetty"
    explanation: "다음 참고 문구에서는 /etc/securetty를 사용한다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 14의 절차와 바로 다음 참고 문구를 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
  - annotationIdentifier: u-01-source-002
    annotationType: sourceDuplication
    targetType: astNode
    targetReference: "u-01:remediation.linux.telnet.step:3"
    sourceLocation:
      physicalPage: 13
      printedPage: "13"
      pageRegionIdentifier: p13-u-01
    sourceText: "auth required /lib/security/pam_securetty.so"
    explanation: "Step 1과 Step 3에 같은 PAM 설정이 반복된다."
    disposition: unresolved
    reviewStatus: pending
    verificationEvidence:
      - "PDF physical page 13의 Linux Telnet Step 1과 Step 3을 대조했다."
    reviewedBy: null
    reviewedAt: null
    approvedBy: null
    approvedAt: null
---
```

### Metadata 규칙

- 모든 식별자 이름은 축약하지 않은 영단어를 사용한다.
- YAML, 레지스트리, manifest, 정규화 JSON, 검색 색인은 lower camel case를 사용한다.
- `cate`, `cfg`, `src`, `ref`, `desc` 같은 축약 필드를 사용해서는 안 된다.
- `criterion.code`는 원문의 대문자 코드를 보존해야 한다.
- `criterion.slug`는 파일 경로와 URL에 사용한다.
- `criterion.title`에는 코드와 중요도를 중복해서 포함하지 않는다.
- `classification`은 분류 경로 문자열이 아니라 taxonomy 식별자를 포함해야 한다.
- 분야, 분류, 대상의 레이블과 순서를 점검항목 메타데이터에 중복 저장해서는 안 된다.
- `targetScope`는 `exhaustive` 또는 `nonExhaustive` 중 하나여야 한다.
- `sourceTargetText`는 원문의 `등`과 같은 비한정 표현을 보존해야 한다.
- `severity.level`은 `high`, `medium`, `low` 중 하나여야 한다.
- `severity.sourceLabel`은 원문의 `상`, `중`, `하`를 보존해야 한다.
- 원문 페이지 범위는 시작과 끝을 포함한 범위로 기록한다.
- 실제 페이지는 PDF의 첫 페이지를 1로 세는 페이지 번호로 기록한다.
- 인쇄 페이지는 로마 숫자와 숫자가 아닌 레이블을 보존할 수 있도록 문자열로 기록한다.
- 스키마에 선언되지 않은 메타데이터 필드는 허용하지 않는다.

### 코드와 경로

- 코드의 유효성은 단일 정규식이 아니라 기준 manifest의 허용 코드 목록으로 검증한다.
- `U-01`과 `CI`처럼 형식이 다른 원문 코드를 모두 지원해야 한다.
- `criterion.code`는 최초 배포 후 변경해서는 안 된다.
- `criterion.slug`는 원문 코드를 ASCII 소문자로 변환한 값이어야 한다. `U-01`은 `u-01`, `CI`는 `ci`로 변환한다.
- Slug는 `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$` 형식을 충족해야 한다.
- Slug와 경로는 저장소 전체에서 유일해야 한다.
- 파일 경로는 `content/criteria/<domainIdentifier>/<criterionSlug>.md` 형식을 사용한다.
- 점검항목 경로는 `/<domainIdentifier>/<criterionSlug>/` 형식을 사용한다.
- 예약된 경로와의 충돌은 빌드 오류로 처리한다.
- 경로와 앵커는 제목이 아니라 코드와 의미 역할에서 생성한다.
- 제목 변경으로 경로와 앵커가 변경되어서는 안 된다.
- 배포된 경로를 변경할 경우 redirect manifest를 제공해야 한다.

## 본문 구조

렌더러는 메타데이터를 이용해 H1을 생성한다. Markdown 본문은 H2부터 시작한다.

`content/criteria/unix/u-01.md`는 이 정책의 정본 서식 기준 문서다. 변환을 완료한 모든 점검항목은 이 문서와 동일한 제목 구성,
서식, 표기 규약을 따라야 한다. 이 절과 `정본 서식 계약` 절이 상충하면 `정본 서식 계약`을 우선 적용한다.

시스템 점검항목의 기본 구조는 다음과 같다.

```markdown
## 개요

### 점검 내용

### 점검 목적

### 보안 위협

### 참고

## 점검 대상 및 판단 기준

### 대상

### 판단 기준

### 조치 방법

### 조치 시 영향

## 점검 및 조치 사례

### 운영체제 또는 제품군

#### 서비스, 프로토콜 또는 세부 환경
```

## 정본 서식 계약

변환을 완료한 모든 점검항목은 `content/criteria/unix/u-01.md`와 동일한 서식 계약을 따라야 한다. 이 계약은
`systemCriterion`과 `webApplicationCriterion`에 공통 적용한다. `extractedCriterion`은 변환 완료 상태가 아닌
중간 산출물이며 `원문 전사` 구조를 사용한다.

### Heading 계약

- H2는 `개요`, `점검 대상 및 판단 기준`, `점검 및 조치 사례` 세 개여야 하며 이 순서를 지켜야 한다.
  제목 전체가 일치해야 하며 접두어만 일치해서는 안 된다. 그 밖의 H2를 추가해서는 안 된다.
- `개요` 아래 H3는 `점검 내용`, `점검 목적`, `보안 위협`, `참고` 네 개여야 하며 이 순서를 지켜야 한다.
- `점검 대상 및 판단 기준` 아래 H3는 `대상`, `판단 기준`, `조치 방법`, `조치 시 영향` 네 개여야 하며
  순서가 정확히 일치해야 한다.
- `점검 및 조치 사례` 아래에는 대상 플랫폼 또는 제품군 H3가 하나 이상 있어야 한다.
- `추가 지침` H3를 사용하는 경우 `점검 및 조치 사례` 아래의 마지막 H3여야 한다.
- 원문에 특정 고정 섹션의 내용이 없더라도 제목을 생략해서는 안 된다. 원문에 내용이 없다는 사실은
  `sourceAnnotations`와 검토 상태로 기록한다.

### 고정 섹션 본문 서식

| 섹션 | 본문 형식 |
| --- | --- |
| `점검 내용` | 단일 문단 |
| `점검 목적` | 단일 문단 |
| `보안 위협` | 단일 문단 |
| `참고` | 참고 blockquote |
| `대상` | 단일 문단. 원문 대상 문자열을 `sourceTargetText`와 동일하게 보존한다 |
| `판단 기준` | 양호와 취약 두 항목의 순서 없는 목록 |
| `조치 방법` | 단일 문단 |
| `조치 시 영향` | 단일 문단. 원문이 여러 항목을 나열하면 순서 없는 목록 |

- 고정 섹션 본문에 제목을 추가해서는 안 된다.
- 원문 문말 표현을 보존한다. 임의로 문체를 통일해서는 안 된다.

### 판단 기준 표기

`판단 기준`은 다음 표기를 사용한다. 콜론은 strong 범위 안에 포함하고 콜론 뒤에 공백 한 칸을 둔다.

```markdown
- **양호:** 원격터미널 서비스를 사용하지 않거나, 사용 시 root 직접 접속을 차단한 경우
- **취약:** 원격터미널 서비스 사용 시 root 직접 접속을 허용한 경우
```

- 양호 항목과 취약 항목은 각각 정확히 하나여야 한다.
- 양호 항목이 취약 항목보다 먼저 와야 한다.
- `양호`, `취약` 이외의 판정 레이블을 사용해서는 안 된다.

### 조치 사례 heading 표기

- 운영체제와 제품군 H3는 원문 표기를 보존한다. `SOLARIS`, `LINUX`, `AIX`, `HP-UX`처럼 원문이 대문자면
  대문자를 유지한다.
- 서비스, 프로토콜, 배포판 H4는 원문 표기를 보존한다. `Telnet`, `SSH`, `Redhat`, `Debian`처럼 원문이
  대소문자를 혼용하면 그대로 유지한다.
- 대상 플랫폼 아래에 서비스나 세부 환경 구분이 없으면 H4를 생략하고 H3 아래에 절차를 배치한다.
- H3와 H4의 식별자는 taxonomy에 등록된 값이어야 한다.

### 절차와 코드 블록 배치

절차는 순서 있는 목록으로 작성하고 각 코드 블록은 해당 항목의 자식 블록으로 배치한다.

````markdown
1. `/etc/default/login` 파일 내에 `CONSOLE` 설정값 수정

   ```text configuration
   CONSOLE=/dev/console
   ```
````

- 코드 블록은 공백 세 칸으로 들여써서 상위 목록 항목에 소속시킨다. 탭을 사용해서는 안 된다.
- 목록 항목 본문과 코드 블록 사이, 코드 블록과 다음 목록 항목 사이에 빈 줄 한 줄을 둔다.
- 파일 경로, 설정 키, 명령 이름, 설정값은 항목 본문에서 인라인 코드로 표기한다.
- 항목 본문은 수행할 작업을 서술한다. 명령과 설정값 자체를 본문에 나열해서는 안 된다.
- 단일 절차도 순서 있는 목록으로 작성한다. 문단만으로 절차를 표현해서는 안 된다.

### 참고 blockquote 표기

- 참고 blockquote는 레이블 줄, 빈 `>` 줄, 본문 줄 순서를 사용한다.
- 용어 정의를 나열할 때는 `> - **용어:** 설명` 형식의 목록 항목을 사용한다.
- 본문 중 참고는 관련 절차 또는 섹션 바로 뒤에 배치한다.
- 주제가 다른 참고는 하나의 blockquote에 합치지 않고 각각 분리한다.

```markdown
> **참고**
>
> - **root 계정:** 모든 기능을 관리할 수 있는 총괄 권한을 가진 특별 계정
> - **tty(terminal-teletype):** 서버에 연결된 콘솔로 직접 로그인하는 터미널
```

### Front matter 표기

- 키 순서는 `schemaVersion`, `contentModel`, `contentModelVersion`, `criterion`, `classification`,
  `targetScope`, `targetIdentifiers`, `sourceTargetText`, `provenance`, `sourceAnnotations`를 사용한다.
- 최상위 블록 사이에 빈 줄 한 줄을 둔다.
- 들여쓰기는 공백 두 칸을 사용한다.
- 값이 없는 검토 필드는 생략하지 않고 `null`로 표기한다.

### 정본 서식 검증

- 제목 계약, 판단 기준 표기, 참고 blockquote 작성 규칙, 코드 펜스 정보 문자열은 저장소 검증기가
  강제한다. Codex 결과 importer와 저장소 검증기는 동일한 제목 상수를 사용해야 한다.
- 정본 서식 계약을 변경하려면 `content/criteria/unix/u-01.md`, 이 절, 검증기 규칙, 기준 픽스처를 함께 변경해야 한다.

### 구조 규칙

- 렌더링 결과에는 H1이 정확히 하나만 존재해야 한다.
- 제목 수준을 건너뛰어서는 안 된다.
- 제목을 시각적 글자 크기 조절 용도로 사용해서는 안 된다.
- 기본 제목의 이름과 순서는 콘텐츠 모델 스키마로 검증한다.
- `systemCriterion`은 Unix, Windows, 웹 서비스, 보안 장비, 네트워크 장비, 제어시스템, PC, DBMS, 이동통신, 가상화 장비, 클라우드에 사용한다.
- `webApplicationCriterion`은 Web Application 21개 항목에 사용한다.
- 두 모델은 `정본 서식 계약`의 공통 제목 구조를 사용하되, `점검 및 조치 사례` 아래의 허용 역할과 제목 계층을 별도 스키마로 검증한다.
- `systemCriterion`의 동적 제목은 taxonomy에 등록된 운영체제, 제품군, 서비스, 프로토콜이어야 한다.
- `systemCriterion`은 플랫폼 공통 보충 내용을 위해 `추가 지침` H3 역할과 그 아래 `guidanceTopic` H4 역할을 허용한다.
- `webApplicationCriterion`의 동적 제목은 공격 유형, 점검 방법, 조치 방법, 구현 언어, 제품 역할 중 하나여야 한다.
- `extractedCriterion`은 전체 검색·열람을 위한 자동 전사 상태다. `원문 전사` H2와 `PDF 페이지 N` H3만 허용하며, 사람 검토 전에는 `structured` 또는 `approved`로 승격할 수 없다.
- `extractedCriterion`의 `technicalLiteralInventoryMode`는 `sourceTranscriptSearchableText`를 사용한다. 기술 리터럴을 유형이 지정된 AST로 추출하는 작업이 완료된 것으로 표시해서는 안 된다.
- 변환을 완료한 문서는 분야와 무관하게 `정본 서식 계약`의 제목 구성과 서식을 동일하게 적용한다.
- `점검 및 조치 사례` 아래의 대상 제목 구성은 원문에 따라 분야별로 달라진다. 원문에 없는 대상 제목을 생성해서는 안 된다.
- 스키마에 등록되지 않은 역할의 자유 형식 제목은 허용하지 않는다.
- 새로운 콘텐츠 모델을 추가하려면 메타데이터 스키마, AST 스키마, 파서, 렌더러, 검증기, 기준 픽스처를 함께 추가해야 한다.
- 배포된 앵커를 삭제하거나 재사용해서는 안 된다.

## 원문 충실도

### 허용하는 자동 정규화

다음 변경은 원문의 의미를 변경하지 않는 범위에서 자동 적용할 수 있다.

- 반복 머리말, 꼬리말, 페이지 번호 제거
- 시각적 줄바꿈으로 분리된 문장의 결합
- 일반 문단의 연속 공백 정리
- 시각적 글머리표를 의미론적 목록으로 변환
- `Step 1)` 형식의 절차를 순서 있는 목록으로 변환
- 표지, 목차, 장 표지, 항목 요약표를 점검항목 본문과 분리
- 장식용 배경과 반복 브랜드 요소 제거

### 허용하지 않는 자동 변경

다음 내용은 자동 변경해서는 안 된다.

- 코드, 제목, 중요도, 판단 기준, 항목 순서
- 명령어, 경로, 설정 키, 옵션, URL
- 대소문자, 슬래시, 따옴표, 대시, 주석 문자
- 숫자, 단위, 버전 문자열
- 표의 행·열 순서와 머리글 관계
- 원문의 반복 단계와 중복 문장
- 원문에 없는 사전 조건, 검증 명령, 재시작 명령

기술 리터럴의 공백과 줄바꿈은 실행 의미에 영향을 줄 수 있다. 자동 정규화 대상에서 제외한다.

### Block-level provenance

- 정규화 AST의 모든 리프 블록은 하나 이상의 원문 범위를 가져야 한다.
- Markdown 파서는 첫 파싱 단계에서 각 블록에 `<criterionSlug>:<semanticPath>:<ordinal>` 형식의 `blockReference`를 생성한다.
- `.provenance.yaml`은 모든 `blockReference`를 하나 이상의 원문 범위에 연결해야 한다.
- Markdown 블록과 provenance 사이드카 사이에 누락되거나 사용되지 않는 참조가 있으면 빌드를 실패시킨다.
- 원문 범위는 실제 페이지, 인쇄 페이지, 페이지 영역 식별자를 포함해야 한다.
- 필요한 경우 원문 경계 상자 또는 추출 오프셋을 포함해야 한다.
- 시스템은 한 페이지에 여러 점검항목 또는 탐색과 점검항목이 함께 존재하는 구조를 지원해야 한다.
- 페이지 전체에 단일 역할을 강제하지 않고 페이지 영역별로 역할과 소유권을 기록한다.
- 페이지 영역 경계 상자는 실제 페이지 좌상단을 원점으로 하는 정규화 좌표 `[xMinimum, yMinimum, xMaximum, yMaximum]`을 사용한다.
- 좌표값은 0 이상 1 이하이며, 최솟값은 대응하는 최댓값보다 작아야 한다.
- 페이지 영역 역할은 `frontMatter`, `navigation`, `criterion`, `backMatter`, `excludedDecoration` 중 하나여야 한다.
- 각 콘텐츠 영역은 정확히 하나의 역할과 소유권을 가져야 한다.
- 추출된 텍스트 블록과 수동 식별된 정보성 시각 블록은 정확히 하나의 콘텐츠 영역에 소속되어야 한다.
- 영역 경계 상자는 겹칠 수 있지만 콘텐츠 블록 소유권은 중복될 수 없다.
- 미분류 텍스트 블록과 정보성 시각 블록이 0개일 때 페이지 영역 분류율을 100%로 판정한다.
- 영역은 `published`, `derived`, `excluded` 공개 처리 상태 중 하나를 가져야 한다.
- `published`와 `derived` 영역은 원문 시각 대조를 완료해야 한다.
- `excluded` 영역은 제외 근거를 기록해야 한다.

## 원문 이상과 변환 오류

원문 이상과 변환 오류를 분리해서 관리한다.

| 유형 | 정의 | 처리 |
| --- | --- | --- |
| 변환 오류 | 웹 콘텐츠가 원본 PDF와 다름 | 릴리스 전에 수정 |
| 원문 이상 | PDF 내부 표기가 상충하거나 기술적으로 의심됨 | 원문 보존 후 주석 등록 |
| 편집자 보정 | 검증된 대체 표기 또는 설명 제공 | 원문과 분리하고 근거 표시 |

원문 이상을 본문에서 알리지 않고 수정해서는 안 된다. 주석은 다음 정보를 포함해야 한다.

- 주석 식별자
- 주석 유형
- 대상 유형과 대상 참조
- 원본 실제 페이지와 인쇄 페이지
- 페이지 영역 식별자
- 원문 표기
- 설명
- 처리 상태
- 보정 표기가 있는 경우 대체 내용과 검증 근거
- 승인자와 승인일

처리 상태는 `preserved`, `correctedWithNotice`, `unresolved` 중 하나를 사용한다.

주석 대상 유형은 `astNode`, `metadata`, `pageRegion`, `navigation`, `document` 중 하나를 사용한다.
주석 유형은 `sourceInconsistency`, `sourceDuplication`, `sourceOmission`, `sourceTypographicalError`,
`missingReference`, `conversionDecision` 중 하나를 사용한다.
`metadata` 대상은 JSON Pointer를 사용한다. `pageRegion` 대상은 페이지 영역 식별자를 사용한다.
AST 노드 식별자는 `<criterionSlug>:<semanticPath>:<ordinal>` 형식으로 생성한다.
주석이 연결된 노드 식별자를 변경할 경우 alias 또는 migration mapping을 제공해야 한다.
`correctedWithNotice`에는 `replacementText` 문자열, 비어 있지 않은 `verificationEvidence` 배열,
`approvedBy` 문자열, ISO 8601 UTC `approvedAt` 값이 필요하다.
모든 주석은 `reviewStatus` 값을 가져야 하며, 값은 `pending` 또는 `reviewed` 중 하나여야 한다.
`preserved`와 `unresolved`에는 처리 근거를 설명하는 `verificationEvidence` 배열이 필요하다.
`preserved` 또는 `unresolved` 주석을 `reviewStatus: reviewed`로 변경하려면 비어 있지 않은 `reviewedBy`와
ISO 8601 UTC `reviewedAt` 값이 필요하다.
주석 식별자는 저장소 전체에서 유일해야 한다.

U-01의 다음 항목은 주석 동작을 검증하는 픽스처로 사용한다.

- HP-UX Telnet 절차의 `etc/securetty`와 다음 참고 문구의 `/etc/securetty` 불일치
- Linux Telnet Step 1과 Step 3의 PAM 설정 반복

## 절차와 명령어

### MUST

- 절차는 순서 있는 목록으로 표현한다.
- 순서 있는 목록의 한 항목은 원문의 한 Step을 보존한다.
- 원문 Step 안에 여러 하위 작업이 있으면 중첩 목록으로 표현하고 원문 Step 번호를 변경하지 않는다.
- 명령, 설정값, 예상 출력, 설명을 서로 다른 의미 단위로 분리한다.
- 원문의 주의사항은 영향을 받는 단계와 인접하게 배치한다.
- 코드, 명령어, 설정 조각, 예상 출력은 유형별로 분리된 fenced 코드 블록으로 표현한다.
- 모든 fenced 코드 블록에 `shell`, `ini`, `yaml`, `text` 등 정확한 언어를 지정한다.
- 코드 펜스 정보 문자열의 두 번째 토큰은 명령에 `command`, 설정에 `configuration`, 출력에 `output`, 그 밖의 원문 코드와 기술 리터럴에 `literal`을 사용한다. 초기 전사 블록에만 `transcription`을 사용할 수 있다.
- 명령과 실행 결과를 같은 코드 블록에 혼합해서는 안 된다.
- 파일 경로, 설정 키, 명령 이름은 인라인 코드로 표현한다.
- 코드 블록의 원문 대소문자, 공백, 경로, 따옴표, 주석, 줄바꿈을 보존한다.
- 화면에서는 코드 블록 내부에서만 가로 스크롤을 허용한다.
- 복사 기능은 원문 코드 내용만 복사해야 한다.
- 복사 기능의 접근 가능한 이름과 완료 상태를 제공해야 한다.
- 색상만으로 토큰 종류와 오류 상태를 구분해서는 안 된다.

### SHOULD

- 설정 파일 조각은 `shell`이 아니라 실제 형식 또는 `text`로 표시한다.
- 줄 번호는 원문 의미에 필요한 경우에만 표시한다.
- 인쇄할 때 긴 줄이 잘리지 않도록 하되 정본 텍스트는 변경하지 않는다.

## 참고와 주의 문구

### MUST

- 문구 유형을 `참고`, `주의`, `경고`, `편집자 주`로 구분한다.
- 문구는 다음 CommonMark blockquote 작성 규칙에 따라 작성한다.

  ```markdown
  > **참고**
  >
  > 참고 내용
  ```

- Blockquote의 첫 strong 레이블은 `참고`, `주의`, `경고`, `편집자 주` 중 하나여야 한다.
- 유형을 텍스트 레이블과 시각 표시로 함께 표현한다.
- 색상만으로 유형을 구분해서는 안 된다.
- 원문 경고와 편집자 주를 같은 유형으로 표시해서는 안 된다.
- 위험 작업 관련 경고는 작업 단계보다 먼저 읽을 수 있어야 한다.
- 인쇄 결과에서도 레이블과 본문이 유지되어야 한다.

### SHOULD

- 하나의 참고 문구에는 하나의 주제만 포함한다.
- 일반 설명을 불필요하게 참고 문구로 변환하지 않는다.

## 표

### MUST

- 원문에서 행과 열의 관계로 표현된 정보는 OCR 평문, 서식이 고정된 텍스트, 이미지로만 제공해서는 안 되며 의미론적 표로 변환한다.
- 비교 또는 행렬 데이터에만 표를 사용한다.
- 화면 배치를 위해 표를 사용해서는 안 된다.
- 모든 표에 머리글 행 또는 머리글 열을 지정한다.
- 원문 캡션과 각주를 보존한다.
- 캡션이 없으면 인접 제목을 접근 가능한 이름으로 연결한다.
- 행·열 순서와 머리글과 셀의 관계를 보존한다.
- 모바일에서는 표 컨테이너만 가로 스크롤해야 한다.
- 전체 페이지에 표로 인한 가로 스크롤이 발생해서는 안 된다.
- 인쇄 시 머리글 행을 반복하고 가능하면 행 안에서 페이지가 나뉘지 않도록 한다.

### 복잡한 표

- MAY: 단순 표는 GFM 표로 작성할 수 있다.
- 병합 셀 또는 다단 머리글이 있는 표는 스키마로 검증되는 구조화 데이터로 관리한다.
- 복잡한 표의 정본 데이터는 점검항목의 `.tables.yaml` 사이드카에 저장한다.
- Markdown은 `[표: <caption>](<criterionSlug>.tables.yaml#<tableIdentifier>)` 형식으로 사이드카를 참조한다.
- 파서는 `.tables.yaml` 링크를 일반 링크가 아니라 유형이 지정된 표 AST 노드로 변환한다.
- 구조화 데이터에서 접근 가능한 HTML 표를 생성한다.
- 표 구조가 확인되지 않은 상태에서는 원본 페이지 이미지와 전사본을 함께 제공하고 `sourceAnomalyStatus: reviewRequired`로 표시한다.

## 이미지

### MUST

- 의미 있는 이미지는 원본 PDF에서 원본 해상도로 추출하거나 원문 영역을 잘라내어 생성한다.
- 생성형 이미지로 원본 이미지를 대체해서는 안 된다.
- 원본 이미지와 웹 최적화 파생 이미지를 구분한다.
- 정보성 이미지에 목적과 핵심 상태를 설명하는 대체 텍스트를 제공한다.
- 장식 이미지는 빈 대체 텍스트로 표시한다.
- 복잡한 도표에는 인접한 상세 설명을 제공한다.
- 명령어, 설정값, 판단 기준을 이미지로만 제공해서는 안 된다.
- 원문 캡션과 원문 페이지를 기록한다.
- 자산 provenance는 원문 페이지, 잘라내기 좌표, 픽셀 크기, 체크섬, 캡션, 대체 텍스트를 포함해야 한다.
- PDF 페이지에서 잘라낸 이미지는 `assetType: sourcePageCrop`과 고정된 `renderingProfileIdentifier`를 기록한다. 최초 생성한 잘라내어 정본으로 저장한 이미지의 픽셀 크기를 원본과 출력 크기로 기록한다. 이를 PDF에 삽입된 이미지의 원본 해상도로 표현해서는 안 된다.
- Markdown 이미지 경로는 `.provenance.yaml`의 자산 경로와 정확히 일치해야 한다.
- 자산 provenance 체크섬과 실제 정본 자산 바이트의 SHA-256 체크섬이 일치해야 한다.
- 원본보다 확대된 픽셀 크기를 원본 해상도로 간주해서는 안 된다.
- 작은 글자와 경계선이 최적화 과정에서 손실되어서는 안 된다.
- 확대 기능은 키보드로 열고 닫을 수 있어야 한다.
- 이미지 파일명은 항목 코드와 내용을 나타내는 축약하지 않은 영단어를 사용한다.

### SHOULD

- 화면 캡처에는 PNG를 사용한다.
- 이미지 내부 문자는 200% 확대 상태에서도 판독할 수 있어야 한다.

## 가독성과 시인성

### 문서 구조

- 본문 최대 폭은 `68ch` 이상 `78ch` 이하로 설정한다.
- 기본 본문 글자 크기는 16 CSS px 이상으로 설정한다.
- 기본 줄 높이는 1.5 이상으로 설정한다.
- 본문과 고정폭 글꼴 목록은 시각 테스트 프로파일에서 고정한다.
- H2와 H3가 합계 6개 이상이면 문서 내 목차를 제공한다.
- 중요도는 `상`, `중`, `하` 또는 동등한 텍스트를 표시한다.
- 중요도를 색상만으로 표시해서는 안 된다.
- 긴 절차를 기본 상태가 닫힌 탭 또는 아코디언에 배치해서는 안 된다.
- 접기 기능을 제공하더라도 검색, deep link, 인쇄에서 전체 내용에 접근할 수 있어야 한다.

### 반응형

- 320 CSS px 폭에서 페이지 전체의 가로 스크롤이 발생해서는 안 된다.
- 표와 코드 블록의 내부 가로 스크롤은 허용한다.
- 좁은 화면에서는 사이드바를 닫을 수 있는 탐색 메뉴로 전환한다.
- 앵커 이동 시 고정 머리글이 제목을 가려서는 안 된다.
- 화면 크기에 따라 검색, 탐색, 분류 경로, 본문의 의미 순서가 변경되어서는 안 된다.
- 분기점은 특정 기기명이 아니라 콘텐츠가 깨지는 지점으로 정의한다.

### 접근성

- WCAG 2.2 AA를 최소 품질 기준으로 사용한다.
- `header`, `nav`, `main`, `aside`, `footer` 랜드마크를 사용한다.
- 본문 바로가기를 첫 키보드 포커스 대상으로 제공한다.
- HTML 문서의 기본 언어를 `ko`로 설정한다.
- 독립적인 영문 구문은 필요한 경우 `lang="en"`을 사용한다.
- 모든 기능을 키보드만으로 사용할 수 있어야 한다.
- 포커스 표시를 제거해서는 안 된다.
- 일반 텍스트 대비는 4.5:1 이상이어야 한다.
- 큰 텍스트와 UI 경계 대비는 3:1 이상이어야 한다.
- 200% 확대와 400% reflow에서 내용과 기능이 유지되어야 한다.
- 애니메이션은 `prefers-reduced-motion` 설정을 준수해야 한다.
- 포커스 순서는 DOM의 의미 순서와 일치해야 하며 포커스 표시는 고정 UI에 가려져서는 안 된다.
- 검색 결과 수와 빈 결과 상태는 스크린 리더가 인식할 수 있도록 상태 변화를 알린다.
- 상호작용 대상은 WCAG 2.2 AA의 예외를 제외하고 최소 24×24 CSS px를 확보한다.
- 화면 방향을 세로 또는 가로로 제한해서는 안 된다.
- 사용자 텍스트 간격 재정의를 적용해도 내용과 기능이 유지되어야 한다.
- 테스트 프로파일은 적용 가능한 WCAG 2.2 AA 성공 기준을 자동 검사, 수동 검사, 증거 산출물에 대응시켜야 한다.
- 자동 접근성 검사만으로 승인해서는 안 된다.

### 인쇄

- 기본 인쇄 용지 크기는 A4로 설정한다.
- 탐색, 검색 입력, 복사 기능, 접기 기능을 인쇄 결과에서 제거한다.
- 항목 코드, 제목, 원문 문서명, 원문 페이지 범위, 원문 URL을 표시한다.
- 접힌 콘텐츠가 있으면 인쇄 시 모두 펼친다.
- 제목을 다음 본문과 분리된 페이지 하단에 남겨서는 안 된다.
- 인쇄 가능 영역보다 작은 코드 블록, 참고 문구, 이미지, 표 행은 페이지 경계에서 분할하지 않는다.
- 인쇄 가능 영역보다 큰 요소는 내용 손실 없이 분할한다. 표는 머리글을 반복하고, 코드 블록은 인쇄 화면에서만 줄바꿈할 수 있다.
- 흑백 인쇄에서도 중요도와 참고 문구 유형을 판독할 수 있어야 한다.

## 머신 리더블 출력

### 정규화 JSON

- 점검항목마다 하나의 정규화 JSON 레코드를 생성한다.
- 항목별 공개 JSON 데이터셋은 정규화 JSON에서 생성하고 의미 노드, provenance, 원문 주석을 유지해야 한다.
- 정규화 JSON은 메타데이터, 본문 AST, provenance, 원문 주석을 포함한다.
- AST 리프 블록은 블록 단위 원문 범위를 포함한다.
- 정규화 JSON 스키마는 버전을 가져야 한다.
- 스키마에 선언되지 않은 속성은 허용하지 않는다.
- 동일한 정본 콘텐츠에서 byte-identical JSON을 생성해야 한다.

### Deterministic serialization

- 정규화 JSON과 검색 색인은 RFC 8785 JSON Canonicalization Scheme으로 직렬화한다.
- RFC 8785 입력은 I-JSON 제약을 충족해야 하며, canonical JSON 뒤에 줄바꿈이나 추가 공백을 붙이지 않는다.
- 배열은 manifest 또는 원문 순서를 사용한다. Set 성격의 exact term은 정렬하고 중복을 제거한 뒤 직렬화한다.
- 실행 시점의 타임스탬프, 절대 경로, 호스트 이름을 결정론적 출력에 포함해서는 안 된다.
- 병렬 검증과 생성 결과는 작업 완료 순서가 아니라 manifest와 정렬된 입력 순서로 병합한다.
- 로케일은 `ko-KR`, 시간대는 `UTC`로 고정한다.
- 생성기와 파서 버전은 lockfile 또는 빌드 manifest로 고정한다.
- 동일 입력의 클린 빌드를 두 번 실행하고 canonical JSON, 검색 색인, 정규화 DOM 스냅샷의 체크섬을 비교한다.
- HTML 바이트, 스크린샷, PDF 바이너리는 byte-identical 대상에서 제외한다. HTML은 고정된 직렬화기의 정규화 DOM
  스냅샷과 시각적 차이로 검증한다.

체크섬 이름은 다음 의미로 구분한다.

- `sourceDocumentChecksum`: 원본 PDF 체크섬
- `criterionSourceChecksum`: 점검항목 Markdown, 사이드카, 정본 자산 바이트의 통합 체크섬
- `canonicalCorpusChecksum`: 모든 점검항목 패키지, `data/` 레지스트리, `schemas/` 스키마의 통합 체크섬
- `generatorVersion`: 정규화 및 렌더링 도구 버전

모든 체크섬은 SHA-256으로 계산하고 소문자 16진수로 저장한다. 통합 체크섬은 다음 방식으로 계산한다.

1. 포함 파일의 실제 바이트에 대한 SHA-256과 체크섬 범위에서 정의한 POSIX 논리 경로를 구한다.
2. 논리 경로를 UTF-8 바이트 순서로 정렬한다.
3. 각 파일을 `<sha256><two spaces><logicalPath><LF>` 레코드로 직렬화한다.
4. 전체 레코드 바이트의 SHA-256을 통합 체크섬으로 사용한다.

`criterionSourceChecksum`에는 해당 점검항목의 Markdown, `.tables.yaml`, `.provenance.yaml`, 정본 자산을 포함한다.
점검항목 패키지의 논리 경로는 각각 `<domainIdentifier>/<criterionSlug>.*`와
`assets/<criterionSlug>/<assetPath>`를 사용한다. `content/criteria/`와 `content/assets/` 같은 물리 저장 경로의 접두어는
논리 경로에 포함하지 않는다. 파일 바이트와 패키지 내부 경로가 같다면 저장소 구조를 옮겨도 기존 검토
식별 정보는 유효하다.
`canonicalCorpusChecksum`에는 `content/criteria/` 아래의 모든 점검항목 원본과 `data/`, `schemas/` 아래의 정본 파일을 포함한다.
이 체크섬의 논리 경로는 저장소 기준 POSIX 상대 경로를 사용한다.
원본 PDF, 생성물, 원시 추출물, 페이지 렌더링, 스크린샷은 문서 집합의 통합 체크섬에서 제외한다.
원본 PDF는 `sourceDocumentChecksum`으로 별도 검증한다.

### 의미론적 HTML

- 점검항목 하나를 `<article>` 하나로 렌더링한다.
- 문서당 `<h1>`을 하나만 생성한다.
- 주요 구역은 `<section>`과 연결된 제목 식별자를 사용한다.
- 분류 경로는 `<nav aria-label="분류 경로">`로 렌더링한다.
- 점검 내용, 목적, 위협, 대상은 고정 H3 레이블 뒤에 해당 본문 블록을 렌더링한다.
- 판단 기준의 양호와 취약은 각각 `<section>`으로 묶고, 레이블은 `<h4>`, 내용은 `<p>`로 분리한다.
- 절차는 `<ol>`과 `<li>`로 렌더링한다.
- 참고 항목은 `<ul>` 또는 `<aside>`로 렌더링한다.
- 명령어와 설정은 `<pre><code>`로 렌더링한다.
- 파일 경로와 설정 키는 인라인 `<code>`로 렌더링한다.
- 표는 `<table>`, `<thead>`, `<tbody>`, `<th>`, `<td>`와 올바른 머리글과 셀의 관계로 렌더링한다.
  원문 캡션이 있으면 `<caption>`을 보존하고, 없으면 인접 제목을 `aria-labelledby`로 연결한다.
- 원문 주석은 본문과 구분되는 별도 영역에 표시한다.
- provenance 영역에서 원본 문서와 페이지 범위를 확인할 수 있어야 한다.
- `<article>`에 `data-criterion-code`, `data-severity`, `data-content-model`, `data-source-document` 속성을 제공해야 한다.
- 각 리프 블록의 실제 의미 요소에 `data-block-reference`, `data-block-type`, `data-semantic-role`, `data-semantic-path`, `data-publication-disposition`, `data-source-region-identifiers`, `data-source-physical-pages`, `data-source-printed-pages` 속성을 제공해야 한다.
- 코드 블록은 `data-code-content-type`과 `data-code-language`를 `<pre>`와 `<code>`에 제공해야 한다.
- 항목 상세 페이지는 같은 정본 레코드에서 생성한 정규화 JSON을 `rel="alternate"`와 `application/json`으로 연결해야 한다.

### 검색 색인

- 점검항목마다 정확히 하나의 레코드를 생성한다.
- 기준 manifest 순서에 따라 결정론적으로 정렬한다.
- 코드, 항목 제목, 분야, 분류, 중요도, 대상, 본문 제목, 본문을 포함한다.
- 명령어, 경로, 설정 키, 제품명, 버전을 검색 대상으로 포함한다.
- Markdown과 HTML 마크업은 검색용 텍스트에서 제거한다.
- 한국어 텍스트는 Unicode NFC로 정규화한다.
- 명령어와 경로 리터럴은 원문 대소문자를 보존한 exact term으로 저장한다.
- 일반 검색용 case-folded 토큰과 exact term을 분리한다.
- 토크나이저와 case-folding 알고리즘 버전을 검색 색인에 포함한다.
- 검색 레코드는 스키마 버전, 레코드 식별자, 경로, 원문 페이지 범위, 제목 앵커, 검색용 텍스트, exact term을 포함해야 한다.
- 경로와 제목 앵커는 실제 HTML과 일치해야 한다.
- `criterionSourceChecksum`과 `canonicalCorpusChecksum`을 포함하고 오래된 산출물을 검출해야 한다.
- 검색 색인을 직접 수정해서는 안 된다.

검색 구현은 다음 질의 픽스처를 통과해야 한다.

| Query | 필수 결과 |
| --- | --- |
| `U-01`, `u-01`, `u01` | U-01이 첫 번째 결과 |
| `root`, `원격 접속` | U-01이 결과에 포함 |
| `PermitRootLogin` | U-01이 첫 번째 결과 |
| `/etc/ssh/sshd_config` | U-01이 첫 번째 exact match 결과 |

점검항목 manifest에서 382개 코드와 slug의 exact lookup fixture를 생성하고, 모두 해당 항목을 첫 번째 결과로 반환해야 한다.
각 점검항목의 원문 제목으로 검색하면 해당 항목이 결과에 포함되어야 한다. 기대 기술 리터럴 목록의 각 리터럴로 검색하면
그 리터럴이 속한 점검항목이 exact match 결과에 포함되어야 한다. 분야별 대표 한국어 질의와 순위 픽스처는 manifest에서 관리한다.

## 검증

### Metadata validator

- JSON Schema Draft 2020-12로 YAML front matter를 검증한다.
- YAML 1.2 작성 규칙, 중복 키 금지, alias 금지 규칙을 검사한다.
- 추가 속성을 허용하지 않는다.
- 중요도와 검토 상태를 enum으로 검증한다.
- 분야, 분류, 대상, 원본 문서가 레지스트리에 존재하는지 검사한다.
- 코드가 기준 manifest의 허용 목록에 존재하는지 검사한다.
- Manifest의 제목, 중요도, 분야, 분류, 콘텐츠 모델, 원문 시작 영역, 경로와 점검항목 메타데이터를 대조한다.

### Repository validator

- 코드, slug, 파일명, 경로의 일관성을 검사한다.
- 코드, slug, 경로, 앵커, 주석 식별자의 중복을 검사한다.
- 기준 manifest와 점검항목 파일 목록을 대조한다.
- 382개 코드의 누락과 예상하지 않은 파일을 검사한다.
- 원문 페이지 범위의 누락, 역전, PDF 범위 초과를 검사한다.
- PDF의 873쪽에 페이지 영역 목록이 존재하는지 검사한다.
- 모든 콘텐츠 영역이 정확히 하나의 역할, 소유권, 공개 처리 상태를 갖는지 검사한다.
- 영역 좌표의 역전과 허용되지 않은 중첩을 검사한다.

### Markdown AST validator

- 콘텐츠 모델별 필수 제목과 순서를 검사한다.
- Markdown 원본에 H1이 존재하지 않는지 검사한다.
- 제목 수준 누락을 검사한다.
- `Step 숫자)` 형식이 일반 문단에 남아 있는지 검사한다.
- 언어가 지정되지 않은 fenced 코드 블록을 검사한다.
- 명령어와 설정값이 일반 산문으로 유실되었는지 검사한다.
- 반복 머리말, 꼬리말, 페이지 번호의 본문 유입을 검사한다.
- 비정상 한글 공백과 줄바꿈 결합 오류를 검사한다.
- 대체 문자와 깨진 글머리표를 검사한다.
- 코드 펜스 정보 문자열의 언어와 콘텐츠 유형을 검사한다.
- 기대 기술 리터럴 목록과 AST의 명령어, 경로, 설정 키, 옵션, 버전 토큰을 대조한다.

### Provenance validator

- 원문 레지스트리의 `sourceDocumentChecksum`과 실제 PDF 체크섬을 비교한다.
- 원문 페이지 범위가 PDF 전체 범위 안에 있는지 검사한다.
- 점검항목 주석은 원문 페이지가 해당 점검항목 원문 범위 안에 있는지 검사한다.
- 페이지 영역 주석은 원문 페이지와 영역 식별자가 대상 영역과 일치하는지 검사한다.
- 탐색과 문서 주석은 원문 페이지가 원본 문서 범위 안에 있는지 검사한다.
- 주석 대상 유형에 따라 AST 노드, 메타데이터 JSON Pointer, 페이지 영역, 탐색, 문서 참조를 검사한다.
- `correctedWithNotice`에 대체 내용과 검증 근거가 있는지 검사한다.

### Generated output validator

- 정규화 JSON을 자체 스키마로 검증한다.
- HTML 제목, 랜드마크, 링크, 언어 속성을 검사한다.
- 검색 색인 레코드 수와 점검항목 수가 일치하는지 검사한다.
- 모든 검색 경로와 제목 앵커가 실제 HTML에 존재하는지 검사한다.
- 두 번의 클린 빌드에서 결정론적 산출물 체크섬이 일치하는지 검사한다.
- 생성물이 최신 `criterionSourceChecksum`, `canonicalCorpusChecksum`, `generatorVersion`을 참조하는지 검사한다.
- 내부 링크, 이미지 파일, 외부 URL 문법을 검사한다.
- 외부 URL의 접속 가능 여부는 정기 검사로 분리하고 결정론적 빌드의 차단 조건으로 사용하지 않는다.

### 시각 및 접근성 validator

- 320, 768, 1280 CSS px 뷰포트에서 핵심 화면을 검사한다.
- 허용된 표와 코드 블록 외 가로 넘침이 없는지 검사한다.
- 데스크톱과 모바일 스크린샷 차이를 검사한다.
- 자동 접근성 검사에서 critical과 serious 오류가 없는지 검사한다.
- 키보드 전용 시나리오를 수동 검증한다.
- 200% 확대와 400% reflow를 수동 검증한다.
- A4 인쇄 미리보기에서 잘림과 넘침을 검사한다.
- 시각 테스트 프로파일은 브라우저 엔진과 버전, 뷰포트 너비와 높이, 기기 픽셀 비율, 글꼴, 도구 버전, 규칙 집합, 스크린샷 차이 허용치, 인쇄 설정을 고정해야 한다.
- 핵심 화면은 홈, 분야 목록, 검색 결과, 단순 항목, 장문 항목, 표 포함 항목, 이미지 포함 항목, 원문 이상 표시, 404, 인쇄 결과를 포함한다.

## 검토 상태

검토 워크플로, 전사 품질, 원문 이상 상태를 서로 다른 필드로 관리한다.

### Workflow 상태

`review.workflowStatus`는 다음 상태를 순서대로 사용한다.

```text
extracted
  -> structured
  -> automatedChecksPassed
  -> visuallyReviewed
  -> approved
```

### 전사 품질 상태

검토 레지스트리 레코드의 `transcriptionStatus`는 다음 상태를 사용한다.

```text
verificationRequired
  -> machineChecked
  -> visuallyVerified
```

### 원문 이상 상태

`review.sourceAnomalyStatus`는 다음 상태 중 하나를 사용한다.

- `none`
- `reviewRequired`
- `reviewedWithOpenAnnotations`
- `resolved`

`reviewRequired`는 `approved` 전환을 차단한다. 원문 이상을 검토하고 `preserved` 또는 공개 `unresolved`로 결정하면
`reviewedWithOpenAnnotations`로 변경하고 워크플로 검토를 계속할 수 있다.
`approved` 항목은 `reviewedWithOpenAnnotations` 상태와 공개 주석을 가질 수 있다.

검토 정보는 `data/review-registry.yaml`에 기록한다. 검토 레코드는 점검항목과 페이지 영역에 공통으로 사용한다.

- `subjectType`
- `subjectIdentifier`
- `subjectSourceChecksum`
- `transcriptionStatus`
- `workflowStatus`
- `sourceAnomalyStatus`
- `reviewers`
- `reviewedAt`
- `sourceDocumentChecksum`
- `automatedValidationResult`
- `unresolvedConversionErrorCount`
- `unresolvedSourceAnomalyCount`
- `validationReportIdentifier`
- `visualEvidenceIdentifiers`
- `testProfileVersion`

분야 또는 페이지 단위의 포괄 승인만으로 개별 점검항목 승인을 대체해서는 안 된다.
`subjectType`은 `criterion` 또는 `pageRegion` 중 하나여야 한다.
점검항목 레코드의 `subjectSourceChecksum`은 현재 `criterionSourceChecksum`이어야 한다.
페이지 영역 레코드의 `subjectSourceChecksum`은 현재 `regionSourceChecksum`이어야 한다.

`regionSourceChecksum`은 페이지 영역 목록 레코드와 해당 영역이 참조하는 정본 콘텐츠 레코드를
RFC 8785로 직렬화한 뒤 이 문서의 통합 체크섬 레코드 방식으로 계산한다.

### 상태 전이 조건

- `workflowStatus: automatedChecksPassed`에는 `automatedValidationResult: passed`와 `validationReportIdentifier`가 필요하다.
- `workflowStatus: visuallyReviewed` 또는 `approved`에는 `transcriptionStatus: visuallyVerified`가 필요하다.
- `workflowStatus: visuallyReviewed` 또는 `approved`에는 현재 `subjectSourceChecksum`과 연결된 시각 검토 증거가 필요하다.
- `workflowStatus: approved`에는 한 명 이상의 검토자, `reviewedAt`, `testProfileVersion`이 필요하다.
- `workflowStatus: approved`에는 `unresolvedConversionErrorCount: 0`이 필요하다.
- `sourceAnomalyStatus: reviewedWithOpenAnnotations`에는 모든 공개 주석의 `reviewStatus: reviewed`와
  완결된 검토자 정보가 필요하다.
- 검토 대상 원본, 검증기 규칙 집합, 테스트 프로파일이 변경되면 연결 체크섬을 비교하고 영향을 받은 상태를 무효화해야 한다.

### 항목 승인 조건

항목 승인은 전체 릴리스와 독립적으로 수행한다. 다음 조건을 충족한 항목만 `workflowStatus: approved`로 전환한다.

- 해당 항목의 메타데이터, AST, provenance, 생성 산출물 검증을 통과해야 한다.
- 해당 항목의 원문 페이지와 변환 결과 시각 대조가 완료되어야 한다.
- `unresolvedConversionErrorCount`가 0이어야 한다.
- `sourceAnomalyStatus`가 `none`, `reviewedWithOpenAnnotations`, `resolved` 중 하나여야 한다.
- 검토 레코드가 현재 `criterionSourceChecksum`과 검증 증거를 참조해야 한다.

## QA workflow

1. 원본 PDF를 고정하고 체크섬과 기준 manifest를 생성한다.
2. 전체 페이지의 원시 텍스트, 페이지 렌더링, 원본 이미지를 추출하고 PDF에 삽입된 이미지의 문자를 포함하는 OCR 전사본을 생성한다.
3. 표지, 목차, 장, 분류, 점검항목, 뒤표지 경계를 구조화한다.
4. 페이지 영역 좌표와 장 경계를 이용해 항목 범위를 결정한다. 다음 코드만으로 범위를 결정해서는 안 된다.
5. 허용된 정규화만 적용하고 모든 원문 이상을 등록한다.
6. 메타데이터, 저장소, AST, provenance 자동 검사를 실행한다.
7. 자동 검사에 실패한 항목은 시각 검토를 진행하지 않는다.
8. 원본 페이지와 변환 결과를 나란히 놓고 382개 항목과 모든 `published`·`derived` 영역을 전수 검토한다.
9. 명령어, 경로, 설정값, 표, 이미지, 판단 기준을 문자 및 구조 단위로 대조한다.
10. 원문 이상과 편집자 보정은 2차 검토한다.
11. HTML, 검색, 접근성, 반응형, 인쇄 회귀 검사를 실행한다.
12. 항목 승인 조건을 충족한 항목만 `approved`로 변경한다.

최초 릴리스에는 샘플 검토를 적용하지 않는다. 샘플링은 전수 승인 이후 콘텐츠에 영향을 주지 않는 레이아웃 회귀 검사에만 사용할 수 있다.

## 릴리스 조건

다음 조건을 모두 충족해야 배포할 수 있다.

- PDF 873쪽의 분류율이 100%여야 한다.
- 모든 콘텐츠 영역의 역할, 소유권, 공개 처리 상태가 확인되어야 한다.
- 모든 `published`·`derived` 영역의 시각 대조가 완료되어야 한다.
- 모든 `published`·`derived` 영역 검토 레코드의 `workflowStatus`가 `approved`여야 한다.
- `sourceAnomalyStatus: reviewRequired`인 공개 영역이 0건이어야 한다.
- 기준 manifest에 382개 점검항목이 존재해야 한다.
- `extractedCriterion` 상태의 점검항목이 0건이어야 한다.
- 382개 점검항목의 자동 검사와 원문 시각 대조가 완료되어야 한다.
- 382개 점검항목의 `workflowStatus`가 `approved`여야 한다.
- `sourceAnomalyStatus: reviewRequired`인 항목이 0건이어야 한다.
- 미해결 변환 오류가 0건이어야 한다.
- 미해결 원문 이상은 `sourceAnnotations` 또는 `data/source-annotations.yaml`에 기록되고, 생성된 공개 원문 이상 목록에 표시되어야 한다.
- 메타데이터와 정규화 JSON의 스키마 오류가 0건이어야 한다.
- H1 중복, 제목 누락, 깨진 내부 링크, 중복 앵커가 0건이어야 한다.
- 언어가 지정되지 않은 fenced 코드 블록이 0건이어야 한다.
- 머리글이 없거나 접근 가능한 이름이 없는 표가 0건이어야 한다.
- 정보성 이미지의 대체 텍스트 누락이 0건이어야 한다.
- 검색 색인 레코드가 정확히 382개여야 한다.
- 정의된 검색 질의 픽스처가 모두 통과해야 한다.
- 자동 접근성 검사에서 critical과 serious 오류가 0건이어야 한다.
- 허용된 표와 코드 블록 외 페이지 전체의 가로 넘침이 0건이어야 한다.
- 정본 콘텐츠만으로 모든 생성물을 재생성할 수 있어야 한다.
- 브라우저 QA 보고서는 빌드 산출물과 분리해 저장하고 현재 정본 문서 집합 체크섬과 테스트 프로파일 버전을 참조해야 한다. 빌드가 QA 보고서를 생성하거나 덮어써서는 안 된다.
- 두 번의 클린 빌드에서 결정론적 산출물 체크섬이 일치해야 한다.
- 원문 레지스트리의 `license`가 비어 있지 않고 모든 생성 HTML의 공통 푸터에 같은 값을 표시해야 한다.
- 승인되지 않았거나 만료된 정책 예외가 0건이어야 한다.

각 검증기는 안정적인 규칙 식별자를 포함한 기계가 읽을 수 있는 보고서를 생성해야 한다.
릴리스는 현재 스키마 버전에 해당하는 전체 규칙 집합의 통과 보고서를 참조해야 한다.

## 변경 관리

- 메타데이터 스키마와 정규화 JSON 스키마는 버전을 가져야 한다.
- 하위 호환성을 깨는 스키마 변경에는 마이그레이션 절차를 제공해야 한다.
- 파서, 렌더러, taxonomy 변경은 영향 항목을 계산해야 한다.
- 영향 항목은 원문 대조와 시각 검토를 다시 수행해야 한다.
- 전역 파서 변경은 전체 manifest와 자동 검사를 다시 실행해야 한다.
- 승인본 대비 필드별 차이와 스크린샷 차이를 생성해야 한다.
- 시각 테스트 프로파일과 접근성 규칙 집합 변경은 영향 범위와 재승인 기준을 기록해야 한다.
- 제목 변경으로 기존 경로와 앵커가 변경되어서는 안 된다.
- 원본 PDF 교체 시 체크섬, 판본, manifest, 원문 페이지 범위를 모두 다시 검증해야 한다.

## 참고 자료

- [KISA CCE 가이드 2026 원본 PDF](content/source/kisa-cce-criteria-2026.pdf)
- [저장소 README](README.md)
- [OpenAI Codex non-interactive mode](https://developers.openai.com/codex/noninteractive)
- [OpenCodeX Codex integration](https://github.com/lidge-jun/opencodex/blob/main/docs-site/src/content/docs/guides/codex-integration.md)
- [CommonMark Specification](https://spec.commonmark.org/spec)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [W3C Page Structure Tutorial](https://www.w3.org/WAI/tutorials/page-structure/)
