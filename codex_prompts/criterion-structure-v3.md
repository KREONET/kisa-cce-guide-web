# Criterion vision OCR and semantic conversion

Convert exactly one KISA CCE criterion from source-page images into structured data.
This is a vision OCR and semantic structuring task, not transcript reformatting.

`unix/u-01.md` is the canonical formatting exemplar for this repository. Every converted criterion must
produce the same heading composition, section body forms, and notation as that document. The canonical
format contract in the conversion policy is normative; this prompt restates the parts you must satisfy.

## Required procedure

1. Read the task JSON, conversion policy, taxonomy, result schema, existing criterion Markdown,
   provenance sidecar, and structured exemplars listed in the task. Treat the structured exemplars
   as the required output shape, not as optional references.
2. Inspect every attached source-page image with vision. Match each attachment to its task record by `imagePath` and `imageChecksum`, then emit exactly one `sourcePageInspections` record for every image. Listing a page without inspecting its image is invalid.
3. Treat source-page images as the visual authority. Use each `transcript` only to navigate to likely regions. Do not copy, paraphrase, segment, or publish the transcript without independently reading the corresponding image.
4. Perform OCR from the images and preserve every visible source section, table, step marker, command, configuration value, output line, path, option, number, and anomaly. Never silently correct source text.
5. Emit typed nodes in visual reading order. A plain paragraph containing a page transcript, or a sequence of paragraphs that merely divides a transcript, is invalid.
6. Use heading nodes for hierarchy, ordered list items for procedures, code blocks with `command`, `configuration`, `output`, or `literal` content types, and table nodes for visually tabular data. Keep commands, configuration, and output in separate code blocks.
7. Transcribe text contained inside an embedded screenshot, diagram, or other image into the appropriate heading, paragraph, list, code, table, or note nodes with `sourceContentType: embeddedImageText`. An image node and alternative text do not substitute for semantic transcription of visible text.
8. Use image nodes only for meaningful non-text visuals. Do not emit the attached source-page render itself as an image node.
9. Record visual provenance for every node. Set each source span's `evidenceOrigin` to `pageImage`, `embeddedImage`, or `mixed`; transcript-only provenance is invalid. `sourceTextExcerpt` is text read from the cited image and may differ from or be absent from the navigation transcript. Record that relationship in `transcriptAlignment`.
10. Preserve OCR and source uncertainty. Mark uncertain spans, describe the uncertainty, add a targeted annotation or unresolved question, set the page inspection and semantic coverage to their uncertainty variants, and set `analysisStatus` to `needsSourceReview`. Do not guess missing text.
11. Copy every required technical literal exactly into `quality.preservedTechnicalLiterals` and preserve it in the appropriate typed node fields.
12. Do not edit repository files. Return only the JSON object required by the result schema.
13. Every node and source span must include every schema field. Set fields that do not apply to that node type to `null`.
14. Use `sourceContentType: pageText` and `publicationDisposition: published` for every heading or
    other node whose text is visibly present in the source page image, including the eleven fixed
    canonical headings. Reserve `derivedStructure` with `publicationDisposition: derived` only for
    a structural heading that is absent from the source and added solely to satisfy the canonical
    hierarchy, such as an `추가 지침` wrapper around visible platform-independent guidance.

## Semantic coverage contract

- Every source page must have at least one node whose source span cites that page.
- Set `transcriptAlignment` to `exact` only when the excerpt is a literal substring of the page transcript. Use `differs` for every non-literal match, including whitespace, punctuation, inserted heading, or reading-order differences. Use `notPresent` when the transcript contains no corresponding text, including text found only inside an embedded image.
- `sourcePageInspections[].observedContentTypes` must equal the semantic content types represented
  by nodes whose source spans cite that page. Do not include a visual layout container such as the
  overview grid as `table` when its content is correctly decomposed into headings, prose, notes, and
  lists instead of a semantic table node.
- `sourcePageInspections[].observedNodeIdentifiers` must list exactly the nodes supported by that page image.
- Compute each page's `observedNodeIdentifiers` as the exact set of node identifiers whose
  `sourceSpans` contain that `physicalPage`. A node with spans on multiple pages must appear in
  every corresponding page inspection, not only the page where the node begins or ends.
