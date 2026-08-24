# Job Search Cockpit — Phase 2 Design

**Date:** 2026-08-20  
**Status:** Phase II-A activation foundation implemented and verified locally. Provider approval, collection, scoring, shortlist, and every other live-discovery function remain unimplemented and disabled pending Phase II-B approval.
**Phase:** Job discovery and match scoring

## Current project status

Phase 1 has passed its documented quality gates, its four curated sources have a complete committed import, its readiness report is ready, and Varun explicitly accepted the Phase I acceptance receipt. Phase II implementation planning may now proceed. Runtime activation, provider access, and any live job work remain separately gated by the `Phase2ActivationGrant` and instance-level provider approval defined below.

No Phase 2 application code may be written, no live job listing may be read or stored, and no live job provider may be contacted until Phase 1 has been implemented and accepted.

Varun has reviewed and approved this corrected written specification, so implementation planning may proceed. Executing any Phase II plan task remains gated by Phase I acceptance, an approved implementation plan, and the runtime safeguards defined below.

## Purpose

Phase 2 creates a reliable local job-discovery and match-assessment capability for the Job Search Cockpit. It finds suitable opportunities, standardizes and deduplicates them, applies the locked search rules, and explains how well each job matches Varun's verified experience.

The central rule is that a good-looking score must never come from an invented, unsupported, stale, rejected, unresolved, wrongly attributed, or confidential fact.

## Scope

Phase 2 will eventually:

- Discover jobs through approved, enabled sources.
- Standardize listings without discarding their original wording.
- Identify reliable duplicates and preserve every source reference.
- Track live, changed, uncertain, expired, and closed listings.
- Apply the locked search profile before presenting a job as a match.
- Calculate an explained 100-point Match Score from real-work fit.
- Keep confidence, freshness, compensation, sponsorship, employer review, source verification, and notice-period compatibility separate from Match Score.
- Produce a focused list of up to 20 strong opportunities and a searchable list of other discoveries.
- Record provider health, discovery coverage, decisions, and assessment history.
- Create an auditable readiness decision for fully cleared 85+ jobs so Phase 3 can request a fresh, short-lived handoff later.

Phase 2 will not:

- Generate a resume or cover letter.
- Create or approve an application document.
- Fill or submit an application.
- Schedule Tuesday runs or missed-run catch-up.
- Publish the Sites dashboard.
- Send notifications or create a `WeeklyRefreshBundle`.
- Create an `ApplicationPacket`.
- Use a paid provider or separately billed model API.
- Contact a live job source before Phase 1 acceptance and explicit provider enablement.

## Locked search rules

Phase 2 must consume the active locked search-profile snapshot from Phase 1 as its sole authority. The rules below describe the currently active version 2 baseline; an implementation must not hard-code them and must fail closed if the snapshot is unavailable or changes.

### Eligible locations and search effort

- Hyderabad: eligible; approximately 40% of search effort.
- Bengaluru: eligible; approximately 45% of search effort.
- Singapore: eligible; approximately 15% of search effort and requires employer-sponsored Employment Pass support.
- Other locations are outside scope unless Varun explicitly creates a new search-profile version.

The percentages govern search effort, not results, score adjustments, or shortlist quotas. They must never promote a weak job, hide a stronger job, or force the shortlist to contain an artificial mix.

A remote job passes the location gate only when its official listing explicitly permits employment from a target city or explicitly permits employment from anywhere in the applicable target country. Region-only wording such as `APAC remote` remains conditional because it does not establish payroll or work-authorization eligibility. Singapore always retains its separate employer-sponsored Employment Pass requirement.

A multi-location job is not evaluated as one blended opportunity. Phase 2 creates a separate `LocationEligibilityPath` for each eligible target location. Each path binds its own location wording, work arrangement, compensation floor and basis, currency, sponsorship requirement, and verification evidence. A job may remain viable when one path fails and another passes. One passing path must be selected before future-drafting readiness can be granted.

### Role-difficulty search effort

- Direct-fit roles: approximately 50% of search effort.
- Stretch roles: approximately 35% of search effort.
- Aspirational roles: approximately 15% of search effort.

These percentages also govern search effort only. Difficulty classification is displayed separately and never changes Match Score.

Direct-fit, stretch, and aspirational lanes draw only from the locked eligible role profiles below. `Aspirational` means unusually demanding scope within those profiles; it is not permission to search for unrelated roles.

### Eligible role profiles

- Senior Product Manager.
- Lead Product Manager when it is an individual-contributor role.
- Selected Principal Product Manager individual-contributor roles supported by approved evidence.
- Applied AI Product Manager roles connected to existing domain experience.
- Senior Technical Product Manager roles involving platforms, APIs, integrations, data, fintech, lending, commerce, or fulfilment.

A job must positively match at least one of these versioned role profiles before it may be scored. Excluding known bad categories is not sufficient.

### Priority domains

- Digital lending, mortgage, and home buying.
- Banking, fintech, risk, fraud, and relevant payments experience.
- E-commerce, fulfilment, last mile, and omnichannel products.
- Subscriptions, billing, and commerce platforms.
- Platforms, APIs, and partner integrations.
- Data, analytics, operational products, and decision support.
- Applied AI, document intelligence, workflow automation, AI-assisted compliance, enterprise agents, and intelligent automation where domain overlap exists.

### Compensation floors

- Hyderabad: ₹50 LPA minimum disclosed annual total compensation (`MoneyFloor("INR", 5_000_000, "annual_total")`).
- Bengaluru: ₹55 LPA minimum disclosed annual total compensation (`MoneyFloor("INR", 5_500_000, "annual_total")`).
- Singapore: S$120,000 minimum disclosed annual base compensation.

Compensation rules are:

- A listing with no compensation remains `unknown`; it is not rejected.
- A disclosed range entirely below the applicable floor is ineligible.
- A disclosed range whose lower bound is below and upper bound is at or above the floor remains eligible with `target_compensation_must_be_confirmed`.
- A clearly comparable range entirely at or above the floor passes the compensation check.
- An unclear currency, period, base-versus-total basis, guaranteed-versus-variable basis, or conversion remains `needs_compensation_check`.
- Base or fixed pay, guaranteed variable pay, discretionary bonus, equity, joining payment, and deferred compensation are stored separately. Speculative bonus, equity, one-time joining payments, and deferred compensation cannot be used automatically to prove that an Indian annual-total floor is met.
- An unknown or warning-bearing compensation state blocks `ready_for_future_drafting`.
- The cockpit never guesses an undisclosed value or uses a live exchange rate to make an automatic eligibility decision.

Compensation confidence is separate from Match Score. Versioned states are `verified_comparable`, `verified_crosses_floor`, `unknown`, `incomparable_basis`, and `stale`. Each state records the exact location path, source observation, components, basis, policy, verifier, and recheck time. Only current `verified_comparable` compensation can pass future-drafting readiness.

### Exclusions and constraints

- JPMorganChase opportunities are always excluded. This includes official employer-name variations that clearly identify JPMorgan Chase or its hiring entities. There is no single-job override.
- Junior and Associate Product Manager roles are excluded.
- Generic Business Analyst roles are excluded.
- Program Manager roles without product ownership are excluded.
- People-management-heavy Director roles are excluded.
- Deep AI-infrastructure or foundation-model platform roles without relevant domain overlap are excluded.
- Roles representing a substantial level downgrade are excluded.
- A lateral title is acceptable only for genuine AI product scope; other lateral or lower titles remain conditional or excluded according to the locked profile.
- Delivery-only Product Owner roles are excluded. An ambiguous Senior Product Owner role may remain conditional only when both scope and disclosed compensation could be exceptional and the description indicates strategy, discovery, and outcome ownership.
- A Lead or Principal role with unclear individual-contributor status remains conditional until scope is verified.
- A selected Principal role requires approved evidence of Principal-level scope before scoring can proceed beyond conditional status.
- An Applied AI role requires approved evidence of connection to Varun's existing domain experience. Learning or prototypes cannot satisfy a production-experience requirement.
- A Senior Technical Product Manager role requires approved evidence of overlap with at least one locked technical or domain area.
- A general Singapore role without strong domain match or a credible sponsorship path is excluded or conditional as required by its location path.
- Notice period is 60 days. A listing with a potentially incompatible start-date requirement remains conditional and cannot become ready for drafting until reviewed.
- An explicit, non-negotiable joining requirement shorter than 60 days is ineligible. Ambiguous or negotiable timing remains conditional and requires dated employer or recruiter confirmation before readiness.

Changing any locked rule requires Varun's explicit confirmation, a reason, and a new Phase 1 search-profile version. Phase 2 cannot create a local exception that bypasses the active profile.

## Approved design choices

- Allocations are search-effort targets, not shortlist quotas.
- Missing compensation is kept, flagged, and blocked from future drafting until verified.
- Unknown Singapore sponsorship is kept, flagged, and blocked from future drafting until verified.
- Scoring emphasizes real work fit rather than keyword density.
- Initial discovery is reliability-first.
- Jobs from unfamiliar employers are shown and flagged, but blocked from future drafting until employer approval.
- Weekly output is a focused shortlist plus a searchable full list.
- Confidential facts never influence Phase 2 scoring, even if another use has a confidential permission.
- Matching uses an evidence-led hybrid: fixed rules own gates, weights, and arithmetic; a constrained interpreter maps differently worded requirements to evidence.
- Existing Codex/ChatGPT access may process a restricted scoring packet. No separately billed model API is part of Phase 2.

## Phase 1 dependency and activation gate

Phase 2 is disabled until all of these are true:

1. Phase 1 application code has been built.
2. The Phase 1 automated and manual acceptance checks have passed.
3. The latest four-source import is complete.
4. The Phase 1 readiness report says the verified profile is ready.
5. The active locked search profile is available through its approved service boundary.
6. A `Phase1AcceptanceReceiptSnapshot` identifies the exact successful test run, application commit or build, schema revision, acceptance-suite version, result fingerprint, restore high-water mark, and acceptance time.
7. Varun explicitly enables Phase 2 after viewing that report and the current readiness state.

The explicit enablement creates a revocable `Phase2ActivationGrant` issued and owned by the Phase 2 coordinator. It records the Phase 1 application commit or build, schema revision, acceptance-run ID and fingerprint, exact four-source committed import-run ID, active search-profile version and ABA-safe generation, readiness-report fingerprint and ABA-safe generation, Phase 1 restore high-water mark, Phase 1 contract version, Phase 2 restore generation, Phase 2 revocation generation, actor, confirmation, and time. Any Phase 2 restore suspends the old grant and requires a new grant after compatibility and staleness checks pass.

This grant is revalidated before every provider request, redirect, manual-URL fetch, fact-set request, scoring-packet dispatch, result publication, evidence display, and later-phase handoff. A changed import, readiness state, active profile, schema, application compatibility, acceptance record, restore generation, or unavailable Phase 1 check suspends all new Phase 2 live work immediately. Existing results remain visible only as clearly marked historical, unverified records.

The following cannot operate before the activation gate passes:

- Provider activation.
- Live or manual-URL job ingestion.
- Discovery runs.
- Employer approval for live discovery.
- Match assessment of a real opportunity.
- Shortlist creation.
- Future-drafting readiness.

The implementation plan has a separate human-controlled prerequisite: no Phase 2 implementation task may be executed until Varun confirms that the completed Phase 1 acceptance receipt is satisfactory. The plan may be written and approved earlier. The runtime activation grant does not replace the execution prerequisite.

## Separation from Phase 1

Phase 1 remains the sole owner of:

- Career claims and revisions.
- Documentary and user-confirmed support.
- Employer and time-period attribution for career facts.
- Factual decisions and sensitivity.
- The active locked search profile.
- Fact-vault readiness.

Phase 2 owns:

- Provider definitions, approvals, and health.
- Discovery runs and source observations.
- Employer review decisions for job-search use.
- Job records and revisions.
- Eligibility assessments.
- Extracted job requirements.
- Match assessments and confidence.
- Saved, dismissed, and shortlist decisions.

Phase 2 uses a separate local job-catalog database. It never reads or writes Phase 1 tables. Phase 1 and Phase 2 run inside the same local application process; fact-bearing Phase 1 methods are internal application-service calls and are never exposed as browser or loopback HTTP endpoints.

