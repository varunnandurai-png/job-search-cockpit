# Job Search Cockpit — Phase 2 Design

**Date:** 2026-08-20  
**Status:** Approved design; fresh QA review pending  
**Phase:** Job discovery and match scoring

## Current project status

Phase 1 has been designed and QA-hardened, but its application code has not been built. Phase 2 is therefore design-only at this point.

No Phase 2 application code may be written, no live job listing may be read or stored, and no live job provider may be contacted until Phase 1 has been implemented and accepted.

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
- Mark fully cleared 85+ jobs as `ready_for_future_drafting` for Phase 3 to consume later.

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

Phase 2 must consume the active locked search-profile version from Phase 1. Version 1 contains the following non-negotiable rules.

### Eligible locations and search effort

- Hyderabad: eligible; approximately 40% of search effort.
- Bengaluru: eligible; approximately 45% of search effort.
- Singapore: eligible; approximately 15% of search effort and requires employer-sponsored Employment Pass support.
- Other locations are outside scope unless Varun explicitly creates a new search-profile version.

The percentages govern search effort, not results, score adjustments, or shortlist quotas. They must never promote a weak job, hide a stronger job, or force the shortlist to contain an artificial mix.

A remote job qualifies only when its official listing explicitly allows work from Hyderabad, Bengaluru, Singapore, or a broader region that clearly includes at least one of those locations. A multi-location job qualifies when at least one official location is eligible.

### Role-difficulty search effort

- Direct-fit roles: approximately 50% of search effort.
- Stretch roles: approximately 35% of search effort.
- Aspirational roles: approximately 15% of search effort.

These percentages also govern search effort only. Difficulty classification is displayed separately and never changes Match Score.

### Eligible role profiles

- Senior Product Manager.
- Lead Product Manager when it is an individual-contributor role.
- Selected Principal Product Manager individual-contributor roles supported by approved evidence.
- Applied AI Product Manager roles connected to existing domain experience.
- Senior Technical Product Manager roles involving platforms, APIs, integrations, data, fintech, lending, commerce, or fulfilment.

### Priority domains

- Digital lending, mortgage, and home buying.
- Banking, fintech, risk, fraud, and relevant payments experience.
- E-commerce, fulfilment, last mile, and omnichannel products.
- Subscriptions, billing, and commerce platforms.
- Platforms, APIs, and partner integrations.
- Data, analytics, operational products, and decision support.
- Applied AI, document intelligence, workflow automation, AI-assisted compliance, enterprise agents, and intelligent automation where domain overlap exists.

### Compensation floors

- Hyderabad: ₹46 LPA minimum disclosed annual total compensation.
- Bengaluru: ₹48 LPA minimum disclosed annual total compensation.
- Singapore: S$120,000 minimum disclosed annual base compensation.

Compensation rules are:

- A listing with no compensation remains `unknown`; it is not rejected.
- A disclosed range entirely below the applicable floor is ineligible.
- A disclosed range whose lower bound is below and upper bound is at or above the floor remains eligible with `target_compensation_must_be_confirmed`.
- A clearly comparable range entirely at or above the floor passes the compensation check.
- An unclear currency, period, base-versus-total basis, guaranteed-versus-variable basis, or conversion remains `needs_compensation_check`.
- An unknown or warning-bearing compensation state blocks `ready_for_future_drafting`.
- The cockpit never guesses an undisclosed value or uses a live exchange rate to make an automatic eligibility decision.

### Exclusions and constraints

- JPMorganChase opportunities are always excluded. This includes official employer-name variations that clearly identify JPMorgan Chase or its hiring entities. There is no single-job override.
- Junior and Associate Product Manager roles are excluded.
- Generic Business Analyst roles are excluded.
- Program Manager roles without product ownership are excluded.
- People-management-heavy Director roles are excluded.
- Deep AI-infrastructure or foundation-model platform roles without relevant domain overlap are excluded.
- Roles representing a substantial level downgrade are excluded.
- Delivery-only Product Owner roles are excluded; an ambiguous Product Owner role may remain conditional when the description indicates possible strategy, discovery, outcome ownership, and exceptional scope.
- A Lead or Principal role with unclear individual-contributor status remains conditional until scope is verified.
- Notice period is 60 days. A listing with a potentially incompatible start-date requirement remains conditional and cannot become ready for drafting until reviewed.

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
6. Varun explicitly enables Phase 2 after viewing the acceptance and readiness state.

