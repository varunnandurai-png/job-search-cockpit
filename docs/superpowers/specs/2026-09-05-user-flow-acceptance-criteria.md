# Job Search Cockpit — User-Flow Acceptance Criteria

**Baseline:** `2026-09-04-approved-user-flow-baseline.md`

**Initial review branch:** `Gravity_dev`

**Historical reviewed commit:** `5f3489a`

**Criteria amendment date:** 5 September 2026

## How to use this document

Each parent criterion corresponds to exactly one numbered step in the approved
user flow. Subcases test important success, failure, recovery, and safety paths
without changing the 22-step baseline.

A parent status may change to `Complete` only when every applicable subcase and
the complete visible outcome pass against the same reviewed commit. A source
file or test filename is not execution evidence.

Execution evidence must record:

- the exact test or scenario and command;
- the result and execution date;
- the exact reviewed commit;
- saved output; and
- a screenshot or recording when the expected result is visible behavior.

## Approval provenance

The following policy decisions were explicitly approved by Varun Nanduri on
5 September 2026 during the acceptance-criteria review conversation:

| Decision | Approved rule |
|---|---|
| Job-fit and resume readiness | A selected 70–84 job may proceed through resume creation, approval, and application preparation. Its score and gaps remain visible and truthful. Resume wording cannot raise the underlying job-fit score. |
| Release platform scope | Release 1 is measured only against the named catalogue below. A newly discovered platform is recorded for a subsequent release and must stop safely in the current release. |
| Resume improvement attempts | The first two truthful improvement attempts may run without another decision. Before attempt 3 and before every later attempt, Varun must explicitly approve that single attempt. |
| Freshness | Shortlist verification age must be no more than 7 × 24 hours. Verification age for resume or application work must be no more than 24 hours. |
| Ranking | Score highest first, then confidence high before medium before low, verification newest first, discovery newest first, and finally stable job ID ascending. |
| Material job change | A change to job ID or application link, role, location, pay, sponsorship, seniority, a mandatory requirement, deadline, or open/closed status is material. Cosmetic wording alone is not. |
| Scheduler week | One week runs from Tuesday at 7:00 AM IST through the following Tuesday at 6:59:59 AM IST. Catch-up is permitted only within that window. |
| No employer review page | The product uses a local review checkpoint and never activates the employer's final control; Varun takes over manually. |

## Approved rules

### Score-band clarification for AC-07

A score of 85 or higher is labelled `strong` only when every mandatory and
critical check passes. An 85+ score with a mandatory gap is not labelled
`strong`; the gap remains visible and follows the gap path. This is an approved
clarification of the simple 85+ branch in the flow diagram.

### Separate job-fit and resume-readiness rules for AC-13 and AC-14

The product does not claim to predict or beat an employer's private ATS score.
Job fit and resume readiness are separate results. Selecting better wording may
improve requirement coverage in the resume, but cannot change the underlying
job-fit score.

A selected job scoring 70–84 may proceed through resume preparation, approval,
and application preparation when Varun chooses it. Its score and every gap must
remain clearly visible. `Resume ready` requires all of the following:

For this 22-step workflow, this approved rule supersedes the older Phase 2
future-drafting rule that allowed only an 85+ job to proceed.

1. Every material job requirement is classified as supported, partly
   supported, unsupported, or unresolved; none may be omitted.
2. Every resume statement uses current, approved, truthful evidence.
3. Supported requirements cite the exact approved evidence; partly supported,
   unsupported, and unresolved requirements remain visible as gaps.
4. The PDF and DOCX are readable, text-extractable, and contain the same
   approved content.

The first two truthful improvement attempts may run without another decision.
Before attempt 3 and every later attempt, the product shows the current result
and asks Varun to approve that attempt. No attempt may invent or strengthen a
career claim. Varun may stop, return to the shortlist, or approve the truthful
resume and continue with its disclosed gaps.

### Artifact timing for AC-12 and AC-15