The two local stores are kept consistent through immutable snapshots, generation fences, and revalidation, not cross-database table access. A run captures Phase 1 input identifiers when it begins and rechecks them before every external packet dispatch and before publishing results. A mismatch prevents the action and requires recalculation.

Phase 1 facts are judged at the instant Phase 1 durably authorizes the exact restricted packet. That authorization is the conservative disclosure boundary even if delivery then fails. A later decision cannot retroactively remove already authorized data, but a mutation before response acceptance causes the response to be rejected and prevents publication, display, reassessment, readiness, or later handoff. Historical displays remain redacted. This temporal boundary is shown during interpreter consent rather than promising impossible retroactive deletion.

## Phase 1 service contract consumed by Phase 2

The approved Phase 1 design already requires later phases to use readiness, search-profile, and fact-vault application boundaries instead of tables. Phase 2 defines the exact consumer-side contract below. During planning, this contract is compared field by field and meaning by meaning with the approved Phase 1 design and implementation plan; no running adapter is claimed before Phase 1 exists. After Phase 1 acceptance, the first executable Phase 2 task is to implement and test a `Phase1MatchingPort` adapter against the accepted application. Every other executable Phase 2 task remains blocked until that adapter proves there is no semantic weakening. If it cannot, Phase 2 remains blocked and the Phase 1 design and plan must be amended and reaccepted explicitly.

### `Phase1AcceptanceReceiptSnapshot`

Provides the exact Phase 1 application commit or build, schema revision, acceptance-suite and fixture-corpus versions, successful run ID, result and result fingerprint, current restore high-water mark, reviewer or actor, and completion time. It is a verified local acceptance artifact, not a Phase 2 assertion. Any Phase 1 restore requires a new four-source import, readiness confirmation, full acceptance run, receipt, and Phase 2 activation grant before live work resumes.

### `Phase1ReadinessSnapshot`

- Contract version.
- `ready_for_phase_2` state.
- Exact four-entry curated-source manifest version.
- Latest committed import-run ID, each source's current hash, successful read and parse state, and full four-source completeness.
- Confirmation that no newer committed or in-progress attempt supersedes the reported state.
- Active search-profile version.
- Phase 1 application build, schema revision, and current restore generation.
- ABA-safe monotonic readiness generation and authority high-water mark.
- Counts and reason codes for any remaining blockers.
- Snapshot fingerprint and creation time.

### `SearchProfileSnapshot`

- Exact profile version and immutable payload.
- Eligible roles and priority domains.
- Eligible locations and both allocation dimensions.
- Compensation floors and their basis.
- Sponsorship requirements.
- Excluded employers and role profiles.
- Notice period and level constraints.
- Creation time and profile fingerprint.
- ABA-safe monotonic active-profile generation.

### `MatchingRequirementQuery`

Phase 2 sends server-generated atomic requirement IDs plus bounded, non-instructional semantic predicates from a versioned taxonomy: component, modality, capability or responsibility IDs, domain IDs, technical-object IDs, outcome or scale IDs, role-profile ID, employer or subject constraints, and applicable period needs. Raw listing prose and free-form instructions are not passed to the fact service. Unknown taxonomy values fail closed for high confidence and readiness. Requirement count and category breadth are capped so a hostile listing cannot cause bulk fact enumeration.

### `MatchingFactSetSnapshot`

Phase 1 performs relevance selection inside its service boundary and returns one complete, ordered, non-pageable set for the bounded query. The snapshot records the query fingerprint, selection-policy version, query-specific candidate-universe count, examined count, selected fact IDs, omission reason counts, full eligible-set generation, structural and semantic completeness states, creation time, short expiry, and whole-set fingerprint. A cap, incomplete examination, truncation, or semantic-unknown result blocks high confidence, publication, and readiness.

The versioned retrieval policy uses the locked role, capability, responsibility, technical, outcome, and domain taxonomies plus controlled synonym expansion. Before implementation it is frozen against an adjudicated retrieval corpus. Every scoring-relevant fixture permits zero relevant omissions, whether its job requirement is required, a material responsibility, or preferred. Retrieval is exhaustive over the purpose-eligible taxonomy partitions identified by the bounded query. Any scoring-relevant omission makes the snapshot `semantically_incomplete`; Phase 2 must not publish one current score or band, cross a shortlist or readiness threshold, or send a fact-bearing mapping packet. It may show only a clearly bounded `needs_assessment` interval based on known evidence, with no current rank or authority. Phase 2 cannot enumerate the vault or perform a second local search over unrelated eligible facts.

Each returned fact reference contains:

- Claim ID and exact active revision ID.
- Approved or corrected factual state.
- Active support state.
- Normal sensitivity state.
- Category and subject.
- Employer and applicable period when required.
- Safe display wording.
- Immutable support kind (`documentary` or `explicit_user_confirmation`) and support-event ID.
- Evidence reference identifiers when documentary support exists.
- Eligibility version and fingerprint.

Phase 1 returns a matching fact only when it is approved or corrected, supported, current, non-confidential, correctly attributed, and free of an open conflict. Phase 2 cannot request confidential matching facts, and a confidential-use permission does not change this rule.

### `FactDisclosureAuthorization`

Phase 2 first canonicalizes the exact final fact-bearing evidence-mapping packet in memory and calculates its digest. Phase 1 does not read or authenticate the Phase 2 activation grant; the Phase 2 coordinator validates its own grant, while Phase 1 validates only its own readiness, profile, restore, authority, fact-set, revision, and support generations.

Immediately before synchronous standard-input handoff, Phase 1 revalidates those generations and appends a durable, one-use `FactDisclosureAuthorization` event inside its mutation coordination boundary. The event is bound to the final packet digest, packet ID and nonce, purpose, job revision, selected location path, coverage ledger, profile and readiness generations, complete fact-set fingerprint, rubric, interpreter configuration, response schema, recipient path, and expiry. This event is also copied to the Phase 1 owner-only recovery ledger so a restored Phase 1 store cannot forget a disclosure boundary; if the accepted Phase 1 recovery interface cannot append this event, a reviewed Phase 1 contract amendment is required before the mapping stage can operate.

The durable authorization event is the conservative disclosure boundary: the packet is considered disclosed at authorization even if the following child-process handoff fails. Phase 2 must attempt synchronous stdin delivery immediately, may not queue or reuse the packet, and records `delivered`, `failed_before_delivery`, `indeterminate`, or `validated_response` without altering the Phase 1 event. A fact decision made after this authorization cannot retroactively erase the event. It does cause the response-acceptance recheck to fail, so the response is discarded and cannot be published, displayed as current, used for readiness, or handed onward.

### `InterpreterPacketAuthorization`

Phase 2 durably authorizes each exact interpreter packet in its own recovery ledger before handoff. The record binds packet kind, digest, ID, nonce, job revision, selected location path when applicable, Phase 1 and Phase 2 restore generations, activation generation, policy and schema versions, recipient mode, expiry, and one-use state. Extraction requires this Phase 2 authorization. Evidence mapping requires both this authorization and the matching Phase 1 `FactDisclosureAuthorization`. Authorization, delivery, response validation, denial, expiry, and orphan cleanup are append-only events; a restored store cannot make an old packet reusable.

### `FactEligibilityCheck`

Before an assessment is displayed, shortlisted, or handed to a later phase, Phase 2 asks Phase 1 whether the whole eligible-set generation and every referenced exact revision remain eligible for matching. This catches additions as well as removal, rejection, staleness, support loss, attribution changes, and sensitivity changes. A denial or unavailable check invalidates the assessment immediately.

If the implemented Phase 1 interface differs from these approved concepts, the Phase 2 design and plan must be reviewed before coding. The implementation must not silently substitute direct database access.

## Main Phase 2 records

### Provider definition and approval

A provider definition records:

- Stable provider ID and version.
- Provider kind and friendly name.
- Access method and official documentation reference.
- Allowed hosts and endpoint pattern.
- Whether login, credentials, or browser assistance is required.
- Expected coverage and known limitations.
- Request-rate policy.
- Approval state and append-only approval events.
- Health state and last successful check.

Approval occurs at two levels. Adapter-type approval covers the Greenhouse or Lever protocol. Provider-instance approval separately covers one exact ATS tenant or employer board, official employer identity, hosts, endpoint pattern, redirect allowlist, credential scope, access terms, and data scope. An approved adapter cannot access an unapproved tenant.

Greenhouse and Lever public-board adapter types are approved by this design, but live access remains disabled until the Phase 1 gate passes. Every employer board or official endpoint still requires its own versioned approval event before access. Any new provider type requires a plain-language explanation and explicit approval before activation.

### Discovery run

A discovery run records:

- Stable run ID and state.
- Manual start time and completion time.
- Phase 1 readiness fingerprint and active search-profile version.
- Planned search effort by location and difficulty.
- Each provider attempt, result count, and final status.
- Successful, partial, failed, aborted, or invalidated outcome.
- Coverage summary and warnings.
- Job and assessment counts.
- Publication state and history.
- Activation generation, Phase 1 restore generation, and Phase 2 run-fencing generation.

Attempts and outcomes are immutable. Retrying creates a new attempt or run rather than overwriting the failed record.

Only one discovery run may be active. Provider observations are staged under its run-fencing generation and merge into the catalog only when expected provider, job, activation, profile, and restore generations still match.

### Source listing

A source observation keeps:

- Provider and source-listing identifier.
- Retrieval and observation times.
- Original employer, title, location, compensation, sponsorship text, description, and URL.
- Content fingerprint and safe response metadata.
- Official-versus-lead classification.
- Parsing state and warnings.

Original wording is retained as inert text. It is never executed or rendered as active source HTML.

Immutable audit metadata is stored separately from purgeable source content. Audit history retains hashes, source IDs, timestamps, reason codes, and cited-span IDs; the full response and description payload follow the retention rules below.

### Job record and revision

A canonical job record contains:

- Stable job ID.
- Canonical employer and employer-review reference.
- Original and normalized title.
- Original and normalized eligible locations.
- All original locations, including non-target locations that distinguish otherwise similar requisitions.
- Work arrangement and employment type when stated.
- Official requisition ID and canonical official URL when known.
- Source references.
- First-seen and last-checked times.
- Current lifecycle state.

Each material job revision contains the exact description, compensation, sponsorship, location, title, application deadline, source verification, content fingerprint, and observation time used for its assessment.

Each target location mentioned or explicitly permitted receives a separate `LocationEligibilityPath` containing the applicable profile location, official location evidence, work arrangement, compensation comparison, sponsorship rule, and current state. A path result is `pass`, `conditional`, or `fail`: every location-level hard gate must pass for `pass`; no location-level hard gate may fail and at least one unresolved warning must exist for `conditional`; any location-level hard failure makes that path `fail`. Job-wide gates such as employer exclusion, eligible role, downgrade, live status, and role-profile evidence are evaluated once and veto every path when they fail. The job's location result is `eligible` when at least one path passes, `conditional` when none passes but at least one is conditional, and `ineligible` only when every path fails. Match Score can be shared when the role content is identical, but shortlist display names every viable path and readiness is always bound to one exact passing selected path. A path-specific failure never contaminates another path, and values from different paths may not be combined.

### Employer review

Employer approval is independent of provider approval. Identity records distinguish hiring employer, legal entity, trading name, end client when disclosed, ATS tenant, and verified domains. Review states are `unreviewed`, `identity_uncertain`, `approved`, `rejected`, `excluded`, and `quarantined`; every state has evidence, actor, reason, expected version, expiry or recheck time, and append-only history.

An unfamiliar employer can be scored and shown in the full list with `employer_needs_review`. It may enter the focused shortlist only after exclusion-identity clearance proves it is not JPMorganChase or an unresolved hiring entity. It cannot become ready for drafting until fully approved. Employer approval never overrides JPMorganChase or any other locked gate.

### Employer risk assessment

Employer risk is separate from employer approval and Match Score. Versioned states are `not_assessed`, `no_known_concern`, `review_recommended`, and `blocked`. The assessment records only evidence-backed operational signals such as unverifiable identity, mismatched or unsafe domains, undisclosed staffing or end-client relationships, requests for payment, or confirmed fraud warnings. `No_known_concern` is not an endorsement of the employer. `Blocked` excludes the job; `review_recommended` blocks future-drafting readiness; the state expires or reopens when identity or evidence changes.

