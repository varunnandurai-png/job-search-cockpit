# Job Search Cockpit — Phase 1 Design

**Date:** 2026-08-19  
**Status:** Approved for implementation
**Phase:** Foundation and verified profile

## Purpose

Phase 1 creates the private, trustworthy foundation for the Job Search Cockpit. It gives Varun a simple browser-based workflow for reviewing career facts, resolving conflicts, protecting confidential information, and confirming the job profiles that later discovery runs must use.

The central rule is simple: later phases may use only information that Varun has approved. The system must never invent, silently reinterpret, or strengthen a claim to improve a job application.

## Scope

Phase 1 will:

- Create a private application at `/Users/nandurivarun/Desktop/Documents/CV/job-search-cockpit/`.
- Import career facts from the approved curated sources.
- Identify duplicate, conflicting, numerical, date-related, title-related, and potentially confidential claims.
- Provide a minimalist local review experience.
- Record approvals, corrections, rejections, confidentiality choices, and their history.
- Store a locked first version of the target job-search profile.
- Report whether the fact vault is ready for Phase 2.
- Define safe interfaces that later phases can use without reading private storage directly.

Phase 1 will not:

- Search for live jobs.
- Generate resumes or cover letters.
- Build or publish the Sites dashboard.
- Schedule weekly searches.
- Fill application forms.
- Import every historical resume in `Old Data`.

Those capabilities remain in later phases. Historical resume-wide scanning may be added after the curated-source review process is proven reliable.

## Approved source documents

The initial import is limited to these curated sources:

1. `/Users/nandurivarun/Desktop/Documents/CV/Context/job-search-profile-assessment.md`
2. `/Users/nandurivarun/Desktop/Documents/CV/Old Data/profile_bank/profile.json`
3. `/Users/nandurivarun/Desktop/Documents/CV/Old Data/profile_bank/Varun_Nanduri_Master_Profile.md`
4. `/Users/nandurivarun/Desktop/Documents/CV/Old Data/profile_bank/Varun_Nanduri_Resume_Workflow.md`

Original source documents are read-only. An import must never edit, rename, or delete them.

## Locked job-search profile

`job-search-profile-assessment.md` is the official source for the first search-profile version. Phase 2 and later discovery runs must always apply this profile before a job can be presented as a match.

### Eligible seniority and role profiles

- Senior Product Manager.
- Lead Product Manager when it is an individual-contributor role.
- Selected Principal Product Manager when it is an individual-contributor role and the scope is supported by approved evidence.
- Applied AI Product Manager when the role connects AI to Varun's existing domain experience.
- Senior Technical Product Manager for platforms, APIs, integrations, data, fintech, lending, commerce, or fulfilment.

### Priority domain profiles

- Digital lending, mortgage, and home buying.
- Banking, fintech, risk, fraud, and relevant payments experience.
- E-commerce, fulfilment, last mile, and omnichannel products.
- Subscriptions, billing, and commerce platforms.
- Platforms, APIs, and partner integrations.
- Data, analytics, operational products, and decision support.
- Applied AI, document intelligence, workflow automation, AI-assisted compliance, enterprise agents, and intelligent automation where domain overlap exists.

### Locations and search allocation

- Hyderabad: eligible; approximately 40% of search effort.
- Bengaluru: eligible; approximately 45% of search effort.
- Singapore: eligible; approximately 15% of search effort and requires employer-sponsored Employment Pass support.
- All other locations are outside the Phase 2 search scope unless Varun explicitly approves a new search-profile version.

### Minimum compensation screening

- Hyderabad: ₹46 LPA minimum.
- Bengaluru: ₹48 LPA minimum.
- Singapore: S$120,000 base minimum.

Missing compensation remains `unknown` and is not automatically rejected. A job with disclosed compensation below the relevant minimum is ineligible unless Varun explicitly changes the locked profile through a new version.

### Exclusions and low-priority profiles

- JPMorganChase opportunities are excluded.
- Associate Product Manager and other junior product roles are excluded.
- Generic Business Analyst roles are excluded.
- Delivery-only Product Owner roles are excluded or treated as low priority when scope and compensation are not exceptional.
- Program Manager roles without product ownership are excluded.
- Director roles that depend heavily on formal people management are excluded.
- Deep AI infrastructure or foundation-model platform roles without domain overlap are excluded.
- General Singapore roles without a strong domain match or sponsorship path are excluded.

### Other fixed screening information

- Notice period: 60 days.
- Preferred level: senior individual contributor.
- A lateral title is acceptable only for genuine AI product scope.
- A substantial level downgrade is not acceptable.

### Changing the locked profile

The target profile is not casually editable. A change requires a clear confirmation from Varun, records the reason, preserves the earlier version, and creates a new active version. Later job discovery must record which profile version it used.

