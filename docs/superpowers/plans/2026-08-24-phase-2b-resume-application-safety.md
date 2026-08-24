# Phase II-B Résumé and Application Safety Implementation Plan

**Goal:** Build the local, fail-closed safety boundaries that later allow a
verified eligible job to use only approved Phase I facts for a tailored résumé
and a user-reviewed, never-submitted application draft.

**Architecture:** Phase I remains the sole owner of factual acceptance,
support, sensitivity, and revisions. Phase II-B adds a separate, append-only
preparation workflow in the isolated Phase II catalog. It accepts only a
short-lived, purpose-bound verified-job authorization through an internal
port; no route, browser action, or caller may manufacture that authorization.
The current Phase II-A activation path remains setup-only throughout these
stages.

## Global constraints

- Use only approved, current, supported, non-confidential, correctly
  attributed Phase I facts through typed internal contracts; never query Phase
  I tables from Phase II.
- The active locked Phase I search-profile snapshot remains the only authority
  for eligibility. A failed or unknown mandatory condition denies preparation.
- Do not read existing résumé files. A generic résumé stops the flow.
- Do not implement provider access, job discovery, scoring, browser automation,
  credentials, submission, or Google Drive in this plan.
- No résumé files are created until the user explicitly selects **Finalise
  résumé for this job**. Final PDF/DOCX generation and Drive backup are later,
  separately reviewed stages.
- All tests use synthetic Phase I and job fixtures in temporary directories.

## Stages

### Stage 1 — Verified preparation authorization and fail-closed workflow state

**Scope:** Add a Phase II-B `ResumePreparationService` with an internal
`VerifiedJobPreparationPort`. The port returns a short-lived, opaque,
purpose-bound authorization only for an eligible job revision whose mandatory
rules are all known and passing. The service persists append-only preparation
attempt metadata in the Phase II catalog and invalidates an attempt whenever
the authorization, active profile, Phase I snapshot, job revision, or Phase II
activation generation changes.

**Acceptance criteria:**

- No public route can create an authorization or preparation attempt.
- Failed eligibility, unknown mandatory eligibility, expired authorization, a
  generic-résumé request, and any Phase I revalidation failure stop before a
  draft exists.
- The service exposes an explainable decision with coded denial reasons; it
  stores no career wording, job description, credential, or existing-resume
  path.
- Focused tests first demonstrate each denial, then confirm a synthetic,
  verified eligible authorization may create an in-memory/local draft state.

**Likely files:** new `src/job_search_cockpit/phase2/resume_safety.py`,
`src/job_search_cockpit/phase2/resume_types.py`, a narrowly extended
`src/job_search_cockpit/ports.py`, a Phase II Alembic migration, and focused
unit/integration tests. No browser route is included.

### Checkpoint 1

- Run the focused Stage 1 tests, Ruff, and mypy.
- Re-read the Phase I contract boundary and verify Phase II imports no Phase I
  storage model or session.
- Run the full suite before moving to human-visible work.

### Stage 2 — Approved-fact projection, requirement gap review, and manual-content handoff

**Scope:** Extend the internal contract—not table access—to obtain one
purpose-minimized fact projection for the authorized job. Build a local,
explainable requirement ledger that separates supported requirements from
unsupported gaps. Add a Phase I review-intake contract for new answers and
manual wording edits; neither becomes usable until Phase I returns a fresh
accepted projection.

**Acceptance criteria:**

- Unsupported requirements pause the attempt and name the gap without claiming
  the user lacks the capability.
- Unresolved, rejected, stale, unsupported, superseded, confidential, or
  wrongly attributed facts never enter the projection.
- A manual edit or missing answer only creates a Phase I review request; it
  cannot alter the draft or be reused until accepted and re-projected.
- Tests prove snapshot invalidation while drafting and no direct Phase I table
  access.

### Checkpoint 2

- Run focused contract, safety, and review-handoff tests, then full Ruff, mypy,
  and pytest checks.
- Review the bounded projection fields for accidental disclosure of contacts,
  credentials, source documents, or confidential facts.

### Stage 3 — Reusable-answer policy and no-submit application draft state

**Scope:** Add local metadata-only reusable-answer records and application
draft state. Reuse requires the same clearly labelled question, a current
accepted Phase I projection, and an age of at most 45 days. Sensitive voluntary
disclosure fields always remain blank and are neither stored nor reused.

**Acceptance criteria:**

- Exact-label matching, 45-day expiry, changed-answer review flags, and
  sensitive-field exclusion are enforced in the service layer.
- Application drafts expose a no-submit boundary and never persist passwords,
  one-time codes, cookies, or browser sessions.
- A confirmed user submission is not implemented in this stage; its future
  metadata-only history and sign-out path require the separately approved
  visible-browser integration stage.

### Checkpoint 3

- Run focused answer-policy and application-draft tests, then the complete
  quality suite.
- Verify the database and recovery ledger contain metadata and identifiers only
  for draft state, never credentials or sensitive disclosure values.

### Stage 4 — Tailored résumé review UI and finalisation-only artifact boundary

**Scope:** Add local review screens for supported requirements, gaps, pending
Phase I reviews, and an explicit **Finalise résumé for this job** control.
The finalisation service receives only an authorization-backed, accepted
tailored content projection and creates one PDF/DOCX pair with matching
content. It retains no draft/revision files.

**Acceptance criteria:**

- No file exists before explicit finalisation; generic résumé selection stops
  the flow.
- The UI remains local, keyboard accessible, and explains why a step is
  blocked.
- Final artefacts are verified as matching, local-only outputs. Google Drive is
  represented only as an explicit `not_implemented` status.

### Checkpoint 4

- Run focused document and browser tests, render-verify generated artefacts,
  then run Ruff, mypy, and the full test suite.
- Conduct a safety review of finalisation, retention, and no-submit boundaries.

### Stage 5 — Isolated Google Drive backup design and optional application-browser stage

**Status:** Explicitly deferred. These are separate plans and require a new
user approval before implementation. Drive may handle only the final,
user-approved PDF/DOCX pair after visible sign-in/consent; it may not access
other Drive content, share files, retry in the background, or upload drafts.
The application-browser stage must use visible local browser activity, stop for
CAPTCHAs or restrictions, never submit, and record metadata-only history only
after clear user-performed confirmation.

## Stage 1 risks and mitigations

| Risk | Mitigation |
|---|---|
| A caller fabricates eligibility | Require a narrow internal port and a short-lived authorization with complete generation revalidation. |
| Phase II bypasses Phase I ownership | Keep Phase I models/sessions out of the Phase II package; enforce with import and integration tests. |
| Generic-resume or early-file path slips in | Model these as explicit terminal denials and test that no artifact writer is reachable. |
| Existing Phase II-A safety regresses | Keep provider/discovery/scoring actions denied and run the existing activation acceptance tests at each milestone. |

## Plan self-review

- Covers the approved Phase II-B safeguards in dependency order while leaving
  job discovery, live sources, Drive, credentials, and submission out of scope.
- Starts with a meaningful but inert safety boundary because the current code
  has no verified job, scoring, or future-draft-readiness implementation.
- Preserves the Phase I snapshot-only contract and fails closed when required
  authority is unavailable or changes.
