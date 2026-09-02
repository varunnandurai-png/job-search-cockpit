# Phase I taxonomy review and bounded multi-bundle mapping

**Status:** approved design amendment; implementation pending plan review
**Date:** 2026-09-02
**Extends:** `2026-08-30-phase-2-local-manual-mapping-amendment.md`
**Preserves:** Phase I fact ownership, per-bundle retrieval limits, Phase II
append-only assessment data, Phase III direct-evidence gating, and Phase IV's
no-upload/no-submit boundaries.

## Problem

The recovered Phase I retrieval policy receives real accepted canonical fact
identifiers that its frozen classifier cannot classify. It therefore treats the
retrieval set as semantically incomplete. Separately, a real Eltropy listing
has 28 bounded public requirements and more than 96 requirement-to-fact
relevance edges. The existing one-bundle protocol correctly blocks both
conditions, but the local UI hides the reason behind a redirect.

Increasing the edge cap or treating incomplete retrieval as mappable is out of
scope: both would weaken the approved anti-enumeration and evidence-completeness
rules.

## Goals

1. Let the user review a controlled classification for every currently
   unclassified accepted Phase I canonical identifier.
2. Preserve a complete, bounded Phase I retrieval set per mapping bundle.
3. Permit one job to be mapped through more than one bounded bundle while
   producing one final Phase II assessment only when every bundle succeeds.
4. Make a failed launch visible in the local UI without exposing fact wording
   or provider content beyond the existing approved views.

## Non-goals

- Automatically changing a career fact, its safe wording, support assertion,
  eligibility, or resume content.
- Raising the 32-choice, 96-edge, 24-taxonomy-ID, 32-requirement, or
  64-distinct-disclosed-fact limits.
- Publishing a partial assessment, verification, résumé ledger, final résumé,
  Drive backup, or application submission.
- Sending user data to a new service or changing the provider-discovery policy.

## Phase I taxonomy review

### Review packet

Phase I derives a deterministic packet from active, accepted canonical fact
identifiers whose current classification is unknown. Each packet item contains
only its canonical identifier, current immutable claim/revision/support
references, and a proposed closed classification:

- one or more IDs from the existing frozen matching taxonomy; or
- `non_matching`.

The packet does not expose or persist free-form job text, raw fact wording,
model rationale, or arbitrary taxonomy strings. A claim's selected taxonomy
IDs must belong to the existing controlled taxonomy; `non_matching` has no
taxonomy IDs.

### Acceptance and authority

The user reviews and accepts the complete packet through the existing Phase I
acceptance flow. Acceptance appends a new taxonomy-review receipt bound to the
packet fingerprint, active claim/revision/support identifiers, current Phase I
authority generation, and restore generation. It never overwrites a prior
classification or receipt.

The Phase I matching classifier reads only the latest current receipt that
matches each exact active claim revision and support assertion. A missing,
stale, changed, duplicated, or malformed classification remains unknown and
causes any affected retrieval bundle to be incomplete. An accepted updated
packet invalidates the prior Phase I readiness/acceptance boundary; the user
must accept the new Phase I receipt and explicitly reactivate Phase II before
discovery, mapping, verification, or résumé work resumes.

### Classification rules

System-proposed classifications are deterministic rules over canonical
identifiers only. They can propose `non_matching` for explicit metadata classes
such as location, date, contact, and application facts. Certifications and
languages remain reviewable evidence because a job can require either. The
system may propose controlled taxonomy IDs only where exact canonical
identifier tokens match a frozen rule. The user may accept a proposal or select
another allowed closed value. The system cannot fabricate a new taxonomy,
career fact, or safe wording.

## Bounded multi-bundle mapping

### Planning

Phase II sends the existing immutable ordered requirement ledger, with at most
32 requirements, to one new Phase I-owned wording-free bundle planner. The
planner evaluates deterministic contiguous partitions without exposing rejected
candidate sets to Phase II, then returns only a complete ordered plan of child
manifests. A partition is valid only when its manifest is complete and stays
within every existing bundle budget:

| Limit | Maximum per bundle |
| --- | ---: |
| Requirements | 32 |
| Controlled taxonomy IDs | 24 |
| Relevant fact choices | 32 |
| Requirement-to-fact edges | 96 |

The planner starts with the longest remaining contiguous partition and reduces
the end position until it finds a complete manifest. If even one requirement is
incomplete alone, planning fails. The parent plan is also incomplete when the
union of its child choices would exceed the existing disclosure-epoch limit.
The resulting ordered partition list, each manifest fingerprint, and the
overall requirement-ledger fingerprint are bound into a parent mapping session
before any wording release.

Planning uses only existing public requirement IDs and controlled predicates.
It never transmits listing prose or requests arbitrary canonical keys.