The explicit enablement records the Phase 1 application version, schema version, latest committed import-run ID, active search-profile version, readiness-report fingerprint, actor, confirmation, and time. A later Phase 1 restore or incompatible schema change suspends Phase 2 until compatibility is rechecked.

The following cannot operate before the activation gate passes:

- Provider activation.
- Live or manual-URL job ingestion.
- Discovery runs.
- Employer approval for live discovery.
- Match assessment of a real opportunity.
- Shortlist creation.
- Future-drafting readiness.

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

Phase 2 uses a separate local job-catalog database. It never reads or writes Phase 1 tables. It may call only versioned Phase 1 application services.

The two local stores are kept consistent through immutable snapshots and revalidation, not cross-database table access. A run captures Phase 1 input identifiers when it begins and rechecks them before publishing results. A mismatch prevents publication and requires recalculation.

## Phase 1 service contract consumed by Phase 2

The Phase 1 implementation must expose documented service responses equivalent to the following concepts before Phase 2 can start:

### `Phase1ReadinessSnapshot`

- Contract version.
- `ready_for_phase_2` state.
- Latest committed import-run ID and completeness.
- Active search-profile version.
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

### `MatchingFactReference`

- Claim ID and exact active revision ID.
- Approved or corrected factual state.
- Active support state.
- Normal sensitivity state.
- Category and subject.
- Employer and applicable period when required.
- Safe display wording.
- Evidence reference identifiers.
- Eligibility version and fingerprint.

Phase 1 returns a matching fact only when it is approved or corrected, supported, current, non-confidential, correctly attributed, and free of an open conflict. Phase 2 cannot request confidential matching facts, and a confidential-use permission does not change this rule.

### `FactEligibilityCheck`

Before an assessment is displayed, shortlisted, or handed to a later phase, Phase 2 asks Phase 1 whether every referenced exact revision remains eligible for matching. A denial invalidates the assessment immediately.

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

Greenhouse and Lever public-board adapter types are approved by this design, but live access remains disabled until the Phase 1 gate passes. Each employer board or official endpoint is registered before access. Any new provider type requires a plain-language explanation and explicit approval before activation.

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

Attempts and outcomes are immutable. Retrying creates a new attempt or run rather than overwriting the failed record.

### Source listing

A source observation keeps:

- Provider and source-listing identifier.
- Retrieval and observation times.
- Original employer, title, location, compensation, sponsorship text, description, and URL.
- Content fingerprint and safe response metadata.
- Official-versus-lead classification.
- Parsing state and warnings.

Original wording is retained as inert text. It is never executed or rendered as active source HTML.

### Job record and revision

A canonical job record contains:

- Stable job ID.
- Canonical employer and employer-review reference.
- Original and normalized title.
- Original and normalized eligible locations.
- Work arrangement and employment type when stated.
- Official requisition ID and canonical official URL when known.
- Source references.
- First-seen and last-checked times.
- Current lifecycle state.

Each material job revision contains the exact description, compensation, sponsorship, location, title, application deadline, source verification, content fingerprint, and observation time used for its assessment.

### Employer review

Employer approval is independent of provider approval. It records the canonical employer identity, official domains, review state, actor, reason, expected version, and append-only decision history.

An unfamiliar employer can be ranked and can appear in the focused shortlist with `employer_needs_review`. It cannot become ready for drafting. Employer approval never overrides JPMorganChase or any other locked gate.

### Eligibility assessment

The eligibility assessment records the job revision, search-profile version, every gate result, warning code, source evidence, and assessment time. It distinguishes:

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
- Creation time, supersession, and invalidation state.

Earlier assessments are immutable. Reassessment creates a new record and preserves the previous one.

## Discovery sources and approval rules

The first working source strategy is reliability-first:

- Public Greenhouse job-board feeds.
- Public Lever job-board feeds.
- Approved official employer career pages.
- Manually supplied official job URLs when useful.

