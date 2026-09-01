# Task 3C report: assessment-bound canonical Phase III ledger

## Status

Delivered an assessment-bound, idempotent Phase III requirement ledger that contains
only revalidated canonical Phase I fact keys. Public `job.*` requirement IDs remain
in the Phase II assessment boundary and are never written to the resume ledger.

## Implementation

- Added a bounded Phase I resolution operation for an exact choice that has already
  been released. It verifies the authorization snapshot, non-terminal/expiry state,
  release event, immutable manifest membership and edge, active claim revision, exact
  support assertion, and current resume eligibility before returning only the
  canonical key plus opaque IDs.
- Persisted the returned canonical key on each non-`none` Phase II mapping through
  migration `0019_mapping_canonical_fact_keys`. `none` mappings receive no key.
- Verification reloads the latest authority-fenced stable/adjudicated assessment and
  mappings, rejects stale, malformed, `job.*`, unbound, or forged mappings, and
  requires direct approved evidence for every required requirement.
- The ledger de-duplicates canonical keys in first requirement order; its fingerprint
  binds revision, assessment, mapping evidence references, canonical keys, and active
  Phase II generations. An exact fingerprint reuses the ledger; a changed assessment
  produces a new one.
- Verification no longer trusts posted eligibility or unknown-rule command fields;
  it relies on the current assessed, fenced evidence state.

## Verification

`97 passed, 1 warning` for Task 3/Phase II/Phase I contract, scoring, mapping,
and migration-head suites; Ruff, mypy, and `git diff --check` also pass.

## Commit

Recorded in the accompanying `feat: bind resume ledgers to canonical assessment facts` commit.

## Concerns

Existing assessments created before migration `0019` have no canonical mapping keys
and deliberately cannot issue a resume ledger. They must be reassessed through the
current local-manual flow.
