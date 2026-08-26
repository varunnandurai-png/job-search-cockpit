# Phase III Local Resume Finalisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one current, explicitly verified Phase II job with an immutable canonical requirement ledger into exactly one user-reviewed local PDF/DOCX resume pair, generated from one canonical document model only after exact finalisation confirmation.

**Architecture:** `LocalResumeFinalisationService` consumes job authority only through `VerifiedJobPreparationPort` and career evidence only through `Phase1MatchingPort`. It stores append-only attempt, event, and final-artifact metadata in the isolated Phase II catalog, rebuilds the canonical model in memory from canonical requirement IDs at every sensitive boundary, renders both formats into a private temporary directory, verifies readable equivalent content, revalidates bound state again, and then publishes one pair with cleanup on every failure. Current provider-discovery records have no requirement ledger, so the production path must deny them until an independently approved Phase II ledger producer exists; Phase III must not infer IDs from listing prose or implement the deferred scoring system.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, FastAPI, Jinja2, SQLite, SHA-256, `python-docx`, ReportLab, and pypdf. Varun approved the three local rendering dependencies on 2026-08-26.

## Global Constraints

- Do not implement or redesign Phase II scoring, shortlist, requirement extraction, or evidence mapping in this plan.
- Never read an existing or generic resume, Phase I persistence models, provider secrets, raw credentials, cookies, OTPs, or `.env` values.
- Obtain job readiness and all bound job/revision/authorization state only through `VerifiedJobPreparationPort`.
- Obtain career facts only through `Phase1MatchingPort.resume_fact_projection` and revalidate the exact projection before every sensitive transition.
- Send only canonical requirement IDs with purpose `tailored_resume` to Phase I; never send job prose or free-form instructions.
- Missing, stale, incomplete, sensitive, unsupported, duplicate, or unrequested evidence is a blocking gap.
- Store no resume body, safe wording, document bytes, draft files, or revision files in SQLite.
- Create no final file before the exact finalisation action; keep only the successful final PDF/DOCX pair.
- Revalidate authorization immediately before attempt creation, review return, finalisation, publication, metadata recording, and artifact access.
- Generate both formats from one frozen canonical model and require readable, normalized content equivalence before success.
- Use synthetic facts and temporary directories only in automated tests; do not contact providers or inspect real career facts.
- No provider search, browser automation, application submission, upload, sharing, Drive access, scheduler, retry loop, or background task may be added.
- Output directory: `Settings.data_dir / "final-resumes"`; approved for Phase III local-only storage.
- Filename: first final pair uses `Varun_Resume_<company_name>.docx` and `Varun_Resume_<company_name>.pdf`; a later role at the same company uses `<role_name>_Varun_Resume_<company_name>.<ext>`. Safely normalize public company and role names, and never overwrite an existing pair.
- Exact confirmation: `FINALISE RESUME FOR THIS VERIFIED JOB`.
- Document presentation: approved classic-executive design: navy header, restrained gold accent, professional headshot, formal hierarchy, and tables only where they improve scanning. Follow `docs/superpowers/specs/2026-08-26-phase-3-resume-presentation-design.md`. No new factual profile fields, manual wording, cover letter, or template picker is added.
- Rendering dependencies: `python-docx>=1.2,<2` (MIT), `reportlab>=4.4,<5` (BSD), and `pypdf>=6.10,<7` (BSD-3-Clause). All are pure Python wheels; ReportLab may install Pillow as a transitive dependency. LibreOffice and Poppler from the bundled workspace runtime are QA tools, not application runtime dependencies.
- Commit and push every accepted task as one logical increment on `Dev`; after each push compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/Dev`.

## Reconciliation Findings and Execution Gates

1. Local `Dev` and `origin/Dev` both start at `660630b894ccac00e24b12a46c178b842b3d5eb3`; the working tree was clean before this plan.
2. The baseline suite passes outside the restricted sandbox: `186 passed, 1 existing Starlette/httpx deprecation warning`.
3. Main Alembic head is `0002_phase1_contract`; Phase II head is `0006_provider_discovery`.
4. No PDF or DOCX runtime renderer is declared in `pyproject.toml` or `uv.lock`.
5. The bundled QA runtime contains `python-docx 1.2.0`, `reportlab 4.4.9`, `pypdf 6.10.0`, `pdfplumber 0.11.9`, LibreOffice/`soffice`, Poppler `pdftoppm`, and `pdfinfo`.
6. The approved Phase III design assumes an existing per-job canonical requirement ledger. Current Phase II discovery stores listing prose but no atomic requirement IDs, coverage ledger, or ledger fingerprint. Phase III therefore consumes a ledger when available and denies its absence. Producing that ledger remains part of the deferred broader Phase II assessment system and is not added here.
7. Explicit user approval is required before Task 1 because it changes rendering dependencies. The local output directory and visual presentation are approved; Google Drive remains future scope.
8. Real-user acceptance remains blocked after automated implementation/QA until a separately approved Phase II requirement-ledger producer exists and a fresh candidate is verified. This does not block synthetic implementation or document QA.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Approved runtime renderer and parser dependencies only. |
| `src/job_search_cockpit/phase2/resume_documents.py` | Frozen review/command/artifact/canonical-model types, confirmation constant, canonical text, filenames, and renderer/parser protocols. |
| `src/job_search_cockpit/phase2/finalisation.py` | `LocalResumeFinalisationService`, fail-closed validation order, revalidation, publication, replay denial, and cleanup orchestration. |
| `src/job_search_cockpit/phase2/document_rendering.py` | Deterministic DOCX and PDF generation plus readable-content extraction/equivalence checks. |
| `src/job_search_cockpit/phase2/models.py` | New append-only document-attempt, event, requirement-ledger reference, and final-artifact ORM metadata. |
| `alembic_phase2/versions/0007_resume_finalisation.py` | New immutable Phase III tables and SQLite update/delete rejection triggers. |
| `src/job_search_cockpit/phase2/resume_safety.py` | Extend verified authorization with an optional canonical requirement-ledger binding; absence denies Phase III only. |
| `src/job_search_cockpit/phase2/verification.py` | Catalog adapter loads and revalidates the ledger binding when it exists and fails closed when it does not. |
| `src/job_search_cockpit/phase2/config.py` | Approved final output directory property only. |
| `src/job_search_cockpit/phase2/runtime.py` | Construct and expose the finalisation service with production ports, stores, renderer, and output path. |
| `src/job_search_cockpit/web/routes/phase2.py` | Authenticated review start/view, exact finalisation POST, and artifact metadata view; no external actions. |
| `src/job_search_cockpit/web/templates/phase2_local_review.html` | Current candidate metadata, supported requirements/gaps, exact confirmation, and final local paths/fingerprints. |
| `tests/support/phase3.py` | Synthetic authorization, canonical ledger, projection, renderer, and temporary-output builders. |
| `tests/unit/test_resume_documents.py` | Canonical-model determinism, confirmation, generic-resume, gap, renderer failure, and content mismatch tests. |
| `tests/unit/test_finalisation.py` | Service sequencing, drift, replay, cleanup, and artifact-access unit tests. |
| `tests/integration/test_phase3_database.py` | Migration head, append-only triggers, prohibited columns, and no-body metadata tests. |
| `tests/integration/test_phase3_finalisation_runtime.py` | Real SQLite + synthetic ports + temporary renderer integration tests. |
| `tests/integration/test_phase3_routes.py` | Local-session authentication, origin/CSRF, route scope, and no-provider/no-submit assertions. |
| `tests/document/test_phase3_rendering.py` | Synthetic DOCX/PDF generation, extraction equality, temp cleanup, and render fixtures for visual QA. |

## Task 1: Approve and Lock the Minimum Renderer Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/unit/test_resume_documents.py`