LinkedIn, Naukri, Google Jobs, and Indeed may later provide leads only through an explicitly approved browser-assisted process. Their observations do not qualify as official verification. A lead must resolve to a current official employer listing before entering the focused shortlist.

Adzuna remains disabled unless Varun separately approves and configures it. Paid or restricted providers require a new design decision.

A newly discovered provider cannot activate itself. Activation requires a versioned provider definition, safe access review, clear explanation, Varun's confirmation, and an append-only event.

Every run reports source coverage honestly. A failed source does not stop healthy sources, and results from a partial run are visibly marked as partial.

## Search-effort planning

The cockpit plans query effort across the most recent four published discovery runs.

- Location effort targets are 40% Hyderabad, 45% Bengaluru, and 15% Singapore.
- Difficulty effort targets are 50% direct fit, 35% stretch, and 15% aspirational.
- A query or source slice records its intended location and difficulty lane before execution.
- Planned and attempted effort are reported separately from successful coverage and resulting jobs.
- Aborted runs do not count toward the rolling four-run target calculation.
- Provider failures do not cause the system to claim that missing coverage was achieved.
- Scarce market supply is reported and never repaired by changing scores or thresholds.

The Phase 2 user starts runs manually. Tuesday scheduling, catch-up behavior, and notifications remain Phase 4 work.

## Normalization and deduplication

The standardizer preserves original values and produces separate normalized values. Missing or ambiguous information remains unknown.

Duplicate decisions use the strongest available identity in this order:

1. Same canonical employer and official requisition ID.
2. Same canonical official job URL.
3. Same canonical employer, normalized title, eligible location set, and substantially identical description fingerprint.

A source-specific listing ID alone cannot merge jobs from different providers. Similar titles alone are insufficient. A doubtful identity becomes `possible_duplicate` for review; the system never silently combines it.

Combining confirmed duplicates preserves all source observations, discovery times, and links. The official employer source is preferred for current job content, while other sources remain provenance.

Material changes create a new job revision and invalidate earlier assessments. Material fields include employer identity, title, location, work arrangement, description requirements, compensation, sponsorship, requisition status, and deadline. Presentation-only changes do not create a false new job.

## Job lifecycle and retention

Job states are:

- `lead`: discovered but not officially verified.
- `live`: verified on a current official source.
- `changed`: a material new revision needs reassessment.
- `needs_verification`: current status cannot be established reliably.
- `expired`: a confirmed application deadline has passed.
- `closed`: an official source or healthy complete feed reliably confirms removal.

A missing observation during provider failure never closes a job. Confirmed closure may come from an official removal, a passed official deadline, or confirmed absence from a healthy provider response known to be complete for that board.

Freshness is displayed separately from Match Score. Leads and jobs needing verification remain searchable but cannot enter the focused shortlist or become ready for drafting.

After 30 days, an unselected listing loses its stored full description. A minimal non-sensitive tombstone retains canonical identity and content fingerprints to prevent immediate rediscovery as a new job. Saved, reviewed, or later-submitted opportunities and their decision history follow later pipeline-retention rules and are not removed by this cleanup.

## Eligibility evaluation

Hard gates are applied before Match Score. The evaluator uses only the active search-profile snapshot and the exact job revision.

### Hard failures

- Employer is JPMorganChase or a confirmed hiring entity of JPMorgan Chase.
- No officially stated location qualifies under the locked location and remote-work rule.
- Singapore sponsorship is explicitly unavailable.
- Entire clearly comparable disclosed compensation range is below the applicable floor.
- Role is a locked excluded category.
- Role is a substantial level downgrade.
- Official listing is closed or expired.

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

Warnings do not add or subtract Match Score. Each warning has a clear resolution requirement and blocks future-drafting readiness until resolved.

Hard failures remain visible in a concise rejection history with source, profile version, rule, reason, and time. Keeping or saving a rejected job does not turn it into an eligible match.

## Requirement extraction

The interpreter first separates the job description into:

- Role level and reporting or management expectations.
- Required qualifications.
- Preferred qualifications.
- Product responsibilities and problems to solve.
- Domain expectations.
- Technical, platform, data, and integration expectations.
- Strategy, leadership, influence, and operating-scale expectations.
- Location, compensation, sponsorship, timing, and employment conditions.

