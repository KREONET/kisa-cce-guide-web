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

현재 두 가지 content model이 존재합니다.

### `systemCriterion`

U-01과 U-02에 적용됩니다.

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

`extractedCriterion`은 원문 누락 방지와 후속 구조화 작업을 위한 초기 상태입니다. 접근성 검토와 내용 승인의 대상이 되는 최종 변환 상태가 아닙니다. 릴리스 검증은 `extractedCriterion`이 한 건이라도 존재하면 실패합니다.

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

- 380개 항목이 `extractedCriterion` 상태
- 1,206개 review record가 모두 사람 승인 전 상태
- 대체 텍스트와 원문 영역 시각 자산의 사람 검토 미완료
- 자동 검증 결과가 review registry에 반영되지 않음
- 65개 항목별 source inconsistency annotation이 미검토 상태
- 라이선스 유형, 허용 이용 범위, 필수 출처 문구가 미승인 상태
- 시각·접근성 test profile이 미완성 상태
- 접근성, 반응형, 인쇄 브라우저 QA 보고서가 없음
- 공개 배포 구성이 승인되지 않음

브라우저 QA 보고서는 `schemas/qa-report.schema.json`을 따라야 합니다. 보고서는 현재 canonical corpus checksum과 test profile version을 참조해야 하며, 빌드 과정에서 자동 생성하거나 덮어쓰지 않습니다.

## 범위와 한계

- 원본 PDF가 점검·감사·법적 판단의 기준입니다.
- 페이지 단위 자동 전사에는 줄 분리, 표 구조 손실, 이미지 설명 누락, 특수문자 손상 가능성이 있습니다.
- 380개 초기 전사 항목의 명령어, 경로, 표, 판단 기준은 사람의 원문 대조를 완료하지 않았습니다.
- 원문 영역 PNG는 시각 대조 자료입니다. 사람의 검토 완료를 의미하지 않습니다.
- 원문 내부의 코드, 중요도, 제목, 분류 차이는 자동 수정하지 않고 annotation으로 보존합니다.
- 대상 시스템 metadata는 U-01과 U-02를 제외하면 아직 `unspecified`입니다.
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