Employer state consequences are fixed:

| Employer state | Full list | Focused shortlist | Future drafting |
|---|---|---|---|
| Unreviewed but exclusion identity cleared | Show with warning | Allowed if other rules pass | Blocked |
| Identity uncertain | Show as conditional | Blocked | Blocked |
| Approved | Allowed | Allowed | Continue to risk check |
| Rejected, excluded, or quarantined | Rejection history only | Blocked | Blocked |
| Risk not assessed | Show with warning | Allowed if identity is cleared | Blocked |
| Risk `review_recommended` | Show with warning | Allowed with warning | Blocked |
| Risk `blocked` | Rejection history only | Blocked | Blocked |
| Current risk `no_known_concern` | Allowed | Allowed | Passes this check only |

`No_known_concern` requires verified employer identity and domains, no request for applicant payment, no unsafe domain mismatch, no unresolved staffing or end-client relationship, and no confirmed fraud evidence in the approved review inputs. It expires after 90 days or immediately on identity, domain, provider, end-client, or warning change.

The table is applied as two independent inputs with one fixed precedence: first, any `rejected`, `excluded`, or `quarantined` approval state or `blocked` risk state sends the record to rejection history and blocks shortlist and drafting. Second, `identity_uncertain` blocks shortlist and drafting. Third, all other combinations use the most restrictive remaining consequence from the approval row and risk row. Drafting therefore requires approval `approved` and current risk `no_known_concern`; shortlist may allow an exclusion-cleared `unreviewed` employer with `not_assessed` or `review_recommended` risk and a warning. No permissive row overrides a stricter row.

### Eligibility assessment

Eligibility is recorded in two linked stages. `JobGateAssessment` evaluates job and profile information such as employer identity, role taxonomy, location paths, compensation, sponsorship, live status, and semantic gate uncertainty. `EvidenceClearanceAssessment` runs only after requirement extraction and the complete matching fact-set snapshot; it evaluates Principal scope, Applied-AI domain connection, Technical-PM overlap, and required evidence.

Every gate result is `pass`, `fail`, or `unknown`. Objectively testable gates use fixed rules. Semantic gates such as delivery-only ownership, substantial downgrade, management-heavy scope, or deep-AI infrastructure use constrained classification and require recorded human review when the result could be a hard failure. A potentially failing `unknown` cannot enter the focused shortlist.

Together the assessments record the job revision, location path, search-profile version, every gate result, warning code, source or Phase 1 evidence, decision version, and time. They distinguish:

- `ineligible`: failed a locked hard gate.
- `conditional`: no hard failure, but one or more required facts need verification.
- `eligible`: hard gates and required verification checks passed.

A conditional official job may be scored and shortlisted when otherwise strong. It cannot become ready for drafting.

### Match assessment

A match assessment records:

- Exact job revision.
- Exact search-profile version.
- Exact Phase 1 fact-revision references.
- Scoring-rubric version.
- Interpreter version and restricted-packet fingerprint.
- Seven component results and total.
- Requirement-to-evidence mappings.
- Gaps and warning codes.
- Confidence and confidence reasons.
- Complete matching-fact-set generation and fingerprint.
- Requirement-coverage-ledger fingerprint.
- Creation time, supersession, and invalidation state.

Earlier assessments are immutable. Reassessment creates a new record and preserves the previous one.

## Discovery sources and approval rules

The first working source strategy is reliability-first:

- `greenhouse_public_board`: public Greenhouse job-board feeds.
- `lever_public_board`: public Lever job-board feeds.
- `official_page_read_only`: approved official employer career pages using a provider-instance-specific parser and containment policy.
- `manual_official_url_read_only`: manually supplied official HTTPS job URLs, fetched only after exact host and instance approval.

These four adapter types are authorized by this design but disabled until the Phase 1 and instance-level gates pass. Every parser, host, tenant, board, and redirect scope remains separately versioned and approved.

LinkedIn, Naukri, Google Jobs, and Indeed may later provide leads only through an explicitly approved browser-assisted process. Their observations do not qualify as official verification. A lead must resolve to a current official employer listing before entering the focused shortlist.

Adzuna remains disabled unless Varun separately approves and configures it. Paid or restricted providers require a new design decision.

A newly discovered provider cannot activate itself. Activation requires a versioned adapter definition and a separate provider-instance definition, safe access review, clear explanation, Varun's confirmation, and append-only events.

Every run reports source coverage honestly. A failed source does not stop healthy sources, and results from a partial run are visibly marked as partial.

Reliability-first feeds cover known boards; they do not define the whole market. The initial discovery universe therefore begins as an empty inventory and is populated only with employer boards and official sites Varun approves after Phase 1 acceptance. Each inventory version records included employers, provider instances, known scope, unsupported coverage, and change history. Employer examples in the profile assessment are not automatically added. `Market supply` means current official jobs observable within this approved universe, not the entire employment market.

## Search-effort planning

Each standard run has exactly 100 logical search-effort units with this locked joint location-by-difficulty matrix:

| Location | Direct fit | Stretch | Aspirational | Total |
|---|---:|---:|---:|---:|
| Hyderabad | 20 | 14 | 6 | 40 |
| Bengaluru | 22 | 16 | 7 | 45 |
| Singapore | 8 | 5 | 2 | 15 |
| **Total** | **50** | **35** | **15** | **100** |

The cockpit reports planned, attempted, completed, and covered effort for one fixed reporting window: the four most recently published terminal standard runs, ordered by run completion time and then run ID. A run enters this window only once, when its publication transaction commits. A restored, superseded, diagnostic, or never-published run is excluded. Before four such runs exist, the view shows the available runs beside the fixed target and says that the window is incomplete.

A standard run owns exactly 100 immutable units. Each unit has exactly one terminal state:

| Terminal unit state | Attempted | Completed | Covered |
|---|---:|---:|---:|
| `covered` — provider returned a complete valid response for that query | 1 | 1 | 1 |
| `completed_no_results` — complete valid response, no jobs | 1 | 1 | 1 |
| `failed_after_request` — request began but did not produce complete valid coverage | 1 | 0 | 0 |
| `unavailable_capacity` — no unique approved query/provider specification existed | 0 | 0 | 0 |
| `aborted_before_request` — explicitly stopped before provider access | 0 | 0 | 0 |

All 100 units must reach one of these terminal states before a run can publish. Recovery may move only a non-terminal unit to the truthful terminal state supported by its append-only attempt record; it cannot convert failure or unavailability into coverage.

- Location effort targets are 40% Hyderabad, 45% Bengaluru, and 15% Singapore.
- Difficulty effort targets are 50% direct fit, 35% stretch, and 15% aspirational.
- One `SearchEffortUnit` is one predeclared, canonically hashed query specification for exactly one location lane, one difficulty lane, one locked role-taxonomy lane, and one approved provider instance. Direct, stretch, and aspirational classification comes from the versioned locked-role taxonomy before execution; one query cannot receive duplicate lane credit.
- Multi-lane searches are split into separate effort units; results never count as effort.
- Within each matrix cell, capable approved provider instances are ordered by stable ID and receive unique query specifications in deterministic round-robin order. A canonical query hash cannot repeat in one run. If the approved universe cannot supply enough unique specifications, remaining units are `unavailable_capacity` rather than fabricated work.
- An adapter may batch several logical units into one transport request, but each unit retains its own query hash and coverage outcome.
- Planned, attempted, completed, and covered units are reported separately from resulting jobs.
- A failed or post-request aborted unit becomes `failed_after_request`; a pre-request abort becomes `aborted_before_request`.
- Custom diagnostic or single-provider runs are reported but never enter the four-run allocation view.
- Effort is summed from the immutable terminal-unit rows inside the fixed window. A unit is never carried forward, reassigned to another cell, or counted twice after retry; a retry is part of that unit's attempt history until the unit reaches one terminal state.
- Provider failures do not cause the system to claim that missing coverage was achieved.
- Scarce market supply is reported and never repaired by changing scores or thresholds.

The Phase 2 user starts runs manually. Tuesday scheduling, catch-up behavior, and notifications remain Phase 4 work.

## Normalization and deduplication

The standardizer preserves original values and produces separate normalized values under a versioned policy. It defines Unicode normalization, case and whitespace handling, HTML-to-text conversion, title qualifiers, employer-alias authority, location ontology, URL host/path normalization, removal of tracking parameters and fragments, retained identity parameters, and description-similarity algorithm and threshold. Ambiguous normalization remains unknown and cannot support automatic merge or a hard gate.

Before duplicate linking, every observation receives a `PostingIdentityKey` from the strongest available pre-link identity: verified ATS tenant plus requisition ID; otherwise canonical official employer domain plus canonical official URL; otherwise source instance plus source listing ID as an observation-only key. The key also carries hiring entity and business unit when known. A source-only key can group revisions from that source but can never merge providers.

Posting generation is then derived within that pre-link key:

- A continuously live requisition with requirement, pay, location, or deadline changes remains one posting generation with new revisions.
- A closed or expired posting later observed live creates a new generation.
- A requisition ID or evergreen URL observed again after a 30-day verified absence creates a new generation.
- A changed requisition ID, hiring entity, business unit, or materially different role identity creates a new generation.
- A deadline extension while continuously live is a revision; an extension after expiry is a reopening and new generation.

Duplicate decisions link already generated posting identities using the strongest available identity in this order:

1. Same verified ATS tenant or official employer domain, requisition ID, and posting generation.
2. Same canonical official URL, overlapping live period, and posting generation.
3. Same canonical employer, normalized title, full original location set, and substantially identical description fingerprint creates only a `possible_duplicate`; it never auto-merges.

A source-specific listing ID alone cannot merge jobs from different providers. Similar titles or boilerplate descriptions are insufficient. When signals conflict, verified hiring entity and ATS tenant outrank URL, URL outranks fuzzy content, and any unresolved higher-priority conflict forbids automatic linking. Requisition IDs and URLs reused after closure, a material rewrite, or a configured reopen interval create a new posting generation.

Combining confirmed duplicates creates a reversible, versioned identity link; it does not destructively move or delete observations. All sources, discovery times, and links remain intact. The official employer source is preferred for current job content, while other sources remain provenance. An audited split operation can remove a mistaken link, reassign derived views, and invalidate affected assessments.

Material changes create a new job revision and invalidate earlier assessments. Material fields include employer identity, title, location, work arrangement, description requirements, compensation, sponsorship, requisition status, and deadline. Presentation-only changes do not create a false new job.

## Job lifecycle and retention

Lifecycle uses independent dimensions rather than one overloaded state:

- Availability: `observed_live`, `expired`, `closed`, or `unknown`.
- Verification: `official_current`, `lead_only`, or `needs_verification`.
- Revision processing: `current` or `changed_needs_assessment`.
- Duplicate review: `unique`, `possible_duplicate`, or `linked_duplicate`.
- Catalog state: `active` or `archived`.
- Saved state: `saved` or `not_saved`.
- Dismissal state: `dismissed` or `not_dismissed`.
- Shortlist membership: a computed current result, never a stored lifecycle substitute.

The legal-state validator enforces these invariants: `official_current` requires `observed_live`; `expired` or `closed` cannot be `official_current`; `linked_duplicate` cannot itself be shortlisted; `archived` cannot be shortlisted; `dismissed` cannot be shortlisted; and current shortlist membership requires `active`, `not_dismissed`, `observed_live`, `official_current`, and revision processing `current`. `Saved` may coexist with dismissed, archived, closed, expired, or possible-duplicate records because saving is a user bookmark, not eligibility. Any combination not admitted by these rules is rejected rather than silently normalized.

Every transition records trigger evidence, source observation, policy version, expected prior state, time, and any superseded transition. A closed or expired job can reopen only through a new official observation and posting-generation decision.

Transport success is not feed completeness. Each adapter defines a versioned completeness proof covering tenant and board scope, filters, pagination or cursors, page counts, and invariants. Absence closes a job only after two consecutive complete observations at least 24 hours apart plus a current direct official-URL check, unless the job-specific official page explicitly states that it is closed. Contradictory official evidence keeps availability unknown.