Every extracted requirement keeps an exact job-text reference and importance classification. The interpreter cannot convert employer marketing language into a candidate requirement without showing the source wording.

Requirements used for hard gates are evaluated by fixed rules and conservative review states. The interpreter may identify candidate text for a gate but cannot make the final hard-gate decision.

## Restricted scoring packet

The approved interpreter path uses Varun's existing Codex/ChatGPT access. No separately billed model API is authorized by this design.

Each packet contains only:

- The public job description and inert source metadata needed for matching.
- The scoring-rubric version and fixed instructions.
- Relevant approved or corrected Phase 1 fact revisions that are supported, current, non-confidential, correctly attributed, and conflict-free.
- Stable opaque identifiers needed to return evidence mappings.

The packet excludes:

- Confidential facts, even when another use has permission.
- Unresolved, rejected, stale, unsupported, superseded, or wrongly attributed facts.
- Contact details and personal identifiers.
- Current compensation and unrelated personal information.
- Source documents or facts irrelevant to the job.
- Credentials, tokens, cookies, local paths, and database details.

The packet is immutable, short-lived, bound to one job revision, one profile version, one rubric version, and an exact fact-set fingerprint. Returned mappings with unknown identifiers, changed fingerprints, expired packets, or unexpected fields are rejected.

The interpreter has no browsing, provider, file, profile-change, approval, or application tools. It returns structured requirement mappings only.

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

The fixed calculator validates allowed anchors and performs all arithmetic. The interpreter cannot award a value between anchors or change a maximum.

### Evidence rules

For every non-zero component, the assessment must retain:

- Exact job-requirement references.
- Exact eligible Phase 1 claim and revision references.
- A reason code describing direct, adjacent, partial, strong, or close fit.
- Plain-language gaps.

Repeated wording does not earn repeated credit. The same fact may support different components only when it genuinely supports distinct aspects, and each use must be explained. Coursework, learning, or prototypes cannot be described as production AI experience. Missing evidence is written as `no_approved_evidence_found`, not as a claim that Varun lacks the capability.

An unsupported explicit minimum requirement is displayed prominently and blocks future-drafting readiness until reviewed, even when the overall score is high.

### Score bands

- 85–100: strong match; potentially ready for future drafting after every separate check passes.
- 70–84: worthwhile match; eligible for the focused shortlist.
- 55–69: exploratory match; retained in the full list.
- Below 55: weak match; searchable but not recommended.

Thresholds are versioned and cannot be lowered to fill a weekly list.

## Confidence and interpretation stability

Confidence describes assessment quality, not Varun's ability.

- `high`: current official description is sufficiently complete; all material requirements were processed; every awarded component has valid evidence; no material ambiguity or instability remains.
- `medium`: official description and evidence are usable, but limited ambiguity or incomplete preferred criteria remain.
- `low`: description is incomplete, unofficial, poorly parsed, materially ambiguous, or produces unstable mappings.

Low confidence blocks future-drafting readiness. An interpretation failure produces `needs_assessment`, never a default or estimated score.

The fixed reference suite reassesses identical representative inputs. A difference of more than five total points or more than two points within a component is considered unstable and must fail acceptance. In normal use, a reassessment of unchanged inputs that exceeds the same limits receives `unstable_interpretation` and requires review.

## Focused shortlist and full list

The focused shortlist contains up to 20 jobs that:

- Are live on an official employer source.
- Pass all hard gates.
- Score at least 70.
- Have a completed match assessment.

Conditional jobs may appear with prominent warnings. An unfamiliar employer, unknown compensation, or unknown Singapore sponsorship does not hide an otherwise strong job.

The shortlist order is:

1. Match Score descending.
2. Confidence, with higher confidence first.
3. Official verification and freshness.
4. Discovery time, newest first, when earlier factors are equal.

These ordering rules do not change Match Score.

When the market supplies fewer than 10 qualifying jobs, the cockpit shows fewer and explains why. It never lowers the threshold or introduces hard-gate failures. When more than 20 qualify, the remainder stay searchable in the full list.

The full list contains eligible and conditional discoveries, exploratory matches, weak matches, and leads awaiting official verification. Rejected jobs appear only in the concise rejection history.

## Future-drafting readiness

