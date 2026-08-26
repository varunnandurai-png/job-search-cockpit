# Phase III local tailored-résumé finalisation design

## Objective

Phase III turns one explicitly selected, currently verified Phase II job into
one local, tailored résumé artefact pair only after a user reviews it and
explicitly finalises it. It exists to make the already-approved Phase I facts
and Phase II verification boundary useful without granting any application,
provider, browser, upload, sharing, or Google Drive capability.

Success means a current verified job can produce exactly one user-approved PDF
and DOCX pair whose content comes from the same immutable local document model;
any unavailable, expired, changed, or incomplete input fails closed before a
file exists.

## Scope and boundaries

### Always

- Obtain job readiness only through `VerifiedJobPreparationPort` and
  revalidate it immediately before document-attempt creation, review,
  finalisation, and artefact access.
- Obtain career facts only through `Phase1MatchingPort.resume_fact_projection`
  and revalidate the exact projection before every sensitive transition.
- Use canonical requirement IDs only. The request purpose remains
  `tailored_resume`; Phase III neither sends job prose to Phase I nor accesses
  Phase I tables.
- Require every requested requirement to have approved, current, non-sensitive
  supporting evidence. A missing or invalidated fact is a gap and blocks
  finalisation.
- Retain final artefact metadata and the immutable fingerprints needed for
  audit. Retain no draft or revision files.
- Render-verify the generated PDF and DOCX before marking finalisation
  successful, and ensure both derive from the exact same document model.

### Ask first

- Adding or changing document-rendering dependencies.
- Changing the final output directory or retention model.
- Adding any new document type, template, profile field, or a manual wording
  workflow beyond the existing Phase I review port.

### Never

- Read an existing résumé; use generic résumé content; invent, strengthen, or
  reuse career claims; or bypass Phase I acceptance.
- Treat a provider listing, prior verification, or a Phase II preparation
  attempt as a current finalisation authorization.
- Submit an application, sign in to a provider, automate a browser, upload or
  share a file, invoke Google Drive, schedule work, retry in the background,
  or expose credentials, tokens, `.env` values, raw secrets, or raw provider
  payloads.
- Read Phase I tables from Phase II or Phase III code.

## Architecture

Phase III adds a small local finalisation service behind the existing Phase II
runtime. It consumes existing contracts rather than changing their authority:

1. The user starts a tailored-resume review for a job ID. The service requests
   and revalidates a `VerifiedJobPreparationAuthorization`; expired (including
   the previously issued 15-minute authorization), replayed, cross-job, or
   changed authorizations are unavailable.
2. The service derives the canonical requirement IDs from the bound job
   revision's existing local requirement ledger and requests a
   `Phase1ResumeFactProjection`. It validates the resulting ledger and binds a
   new append-only document attempt to the job/revision, authorization,
   projection, Phase I generations, and Phase II activation/restore
   generations.
3. A local authenticated review route displays only the derived résumé content,
   supported requirements, blocking gaps, and status. It displays no provider
   credentials or raw source payloads and makes no external request.
4. The user sends an exact finalisation confirmation with the document-attempt
   ID. The service revalidates every binding, constructs one canonical document
   model from approved safe wording, and writes one PDF and DOCX pair from that
   model. It verifies the files are present, readable, and content-equivalent
   before appending immutable final-artifact metadata.
5. Any failed revalidation or render verification leaves no final artefact
   metadata and no published file. A new attempt requires a new current job
   verification and explicit confirmation.

The user-facing confirmation text, output filename format, and renderer choice
will be fixed in the implementation plan after an explicit dependency review;
they are not inputs accepted from a provider or browser.

## Data model and retention

Add append-only Phase III document-attempt and final-artifact records to the
isolated Phase II catalog. Records contain opaque identifiers, job/revision and
authorization IDs, fingerprints, bounded lifecycle state, timestamps, output
filenames, byte lengths, and cryptographic file/content fingerprints. They do
not contain document body text, Phase I source content, credential material,
cookies, submission state, or Drive metadata.

The only persistent files are a completed final PDF/DOCX pair. Intermediate
render files live in a private temporary directory and are removed on both
success and failure. A failed or incomplete attempt has audit metadata only.

## Interface sketch

`LocalResumeFinalisationService` will expose:

- `start_review(job_id: str) -> ResumeDocumentReview`: creates a durable,
  revalidated attempt and returns a safe local projection.
- `finalise(command: FinaliseResumeCommand) -> FinalisedResumeArtifacts`:
  accepts an attempt ID and exact confirmation, revalidates all bindings, and
  creates/verifies the final artefact pair once.
- `artifacts_for(attempt_id: str) -> FinalisedResumeArtifacts`: revalidates
  bound state before exposing local file metadata or paths.

The service is fail-closed. No public route may manufacture an authorization,
fact projection, document attempt, approval, or external action.

## Commands and project structure

Implementation will use the repository's existing commands:

```bash
uv run pytest tests/unit/test_finalisation.py -q
uv run pytest tests/integration/test_phase2_resume_runtime.py -q
uv run ruff check src tests
uv run mypy src
uv run pytest -q
git diff --check
```

Likely responsibilities are deliberately narrow:

- `src/job_search_cockpit/phase2/finalisation.py` — document attempt,
  revalidation, canonical model, and finalisation service.
- `src/job_search_cockpit/phase2/models.py` and a new Phase II migration —
  append-only metadata and SQLite immutability triggers.
- `src/job_search_cockpit/web/routes/phase2.py` and local templates —
  authenticated review and explicit finalisation action only.
- `tests/unit/` — pure validation, content-model, and renderer tests.
- `tests/integration/` — migration, authorization/projection drift, route
  safety, retention, and local artefact verification.

## Testing strategy

Test-first behavior must prove that finalisation denies: unavailable or expired
authorization; wrong/reused job binding; changed Phase I/II generations;
missing evidence; generic résumé selection; incorrect confirmation; replayed
attempt; renderer failure; and failed PDF/DOCX equivalence.

Tests must also prove that no artefact exists before explicit finalisation,
successful artefacts use one canonical model, temporary drafts are removed,
metadata has no secret-like columns, the routes have no provider search or
application submission action, and Phase III imports no Phase I persistence
models. Synthetic test facts and temporary directories are permitted; no live
provider call or real listing is needed for automated coverage.

Before any real finalisation, the user must explicitly re-verify a current
candidate. The prior authorization is not reusable and must never be treated as
evidence of approval.

## Acceptance criteria

1. A real finalisation requires a fresh explicit job verification and exact
   finalisation confirmation.
2. No file is created before finalisation, and no draft/revision file survives.
3. Each final PDF/DOCX pair is derived from the same approved canonical content
   and passes render/readability verification.
4. Every input is revalidated at each sensitive boundary; any drift fails
   closed with no final artefact.
5. The implementation performs no external, browser, provider, application,
   Drive, upload, sharing, or background action.
6. Focused tests, Ruff, mypy, whitespace validation, and the complete test
   suite pass before each commit; every commit is pushed to `Dev` and its live
   remote ref matches the local commit.