**Interfaces:**
- Consumes: explicit user approval for `python-docx`, ReportLab, and pypdf.
- Produces: importable `docx`, `reportlab`, and `pypdf` runtime packages at locked compatible versions.

- [x] **Step 1: Record the explicit dependency decision in the task commentary**

Require an unambiguous approval of all three proposed packages before editing dependency files. If any package is declined, stop and revise this plan; do not substitute LibreOffice, WeasyPrint, Pandoc, or a handwritten OOXML/PDF implementation without a new decision.

- [x] **Step 2: Write the failing runtime-availability test**

```python
from importlib.util import find_spec


def test_approved_resume_rendering_dependencies_are_runtime_available() -> None:
    assert find_spec("docx") is not None
    assert find_spec("reportlab") is not None
    assert find_spec("pypdf") is not None
```

- [x] **Step 3: Run the test and confirm the expected failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_resume_documents.py::test_approved_resume_rendering_dependencies_are_runtime_available -q`

Expected: FAIL before the packages are added to the project environment.

- [x] **Step 4: Add only the approved dependencies**

Add these bounds to `[project].dependencies` and regenerate the lock:

```toml
"python-docx>=1.2,<2",
"reportlab>=4.4,<5",
"pypdf>=6.10,<7",
```

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv lock`

