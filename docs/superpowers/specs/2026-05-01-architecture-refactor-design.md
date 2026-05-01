# Architecture Refactor Design

## Problem

The project currently ships as a single script, `gif_similarity.py`, which mixes CLI parsing, pipeline orchestration, GIF I/O, feature extraction, clustering, caching, report generation, and visualization. That structure works for a prototype, but it makes the code hard to test, hard to evolve, and risky to change when adding caching improvements, Stage 1 scalability work, or retrieval-oriented features later.

This refactor will keep the project as a command-line tool, but change the internals into a reusable package with explicit boundaries between orchestration, computation, and artifact persistence.

## Goals

1. Preserve the project as a CLI-first tool.
2. Replace the monolithic script with a small package of focused modules.
3. Ensure stage computation does not write files directly.
4. Introduce stable internal result models instead of ad hoc dictionaries and arrays crossing module boundaries.
5. Make future work on caching, Stage 1 scalability, and retrieval features easier without redesigning the project again.

## Non-Goals

1. Redesign Stage 1 candidate generation in this round.
2. Change clustering algorithms in this round.
3. Turn the project into a plugin-based framework.
4. Optimize large-scale performance beyond what is needed to support the refactor.

## Recommended Approach

Use a lightweight modular refactor:

- Keep a thin CLI entrypoint.
- Move orchestration into a pipeline module.
- Split Stage 1 and Stage 2 into computation-focused modules.
- Centralize output writing in an artifact layer.
- Introduce shared dataclasses and typed aliases for internal contracts.

This approach gives most of the maintainability benefit with much less migration risk than a full library redesign or an over-general pipeline framework.

## Alternatives Considered

### 1. Deep library-first redesign

Convert the whole project into a general-purpose Python library with a very thin CLI wrapper.

**Pros**
- Cleanest long-term architecture.
- Best reuse for external callers.

**Cons**
- Larger first-round migration.
- More API design work than this project currently needs.

### 2. Stage registry / pluggable pipeline

Abstract stages into a registry-based system with interchangeable pipeline nodes.

**Pros**
- Strong future extensibility.
- Natural fit if many algorithms will be swapped in and out.

**Cons**
- Premature abstraction for the current codebase.
- Adds architectural weight before the simpler separation problems are solved.

## Target Architecture

```text
gif_similarity.py
    -> CLI argument parsing only
    -> calls package entrypoint

gif_similarity_finder/
    __init__.py
    cli.py              # optional shared CLI helpers
    pipeline.py         # run orchestration for stages and artifact generation
    types.py            # dataclasses / shared result models
    io.py               # GIF collection and frame sampling helpers
    artifacts.py        # JSON / cache / index / report / visualization writing
    stage1.py           # pHash computation and same-source grouping
    stage2.py           # CLIP embedding extraction and action clustering
```

## Module Responsibilities

### `gif_similarity.py`

- Parse CLI arguments.
- Create output directory if needed.
- Call the package-level pipeline entrypoint.
- Report overall completion status.

It should not contain stage logic, report generation, or caching logic.

### `gif_similarity_finder.pipeline`

- Build the end-to-end workflow.
- Decide which stages run based on CLI options.
- Call stage computation modules.
- Call artifact writers after each stage returns a result.
- Own cross-stage control flow and top-level error propagation.

This becomes the only place that knows the full application flow.

### `gif_similarity_finder.io`

- Collect GIF paths.
- Sample frames from GIFs.
- Keep GIF reading concerns separate from stage algorithms where practical.

This module owns low-level input handling and isolates Pillow-specific logic.

### `gif_similarity_finder.stage1`

- Compute perceptual hashes.
- Compare hash outputs.
- Build same-source groups.
- Return a structured Stage 1 result object.

This module should not write JSON or HTML directly.

### `gif_similarity_finder.stage2`

- Load CLIP model.
- Extract embeddings.
- Build the nearest-neighbor index artifact input.
- Cluster embeddings.
- Return a structured Stage 2 result object.

This module should not write cache files, index files, or reports directly.

### `gif_similarity_finder.artifacts`

- Persist Stage 1 JSON output.
- Persist Stage 2 JSON output.
- Read and write embedding cache files.
- Build and save the HNSW index.
- Generate HTML reports.
- Generate optional UMAP visualization.

Centralizing side effects here makes pipeline behavior explicit and makes stage logic easier to test.

### `gif_similarity_finder.types`

Define internal contracts for data exchanged between modules. Likely models include:

- `Stage1Result`
- `Stage2Result`
- `EmbeddingCacheData`
- `PipelineConfig`

The exact shape can stay lightweight, but the goal is to replace loosely coupled raw dictionaries and arrays with named structures.

## Data Flow

1. CLI parses arguments into a config object.
2. Pipeline collects GIF inputs once.
3. Stage 1 consumes the GIF list and returns a Stage 1 result object.
4. Artifact writers persist Stage 1 JSON and HTML outputs.
5. Stage 2 consumes the same GIF list and returns a Stage 2 result object.
6. Artifact writers persist Stage 2 cache, index, JSON, HTML, and optional visualization outputs.
7. Pipeline returns overall completion status to the CLI.

The key rule is: **stages return results, artifact writers persist results**.

## Error Handling

### Per-GIF failures

- If one GIF cannot be read or processed, log a warning and continue.
- Failed GIFs are excluded from the relevant stage result.

### Stage-level empty results

- If a stage produces no usable outputs, it should return an explicit empty result object.
- The pipeline decides whether to skip artifact writing, write empty artifacts, or report a user-facing warning.

### Fatal failures

- Configuration errors, missing input folders, or hard dependency failures should surface clearly and stop the run.
- Avoid broad catch-all suppression at the pipeline level.

## Testing Strategy

Focus on tests that validate module boundaries and pure logic rather than large end-to-end datasets.

### Unit-level priorities

- GIF collection behavior.
- Frame sampling behavior.
- Hash comparison behavior.
- Result grouping logic.
- Cache read/write behavior.
- Artifact writing behavior with small synthetic inputs.

### Integration-level priorities

- A small fixture set that exercises the pipeline with a minimal number of GIFs.
- Smoke coverage for skip-stage flags and output generation.

The first goal is to make the refactor safe, not to build a heavyweight benchmark suite.

## Migration Plan Shape

The implementation should proceed in small, safe moves:

1. Introduce the package and shared types.
2. Move reusable helpers out of the script.
3. Move Stage 1 computation behind a stable interface.
4. Move Stage 2 computation behind a stable interface.
5. Move all file writing into the artifact layer.
6. Reduce `gif_similarity.py` to thin CLI orchestration.
7. Add or update targeted tests around the new boundaries.

## Compatibility Direction

This refactor is allowed to redesign CLI and output structure, but it should still aim for a sane migration path:

- Keep core concepts recognizable (`input`, `output`, stage flags, frame count, clustering parameters).
- Avoid unnecessary renaming when old names are still clear.
- Prefer improved structure over exact backward compatibility where the old shape causes architectural friction.

## Risks

1. Moving code too aggressively could break working behavior.
2. Splitting modules without introducing clear data models would only move complexity around.
3. Artifact writing may still leak back into stage modules if boundaries are not enforced.

The implementation should guard against these by refactoring around explicit contracts and verifying behavior after each major move.

## Expected Outcome

After this refactor, the project should still behave like a command-line GIF analysis tool, but the internal structure should support:

- safer iterative development,
- easier testing,
- cleaner caching improvements,
- future Stage 1 scalability work,
- future retrieval and querying features.
