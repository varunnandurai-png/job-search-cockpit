# Phase II provider discovery and verified-job authorization design

## Purpose

Add a bounded, local job-discovery path that can eventually issue a verified,
short-lived authorization for Phase II preparation. A provider listing is only
a candidate. It cannot authorize résumé preparation, document generation, or
an application submission by itself.

## Sources and pilot limits

The first manual pilot uses these read-only sources:

- Apify LinkedIn Actor: `curious_coder/linkedin-jobs-scraper`, at most 40
  listings.
- Apify Naukri Actor: `crawlerbros/naukri-scraper`, at most 25 listings.
- JSearch through the configured RapidAPI subscription: one request.

The Apify run uses a US$0.50 maximum charge when the selected Actor supports a
per-run charge limit. The application also enforces the listing caps. No
scheduled runs, automatic retries, browser automation, provider sign-in,
submission, uploads, sharing, or notifications are in scope.

Provider credentials stay only in the git-ignored local `.env` file. They are
never copied into application storage, logs, test output, or version control.

## Discovery boundary

1. A user explicitly starts a manual discovery run.
2. Read-only provider adapters retrieve the bounded listings and retain each
   source observation with its source identifier, canonical URL, retrieval
   time, raw-content fingerprint, and provider/run metadata.
3. Phase II normalizes source observations and deduplicates them into local
   job records without discarding the source provenance.
4. The service retrieves the current profile through the internal Phase I
   matching port and fails closed if the snapshot cannot be obtained or changes.
   It does not read Phase I tables or hard-code roles, locations, compensation,
   exclusions, or other search rules.
5. Eligibility and requirement assessment produce an auditable candidate
   result. Uncertain, stale, incomplete, or conflicting source data remains
   unverified.
6. Only a separately explicit local verification decision for an eligible,
   current job revision may issue a one-use, expiring
   `VerifiedJobPreparationAuthorization`.
7. Phase II revalidates that authorization immediately before preparation,
   drafting, finalisation, and any artefact access.

## Data minimization and retention

The Phase II catalog stores only the listing data, source provenance,
assessment results, immutable revision fingerprints, and authorization
metadata required for discovery and audit. It stores no provider credential,
cookie, browser session, answer wording, OTP, password, voluntary-sensitive
disclosure, résumé draft, or application submission state.

Listings are append-only observations. Normalized job records preserve source
links and revision history so changed or closed listings invalidate a prior
candidate assessment or authorization rather than being rewritten in place.

## Safety and testing

- Production uses the existing `VerifiedJobReadinessUnavailable` adapter until
  this design is implemented and a specific authorization is issued.
- No synthetic data, fabricated listings, or saved response fixtures are
  created. Static tests may cover only configuration and fail-closed behavior
  without listing payloads. Provider verification uses a user-started,
  real-data micro-run: at most five listings from each selected Apify Actor,
  a US$0.10 per-Actor limit when supported, and one JSearch request. Returned
  public listings are production catalog records, never test fixtures.
- Provider adapters have strict timeouts, fixed request/listing limits, and
  sanitized error reporting. They make no retry, polling, webhook, or browser
  automation behavior.
- Static tests prove that unavailable configuration and Phase I snapshots block
  provider access, and that credentials never enter persistence or output. The
  user-authorized real-data micro-run verifies source retrieval, catalog
  persistence, deduplication, and the rule that a listing cannot directly
  create a preparation attempt, document, or submission.

## Deferred work

The remaining WP4 document adapter, finalisation route, and authorised review
view remain blocked on a real verified-job authorization. They are implemented
only after this upstream discovery and verification boundary is complete.