- [x] **Step 5: Verify the dependency increment**

Run:

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv lock --check
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_resume_documents.py -q
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check tests/unit/test_resume_documents.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit, push, and compare refs**

```bash
git add pyproject.toml uv.lock tests/unit/test_resume_documents.py
git commit -m "chore: add local resume rendering dependencies"
git push origin Dev
git rev-parse HEAD
git ls-remote origin refs/heads/Dev
```

Expected: the two commit hashes match.

## Task 2: Define the Canonical Document and Fail-Closed Requirement-Ledger Binding

**Files:**
- Create: `src/job_search_cockpit/phase2/resume_documents.py`
- Modify: `src/job_search_cockpit/phase2/resume_safety.py`
- Modify: `src/job_search_cockpit/phase2/verification.py`
- Create: `tests/support/phase3.py`
- Modify: `tests/unit/test_finalisation.py`
- Modify: `tests/unit/test_resume_safety.py`
- Modify: `tests/unit/test_phase2_verification.py`

**Interfaces:**
- Consumes: `VerifiedJobPreparationAuthorization`, `Phase1ResumeFactProjection`, `RequirementLedger`, and canonical requirement IDs.
- Produces: `ResumeDocumentReview`, `FinaliseResumeCommand`, `FinalisedResumeArtifacts`, `CanonicalResumeDocument`, `ResumeRenderer`, and authorization fields `requirement_ids` plus `requirement_ledger_fingerprint`.

- [ ] **Step 1: Write failing tests for canonical models and missing ledgers**

```python
def test_phase3_denies_an_authorization_without_a_canonical_requirement_ledger() -> None:
    authorization = synthetic_authorization(requirement_ids=(), requirement_ledger_fingerprint="")
    with pytest.raises(FinalisationError, match="requirement ledger is unavailable"):
        validate_phase3_authorization(authorization)


def test_canonical_model_is_deterministic_and_contains_only_approved_wording() -> None:
    projection = synthetic_projection(("skills.python",))
    first = build_canonical_resume_document(projection)
    second = build_canonical_resume_document(projection)
    assert first == second
    assert first.content_fingerprint == second.content_fingerprint
    assert first.plain_text == "Tailored Resume\n\nApproved experience\n\nBuilt safe systems."
```

- [ ] **Step 2: Run the focused tests and confirm the expected failures**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_finalisation.py tests/unit/test_resume_safety.py tests/unit/test_phase2_verification.py -q`

Expected: FAIL because the Phase III types and ledger binding do not exist.

- [ ] **Step 3: Add frozen public types and exact constants**

Define these minimum interfaces in `resume_documents.py`:

```python
FINALISATION_CONFIRMATION = "FINALISE RESUME FOR THIS VERIFIED JOB"