Phase 2 does not draft documents. It may set `ready_for_future_drafting` only when all of these are true:

- Match Score is at least 85.
- Confidence is high or medium.
- Job is live and officially verified.
- Compensation is verified, comparable, and acceptable.
- Singapore sponsorship is confirmed when applicable.
- Employer is approved.
- Role scope is resolved.
- No explicit minimum requirement remains unsupported.
- No notice-period timing conflict remains unresolved.
- Search-profile version is still active.
- Every referenced Phase 1 fact revision remains eligible for matching.
- No job change has invalidated the assessment.

Phase 3 must recheck this state and all referenced versions before generating anything. A Phase 2 readiness flag is not permission to invent a claim or use confidential evidence.

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

Shows provider approval and health separately from employer approval. A provider or employer change requires confirmation, reason, expected version, and append-only history.

### Run history

Shows planned and attempted search effort, actual source coverage, provider failures, jobs found, duplicates combined, assessments completed, invalidations, and publication state.

### User actions

Varun may save, dismiss, request reassessment, review an employer, or resolve a job-information warning. Dismissal reasons organize the workflow but never silently change the search profile, scoring weights, or future rankings. A correction creates a new verified observation or assessment with source, actor, reason, and history; it never overwrites source text.

## Information flow

1. Varun opens the local cockpit.
2. Phase 2 checks Phase 1 acceptance, readiness, compatibility, and activation.
3. Varun starts a manual discovery run.
4. The run captures the exact Phase 1 readiness and search-profile snapshots.
5. The effort planner creates location and difficulty query lanes.
6. Approved providers return inert source observations.
7. The standardizer creates or updates job revisions.
8. The duplicate checker combines only reliable identities and flags uncertainty.
9. The lifecycle checker verifies live status and freshness.
10. The gate evaluator excludes hard failures and records conditional warnings.
11. The requirement extractor builds cited job requirements.
12. Phase 1 returns the minimal eligible matching-fact set.
13. The restricted packet is interpreted through approved existing Codex/ChatGPT access.
14. The fixed calculator validates anchors and calculates the total.
15. Confidence and future-drafting readiness are evaluated separately.
16. Before publication, Phase 2 rechecks the Phase 1 snapshots and every fact reference.
17. A valid run publishes the focused shortlist and full list; an incompatible run is invalidated.
18. Every view and later handoff rechecks current fact eligibility and job revision.

## Concurrency, history, backup, and restore

- Only one discovery run may publish at a time.
- Provider, employer, verification, save, dismissal, and reassessment changes are serialized inside the Phase 2 store.
- A run uses immutable Phase 1 input snapshots and revalidates before publication.
- Concurrent profile or fact changes cannot silently publish a stale assessment.
- Phase 2 decisions and assessments are append-only or superseding; they are not rewritten in place.
- A verified safety copy is created before risky Phase 2 data changes and schema upgrades.
- Phase 2 backup and restore follow the owner-only permissions, integrity checks, safe-copy installation, and external recovery-history principles approved for Phase 1.
- After either store is restored, compatibility and references are rechecked before Phase 2 resumes.
- A Phase 1 restore that removes or changes referenced revisions invalidates affected assessments without deleting their historical record.

## Security and privacy

- Phase 2 remains bound to `127.0.0.1` and uses the Phase 1 launch-session protections.
- Its database, backups, and operational logs use owner-only permissions and remain outside Git.
- Provider credentials, if later required, use macOS Keychain.
- Logs never contain credentials, tokens, cookies, career-fact wording, restricted scoring packets, or unnecessary description text.
- Browser responses remain non-cacheable, imported text is escaped, and unapproved origins are rejected.
- Job HTML is never rendered as active source content.
- URLs are restricted to approved HTTP or HTTPS hosts and safe redirects.
- Local-file URLs, loopback or private-network targets, unsafe schemes, unexpected content types, and oversized responses are rejected.
- Provider access uses documented public feeds or explicitly approved browser assistance, honors sensible rate limits, and does not silently bypass login or access controls.
- Demographic information, age, gender, photographs, and unrelated personal details never influence matching.
- Singapore sponsorship is evaluated only as a practical eligibility requirement from the locked profile.

## Hostile-listing protection