- `quality.semanticCoverageStatus: complete` asserts that all visible criterion text has been represented as typed semantic nodes.
- Use `completeWithUncertainty` only with `analysisStatus: needsSourceReview` and explicit uncertainty records.
- Never use `semanticRole: sourceEvidence`, `transcription`, or an equivalent catch-all role to carry raw page text.
- Put table text in `tableCaption`, `tableHeaders`, and `tableRows`; do not flatten it into `content`.
- Put command, configuration, output, and literal text in `codeBlock.content` with the matching `codeContentType`; do not put it in a paragraph or list item.
- Every value in the task's `requiredTechnicalLiterals` must occur verbatim in the searchable content
  of at least one semantic node or in `sourceAnnotations[].sourceText`, as well as in
  `quality.preservedTechnicalLiterals`. A declaration in the quality array alone is invalid. When a
  literal is visible only in a screenshot caption or label, emit an appropriate paragraph or
  `literal` code block node with embedded-image provenance instead of dropping it.

## Canonical format contract

Apply this contract for both `systemCriterion` and `webApplicationCriterion` recommendations.

- Use taxonomy `identifier` values in `targetIdentifiers`, never source labels or display labels.
  Preserve the exact source labels only in `sourceTargetText` and heading content. For example,
  `SOLARIS, LINUX, AIX, HP-UX 등` maps to `solaris`, `linux`, `aix`, and `hp-ux`.

### Heading composition

Emit exactly these headings, in this order, as heading nodes.

- H2 `개요`
  - H3 `점검 내용`
  - H3 `점검 목적`
  - H3 `보안 위협`
  - H3 `참고`
- H2 `점검 대상 및 판단 기준`
  - H3 `대상`
  - H3 `판단 기준`
  - H3 `조치 방법`
  - H3 `조치 시 영향`
- H2 `점검 및 조치 사례`
  - One or more H3 target platform or product headings

- Emit no other H2. The H2 sequence must match exactly, not merely start with these three.
- Emit the four `개요` H3 headings and the four `점검 대상 및 판단 기준` H3 headings in the order shown, with no additions or omissions.
- Do not replace these required headings with paragraph, note, table, or list nodes.
- When a source page carries no content for a required section, still emit the heading, then record the gap in `sourceAnnotations` or `quality.unresolvedQuestions` and set `analysisStatus` to `needsSourceReview`. Do not drop the heading.
- Place an `추가 지침` H3, when the source contains platform-independent supplementary guidance, as the last H3 under `점검 및 조치 사례`.

### Section body forms

| Section | Required body |
| --- | --- |
| `점검 내용` | One paragraph node |
| `점검 목적` | One paragraph node |
| `보안 위협` | One paragraph node |
| `참고` | Note nodes using the `참고` label |
| `대상` | One paragraph node preserving the source target string |
| `판단 기준` | Exactly two unordered list items |
| `조치 방법` | One paragraph node |
| `조치 시 영향` | One paragraph node, or unordered list items when the source enumerates several impacts |

- Preserve source sentence endings. Do not normalize the writing style of the source.
- Do not emit headings inside a fixed section body.

### Judgment criteria notation

`판단 기준` must contain exactly one 양호 item followed by exactly one 취약 item, rendered as:

```markdown
- **양호:** 원격터미널 서비스를 사용하지 않거나, 사용 시 root 직접 접속을 차단한 경우
- **취약:** 원격터미널 서비스 사용 시 root 직접 접속을 허용한 경우
```

- Keep the colon inside the strong span and place exactly one space after it.
- Use no judgment label other than `양호` and `취약`.

### Remediation case headings

- Preserve source capitalization for operating system and product headings, such as `SOLARIS`, `LINUX`, `AIX`, and `HP-UX`.
- Preserve source capitalization for service, protocol, and distribution headings, such as `Telnet`, `SSH`, `Redhat`, and `Debian`.
- Treat brackets used only as visual heading markers as `sourceMarker`, not heading content. For
  example, source `[11.v2 이하 버전]` becomes heading content `11.v2 이하 버전` with the original
  bracket marker preserved separately.
- Omit the H4 level when a target platform has no service or environment subdivision, and attach the procedure directly under the H3.
- Do not invent a target heading that the source page does not show.

### Procedures

- Express every procedure as ordered list items, including a procedure with a single step.
- Describe the action in the list item text and keep the command, configuration, or expected output in a separate code block node attached to that item.
- A procedure list item must cite only the page image that visibly contains its Step text. When its
  command, configuration, or output continues on another page, cite that page on the separate
  code block node instead of adding the continuation span to the procedure item.
- Mark file paths, configuration keys, command names, and configuration values as inline code in the list item text.
- Preserve the source step numbering. Do not renumber, merge, or split source steps.

### Notes

- Use `참고`, `주의`, `경고`, or `편집자 주` as the note label.
- Place a note immediately after the procedure or section it qualifies.
- Keep one topic per note. Emit separate notes for separate topics instead of merging them.

## Status boundary

This output is a machine-generated candidate. It can recommend a content model but cannot approve content, resolve an anomaly, or mark a human review complete.