@dataclass(frozen=True, slots=True)
class CanonicalResumeEntry:
    requirement_id: str
    safe_wording: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    employer_key: str | None
    period_start: str | None
    period_end: str | None

@dataclass(frozen=True, slots=True)
class CanonicalResumeDocument:
    title: str
    section_title: str
    entries: tuple[CanonicalResumeEntry, ...]
    plain_text: str
    content_fingerprint: str

@dataclass(frozen=True, slots=True)
class ResumeDocumentReview:
    attempt_id: str
    job_id: str
    job_revision_id: str
    authorization_id: str
    requirements: RequirementLedger
    document: CanonicalResumeDocument
    exact_confirmation: str

@dataclass(frozen=True, slots=True)
class FinaliseResumeCommand:
    attempt_id: str
    confirmation: str

@dataclass(frozen=True, slots=True)
class FinalisedResumeArtifacts:
    attempt_id: str
    job_id: str
    job_revision_id: str
    content_fingerprint: str
    docx_path: Path
    docx_sha256: str
    docx_byte_length: int
    pdf_path: Path
    pdf_sha256: str
    pdf_byte_length: int
```

Define `ResumeRenderer.render(document, output_dir, stem) -> RenderedResumeFiles` as a protocol. Reject blank or duplicate IDs, empty safe wording, missing support IDs, unsupported gaps, and non-canonical IDs before creating a document. Order entries by the immutable `projection.requirement_ids`; never sort or rewrite safe wording semantically.

- [ ] **Step 4: Bind the verified authorization to canonical requirements**

Add `requirement_ids: tuple[str, ...] = ()` and `requirement_ledger_fingerprint: str = ""` to `VerifiedJobPreparationAuthorization`. Validation requires 1–32 canonical unique IDs and a 64-character fingerprint for Phase III. `CatalogVerifiedJobPreparationPort` must load these only from an immutable Phase II ledger source; because none exists at this baseline, its production result for existing candidates remains denied for Phase III. Do not parse `Phase2JobRevision.public_description` and do not add a browser form for requirement IDs.

- [ ] **Step 5: Run focused tests and static checks**

Run:

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_finalisation.py tests/unit/test_resume_safety.py tests/unit/test_phase2_verification.py -q
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src/job_search_cockpit/phase2/resume_documents.py src/job_search_cockpit/phase2/resume_safety.py src/job_search_cockpit/phase2/verification.py tests/support/phase3.py tests/unit/test_finalisation.py tests/unit/test_resume_safety.py tests/unit/test_phase2_verification.py
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: define immutable resume document contract`

## Task 3: Add Immutable Attempt and Final-Artifact Metadata

**Files:**
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/0007_resume_finalisation.py`
- Create: `tests/integration/test_phase3_database.py`

**Interfaces:**
- Consumes: the Phase II `0006_provider_discovery` migration head and Task 2 identifiers/fingerprints.
- Produces: `Phase2ResumeDocumentAttempt`, `Phase2ResumeDocumentAttemptEvent`, `Phase2ResumeRequirementLedger`, and `Phase2FinalResumeArtifact` tables with append-only stores.

- [ ] **Step 1: Write failing migration tests**

Assert the four tables exist, Phase II head is `0007_resume_finalisation`, every table rejects UPDATE and DELETE, `phase2_final_resume_artifacts.attempt_id` is unique, and no column name contains any of:

```python
PROHIBITED = {
    "body", "wording", "content", "draft", "revision_file", "bytes",
    "token", "secret", "password", "cookie", "otp", "submission", "drive",
}
```

- [ ] **Step 2: Run the focused migration test and confirm failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase3_database.py -q`

Expected: FAIL because migration `0007_resume_finalisation` does not exist.

