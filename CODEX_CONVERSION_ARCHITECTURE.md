# Codex-native document conversion architecture

## Decision

Codex owns the complete semantic conversion of each criterion. It reads immutable criterion evidence,
inspects every source-page image, and writes a review-ready canonical Markdown and provenance package.
Deterministic code is limited to job planning, process isolation, contract validation, resume decisions,
and review-gated publication.

The previous `taskBuild -> structured JSON -> importer -> candidate renderer` path remains available
for migration and artifact comparison. New corpus work uses the Codex-native path.

## Rationale

The previous U-03 baseline used 142,814 input tokens and 17,085 output tokens, ran for 330.97 seconds,
and then failed because the importer rejected a type-specific table field. The 61 KiB intermediate
result repeated node type placeholders, page inspections, node-to-page indexes, source excerpts, and
rendering information that Codex had already resolved.

The new contract removes the intermediate semantic JSON and deterministic re-rendering pass. Codex
writes the final review package in an isolated job workspace. The final model response is a bounded
status record. Validation derives Markdown structure, technical literal coverage, page coverage, and
block references from the files instead of requiring Codex to repeat those indexes.

## Data flow

```text
Canonical extracted criterion + provenance + source page crops
  -> content-addressed isolated job workspace
  -> one Codex workspace-write run
       -> output/criterion.md
       -> output/provenance.yaml
       -> bounded status.json
  -> deterministic package validation
  -> review candidate
  -> explicit human review
  -> review-gated canonical publication
```

## Invalidation and resume

The job checksum includes only the criterion identity and source checksum, relevant page evidence,
the compact agent contract, the status schema, compact canonical references, and the relevant taxonomy
slice. An unrelated policy paragraph or taxonomy record does not invalidate completed jobs.

A job is resumable only when its task checksum, model routing, status record, candidate file checksums,
Markdown contract, provenance coverage, and technical literals all validate. Generated workspaces are
criterion-scoped, so one failure cannot mutate another criterion.

## Safety boundary

Codex runs with `workspace-write` inside a criterion-specific workspace containing copies of the
required inputs. It cannot publish directly to canonical repository paths. Publication is a separate
explicit operation after human review. Source document commands remain inert input data and are never
executed by conversion or validation code.

## Performance acceptance criteria

- The final response schema remains below 2 KiB and contains no semantic document body.
- A job does not read the full conversion policy, full result-node schema, or unrelated taxonomy.
- Job planning and resume validation are deterministic and do not invoke Codex.
- Corpus concurrency is bounded and configurable. The default is four independent Codex processes.
- A failed or interrupted criterion can resume without rebuilding or rerunning valid unrelated jobs.

## U-03 canary

The final `gpt-5.6-sol` canary completed and passed production validation in 174.37 seconds. The legacy
baseline took 330.97 seconds and failed after the model run, so the measured end-to-end latency fell
47.3%. Output tokens fell from 17,085 to 8,079, a 52.7% reduction. A verified resume completed in
0.046 seconds without a model request.

Total input tokens increased from 142,814 to 495,541 because the agent iterated on local provenance
and validation. Of the new total, 450,688 tokens were cached and 44,853 were uncached. Further input
token reduction requires a lower-iteration provenance authoring interface; it does not block the
current latency, output-size, isolation, or resume improvements.