Job descriptions and source metadata are untrusted data. Embedded text cannot:

- Change gates, weights, thresholds, or allocations.
- Approve a provider or employer.
- Confirm compensation, sponsorship, or live status.
- Change a Phase 1 fact.
- Request additional private facts.
- Activate a tool, browser action, file action, download, or application step.
- Tell the interpreter to ignore cockpit rules.

Unexpected instruction-like text is ignored and may be recorded as suspicious content. The interpreter returns only the approved structured schema, and unknown fields or identifiers cause rejection.

## Failure handling

- A provider failure is isolated and creates an honest coverage warning.
- A partial run cannot claim complete coverage.
- A failed or interrupted run never replaces the last published results.
- An unreadable listing remains an unscored lead with a plain-language reason.
- A parsing or interpretation failure never creates a guessed score.
- An ambiguous location, compensation, sponsorship, role scope, or deadline remains unknown or conditional.
- A changed source observation creates a new revision rather than silently changing an assessment.
- A changed Phase 1 snapshot invalidates publication and requires recalculation.
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

Provides an allowed or denied result, exact job revision, exact assessment ID, profile version, fact references, and explicit denial reasons.

### `DiscoveryRunSummary`

Provides provider health, coverage, allocations, jobs, scores, warnings, and run provenance for later Sites-bundle work.

Phase 3 and later phases must call these services and recheck versions. They cannot read Phase 2 tables directly.

## Test strategy

Automated tests use sanitized saved provider responses and synthetic Phase 1 service fixtures. They never contact live providers or read Varun's live fact vault.

### Contract tests

- Phase 1 readiness, profile, matching-fact, and exact-revision eligibility contracts.
- Provider adapter inputs, outputs, rate behavior, error mapping, and safe-host restrictions.
- Later-phase Phase 2 views and denial reasons.

### Discovery tests

- All location and difficulty effort calculations across four published runs.
- Provider success, partial failure, rate limiting, and complete failure.
- Greenhouse, Lever, official-page, and manual-link fixtures.
- Unapproved providers and endpoints cannot run.
- Provider failure never becomes false job closure.

### Normalization and lifecycle tests

- Requisition, URL, and description-based duplicate tiers.
- Ambiguous duplicates remain separate.
- Multiple source references survive combination.
- Material changes create revisions and invalidate scores.
- Presentation-only changes do not create false revisions.
- Live, changed, needs-verification, expired, and closed transitions.
- Thirty-day description cleanup and non-sensitive tombstones.

### Eligibility tests

- Exact locked profile matches the Phase 1 golden profile field by field.
- JPMorganChase and clear employer-name variations are always rejected.
- All eligible, ineligible, remote, and multi-location cases.
- Every excluded and ambiguous role category.
- Below-floor, crossing-range, above-floor, missing, wrong-basis, and ambiguous compensation.
- Singapore sponsorship confirmed, unavailable, and unknown.
- Unknown employer, role scope, notice period, and minimum requirement warnings.
- No single-job bypass of a locked gate.

### Scoring tests

- Seven exact component maxima and a total maximum of 100.
- Only allowed discrete anchors are accepted.
- Fixed arithmetic cannot be changed by interpreter output.
- Every non-zero component has job and eligible-fact references.
- Duplicate wording does not earn duplicate points.
- Coursework and prototypes are not treated as production experience.
- Missing evidence is not rewritten as a negative fact.
- Score bands and focused-shortlist threshold never lower automatically.
- Confidence and readiness checks remain separate from Match Score.
- Direct-fit, stretch, aspirational, misleading-title, sparse-description, and near-miss golden fixtures.
- Repeated reference assessments stay within five total points and two component points.

### Fact-safety tests

- Unresolved, rejected, stale, unsupported, superseded, confidential, and wrongly attributed facts are excluded from packets and mappings.
- A confidential permission for another use does not permit Phase 2 use.
- Contact details and unrelated personal information are excluded.
- A Phase 1 sensitivity or support change invalidates the assessment and redacts its evidence display.
- A profile change or restore invalidates incompatible runs and assessments.

### Security tests

