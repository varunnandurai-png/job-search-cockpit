# Phase II local-manual evidence mapping amendment

**Status:** implementation amendment to the approved Phase I-IV recovery design  
**Supersedes:** only the requirement-ledger implementation details in recovery-plan Task 3  
**Preserves:** provider discovery, Phase I authority, scoring, Phase III finalisation, and Phase IV boundaries

## Why this amendment is required

The recovery plan proposed public job-clause IDs such as
`job.<revision>.required.<n>` and then placed those IDs in the Phase III resume
requirement ledger. The implemented Phase I contract resolves a resume
requirement only by exact `Claim.canonical_key`. A public job-clause ID is not a
Phase I fact key, so that handoff cannot produce an approved fact projection.

The repository also has no production producer for `Phase2RequirementMapping`.
Assessment tests construct opaque mappings directly, but a newly discovered job
cannot create them through a service, command, or UI. Faking either the mapping
or the ledger would make synthetic tests pass while a real job still fails.

## Corrected local workflow

1. Phase II loads the latest immutable job revision and deterministically
   extracts at most 32 bounded, cited public requirements. Uncertain mandatory
   clauses remain visible and blocking.
2. Phase II sends one job-level bundle containing all bounded controlled
   taxonomy predicates for at most 32 requirements. Phase I first returns the
   complete wording-free retrieval manifest. After the two stores authorize the
   same logical payload digest, Phase I releases one non-pageable,
   authority-fenced set of at most 32 unique relevant, current, accepted,
   supported, non-confidential, resume-eligible fact choices plus their
   requirement edges.
   A fact cap, taxonomy-breadth cap, unknown taxonomy, incomplete examination,
   or semantic uncertainty marks the bundle incomplete and blocks mapping. Each
   choice contains the canonical key, opaque claim/revision/support IDs, and
   already-approved safe wording. Phase II never queries Phase I tables or
   enumerates unrelated facts.
3. The cockpit shows one public requirement and the Phase I-owned choices. The
   user may select one choice or **No approved evidence** and may choose only
   closed relation and reason-code values. It cannot accept free-form facts,
   mapping explanations, or scores.
4. Submission reloads the current job revision and requirements server-side,
   rejects changed or unknown identifiers, obtains the selected Phase I
   projection, and constructs exact `RequirementEvidenceMapping` values.
5. Existing fixed scoring and `AssessmentPublicationService` accept the exact
   expected Phase I fact-set/projection snapshot, verify that every non-`none`
   mapping belongs to it, and revalidate it immediately before and again inside
   the Phase II mutation. Persisted rows use that expected snapshot's authority
   fence; they never relabel old evidence with a newer authority generation.
   The service then appends the assessment, components, mappings, and shortlist
   decision.
6. Only an assessment with direct approved evidence for every mandatory
   requirement can issue a Phase III ledger. The ledger contains deduplicated
   Phase I canonical fact keys in first-requirement order, never public job IDs.
7. Verification reloads the current assessment and ledger and does not trust
   posted eligibility, gap, score, or requirement values.

## Additive Phase I contract

Extend the implemented `Phase1MatchingRequirementQuery` into the bounded
job-level semantic bundle required by the original Phase II design. Add durable
preflight, disclosure-authorization, and wording-release operations that
together produce one complete `Phase1MatchingFactSetSnapshot`. This replaces
the implemented exact-canonical-key lookup for production matching; the existing
`resume_fact_projection()` remains unchanged for Phase III.

The bundle binds job revision, coverage-ledger fingerprint, a fingerprint of the
current local launch session, and 1..32 server-generated job requirement IDs.
Each requirement contains only controlled, versioned taxonomy predicates:
component, modality, capability/responsibility, domain, technical-object,
outcome/scale, role-profile, and applicable employer/period constraints. It
contains no raw listing prose, free-form search text, canonical Phase I key, or
instruction. The response contains:

- query and retrieval-policy versions and fingerprint;
- at most 32 unique relevant eligible choices and bounded requirement edges in
  one non-pageable set;
- canonical key, claim ID, exact active revision ID, current support assertion
  ID, and approved safe wording;
- candidate-universe/examined counts, omission reason counts, complete semantic
  and structural states, and eligible-set fingerprint;
- Phase I profile, readiness, authority, and restore generations;
- a canonical set fingerprint.

Phase I applies the same resume-eligibility checks used by final projection.
Relevance is selected inside Phase I from a frozen taxonomy/retrieval policy and
verified against a retrieval corpus. Ordering is stable by canonical key and
claim ID. If more than 32 relevant facts exist, a predicate is unknown, or the
set cannot be proven complete, `complete` is false and no mapping or score can
publish. Exact revalidation fails closed when authority, the complete eligible
set, or any returned fact changes. The response is local-session only, rendered
with `Cache-Control: no-store`, and never stored wholesale in Phase II.

## Anti-enumeration and disclosure authorization

One bundle may contain at most 32 requirements, seven component categories,
24 distinct controlled taxonomy IDs, 32 unique returned facts, and 96 bounded
requirement-to-fact relevance edges. Exceeding any budget returns an incomplete
snapshot and blocks mapping and publication.

