# Phase 2 Design — Fresh Adversarial QA Review

**Date:** 2026-08-20
**Artifact reviewed:** `docs/superpowers/specs/2026-08-20-phase-2-job-discovery-match-scoring-design.md`
**Review method:** Three isolated, read-only adversarial reviews covering Phase 1 boundaries, discovery and eligibility, and scoring and acceptance. A cross-model review was offered and declined.
**Scope:** Design documentation only. No Phase 1 or Phase 2 application code and no live-provider access.

## Review contract

The reviewers were asked to find failures rather than validate the design. The design had to:

- Preserve the approved Phase 1 contracts and locked search profile.
- Keep Phase 2 disabled until Phase 1 implementation and acceptance.
- Prevent use of confidential, unresolved, rejected, stale, unsupported, or wrongly attributed facts.
- Keep discovery, scoring, confidence, and later-phase actions clearly separated.
- Define behavior precise enough for an implementation plan and acceptance tests.

## Reconciliation key

- `Actionable`: confirmed defect; the design was changed.
- `Mixed`: part confirmed and fixed; part resulted from an incomplete or incorrect reading of the approved contract.
- `Trade-off`: real limitation that cannot be eliminated; the design now states it explicitly and constrains its impact.
- `Contract misread`: the approved source already resolves the concern; clarifying text or tests were added when useful.

## Phase 1 boundary and safety findings

| ID | Classification | Resolution |
|---|---|---|
| B1 | Mixed | Added normative consumer-side contracts and a fail-closed adapter check. If implemented Phase 1 cannot satisfy them, Phase 2 stays blocked and Phase 1 must be amended and reaccepted. |
| B2 | Actionable | Revalidation now occurs before every live access, packet, publication, display, and handoff; drift suspends Phase 2. |
| B3 | Trade-off + actionable | Added one-use dispatch authorization and generation fencing. The document now states that later revocation cannot erase an already authorized external disclosure but blocks all future use. |
| B4 | Actionable | Selected fresh non-interactive Codex CLI sessions with a validated restricted profile, schema output, consent, and fail-closed activation. |
| B5 | Actionable | Added capped requirement-scoped Phase 1 retrieval and prohibited broad fact enumeration. |
| B6 | Actionable | Separated immutable audit metadata from purgeable content, added cited-span retention and restore-safe tombstones, and prohibited stored model fact prose. |
| B7 | Actionable | Added a Phase 2 recovery ledger, restore fencing, replay of later revocations, and disabled-after-restore state. |
| B8 | Mixed | Restored lateral-AI, Singapore-domain, and Principal predicates. Indian `annual_total` basis already exists in the approved Phase 1 implementation plan; the design now clarifies component comparison. |
| B9 | Actionable | Defined exact four-source completeness, hashes, parse success, and superseding-attempt checks. |
| B10 | Actionable | Split job-only gates from later evidence-clearance assessment and reordered the flow. |
| B11 | Actionable | Every semantic gate now uses pass/fail/unknown; potentially failing unknowns require review and cannot be shortlisted. |
| B12 | Actionable | Employer and end-client exclusion identity must be cleared before shortlist entry. |
| B13 | Actionable | Calculator now derives anchors from requirement importance and validated mappings. |
| B14 | Actionable | Unchanged inputs reuse an assessment; any changed anchor, band, shortlist state, or readiness outcome is unstable. |
| B15 | Actionable | Added span IDs, closed enums, no model prose, suspicious-content quarantine, and semantic mapping validation. |
| B16 | Actionable | Fact-bearing services are in-process only and are not browser or loopback endpoints. |
| B17 | Actionable | Added independent per-location eligibility paths and selected-path readiness. |
| B18 | Actionable | Defined adapter completeness proofs, two complete absences plus direct check, and reopening transitions. |
| B19 | Actionable | Merges are reversible identity links with audited split and invalidation. |
| B20 | Actionable | Any unavailable or incompatible Phase 1 check now fails closed across all sensitive actions. |
| B21 | Actionable | Only one run may be active; staged writes and run generations fence merges and restore. |
| B22 | Actionable | Replaced a stale readiness boolean with an immutable decision and one-use Phase 3 capability. |
| B23 | Actionable | Defined effort units, lane attribution, bootstrap, failure accounting, rounding, and standard versus diagnostic runs. |
| B24 | Actionable | Added HTTPS-only retrieval, per-hop DNS validation, redirect limits, credential stripping, no-referrer, and opener isolation. |
| B25 | Actionable | Added typed warning evidence and made acknowledgement insufficient for readiness. |
| B26 | Actionable | Added documentary and explicit-user-confirmation support kinds and exact support-event IDs. |
| B27 | Actionable | Added read-only browser-assistance containment and runtime tests. |
| B28 | Actionable | Changed status to user-approved draft under QA and added the written-review gate before planning. |