## Fact-review rules

### Information groups

Imported facts are organized into understandable groups:

- Contact details.
- Employment history.
- Job titles and dates.
- Responsibilities and product ownership.
- Achievements and quantified outcomes.
- Team and leadership scope.
- Education and certifications.
- Skills, tools, and domain experience.
- Job-search preferences.

### Decisions

Every claim has a review decision:

- `unresolved`: not yet approved for use.
- `approved`: accepted as accurate.
- `corrected`: replaced with wording or a value explicitly supplied or confirmed by Varun.
- `rejected`: inaccurate or unsuitable for use.

Confidentiality is separate from the review decision:

- `normal`: may be used by later phases when relevant.
- `confidential`: stays available for private reasoning but is excluded from generated documents unless Varun explicitly permits that use.

This allows a claim to be both accurate and confidential.

### Individual and grouped review

The following always require individual review:

- Conflicting claims.
- Quantified results or financial values.
- Dates and durations.
- Job titles.
- Team counts and leadership scope.
- Confidential claims.

Only uncontested, low-risk facts may be approved as a group. A grouped approval is still an explicit user decision and is recorded in the history.

### Known conflicts that must not be silently resolved

The importer is expected to surface, at minimum, conflicts such as:

- Approximately six years versus eight years of direct product experience.
- Differing Scrum-team counts.
- Title and chronology differences across sources.
- Repeated or differently attributed savings and outcome metrics.

The application must not decide which version is correct. It presents the evidence and waits for Varun's decision.

## Resume correctness gate

Although document generation begins in a later phase, Phase 1 establishes the mandatory rules it must follow.

A resume statement may be used only when:

- It exists in the fact vault.
- Its source is recorded.
- Its final wording and meaning are approved.
- Any related conflict has been resolved by Varun.
- Numerical results, dates, titles, and team sizes received individual approval.
- It is not confidential, unless Varun explicitly permits that particular use.
- It belongs to the correct employer and time period.

The cockpit must never:

- Invent achievements, responsibilities, skills, employers, or numbers.
- Increase or improve a metric without evidence and approval.
- Guess missing dates, titles, or details.
- Present learning, coursework, or prototypes as production experience.
- Use an unresolved or rejected claim.
- Change a fact silently to match a job description.

If evidence is missing, later document generation must omit the claim and explain the resulting gap. Before a resume can be approved, Varun must receive a plain-language list of the approved facts used in it.

An unresolved claim blocks generation only when that claim would be used. Unrelated approved facts remain available, while the application displays a clear vault-wide warning about outstanding review items.

Zero fabricated or unresolved claims is an acceptance requirement, not a preference.

## User experience

Phase 1 has five primary screens.

### 1. Home

Shows:

- The next action requiring attention.
- Counts of approved, unresolved, rejected, and confidential facts.
- Overall readiness for Phase 2.

It must not resemble a crowded analytics dashboard.

### 2. Review queue

Shows claims that require attention, with conflicts and higher-risk items first. Plain-language filters allow Varun to focus on dates, titles, numbers, confidentiality, or other groups.

### 3. Review a fact

Shows:

- The claim in plain language.
- Where it came from.
- Conflicting versions, when present.
- The effect of marking it confidential.
- Clear actions to approve, correct, reject, or mark confidential.

Important decisions require confirmation. The screen must never choose an answer on Varun's behalf.

### 4. Target job profile

Shows the active locked roles, domains, locations, compensation minimums, exclusions, notice period, and search allocation. Any change follows the confirmed version-change process.

### 5. History

Shows imports and decisions in chronological order, including the earlier value, new value, time, and reason when applicable. The history is readable and supports safe correction without erasing the prior record.

## Visual direction

The interface follows minimalist principles inspired by Apple.com's clarity, not its branding:

- White and soft-grey backgrounds.
- Dark, highly readable text.
- One restrained accent colour for important actions.
- Generous spacing.
- Large, clear headings.
- Plain-language instructions.
- One obvious primary action per screen.
- Essential information first, with supporting detail revealed on request.
- Simple progress indicators rather than complicated charts.
- No unnecessary animation, decoration, or technical terminology.
- Strong colour contrast, keyboard navigation, visible focus states, and readable text sizes.
- A responsive layout that remains clear at different browser-window sizes.

The design may take inspiration from the reference site's hierarchy and restraint but must not copy Apple logos, product imagery, marketing copy, or distinctive brand assets.

## Privacy and mistake prevention