- [ ] **Step 3: Add metadata-only tables**

`phase2_resume_requirement_ledgers` stores: opaque ID, job ID, job revision ID, ordered canonical requirement IDs as JSON, requirement-ledger fingerprint, source kind constrained to `phase2_assessment`, Phase II activation/restore generations, and created time. No Phase III code creates these rows; it only consumes them when a separately approved Phase II assessment producer exists.

`phase2_resume_document_attempts` stores: opaque ID, job/revision IDs, ledger ID/fingerprint, ordered canonical requirement IDs, authorization ID/nonce/expiry, projection fingerprint, canonical-model fingerprint, every Phase I profile/readiness/authority/restore binding, Phase II activation/restore bindings, and created time.

`phase2_resume_document_attempt_events` stores: opaque ID, attempt ID, kind constrained to `finalisation_failed`, bounded reason code, and created time. It stores no exception string or document text.

`phase2_final_resume_artifacts` stores: opaque ID, unique attempt ID, job/revision IDs, projection/content fingerprints, relative DOCX/PDF paths, SHA-256 values, byte lengths, and created time.

Create `BEFORE UPDATE` and `BEFORE DELETE` rejection triggers for all four tables. Downgrade remains intentionally irreversible, matching existing Phase II audit tables.

- [ ] **Step 4: Run migration and schema verification**

Run:

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase3_database.py tests/integration/test_phase2_database.py -q
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run alembic -c alembic_phase2.ini heads
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0007_resume_finalisation.py tests/integration/test_phase3_database.py
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src
git diff --check
```

Expected: focused tests pass and Phase II reports exactly one head, `0007_resume_finalisation`.

- [ ] **Step 5: Commit, push, and compare refs**

Commit message: `feat: add immutable resume finalisation metadata`

## Task 4: Implement Start Review and Bound-State Revalidation

**Files:**
- Modify: `src/job_search_cockpit/phase2/finalisation.py`
- Create: `tests/integration/test_phase3_finalisation_runtime.py`
- Modify: `tests/unit/test_finalisation.py`

**Interfaces:**
- Consumes: Task 2 types, `VerifiedJobPreparationPort`, `Phase1MatchingPort`, and Task 3 stores.
- Produces: `LocalResumeFinalisationService.start_review(job_id: str) -> ResumeDocumentReview` and durable attempt lookup/reconstruction.

- [ ] **Step 1: Write failing start-review tests**

Cover absent authorization, expired authorization, wrong job, wrong revision, replayed/cross-job authorization, changed Phase I generation, changed Phase II generation, absent ledger, stale/incomplete projection, missing supporting evidence, generic resume input rejection through the existing safety boundary, and no artifact before finalisation.

The happy-path test must assert this call order:

```python
assert calls == [
    "authorization_for_resume",
    "revalidate_authorization_before_attempt",
    "resume_fact_projection",
    "revalidate_projection_before_attempt",
    "revalidate_authorization_before_record",
    "record_attempt",
    "revalidate_authorization_before_review",
    "revalidate_projection_before_review",
]
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_finalisation.py tests/integration/test_phase3_finalisation_runtime.py -q`

- [ ] **Step 3: Implement the minimum service**

`start_review` must:

1. obtain the current authorization for the exact `job_id`;
2. validate expiry, job/revision/nonce/generation/ledger bindings;
3. immediately revalidate the authorization;
4. request `Phase1ResumeFactProjectionRequest(requirement_ids=authorization.requirement_ids)`;
5. require projection bindings to equal the authorization’s Phase I bindings;
6. build the requirement ledger and reject every gap;
7. revalidate projection and authorization again;
8. build the canonical model in memory;
9. append one attempt inside the mutation coordinator, rejecting reused authorization nonce/ID;
10. revalidate authorization and projection before returning the review.

No output directory is created and no renderer is invoked in this method.

- [ ] **Step 4: Verify the start-review milestone**

Run focused unit/integration tests, Ruff on touched files, `uv run mypy src`, the non-E2E integration suite, and `git diff --check`.

- [ ] **Step 5: Commit, push, and compare refs**

Commit message: `feat: add fail-closed resume review attempts`

## Task 5: Render and Verify One Canonical PDF/DOCX Pair

**Files:**
- Create: `src/job_search_cockpit/phase2/document_rendering.py`
- Modify: `src/job_search_cockpit/phase2/config.py`
- Create: `tests/document/test_phase3_rendering.py`
- Modify: `tests/unit/test_resume_documents.py`

**Interfaces:**
- Consumes: approved template/output directory, `CanonicalResumeDocument`, python-docx, ReportLab, and pypdf.
- Produces: `LocalResumeRenderer.render(...)`, `extract_docx_text`, `extract_pdf_text`, and `verify_content_equivalence`.

- [ ] **Step 1: Write failing renderer tests**

Use `tmp_path` and synthetic entries only. Assert both files are readable, normalized extracted text equals `document.plain_text`, the canonical content fingerprint is identical for both, temporary directories are empty after success/failure, filenames are opaque, and a deliberately mismatched renderer raises `FinalisationError("Rendered resume content does not match.")`.

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/document/test_phase3_rendering.py tests/unit/test_resume_documents.py -q`

