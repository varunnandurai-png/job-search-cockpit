# Phase II Local-Only Match Scoring and Shortlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assess only catalogued real, official job listings against the active Phase I profile and produce an explainable, fail-closed shortlist without using Apify, JSearch, synthetic job listings, or external scoring services.

**Architecture:** This plan adds a local assessment layer on top of immutable Phase II job revisions. It consumes the active profile and career-evidence projections only through `Phase1MatchingPort`, persists append-only eligibility, requirement, score, and shortlist decisions, and revalidates all generation fences before publication. Direct official-source ingestion remains a separate, user-approved implementation plan; this plan neither contacts a source nor makes a live collection request.

**Tech Stack:** Python 3.12, SQLAlchemy, Alembic, Pydantic, FastAPI, SQLite, pytest, Ruff, mypy.

## Global Constraints

- Exclude Apify and JSearch from all future Phase II discovery and corpus work. Do not add credentials, dependencies, API calls, browser automation, proxies, schedules, webhooks, uploads, sharing, notifications, or external model calls.
- Use only real listings from explicitly approved official public ATS endpoints or official employer pages. Do not create synthetic job listings, save provider responses as fixtures, or treat leads from aggregators as official verification.
- This plan performs no live collection. Before any collection, an exact provider-instance/host/tenant containment plan and a user-started run must be approved separately.
- Use `Phase1MatchingPort` exclusively for profile, readiness, taxonomy, and fact access. Never read Phase I tables, cache career wording in Phase II, or emit facts beyond an authorized projection.
- A score is not a readiness authorization. Existing `VerifiedJobPreparationPort` and Phase III boundaries remain unchanged.
- Requirement extraction classifies listing prose into bounded taxonomy references and cited spans; it never turns job-description prose into career claims or evidence.
- Preserve original public source text only in the existing local catalog retention boundary. New assessment records contain identifiers, citations, hashes, bounded reason codes, numeric results, and safe metadata—not duplicated résumé text, provider secrets, or unrestricted prose.
- Require an immutable, independently reviewed real-listing corpus of at least 30 approved official listings before rubric calibration, threshold acceptance, or end-to-end scoring acceptance. The corpus is evaluation input, not test fixtures, and is not created by this plan.
- Follow TDD for each task: first a failing focused test, then the smallest implementation, then focused tests; commit and push each accepted increment only when the user requests it.

---

## File structure

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/assessment_types.py` | Immutable taxonomy, gate, requirement, score, confidence, and shortlist value objects. |
| `src/job_search_cockpit/phase2/eligibility.py` | Fixed profile gates and independent location-path evaluation. |
| `src/job_search_cockpit/phase2/assessment.py` | Requirement extraction, fact-set revalidation, fixed arithmetic, and append-only assessment publication. |
| `src/job_search_cockpit/phase2/shortlist.py` | Deterministic, explainable focused-list and full-list views. |
| `src/job_search_cockpit/phase2/models.py` | Append-only metadata models for assessments, components, mappings, and shortlist decisions. |
| `alembic_phase2/versions/0008_match_scoring_shortlist.py` | New Phase II assessment schema and SQLite immutability triggers. |
| `src/job_search_cockpit/phase2/runtime.py` | Wires assessment and shortlist services without replacing preparation authorization. |
| `src/job_search_cockpit/web/routes/phase2.py` | Read-only, authenticated local assessment and shortlist views only. |
| `src/job_search_cockpit/web/templates/phase2_local_review.html` | Safe escaped rendering of assessment summaries and warnings. |
| `tests/unit/test_phase2_eligibility.py` | Fixed-rule, location-path, and fail-closed tests using abstract assessment inputs, not job listings. |
| `tests/unit/test_phase2_scoring.py` | Taxonomy, arithmetic, evidence-mapping, and confidence tests using opaque IDs and bounded clauses. |
| `tests/integration/test_phase2_assessment_database.py` | Schema, append-only, invalidation, and prohibited-content tests. |
| `tests/integration/test_phase2_scoring_runtime.py` | Port revalidation, publication, shortlist, and route-security tests. |

## Task 1: Freeze local assessment contracts and the no-aggregator boundary

**Files:**
- Create: `src/job_search_cockpit/phase2/assessment_types.py`
- Modify: `src/job_search_cockpit/phase2/providers.py`
- Modify: `src/job_search_cockpit/phase2/provider_config.py`
- Test: `tests/unit/test_phase2_scoring.py`

**Consumes:** Existing immutable `Phase2JobRevision` records and Phase I matching-port snapshots.

**Produces:** Bounded assessment input/output types and a provider configuration that cannot select Apify or JSearch.

- [ ] **Step 1: Write failing boundary and type tests**

```python
def test_aggregator_provider_ids_are_not_supported() -> None:
    with pytest.raises(ValueError, match="official provider instance"):
        ProviderRequest(provider_id="jsearch", role_query_id="x", location_id="y", listing_limit=1)


