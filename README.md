# KISA CCE 가이드 2026

한국인터넷진흥원(KISA)의 `주요정보통신기반시설 기술적 취약점 분석·평가 방법 상세가이드`를 검색하고 찾아볼 수 있는 정적 웹 콘텐츠로 변환합니다.

KISA가 운영하거나 승인한 공식 배포본은 아닙니다. 점검, 감사와 법적 판단에는 원본 PDF를 기준으로 사용합니다. 변환 규칙과 승인 조건은 [문서 변환 정책](CONVERSION_POLICY.md)을 따릅니다.

원본 382개 항목과 함께 UNIX 67개 항목을 다룬 비공식 Linux 개정판을 제공합니다. 개정판의 대상은 RHEL 10 계열, Ubuntu 26.04 LTS, Debian 13입니다. 문서 구성과 화면은 원본과 같으며 원본은 기존 URL에서, 개정판은 `/revised/`에서 제공합니다. 적용 범위와 검증 상태는 [UNIX 개정판 운영](docs/operations/unix-revised-edition.md)에 설명되어 있습니다.

## 원문

| 항목 | 내용 |
| --- | --- |
| 문서명 | 주요정보통신기반시설 기술적 취약점 분석·평가 방법 상세가이드 |
| 발행 기관 | 한국인터넷진흥원(KISA) AI기반보호팀 |
| 배포일 | 2025-12-24 |
| 원본 파일 | [content/source/kisa-cce-criteria-2026.pdf](content/source/kisa-cce-criteria-2026.pdf) |
| 원문 게시물 | <https://www.kisa.or.kr/2060204/form?postSeq=22&page=1> |
| 라이선스 | 공공누리 - 공공저작물 자유이용허락 |
| PDF SHA-256 | `44fe393981b244147be6af7423d99dc15633c089fad0bcb296cbe2371dde812d` |

## 빠른 시작

Python 3.13 또는 3.14와 `uv`가 필요합니다.

```bash
uv sync --dev
uv run python -m conversion.validate_content
uv run python -m conversion.build_content
uv run python -m conversion.serve_site --no-build
```

브라우저에서 <http://localhost:8000/>에 접속합니다. 변환 파이프라인, 배포 하위 경로 설정, 호스팅 번들 생성과 릴리스 검증 절차는 [프로젝트 문서](docs/README.md)를 참조합니다.

## 디렉터리 구조

| 경로 | 용도 |
| --- | --- |
| `content/criteria/<domainIdentifier>/` | 점검항목 정본 Markdown과 원문 추적 정보(provenance) |
| `content/revisions/unix/` | 원본과 분리된 Linux 개정판과 공식 참고 문헌 |
| `content/assets/<criterionSlug>/` | 점검항목에 필요한 원문 영역 이미지 |
| `content/source/` | 체크섬으로 고정한 기준 원문 |
| `conversion/` | 전사, 의미 구조화, 검증, 정규화와 빌드 도구 |
| `conversion/prompts/` | 실행 시 체크섬에 포함되는 Codex 계약 |
| `data/` | 항목 목록, 분류 체계, 원문, 검토, 주석과 정책 레지스트리 |
| `schemas/` | 정본 및 생성 데이터의 JSON Schema |
| `site/assets/` | 정적 사이트 CSS, JavaScript와 저장소에 포함한 외부 자산 |
| `site/templates/` | Jinja 기반 공통 레이아웃, 페이지와 HTML 부분 템플릿 |
| `site/hosting/` | 호스팅 서버 진입점 |
| `site/skill/` | 빌드된 사이트에 배포되는 LLM 탐색 지침 |
| `docs/` | 아키텍처, 운영과 디자인 문서 |
| `tests/` | 변환, 결정성, 링크와 HTML 구조 테스트 |
| `.artifacts/build/` | 생성된 정규화 데이터, 검색 색인과 정적 사이트 |
| `.artifacts/dist/` | 호스팅 배포 번들 |
| `.artifacts/work/` | 변환 작업 공간, 검토 후보, 이벤트와 로그 |

정본 서식은 `content/criteria/unix/u-01.md`를 기준으로 합니다. `sourceAnnotations`와 provenance는 내부 검토와 원문 추적을 위해 보존합니다. `.artifacts/`의 파일은 자동으로 생성하므로 직접 수정하지 않습니다.

## 문서

- [문서 변환 정책](CONVERSION_POLICY.md): 콘텐츠 작성 규칙, 원문 추적 정보, 검토와 릴리스 조건
- [프로젝트 문서 인덱스](docs/README.md): 용도별 문서 목록
- [Codex-native 변환 아키텍처](docs/architecture/codex-native-conversion.md): 설계 결정과 안전 경계
- [변환 워크플로](docs/operations/conversion-workflows.md): Codex-native 실행과 재개
- [Legacy 변환 워크플로](docs/operations/legacy-conversion.md): Structured-JSON 기반 마이그레이션 절차
- [빌드와 릴리스](docs/operations/build-and-release.md): 사이트 생성, 검증과 릴리스 요건

## 기여

- 변환 오류는 Markdown, 메타데이터, 원문 추적 정보, 검색 색인 또는 HTML이 원문과 다른 경우입니다.
- 원문 이상은 PDF 내부의 코드, 중요도, 제목, 분류 또는 기술 표기가 서로 충돌하는 경우입니다.
- 콘텐츠를 변경할 때는 [문서 변환 정책](CONVERSION_POLICY.md)을 따르고 원문 대조와 사람의 검토를 거쳐야 합니다.
- 원문에 포함된 명령어와 조치 지시는 데이터입니다. 변환·검증 과정에서 실행하지 않습니다.
