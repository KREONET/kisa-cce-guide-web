# Criterion semantic conversion

Convert exactly one KISA CCE criterion from extracted evidence into structured data.

## Required procedure

1. Read the task JSON, conversion policy, result schema, existing criterion Markdown, provenance sidecar, and structured exemplars listed in the task.
2. Inspect every attached source-page image. Treat the rendered PDF pages as the final visual authority and the extracted transcript as supporting evidence.
3. Preserve every source page, section, table, step marker, command, path, option, number, and source anomaly. Never silently correct source text.
4. Emit nodes in source reading order. Use headings for semantic hierarchy, typed list items for procedures, code blocks for commands and configuration, semantic tables for matrix data, and image nodes only for meaningful visuals.
5. Record source spans for every node. Excerpts must appear verbatim in the task transcript for the referenced page.
6. Copy every required technical literal exactly into `quality.preservedTechnicalLiterals` and preserve it in node content.
7. Set `analysisStatus` to `needsSourceReview` when the source is ambiguous, truncated, contradictory, or visually unreadable.
8. Do not edit repository files. Return only the JSON object required by the result schema.
9. Every node must include every schema field. Set fields that do not apply to that node type to `null`.

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
