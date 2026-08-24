# Phase II-B Local Completion Implementation Plan

**Goal:** Complete the local-only tailored-résumé and no-submit application-draft
workflow, while preserving the rule that no real preparation can begin until a
separately implemented discovery system issues verified job readiness.

**Architecture:** Phase I remains the sole owner of approved facts, manual
content review, sensitivity, support, and the locked search profile. Phase II
owns append-only preparation attempts, requirement ledgers, answer reuse,
application-draft metadata, and final local artefact state. Phase II accesses
Phase I only through purpose-minimized internal ports. A runtime adapter with
no verified job-readiness implementation denies all real preparation; synthetic
fixtures exercise the complete workflow without provider access.

## Global constraints

- Do not read Phase I tables from Phase II, or hard-code search-profile rules.
- Never allow a failed or unknown mandatory eligibility condition past the
  preparation boundary.
- Never read an existing résumé file; a generic résumé stops the flow.
- Never use unresolved, rejected, stale, unsupported, superseded,
  confidential, or wrongly attributed facts.
- Manual wording and missing answers enter Phase I review; they are unusable
  until explicitly accepted and freshly projected.
- Store voluntary sensitive disclosures nowhere; leave them blank.
- Do not implement providers, discovery, browser automation, credentials,
  submission, Google Drive, sharing, or background retries.

## Work package 1 — Complete the authorization and snapshot boundary

**Files:** `phase2/resume_safety.py`, `phase2/models.py`, a new Phase II
migration, `phase1_contract/matching_port.py`, `phase1_contract/service.py`,
`ports.py`, and focused unit/integration tests.

1. Expand the opaque preparation authorization to bind its job revision,
   selected location path, active profile fingerprint/generation, Phase I
   readiness and authority fingerprints/generations, Phase II activation and
   restore generations, expiry, and one-use nonce.
2. Revalidate every bound input immediately before a preparation attempt,
   fact-projection request, draft-state change, finalisation, and artefact
   read. Any mismatch appends an invalidation outcome and stops the workflow.
3. Keep the production adapter denied with a plain `verified job readiness is
   unavailable` result until a future discovery/readiness phase supplies this
   authorization. No UI or route may create a synthetic authorization.
4. Extend append-only Phase II preparation records with binding fingerprints
   and terminal invalidation events only; retain no career wording, job prose,
   answers, credentials, or document contents.

**Acceptance:** generic, expired, replayed, cross-job, profile-changed, Phase
I-changed, restored, or activation-changed authorizations cannot create or
reuse a preparation attempt. Tests prove the runtime adapter remains denied.

## Work package 2 — Purpose-minimized fact projection and Phase I review handoff

**Files:** `phase1_contract/`, Phase I fact-review service/model/migration,
new `phase2/requirements.py`, `phase2/resume_safety.py`, and contract tests.

1. Define a bounded requirement query and a frozen fact-projection response.
   The request carries canonical requirement IDs and purpose only—not job prose
   or free-form instructions. The response contains only eligible approved
   fact revisions, their safe wording, attribution when needed, support IDs,
   and exact snapshot fingerprints.
2. Add a local requirement ledger that lists supported requirements and
   unsupported gaps separately. A gap says `no approved evidence found`; it
   never asserts the user lacks a capability. Any required gap pauses drafting.
3. Add a Phase I manual-content review request for missing answers and local
   wording edits. Reject sensitive-disclosure categories before storage. An
   accepted review produces a new eligible Phase I projection; it never edits
   an existing draft in place.
4. Reject incomplete, capped, stale, or semantically unknown fact projections
   before display, draft creation, or finalisation.

**Acceptance:** every displayed support reference is an exact current Phase I
revision; direct table imports are prohibited by contract tests. A manual edit
or missing answer remains pending until Phase I acceptance and a fresh
projection.

## Work package 3 — Answer reuse and no-submit application-draft state

**Files:** `phase2/models.py`, a Phase II migration,
`phase2/application_drafts.py`, `phase2/resume_safety.py`, and unit/integration
tests.

1. Store an approved reusable answer only as local metadata bound to its exact
normalised question label, the accepted Phase I revision/projection, creation
time, expiry, and supersession chain.
2. Permit reuse only when the new question has the same clearly labelled
question fingerprint and the answer is at most 45 days old. Changed answers
mark existing drafts for review rather than rewriting them.
3. Model application drafts as local, append-only metadata. They may refer to
the exact final résumé version and approved answer IDs, but never persist
passwords, one-time codes, cookies, browser sessions, or sensitive voluntary
disclosures.
4. Expose an explicit `manual review required — no submission available` state.
   Submission confirmation, history recording, sign-out, and browser form work
   remain deferred.

**Acceptance:** tests cover exact-label-only reuse, 45-day expiry, changed
answer flags, sensitive-field exclusion, and the absence of any submission or
credential persistence path.

## Work package 4 — Local review UI and finalisation-only artefacts

**Files:** Phase II routes/templates, local static styles, finalisation service,
Phase II migration, document-generation adapter, and browser/document tests.

1. Add authenticated local review pages that show eligibility, supported
requirements, gaps, pending Phase I reviews, finalisation status, and the
explicit **Finalise résumé for this job** action. The normal runtime shows the
unavailable verified-job state until a later discovery phase exists.
2. Generate a fresh tailored document only from the authorised fact projection
and current job requirements. Retain no draft or revision files.
3. Create one final local PDF/DOCX pair only after the explicit finalisation
action; bind both to the same final content fingerprint and verify both files.
4. Keep Drive status as `not implemented`; never invoke sign-in, consent,
upload, sharing, or retry behaviour.

**Acceptance:** no file exists before finalisation; generic résumés and gaps
stop the flow; PDF/DOCX content matches; pages are keyboard accessible; no
browser action can submit an application.

## Execution order and checkpoints

1. Implement Work package 1 with synthetic fixtures; run focused tests, Ruff,
   mypy, and the full suite.
2. Implement Work package 2; run Phase I contract/review and Phase II safety
   tests, then the full suite.
3. Implement Work package 3; run answer/draft tests, storage inspection tests,
   and the full suite.
4. Implement Work package 4; run browser and document render verification,
   then the full suite and a safety review.

Each package must remain independently safe and leave provider access,
discovery, Google Drive, browser automation, credentials, and submission
disabled. Drive backup and visible-browser application handling remain
separate future plans requiring explicit approval.

## Plan self-review

- Consolidates every outstanding local-only item from the earlier Stage 1–4
  plan into one implementation phase.
- Keeps upstream real-job authorization and all external integrations out of
  scope, so the phase cannot accidentally start live job-search activity.
- Provides testable fail-closed behavior even while the discovery system is
  absent.
