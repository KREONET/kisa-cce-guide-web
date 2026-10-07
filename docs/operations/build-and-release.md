# 빌드와 릴리스

정본 콘텐츠를 검증하고 정적 사이트를 생성한 뒤 로컬에서 확인하는 절차와 릴리스 조건을 다룬다. 승인 조건은 [문서 변환 정책](../../CONVERSION_POLICY.md)이 기준이다.

## 검증과 빌드

```bash
uv run python -m conversion.validate_content
uv run python -m conversion.build_content
```

두 명령은 항목별 작업을 별도 프로세스에서 병렬로 실행한다. 기본 프로세스 수는 사용 가능한 CPU 수를 따르며 최대 8개다. 문제 재현이나 디버깅을 위해 직렬로 실행하려면 `--workers 1`을 지정한다. 병렬 실행에서도 검증 결과, 정규화 문서, 검색 레코드와 생성 경로를 매니페스트 순서로 병합하므로 직렬 실행과 파일 집합 및 바이트가 같다.

하위 경로에 배포할 때는 기준 경로(base path)를 지정한다.

```bash
uv run python -m conversion.build_content \
  --base-path /kisa-cce-guide-web \
  --site-origin https://example.github.io
```

호스팅용 번들은 다음 명령으로 생성한다.

```bash
uv run python -m conversion.build_sites_bundle
```

호스팅 번들과 로컬 서버의 자동 빌드도 같은 `--workers` 옵션을 지원한다.

정적 사이트 빌드 결과는 `.artifacts/build/`에 생성한다. 호스팅 번들은 `.artifacts/dist/client/`와 `.artifacts/dist/server/`에 생성한다.

| 원본 | 역할 |
| --- | --- |
| `content/criteria/` | 정본 항목과 원문 추적 정보(provenance) |
| `content/assets/` | 공개가 허용된 항목별 자산 |
| `data/` | 분류 체계, 매니페스트와 공개 데이터셋 입력 |
| `site/assets/` | CSS, JavaScript와 자체 호스팅 외부 라이브러리 자산 |
| `site/templates/` | Jinja 기반 공통 문서 틀, 페이지와 HTML 부분 템플릿 |
| `site/skill/kisa-cce-guide-explorer/SKILL.md` | `/SKILL.md`와 `/skill/` 페이지 원본 |
| `site/templates/llms.txt` | 두 판본의 탐색 진입점을 안내하는 `/llms.txt` 원본 |
| `site/hosting/worker.js` | 호스팅 번들의 서버 진입점 |

사이트 생성기는 `FileSystemLoader`로 `site/templates/`를 읽는다. HTML 자동 이스케이프와 `StrictUndefined`를 적용하며 Markdown에서 만든 HTML은 원시 HTML을 허용하지 않는 렌더러의 출력만 명시적으로 삽입한다.

구문 강조 자산과 BSD-3-Clause 라이선스, 체크섬은 `site/assets/vendor/highlight.js/`에 보존한다. 외부 CDN은 사용하지 않는다.

## 로컬 서버

```bash
uv run python -m conversion.serve_site
uv run python -m conversion.serve_site --no-build
uv run python -m conversion.serve_site \
  --base-path /kisa-cce-guide-web
```

기본 URL은 <http://localhost:8000/>이며 기본 수신 주소는 `127.0.0.1`이다. 다른 장치에서 접근해야 할 때만 `--host 0.0.0.0`을 명시한다.

## 생성 사이트 계약

빌드는 홈, 12개 분야, 분류, 382개 점검항목, 검색, 404, 정규화 JSON, 분류 체계 JSON, `/SKILL.md`, `/skill/`, `/llms.txt`, 반응형·접근성·인쇄 자산을 생성한다. 모든 HTML에서 언어, 단일 H1, 랜드마크, 건너뛰기 링크, 앵커, 내부 링크, 이미지, 표와 검색 앵커를 정적으로 검사한다. 원본 PDF는 사이트에 복사하지 않는다.

`/llms.txt`는 원본과 비공식 Linux 개정판의 범위를 구분하고 각 판본의 홈, 검색과 UNIX 목록 및 공통 탐색 지침을 연결한다. 빌드의 `--base-path`는 이 문서의 링크에도 적용한다. 자세한 판본 선택과 인용 규칙은 `/SKILL.md`와 `/skill/`에서 제공한다.

### 검색 엔진 탐색 파일

빌드는 `robots.txt`를 생성해 모든 사용자 에이전트의 접근을 허용한다. 공개 주소를 `--site-origin`으로 지정하면 `sitemap.xml`과 robots.txt의 `Sitemap` 항목도 생성한다. Origin에는 경로가 없는 HTTP(S) 주소를 지정하고 배포 하위 경로는 `--base-path`로 분리한다. 예시의 `https://example.github.io`는 실제 배포 도메인으로 바꾼다. 잘못된 origin은 기존 빌드 산출물을 교체하기 전에 거부한다.

