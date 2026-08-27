# Phase II Assessment Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist only validated, authority-fenced local match-assessment metadata and expose it through a read-only current-assessment view.

**Architecture:** `AssessmentPublicationService` accepts frozen, opaque value objects and uses `AssessmentAuthorityService` plus `Phase2MutationCoordinator` for a single append-only transaction. `AssessmentReviewService` revalidates authority before querying compact current metadata; the route never exposes source prose, fact wording, or actions.

**Tech Stack:** Python 3.12, SQLAlchemy, SQLite, FastAPI, pytest, Ruff, mypy.

## Global Constraints

- No collection, external calls, real-listing corpus, résumé generation, readiness authorization, upload, sharing, or application submission.
- Use `Phase1MatchingPort` only through `AssessmentAuthorityService`; never read Phase I tables.
- Persist only IDs, hashes, fingerprints, bounded enums/reason codes, numeric values, booleans, timestamps, and authority fences.
- Every write is append-only through `Phase2MutationCoordinator`; drift fails closed before any row is written.
- Tests use opaque IDs and abstract assessment inputs, never synthetic listings or career facts.

---

## File structure

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/assessment.py` | Frozen publication command/value objects and authority-fenced append-only writer. |
| `src/job_search_cockpit/phase2/shortlist.py` | Current-only compact read model and deterministic focused-list selection. |
| `src/job_search_cockpit/phase2/runtime.py` | Wires the publication and review services to the existing coordinator. |
| `src/job_search_cockpit/web/routes/phase2.py` | Read-only local assessment route context only. |
| `src/job_search_cockpit/web/templates/phase2_assessments.html` | Escaped compact current-state rendering. |
| `tests/unit/test_phase2_scoring.py` | Publication input validation with opaque identifiers. |
| `tests/integration/test_phase2_assessment_database.py` | Append-only writer and prohibited-content coverage. |
| `tests/integration/test_phase2_scoring_runtime.py` | Authority drift, current read, and authenticated redaction coverage. |

## Task 1: Freeze a publication command

**Files:**
- Modify: `src/job_search_cockpit/phase2/assessment.py`
- Test: `tests/unit/test_phase2_scoring.py`

**Consumes:** `MatchAssessmentResult`, `Requirement`, `RequirementEvidenceMapping`, `LocationEligibilityPath`, and `AssessmentAuthoritySnapshot`.

**Produces:** `AssessmentPublicationCommand` with immutable job-gate, location-path, requirement-mapping, component, fingerprint, and shortlist-decision metadata.

- [ ] **Step 1: Write the failing validation test**

```python
def test_publication_command_rejects_a_mapping_without_a_matching_requirement() -> None:
    command = _publication_command(mapping_requirement_id="requirements.other")
    with pytest.raises(ValueError, match="publication mapping must reference a published requirement"):
        command.validate()
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/test_phase2_scoring.py::test_publication_command_rejects_a_mapping_without_a_matching_requirement -q`

Expected: FAIL because no publication command exists.

- [ ] **Step 3: Implement the frozen command**

```python
@dataclass(frozen=True, slots=True)
class AssessmentPublicationCommand:
    result: MatchAssessmentResult
    requirements: tuple[Requirement, ...]
    mappings: tuple[RequirementEvidenceMapping, ...]
    location_paths: tuple[LocationEligibilityPath, ...]
    rubric_version: str
    coverage_ledger_fingerprint: str
    fact_set_fingerprint: str
    assessment_state: str
    shortlist_reason_codes: tuple[str, ...]

    def validate(self) -> None:
        requirement_ids = {requirement.requirement_id for requirement in self.requirements}
        if not requirement_ids or any(
            mapping.requirement_id not in requirement_ids for mapping in self.mappings
        ):
            raise ValueError("publication mapping must reference a published requirement")
```

Reject empty bounded identifiers, duplicate requirement IDs, mappings for an unlisted requirement, an incomplete seven-component set, unsafe reason codes, and any result whose existing value-object invariants fail.

- [ ] **Step 4: Verify the contract**

Run: `uv run pytest tests/unit/test_phase2_scoring.py -q && uv run ruff check src/job_search_cockpit/phase2/assessment.py tests/unit/test_phase2_scoring.py && uv run mypy src`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/job_search_cockpit/phase2/assessment.py tests/unit/test_phase2_scoring.py && git commit -m "feat: define assessment publication command"`

## Task 2: Persist one authority-fenced append-only assessment

**Files:**
- Modify: `src/job_search_cockpit/phase2/assessment.py`
- Test: `tests/integration/test_phase2_assessment_database.py`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** A validated `AssessmentPublicationCommand`, `AssessmentAuthorityService`, and `Phase2MutationCoordinator`.