AC-12 creates a browser or in-memory draft preview only. It creates no final
PDF or DOCX. AC-15 approval binds the exact reviewed content and version, then
creates the immutable final PDF/DOCX pair used for attachment.

### Release 1 application-platform catalogue for AC-16 through AC-21

Release 1 has this fixed acceptance catalogue:

1. LinkedIn Easy Apply
2. Naukri
3. Glassdoor
4. Greenhouse
5. Lever
6. Workday
7. Indeed
8. SmartRecruiters
9. iCIMS
10. Oracle Taleo
11. SAP SuccessFactors
12. Ashby

AC-16 through AC-21 may become complete only when the maintained fixture for
each named platform passes. A platform discovered after this catalogue is
frozen does not reverse Release 1 completion: it is recorded as subsequent
acceptance work. The current release must stop safely before entering data or
submitting on that platform. Safe stopping is mandatory but is not a claim that
the newly discovered platform is supported. The product never presses Submit.

### Exact scheduling, ranking, freshness, and material-change rules

- A scheduler week begins Tuesday at 7:00 AM IST and ends the following Tuesday
  at 6:59:59 AM IST. A missed run catches up once only within that same window.
  Once the next window begins, the previous window is not run.
- Ranking is score highest first, then confidence high before medium before
  low, official verification newest first, discovery newest first, then stable
  job ID ascending.
- Shortlist verification age must be no more than 7 × 24 hours; resume and
  application verification age must be no more than 24 hours.
- A change to job ID or application link, role, location, pay, sponsorship,
  seniority, a mandatory requirement, deadline, or open/closed status is
  material. Cosmetic wording alone is not material.

## Parent acceptance criteria

