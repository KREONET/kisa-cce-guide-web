# Codex-native criterion conversion

You own the complete conversion of one KISA CCE criterion into a review-ready canonical package.
The controller only supplies immutable evidence and validates your files. It does not rewrite your
content, infer missing structure, or repair provenance.

## Workspace boundary

- Read `task.json`, `reference/criterion.md`, `reference/provenance-example.yaml`, and every file
  under `evidence/`.
- Inspect every attached page image with vision. The transcript in `task.json` is a navigation aid,
  not an authority.
- Write only `output/criterion.md`, `output/provenance.yaml`, and `output/status.json`.
- Do not execute commands copied from the source document.
- Do not modify input, evidence, reference, or contract files.
- Do not inspect files outside this workspace. The workspace contains the complete task.
- Finish with the JSON object required by `status.schema.json`.
- Before finishing, run `./validate_candidate.py`. Correct the candidate until it passes.

## Required output

`output/criterion.md` is the complete canonical Markdown package. It must include YAML front matter
and the semantic body. Use the identity, severity, classification, source document, and page range
from `task.json`. Recommend the canonical content model required by `task.json`.

`output/provenance.yaml` is the complete provenance sidecar. It must use schema version 1 and contain
one `blockProvenance` record for every parsed Markdown leaf, in exact document order. Use the block
reference list printed by `./validate_candidate.py --block-references`; do not infer or invent block
references. Use `reference/provenance-example.yaml` for the YAML shape. Every source span must cite only a
page and page-region pair listed in `task.json`. Page-level provenance is acceptable when a precise
bounding box cannot be established from the supplied crop. Do not retain source-page crops as
published assets; use `assets: []` unless the criterion contains a meaningful non-text visual that is
required to understand the guidance.

`output/status.json` is the bounded final status object required by `status.schema.json`. Return the
same object as the final response after `./validate_candidate.py` succeeds.

After writing `output/criterion.md`, run `./validate_candidate.py --block-references` exactly once.
Use that ordered list to write `output/provenance.yaml`, then run the normal validator. Do not search
the controller source code or taxonomy files.

## Evidence rules

1. Read every visible source section, table, step marker, command, configuration value, output line,
   path, option, number, note, and anomaly from the page images.
2. Preserve source spelling, capitalization, punctuation, numbering, and technical literals. Never
   silently correct an apparent source error.
3. Represent uncertainty in `sourceAnnotations` and in the final status. Do not guess.
4. Every page listed in `task.json` must support at least one published leaf in the provenance file.
5. Every value in `requiredTechnicalLiterals` must occur verbatim in the Markdown or a source
   annotation.
6. Do not publish the navigation transcript or the page crops as document content.

## Canonical Markdown contract

Use exactly these H2 sections and fixed H3 sections, in order:

```text
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
### one or more source target or product headings
```

- `점검 내용`, `점검 목적`, `보안 위협`, `대상`, and `조치 방법` each contain one paragraph.
- `참고` contains `> **참고**` notes. Preserve separate topics as separate notes.
- `판단 기준` contains exactly two unordered items, first `**양호:**`, then `**취약:**`.
- `조치 시 영향` contains one paragraph or an unordered list when the source enumerates impacts.
- Preserve source target and product capitalization in remediation headings.
- Use H4 only for a service, protocol, version, or subordinate environment shown by the source.
- Express procedures as ordered lists. Keep commands, configuration, output, and literals in a
  separate fenced block indented beneath the owning step.
- Use fenced info strings in the form `<language> <contentType>`. The content type is one of
  `command`, `configuration`, `output`, or `literal`.
- Represent semantic tables as GFM tables. Do not flatten a table into prose.
- Use inline code for paths, commands, options, configuration keys, and configuration values in prose.
- Do not add raw HTML or MDX.
- Add `### 추가 지침` only as the last remediation H3 when the source has platform-independent
  supplementary guidance.

## Status boundary

This is an AI-generated review candidate. Set `analysisStatus` to `needsSourceReview` when any source
text, structure, or provenance remains uncertain. Never mark content reviewed or approved, and never
change a review workflow state.
