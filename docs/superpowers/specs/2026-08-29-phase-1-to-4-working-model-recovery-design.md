# Job Search Cockpit Phase I–IV working-model recovery design

**Date:** 2026-08-29  
**Status:** Approved direction; written specification awaiting user review

## Outcome

The Job Search Cockpit will run locally as one usable workflow from the accepted
Phase I profile through real job discovery, job-specific resume finalisation,
and optional private Google Drive backup. Apify and JSearch are the production
discovery sources. A Vanguard page may be used as ordinary listing evidence,
but no employer-specific adapter or single-listing validation path is part of
this recovery.

Completion means the launcher starts the cockpit and the user can:

1. inspect the active Phase I profile and acceptance evidence;
2. manually fetch current public jobs through bounded Apify and JSearch calls;
3. inspect normalized, deduplicated, eligible, and scored candidates;
4. select and explicitly verify one current job revision;
5. review its requirement ledger and finalise its PDF/DOCX resume pair;
6. request or retry the existing Phase IV private Drive backup; and
7. see accurate actionable states when any external or manual gate remains.

No application form is filled or submitted. No job is applied to, no employer
is contacted, and no Drive upload starts without its existing explicit action.

## Recovery decision

The existing direct-official-source-only decision is superseded for discovery.
The earlier bounded Apify/JSearch implementation will be recovered from Git
history and adapted to the current codebase rather than restoring an old tree.
This preserves the Phase III and Phase IV safety work added after aggregator
discovery was removed.

Three approaches were considered:

- Restore the old tree wholesale: fastest, but it would discard later safety
  and backup work and is therefore rejected.
- Recover the earlier provider units and integrate them with the current
  runtime: selected because it restores the intended capability while keeping
  later work.
- Continue with employer-specific official adapters: rejected because it does
  not satisfy broad online discovery and caused the Vanguard-only detour.

## Source and credential boundaries

Production discovery uses these two source families:

- Apify Actors for bounded public-job retrieval, initially covering LinkedIn,
  Naukri, and Glassdoor where the selected Actor's current contract is verified.
- JSearch through RapidAPI for an independent, bounded search result set.

Actor IDs, endpoints, request fields, response shapes, pricing mode, and public
listing URL hosts must be verified against their current published contracts
before a live run. An adapter whose contract cannot be verified or whose output
fails validation is disabled without blocking the other provider.

The already-configured `APIFY_API_TOKEN` and `JSEARCH_API_KEY` remain local and
git-ignored. They are migrated into the clean recovery workspace without being
printed, logged, committed, copied into SQLite, or exposed in browser output.
Runtime configuration accepts only those exact keys.

Apify calls use the platform's item and total-charge caps. The first acceptance
run is a micro-run: at most five results per enabled Apify Actor and at most
US$0.10 per Actor. JSearch makes one request capped at 25 returned listings.
There is no scheduler, background polling, retry loop, or automatic paid run.

## Search inputs

Every discovery run reads the current accepted Phase I search-profile snapshot;
queries and eligibility rules are not hard-coded into provider adapters. The
current profile targets Senior, Lead individual-contributor, selected Principal,
Applied AI, and Senior Technical Product Manager work across Hyderabad,
Bengaluru, and Singapore. Location effort and role-lane allocations guide query
coverage rather than forcing result quotas.

The service records the exact profile version and activation generation used by
each run. If Phase I acceptance, Phase II activation, or the profile changes,
the run stops before the next provider call or persistence step.

## Components

### Provider configuration and adapters

Small source-specific adapters prepare bounded HTTPS requests and normalize only
the public fields needed by the catalog: provider listing ID, canonical URL,
title, employer, location, posting time, description, compensation wording,
and retrieval time. Each adapter rejects excess results, malformed identifiers,
unexpected response shapes, invalid URLs, and unapproved listing hosts.

Credentials are redacted by construction. HTTP clients use fixed connect/read
timeouts, no transport retries, and no redirects unless a provider contract
requires a narrowly approved redirect policy.

### Discovery orchestration

A manually initiated discovery service creates an append-only run, builds query
requests from the active profile, calls each available provider independently,
and records bounded provider outcomes. One failed provider produces a visible
partial result rather than deleting successful results or fabricating coverage.