Freshness is displayed separately from Match Score. Official verification for the focused shortlist expires after seven days or an earlier adapter-specific limit. Future-drafting readiness requires an official observation no older than 24 hours, and Phase 3 must recheck again immediately before use. Expired verification automatically becomes `needs_verification`; provider failure never extends it.

Leads and jobs needing verification remain searchable but cannot enter the focused shortlist or become ready for drafting.

Retention is exhaustive. `Selected` means currently saved, currently shortlisted, or linked to a later-phase application record. While selected, no purge clock runs. When the last selection reason ends, one `unselected_at` timestamp is set to that latest event. For a job never selected it is the latest official observation; for a closed or expired never-selected job it is the later of that observation and closure/expiry confirmation; for a duplicate it is the later of the observation and duplicate decision. Later review or reassessment can move `unselected_at` forward only where the table explicitly names that event. A new official observation, save, shortlist selection, or application link cancels the running clock. When several rows appear to apply, the row with the latest permitted `unselected_at` controls, but no row can retain purgeable content beyond 30 days after that controlling time unless the job becomes selected again.

| Record state | Full-content retention |
|---|---|
| Current saved, current shortlist, or later-phase application link | Retain while selected |
| Active full-list job never selected | Purge 30 days after its last official observation unless refreshed |
| Dismissed or unsaved job | Purge 30 days after the latest dismissal or unsave |
| Former shortlist job | Purge 30 days after shortlist removal unless saved |
| Reviewed or assessed but unselected exploratory job | Purge 30 days after its latest review or assessment |
| Resolved or unresolved possible duplicate not otherwise selected | Purge 30 days after latest duplicate decision or observation |
| Closed or expired job not otherwise selected | Purge 30 days after closure or expiry confirmation |
| Submitted opportunity | Preserve under later pipeline-retention rules |

All source copies and revisions for a purged unselected job follow the same clock. An assessment whose full listing is retired retains only job and source IDs, hashes, cited requirement spans, coded mappings, score, and decision history; it is marked `content_retired` and cannot be displayed as current or handed off.

The Phase 2 recovery ledger carries retention tombstones across restore. Backup rotation removes expired Phase 2 content after a new clean verified backup exists; restore cannot make tombstoned content active again.

## Eligibility evaluation

Job-only hard gates are applied before Match Score. Evidence-dependent profile predicates are applied after requirement extraction and a complete matching-fact-set snapshot. Both stages must complete before a job becomes eligible.

### Hard failures

- Employer is JPMorganChase or a confirmed hiring entity of JPMorgan Chase.
- No location path qualifies under the locked location and remote-work rule.
- Singapore sponsorship is explicitly unavailable for the selected Singapore path.
- Entire clearly comparable disclosed compensation range is below the applicable floor for a location path.
- Job does not positively match any locked eligible role profile.
- Role is a locked excluded category.
- Role is a substantial level downgrade.
- Official listing is closed or expired.
- Explicit non-negotiable joining time is shorter than the locked 60-day notice period.
- A selected Principal role lacks approved Principal-scope evidence.
- An Applied AI role lacks approved connection to an existing locked domain.
- A Senior Technical Product Manager role lacks approved technical or locked-domain overlap.

### Conditional warnings

- Compensation missing or ambiguous.
- Compensation range crosses the floor.
- Singapore sponsorship unknown.
- Employer not reviewed.
- Lead or Principal individual-contributor status unclear.
- Product Owner scope unclear.
- Required start timing may conflict with the 60-day notice period.
- An explicit minimum job requirement has no approved evidence.
- Job is live but description quality makes a requirement uncertain.
- A semantic gate that could be a hard failure remains unknown.
- Employer or end-client identity cannot yet be cleared against the JPMorganChase exclusion.

Warnings do not add or subtract Match Score. A potentially failing semantic-gate unknown also blocks the focused shortlist. Every other warning has the typed resolution requirements below and blocks future-drafting readiness until resolved.

Hard failures remain visible in a concise rejection history with source, profile version, rule, reason, and time. Keeping or saving a rejected job does not turn it into an eligible match.

### Typed warning resolution

Acknowledging a warning or adding a free-form note never changes a factual field from unknown to verified.

| Warning | Evidence that may clear it | Recheck rule |
|---|---|---|
| Compensation | Current official listing or admissible dated written employer/recruiter confirmation that states currency, period, components, and applicable location | Official observation expires under source freshness; written confirmation after 30 days or on listing change |
| Singapore sponsorship | Current official employer statement or admissible dated written employer/recruiter confirmation for the exact role or hiring path | Official observation expires under source freshness; written confirmation after 30 days or on listing change |
| Employer identity/exclusion | Verified official domains, legal or hiring entity, ATS tenant, and end-client disclosure when applicable | Reopen on domain, tenant, or relationship change |
| Employer approval | Varun's recorded decision after identity clearance and risk review | Reopen on identity or material risk change |
| Role or IC scope | Current official description or dated employer/recruiter clarification; Varun may adjudicate subjective scope with cited source text and a reason | Reopen on material job change |
| Notice timing | Admissible dated written employer/recruiter confirmation accepting the 60-day period | Expires after 30 days or on listing change; recheck before readiness |
| Location path | Current official listing or admissible dated employer/recruiter confirmation of employment from the exact target country/location | Official observation expires under source freshness; written confirmation after 30 days or on listing change |
| Unsupported requirement | A newly eligible Phase 1 fact, or official clarification that the clause is not required | Recompute the requirement ledger and score |
| Employer risk | Verified identity evidence and resolution of the exact risk signals that caused review or block | Expires after 90 days or immediately on identity, domain, end-client, provider, or warning change |

Every resolution stores the exact observation or Phase 1 decision ID, source class, verifier, actor, policy version, time, expiry or recheck trigger, and supersession history. A user acknowledgement alone can organize work but cannot clear readiness.

An admissible written-confirmation observation records sender identity and relationship, original message or document hash and protected local locator, capture method, date, exact role and requisition, applicable employer and location path, quoted factual field, authenticity review, actor, and redacted display summary. A typed transcription or user attestation without the original evidence remains a note and cannot clear a factual warning. Written confirmations stay local and are excluded from scoring packets.

For Indian `annual_total`, the versioned comparison formula includes fixed or base annual cash plus explicitly guaranteed recurring cash components for the applicable year. Discretionary bonus, equity, joining payment, retention payment, deferred compensation, benefits valuation, and unguaranteed incentives are itemized but excluded from automatic floor proof. This design does not invent a new basis: it consumes the exact basis in the active Phase 1 profile snapshot. If that snapshot does not return `annual_total` for an Indian location, automatic comparison is blocked; Phase 2 must not infer it, and changing it requires a new locked profile version.

## Requirement extraction

Before external interpretation, a trusted local segmenter assigns an immutable span ID and hash to every heading, paragraph, table row, and list item in the official job description. A separate public-job-only extraction stage then splits each span into atomic candidate-facing clauses.

Atomic clauses preserve:

- `AND` requirements as separate required clauses.
- `OR` alternatives as one alternative group satisfied only by an allowed member.
- Mixed required and preferred wording as separate modalities.
- Minimum years, counts, degree alternatives, and other numeric constraints without dilution.
- Exact source span, offsets, and normalized clause hash.

The logical model is deliberately shallow and deterministic:

- An `AND` produces separate top-level scoring nodes; each receives its own atomic requirement ID and weight.
- An `OR` produces one scoring node with one group ID and two or more member IDs. The group receives one modality, one importance weight, and one primary component, so it enters one denominator exactly once.
- All `OR` members must express alternatives for the same candidate-facing outcome and primary component. If alternatives appear to span components, the group is paused for human assignment of the one outcome/component; it cannot be scored automatically.
- Each `OR` member is mapped separately. The group result is the strongest member result under `direct > adjacent > none`; ties select the lowest canonical member ID for the cited winning member, while other same-strength mappings remain non-crediting corroboration. The group's contribution is therefore at most its one declared weight.
- Duplicate alternatives collapse by normalized clause hash before member IDs are assigned. Nested `OR`, an `OR` inside an `AND` member, or any other nesting beyond one alternative group is unsupported and requires human normalization into this model.
- Numeric alternatives retain their own unit and threshold inside each member; the winning member must satisfy its own comparison rule.

Every candidate-facing clause becomes exactly one atomic requirement or receives an adjudicated `non_requirement` or `gate_only` result. Duplicated clauses link to one requirement and do not add weight. Unclassified clauses reject the assessment.

Modality follows locked precedence:

1. Explicit `must`, `required`, `minimum`, or required-qualifications wording becomes `required`.
2. Explicit job duties, ownership, or `you will` wording becomes `material_responsibility` unless the text clearly makes it optional.
3. Explicit `preferred`, `nice to have`, or equivalent wording becomes `preferred`.
4. Conflicting or unclear modality becomes `uncertain` and requires recorded review; the interpreter cannot choose its scoring weight.

Every scoring requirement receives exactly one primary component from this initial mapping table:

| Primary component | Requirement meaning |
|---|---|
| Role and seniority fit | Level, title, years, IC versus people management, breadth of ownership, reporting scope |
| Relevant domain experience | Industry, customer problem, regulated context, product domain |
| Product responsibilities and problem fit | Discovery, roadmap, prioritization, delivery ownership, lifecycle and product decisions |
| Outcomes, scale, and operating complexity | KPI ownership, commercial or adoption outcomes, scale, regulation, operational complexity |
| Technical, platform, data, and integration fit | APIs, platforms, data, analytics, AI, integrations, systems and technical trade-offs |
| Strategy, influence, and leadership fit | Strategy, executive influence, cross-functional leadership, mentoring and organizational scope |
| Other required and preferred qualifications | Education, certifications, tools, languages, or explicit qualifications not owned above |

Location, compensation, sponsorship, notice timing, employment type, employer identity, and application conditions are `gate_only` and never receive score weight. An ambiguous primary component requires human review. A secondary component may be recorded only for a distinct named aspect and never receives additional requirement weight.

The resulting `RequirementCoverageLedger` proves every source span and atomic clause was handled, retains exact references and logical structure, and records modality and primary component provenance. An uncertain clause that could contain a gate or required qualification blocks the focused shortlist and readiness; other uncertainty blocks high confidence.

Requirements used for hard gates are evaluated by fixed rules and conservative review states. The extraction interpreter may propose clause structure, controlled taxonomy IDs, modality, and component, but trusted validation and human review own every ambiguous decision.

## Restricted scoring packet and interpreter path

The approved interpreter path uses a fresh, non-interactive Codex CLI `exec` session authenticated through Varun's existing ChatGPT/Codex access. No separately billed model API is authorized by this design. The official command reference documents non-interactive `codex exec`, read-only sandbox selection, prompts through standard input, and JSON Schema output validation: [OpenAI Codex developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

Every automated stage uses a new non-resumed session in a newly created owner-only temporary directory. Read-only Codex sandboxing alone is not treated as proof of isolation. A versioned execution capability matrix and an OS-level wrapper must be proven in acceptance to:

- Use read-only sandboxing.
- Allow data reads only from the ephemeral packet and response schema. The minimum runtime may also read the exact executable, signed runtime libraries, certificate store, and dedicated owner-only Codex authentication/configuration files named in the approved capability matrix. It must deny the project workspace, home documents, Phase 1 and Phase 2 stores and backups, logs, other temporary directories, shell history, skills, plugins, connectors, and unrelated configuration.
- Disable live web search, browser or computer use, MCP servers, connectors, plugins, skills, and workspace-file discovery.
- Deny shell and file actions not required for schema-validated response production.
- Accept the prompt only through standard input and validate the final output against the exact JSON Schema.
- Avoid conversation resume, shared project context, and cross-job memory.
- Restrict network egress to the exact authenticated Codex service endpoints required by the approved client; DNS and every connection are checked against the allowlist, and no provider or arbitrary web origin is permitted.

The capability matrix names each control, whether Codex CLI, its permission profile, the macOS wrapper, or the cockpit enforces it, and the acceptance probe that disproves unsafe access. Client-side non-resumption is testable; the document does not claim that it proves external-service deletion or absence of provider-side retention.