def test_score_components_are_bounded_to_the_approved_total() -> None:
    result = MatchScoreComponents(role=25, domain=20, responsibility=15, technical=15,
                                  outcome=10, seniority=10, evidence=5)
    assert result.total == 100
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `uv run pytest tests/unit/test_phase2_scoring.py -q`

Expected: FAIL because the assessment contracts and aggregator rejection do not yet exist.

- [ ] **Step 3: Implement minimal frozen contracts**

Define `GateResult`, `EligibilityState`, `RequirementKind`, `EvidenceRelation`, `ConfidenceState`, `AssessmentInvalidation`, `LocationEligibilityPath`, `Requirement`, `RequirementEvidenceMapping`, `MatchScoreComponents`, and `MatchAssessmentResult` as frozen value objects. Reject unrecognized provider IDs before a request can be prepared; remove Apify/JSearch credential loading only in the separately approved direct-source migration, leaving this task limited to deny-by-default selection. Accept only the fixed score maxima `20, 20, 20, 15, 10, 10, 5` and make totals derived.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/unit/test_phase2_scoring.py tests/unit/test_provider_config.py -q && uv run ruff check src/job_search_cockpit/phase2/assessment_types.py src/job_search_cockpit/phase2/providers.py src/job_search_cockpit/phase2/provider_config.py && uv run mypy src`

Expected: PASS; no test performs network I/O or constructs a job listing.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/assessment_types.py src/job_search_cockpit/phase2/providers.py src/job_search_cockpit/phase2/provider_config.py tests/unit/test_phase2_scoring.py && git commit -m "feat: define local scoring contracts"`

### Task 2: Add append-only assessment persistence