Accepted observations are normalized and deduplicated into stable job records
and immutable revisions. Canonical URL and source identifiers remain attached so
the user can inspect where each listing came from.

### Eligibility, assessment, and shortlist

Existing Phase II rules apply location, role, employer, compensation,
sponsorship, notice-period, and evidence gates. Match Score remains separate
from confidence and unresolved eligibility. The cockpit must never promote an
unknown or unsupported fact into a verified claim.

The UI displays a focused candidate list plus provider/run status. Each card
shows source, title, employer, location path, freshness, score explanation, and
blocking checks. The user can select a current revision and record the required
eligibility confirmation, reason, and exact verification phrase.

### Phase III finalisation

A fresh verified-job authorization creates or exposes the job-specific
requirement ledger. Supported requirements map only to accepted Phase I facts;
unsupported or unknown mandatory requirements remain visible and block
finalisation. The existing preview, content fingerprint, and explicit finalise
confirmation produce one immutable PDF/DOCX pair for the verified revision.

The production mapping and ledger handoff follows the additive local-manual
contract in
`2026-08-30-phase-2-local-manual-mapping-amendment.md`. Public job-clause IDs
remain Phase II identifiers; only revalidated Phase I canonical fact keys enter
the Phase III resume ledger.

The previously disabled **Verify selected candidate** and **Finalise resume**
controls become available only when their real upstream state exists. They are
not enabled cosmetically and do not receive a bypass.

### Phase IV backup

The existing Phase IV implementation remains intact. A final pair exposes the
manual **Back up to Google Drive** action. Local acceptance covers all mocked
OAuth, Keychain, folder, upload, reconciliation, retry, and permission-expiry
paths. Real OAuth consent, Keychain storage, folder creation, and upload remain
visible user actions and are never performed silently during development.

## Error handling and recovery

- Missing credentials: show the exact missing provider without revealing paths
  or values; available providers may still run.
- Provider authentication, quota, cost, schema, timeout, or availability error:
  record a bounded failure code and continue with independent providers.
- Empty search: record a successful zero-result response; never substitute test
  or stale listings.
- Malformed listing: reject that observation and retain a bounded count/reason.
- Duplicate listing: retain source provenance and one stable job identity.
- Changed or closed listing: append a new observation/revision; never rewrite
  the earlier record.
- Activation/profile drift: stop immediately and require a new manual run.
- Resume evidence gap: keep the job reviewable but block finalisation.
- Drive failure: preserve the local pair and expose the existing safe retry.

No raw provider response, secret, unrestricted exception text, resume body,
Phase I confidential fact, OAuth material, or local filesystem path is logged.

## Testing and acceptance loop

Implementation proceeds in thin, test-driven increments. After each increment,
the narrow test is run first, followed by the affected unit/integration suites.
The loop returns to the earliest failing Phase I–IV gate until all local gates
pass.

Required verification includes:

- provider configuration, secret redaction, request caps, timeouts, host and
  schema validation;
- Apify and JSearch parsing against contract fixtures with no live dependency;
- append-only discovery persistence, normalization, deduplication, provider
  partial failure, and activation/profile drift;
- search-profile query construction, eligibility, scoring, shortlist, current
  revision selection, and verification expiry;
- requirement ledger generation and Phase III PDF/DOCX finalisation;
- existing Phase IV backup suites;
- migration-head, Ruff, mypy, unit, integration, and end-to-end test gates; and
- one user-authorized, cost-capped live discovery run using the configured local
  credentials, followed by manual browser acceptance of one real candidate.

Live results are evidence, not fixtures. Tests do not require provider access or
spend. The live acceptance report records counts and bounded statuses but never
credentials, raw payloads, or confidential resume content.

## Completion and manual boundary

Development is complete when all local automated gates pass, the capped live
run stores current real listings, one real candidate can traverse verification
and Phase III finalisation, and the launcher starts the clean recovery build.

The only acceptable manual boundaries are interactions that require the user's
identity or judgment: reviewing/choosing the candidate, making job-eligibility
confirmations, approving final resume wording, Google consent, and visually
confirming the resulting private Drive files. Those steps must have precise
instructions and accurate UI states; they are not reported as automated.