Interpretation mode is explicit and versioned. `codex_restricted` uses the approved automated path and must pass every containment and egress probe. `local_manual` sends nothing externally: the cockpit shows one public clause or one requirement plus the already authorized eligible fact references, and Varun records only allowed taxonomy IDs, modality, component, directness, and reason code through constrained controls. Manual input passes the same coverage, packet-equivalent authorization ledger, mapping validation, calculator, instability comparison, and audit rules; free-form facts and score entry are not allowed. If the installed Codex version, managed configuration, or OS wrapper cannot enforce the matrix, `codex_restricted` remains disabled and `local_manual` is the only mode. The activation screen records the exact mode and, for Codex, the version, profile and wrapper fingerprints, model/configuration identifier, schema version, relevant OpenAI workspace data controls, Varun's consent, and validation result.

The external service may retain data according to Varun's current OpenAI workspace settings; the cockpit cannot promise retroactive deletion from that service. This limitation is disclosed before enabling the interpreter. Locally, raw packets and raw responses are deleted after validated import, while hashes and audit metadata remain.

Interpretation uses two separate fresh sessions and two packet schemas:

1. `RequirementExtractionPacket` contains only public job spans, controlled taxonomies, clause and modality rules, activation and interpreter configuration, nonce, expiry, and a closed extraction response schema. It contains no Phase 1 facts. The Phase 2 coordinator validates the activation grant, records the exact `InterpreterPacketAuthorization`, performs synchronous stdin handoff, validates every returned span offset and clause, assigns final local requirement IDs, and records the coverage ledger.
2. `EvidenceMappingPacket` contains only the validated atomic requirements, scoring-rubric rules needed for directness, relevant eligible Phase 1 fact revisions, stable opaque identifiers, bounded enums, and a closed mapping response schema. It requires an exact Phase 2 `InterpreterPacketAuthorization` and the Phase 1 `FactDisclosureAuthorization` for the same final digest.

Both packets use separate IDs, nonces, one-use records, sessions, output schemas, audit outcomes, timeouts, and cleanup. A response from one stage cannot be accepted by the other.

The packet excludes:

- Confidential facts, even when another use has permission.
- Unresolved, rejected, stale, unsupported, superseded, or wrongly attributed facts.
- Contact details and personal identifiers.
- Current compensation and unrelated personal information.
- Source documents or facts irrelevant to the job.
- Credentials, tokens, cookies, local paths, and database details.

Each packet uses a strict allowlist serializer. It rejects prohibited values at every nested level before fingerprinting or dispatch. It contains a random packet ID and nonce, issue and monotonic-expiry times, maximum size and item counts, exact activation and restore generations, and one-use state. The extraction packet is bound to one public job revision and extraction-policy version. The mapping packet is bound to one job revision, selected location path, profile version, rubric version, coverage-ledger fingerprint, and complete fact-set fingerprint.

Packet acceptance atomically consumes the unique packet ID and nonce. Exact duplicate responses are recognized as replay, while an explicitly created retry receives a new packet ID linked to the earlier attempt. Returned mappings with unknown identifiers, changed fingerprints, expired packets, nested unexpected content, or unexpected fields are rejected.

The extraction interpreter returns only source span IDs, offsets, normalized atomic clauses, logical-group structure, proposed controlled taxonomy IDs, modality enums, component enums, and closed reason codes. The mapping interpreter returns exactly one `RequirementEvidenceResult` per atomic scoring requirement: the requirement ID, zero or more permitted supporting fact-revision IDs, one final `direct`, `adjacent`, or `none` result, and a closed mapping-reason code. `None` requires zero supporting fact IDs. Multiple facts provide corroboration but never add credit; the strongest single valid mapping determines directness, and adjacent facts cannot combine into direct evidence.

Neither interpreter can return candidate-fact prose, score values, component anchors, explanations, gaps, confidence text, or new source content. Trusted local templates generate user-facing explanations from current Phase 1 wording and coded requirement and component results, so model-authored prose cannot preserve or strengthen a fact that later becomes confidential.

Owner-only temporary directories are excluded from backup and indexing. Packet and raw-response files are removed in `finally` handling for success, schema failure, timeout, cancellation, child-process failure, and restore interruption. Startup scans for orphaned packet directories from crashes or forced termination and retires them before serving requests; only bounded non-sensitive forensic metadata remains.

## Evidence-led 100-point Match Score

The seven components are:

| Component | Maximum |
|---|---:|
| Role and seniority fit | 20 |
| Relevant domain experience | 20 |
| Product responsibilities and problem fit | 20 |
| Outcomes, scale, and operating complexity | 15 |
| Technical, platform, data, and integration fit | 10 |
| Strategy, influence, and leadership fit | 10 |
| Other required and preferred qualifications | 5 |
| **Total** | **100** |

Location, compensation, sponsorship, freshness, employer approval, source verification, notice-period compatibility, confidence, and employer risk are not score components.

### Fixed scoring anchors

To reduce interpretation drift, components use discrete evidence anchors:

- A 20-point component may award 0, 5, 10, 15, or 20.
- The 15-point component may award 0, 4, 8, 12, or 15.
- A 10-point component may award 0, 3, 5, 8, or 10.
- The 5-point component may award 0, 1, 3, 4, or 5.

Across all components, anchors mean:

- `none`: no approved evidence found for the material requirement.
- `adjacent`: transferable evidence with a meaningful gap.
- `partial`: several relevant responsibilities or requirements are supported, but important gaps remain.
- `strong`: most material expectations have direct approved support.
- `close`: unusually close, direct, and well-supported fit across the component.

The interpreter does not choose an anchor. It proposes only requirement-to-fact mappings and directness enums. The fixed calculator derives each anchor as follows:

1. Every component requirement receives a fixed importance weight from the coverage ledger: required qualification `3`, material responsibility `2`, and preferred qualification `1`.
2. Each atomic requirement has exactly one final evidence result. Direct contributes `1.0` of its weight, adjacent contributes `0.5`, and none contributes `0`. Multiple supporting facts never increase contribution beyond that one requirement weight.
3. Component coverage is the contributed weight divided by all applicable requirement weight.
4. With exact rational comparison and no pre-comparison rounding, coverage `0` maps to `none`; `(0, 0.35)` maps to `adjacent`; `[0.35, 0.65)` maps to `partial`; `[0.65, 0.85)` maps to `strong`; and `[0.85, 1]` maps to `close`.
5. A component with no applicable requirement has denominator zero, receives zero points with `not_assessable`, and never redistributes its weight. A role-critical empty component blocks readiness and lowers confidence.
6. `Close` additionally requires no unsupported required requirement and direct evidence for at least two distinct atomic requirements. When only one requirement applies, the component is capped at `strong`. An unsupported required requirement caps the component at `partial` and blocks readiness.

For scoring, an `OR` group is one atomic scoring requirement even though its alternatives have member IDs. Its single group result, weight, primary component, gap state, and winning-member citation are used in steps 1–6.

The rubric freezes this closed evidence-result truth table; an interpreter-proposed label is accepted only when the trusted local validator can prove the named predicate from packet IDs and typed values:

| Result and reason code | Required predicate |
|---|---|
| `direct/exact_capability_performed` | Fact and requirement share the same approved capability or responsibility taxonomy ID, and the fact records Varun performing or owning the required work at the required ownership level. |
| `direct/exact_domain_experience` | Fact has the exact required locked-domain ID and the required experience relation. |
| `direct/exact_technical_object_used` | Fact records actual work with the exact technical-object ID or a taxonomy-declared equivalent frozen in the rubric. |
| `direct/numeric_minimum_met` | Comparable fact value, unit, attribution period, and scope are present and value is at least the requirement minimum. |
| `direct/outcome_or_scale_met` | Comparable approved outcome or scale value is at least the stated threshold, or the requirement has no numeric threshold and the exact outcome/scale taxonomy ID matches. |
| `adjacent/same_capability_lower_ownership` | Same capability ID, but the fact shows contribution where the requirement explicitly asks for ownership. |
| `adjacent/approved_taxonomy_neighbor` | Fact ID is connected to the requirement ID by exactly one frozen, directional adjacency edge in the relevant capability, domain, or technical-object taxonomy; no exact match exists. |
| `adjacent/numeric_near_minimum` | Comparable value is at least 75% but below 100% of a stated years/count minimum. |
| `adjacent/scale_near_minimum` | Comparable outcome/scale value is at least 50% but below 100% of the stated threshold. |
| `none/no_approved_evidence_found` | No eligible fact satisfies any direct or adjacent predicate. |
| `none/incomparable_or_ambiguous` | Unit, period, attribution, ownership, taxonomy relation, production status, or scope cannot be validated deterministically. |

Exact matches take precedence over adjacent matches. Numeric rules take precedence when the requirement states a minimum. A fact from another employer or period is allowed only when the job requirement does not constrain employer or period; otherwise it is `none/incomparable_or_ambiguous`. Coursework, learning, or prototypes cannot satisfy `actual work` or `production` predicates. No unlisted reason code is accepted, and an ambiguous case becomes `none/incomparable_or_ambiguous` plus low confidence or adjudication rather than an invented mapping.

The scoring-rubric version owns requirement-to-component rules, importance precedence, direct-versus-adjacent reason codes, aggregation, caps, and thresholds. A requirement mapped to multiple components keeps one primary component; secondary use is allowed only for a different explicitly named aspect and receives no duplicate requirement weight.

The fixed calculator validates coverage-ledger completeness, mapping identifiers, attribution, allowed reason codes, importance, caps, and arithmetic. The interpreter cannot award points, change a maximum, or decide a score band.

### Role-profile critical floors

An aggregate total cannot compensate for a missing role-critical capability. Future-drafting readiness requires:

- Role and seniority fit of at least `strong`.
- Product responsibilities and problem fit of at least `strong`.
- Every component containing a required qualification to be above `none`, with no unsupported required requirement anywhere.
- Senior Technical Product Manager: technical, platform, data, and integration fit of at least `strong`, plus the approved overlap predicate.
- Selected Principal Product Manager: strategy, influence, and leadership fit of at least `strong`, plus the approved Principal-scope predicate.
- Applied AI Product Manager: relevant domain fit of at least `strong`, technical fit of at least `partial`, and no representation of learning or prototypes as production experience.

These floors affect readiness, not the displayed total. They are shown as separate reasons when a high aggregate score is not ready.

### Evidence rules

For every requirement and every non-zero component, the assessment must retain:

- Exact job-requirement references.
- Zero or more exact eligible Phase 1 claim and revision references; `none` has zero references.
- A requirement-level mapping result and reason code (`direct`, `adjacent`, or `none`).
- A separately calculator-derived component anchor and anchor reason (`none`, `adjacent`, `partial`, `strong`, or `close`).
- Plain-language gaps.

Repeated wording does not earn repeated credit. The same fact may support different components only when it genuinely supports distinct aspects, and each use must be explained. Coursework, learning, or prototypes cannot be described as production AI experience. Missing evidence is written as `no_approved_evidence_found`, not as a claim that Varun lacks the capability.

Every required clause without approved evidence is displayed prominently and blocks future-drafting readiness until resolved, even when the overall score is high. Evidence validity is a score-validity invariant: an invalid, unknown, or semantically unverified mapping rejects the assessment rather than lowering confidence.

### Score bands

- Raw 85–100: numerically strong.
- Raw 70–84: numerically worthwhile.
- Raw 55–69: numerically exploratory.
- Raw below 55: numerically weak.

The UI also shows exactly one `QualifiedMatchBand`, assigned by this ordered and exhaustive decision table. `Meaningful role and responsibility evidence` means both Role and Seniority and Product Responsibilities are at least `adjacent`. `Worthwhile structure` means the positive role gate and role-profile predicates pass, both those components are at least `partial`, and no applicable role-profile critical floor fails except solely because of an unsupported required clause.

| First matching rule | Qualified band |
|---|---|
| Raw score below 55, or meaningful role and responsibility evidence is absent | `weak` |
| Raw score below 70, or worthwhile structure fails | `exploratory` |
| One or more required clauses lack evidence | `worthwhile_with_required_gap` |
| Raw score at least 85 and every universal and role-specific critical floor passes | `strong` |
| Otherwise | `worthwhile` |

This order makes the bands mutually exclusive and total for every valid assessment. A non-required critical-floor failure is caught by failed worthwhile structure and therefore produces `exploratory`, even with a high raw score. A required gap can produce `worthwhile_with_required_gap` only after every other worthwhile-structure predicate passes.