- [ ] **Step 3: Implement the approved classic-executive renderers**

Apply one explicit token map in both formats: US Letter, 0.7-inch margins, navy header, restrained gold accent rule, accessible black body text, 18-point title, 11-point section heading, 10.5-point body, and 1.15 line spacing. Use the user-supplied professional headshot only at real finalisation; tests use a synthetic placeholder and retain neither image nor image metadata. DOCX uses real paragraph styles, real bullet numbering, and explicit table geometry where a skills/qualifications table improves scanning. PDF uses matching ReportLab Platypus elements. Neither renderer mutates or reorders the canonical model.

- [ ] **Step 4: Implement structural and equivalence verification**

Reopen DOCX with python-docx and PDF with pypdf. Reject missing pages/paragraphs, empty files, parse errors, encrypted PDFs, unexpected canonical text, or different normalized line sequences. Hash bytes with SHA-256 only after both pass.

- [ ] **Step 5: Run bundled visual QA on the synthetic pair**

Before the first authoring command, run the document/PDF skills’ artifact-operation markers using the bundled Node runtime. Render the DOCX with the bundled `render_docx.py`; render the PDF with bundled Poppler; open every PNG at 100% and confirm no clipping, overlap, missing glyphs, broken bullets, or inconsistent page breaks. Save only synthetic QA evidence under a temporary directory and remove it after review.

- [ ] **Step 6: Verify, commit, push, and compare refs**

Run document tests, focused unit tests, Ruff, mypy, `git diff --check`, then commit as `feat: render equivalent local resume artifacts`.

## Task 6: Finalise Once, Publish Atomically, and Revalidate Artifact Access

**Files:**
- Modify: `src/job_search_cockpit/phase2/finalisation.py`
- Modify: `tests/unit/test_finalisation.py`
- Modify: `tests/integration/test_phase3_finalisation_runtime.py`

**Interfaces:**
- Consumes: Task 4 durable attempt reconstruction and Task 5 verified temporary files.
- Produces: `finalise(command) -> FinalisedResumeArtifacts` and `artifacts_for(attempt_id) -> FinalisedResumeArtifacts`.

- [ ] **Step 1: Write failing finalisation and access tests**

