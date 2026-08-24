# Phase II-B résumé and application safety design

## Status

Approved for planning on 2026-08-24. This document defines the résumé and
application safeguards only. It does not authorize implementation, provider
contact, Google Drive access, form submission, or a commit.

## Purpose

Phase II-B may help the user identify eligible roles and prepare application
drafts without making unsupported claims, silently using a generic résumé, or
submitting an application. The user remains the final decision-maker.

## Boundaries

* Phase II reads only versioned, approved Phase I snapshots through the
  existing internal matching port. It never reads Phase I tables directly.
* A locked Phase I search profile remains the authority for mandatory
  eligibility rules and match priorities.
* A job that fails a mandatory rule cannot reach résumé preparation or an
  application draft. A job with an unstated mandatory condition is marked
  `needs clarification` and also stops there.
* Phase II has no authority to create, strengthen, or reuse a career claim.
  A missing answer or every manual résumé-content edit must be reviewed and
  accepted in Phase I before it can be used.
* Voluntary sensitive-disclosure fields (including health, disability, gender,
  ethnicity, religion, caste, veteran status, and criminal history) are never
  saved or prefilled.
* Existing general résumé files are never read. A general résumé is never
  enough to begin an application draft.
* All source visits remain in a visible, user-inspectable local browser. A
  CAPTCHA, access block, or restriction stops that source; it is never
  bypassed.
* The cockpit never submits an application. It does not read or store passwords
  or one-time codes; the user enters them directly in the browser.

## Role-to-résumé flow

1. Phase II shows a verified, eligible job and waits for the user to choose
   **Prepare tailored résumé**.
2. It builds a draft from accepted Phase I facts and the current job
   description only. It does not read an existing résumé file.
3. The review screen identifies the job requirements supported by accepted
   facts and separately identifies unsupported gaps.
4. A gap pauses the flow. The user may provide an answer, but it enters Phase I
   review before it can appear in the résumé or be reused anywhere else.
5. The user may edit wording. Every content edit follows the same Phase I
   review-and-acceptance path before finalisation.
6. The user explicitly chooses **Finalise résumé for this job**. No résumé file
   is retained before this point.
7. Finalisation creates one final, identical-content PDF and Word (`.docx`)
   pair for that job. Earlier drafts and revisions are not retained as files;
   the local history keeps only basic application metadata.

## Application-draft flow

1. The user signs in to a site in the visible browser. The cockpit never sees
   or stores credentials or one-time codes.
2. It may fill only accepted Phase I information and accepted reusable answers
   for an exact, clearly-labelled question. Reusable answers expire after 45
   days. A changed answer never edits an existing draft; the draft is marked
   for review instead.
3. Missing, sensitive, or differently worded questions remain unanswered and
   are presented to the user. New reusable answers follow Phase I review.
4. After the user has finalised the role-specific résumé, the cockpit may show
   its name and version and attach that exact file to the visible draft.
5. It stops before submission. The user reviews and submits manually.
6. On a clear on-site success confirmation, it records a local metadata-only
   history entry (employer, role, source, date, and résumé version) to prevent
   duplicate applications, then signs out. If confirmation is unclear, it
   leaves the session open and asks the user to check.

## Local storage and Google Drive exception

Job data, preferences, answers, drafts, application history, source data, and
browser sessions remain local to the Mac in Phase II storage. The user has
explicitly authorized one narrowly-scoped exception: after the user finalises a
résumé, the final PDF and `.docx` pair may be backed up to a dedicated private
Google Drive folder named `Job Search Cockpit`.

The future Drive integration must:

* be limited to the folder and files created or explicitly selected for the
  cockpit, not the rest of Drive;
* create no public links, shares, collaborators, or external messages;
* run only after a visible user-authorized sign-in and consent flow;
* back up the final version only, immediately after finalisation;
* retain one final version per job, not draft or revision files; and
* if Drive is unavailable, save the final file locally as `Drive backup
  pending` and retry only when the user selects a visible **Retry backup**
  control.

No Drive account, folder, consent, or upload is performed by this design.

## Required screens

* Job detail: eligibility decision, source, score explanation, and the
  explicit **Prepare tailored résumé** action.
* Résumé review: supported requirements, gaps, local wording edits, Phase I
  review status, and **Finalise résumé for this job**.
* Finalisation: final PDF/Word filenames, local save status, and Drive backup
  status.
* Application draft: exact approved résumé attachment, unanswered-question
  prompts, a clear no-submit boundary, and a local history result after a
  confirmed manual submission.

## Verification requirements

Automated tests must cover at least:

* Phase I snapshot-only access and invalidation while drafting;
* failed and unknown eligibility rules;
* generic-résumé stop, unsupported-gap pause, and manual-edit Phase I review;
* exact-label-only reusable answers, 45-day expiry, changed-answer draft flags,
  and sensitive-field exclusion;
* finalisation-only file creation, matching PDF/Word content, and no retained
  drafts;
* Drive scope, user-consent boundaries, pending-backup recovery, and no
  background retry;
* no credential persistence, no automatic submission, ambiguous-confirmation
  handling, sign-out after confirmed submission, and duplicate prevention; and
* local-only behaviour for all data other than the final user-approved résumé
  backup exception.

## Intentionally out of scope

This design does not choose providers, connect to job sources, implement job
collection, activate scoring, create a Google Drive integration, submit forms,
send notifications, create external accounts, or alter the existing Phase II-A
activation foundation.