The focused shortlist uses the qualified band, not raw total alone. A raw 85+ assessment with a failed critical floor remains exploratory or worthwhile-with-gap and is never labelled strong.

Thresholds are versioned and cannot be lowered to fill a weekly list.

## Confidence and interpretation stability

Confidence describes assessment quality, not Varun's ability. It is resolved from closed reason codes in severity order:

| Highest present reason severity | Confidence |
|---|---|
| Any of `unofficial_or_stale_source`, `coverage_ledger_incomplete`, `fact_set_incomplete`, `gate_clause_uncertain`, `required_clause_uncertain`, `material_responsibility_uncertain`, `mapping_predicate_unvalidated`, `parse_or_schema_failure`, `assessment_instability`, or `current_generation_unavailable` | `low` |
| None above, and at least one of `preferred_clause_uncertain`, `preferred_mapping_none_due_ambiguity`, or `preferred_taxonomy_adjudication_pending` | `medium` |
| No confidence reason code | `high` |

All official spans must be processed and all non-preferred requirements and mappings must be determinate before `medium` is possible. Unknown or unlisted reason codes resolve to `low`.

Low confidence blocks future-drafting readiness. Medium confidence may permit readiness only when its uncertainty is limited to non-material preferred criteria; it cannot contain a gate, required, material-responsibility, evidence-validity, location-path, compensation, sponsorship, employer, or timing ambiguity. An interpretation failure produces `needs_assessment`, never a default or estimated score.

Assessment stability states are `stable`, `unstable_pending_review`, `adjudicated`, and `superseded`. One latest non-superseded assessment is current for each exact input and active scoring-policy generation.

An existing stable assessment is reused when job revision, location path, profile, eligible fact-set, coverage ledger, rubric, interpreter configuration, and packet fingerprint are unchanged. A forced reassessment of identical inputs is unstable if its clause ledger, modalities, primary components, fact retrieval set, mappings, directness, gaps, component anchors, score band, shortlist state, or readiness outcome changes—even when the point total does not.

Any instability atomically invalidates current shortlist publication, readiness decisions, and unconsumed capabilities for that job. Adjudication records the compared assessments, exact disputed clauses or mappings, Varun's source-grounded decision, actor, reason, policy version, and a new canonical assessment; the others become superseded. A scoring-rubric, extraction-policy, retrieval-policy, or interpreter-policy change creates a new active-scoring-policy generation and invalidates older current authority.

For medium-confidence preferred uncertainty, the calculator computes a deterministic lower bound: every unresolved preferred atomic requirement or unresolved `OR` group remains in its original component denominator with its full importance weight and receives contribution zero; all resolved requirements keep their validated contribution. The calculator then reapplies the normal rational thresholds, caps, band table, and critical floors without redistributing weight. Readiness requires this lower-bound score to remain at least 85, its qualified band to be `strong`, and every critical floor to pass. The displayed score is the lower bound until adjudication; no optimistic midpoint is shown. Boundary cases at 69/70 and 84/85 require recorded adjudication when independent results disagree; no automatic transition is allowed.

## Focused shortlist and full list

The focused shortlist contains up to 20 jobs that:

- Are in catalog state `active` and dismissal state `not_dismissed`.
- Are live on an official employer source.
- Have official verification within the current seven-day freshness policy.
- Pass all hard gates.
- Have exclusion identity cleared, including JPMorganChase hiring-entity review.
- Have no potentially failing semantic gate left unknown.
- Have a raw score of at least 70 and a qualified band of `strong`, `worthwhile`, or `worthwhile_with_required_gap`.
- Have the latest non-superseded stable or adjudicated assessment under the active scoring-policy generation.

Conditional jobs may appear with prominent warnings. An unfamiliar employer, unknown compensation, or unknown Singapore sponsorship does not hide an otherwise strong job.

The shortlist order is:

1. Match Score descending.
2. Confidence, with higher confidence first.
3. Most recent official verification.
4. Discovery time, newest first, when earlier factors are equal.
5. Stable job ID ascending as the final deterministic tie-break.

These ordering rules do not change Match Score.

When the market supplies fewer than 10 qualifying jobs, the cockpit shows fewer and explains why. It never lowers the threshold or introduces hard-gate failures. When more than 20 qualify, the remainder stay searchable in the full list.

The full list contains eligible and conditional discoveries, exploratory matches, weak matches, and leads awaiting official verification. Rejected jobs default to a concise rejection history and remain available through an explicit filter.

Dismissed jobs leave the active focused shortlist without changing their immutable score or rank. Saved jobs remain visible in a saved view and retain their score-based order. `All discoveries` includes optional filters for dismissed, archived, and rejected records; the rejection history is the default compact view rather than the only way to find them.

## Future-drafting readiness

Phase 2 does not draft documents. It may create an immutable `FutureDraftReadinessDecision` only when all of these are true:

- Match Score is at least 85.
- Qualified Match Band is `strong`.
- Confidence is high or medium.
- Job is live and officially verified.
- Official verification is no older than 24 hours.
- One exact target `LocationEligibilityPath` has been selected and passes its location, compensation, work-arrangement, and sponsorship rules.
- Compensation is verified, comparable, and acceptable.
- Singapore sponsorship is confirmed when applicable.
- Employer is approved.
- Role scope is resolved.
- No explicit minimum requirement remains unsupported.
- No notice-period timing conflict remains unresolved.
- Search-profile version is still active.
- Every referenced Phase 1 fact revision remains eligible for matching.
- No job change has invalidated the assessment.
- Assessment is the latest non-superseded stable or adjudicated result under the active scoring-policy generation.
- Every applicable role-profile critical floor passes.
- Employer risk is `no_known_concern` and current.

The readiness decision contains every predicate and the exact supporting provider observation, job revision, location path, compensation verification, sponsorship confirmation, employer identity and approval, employer-risk assessment, role-scope decision, notice decision, requirement ledger, assessment, rubric, activation generation, Phase 1 readiness and profile generations, whole fact-set fingerprint, fact revision and support IDs, policy versions, timestamps, and combined fingerprint.

The decision expires when its 24-hour official verification expires or any referenced generation changes. Phase 3 cannot consume a stale boolean. It requests a short-lived, one-use, purpose-bound readiness capability for the exact document use; Phase 2 and Phase 1 revalidate every identifier before issuance and Phase 3 rechecks it on consumption. A Phase 2 readiness decision is not permission to invent a claim or use confidential evidence.

## User experience

Phase 2 extends the minimalist local browser experience approved for Phase 1.

### Discovery home

Shows Phase 1 readiness, Phase 2 activation state, last completed run, source health, coverage, and one primary next action.

### Focused shortlist

Shows up to 20 jobs with score, score band, difficulty lane, location, freshness, confidence, and clear warning labels. It avoids dense analytics and makes the next review action obvious.

### All discoveries

Supports plain-language filters for location, difficulty, score band, employer review, compensation, sponsorship, freshness, confidence, source, saved state, and lifecycle state.

### Job details

Shows original official information, source history, eligibility decisions, seven component explanations, exact approved evidence references rendered through Phase 1, gaps, warnings, confidence reasons, and assessment history.

### Sources and employers

Shows adapter approval, provider-instance approval, transport health, feed completeness, employer identity, employer approval, and employer risk as separate concepts. A change requires confirmation, reason, expected version, supporting evidence where factual, and append-only history.

### Run history

Shows planned and attempted search effort, actual source coverage, provider failures, jobs found, duplicates combined, assessments completed, invalidations, and publication state.

### User actions

Varun may save, dismiss, request reassessment, review an employer, acknowledge a warning, or submit the typed evidence required to resolve one. Dismissal reasons affect presentation only and never silently change the search profile, scoring weights, or immutable score. A factual correction requires the source class specified in the warning-resolution matrix and creates a new verified observation with source, actor, reason, and history; it never overwrites source text. Acknowledgement alone never clears readiness.

## Information flow

1. Varun opens the local cockpit.
2. Phase 2 checks Phase 1 acceptance, readiness, compatibility, and activation.
3. Varun starts a manual standard or diagnostic discovery run.
4. The activation grant is revalidated, and the run captures the exact Phase 1 readiness, restore, and search-profile generations.
5. The effort planner creates location and difficulty query lanes.
6. Approved providers return inert source observations.
7. The standardizer creates or updates job revisions.
8. The duplicate checker combines only reliable identities and flags uncertainty.
9. The lifecycle checker verifies availability, official status, freshness, duplicate state, and revision-processing state.
10. The job-only gate evaluator excludes objective hard failures and records semantic unknowns.
11. A fresh public-job-only extraction packet creates proposed atomic clauses; trusted validation and review create the complete requirement-coverage ledger.
12. Phase 1 returns one complete, purpose-bound matching fact-set snapshot.
13. The evidence-clearance evaluator applies role-profile predicates and required-evidence gates.
14. Phase 2 canonicalizes the final mapping packet; Phase 1 records a one-use fact-disclosure authorization for its exact digest.
15. The fact-bearing mapping packet is delivered synchronously through the locked-down Codex CLI path.
16. The fixed calculator derives anchors and calculates the total from validated mappings.
17. Confidence and future-drafting readiness are evaluated separately.
18. Before publication, Phase 2 rechecks activation, Phase 1 generations, the whole fact set, and every referenced decision.
19. A valid run publishes the focused shortlist and full list; an incompatible run is invalidated.
20. Every view and later handoff rechecks current generations, fact eligibility, job revision, and readiness inputs.

## Concurrency, history, backup, and restore

- Only one discovery run may be active at a time.
- Provider, employer, verification, save, dismissal, and reassessment changes are serialized inside the Phase 2 store.
- A run uses immutable Phase 1 input snapshots and revalidates before publication.
- Concurrent profile or fact changes cannot silently publish a stale assessment.
- Phase 2 decisions and assessments are append-only or superseding; they are not rewritten in place.
- A verified safety copy is created before risky Phase 2 data changes and schema upgrades.
- A Phase 2 owner-only external hash-chained recovery ledger records activation grants and suspensions; provider and employer approvals or revocations; employer-risk changes; interpreter-packet authorization, delivery, denial, expiry, cleanup, and indeterminate outcomes; future-draft capability issue, consuming, denial, delivery, and indeterminate outcomes; security events; assessment invalidations; retention tombstones; backup and restore events; and run-fencing generations. Capability consumption and every terminal transition are append-only and survive restore. Phase 1's separate ledger owns fact-disclosure and future-draft-snapshot authorization events because Phase 1 owns the disclosed facts.
- Restore quiesces requests, cancels and fences active runs, closes connections, verifies and installs the backup safely, rotates the run and restore generations, replays later authoritative recovery-ledger events, and keeps Phase 2 disabled until cross-store compatibility is confirmed.
- After a Phase 2 restore, every external-world observation and factual warning resolution—live status, compensation, sponsorship, location, notice, employer identity, and role clarification—is stale regardless of its earlier TTL and must be refetched or reconfirmed before new authority is calculated.
- After either store is restored, compatibility and references are rechecked before Phase 2 resumes. A restored database cannot reactivate a revoked provider, approval, readiness decision, or retired content.
- A Phase 1 restore that removes or changes referenced revisions invalidates affected assessments without deleting their historical record.

## Security and privacy

- Phase 2 remains bound to `127.0.0.1` and uses the Phase 1 launch-session protections.
- Its database, backups, and operational logs use owner-only permissions and remain outside Git.
- Provider credentials, if later required, use macOS Keychain.
- Logs never contain credentials, tokens, cookies, career-fact wording, restricted scoring packets, or unnecessary description text.
- Browser responses remain non-cacheable, imported text is escaped, and unapproved origins are rejected.
- Job HTML is never rendered as active source content.
- Live source retrieval is restricted to approved HTTPS hosts and safe redirects. A non-HTTPS manual link may be displayed as unverified text but is never fetched.
- Live provider retrieval requires HTTPS. Every DNS resolution and redirect hop is revalidated against private, loopback, link-local, multicast, reserved, and unsupported IPv4 and IPv6 ranges; redirects are capped and must remain inside the approved instance allowlist.
- Local-file URLs, unsafe schemes, unexpected content types, oversized responses, and sensitive query parameters are rejected. Authorization headers and credentials never cross a redirect boundary.
- External job links use `Referrer-Policy: no-referrer` and `rel="noopener noreferrer"`; the launch token never remains in a browser URL.
- Provider access uses documented public feeds or explicitly approved browser assistance, honors sensible rate limits, and does not silently bypass login or access controls.
- Demographic information, age, gender, photographs, and unrelated personal details never influence matching.
- Singapore sponsorship is evaluated only as a practical eligibility requirement from the locked profile.