Cover incorrect confirmation, unknown attempt, wrong/replayed authorization, wrong job/revision, projection or generation drift, repeated finalisation, renderer failure, extraction mismatch, revalidation failure after render, metadata failure, output collision, temp cleanup, published-file cleanup on failure, successful single pair, and artifact access denial after bound-state drift.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_finalisation.py tests/integration/test_phase3_finalisation_runtime.py -q`

- [ ] **Step 3: Implement exact finalisation sequencing**

`finalise` must validate exact confirmation before filesystem work; reconstruct and revalidate authorization/projection; rebuild and fingerprint the canonical model; deny an existing final row; render inside `TemporaryDirectory(dir=output_parent)`; verify both files; revalidate authorization and projection again; create the approved output directory with owner-only permissions; publish both with exclusive names; revalidate once more; append final metadata; and remove both published files if any post-publication operation fails. Append only a bounded failure reason event, never exception text.

- [ ] **Step 4: Implement revalidated artifact access**

`artifacts_for` loads immutable metadata, reconstructs the bound authorization/projection, revalidates both, confirms both paths remain below the approved output directory, rehashes both files, and returns paths only when hashes, byte lengths, and content fingerprint still match.

- [ ] **Step 5: Verify, commit, push, and compare refs**

Run focused tests, all Phase II integration tests, Ruff, mypy, and `git diff --check`; commit as `feat: finalise one verified local resume pair`.

## Task 7: Wire the Authenticated, CSRF-Protected Local Review Flow

**Files:**
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_local_review.html`
- Create: `tests/integration/test_phase3_routes.py`

**Interfaces:**
- Consumes: `LocalResumeFinalisationService` from Tasks 4–6 and existing launch-session middleware.
- Produces: local review/finalisation routes with no external action.

- [ ] **Step 1: Write failing route/security tests**

Test unauthenticated 401, foreign-origin 403, missing/invalid CSRF 403, GET review safety, exact-confirmation enforcement, safe error display, no file before POST, successful redirect after synthetic finalisation, and denial when ledger/readiness is unavailable. Patch service methods to assert that no request calls `DiscoveryService`, provider adapters, application draft submission, browser automation, uploads, Drive, or background tasks.

- [ ] **Step 2: Run route tests and confirm failure**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase3_routes.py -q`

- [ ] **Step 3: Add only three local actions**

- `POST /phase-2/resume-reviews` with CSRF and `job_id`, redirecting to the attempt view.
- `GET /phase-2/resume-reviews/{attempt_id}` returning revalidated supported requirements, gaps, canonical content, and final status.
- `POST /phase-2/resume-reviews/{attempt_id}/finalise` with CSRF and exact confirmation, redirecting to the revalidated artifact view.

Do not add provider discovery, application, download, upload, sharing, or file-serving endpoints. Display local filesystem paths as text only after `artifacts_for` succeeds.

- [ ] **Step 4: Verify route and security scope**

Run route tests, existing Phase II page/security tests, Ruff, mypy, and a route inventory assertion that no Phase III route contains `submit`, `provider`, `discover`, `upload`, `share`, `drive`, `schedule`, or `retry`.

- [ ] **Step 5: Commit, push, and compare refs**

Commit message: `feat: add local resume finalisation review flow`

## Task 8: Complete Automated QA and Synthetic Visual Acceptance

**Files:**
- Modify only files needed to correct defects found by verification.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: implementation-complete and QA-complete evidence, distinct from real-user acceptance.

- [ ] **Step 1: Run focused Phase III verification**

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_resume_documents.py tests/unit/test_finalisation.py tests/integration/test_phase3_database.py tests/integration/test_phase3_finalisation_runtime.py tests/integration/test_phase3_routes.py tests/document/test_phase3_rendering.py -q
```

