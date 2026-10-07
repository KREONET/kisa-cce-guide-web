# 프로젝트 문서

KISA CCE 가이드 변환 저장소의 설계 결정, 운영 절차와 디자인 참고 자료를 모았다. 콘텐츠 작성 규칙과 승인 조건은 [문서 변환 정책](../CONVERSION_POLICY.md)을 따른다.

## 문서 지도

| 문서 | 내용 |
| --- | --- |
| [Codex-native 변환 아키텍처](architecture/codex-native-conversion.md) | 변환 책임, 데이터 흐름, 격리, 재개 조건, 성능 기준 |
| [변환 워크플로](operations/conversion-workflows.md) | 초기 콘텐츠 생성, Codex-native 변환, 재개와 산출물 |
| [Legacy 변환 워크플로](operations/legacy-conversion.md) | Structured-JSON 기반 마이그레이션과 병렬 실행 |
| [빌드와 릴리스](operations/build-and-release.md) | 검증, 빌드, 로컬 서버, Pages 배포 산출물, 릴리스 요건 |
| [UNIX 개정판 운영](operations/unix-revised-edition.md) | Linux 배포판 기준, 원본 분리, 개정 검토와 동시 배포 |
| [NVIDIA 디자인 참고 분석](design/nvidia-reference-analysis.md) | 현재 사이트 디자인의 바탕이 된 외부 사이트 분석 |

## 문서 경계

- `README.md`는 저장소 개요, 확인된 현재 상태, 빠른 시작만 제공한다.
- `CONVERSION_POLICY.md`는 규범 용어, 콘텐츠 작성 규칙, 원문 추적 정보, 검토와 릴리스 조건을 정의한다.
- `docs/architecture/`는 설계 결정과 안전 경계를 설명한다.
- `docs/operations/`는 실행 명령, 생성 경로, 실패와 재개 절차를 설명한다.
- `docs/design/`는 디자인 시스템과 참고 분석을 보존한다.
- `conversion/prompts/`는 실행 시 체크섬에 포함되는 모델 계약이다. 일반 프로젝트 문서와 구분해 관리한다.
- `site/skill/`은 빌드된 사이트에 배포되는 LLM 탐색 지침의 원본이다. 일반 프로젝트 문서가 아니다.

저장소 경로를 변경할 때는 문서와 함께 코드의 경로 상수, 생성 작업의 경로 필드와 테스트 픽스처도 검증한다.