## Hostile-listing protection

Job descriptions and source metadata are untrusted data. Embedded text cannot:

- Change gates, weights, thresholds, or allocations.
- Approve a provider or employer.
- Self-authorize a compensation, sponsorship, location, or live-status decision.
- Change a Phase 1 fact.
- Request additional private facts.
- Activate a tool, browser action, file action, download, or application step.
- Tell the interpreter to ignore cockpit rules.

Unexpected instruction-like text is ignored and may be recorded as suspicious content. The interpreter returns only the approved structured schema, and unknown fields or identifiers cause rejection.

Validated factual fields from an approved official observation may support fixed parsing and verification rules. The source text supplies evidence; it never approves the source, chooses the rule, or clears a warning by instruction alone.

Before packet creation, source text is normalized conservatively and checked for control characters, encoded or fragmented instruction patterns, excessive repetition, hidden Unicode, oversize clause counts, and multilingual instruction-like content. Suspicious content is quarantined for review rather than trusted automatically. Returned direct or adjacent mappings must cite packet-issued source spans and fact IDs and pass semantic reason-code validation; schema validity alone is insufficient.

Browser-assisted discovery, if separately approved later, is read-only extraction on registered origins. It cannot download files, submit forms, follow listing-directed actions, navigate outside the approved origin chain, export credentials, or reuse extracted text as browser instructions. Each provider instance requires runtime containment tests before enablement.

## Failure handling

- A provider failure is isolated and creates an honest coverage warning.
- A partial run cannot claim complete coverage.
- A failed or interrupted run never replaces the last published results.
- An unreadable listing remains an unscored lead with a plain-language reason.
- A parsing or interpretation failure never creates a guessed score.
- An ambiguous location, compensation, sponsorship, role scope, or deadline remains unknown or conditional.
- A changed source observation creates a new revision rather than silently changing an assessment.
- A changed Phase 1 snapshot invalidates publication and requires recalculation.
- Phase 1 timeout, malformed response, unavailable check, or contract-version mismatch denies provider access, packet dispatch, publication, evidence display, shortlist validity, readiness, and later-phase handoff. Cached results remain historical only.
- When current Phase 1 checks are unavailable, a redacted historical view may show public job metadata, old numeric score, invalidation reason, and audit IDs. It cannot show career evidence, current match explanations, current shortlist status, or any actionable readiness state.
- Unsafe response content or redirect is rejected without following it.
- Rate limiting or temporary blocking pauses only the affected provider.
- A second simultaneous publication attempt is rejected or queued safely.
- An unexpected error is logged with operational identifiers and redacted details.

## Versioned interfaces for later phases

Phase 2 will expose versioned application services rather than database access.

### `JobRecordView`

Provides the canonical job, exact current revision, source references, lifecycle, and safe public listing fields.

### `MatchAssessmentView`

Provides total and component scores, requirement references, current eligible evidence references, gaps, confidence, rubric version, and invalidation state.

### `FutureDraftReadinessView`

Provides the immutable readiness-decision ID, allowed or denied result, exact selected location path, every supporting decision and observation ID, activation and restore generations, exact job revision, assessment ID, profile version, whole fact-set fingerprint, fact and support references, expiry, and explicit denial reasons. A separate one-use capability is required for a Phase 3 handoff.

### `IssueFutureDraftCapability`

Accepts the readiness-decision ID, exact Phase 3 document-attempt ID, purpose enum, audience, expected versions, and actor confirmation. It revalidates every readiness input and returns a signed, short-lived capability bound to that one attempt, selected location path, job revision, assessment, fact set, activation and both stores' restore generations, issue time, expiry, and nonce. It contains no career wording. Issuance and denial are append-only events.

### `ConsumeFutureDraftCapability`

Accepts the exact capability and document-attempt ID through a fixed two-store protocol:

1. Phase 2 atomically moves the nonce from `issued` to `consuming`, records the attempt, and revalidates every Phase 2 input. From this point the capability can never return to `issued`.
2. Phase 1 receives the capability digest and exact bound identifiers. Inside its mutation coordinator it revalidates readiness, profile, restore, full eligible-set, fact revisions, support, sensitivity, conflict, and audience/purpose policy; constructs the exact `FutureDraftSnapshot`; records a one-use `FutureDraftSnapshotAuthorization` bound to its digest; and synchronously delivers that snapshot to the named local Phase 3 attempt before releasing the coordinator.
3. Phase 2 records only the terminal outcome: `delivered`, `denied_before_authorization`, or `indeterminate_after_authorization`. `Authorized` is an append-only Phase 1 event, not a retryable Phase 2 state. A crash, timeout, cancellation, or uncertain result after authorization burns the capability and returns no retryable career evidence. A new attempt requires a new readiness decision recheck and capability.

The `FutureDraftSnapshot` schema is fixed and purpose-minimized: snapshot ID and digest; purpose and audience; job, revision, selected location path, assessment, readiness-decision and document-attempt IDs; Phase 1 profile/readiness/restore/authority generations; Phase 2 activation/restore/policy generations; expiry; and an ordered list of career projections. Each projection contains only opaque claim and exact revision IDs, approved current safe wording, employer and period when needed for truthful attribution, support kind and support-event ID, and the exact requirement or document purpose it may support. It excludes confidential or otherwise ineligible facts, source-document content, personal contact details, current compensation, unrelated facts, local paths, and free-form model text. Phase 1, not Phase 2, creates this career-fact projection at consumption. Any later need for additional facts requires a separate Phase 1 document-use contract and a newly authorized capability.

### `DiscoveryRunSummary`

Provides provider health, coverage, allocations, jobs, scores, warnings, and run provenance for private local use.

Later consumers receive purpose- and audience-specific projections. A future `SitesSafeDiscoverySummary` may contain only confirmed non-sensitive public job fields, score totals or bands approved for publication, provider-health summaries, and opaque local references. It excludes career-fact IDs and wording, private gaps, employer-review evidence, restricted packet metadata, detailed search behavior, compensation confirmation messages, and local paths unless a later design explicitly permits them.

Phase 3 and later phases must call these services and recheck versions. They cannot read Phase 2 tables directly.

## Test strategy

Automated tests use sanitized saved provider responses and synthetic Phase 1 service fixtures. They never contact live providers or read Varun's live fact vault.

### Contract tests

- Phase 1 acceptance receipt, readiness, exact four-source state, profile, requirement query, complete fact-set, dispatch authorization, support-kind, generation, and exact-revision eligibility contracts.
- Incompatible, unavailable, malformed, incomplete, paginated, stale, restored, or semantically weakened Phase 1 responses fail closed.
- Provider adapter and provider-instance inputs, outputs, tenant scope, pagination completeness, rate behavior, error mapping, and safe-host restrictions.
- Later-phase Phase 2 views and denial reasons.

### Discovery tests

- All location and difficulty effort calculations across four published runs.
- Provider success, partial failure, rate limiting, and complete failure.
- Greenhouse, Lever, official-page, and manual-link fixtures.
- Unapproved adapter types, tenants, boards, hosts, endpoints, redirects, and scopes cannot run.
- Provider failure never becomes false job closure.
- Exact 100-unit joint matrix, unique query hashes, deterministic provider distribution, batching attribution, unavailable capacity, four-run window, failed attempts, and diagnostic-run exclusion.
- Every terminal-unit row in the truth table, retry attribution, one-time publication-window entry, incomplete-window display, restore exclusion, and proof that 100 terminal units reconcile exactly.
- Versioned employer-board inventory and an honest coverage denominator.

### Normalization and lifecycle tests

- ATS tenant, requisition, posting-generation, URL, and fuzzy duplicate tiers.
- Pre-link posting identity keys, identity-precedence conflicts, generation-before-linking, and observation-only source keys that cannot merge providers.
- Ambiguous duplicates remain separate.
- Reused requisition IDs, evergreen URLs, identical boilerplate, different business units, and reopenings remain distinct when required.
- Multiple source references survive combination.
- Merge links can be split and invalidate derived assessments safely.
- Material changes create revisions and invalidate scores.
- Presentation-only changes do not create false revisions.
- Live, changed, needs-verification, expired, and closed transitions.
- Availability, verification, revision-processing, duplicate-review, catalog, saved, and dismissal transitions are independent and legal combinations are enforced.
- Every admitted lifecycle combination and every forbidden invariant, plus the single controlling `unselected_at` clock, precedence, cancellation, and 30-day maximum.
- Direct closure, two-complete-absence closure, contradictory evidence, reopen, deadline extension, and expired freshness TTL.
- Thirty-day description cleanup, cited-span retention, backup rotation, and recovery-ledger tombstones.
- Exhaustive selected and unselected retention clocks, resets, every source copy, restore staleness, and reopened posting generations.

### Eligibility tests

- Exact locked profile snapshot matches the active Phase 1 profile field by field; the current acceptance fixture is profile version 2.
- JPMorganChase and clear employer-name variations are always rejected.
- All eligible, ineligible, remote, and multi-location cases.
- Separate Hyderabad, Bengaluru, and Singapore location paths for one listing, including different floors and sponsorship outcomes.
- Global-gate veto, path-level pass/conditional/fail aggregation, one-path-pass combinations, all-path-fail combinations, and proof that evidence cannot be mixed across paths.
- Every excluded and ambiguous role category.
- Positive eligible-role gate and exact Principal, Applied-AI, and Technical-PM evidence predicates.
- Below-floor, crossing-range, above-floor, missing, wrong-basis, and ambiguous compensation.
- Singapore sponsorship confirmed, unavailable, and unknown.
- Unknown employer, role scope, notice period, and minimum requirement warnings.
- Exact 59-day, 60-day, and 61-day notice/joining boundaries, plus ambiguous and negotiable timing.
- Typed warning evidence, expiry, recheck, and proof that acknowledgement alone cannot clear readiness.
- Employer identity, hidden end-client, JPMorganChase collision and non-collision aliases, approval, and separate risk states.
- Every employer-approval and risk-state pair, using the strictest-row precedence and immutable exclusion veto.
- No single-job bypass of a locked gate.

### Scoring tests

- Seven exact component maxima and a total maximum of 100.
- Only allowed discrete anchors are accepted.
- Every job-description span is classified; unclassified and gate-relevant uncertain spans fail closed.
- Mixed-modality clauses, `AND` and `OR` groups, numeric minima, duplicate-clause dilution, exact primary component, and gate-only classification.
- Exact `AND` independence; single-weight `OR` aggregation; mixed-component alternative adjudication; numeric alternatives; duplicate alternatives; unsupported nesting rejection; and one winning-member citation.
- Importance weights, direct and adjacent contribution, coverage thresholds, caps, and fixed arithmetic cannot be changed by interpreter output.
- Every requirement and non-zero component has validated job and eligible-fact references.
- Each requirement contribution is capped at its own weight; multiple direct or adjacent supporting facts cannot inflate it.
- Exact rational anchor boundaries, zero-denominator components, and minimum breadth for `close`.
- Every direct, adjacent, and none reason-code predicate, including exact boundaries for numeric, scale, ownership, taxonomy-neighbor, domain, period, employer, production, and ambiguous cases.
- Duplicate wording does not earn duplicate points.
- Coursework and prototypes are not treated as production experience.
- Missing evidence is not rewritten as a negative fact.
- Score bands and focused-shortlist threshold never lower automatically.
- Qualified-band precedence, mutual exclusivity, and exhaustiveness for every legal combination of raw band, role/product anchors, required gaps, positive-role predicates, and critical-floor results.
- Confidence and readiness checks remain separate from Match Score.
- Confidence reason-code severity and deterministic preferred-uncertainty lower bounds, including threshold-crossing mutations.
- Independently adjudicated golden outputs for direct-fit, stretch, aspirational, misleading-title, sparse-description, and near-miss cases. Each golden record fixes expected span classifications, requirements, mappings, anchors, gaps, confidence, warnings, score band, shortlist state, and readiness outcome.
- Adversarial omitted-must-have, double-credit, wrong-employer, wrong-period, critical-zero-component, newly approved relevant fact, and forbidden-fact fixtures.
- Exact 69/70 and 84/85 boundary fixtures and mutation tests proving each defect changes the expected outcome.
- Repeated reference assessments may not change an anchor, score band, shortlist state, or readiness outcome and also stay within five total points and two component points.
- Same-anchor clause, modality, retrieval, mapping, directness, or gap churn produces instability and invalidates prior readiness.
- Active scoring-policy changes invalidate older current assessments, decisions, and capabilities.

