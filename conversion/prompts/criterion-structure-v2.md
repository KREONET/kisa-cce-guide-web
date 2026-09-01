# Criterion vision OCR and semantic conversion

Convert exactly one KISA CCE criterion from source-page images into structured data.
This is a vision OCR and semantic structuring task, not transcript reformatting.

## Required procedure

1. Read the task JSON, conversion policy, result schema, existing criterion Markdown, provenance sidecar, and structured exemplars listed in the task.
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

## Semantic coverage contract

- Every source page must have at least one node whose source span cites that page.
- Set `transcriptAlignment` to `exact` only when the excerpt is a literal substring of the page transcript. Use `differs` for every non-literal match, including whitespace, punctuation, inserted heading, or reading-order differences. Use `notPresent` when the transcript contains no corresponding text, including text found only inside an embedded image.
- `sourcePageInspections[].observedContentTypes` must identify every semantic content type seen in that page image.
- `sourcePageInspections[].observedNodeIdentifiers` must list exactly the nodes supported by that page image.
- `quality.semanticCoverageStatus: complete` asserts that all visible criterion text has been represented as typed semantic nodes.
- Use `completeWithUncertainty` only with `analysisStatus: needsSourceReview` and explicit uncertainty records.
- Never use `semanticRole: sourceEvidence`, `transcription`, or an equivalent catch-all role to carry raw page text.
- Put table text in `tableCaption`, `tableHeaders`, and `tableRows`; do not flatten it into `content`.
- Put command, configuration, output, and literal text in `codeBlock.content` with the matching `codeContentType`; do not put it in a paragraph or list item.

## System criterion heading contract

When `contentModelRecommendation` is `systemCriterion`, emit these headings as heading nodes in this exact order:

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

Do not replace these required headings with paragraph, note, table, or list nodes.

## Status boundary

This output is a machine-generated candidate. It can recommend a content model but cannot approve content, resolve an anomaly, or mark a human review complete.