사이트맵은 현재 빌드에서 생성한 원본·개정판의 홈, 분야, 분류, 항목, 검색과 스킬 HTML 페이지를 절대 URL로 나열한다. 404 페이지, JSON 데이터셋과 정적 자산은 제외한다. URL은 중복 없이 정렬하며 확인되지 않은 수정 시각이나 우선순위는 넣지 않는다. 현재 목록은 543개 페이지다.

`build_sites_bundle`과 `serve_site`의 자동 빌드도 `--site-origin`을 지원한다. Origin을 생략하는 로컬·미리보기 빌드는 호스트를 추측하지 않으며 사이트맵과 `Sitemap` 항목을 생성하지 않는다. 기존 사이트맵이 남아 있으면 제거한다. `serve_site --no-build`는 기존 파일을 그대로 제공한다.

[사이트맵 프로토콜](https://www.sitemaps.org/protocol.html)은 절대 URL을 요구한다. [robots.txt 규칙](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec)에 따라 크롤러는 도메인 루트의 `/robots.txt`를 읽는다. 따라서 `/kisa-cce-guide-web/robots.txt` 같은 프로젝트 하위 경로의 파일은 도메인 전체 크롤링 규칙으로 적용되지 않는다. 이 경우 도메인 루트의 robots.txt에 사이트맵 절대 URL을 추가하거나 검색 엔진 관리 도구에 사이트맵을 직접 제출한다. 파일 생성은 검색 엔진의 수집이나 색인을 보장하지 않는다.

같은 빌드에서 UNIX 개정판 홈, 분야 목록, 5개 분류 목록, 검색과 67개 항목을 `/revised/` 아래에 생성한다. 전체 HTML은 원본 469개와 개정판 75개를 합한 544개다. 두 판본은 같은 목록·검색·항목 템플릿과 본문 렌더러를 사용한다. 개정판 데이터셋은 `/revised/dataset.json`이며 원본 검색 데이터셋과 분리한다. [UNIX 개정판 운영](unix-revised-edition.md)에 대상 배포판과 문서 구성을 설명한다.

공통 헤더의 화면 테마 선택기는 시스템 설정, 화이트, 다크, OLED 블랙을 제공한다. 직접 선택한 테마는 브라우저에 저장한다. 시스템 설정을 선택하면 운영체제의 밝은 화면과 어두운 화면 변경을 따른다. OLED 블랙은 본문과 주요 영역의 배경을 `#000000`으로 렌더링한다. 인쇄할 때는 화면 테마와 관계없이 흰 배경과 검은 글자를 사용한다.

## GitHub Pages 배포

`.github/workflows/pages-build.yml`을 수동 실행하면 GitHub Pages의 기준 경로를 적용해 정본 콘텐츠를 검증하고 사이트를 생성한다. 이 과정을 통과한 Pages 전용 산출물을 `github-pages` 환경에 배포한다. 이 워크플로는 `--release` 검증을 실행하지 않으므로 릴리스 검증은 아래 절차로 별도 수행한다.

원본과 개정판은 같은 Pages 산출물에 포함된다. 개정 브랜치를 선택해 수동 실행하면 해당 브랜치의 두 판본을 함께 배포한다. 서로 다른 브랜치를 각각 배포해 같은 Pages 사이트를 덮어쓰지 않는다. 원본 URL은 유지되고 개정판은 동일한 기준 경로 아래의 `/revised/`에서 열린다.

Pages 빌드는 `actions/configure-pages`의 `origin`과 `base_path`를 전달해 실제 배포 주소에 맞는 사이트맵을 생성하고 robots.txt와 함께 업로드한다. 수동 워크플로를 실행하기 전에는 원격 사이트에 반영되지 않는다.

빌드 작업은 `contents: read`, `pages: read` 권한만 사용한다. 배포 작업은 `pages: write`, `id-token: write` 권한만 사용한다.

저장소의 `Settings > Pages > Build and deployment > Source`는 `GitHub Actions`로 설정해야 한다.

## Pytest CI

`.github/workflows/pytest.yml`은 풀 리퀘스트, `main` 브랜치로의 푸시 또는 수동 실행을 계기로 Python 3.13에서 전체 pytest 테스트를 실행한다. 저장소 읽기 전용 권한과 `uv.lock` 기반 의존성 캐시를 사용하며 같은 ref의 이전 실행은 취소한다.

## 품질 검사

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run ty check conversion tests
uv run pytest -q
node --test tests/search-core.test.cjs tests/theme.test.cjs
git diff --check
```

## 릴리스 검증

```bash
uv run python -m conversion.validate_content \
  --release \
  --report .artifacts/build/reports/release-validation.json
```

현재 `data/review-registry.yaml`에는 `approved` 레코드가 없다. 따라서 릴리스 검증은 통과 조건을 충족하지 않는다.

릴리스하려면 사람의 검토와 현재 전체 콘텐츠 체크섬에 연결된 자동 검증을 마쳐야 한다. 미해결 오류와 정책 예외를 해소하고 접근성·반응형·인쇄 QA를 수행해야 하며 이전 산출물 없이 빌드해도 결과가 같아야 한다.

`.artifacts/build/`, `.artifacts/dist/`, `.artifacts/work/`는 생성 산출물이다. 직접 수정하거나 Git에 포함하면 안 된다.