## Discovery and eligibility findings

| ID | Classification | Resolution |
|---|---|---|
| D1 | Mixed | Added a positive eligible-role gate, Product Owner condition, and bounded aspirational lane. Growth PM was not added because it is absent from the approved Phase 1 eligible role profiles. |
| D2 | Contract misread + clarification | Preserved Phase 1's `annual_total` Indian basis and now stores each pay component separately; ambiguous or speculative components cannot prove the floor. |
| D3 | Actionable | Added independent location paths with their own pay, sponsorship, and work-arrangement result. |
| D4 | Actionable | Target-city or explicit target-country employment can pass; region-only wording remains conditional. |
| D5 | Actionable | Added seven-day shortlist and 24-hour readiness verification limits. |
| D6 | Actionable | Added complete whole-set fact snapshots, query scope, selection policy, and invalidation on additions or removals. |
| D7 | Actionable | Fuzzy similarity now creates only a possible duplicate; tenant, generation, locations, and split behavior are explicit. |
| D8 | Actionable | Defined retention categories and preserved cited spans plus audit metadata without retaining every full description forever. |
| D9 | Actionable | Added the typed evidence-resolution matrix. |
| D10 | Actionable | An explicit non-negotiable start requirement shorter than 60 days is now ineligible. |
| D11 | Actionable | Provider adapter approval and exact tenant or endpoint approval are separate and both required. |
| D12 | Actionable | Expanded employer identity, end-client, alias collision, evidence, expiry, and risk states. |
| D13 | Actionable | Added deterministic aggregation, independently adjudicated golden outputs, and exact boundary checks. |
| D14 | Actionable | Defined search effort and rolling-window behavior, including failed attempts and diagnostic-run exclusion. |
| D15 | Actionable | Defined a versioned approved provider universe; market-wide coverage is not claimed. |
| D16 | Actionable | Added a separate employer-risk model and readiness consequences. |
| D17 | Actionable | Split lifecycle into availability, verification, revision, duplicate, and presentation dimensions. |
| D18 | Actionable | Defined transport health versus completeness and conservative closure evidence. |
| D19 | Actionable | Readiness binds every supporting decision, version, observation, policy, and expiry. |
| D20 | Actionable | Dismissal changes presentation only; saved and rejected views and shortlist tie-breaking are explicit. |
| D21 | Actionable | Added packet nonce, one-use consumption, retry identity, expiry, and concurrent replay tests. |
| D22 | Actionable | Added separately authorized live read-only smoke checks after fixture acceptance and provider-instance approval. |

## Scoring and acceptance findings

| ID | Classification | Resolution |
|---|---|---|
| S1 | Actionable | Added a span-level requirement coverage ledger and blocked unclassified or material uncertain clauses. |
| S2 | Actionable | Added required-clause blocking and role-profile critical component floors. |
| S3 | Actionable | Added selected per-location eligibility and readiness paths. |
| S4 | Actionable | Added explicit Principal, Applied-AI, and Technical-PM evidence predicates. |
| S5 | Actionable | Added exact threshold-boundary adjudication and instability on any band or readiness change. |
| S6 | Actionable | Made evidence validity a score invariant and limited readiness-safe medium confidence to non-material preferred gaps. |
| S7 | Actionable | Replaced subjective anchor selection with requirement weights, mapping strengths, coverage thresholds, and caps. |
| S8 | Actionable | Added deterministic, versioned, recall-tested fact retrieval and completeness blocking. |
| S9 | Actionable | Restricted interpreter responses to IDs and enums; trusted templates generate explanations. |
| S10 | Actionable | Added typed warning evidence and prohibited free-form clearing. |
| S11 | Actionable | Added freshness policies and immediate readiness or handoff rechecks. |
| S12 | Actionable | Added immutable readiness decisions containing every clearance input and combined fingerprint. |
| S13 | Actionable | Defined separate employer-risk and compensation-confidence models. |
| S14 | Actionable | Added strict packet allowlist serialization and nested negative fixtures for every forbidden class. |
| S15 | Actionable | Golden fixtures now contain independently adjudicated expected outputs and mutation tests, not only repeatability checks. |
| S16 | Actionable | Added unique nonce, single-use consumption, and replay or retry rules. |
| S17 | Contract misread + clarification | Kept the approved Phase 1 `annual_total` basis and clarified that non-comparable or speculative components stay conditional. |

## Accepted limitations

Two limitations cannot be erased by local design:

1. A Phase 1 decision made after an authorized restricted packet is sent cannot retroactively remove that packet from the external service. The design records the authorization point, prevents all later use, and discloses the boundary.
2. Data sent through existing Codex/ChatGPT access is governed by Varun's current OpenAI workspace data settings. The cockpit records consent and configuration and deletes local raw packets, but it cannot promise external retroactive deletion.