Authorization uses a two-step handshake. Phase I first returns a wording-free,
authority-fenced retrieval manifest containing the complete relevant opaque fact
references, relevance edges, and SHA-256 of each approved safe wording. The
manifest has its own immutable fingerprint and exposes no career wording.

Phase II then canonicalizes the exact logical local-manual mapping payload. Its
digest binds packet/attempt ID and nonce, job revision, selected location path,
coverage ledger, all validated public requirements, the immutable retrieval
manifest and wording hashes, allowed relation/reason controls, rubric,
retrieval/interpreter configuration and response-schema versions, Phase I and
Phase II generations, recipient mode, issue time, and expiry.

Phase II first appends an `InterpreterPacketAuthorization`-equivalent mapping
attempt in its append-only store and recovery ledger, bound to the manifest and
final logical-payload digest. Phase I recomputes and validates that digest from
the exact manifest and context, then appends the matching
`FactDisclosureAuthorization` in its audit store and recovery ledger. Only then
does Phase I release the one-use wording snapshot. Phase II verifies every
released wording against its manifest hash before rendering. Neither
authorization record contains raw wording. Phase I authorization is the
conservative disclosure boundary and is considered consumed as soon as it is
durably recorded, even if release or rendering later fails.

For one job revision, coverage fingerprint, disclosure-budget epoch, and Phase I
generation, an identical preflight query reuses the immutable retrieval
manifest; a different query is rejected. Before a Phase II mapping attempt is
consumed, an exact reload of its authorized digest may re-release the same
wording snapshot. After `consuming` or any terminal event, replay is denied.
Phase I permits at most 64 unique fact IDs and 32
distinct taxonomy IDs over **all** authorizations in the current monotonic
disclosure-budget epoch, including consumed, expired, denied, failed, and
indeterminate attempts. A new launch session does not reset the budget.
Exhaustion marks the request incomplete and blocks further disclosure.

Opening a new disclosure-budget epoch requires a separate authenticated,
CSRF-protected user action, a reason, the exact confirmation
`START NEW MATCHING DISCLOSURE EPOCH`, and append-only Phase I audit/recovery
events. It increments a monotonic policy generation and never deletes or stops
counting history within an earlier epoch.

The mapping form POST atomically changes the Phase II attempt from `authorized`
to `consuming` before accepting any response. It validates the closed response
against the exact payload digest and current Phase I/II generations, revalidates
the fact set, publishes the assessment in the same Phase II mutation, and
appends terminal `validated_response`. Any expiry, denial, validation failure,
cancellation, crash after consumption, or uncertain outcome appends a terminal
`expired`, `denied`, `failed`, or `indeterminate` event. No terminal or
`consuming` attempt can be replayed; a retry requires a new attempt ID/nonce,
logical-payload digest, and authorizations bound to the same immutable retrieval
manifest, and still counts against the same disclosure epoch.

The existing `resume_fact_projection()` remains the final authority for selected
keys used by Phase III. The semantic query changes the previously incomplete
matching implementation to the already-approved original contract; it does not
change existing Phase III response shapes or weaken Phase I checks.

## Persistence and audit binding

Additive Phase I tables retain monotonic disclosure-budget epochs and exact
fact-disclosure authorization state. Additive Phase II tables retain mapping
attempts and append-only lifecycle events. Both databases add immutability and
uniqueness constraints, and both recovery ledgers record the matching digest
and terminal state needed to reconcile an interrupted handshake.

Existing assessment and mapping tables remain the append-only scoring source. A
resume ledger fingerprint binds the exact job revision, current assessment ID,
ordered mapping IDs and evidence references, canonical output keys, and active
Phase II generations. The ledger's `source_kind` remains `phase2_assessment` and
is now proven by that binding.

## Fail-closed rules

- Missing assessment, stale revision, authority drift, altered choice, invalid
  relation/reason pair, or incomplete mandatory mapping blocks verification.
- `none` uses no fact IDs. `direct` and `adjacent` require one currently eligible
  selected fact.
- Unsupported mandatory requirements stay visible and block ledger issuance.
- Automatic keyword-to-career-fact mapping, direct Phase I database reads,
  full-vault Phase II persistence, and synthetic ledger IDs are prohibited.
- No external interpreter, provider call, Google action, or application action
  occurs in local-manual mapping.

## Acceptance

Automated acceptance must prove:

- taxonomy-scoped, complete non-pageable retrieval and authority revalidation at
  the Phase I boundary;
- confidential, stale, unsupported, conflicted, and unapproved facts are absent;
- unrelated facts cannot be enumerated and cap/incompleteness blocks mapping;
- changed or forged mapping input is rejected;
- evidence drift between form submission and publication cannot create a current
  assessment;
- consumed, expired, failed, or cross-session authorizations cannot reset the
  disclosure budget or be replayed;
- Phase I and Phase II recovery ledgers bind the same exact payload digest and
  preserve indeterminate outcomes;
- released wording must match the pre-authorized manifest hashes, and retries
  cannot change the retrieval manifest silently;
- a complete manual mapping publishes an assessment and canonical-key ledger;
- an unsupported mandatory requirement cannot verify or enter Phase III;
- a discovered test job can proceed through mapping, verification, Phase III
  finalisation, and mocked Phase IV backup without a production bypass.