### Authorization and release

Each child bundle has an independent nonce, Phase I disclosure authorization,
payload digest, expiry, manifest fingerprint, and append-only lifecycle. The
parent session becomes usable only after every child is authorized and every
released safe wording snapshot matches its corresponding manifest hashes.

All child bundles share the existing disclosure epoch. The union of disclosed
fact identifiers must remain within its 64-distinct-fact budget; a duplicate
fact exposed in several bundles counts once. A child failure, expiry, stale
manifest, policy-generation change, or budget exhaustion terminally fails the
parent and releases no mapping UI state. Retrying creates fresh child nonces
and authorizations; it cannot reuse a consumed child.

### Mapping and publication

The UI renders all public requirement clauses in their original deterministic
order, labelled with a bundle number and progress. For each requirement it
shows only the approved choices connected by that bundle's authorized edges,
plus the existing closed `none` options. It accepts no free-form evidence or
score.

On submit, Phase II validates exactly one selection per requirement, verifies
the selection belongs to its child bundle's current manifest, revalidates every
child manifest and released reference, and consumes every child authorization.
Only then may it combine the selections into the existing one assessment
publication. Existing direct-evidence requirements for verification and Phase
III ledger issuance remain unchanged: any required adjacent or `none` mapping
blocks both.

The parent and child records retain opaque identifiers, fingerprints, lifecycle
state, and authority fences only. Phase II continues not to persist Phase I
safe wording or provider job prose in new mapping tables.

## UI behaviour

The review page stores a bounded server-side status for the current local
session. A failed mapping launch returns to review with a neutral, specific
message such as `retrieval bundle exceeds the approved edge budget` or
`Phase I taxonomy review is required`. It does not reveal hidden fact choices,
raw exceptions, credentials, or stack traces.

The mapping page presents a parent session identifier, current bundle progress,
and the existing CSRF-protected form. Browser requests remain local-host,
same-origin, no-store, and session-bound.

## Data model and migration

Phase I adds append-only taxonomy-review packet, item, and acceptance-receipt
records with immutability triggers and exact active-fact bindings. Phase II adds
one parent mapping-session record and one child-bundle record per planned
partition. Existing single-bundle attempts are preserved as historical records;
new code reads them as a one-child parent only where all fields validate.

No migration mutates existing facts, claim revisions, safe wording, prior
receipts, mapping attempts, assessments, or resume ledgers.

## Failure handling

- Unknown or stale taxonomy review: retrieval is incomplete and mapping stops.
- A requirement that cannot form a complete single-requirement bundle: parent
  planning fails; no wording is released.
- A bundle that exceeds disclosure limits: parent planning fails; no assessment
  can publish.
- Any child after authorization fails or expires: terminally settle that child
  and parent; deny replay.
- Authority, profile, readiness, restore, revision, location, or provider-data
  drift: invalidate the parent before publication.
- Required `none` or adjacent evidence: publishable as an honest assessment,
  but not verifiable and never eligible for Phase III or IV.

## Tests and acceptance evidence

Automated tests must prove:

1. Unknown classifications block retrieval; an exact accepted current review
   permits only its declared taxonomy or explicit non-matching result.
2. A changed fact revision, support assertion, Phase I generation, or restore
   generation invalidates a taxonomy review and blocks mapping.
3. A job requiring more than 96 edges plans multiple deterministic complete
   bundles without exceeding any per-bundle cap.
4. An unplannable single requirement, incomplete bundle, stale child, exhausted
   disclosure epoch, or forged child selection blocks the parent.
5. Multi-bundle publication produces one full mapping set in requirement order;
   missing or duplicate selections cannot publish.
6. Required gaps still block verification, Phase III ledger creation, Phase III
   finalisation, and Phase IV backup.
7. The local review route displays a safe blocker rather than silently
   redirecting.
8. A real Eltropy preflight can plan bounded bundles after the user accepts the
   reviewed Phase I taxonomy packet. No real mapping selection, verification,
   or résumé finalisation is performed without that later explicit user action.

## Rollout sequence

1. Add the Phase I taxonomy-review data model, receipt, review route, and
   contract tests.
2. Add deterministic multi-bundle planning and opaque parent/child lifecycle
   persistence, behind the new taxonomy receipt gate.
3. Add the mapping UI and route status for bundle progress and safe failures.
4. Run focused unit/integration tests, lint, types, migration checks, and a
   local Eltropy preflight.
5. Ask the user to review and accept the fresh Phase I taxonomy packet, then
   record a new Phase I acceptance receipt and reactivate Phase II.
6. Resume Eltropy mapping only to the point of user-selected evidence. Do not
   verify or create a résumé until the user explicitly confirms those selections.