**Produces:** `AssessmentPublicationService.publish(command) -> str`, returning the immutable assessment ID after one transaction inserts the gate, paths, assessment, seven components, mappings, and shortlist decision.

- [ ] **Step 1: Write a failing no-write-on-drift integration test**

```python
def test_publication_writes_no_assessment_when_authority_drifts(phase2_settings) -> None:
    service, phase1_port = _publication_service(phase2_settings)
    phase1_port.drift_before_publication = True
    with pytest.raises(AssessmentUnavailable, match="authority changed"):
        service.publish(_publication_command())
    assert _count(phase2_settings.database_path, "phase2_match_assessments") == 0
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/integration/test_phase2_scoring_runtime.py::test_publication_writes_no_assessment_when_authority_drifts -q`

Expected: FAIL because no publication service exists.

- [ ] **Step 3: Implement the transaction**

Capture authority before the coordinator operation. In the operation, revalidate authority, call `command.validate()`, generate UUIDs, add each existing `Phase2JobGateAssessment`, `Phase2LocationEligibilityPath`, `Phase2MatchAssessment`, `Phase2MatchComponent`, `Phase2RequirementMapping`, and `Phase2ShortlistDecision` row, and pass `snapshot.persistence_fields()` to every row. Derive component rows only from `command.result.components`; persist opaque mapping references only; do not query a Phase I model or retain prose.

- [ ] **Step 4: Verify append-only publication**

Run: `uv run pytest tests/integration/test_phase2_assessment_database.py tests/integration/test_phase2_scoring_runtime.py -q && uv run ruff check src/job_search_cockpit/phase2/assessment.py tests/integration/test_phase2_assessment_database.py tests/integration/test_phase2_scoring_runtime.py && uv run mypy src && git diff --check`

Expected: PASS; drift leaves zero rows and successful rows carry identical current fence fields.

- [ ] **Step 5: Commit**

Run: `git add src/job_search_cockpit/phase2/assessment.py tests/integration/test_phase2_assessment_database.py tests/integration/test_phase2_scoring_runtime.py && git commit -m "feat: publish append-only match assessments"`

## Task 3: Read current assessments and focused shortlist safely

**Files:**
- Modify: `src/job_search_cockpit/phase2/shortlist.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_assessments.html`
- Test: `tests/integration/test_phase2_scoring_runtime.py`

**Consumes:** Current revalidated authority and append-only `Phase2MatchAssessment` / `Phase2ShortlistDecision` rows.

**Produces:** A compact `AssessmentReviewView` with deterministic, at-most-20 current shortlist entries or the existing redacted unavailable state.

- [ ] **Step 1: Write a failing focused-list test**

```python
def test_current_review_returns_only_fenced_eligible_assessments(phase2_settings) -> None:
    service = _published_review_service(phase2_settings)
    view = service.current_view()
    assert [item.assessment_id for item in view.focused] == ["assessment-current"]
    assert all(item.score >= 70 for item in view.focused)
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/integration/test_phase2_scoring_runtime.py::test_current_review_returns_only_fenced_eligible_assessments -q`

Expected: FAIL because the review service does not query persisted assessment metadata.

- [ ] **Step 3: Implement current-only read and route rendering**

Define a compact item with assessment ID, score, qualified band, confidence, and shortlist decision. After authority revalidation, query only rows whose persisted fence fields exactly equal the current snapshot, whose state is `stable` or `adjudicated`, and whose associated decision is eligible. Order by score descending, confidence rank, creation time descending, then immutable ID; cap focused results at 20. The route passes only this view to the escaped template. On unavailable authority retain `current=False` and render no item metadata.

- [ ] **Step 4: Verify route and read behavior**

Run: `uv run pytest tests/integration/test_phase2_scoring_runtime.py tests/e2e/test_phase2_activation_flow.py -q && uv run ruff check src/job_search_cockpit/phase2/shortlist.py src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py && uv run mypy src`

Expected: PASS; anonymous access remains 401, redacted unavailable output contains no safe wording, and the local review page remains read-only.

- [ ] **Step 5: Commit**

Run: `git add src/job_search_cockpit/phase2/shortlist.py src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py src/job_search_cockpit/web/templates/phase2_assessments.html tests/integration/test_phase2_scoring_runtime.py tests/e2e/test_phase2_activation_flow.py && git commit -m "feat: read current local match shortlist"`

## Final verification

- [ ] Run `uv run ruff check src tests`.
- [ ] Run `uv run mypy src`.
- [ ] Run `uv run pytest -q`.
- [ ] Run `git diff --check`, `git status --short`, `git push origin Dev`, `git fetch origin Dev`, `git rev-parse HEAD`, and `git rev-parse origin/Dev`.
- [ ] Confirm the working tree is clean and both SHA values are identical.
