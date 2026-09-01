# 빌드와 릴리스

이 문서는 canonical 콘텐츠 검증, 정적 사이트 생성, 로컬 확인과 릴리스 게이트를 설명한다. 승인 조건은 [문서 변환 정책](../../CONVERSION_POLICY.md)이 기준이다.

## 검증과 빌드

```bash
uv run python -m conversion.validate_content
uv run python -m conversion.build_content
```

하위 경로에 배포할 URL을 만들 때는 base path를 지정한다.

```bash
uv run python -m conversion.build_content \
  --base-path /kisa-cce-guide-web
```

호스팅용 bundle을 생성한다.

```bash
uv run python -m conversion.build_sites_bundle
```

정적 결과는 `.artifacts/build/`, 호스팅 bundle은 `.artifacts/dist/client/`와 `.artifacts/dist/server/`에 생성한다.

| Source | 역할 |
| --- | --- |
| `content/criteria/` | Canonical criterion과 provenance |
| `content/assets/` | 공개가 허용된 criterion asset |
| `data/` | Taxonomy, manifest와 공개 dataset 입력 |
| `site/assets/` | CSS, JavaScript와 self-hosted vendor asset |
| `site/skill/kisa-cce-guide-explorer/SKILL.md` | `/SKILL.md`와 `/skill/` 페이지 원본 |
| `site/hosting/worker.js` | 호스팅 bundle server entrypoint |

구문 강조 자산과 BSD-3-Clause 라이선스, checksum은 `site/assets/vendor/highlight.js/`에 보존한다. 외부 CDN은 사용하지 않는다.

## 로컬 서버

```bash
uv run python -m conversion.serve_site
uv run python -m conversion.serve_site --no-build
uv run python -m conversion.serve_site \
  --base-path /kisa-cce-guide-web
```

기본 URL은 <http://localhost:8000/>이고, 기본 listen 주소는 `127.0.0.1`이다. 다른 장치에서 접근해야 할 때만 `--host 0.0.0.0`을 명시한다.

## 생성 사이트 계약

빌드는 홈, 12개 분야, 분류, 382개 criterion, 검색, 404, 정규화 JSON, taxonomy JSON, `/SKILL.md`, `/skill/`, 반응형·접근성·인쇄 자산을 생성한다. 모든 HTML의 언어, 단일 H1, landmark, skip link, anchor, 내부 링크, 이미지, 표와 검색 anchor를 정적 검사한다. 원본 PDF는 사이트에 복사하지 않는다.

## GitHub Pages 검토 artifact

`.github/workflows/pages-build.yaml`은 수동 실행에서 base path를 적용하고, canonical 검증 후 검토 artifact를 생성한다. `.nojekyll`을 포함하지만 공개 배포 job은 구성하지 않는다.

## 품질 검사

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run ty check conversion tests
uv run pytest -q
git diff --check
```

## 릴리스 검증

```bash
uv run python -m conversion.validate_content \
  --release \
  --report .artifacts/build/reports/release-validation.json
```

현재 `data/review-registry.yaml`에는 `approved` record가 없다. 따라서 릴리스 검증은 통과 조건을 충족하지 않는다.

릴리스에는 사람 검토, 현재 corpus checksum에 연결된 자동 검증, 미해결 오류와 정책 예외 해소, 접근성·반응형·인쇄 QA와 deterministic clean build가 필요하다.

`.artifacts/build/`, `.artifacts/dist/`, `.artifacts/work/`는 생성 산출물이다. 직접 수정하거나 Git에 포함하면 안 된다.