| Criterion ID | Workflow step | Expected outcome | Test scenario | Status | Reviewed commit | Evidence | Defect/blocker |
|---|---|---|---|---|---|---|---|
| AC-01 | 1. Approve profile, experience and job preferences | Only reviewed facts and the current approved search preferences are usable. | Approve a profile containing a resolved conflict, restart, and confirm approved data persists while rejected and unresolved facts remain unusable. | Partly complete | `5f3489a` | No complete execution record exists for `5f3489a`; candidate tests are `test_phase_1_acceptance.py`, `test_review_service.py`, and `test_search_profile_versioning.py`. | Visible end-to-end evidence and saved output are missing. |
| AC-02 | 2. Run every Tuesday at 7:00 AM IST | Exactly one weekly search runs automatically, catches up safely after downtime, and survives interruption without duplicate work. | Exercise the normal schedule plus AC-02.1 through AC-02.3. | Not built | `5f3489a` | No execution record; `README.md` requires manual discovery. | Scheduler, catch-up, single-run protection, and recovery are absent. |
| AC-03 | 3. Find jobs across all agreed sources | Every source reports success, successful zero results, timeout, or failure independently; valid results from healthy sources remain available. | Exercise a normal multi-source run plus AC-03.1 through AC-03.3. | Partly complete | `5f3489a` | No complete execution record; candidate coverage exists in `test_phase2_discovery_runtime.py`. | Company-site coverage and automatic weekly execution are incomplete. |
| AC-04 | 4. Remove duplicates, expired jobs, and unreliable listings | Genuine duplicates combine without merging different openings; stale or unreliable listings are excluded with reasons. | Exercise AC-04.1 through AC-04.3 using controlled listings. | Partly complete | `5f3489a` | No complete execution record; candidate coverage exists in `test_phase2_discovery_runtime.py`. | Cross-source identity and complete freshness behavior lack end-to-end evidence. |
| AC-05 | 5. Apply essential job rules | Failed rules exclude a job with a visible reason; missing information remains conditional and is routed to AC-11. | Test every rule as pass, fail, and unknown, then verify the visible label, reason, and next action. | Partly complete | `5f3489a` | Rule-level test files exist, but no UI execution result or screenshot is recorded for `5f3489a`. | Rules are tested below the UI; the complete visible outcome is unverified. |
| AC-06 | 6. Compare the job with the profile and calculate fit | Every material requirement is accounted for and the same approved inputs produce the same 0–100 score without manual mapping. | Score a job twice; confirm every material requirement has one visible state and any omitted requirement blocks publication. | Partly complete | `5f3489a` | Scoring tests exist, but no complete execution record covers automatic full-requirement mapping. | Manual evidence mapping remains and full requirement coverage is not demonstrated. |
| AC-07 | 7. Apply the score bands | Boundaries 69, 70, 84, and 85 produce the approved visible label and next action; 85+ is strong only when all required checks pass. | Exercise every boundary, including an 85+ result with a mandatory gap, and verify visible labels and actions. | Partly complete | `5f3489a` | Rule-level tests exist, but no UI execution result or screenshot is recorded for `5f3489a`. | The arithmetic exists; the complete visible outcome is unverified. |
| AC-08 | 8. Display up to 20 ranked jobs | The weekly shortlist shows zero through 20 jobs in the exact approved direction for every tie-break and persists after restart. | Exercise AC-08.1 through AC-08.4. | Partly complete | `5f3489a` | Ranking tests exist, but no automatic weekly shortlist execution record is saved. | Automatic publication and visible persistence are incomplete. |
| AC-09 | 9. Let Varun choose or dismiss a job | Continue advances only the chosen job; dismissal persists and reopens only after a material job change. | Exercise AC-09.1 and AC-09.2. | Partly complete | `5f3489a` | No complete choose/dismiss execution record exists. | Dismissal, history, and material-change reappearance are incomplete. |
| AC-10 | 10. Reconfirm the job remains suitable | Immediately before resume work, current job, location, pay, sponsorship, timing, and other essential conditions are rechecked. | Change or close a selected listing, confirm the flow stops with the reason, then repeat with unchanged suitable data and confirm continuation. | Partly complete | `5f3489a` | Candidate verification tests exist, but no complete visible execution record is saved. | Several suitability decisions remain separate manual checks. |
| AC-11 | 11. Ask only for important unresolved decisions | Failed conditions reject; unknown conditions pause with one clear question and resume the same job after resolution. | Exercise AC-11.1 and AC-11.2 plus a definite failure. | Partly complete | `5f3489a` | No focused prompt-and-resume execution record exists. | Resolution is spread across several approval and mapping screens. |
| AC-12 | 12. Create a truthful tailored resume | A selected job creates an exact draft preview from approved facts only; no final files exist yet. | Generate a preview with supported and unsupported requirements and confirm no hard-coded, invented, confidential, or cross-job content and no final artifact. | Partly complete | `5f3489a` | Renderer tests exist, but no complete preview execution record is saved. | The executive generator is hard-coded and disconnected; preview-only timing is not implemented consistently. |
| AC-13 | 13. Check the resume against job requirements | Every material requirement has a visible coverage state and citation; resume readiness is separate from the unchanged job-fit score. | Use supported, partly supported, unsupported, and unresolved requirements and verify all appear and satisfy the resume-readiness rule without changing job fit. | Partly complete | `5f3489a` | Requirement and finalisation test files exist, but no complete visible coverage report is recorded. | Full requirement coverage and the measurable resume-readiness result are incomplete. |
| AC-14 | 14. Improve until ready or explain the gap | Truthful improvement is rechecked; after two attempts, every additional attempt requires Varun's explicit approval and gaps never disappear by invention. | Exercise AC-14.1 through AC-14.4. | Partly complete | `5f3489a` | Gap-blocking tests exist; no user-controlled improvement-loop execution record exists. | Automatic improvement, rechecking, per-attempt approval, and return-or-continue choices are absent. |
| AC-15 | 15. Let Varun review and approve the final resume | Varun can request changes or approve, including a truthful resume for a 70–84 job with disclosed gaps; only approval creates final files bound to the exact reviewed content and version. | Request a change and confirm no final files; approve the corrected preview for a 70–84 job with its visible gaps and confirm both final files match it. | Partly complete | `5f3489a` | Finalisation tests exist, but the required request-change journey lacks complete execution evidence. | AC-15 cannot be Complete until both request-change and approve paths pass visibly. |
| AC-16 | 16. Open the employer application | The exact application for the chosen job opens visibly on every platform in the fixed Release 1 catalogue. | Exercise all 12 named Release 1 fixtures and confirm the job and final resume binding on each platform. | Not built | `5f3489a` | No employer-application browser execution record exists. | Employer browser automation and Release 1 platform coverage are absent. |
| AC-17 | 17. Let Varun handle sign-in and identity checks | Automation pauses without observing or storing credentials, codes, or CAPTCHA answers and resumes safely afterward. | Exercise AC-17.1 and AC-17.2 across all 12 Release 1 platform fixtures. | Not built | `5f3489a` | Safety intent is documented; no browser execution evidence exists. | Controlled pause, session recovery, and resume behavior are absent. |
| AC-18 | 18. Fill approved answers and attach the resume | Every supported form receives only exact approved answers and the final resume bound to that job. | Exercise AC-18.1 through AC-18.3. | Partly complete | `5f3489a` | Reusable-answer data tests exist; no real form-fill or attachment result is recorded. | Data foundations exist, but browser filling and attachment do not. |
| AC-19 | 19. Pause for missing, sensitive, or uncertain questions | Such fields remain unfilled, are highlighted for Varun, and resume only after an allowed answer is approved. | Exercise AC-19.1 and AC-19.2 across all 12 Release 1 platform fixtures. | Partly complete | `5f3489a` | Answer-safety tests exist; no live-form prompt-and-resume evidence exists. | Safety rules are not connected to employer forms. |
| AC-20 | 20. Stop at the employer's final review page | Automation cannot submit by click, keyboard, script, retry, restart, or a form without a distinct review page. | Exercise AC-20.1 through AC-20.3 across all 12 Release 1 platform fixtures. | Not built | `5f3489a` | No employer final-review execution record exists. | Final-review detection and enforced no-submit behavior are absent. |
| AC-21 | 21. Let Varun review the completed application | Varun can inspect and correct every answer and attachment, including after interruption, while submission remains manual. | Exercise AC-21.1 and AC-21.2. | Not built | `5f3489a` | No completed-application review execution record exists. | Review, correction, interruption, and resume behavior are absent. |
| AC-22 | 22. Record confirmed submission and prevent duplicates | Clear success is recorded once; ambiguous or interrupted recording remains unresolved and blocks automatic repeat attempts. | Exercise AC-22.1 through AC-22.3. | Not built | `5f3489a` | Only no-submit draft metadata exists; no outcome execution evidence exists. | Confirmation detection, durable outcome recording, uncertainty handling, and duplicate prevention are absent. |