### Fact-safety tests

- Unresolved, rejected, stale, unsupported, superseded, confidential, and wrongly attributed facts are excluded from packets and mappings.
- A confidential permission for another use does not permit Phase 2 use.
- Contact details and unrelated personal information are excluded.
- A Phase 1 sensitivity or support change invalidates the assessment and redacts its evidence display.
- A profile change or restore invalidates incompatible runs and assessments.
- A newly approved relevant fact changes the whole fact-set generation and invalidates an older assessment even when it referenced none of the new fact's IDs.
- Every scoring-relevant fixture has zero retrieval omissions; any single omitted preferred, material, required, or critical fact produces `semantically_incomplete`, a bounded non-authoritative interval, and no published score, band, rank, shortlist, or readiness decision.

### Security tests

- Prompt-like instructions in job descriptions cannot affect rules or actions.
- Script and HTML content renders only as text.
- Unsafe schemes, local files, internal-network targets, redirect chains, oversized bodies, and unexpected content types are rejected.
- Strict allowlist serialization rejects every prohibited packet field—including personal identifiers, current compensation, source documents, credentials, tokens, cookies, local paths, database details, and nested unexpected content—before dispatch.
- Packet replay, concurrent duplicate response, expiry, wrong nonce, wrong job revision, wrong location path, wrong profile or activation generation, wrong coverage or fact fingerprint, and unknown returned IDs are rejected.
- Dedicated Codex profile validation proves a fresh non-resumed session, empty temporary context, read-only sandbox, exact runtime/config read allowlist, service-endpoint egress allowlist, disabled search/tools/connectors/plugins/skills, exact schema output, and denial of workspace, home-document, store, backup, log, and unrelated-file access before interpreter activation.
- Separate extraction and evidence-mapping packets cannot be confused, replayed, or cross-accepted.
- Both packet kinds require their exact Phase 2 authorization; mapping additionally requires the matching Phase 1 authorization. Restore, authorization-without-delivery, post-authorization mutation, and response-acceptance recheck fixtures fail closed as specified.
- Timeout, schema failure, cancellation, child crash, application kill, restore, and startup orphan cleanup retire all raw packet material.
- Credentials and sensitive content do not appear in logs or Git.
- Local session, CSRF, Host, Origin, caching, framing, and file-permission protections remain effective.

### User-flow tests

- Phase 2 remains visibly disabled before Phase 1 acceptance and explicit enablement.
- A complete manual run produces source health, a focused shortlist, and a full list.
- `local_manual` extraction and mapping use the same closed controls, authorization history, validator, calculator, instability comparison, and output as frozen automated responses, without external dispatch or free-form facts/scores.
- Conditional jobs display exact warnings and cannot become ready for drafting.
- Saving, dismissal, employer review, warning resolution, and reassessment preserve history.
- A mid-run Phase 1 change prevents publication.
- A changed job invalidates its prior assessment.
- Phase 2 restore makes every external observation and factual warning resolution stale even when an earlier TTL had time remaining.
- Dismissal removes presentation from the active shortlist without changing score; saved and rejected filters behave as documented.
- Readiness capability issue, audience binding, expiry, mismatch, `issued`-to-`consuming` transition, Phase 1 snapshot construction under mutation coordination, delivery, denial, indeterminate terminal state, replay denial, invalidation, and new-attempt requirements.
- No action generates a document or starts an application.
- Primary screens remain keyboard accessible and readable at narrow, medium, and wide browser sizes.

Before implementation, at least two independent reviewers freeze the end-to-end golden corpus from raw synthetic job descriptions and a synthetic eligible fact vault. Disagreements and Varun's final policy decision are recorded before code uses the corpus. It contains at least 30 jobs, more than 20 independently labelled qualifying 70+ jobs, and below-threshold and hard-gap decoys. Every record fixes atomic clauses, logical groups, modality, primary component, retrieval ground truth, mappings, anchors, raw and qualified bands, warnings, confidence, shortlist state, and readiness outcome.

Acceptance separates two gates. The deterministic pipeline gate injects frozen, schema-valid extraction and mapping responses and requires exact output for every intermediate value and the final ordered shortlist. It freezes expected job IDs in order, verification and discovery timestamps, dismissal and catalog states, stable-ID tie-breaks, and explicit rank-20/rank-21 ties. The automated-interpreter qualification gate runs each reference packet three times in fresh restricted sessions. All three outputs must be schema-valid and identical on clauses, modalities, components, logical groups, mapping results, and reason codes; any disagreement disables `codex_restricted` until adjudication and a new policy/configuration qualification. Live interpreter output is never used as the exact deterministic test oracle.

After fixture acceptance and only after Phase 1 acceptance plus provider-instance approval, each enabled live instance receives a separately authorized read-only smoke check. It records schema compatibility, official identity, tenant and board scope, pagination completeness, safe redirects, rate behavior, and redacted provenance. A failed smoke check leaves that instance disabled.

## Acceptance criteria

Phase 2 is complete only when all of the following are demonstrated after Phase 1 acceptance:

1. The implementation plan may be written and approved now, but no plan task may be executed before Varun accepts the completed Phase 1 acceptance receipt.
2. Runtime Phase 2 cannot activate before Phase 1 implementation, acceptance, exact four-source readiness, compatibility, and Varun's confirmation. The first executable Phase 2 task proves the adapter contract; every other task stays blocked until it passes.
3. Activation is revalidated and fails closed before every live access, packet, publication, current evidence or actionable-result display, and handoff; only the defined redacted historical view remains available when checks fail. Either store's restore invalidates the old activation grant, and a Phase 2 restore requires a new one.
4. No automated acceptance test contacts a live provider or reads Varun's real fact vault.
5. Every locked role, domain, location, allocation, compensation floor and basis, exclusion, notice period, and JPMorganChase exclusion matches the active Phase 1 profile snapshot field by field; the current acceptance fixture is profile version 2.
6. A job must positively match an eligible role profile; an aspirational lane cannot admit unrelated roles.
7. Principal, Applied-AI, and Technical-PM evidence predicates work exactly as specified.
8. Search allocations use the exact terminal-unit truth table and fixed four-published-run window and guide effort without changing scores, thresholds, or shortlist composition.
9. The approved employer-board inventory defines observable coverage without claiming to represent the whole market.
10. Greenhouse, Lever, and official-page fixtures degrade independently.
11. Neither a new adapter type nor a new provider instance can activate without exact approval.
12. Each enabled live provider instance passes a separately authorized read-only smoke check after Phase 1 acceptance.
13. Unfamiliar employers remain visible in the full list and cannot bypass JPMorganChase identity clearance, employer approval, or employer-risk review.
14. Original active listing wording and source provenance remain inert; retired content follows the explicit 30-day and backup-retention policy.
15. Posting generation is derived from a pre-link identity key; reliable duplicate links preserve every source and can be split; fuzzy matches and source-only keys never auto-merge across providers.
16. Material job changes create revisions and invalidate assessments.
17. Transport success and feed completeness remain separate; provider failure or one incomplete absence never closes a listing.
18. Focused-shortlist verification expires after at most seven days; future-drafting verification expires after 24 hours.
19. Only an official, current listing with exclusion identity cleared, no potentially failing semantic-gate unknown, a raw score of at least 70, and an allowed qualified band enters the focused shortlist.
20. The shortlist contains at most 20 active, non-dismissed jobs and never lowers its threshold to fill a target.
21. Missing compensation stays unknown, is clearly flagged, and blocks future drafting.
22. A compensation range crossing the floor stays conditional; a range entirely below the applicable floor fails that location path.
23. Compensation components and confidence are recorded separately and speculative components cannot prove a floor.
24. Unknown Singapore sponsorship stays conditional for that location path; unavailable sponsorship fails that path.
25. Multi-location jobs use the fixed global-veto and per-path aggregation rules, never mix path evidence, and readiness identifies one exact passing path.
26. Remote work passes only with explicit target-city or target-country employment eligibility; region-only wording remains conditional.
27. Every job-description span and atomic candidate-facing clause appears in a complete coverage ledger with logical structure, modality, and primary component; unclassified or gate-relevant uncertain clauses fail closed.
28. All seven score components use the approved weights, deterministic `AND` and single-weight `OR` aggregation, closed directness predicates, fixed anchors, total qualified-band table, and critical-component floors.
29. Every requirement points to exact job wording; every direct or adjacent requirement result and non-zero score component points to eligible Phase 1 evidence, while `none` carries no invented fact reference.
30. Required gaps, invalid mappings, and critical component gaps cannot be hidden by a high aggregate score.
31. Confidential facts never influence Phase 2, regardless of other permissions.
32. Unapproved, unsupported, stale, rejected, unresolved, superseded, or wrongly attributed career facts never influence Phase 2.
33. A whole matching-fact-set fingerprint invalidates old assessments when relevant eligible facts are added or removed; any scoring-relevant omission makes the set incomplete and prevents a published score, band, rank, shortlist, or readiness decision.
34. Codex receives only a one-use public extraction packet or a separately authorized one-use fact-bearing mapping packet through the validated fresh-session restricted path; both require exact Phase 2 authorization and mapping also requires exact Phase 1 disclosure authorization. If isolation cannot be enforced, the closed-control `local_manual` mode remains available.
35. Interpreter output contains only permitted IDs and enums and cannot change gates, weights, arithmetic, approvals, facts, prose, or application state.
36. Packet serialization and response validation reject every prohibited field, replay, mismatch, and hostile-content case.
37. Freshness, compensation confidence, sponsorship, employer approval, employer risk, source verification, notice compatibility, and assessment confidence remain separate from Match Score.
38. Confidence follows the closed severity table, preferred uncertainty uses the exact zero-contribution lower bound, and low-confidence, unstable, or threshold-disagreeing assessments cannot become ready for drafting.
39. A changed Phase 1 profile, fact set, fact state, support, sensitivity, activation, acceptance, policy, or restore invalidates affected work and suspends unsafe actions; Phase 2 restore makes all external-world evidence stale.
40. Typed warning resolution requires the specified evidence; acknowledgement or a free-form note cannot manufacture verification.
41. An 85+ score alone is insufficient; an immutable readiness decision must bind every exact supporting observation, decision, generation, policy, and expiry.
42. Phase 3 can proceed only through the fixed one-use protocol in which Phase 1 constructs, authorizes, and synchronously delivers the exact minimized snapshot under its mutation coordinator; denial or any indeterminate post-authorization result returns no retryable career evidence.
43. Provider, employer, risk, run, job, eligibility, score, packet, readiness, retention, restore, and user-decision histories survive through append-only or superseding records.
44. Unsafe listing content, URLs, DNS results, redirects, responses, browser-assisted actions, and packet results are rejected safely.
45. The local security, recovery ledger, backup, restore, fencing, and permission controls remain effective for the Phase 2 store.
46. In the frozen, independently adjudicated corpus of at least 30 jobs and more than 20 qualifying 70+ jobs plus decoys, the deterministic pipeline returns the frozen ordered top 20 and every exact intermediate result without threshold changes. The automated interpreter separately passes three-run agreement qualification or remains disabled. Live operation reports how many worthwhile jobs the approved universe actually supplies and never promises market-wide coverage.
47. Phase 2 never generates documents, fills forms, or submits applications.

## Phase 2 completion output

After implementation and acceptance, Varun will have:

- A private local catalog of current, traceable job opportunities.
- Honest provider-health and discovery-coverage reporting.
- A focused shortlist and searchable full discovery list.
- Explained 100-point Match Scores grounded only in permitted evidence.
- Visible gaps, uncertainty, and readiness warnings.
- Versioned outputs that Phase 3 can consume safely after revalidation.

Phase II implementation remains constrained by this design's activation, approval, and no-live-access gates.