- The application runs only on Varun's Mac and binds to `127.0.0.1`.
- A fresh session token is required each time the application launches.
- Closing the application invalidates the session.
- There is no separate username and password in Phase 1.
- The SQLite fact vault is stored locally and excluded from Git.
- Secrets, if later required, use macOS Keychain and are never stored in source files.
- The browser receives only the information needed for the current review page.
- Original documents are never modified.
- A timestamped local safety copy is created before a database change that could affect existing decisions.
- An interrupted or invalid import leaves the last complete vault unchanged.
- Missing or unreadable sources are named clearly; available sources may still be processed.
- Ambiguous information remains unresolved instead of being guessed.
- The application does not send facts to an external service during Phase 1.
- Locked search filters cannot be changed without explicit confirmation and a new version.
- Corrections preserve the decision history and can be superseded safely.

## Chosen technical shape

The product is a Python 3.12 local application with:

- FastAPI for the local application server.
- Server-rendered HTML for the browser experience.
- Lightweight browser interactions without a separate large frontend application.
- SQLite for the local fact vault.
- A clear service boundary between import, review, search-profile versioning, audit history, and readiness reporting.
- Automated tests for all approval, privacy, import, and versioning rules.

The server-rendered approach was selected because it supports a polished interface and reliable history while keeping Phase 1 smaller and easier to maintain than a separate React application. Streamlit was not selected because its interaction model is less suitable for a durable approval and audit workflow.

## Information flow

1. Varun launches the local cockpit.
2. The application verifies the session token and opens the Home screen.
3. Varun starts or reviews the curated-source import.
4. The importer reads source documents without modifying them.
5. Claims are standardized, linked to their exact source, and compared.
6. Conflicts and high-risk claims enter the individual review queue.
7. Uncontested low-risk facts may enter the grouped-review queue.
8. Varun approves, corrects, rejects, or marks facts confidential.
9. Each decision is recorded without deleting prior history.
10. The readiness check reports remaining required decisions.
11. When required reviews are complete, Phase 2 can use the approved facts and locked target profile through defined application services.

## Failure handling

- An invalid source never produces partially trusted claims.
- A malformed claim is shown as unresolved with its source context.
- A duplicate import does not create duplicate active facts.
- Re-importing a changed source creates reviewable changes rather than silently overwriting decisions.
- A failed database update is rolled back completely.
- A missing safety copy or failed safety-copy operation prevents a risky change.
- An expired or absent session token denies access and instructs Varun to relaunch.
- An unexpected error is explained in plain language and recorded locally without exposing sensitive values in logs.

## Main internal boundaries

Later implementation will keep these responsibilities separate:

- **Source importer:** reads curated documents and extracts candidate claims.
- **Conflict checker:** compares claims and identifies differences without choosing a winner.
- **Fact vault:** stores claims, sources, decisions, sensitivity, and versions.
- **Review workflow:** enforces which claims need individual attention.
- **Search-profile manager:** preserves the locked target profile and confirmed revisions.
- **Audit history:** records imports and decisions without deleting past events.
- **Readiness checker:** explains what prevents Phase 2 readiness.
- **Local web interface:** presents the workflow in plain language.

Later phases must call these boundaries rather than reading or changing database tables directly.

## Acceptance criteria

Phase 1 is complete only when all of the following are demonstrated:

1. All four curated sources import without changing the originals.
2. Missing sources are reported clearly and do not corrupt the import.
3. Duplicate imports do not create duplicate active claims.
4. Conflicts are identified, including product-years, team-count, chronology, title, and metric conflicts.
5. Conflicting, quantified, date-related, title-related, and confidential claims require individual review.
6. Only uncontested low-risk facts allow grouped approval.
7. Confidentiality remains independent from approval status.
8. Every active claim retains its source and decision history.
9. Rejected and unresolved claims are unavailable for resume use.
10. Confidential claims are unavailable for resume use unless Varun gives explicit permission.
11. No resume-eligible fact lacks approval and supporting source evidence.
12. The locked target profile exactly preserves the approved roles, domains, locations, compensation minimums, exclusions, notice period, and search allocation.
13. A target-profile change requires confirmation and creates a new version.
14. The application is reachable only from the local Mac and requires a current launch token.
15. Interrupted imports or updates leave the last complete vault unchanged.
16. A safety copy is created before risky data changes.
17. The Home screen clearly states the next action and readiness state.
18. The interface follows the approved minimalist direction and remains usable by keyboard.
19. The final readiness report lists approved, unresolved, rejected, and confidential facts.
20. Automated checks cover import, review, confidentiality, history, security boundaries, locked-profile versioning, and readiness behavior.

## Phase 1 completion output

At the end of Phase 1, Varun will have:

- A private local Job Search Cockpit.
- A reviewed and traceable fact vault.
- A locked, versioned target job-search profile.
- A clear list of unresolved information, if any.
- A readiness report for Phase 2.
- A reliable rule boundary preventing later phases from using unsupported career claims.