## First-cycle result

All confirmed first-cycle defects received design corrections. No finding authorized application code or live-provider access. Because the findings were substantive, a second isolated pass reviewed the corrected artifact.

## Second-cycle Phase 1 boundary findings

| ID | Classification | Resolution |
|---|---|---|
| B2-1 | Actionable | Final mapping packet is canonicalized first; Phase 1 authorizes its exact digest at a durable conservative disclosure boundary immediately before synchronous delivery. |
| B2-2 | Actionable | Any Phase 1 restore now requires a fresh four-source import, full acceptance run and receipt, and new Phase 2 grant. |
| B2-3 | Actionable | Added acceptance receipt plus ABA-safe readiness, profile, authority, and restore generations. |
| B2-4 | Actionable | Phase 2 owns activation; Phase 1 validates only its own generations and owns fact-disclosure authorization. |
| B2-5 | Actionable | Split public requirement extraction and fact-bearing evidence mapping into separate packets, sessions, schemas, and audits. |
| B2-6 | Trade-off + actionable | Replaced read-only-sandbox claims with a capability matrix and OS-level wrapper; automated use fails closed and local manual mapping remains available. |
| B2-7 | Actionable | Phase 2 restore makes all external-world observations and factual resolutions stale regardless of prior TTL. |
| B2-8 | Actionable | Defined readiness capability issue and consume operations with exact audience, attempt, expiry, nonce, and atomic burn. |
| B2-9 | Actionable | Corrected the gate: the plan may be written now; only plan execution is blocked by Phase 1 acceptance. |
| B2-10 | Contract misread + clarification | The approved Phase 1 implementation plan defines Indian floors as `annual_total`; added an exact guaranteed-cash comparison formula. |
| B2-11 | Actionable | Added controlled semantic requirement predicates and fail-closed unknown taxonomy behavior. |
| B2-12 | Actionable | Added cleanup for every terminal and crash outcome plus startup orphan retirement. |
| B2-13 | Actionable | Added audience-specific later-phase projections and a minimized Sites-safe concept. |
| B2-14 | Actionable | Separated requirement-level directness reason codes from calculator-derived component anchor reasons. |

## Second-cycle discovery findings

| ID | Classification | Resolution |
|---|---|---|
| D2-1 | Actionable | Added the separate public extraction packet and closed extraction schema. |
| D2-2 | Actionable | Fixed the standard run at 100 units with an exact 3×3 matrix, unique query hashes, provider distribution, terminal-state window, and unavailable capacity. |
| D2-3 | Actionable | One requirement now has one capped result; multiple facts cannot inflate its weight. |
| D2-4 | Actionable | Split catalog, saved, dismissal, and computed shortlist dimensions. |
| D2-5 | Actionable | Defined posting generation before dedupe and distinguished continuous revisions from reopening. |
| D2-6 | Actionable | Added a complete employer state-to-gate matrix and current `no_known_concern` procedure. |
| D2-7 | Actionable | Added an exhaustive state-based retention table, clock origin, pause and reset events, and all source copies. |
| D2-8 | Actionable | Clarified that official source fields provide evidence but never self-authorize decisions. |
| D2-9 | Actionable | Defined Indian guaranteed-cash comparison and 30- or 90-day confirmation expiry. |
| D2-10 | Actionable | Added versioned normalization transformations, thresholds, and conservative ambiguous behavior. |
| D2-11 | Actionable | Added immutable written-confirmation provenance and authenticity rules plus employer-risk resolution. |
| D2-12 | Actionable | Added stability lifecycle, invalidation, policy generations, and adjudication. |
| D2-13 | Actionable | Enumerated the four initially authorized adapter types and retained instance-level approval. |
| D2-14 | Actionable | Added retrieval ground truth with zero required/critical omissions and 95% material recall. |
| D2-15 | Actionable | Separated current evidence display from a redacted, non-actionable historical view. |

## Second-cycle scoring findings

| ID | Classification | Resolution |
|---|---|---|
| S2-1 | Actionable | Added two explicit packet stages and richer controlled retrieval predicates. |
| S2-2 | Actionable | Added atomic clauses, `AND`/`OR`, numeric minima, locked modality precedence, and the initial component mapping table. |
| S2-3 | Actionable | Added exactly one capped evidence result per requirement and separated component reasons. |
| S2-4 | Actionable | Added a qualified match band so a critical gap cannot be labelled strong despite a high raw total. |
| S2-5 | Actionable | Defined exact rational intervals, zero-denominator handling, and minimum breadth for `close`. |
| S2-6 | Actionable | Added latest-stable and active-policy requirements, conservative medium-confidence bounds, and atomic invalidation on disagreement. |
| S2-7 | Actionable | Defined a pre-implementation frozen corpus with two independent adjudicators, over 20 qualifiers, decoys, exact intermediates, and mutation tests. |

