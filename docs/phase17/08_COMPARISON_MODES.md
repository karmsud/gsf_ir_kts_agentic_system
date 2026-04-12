# Phase 17 — Comparison, Diff & Aggregate Modes

> **Document**: 08_COMPARISON_MODES.md
> **Phase**: 17 — Document-Level Isolation & Cross-Deal Intelligence
> **Status**: Design Specification
> **Last Updated**: 2025-07-14

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current State: ComparisonMode (Phase 15.1)](#2-current-state-comparisonmode-phase-151)
3. [Enhanced /compare Mode](#3-enhanced-compare-mode)
4. [New /diff Mode](#4-new-diff-mode)
5. [New /aggregate Mode](#5-new-aggregate-mode)
6. [ContradictionDetector Enhancements](#6-contradictiondetector-enhancements)
7. [AnomalyScorer Enhancements](#7-anomalyscorer-enhancements)
8. [Integration with Doc Filter](#8-integration-with-doc-filter)
9. [Output Format Specifications](#9-output-format-specifications)
10. [LLM Prompt Templates](#10-llm-prompt-templates)
11. [Performance Budgets](#11-performance-budgets)

---

## 1. Overview

Phase 17 evolves the comparison infrastructure from a single `/compare`
mode into three distinct analysis modes:

| Mode | Purpose | Existing? | Phase 17 Changes |
|------|---------|-----------|-----------------|
| `/compare` | Side-by-side comparison | ✅ Phase 15.1 | + doc_filter support, + multi-scope wildcard |
| `/diff` | Red-flag difference detection | ❌ New | Contradiction + anomaly focused |
| `/aggregate` | Pattern analysis across many deals | ❌ New | Market-standard + outlier detection |

### Mode Selection Matrix

| Command Pattern | Mode | Scopes | Doc Filter |
|----------------|------|--------|-----------|
| `/compare /s1 /s2 concept` | Compare | 2 explicit | No |
| `/compare /s1 /s2 /PSA concept` | Compare | 2 explicit | PSA only |
| `/compare /bear* concept` | Compare | N wildcard | No |
| `/diff /s1 /s2 concept` | Diff | 2 explicit | No |
| `/diff /s1 /s2 /PSA concept` | Diff | 2 explicit | PSA only |
| `/aggregate //PSA concept` | Aggregate | All deals | PSA only |
| `/aggregate /bear* concept` | Aggregate | N wildcard | No |

---

## 2. Current State: ComparisonMode (Phase 15.1)

### 2.1 Existing Implementation

Located at `backend/retrieval/comparison_mode.py`:

```python
class ComparisonMode:
    """Cross-deal comparison mode for /compare slash command."""

    def __init__(self, llm_call_fn=None, max_tokens=3000,
                 temperature=0.3, top_k_per_scope=2):
        ...

    async def compare(self, concept, scope_chunks, *, content_key="content"):
        """Compare a concept across scopes.
        
        Parameters:
            concept: The concept/term to compare
            scope_chunks: {scope_slug: [chunk_dict, ...]}
        
        Returns: ComparisonResult
        """
        ...
```

### 2.2 Existing Data Structures

```python
@dataclass
class ScopeDefinition:
    scope_slug: str
    text: str
    source_section: str = ""

@dataclass
class ComparisonResult:
    concept: str
    scopes_compared: List[str]
    raw_markdown: str = ""
    definitions: List[ScopeDefinition]
    has_divergences: bool = False
```

### 2.3 Existing Retrieval Service Integration

```python
# In retrieval_service.py execute():
if retrieval_mode == "compare" and self._comparison_mode:
    compare_scopes = request.get("compare_scopes", [])
    # Fan-out search across scopes
    fed_results = await router.federated_search(...)
    # Run comparison
    comparison = await self._comparison_mode.compare(concept, scope_chunks)
    # Run contradiction detection
    if self._contradiction_detector:
        contradictions = await self._contradiction_detector.detect_batch(...)
```

### 2.4 Gaps in Current Implementation

| Gap | Impact |
|-----|--------|
| No doc_filter in compare pipeline | Cannot compare specific doc types |
| No diff mode | Cannot focus on material differences |
| No aggregate mode | Cannot analyze patterns across many deals |
| No within-deal comparison | Cannot compare PSA vs Indenture in same deal |
| No wildcard scope support in compare | `/compare /bear*` not supported |

---

## 3. Enhanced /compare Mode

### 3.1 New Features

1. **Doc-type filtering**: `/compare /s1 /s2 /PSA concept`
2. **Wildcard scope**: `/compare /bear* concept`
3. **Within-deal doc comparison**: `/compare /deal/PSA /deal/INDENTURE concept`
4. **Enhanced output**: Table format with per-field breakdown

### 3.2 Enhanced `compare()` Method

```python
async def compare(
    self,
    concept: str,
    scope_chunks: Dict[str, List[Dict[str, Any]]],
    *,
    content_key: str = "content",
    doc_type: Optional[str] = None,          # ← NEW Phase 17
    within_deal: bool = False,               # ← NEW Phase 17
) -> ComparisonResult:
    """Phase 17 enhanced comparison.

    When doc_type is set, adds doc-type context to the prompt.
    When within_deal is True, compares docs within a single deal.
    """
    # Build context-aware prompt
    if within_deal:
        prompt_template = WITHIN_DEAL_COMPARISON_PROMPT
    elif doc_type:
        prompt_template = DOC_TYPE_COMPARISON_PROMPT
    else:
        prompt_template = COMPARISON_PROMPT

    # ... build and execute LLM call ...
```

### 3.3 Within-Deal Comparison

Comparing documents within the same deal (PSA vs Indenture):

```python
# Command: @kts /diff /bear_2006_he1/PSA /bear_2006_he1/INDENTURE Events of Default

# Parser extracts:
# scope_doc_pairs = [
#     ("bear_2006_he1", "PSA"),
#     ("bear_2006_he1", "INDENTURE"),
# ]

# Retrieval:
# For each pair, search with doc_filter
scope_chunks = {}
for scope, doc_type in scope_doc_pairs:
    doc_filter = catalog.resolve_doc_prefix(scope, doc_type)
    results = retriever.retrieve(concept, doc_filter=doc_filter)
    scope_chunks[f"{scope}/{doc_type}"] = results
```

---

## 4. New /diff Mode

### 4.1 Purpose

`/diff` focuses specifically on **material differences** — it is not a
general comparison but a targeted analysis that:
- Highlights contradictions
- Flags anomalies against market baseline
- Assigns severity ratings
- Provides actionable risk flags

### 4.2 DiffEngine Specification

```python
class DiffEngine:
    """Phase 17 — Focused difference detection engine.

    Unlike ComparisonMode which produces a balanced side-by-side view,
    DiffEngine specifically hunts for:
    1. Contradictions (opposite language)
    2. Missing provisions (present in A but absent in B)
    3. Threshold differences (numeric values that differ)
    4. Defined term differences (same term, different definition)
    """

    def __init__(
        self,
        llm_call_fn=None,
        contradiction_detector: Optional[ContradictionDetector] = None,
        anomaly_scorer: Optional[AnomalyScorer] = None,
        max_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.contradiction_detector = contradiction_detector
        self.anomaly_scorer = anomaly_scorer
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def diff(
        self,
        topic: str,
        scope_a: str,
        chunks_a: List[Dict],
        scope_b: str,
        chunks_b: List[Dict],
        *,
        doc_type: Optional[str] = None,
    ) -> DiffResult:
        """Compute focused diff between two scopes.

        Returns DiffResult with categorized differences.
        """
        # Step 1: Run contradiction detection
        contradictions = []
        if self.contradiction_detector:
            text_a = self._combine_chunks(chunks_a)
            text_b = self._combine_chunks(chunks_b)
            contradictions = await self.contradiction_detector.detect(
                topic, {scope_a: text_a, scope_b: text_b}
            )

        # Step 2: Run anomaly scoring on each
        anomalies = {}
        if self.anomaly_scorer:
            for scope, chunks in [(scope_a, chunks_a), (scope_b, chunks_b)]:
                for chunk in chunks:
                    result = self.anomaly_scorer.score(
                        chunk.get("content", ""),
                        clause_type=topic,
                        deal_type=doc_type or "unknown",
                    )
                    if result.is_anomalous:
                        anomalies.setdefault(scope, []).append(result)

        # Step 3: LLM-powered diff analysis
        diff_markdown = await self._llm_diff(
            topic, scope_a, chunks_a, scope_b, chunks_b
        )

        return DiffResult(
            topic=topic,
            scope_a=scope_a,
            scope_b=scope_b,
            contradictions=contradictions,
            anomalies=anomalies,
            raw_markdown=diff_markdown,
            has_material_differences=bool(contradictions) or bool(anomalies),
        )
```

### 4.3 DiffResult Data Structure

```python
@dataclass
class DiffResult:
    """Result of a focused diff analysis."""

    topic: str
    scope_a: str
    scope_b: str
    contradictions: List[ContradictionResult] = field(default_factory=list)
    anomalies: Dict[str, List[AnomalyResult]] = field(default_factory=dict)
    raw_markdown: str = ""
    has_material_differences: bool = False
    missing_provisions: List[Dict] = field(default_factory=list)
    threshold_differences: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "scope_a": self.scope_a,
            "scope_b": self.scope_b,
            "has_material_differences": self.has_material_differences,
            "contradiction_count": len(self.contradictions),
            "anomaly_count": sum(len(v) for v in self.anomalies.values()),
            "raw_markdown": self.raw_markdown,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "anomalies": {
                k: [a.to_dict() for a in v]
                for k, v in self.anomalies.items()
            },
            "missing_provisions": self.missing_provisions,
            "threshold_differences": self.threshold_differences,
        }
```

### 4.4 Diff Detection Algorithms

#### 4.4.1 Missing Provision Detection

```python
async def _detect_missing_provisions(
    self,
    topic: str,
    chunks_a: List[Dict],
    chunks_b: List[Dict],
) -> List[Dict]:
    """Detect provisions present in one scope but missing from the other.

    Uses a two-pass approach:
    1. Extract key provisions from each set
    2. Cross-reference to find gaps
    """
    provisions_a = self._extract_provisions(chunks_a)
    provisions_b = self._extract_provisions(chunks_b)

    missing = []
    for prov in provisions_a:
        if not self._has_matching_provision(prov, provisions_b):
            missing.append({
                "provision": prov["summary"],
                "present_in": self.scope_a,
                "absent_from": self.scope_b,
                "severity": "medium",
            })

    for prov in provisions_b:
        if not self._has_matching_provision(prov, provisions_a):
            missing.append({
                "provision": prov["summary"],
                "present_in": self.scope_b,
                "absent_from": self.scope_a,
                "severity": "medium",
            })

    return missing
```

#### 4.4.2 Threshold Difference Detection

```python
async def _detect_threshold_differences(
    self,
    chunks_a: List[Dict],
    chunks_b: List[Dict],
) -> List[Dict]:
    """Detect differences in numeric thresholds, dates, and percentages.

    Matches patterns like:
    - "60 days" vs "90 days"
    - "0.25%" vs "0.50%"
    - "Class A" priority vs "Class B" priority
    """
    # Extract numeric triplets: (context, number, unit)
    numbers_a = self._extract_numeric_triplets(chunks_a)
    numbers_b = self._extract_numeric_triplets(chunks_b)

    differences = []
    for key, val_a in numbers_a.items():
        val_b = numbers_b.get(key)
        if val_b and val_a["value"] != val_b["value"]:
            differences.append({
                "context": key,
                "value_a": f"{val_a['value']} {val_a['unit']}",
                "value_b": f"{val_b['value']} {val_b['unit']}",
                "severity": "high" if abs(val_a["value"] - val_b["value"]) / max(val_a["value"], 1) > 0.25 else "medium",
            })

    return differences
```

---

## 5. New /aggregate Mode

### 5.1 Purpose

`/aggregate` is designed for portfolio-level analysis. It takes a concept
and analyzes it across many deals to identify:
- **Market standard**: What most deals say
- **Outliers**: Deals that deviate from the standard
- **Patterns**: Common variations and their frequency
- **Trends**: Year-over-year evolution (if vintage data available)

### 5.2 AggregationEngine Specification

```python
class AggregationEngine:
    """Phase 17 — Cross-deal pattern analysis engine.

    Designed for portfolio-level analysis of a concept across
    10+ deals simultaneously.
    """

    def __init__(
        self,
        llm_call_fn=None,
        anomaly_scorer: Optional[AnomalyScorer] = None,
        max_tokens: int = 6000,
        temperature: float = 0.3,
        max_scopes: int = 50,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.anomaly_scorer = anomaly_scorer
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_scopes = max_scopes

    async def aggregate(
        self,
        concept: str,
        scope_chunks: Dict[str, List[Dict]],
        *,
        doc_type: Optional[str] = None,
    ) -> AggregateResult:
        """Analyze a concept across multiple scopes.

        Parameters
        ----------
        concept : str
            The concept or term to analyze.
        scope_chunks : dict
            {scope_slug: [chunks]} — top chunks per scope.
        doc_type : str, optional
            Document type context for anomaly scoring.
        """
        if len(scope_chunks) > self.max_scopes:
            # Subsample to max_scopes
            scope_chunks = dict(
                list(scope_chunks.items())[:self.max_scopes]
            )

        # Step 1: Score each scope's content for anomalies
        scope_scores = {}
        if self.anomaly_scorer:
            for slug, chunks in scope_chunks.items():
                combined = " ".join(
                    c.get("content", "") for c in chunks[:3]
                )
                score = self.anomaly_scorer.score(
                    combined,
                    clause_type=concept,
                    deal_type=doc_type or "unknown",
                )
                scope_scores[slug] = score

        # Step 2: Cluster scopes by similarity
        clusters = self._cluster_by_similarity(scope_chunks)

        # Step 3: LLM analysis
        analysis = await self._llm_aggregate(concept, scope_chunks, clusters)

        # Step 4: Identify outliers
        outliers = [
            slug for slug, score in scope_scores.items()
            if score.is_anomalous
        ]

        return AggregateResult(
            concept=concept,
            total_scopes=len(scope_chunks),
            clusters=clusters,
            outlier_scopes=outliers,
            scope_scores=scope_scores,
            raw_markdown=analysis,
            doc_type=doc_type,
        )
```

### 5.3 AggregateResult Data Structure

```python
@dataclass
class AggregateResult:
    """Result of aggregate pattern analysis."""

    concept: str
    total_scopes: int = 0
    clusters: List[Dict] = field(default_factory=list)
    outlier_scopes: List[str] = field(default_factory=list)
    scope_scores: Dict[str, AnomalyResult] = field(default_factory=dict)
    raw_markdown: str = ""
    doc_type: Optional[str] = None
    pattern_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "total_scopes": self.total_scopes,
            "outlier_count": len(self.outlier_scopes),
            "outlier_scopes": self.outlier_scopes,
            "cluster_count": len(self.clusters),
            "raw_markdown": self.raw_markdown,
            "pattern_summary": self.pattern_summary,
        }

    @property
    def standard_count(self) -> int:
        return self.total_scopes - len(self.outlier_scopes)

    @property
    def outlier_percentage(self) -> float:
        if self.total_scopes == 0:
            return 0.0
        return len(self.outlier_scopes) / self.total_scopes * 100
```

### 5.4 Clustering Algorithm

```python
def _cluster_by_similarity(
    self,
    scope_chunks: Dict[str, List[Dict]],
) -> List[Dict]:
    """Cluster scopes by semantic similarity of their content.

    Uses pairwise cosine similarity between scope embeddings,
    then agglomerative clustering.
    """
    # Get embeddings for each scope's combined content
    scope_embeddings = {}
    for slug, chunks in scope_chunks.items():
        combined = " ".join(c.get("content", "") for c in chunks[:3])
        if combined.strip():
            emb = self._embed(combined)
            if emb is not None:
                scope_embeddings[slug] = emb

    if len(scope_embeddings) < 2:
        return [{"label": "all", "scopes": list(scope_chunks.keys())}]

    # Cosine similarity matrix
    slugs = list(scope_embeddings.keys())
    embeddings = np.array([scope_embeddings[s] for s in slugs])
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity_matrix = normalized @ normalized.T

    # Simple threshold-based clustering
    threshold = 0.85  # High similarity = same cluster
    clusters = self._threshold_cluster(slugs, similarity_matrix, threshold)

    return clusters
```

---

## 6. ContradictionDetector Enhancements

### 6.1 Current Implementation

Located at `backend/retrieval/contradiction_detector.py`:

```python
class ContradictionDetector:
    """LLM-powered contradiction detection between scope definitions."""
    
    async def detect_batch(self, concept, definitions_dict):
        """Detect contradictions across scope definitions.
        
        definitions_dict: {scope_slug: definition_text}
        """
```

### 6.2 Phase 17 Enhancements

```python
class ContradictionDetector:
    """Phase 17 enhanced contradiction detector."""

    async def detect(
        self,
        topic: str,
        scope_texts: Dict[str, str],
    ) -> List[ContradictionResult]:
        """Detect contradictions between scope texts.

        Phase 17: Enhanced to work with arbitrary text (not just definitions),
        supporting provision-level contradiction detection.
        """
        ...

    async def detect_within_deal(
        self,
        topic: str,
        doc_texts: Dict[str, str],
    ) -> List[ContradictionResult]:
        """Detect contradictions between documents within a single deal.

        New in Phase 17: Detects when PSA and Indenture disagree.
        Uses a specialized prompt aware of document hierarchy.
        """
        ...

    async def detect_with_severity(
        self,
        topic: str,
        scope_texts: Dict[str, str],
    ) -> List[ContradictionResult]:
        """Enhanced detection with severity classification.

        New in Phase 17: Each contradiction gets:
        - severity: "high" | "medium" | "low"
        - legal_impact: description of legal implications
        - recommendation: suggested action
        """
        ...
```

### 6.3 Enhanced ContradictionResult

```python
@dataclass
class ContradictionResult:
    """Phase 17 enhanced contradiction result."""

    scope_a: str
    scope_b: str
    description: str
    severity: str = "medium"            # ← NEW Phase 17
    legal_impact: str = ""              # ← NEW Phase 17
    recommendation: str = ""            # ← NEW Phase 17
    text_a: str = ""
    text_b: str = ""
    confidence: float = 0.0
```

---

## 7. AnomalyScorer Enhancements

### 7.1 Current Implementation

Located at `backend/retrieval/anomaly_scorer.py`:

```python
class AnomalyScorer:
    """Scores clauses against market baseline for anomaly detection."""

    def score(self, clause_text, clause_type, deal_type) -> AnomalyResult:
        """Score a single clause. Returns AnomalyResult."""
        ...
```

### 7.2 Phase 17 Enhancements

```python
class AnomalyScorer:
    """Phase 17 enhanced anomaly scorer."""

    def score_across_deals(
        self,
        clause_type: str,
        deal_clauses: Dict[str, str],
    ) -> Dict[str, AnomalyResult]:
        """Score clauses from multiple deals against each other.

        New in Phase 17: Instead of scoring against a pre-built baseline,
        uses the deal clauses themselves as the baseline (consensus = standard).
        """
        if len(deal_clauses) < 3:
            # Not enough data for consensus — use existing baseline
            return {
                slug: self.score(text, clause_type, "unknown")
                for slug, text in deal_clauses.items()
            }

        # Build dynamic baseline from consensus
        all_texts = list(deal_clauses.values())
        consensus_embedding = self._compute_centroid(all_texts)

        results = {}
        for slug, text in deal_clauses.items():
            emb = self._embed(text)
            sim = self._cosine_sim(emb, consensus_embedding)
            score = 1.0 - sim
            results[slug] = AnomalyResult(
                score=score,
                is_anomalous=score > self.anomaly_threshold,
                severity=self._classify_severity(score),
                similarity_to_standard=sim,
                clause_type=clause_type,
            )

        return results
```

---

## 8. Integration with Doc Filter

### 8.1 Compare + Doc Filter

When `/compare` is used with a doc_type filter:

```python
# In retrieval_service.py:

if retrieval_mode == "compare":
    compare_scopes = request.get("compare_scopes", [])
    doc_filter = request.get("doc_filter")                # ← Phase 17
    
    # Fan-out search with doc_filter applied per scope
    async def _search_scope_with_filter(q, slug, k):
        return self.vector_store.search(
            q, top_k=k, scope=slug,
            filters={"doc_name_prefix": doc_filter} if doc_filter else None,
        )
    
    fed_results = await router.federated_search(
        concept, compare_scopes,
        search_fn=_search_scope_with_filter,
        top_k=self._comparison_mode.top_k_per_scope,
    )
```

### 8.2 Diff + Doc Filter

```python
if retrieval_mode == "diff":
    scope_a, scope_b = request["compare_scopes"][:2]
    doc_filter = request.get("doc_filter")
    
    chunks_a = self._retrieve_chunks(concept, scope_a, doc_filter)
    chunks_b = self._retrieve_chunks(concept, scope_b, doc_filter)
    
    diff_result = await self._diff_engine.diff(
        concept, scope_a, chunks_a, scope_b, chunks_b,
        doc_type=request.get("doc_type_filter"),
    )
```

### 8.3 Aggregate + Doc Filter

```python
if retrieval_mode == "aggregate":
    target_scopes = self._resolve_aggregate_scopes(request)
    doc_filter_per_scope = {}
    
    if request.get("doc_type_filter"):
        # Resolve doc_filter for each scope
        for slug in target_scopes:
            prefix = self._resolve_doc_filter(slug, request["doc_type_filter"])
            if prefix:
                doc_filter_per_scope[slug] = prefix
    
    # Fan out with per-scope doc filters
    scope_chunks = await self._multi_scope_retrieve(
        concept, target_scopes,
        doc_filter_per_scope=doc_filter_per_scope,
    )
    
    aggregate_result = await self._aggregation_engine.aggregate(
        concept, scope_chunks,
        doc_type=request.get("doc_type_filter"),
    )
```

---

## 9. Output Format Specifications

### 9.1 /compare Output

```markdown
## Comparison: "{concept}" across {n} deals

| Aspect | {Scope A} | {Scope B} |
|--------|-----------|-----------|
| Definition | "..." | "..." |
| Source | § X.XX | § Y.YY |
| Key Difference | ... | ... |

### Divergence Summary
- ⚠️ {divergence_1}
- ✅ {agreement_1}

📊 Comparison confidence: 0.92
```

### 9.2 /diff Output

```markdown
## Diff: {topic} — {Scope A} vs {Scope B}

### 🔴 Material Differences ({count})
1. **{title}** (Severity: {HIGH|MEDIUM|LOW})
   - {Scope A}: {text}
   - {Scope B}: {text}
   - ⚠️ Impact: {legal_impact}

### ⚠️ Missing Provisions ({count})
- {provision} — present in {Scope A}, absent from {Scope B}

### 📊 Threshold Differences ({count})
| Metric | {Scope A} | {Scope B} | Delta |
|--------|-----------|-----------|-------|
| Days delinquent | 60 | 90 | +30 |

### ✅ Same Across Both
- {agreement_1}
- {agreement_2}

📊 Diff severity: {HIGH|MEDIUM|LOW} | Contradictions: {n}
```

### 9.3 /aggregate Output

```markdown
## Aggregate: {concept} across {n} {doc_type}s

### Market Standard ({standard_count}/{total} deals)
- {standard_provision_1}
- {standard_provision_2}

### Outliers ({outlier_count}/{total} deals)
- ⚠️ **{deal_name}**: {deviation_description}
  Anomaly score: {score} | Severity: {severity}

### Pattern Summary
| Feature | Standard | % Adoption |
|---------|----------|-----------|
| {feature_1} | {value} | {percentage}% |
| {feature_2} | {value} | {percentage}% |

### Trend Analysis
- {trend_1}
- {trend_2}

📊 Scopes analyzed: {n} | Outliers: {outlier_count} ({percentage}%)
```

---

## 10. LLM Prompt Templates

### 10.1 Comparison Prompt (Enhanced)

```python
COMPARISON_PROMPT_V17 = """You are analyzing legal documents for a structured finance knowledge system.

Compare the following {doc_type or 'provisions'} about "{concept}" from {n} different legal documents.

For each source:
1. Quote the key language verbatim
2. Identify substantive legal differences (not just wording differences)
3. Flag any definition that is materially narrower, broader, or structured differently
4. Note any components present in some versions but missing from others

{per_scope_content}

IMPORTANT:
- Focus on LEGAL substance, not drafting style
- Use ⚠️ to flag material divergences that could affect deal economics or investor rights
- Present as a markdown table followed by a divergence summary

Output format:
| Aspect | {scope_headers} |
..."""
```

### 10.2 Diff Prompt

```python
DIFF_PROMPT = """You are a structured finance legal analyst identifying material differences between two deal documents.

Topic: "{topic}"

DOCUMENT A ({scope_a}):
{text_a}

DOCUMENT B ({scope_b}):
{text_b}

Analyze these texts and identify:
1. 🔴 Material contradictions (opposite or conflicting provisions)
2. ⚠️ Missing provisions (present in one, absent from other)  
3. 📊 Threshold/numeric differences (different values for same metric)
4. ✅ Areas of agreement

For each difference:
- Rate severity: HIGH (affects economics/rights), MEDIUM (affects process), LOW (immaterial)
- Explain the legal/economic impact
- Suggest recommended action

Format as structured markdown with severity ratings."""
```

### 10.3 Aggregate Prompt

```python
AGGREGATE_PROMPT = """You are analyzing {n} versions of "{concept}" from different {doc_type} documents to identify market standards and outliers.

{per_scope_content}

Analyze and produce:
1. **Market Standard**: What do the majority of documents say? Quote common language.
2. **Outliers**: Which documents deviate? How and why does it matter?
3. **Pattern Summary**: Table of key features with adoption percentages.
4. **Trend Analysis**: If vintage years vary, note any evolution over time.

Use statistical framing (e.g., "12/15 deals" or "80% adoption").
Flag outliers with ⚠️ and anomaly severity ratings."""
```

---

## 11. Performance Budgets

### 11.1 Latency Targets

| Mode | Scopes | Target Latency | LLM Calls |
|------|--------|---------------|-----------|
| /compare (2 scopes) | 2 | < 5 sec | 1 compare + 1 contradiction |
| /compare (wildcard, 5) | 5 | < 10 sec | 1 compare + 1 contradiction |
| /diff (2 scopes) | 2 | < 8 sec | 1 diff + 1 contradiction |
| /aggregate (10 scopes) | 10 | < 15 sec | 1 aggregate |
| /aggregate (50 scopes) | 50 | < 30 sec | 1 aggregate (subsampled) |

### 11.2 Concurrency

- Multi-scope retrieval: max 5 concurrent searches (semaphore)
- LLM calls: sequential (1 at a time)
- Anomaly scoring: parallel (CPU-bound, uses embeddings)

### 11.3 Token Budget

| Mode | Content per scope | Max scopes | Total content tokens | LLM max_tokens |
|------|------------------|-----------|---------------------|----------------|
| /compare | 500 tokens | 5 | 2,500 | 3,000 |
| /diff | 800 tokens | 2 | 1,600 | 4,000 |
| /aggregate | 300 tokens | 20 | 6,000 | 6,000 |

---

*End of Document — 08_COMPARISON_MODES.md*
