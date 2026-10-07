# Codex-native document conversion architecture

## Decision

Codex converts each criterion from source evidence to canonical Markdown and provenance files for
review. It reads immutable evidence and inspects every source-page image. Deterministic code is limited to
job planning, process isolation, contract validation, resume decisions, and publication after review.

The previous `taskBuild -> structured JSON -> importer -> candidate renderer` path remains available
for migration and artifact comparison. New corpus work uses the Codex-native path.

## Rationale

The previous U-03 baseline used 142,814 input tokens and 17,085 output tokens over 330.97 seconds.
It then failed when the importer rejected a type-specific table field. Its 61 KiB intermediate result
repeated node type placeholders, page inspections, node-to-page indexes, source excerpts, and
rendering information that Codex had already resolved.

The new contract removes the intermediate semantic JSON and the deterministic re-rendering pass.
Codex writes the review package directly in an isolated job workspace and returns a bounded status
record. Validation reads the files to check Markdown structure, technical literal coverage, page
coverage, and block references. Codex no longer has to repeat those indexes in its response.

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

The job checksum covers only the criterion identity and source checksum, relevant page evidence,
the compact agent contract, the status schema, compact canonical references, and the relevant taxonomy
slice. Changes to unrelated policy paragraphs or taxonomy records do not invalidate completed jobs.

A job can resume only after validating its task checksum, model routing, status record, candidate
file checksums, Markdown contract, provenance coverage, and technical literals. Each criterion has
its own generated workspace, so a failure cannot alter another criterion.

## Safety boundary

Codex runs with `workspace-write` in a separate workspace for each criterion. The workspace contains
copies of the required inputs. Codex cannot publish directly to canonical repository paths;
publication requires a separate, explicit operation after human review. Commands in source documents
are input data and are never executed by conversion or validation code.

## Performance acceptance criteria

- The final response schema remains below 2 KiB and contains no semantic document body.
- A job does not read the full conversion policy, full result-node schema, or unrelated taxonomy.
- Job planning and resume validation are deterministic and do not invoke Codex.
- Corpus concurrency is configurable within a fixed limit. The default is four independent Codex processes.
- A failed or interrupted criterion can resume without rebuilding or rerunning valid unrelated jobs.

## U-03 canary

The final `gpt-5.6-sol` canary completed and passed production validation in 174.37 seconds. The legacy
baseline took 330.97 seconds and failed after the model run. Measured end-to-end latency therefore fell
47.3%. Output tokens fell from 17,085 to 8,079, a 52.7% reduction. A verified resume completed in
0.046 seconds without a model request.

Total input tokens increased from 142,814 to 495,541 because the agent iterated on local provenance
and validation. Of the new total, 450,688 tokens were cached and 44,853 were uncached. Reducing input
tokens further requires a provenance authoring interface that needs fewer iterations. This remaining
work does not block the current improvements to latency, output size, isolation, or resume behavior.