## Second-cycle result

The second pass found substantive integration gaps, so the bounded QA workflow requires one final isolated pass after these corrections. No application code or live-provider connection has been created.

## Third-cycle Phase 1 boundary findings

| ID | Classification | Resolution |
|---|---|---|
| B3-1 | Contract misread + clarification | The approved Phase 1 implementation plan explicitly defines both Indian `MoneyFloor` values with basis `annual_total`. The design now quotes those exact golden-profile entries and blocks comparison if accepted Phase 1 returns anything different. |
| B3-2 | Actionable | Split the adapter gate into a planning-only contract comparison now and a first executable adapter proof after Phase 1 acceptance; every other Phase 2 task stays blocked until it passes. |
| B3-3 | Actionable | Added the Phase 2 restore generation to the activation grant; restore suspends it and requires a new grant. |
| B3-4 | Actionable | Added durable Phase 2 `InterpreterPacketAuthorization` for both packet kinds; mapping requires matching Phase 2 and Phase 1 authorizations. |
| B3-5 | Actionable | Defined Phase 1 authorization as the exact disclosure boundary and made any later mutation reject response acceptance and all current use. |
| B3-6 | Actionable | Added packet, disclosure, cleanup, indeterminate, and future-capability events to the correct store's recovery ledger, including append-only consumption. |
| B3-7 | Actionable | Replaced the impossible literal file-read claim with an exact runtime/config/data allowlist, explicit data denials, service-endpoint egress allowlist, and negative probes. |
| B3-8 | Actionable | Defined `codex_restricted` and `local_manual` modes; manual work uses constrained controls and the same authorization, validation, calculation, stability, and audit rules. |
| B3-9 | Actionable | Defined the exact minimized future-draft snapshot and made Phase 1 construct, authorize, and synchronously deliver it under its mutation coordinator. |

## Third-cycle discovery findings

| ID | Classification | Resolution |
|---|---|---|
| D3-1 | Contract misread + clarification | Preserved the explicit Phase 1 plan basis and added a fail-closed check against the implemented Phase 1 snapshot. |
| D3-2 | Actionable | Added an exact terminal-unit truth table, one immutable 100-unit run, retry attribution, and one fixed four-published-run reporting window. |
| D3-3 | Actionable | Added separate global vetoes and path pass/conditional/fail aggregation; evidence can never be mixed across locations. |
| D3-4 | Actionable | Added a pre-link posting identity key, identity precedence, observation-only source keys, and generation-before-linking. |
| D3-5 | Actionable | Added strictest-result precedence across employer approval and risk; no permissive state can override exclusion, quarantine, rejection, or blocking risk. |
| D3-6 | Actionable | Added legal lifecycle invariants and one controlling, precedence-defined retention clock with cancellation and a 30-day maximum. |
| D3-7 | Actionable | Shortlist membership now explicitly requires active and not dismissed; final ordering uses stable job ID, and exact 59/60/61-day notice fixtures were added. |

## Third-cycle scoring findings

| ID | Classification | Resolution |
|---|---|---|
| S3-1 | Actionable | Replaced the cross-store check-then-return flow with a conservative non-retryable protocol: Phase 1 builds and delivers the exact snapshot while mutations are excluded. |
| S3-2 | Contract misread + clarification | Retained the exact approved `annual_total` Phase 1 plan fields and made mismatch a blocker. |
| S3-3 | Actionable | Defined shallow Boolean requirements, one-weight `OR` aggregation, winning-member evidence, mixed-component review, duplicate collapse, and nesting rejection. |
| S3-4 | Actionable | Added a closed, locally validated direct/adjacent/none reason-code truth table with exact numeric and ambiguity boundaries. |
| S3-5 | Actionable | Replaced overlapping qualified bands with an ordered, mutually exclusive, exhaustive decision table and exact meaningful-evidence predicate. |
| S3-6 | Actionable | Added a severity-ordered confidence table and exact conservative lower-bound arithmetic for unresolved preferred criteria. |
| S3-7 | Actionable | Tightened retrieval to zero scoring-relevant omissions; any omission blocks a current score, band, rank, shortlist, and readiness authority. |
| S3-8 | Actionable | Split exact frozen-response pipeline acceptance from three-run automated-interpreter qualification and froze complete shortlist ordering, timestamps, states, and tie fixtures. |

## Final QA result

All confirmed third-cycle findings received design corrections. The two repeated Indian-compensation objections were reconciled against the explicit approved Phase 1 implementation-plan contract rather than changing a locked rule. Per the three-cycle doubt-review limit, no fourth adversarial cycle was started; the corrected artifact instead received a final local consistency, placeholder, formatting, and contract check. This QA result applies only to the Phase 2 design. Phase 1 application code is still not built, Phase 2 is not implemented, and no live provider has been connected.