## Required subcases

Every subcase begins as `Not executed`. Status changes require the execution
evidence format defined above.

| Subcase ID | Preconditions / fixture | Action | Exact expected result | Test level | Status | Reviewed commit | Execution evidence | Defect/blocker |
|---|---|---|---|---|---|---|---|---|
| AC-02.1 | The weekly run is due while the Mac is asleep, offline, or the product is not running. | Wake, reconnect, or start the Mac after the due time but before the next Tuesday at 7:00 AM IST. | The product starts one catch-up run for that Tuesday-to-Tuesday window at the next available opportunity; a persisted window key prevents a second run. | Integration and end-to-end | Not executed | — | Required command, result, date, commit, and run-history screenshot are not recorded. | Scheduler not built. |
| AC-02.2 | Two scheduler triggers occur in the same Tuesday-to-Tuesday window. | Start both concurrently. | Exactly one run owns the persisted window key; the other exits without provider calls or duplicate records. | Integration | Not executed | — | Required command, result, date, commit, and output are not recorded. | Single-run protection not built. |
| AC-02.3 | A weekly run crashes after starting. | Restart within the same scheduling window, then separately restart after the next window begins. | Within the same window, the interrupted run is visible and recovery uses the same window key; after the boundary, the missed prior window never runs. An uncertain paid provider call is not repeated automatically. | Integration and end-to-end | Not executed | — | Required command, result, date, commit, and visible recovery evidence are not recorded. | Crash recovery not built. |
| AC-03.1 | One healthy source has no matching jobs. | Run weekly discovery. | The source reports successful zero results; the overall run remains valid and no jobs are fabricated. | Integration and visible acceptance | Not executed | — | Required output and screenshot are not recorded. | Complete weekly source reporting unverified. |
| AC-03.2 | One source fails while at least one other source succeeds. | Run weekly discovery. | Successful results remain available and the failed source and reason are displayed without exposing secrets. | Integration and visible acceptance | Not executed | — | Required output and screenshot are not recorded. | UI outcome unverified. |
| AC-03.3 | One source times out. | Run weekly discovery. | The timed-out source is marked separately, healthy sources finish, and no automatic unbounded retry occurs. | Integration | Not executed | — | Required output is not recorded. | Weekly timeout behavior unverified. |
| AC-04.1 | The same vacancy arrives with different source URLs or provider IDs but the same verified employer requisition or official application identity. | Process both listings. | One job remains with both source histories; identity is based on verified requisition or official application identity, not title alone. | Integration | Not executed | — | Required result is not recorded. | Cross-source identity not fully demonstrated. |
| AC-04.2 | Two genuinely different vacancies have similar titles at the same employer. | Process both listings. | They remain separate unless verified identity proves they are the same opening. | Integration | Not executed | — | Required result is not recorded. | Similar-title false-merge evidence missing. |
| AC-04.3 | A shortlisted listing exceeds seven-day verification freshness or reaches resume/application work without verification in the prior 24 hours. | Continue the workflow. | It leaves the current shortlist or pauses for revalidation; stale data cannot continue to resume or application work. | Integration and end-to-end | Not executed | — | Required result and screenshot are not recorded. | Complete freshness journey unverified. |
| AC-05.1 | One job definitely fails a rule and another has missing salary, sponsorship, or timing information. | Evaluate both. | The failed job is excluded with a reason; the unknown job remains conditional and is routed to the exact AC-11 question. | Integration and visible acceptance | Not executed | — | Required output and screenshot are not recorded. | Fail-versus-unknown UI behavior unverified. |
| AC-08.1 | No jobs qualify. | Publish the weekly shortlist. | An empty shortlist is shown with truthful source/run reasons; thresholds are not lowered. | End-to-end and visible acceptance | Not executed | — | Required screenshot and run output are not recorded. | Automatic shortlist publication incomplete. |
| AC-08.2 | Between one and nineteen jobs qualify. | Publish the weekly shortlist. | Every qualifying job appears; filler, stale, or below-threshold jobs are not added. | End-to-end and visible acceptance | Not executed | — | Required screenshot and output are not recorded. | Automatic shortlist publication incomplete. |
| AC-08.3 | More than twenty jobs qualify, including ties. | Publish the shortlist. | Exactly twenty appear in this order: score highest first, confidence high before medium before low, official verification newest first, discovery newest first, then stable job ID ascending. | Integration and visible acceptance | Not executed | — | Required output and screenshot are not recorded. | Full visible tie-break proof missing. |
| AC-08.4 | A shortlist has been published. | Restart the product. | The same current shortlist and order return unless source or profile changes require re-evaluation. | End-to-end | Not executed | — | Required restart evidence is not recorded. | Visible persistence unverified. |
| AC-09.1 | A job is dismissed. | Restart and run discovery again with the unchanged vacancy. | The job remains dismissed and its reason/history remain available. | Integration and end-to-end | Not executed | — | Required history evidence is not recorded. | Dismissal flow incomplete. |
| AC-09.2 | A dismissed job changes its job ID/application link, role, location, pay, sponsorship, seniority, mandatory requirements, deadline, or open/closed status. | Process the changed vacancy. | It may reappear clearly labelled with the material field that changed; cosmetic wording alone and unchanged rediscovery cannot make it reappear. | Integration and visible acceptance | Not executed | — | Required result is not recorded. | Material-change reappearance rule not implemented. |
| AC-11.1 | Salary is absent or not comparable. | Continue from the shortlist. | One salary decision prompt appears; the job remains conditional until Varun resolves it and cannot silently pass. | End-to-end and visible acceptance | Not executed | — | Required screenshot is not recorded. | Focused prompt flow absent. |
| AC-11.2 | Singapore sponsorship is unknown. | Continue from the shortlist. | One sponsorship prompt appears; confirmed support resumes the same job and unavailable support rejects only that location path. | End-to-end and visible acceptance | Not executed | — | Required screenshot is not recorded. | Focused prompt flow absent. |
| AC-14.1 | Approved unused evidence can improve a not-ready preview. | Run one improvement attempt. | Coverage or readiness improves using only approved evidence, every requirement is rechecked, and the revised preview is versioned. | Integration and visible acceptance | Not executed | — | Required before/after evidence is not recorded. | Improvement loop absent. |
| AC-14.2 | An improvement attempt produces no better coverage or readiness. | Review the result. | The product explains that no truthful improvement occurred, keeps every gap visible, and offers stop, return to shortlist, approve the truthful resume, or request another permitted attempt. | Integration and visible acceptance | Not executed | — | Required result is not recorded. | No-progress decision flow not implemented. |
| AC-14.3 | A selected 70–84 job retains a mandatory or other disclosed gap after improvement. | Review and approve the truthful resume. | The unchanged fit score and gap remain prominent; Varun may return to the shortlist or explicitly approve the resume and continue to application preparation. | End-to-end and visible acceptance | Not executed | — | Required screenshot and output are not recorded. | Disclosed-gap approval path not implemented. |
| AC-14.4 | Two improvement attempts have completed, or a user-approved later attempt has completed. | Request one more improvement attempt. | Before attempt 3 and every later attempt, the product shows the current result and requires explicit approval for that single attempt; declining performs no regeneration. | End-to-end and visible acceptance | Not executed | — | Required prompt, decision, and output evidence are not recorded. | Per-attempt approval after attempt 2 is not implemented. |
| AC-17.1 | An employer session expires during filling. | Resume after Varun signs in again. | The product rechecks the job and form, restores only safe non-sensitive progress, and never stores credentials or codes. | End-to-end and security | Not executed | — | Required browser and storage evidence are not recorded. | Employer browser flow absent. |
| AC-17.2 | Login requires a password, one-time code, consent, or CAPTCHA. | Reach each identity step. | Automation pauses before the field, Varun completes it directly, secrets never enter product storage/logs, and filling resumes only after user action. | End-to-end and security | Not executed | — | Required recording and storage/log inspection are not recorded. | Identity handoff absent. |
| AC-18.1 | A supported form reveals dynamic fields based on earlier answers. | Fill the triggering answer. | Newly revealed fields are rescanned and handled under the same approved-answer and sensitive-field rules. | End-to-end | Not executed | — | Required browser recording is not recorded. | Dynamic-form handling absent. |
| AC-18.2 | Resume attachment fails or the site changes the uploaded file. | Attach the approved final resume. | The flow stops, shows the exact failure, and cannot proceed until the correct file identity is visibly confirmed. | End-to-end and visible acceptance | Not executed | — | Required screenshot and file evidence are not recorded. | Attachment handling absent. |
| AC-18.3 | The fixture catalogue contains LinkedIn Easy Apply, Naukri, Glassdoor, Greenhouse, Lever, Workday, Indeed, SmartRecruiters, iCIMS, Oracle Taleo, SAP SuccessFactors, and Ashby. | Run the same job-bound fill-and-attach scenario on every fixture. | Every named Release 1 platform passes; the result is unaffected by a later platform discovery, which follows AC-19.2. | End-to-end and acceptance | Not executed | — | Per-platform command, result, date, commit, and recording are not recorded. | Release 1 browser-platform support absent. |
| AC-19.1 | A form contains a missing answer, sensitive voluntary question, and differently worded prior question. | Fill the form. | All three remain unfilled and highlighted; prohibited answers are never stored and only explicitly approved allowed answers can resume filling. | End-to-end and security | Not executed | — | Required recording and storage evidence are not recorded. | Live prompt-and-resume behavior absent. |
| AC-19.2 | A platform outside the frozen Release 1 catalogue is reached. | Attempt form preparation. | The product stops safely before entering data or submitting, identifies the platform, and records it as subsequent-release acceptance work without reversing Release 1 completion. | End-to-end and visible acceptance | Not executed | — | Required screenshot and platform record are not recorded. | Unsupported-form safe stop and intake are absent. |
| AC-20.1 | Every allowed field and attachment is complete on a form with a separate review page. | Continue after the last field. | The employer review page opens and all automation stops before Submit across waiting and restart. | End-to-end and safety | Not executed | — | Required recording is not recorded. | Final-review detection absent. |
| AC-20.2 | A form has no distinct review page and its continue control may submit. | Reach the last safe field. | The product creates a local review checkpoint and never activates the final site control; Varun must take over manually. | End-to-end and safety | Not executed | — | Required recording is not recorded. | No-review-page safety boundary absent. |
| AC-20.3 | Submit can be triggered by Enter, keyboard shortcut, focused button, script, or retry. | Exercise every trigger while automation is active. | No automated click, keypress, script, form submission, or retry can trigger submission. | End-to-end and security | Not executed | — | Required browser evidence is not recorded. | Enforced no-submit controls absent. |
| AC-21.1 | Filling is interrupted before final review. | Restart and resume. | The exact job and final resume are revalidated, safe progress is restored, changed fields are rescanned, and no submission occurs. | End-to-end | Not executed | — | Required restart recording is not recorded. | Interruption and resume absent. |
| AC-21.2 | Varun changes an answer or attachment during final review. | Save the correction and return to review. | The corrected value and exact attachment appear, dependent dynamic fields are rechecked, and Submit remains manual. | End-to-end and visible acceptance | Not executed | — | Required before/after recording is not recorded. | Review correction flow absent. |
| AC-22.1 | Varun submits successfully, but local recording crashes before completion. | Restart the product. | The outcome is marked uncertain, the job is blocked from automatic repeat, and Varun is asked to resolve it before any new attempt. | Integration and end-to-end | Not executed | — | Required recovery evidence is not recorded. | Durable outcome recovery absent. |
| AC-22.2 | The employer response after manual submission is ambiguous. | Observe the outcome. | No success is claimed; the attempt remains uncertain and prevents automatic repeat until Varun resolves it. | End-to-end and visible acceptance | Not executed | — | Required screenshot is not recorded. | Ambiguous-confirmation handling absent. |
| AC-22.3 | A successfully submitted job is rediscovered through another source or URL. | Process the rediscovered listing. | Verified job identity links it to the completed application and blocks a duplicate application while preserving the new source history. | Integration and end-to-end | Not executed | — | Required output is not recorded. | Cross-source application duplicate prevention absent. |

## Historical and current status interpretation

The first tracker recorded 4 `Complete`, 12 `Partly complete`, and 6 `Not
built` statuses against commit `5f3489a`. That assessment remains in Git
history and is not fresh verification of a later branch.

After reviewing the evidence standard, the current defensible interpretation
of that historical commit is:

- Complete: 0 parent criteria
- Partly complete: 16 parent criteria
- Not built: 6 parent criteria

No parent criterion is release-accepted until the required execution evidence
is recorded against one exact reviewed commit.

## Verification ownership

- The developer implements each parent criterion and subcase.
- The engineering tester verifies rules, integrations, failures, recovery, and
  security behavior.
- The acceptance tester validates the visible outcome and exclusively approves
  status changes to `Complete`.
