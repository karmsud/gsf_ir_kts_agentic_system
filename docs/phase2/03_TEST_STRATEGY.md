# Phase 2 — Comprehensive Test Strategy

## Testing Goals
- Validate every agent and major function path
- Cover positive, negative, edge, and corner cases
- Validate end-to-end workflows from crawl through analytics
- Validate command-line operational usability

## Test Layers

1. **Unit-level functional tests**
   - Common utilities: cleaning, chunking, hashing, manifest, quality gates
   - Agent-specific behavior and contract validation

2. **Agent integration tests**
   - Ingestion + taxonomy + graph + retrieval
   - Training/impact/freshness over graph data
   - Vision manifest and indexing lifecycle

3. **CLI integration tests**
   - Real command execution via subprocess
   - Option/flag coverage and output schema checks

4. **Smoke and scenario tests**
   - Full pipeline smoke script
   - Complex fixture workflows and status checks

## 10-Way Scenario Standard
For each major subsystem, at least 10 scenario variants were covered through parameterized or enumerated tests:
- Nominal flow
- Empty input
- Missing input
- Unsupported input
- Boundary values
- Re-run idempotency
- Failure and recovery
- Filtering and narrowing
- Cross-component consistency
- Operational output integrity

## Risk-Driven Focus Areas
- False positives in taxonomy classification
- Retrieval relevance under filters and sparse data
- Freshness calculation under scope/threshold overrides
- Impact analysis for unknown entities
- Vision workflow state transitions and invalid descriptions

## Exit Criteria
- All tests green
- Smoke flow green
- Complex scenario command chain green
- No unresolved runtime failures in phase2 scope