- [ ] **Step 2: Run migration, route, and safety regression suites**

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase2_database.py tests/integration/test_phase2_resume_runtime.py tests/integration/test_phase2_activation_page.py tests/integration/test_web_security.py -q
```

- [ ] **Step 3: Prove import and route boundaries statically**

Use an AST test to reject imports from `job_search_cockpit.storage.models` or other Phase I persistence modules anywhere under `phase2/`. Inventory FastAPI routes and assert Phase III exposes only the three approved local review actions.

- [ ] **Step 4: Run repository-wide verification**

```bash
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest -q
git diff --check
git status --short
```

Run the full suite outside the restricted sandbox when browser launch or loopback binding is denied by sandbox policy.

- [ ] **Step 5: Repeat visual QA on the final synthetic renderer output**

Render every DOCX and PDF page to PNG with the bundled runtime, inspect every page, verify extracted-content equality and fingerprints, and remove all synthetic outputs/intermediates afterward.

- [ ] **Step 6: Commit any verification-only corrections, push, and compare refs**

Use a narrowly scoped commit message describing the corrected defect. If no correction is needed, create no empty commit. Confirm clean worktree and matching local/remote `Dev` hashes.

## Task 9: Real-User Acceptance Gate (Blocked Until a Phase II Ledger Exists)

**Files:**
- No source changes unless a verified defect is found.

**Interfaces:**
- Consumes: one persisted real candidate with an approved immutable requirement ledger, fresh Phase II verification, and exact user confirmation.
- Produces: one real local PDF/DOCX pair and acceptance evidence; performs no upload or submission.

- [ ] **Step 1: Show safe candidate metadata only**

Display candidate/job ID, job revision ID, provider name, title, employer, locations, canonical public URL, observation/revision timestamps, and current verification state. Do not display raw provider payloads or secrets.

- [ ] **Step 2: Obtain a fresh explicit Phase II verification**

Require `VERIFY JOB FOR PHASE II PREPARATION`, record the user actor/reason through the existing verification service, and immediately revalidate its 15-minute authorization. Never reuse the expired Vanguard authorization.

- [ ] **Step 3: Show the complete review**

Call `start_review`, display every supported canonical requirement with exact approved Phase I wording and support identifiers, display every gap, and stop if any gap or state drift exists.

- [ ] **Step 4: Obtain exact Phase III confirmation**

Require the user to type `FINALISE RESUME FOR THIS VERIFIED JOB` for the exact attempt.

- [ ] **Step 5: Finalise and visually verify the real pair**

Create exactly one pair, render every PDF/DOCX page to images with the bundled skills, inspect them at 100%, verify content equality and fingerprints, and do not upload or share either file.

- [ ] **Step 6: Report acceptance evidence**

Report local paths, byte lengths, SHA-256 hashes, canonical content fingerprint, authorization/attempt IDs, visual-QA result, clean temporary state, and matching local/remote commit. Mark real-user acceptance complete only after the user reviews the final pair.

## Plan Self-Review

- **Spec coverage:** Tasks 2–7 cover the three required service methods, all revalidation boundaries, canonical IDs, evidence gaps, immutable metadata, SQLite triggers, no body persistence, finalisation-only files, one canonical model, equivalence, cleanup, replay denial, authenticated/CSRF routes, and external-action exclusions. Task 8 covers all required verification commands and visual QA. Task 9 preserves the real gate.
- **Known design/code gap:** Current Phase II has no canonical requirement-ledger producer. The plan consumes but does not fabricate this authority, so implementation and synthetic QA can complete while real-user acceptance remains blocked. This matches the instruction not to claim broader Phase II scoring/shortlist completion.
- **Dependency/install impact:** The proposed application dependencies are three permissively licensed Python packages; the heavier LibreOffice and Poppler binaries remain bundled QA tools. No network service or external document processor is introduced.
- **Retention:** Only one successful final pair plus metadata remains. Attempts/failure events are append-only metadata; all temporary render files are removed.
- **Placeholder scan:** The plan contains no TBD/TODO steps. Any change to renderer packages, output directory, template, ledger production, fields, or retention requires a new explicit decision.
- **Type consistency:** `ResumeDocumentReview`, `FinaliseResumeCommand`, `FinalisedResumeArtifacts`, and `CanonicalResumeDocument` names and signatures are used consistently across service, runtime, routes, and tests.