- Prompt-like instructions in job descriptions cannot affect rules or actions.
- Script and HTML content renders only as text.
- Unsafe schemes, local files, internal-network targets, redirect chains, oversized bodies, and unexpected content types are rejected.
- Packet replay, expiry, wrong job revision, wrong profile version, wrong fact fingerprint, and unknown returned IDs are rejected.
- Credentials and sensitive content do not appear in logs or Git.
- Local session, CSRF, Host, Origin, caching, framing, and file-permission protections remain effective.

### User-flow tests

- Phase 2 remains visibly disabled before Phase 1 acceptance and explicit enablement.
- A complete manual run produces source health, a focused shortlist, and a full list.
- Conditional jobs display exact warnings and cannot become ready for drafting.
- Saving, dismissal, employer review, warning resolution, and reassessment preserve history.
- A mid-run Phase 1 change prevents publication.
- A changed job invalidates its prior assessment.
- No action generates a document or starts an application.
- Primary screens remain keyboard accessible and readable at narrow, medium, and wide browser sizes.

## Acceptance criteria

Phase 2 is complete only when all of the following are demonstrated after Phase 1 acceptance:

1. Phase 2 cannot activate before Phase 1 implementation, acceptance, readiness, and Varun's confirmation.
2. No automated acceptance test contacts a live provider or reads Varun's real fact vault.
3. Every locked role, domain, location, allocation, compensation floor, exclusion, notice period, and JPMorganChase exclusion is preserved exactly.
4. Search allocations guide effort without changing scores, thresholds, or shortlist composition.
5. Public Greenhouse and Lever fixtures and approved official-page fixtures degrade independently.
6. Newly discovered provider types cannot activate without explicit approval.
7. Unfamiliar employers remain visible and cannot become ready for drafting until approved.
8. Original listing wording and source provenance are retained as inert text.
9. Reliable duplicates combine without losing sources; ambiguous duplicates never auto-merge.
10. Material job changes create revisions and invalidate assessments.
11. Provider failure alone never closes a listing.
12. Only an official live listing scoring at least 70 enters the focused shortlist.
13. The shortlist contains at most 20 jobs and never lowers its threshold to fill a target.
14. Missing compensation stays unknown, is clearly flagged, and blocks future drafting.
15. A compensation range crossing the floor stays conditional rather than being rejected.
16. A range entirely below the applicable floor is rejected.
17. Unknown Singapore sponsorship stays conditional; unavailable sponsorship is rejected.
18. Remote work qualifies only with explicit target-location eligibility.
19. All seven score components use the approved weights and fixed anchors.
20. Every non-zero score component points to exact job wording and eligible Phase 1 evidence.
21. Confidential facts never influence Phase 2, regardless of other permissions.
22. Unapproved, unsupported, stale, rejected, unresolved, superseded, or wrongly attributed facts never influence Phase 2.
23. Existing Codex/ChatGPT access receives only a valid restricted scoring packet.
24. Interpreter output cannot change gates, weights, arithmetic, approvals, facts, or application state.
25. Freshness, salary confidence, sponsorship, employer review, source verification, notice-period compatibility, employer risk, and confidence remain separate from Match Score.
26. Low-confidence or unstable assessments cannot become ready for drafting.
27. A changed Phase 1 profile, fact state, support state, sensitivity, or restore invalidates affected assessments.
28. An 85+ score alone is insufficient; every future-drafting readiness check must pass.
29. Provider, employer, run, job, eligibility, score, and user-decision histories are preserved through superseding events.
30. Unsafe listing content, URLs, responses, and packet results are rejected safely.
31. The local security, backup, restore, and permission controls remain effective for the Phase 2 store.
32. When the market supplies them, the cockpit presents 10–20 ranked worthwhile opportunities without weakening standards.
33. Phase 2 never generates documents, fills forms, or submits applications.

## Phase 2 completion output

After implementation and acceptance, Varun will have:

- A private local catalog of current, traceable job opportunities.
- Honest provider-health and discovery-coverage reporting.
- A focused shortlist and searchable full discovery list.
- Explained 100-point Match Scores grounded only in permitted evidence.
- Visible gaps, uncertainty, and readiness warnings.
- Versioned outputs that Phase 3 can consume safely after revalidation.

Until Phase 1 has been implemented and accepted, this document authorizes design and planning only.