**Files:**
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/0008_match_scoring_shortlist.py`
- Create: `tests/integration/test_phase2_assessment_database.py`

**Consumes:** `Phase2JobRevision`, Phase II authority generations, and Task 1 identifiers.

**Produces:** Immutable job-gate, location-path, assessment, component, requirement-mapping, and shortlist-decision rows.

- [ ] **Step 1: Write failing schema tests**

```python
def test_assessment_schema_is_append_only_and_does_not_duplicate_listing_or_fact_text(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    columns = _columns(phase2_settings.database_path, "phase2_match_assessments")
    assert {"job_revision_id", "rubric_version", "total_score", "fact_set_fingerprint"} <= columns
    assert not {"public_description", "safe_wording", "token", "api_key", "resume_text"} & columns
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/integration/test_phase2_assessment_database.py -q`

Expected: FAIL because the assessment tables and triggers do not exist.

- [ ] **Step 3: Add the minimum append-only schema**

Create `phase2_job_gate_assessments`, `phase2_location_eligibility_paths`, `phase2_match_assessments`, `phase2_match_components`, `phase2_requirement_mappings`, and `phase2_shortlist_decisions`. Bind every derived row to the exact job revision, active profile fingerprint/generation, Phase I readiness/authority/restore generations, and Phase II activation/restore generations. Store source citation offsets, taxonomy IDs, opaque fact IDs/revision IDs, reason codes, component scores, ledger/fact-set fingerprints, and timestamps. Add update/delete rejection triggers and foreign keys; do not persist job prose or fact wording in the new tables.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/integration/test_phase2_assessment_database.py -q && uv run ruff check src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0008_match_scoring_shortlist.py tests/integration/test_phase2_assessment_database.py && uv run mypy src && git diff --check`

Expected: PASS; attempts to update or delete an assessment row fail.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0008_match_scoring_shortlist.py tests/integration/test_phase2_assessment_database.py && git commit -m "feat: persist immutable match assessments"`

### Task 3: Implement fixed eligibility and independent location paths

**Files:**
- Create: `src/job_search_cockpit/phase2/eligibility.py`
- Test: `tests/unit/test_phase2_eligibility.py`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** A current `SearchProfileSnapshot`, a job revision, and no Phase I table access.

**Produces:** `EligibilityAssessment` with job-wide gates and separately evaluated `LocationEligibilityPath` results.

- [ ] **Step 1: Write failing profile-gate tests**

```python
def test_one_passing_location_path_is_not_contaminated_by_another_failed_path() -> None:
    assessment = assess_eligibility(_profile(), _revision_with_two_locations())
    assert assessment.state is EligibilityState.ELIGIBLE
    assert {path.state for path in assessment.location_paths} == {"pass", "fail"}


def test_unknown_hard_gate_fails_closed_for_shortlist() -> None:
    assessment = assess_eligibility(_profile(), _revision_with_unknown_role_scope())
    assert assessment.shortlist_allowed is False
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/unit/test_phase2_eligibility.py -q`

Expected: FAIL because fixed eligibility evaluation does not exist.

- [ ] **Step 3: Implement only the approved fixed rules**

Evaluate positive eligible-role matching, excluded employer/role checks, job lifecycle freshness, compensation state, Singapore sponsorship, notice-period compatibility, employer identity/risk consequences, and per-location pass/conditional/fail aggregation from the current profile. Do not blend evidence between locations. Unknown potentially failing gates remain conditional and block shortlist/readiness as specified. Return reason codes and source-span citations; do not use score to repair a failed gate.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/unit/test_phase2_eligibility.py tests/integration/test_phase2_scoring_runtime.py -q && uv run ruff check src/job_search_cockpit/phase2/eligibility.py tests/unit/test_phase2_eligibility.py && uv run mypy src`

Expected: PASS for all-profile gates, multi-location isolation, compensation/notice boundaries, and unknown fail-closed cases.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/eligibility.py tests/unit/test_phase2_eligibility.py tests/integration/test_phase2_scoring_runtime.py && git commit -m "feat: add fail-closed job eligibility"`

### Task 4: Extract bounded requirements and revalidate fact evidence

**Files:**
- Create: `src/job_search_cockpit/phase2/assessment.py`
- Modify: `src/job_search_cockpit/phase2/requirements.py`
- Test: `tests/unit/test_phase2_scoring.py`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** Current Phase I matching-port snapshots and the exact assessed job revision.

**Produces:** A cited taxonomy requirement set and a complete fact-set/ledger result, or a fail-closed assessment denial.

- [ ] **Step 1: Write failing fact-boundary tests**

```python
def test_incomplete_fact_set_cannot_publish_a_score() -> None:
    service = AssessmentService(_incomplete_phase1_port(), _coordinator())
    with pytest.raises(AssessmentUnavailable, match="complete matching fact set"):
        service.assess("job-revision-id")


def test_unclassified_gate_relevant_clause_blocks_publication() -> None:
    with pytest.raises(AssessmentUnavailable, match="unclassified requirement"):
        extract_requirements(_gate_relevant_unclassified_text())
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/unit/test_phase2_scoring.py tests/integration/test_phase2_scoring_runtime.py -q`

Expected: FAIL because assessment extraction and fact-set validation do not exist.

- [ ] **Step 3: Implement constrained extraction and port-only evidence access**

Convert only bounded, cited clauses of the immutable job revision into versioned taxonomy predicates. Reject control characters, instruction-like content, unknown taxonomy values, excess clauses, unclassified gate-relevant text, unsupported boolean nesting, and malformed spans. Request the complete matching fact set via `Phase1MatchingPort`; require current, non-sensitive, approved, exact-revision support and reject incomplete, stale, malformed, or changed snapshots. Keep only opaque references and reason codes in Phase II persistence; `RequirementLedger` remains the sole bridge to authorised Phase I safe wording for Phase III.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/unit/test_phase2_scoring.py tests/integration/test_phase2_scoring_runtime.py -q && uv run ruff check src/job_search_cockpit/phase2/assessment.py src/job_search_cockpit/phase2/requirements.py tests/unit/test_phase2_scoring.py && uv run mypy src`

Expected: PASS; Phase I tables, raw facts, and job prose are not accessed outside their permitted boundaries.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/assessment.py src/job_search_cockpit/phase2/requirements.py tests/unit/test_phase2_scoring.py tests/integration/test_phase2_scoring_runtime.py && git commit -m "feat: add evidence-bound requirement assessment"`

### Task 5: Calculate the fixed seven-component score and confidence

**Files:**
- Modify: `src/job_search_cockpit/phase2/assessment.py`
- Test: `tests/unit/test_phase2_scoring.py`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** Task 3 eligibility, Task 4 requirement/evidence mappings, and the frozen rubric version.

**Produces:** An immutable 0–100 score, seven component results, confidence state, gaps, and invalidation metadata.

- [ ] **Step 1: Write failing arithmetic tests**

```python
def test_component_caps_prevent_duplicate_evidence_from_inflating_score() -> None:
    result = calculate_match_score(_mapping_with_duplicate_support())
    assert result.components.role == 25
    assert result.total <= 100


def test_incomplete_or_uncertain_evidence_cannot_cross_shortlist_threshold() -> None:
    result = calculate_match_score(_mapping_with_semantic_unknown())
    assert result.confidence is ConfidenceState.BLOCKED
    assert result.shortlist_eligible is False
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/unit/test_phase2_scoring.py -q`

Expected: FAIL because fixed score arithmetic and confidence thresholds do not exist.

- [ ] **Step 3: Implement the locked arithmetic**

Calculate role fit (25), domain fit (20), responsibility fit (15), technical fit (15), outcomes/scale (10), seniority/scope (10), and evidence quality (5) using only validated direct/adjacent/no-support reason codes. Apply fixed per-requirement caps, one winning citation for alternatives, AND independence, single-weight OR handling, zero-denominator rules, and declared confidence/breadth thresholds. Keep compensation, sponsorship, employer review/risk, freshness, and notice compatibility outside the numeric score. Persist no score if a required input is incomplete, stale, or invalidated.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/unit/test_phase2_scoring.py tests/integration/test_phase2_scoring_runtime.py -q && uv run ruff check src/job_search_cockpit/phase2/assessment.py tests/unit/test_phase2_scoring.py && uv run mypy src`

Expected: PASS for maxima, anchors, alternatives, duplicate dilution, stale snapshots, and score-band boundaries.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/assessment.py tests/unit/test_phase2_scoring.py tests/integration/test_phase2_scoring_runtime.py && git commit -m "feat: calculate explainable match scores"`

### Task 6: Publish deterministic focused shortlist and secure local views

**Files:**
- Create: `src/job_search_cockpit/phase2/shortlist.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_local_review.html`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** Current valid assessments and active Phase I/II generation fences.

**Produces:** A maximum-20 focused shortlist, searchable full-list view, and authenticated local read-only routes.

- [ ] **Step 1: Write failing shortlist and route-security tests**

```python
def test_shortlist_is_capped_and_does_not_promote_unknown_hard_gates() -> None:
    view = ShortlistService(_store()).focused(limit=20)
    assert len(view.jobs) <= 20
    assert all(job.eligibility_state != "conditional_hard_gate_unknown" for job in view.jobs)


def test_assessment_view_requires_the_local_authenticated_session(client: TestClient) -> None:
    response = client.get("/phase-2/assessments/job-revision-id")
    assert response.status_code in {401, 403}
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/integration/test_phase2_scoring_runtime.py -q`

Expected: FAIL because the shortlist service and protected read-only routes do not exist.

- [ ] **Step 3: Implement publication with revalidation**

Define stable ordering: valid eligible assessments first by score, then confidence, current source freshness, and immutable assessment ID; keep conditional jobs separately marked and do not let quotas override strength. Limit the focused list to 20 and expose other permitted records through the full list. Before every read/publication, revalidate activation, profile, readiness, authority, and restore generations; present stale results only as redacted historical metadata. Use the existing local session/CSRF pattern, escape all text, return no artifact paths or career wording, and provide no route that triggers collection, assessment mutation, finalisation, upload, sharing, or submission.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/integration/test_phase2_scoring_runtime.py tests/integration/test_phase3_routes.py -q && uv run ruff check src/job_search_cockpit/phase2/shortlist.py src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py && uv run mypy src`

Expected: PASS; anonymous/CSRF-invalid mutation attempts fail, output is escaped, and assessment reads cannot bypass revalidation.

- [ ] **Step 5: Commit the increment when requested**

Run: `git add src/job_search_cockpit/phase2/shortlist.py src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py src/job_search_cockpit/web/templates/phase2_local_review.html tests/integration/test_phase2_scoring_runtime.py && git commit -m "feat: publish local match shortlist"`

### Task 7: Calibrate only against the approved real-listing corpus and complete acceptance

**Files:**
- Modify: `docs/superpowers/reviews/2026-08-20-phase-2-design-qa.md`
- Test: `tests/e2e/test_phase2_scoring_acceptance.py`

**Consumes:** User-approved, frozen, real official listing corpus; independently adjudicated expected outcomes; completed Tasks 1–6.

**Produces:** A signed local acceptance receipt or a documented fail-closed rejection; no generated listing fixtures are committed.

- [ ] **Step 1: Record corpus provenance before any calibration**

Record only corpus item IDs, official source URLs, retrieval timestamps, source fingerprints, approval event IDs, adjudicator IDs, taxonomy/rubric versions, and expected decision IDs in the local review record. Reject a corpus with fewer than 30 items, non-official sources, mutable/missing fingerprints, unapproved hosts, or unresolved adjudication. Do not copy listing bodies into tests or documentation.

- [ ] **Step 2: Write a failing acceptance test driven by the local approved corpus registry**

```python
def test_scoring_acceptance_requires_a_frozen_real_official_corpus(
    approved_corpus: ApprovedCorpusRegistry,
) -> None:
    assert approved_corpus.count >= 30
    assert approved_corpus.all_items_are_official
    assert approved_corpus.is_frozen
```

- [ ] **Step 3: Run it and confirm it fails until the user approves a real corpus**

Run: `uv run pytest tests/e2e/test_phase2_scoring_acceptance.py -q`

Expected: FAIL closed with a clear missing-corpus reason. This is expected until a separate user-started official-source collection and corpus review are complete.

- [ ] **Step 4: Execute end-to-end acceptance only after separate collection approval**

Verify the approved corpus against gates, expected requirement classifications, evidence mappings, component scores, confidence, score bands, shortlist inclusion/exclusion, stale/drift invalidation, and no Phase III authorization bypass. Render and inspect the local read-only assessment pages with only synthetic/non-listing UI test data; do not generate résumés or make external requests as part of visual QA.

- [ ] **Step 5: Run final quality gates and commit/push only when requested**

Run: `uv run ruff check src tests && uv run mypy src && uv run pytest -q && git diff --check`

Expected: PASS once the separately approved corpus exists. Then use `git status --short`, `git rev-parse HEAD`, `git push origin Dev`, and `git rev-parse origin/Dev` to prove a clean working tree and matching local/remote heads.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| An unapproved URL turns discovery into SSRF or scope creep | This plan makes no requests; the future direct-source plan must enforce exact HTTPS host/tenant/redirect containment before a user-started run. |
| Aggregator or third-party retention conflicts with local-only design | Apify and JSearch are excluded; only approved direct official sources may later populate the corpus. |
| Listing prose attempts to influence classification or invent claims | Treat text as inert evidence, require bounded taxonomy/citations, quarantine hostile text, and use Phase I's authorized projection for claims. |
| Stale Phase I evidence creates an attractive but unsafe score | Revalidate Phase I/II fingerprints and generations before extraction, publication, display, shortlist, and readiness. |
| Scores become opaque or inflated | Fixed component maxima, deterministic arithmetic, per-requirement caps, immutable mappings, and independent real-corpus adjudication. |
| Tests accidentally become synthetic job-listing corpus | Tests exercise abstract contracts with opaque identifiers only; calibration/acceptance consumes the separately approved real corpus and stores provenance rather than bodies. |

## Self-review

- The plan implements only broader Phase II match scoring and shortlist capability already authorized by the 2026-08-20 design.
- It explicitly excludes Apify and JSearch and does not authorize any live collection, third-party storage, dependency, or retention change.
- Every task has a failing-test step, focused verification, and a separate commit point.
- Phase I data stays behind `Phase1MatchingPort`; Phase III authorization and finalisation boundaries are untouched.
- Real listings are required for calibration and acceptance; no synthetic job listings or saved live response fixtures are introduced.
