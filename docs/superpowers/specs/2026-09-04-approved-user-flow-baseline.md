# Job Search Cockpit — Approved User-Flow Baseline

**Approved by:** Varun Nanduri

**Approved on:** 4 September 2026
**Status:** Baseline for requirements, implementation, and acceptance reviews

## Completion rule

Each numbered step remains `Not built`, `Partly complete`, or `Complete` until
its agreed outcome is demonstrated. Supporting code alone does not make a step
complete. The product must provide the user-visible result and pass the
relevant acceptance check.

The system must never press the employer's final **Submit** button. It prepares
and fills the application, stops at the employer's final review page, and waits
for Varun to review and submit it.

## Approved flow

```mermaid
flowchart TD
    A["1. Approve profile, experience and job preferences"] --> B["2. Every Tuesday at 7:00 AM IST"]
    B --> C["3. Find jobs across LinkedIn, Naukri, Glassdoor, other search results and company career pages"]
    C --> D["4. Remove duplicates, expired jobs and unreliable listings"]
    D --> E{"5. Does the job meet your essential rules?"}

    E -- No --> X["Keep it outside the shortlist and explain why"]
    E -- Yes --> F["6. Compare the job with your approved profile and calculate a fit score"]

    F --> G{"7. Fit score"}
    G -- "Below 70" --> X
    G -- "70–84" --> H["Show in the shortlist with gaps clearly identified"]
    G -- "85 or higher" --> I["Show as a strong match"]

    H --> J["8. Display up to 20 ranked jobs"]
    I --> J
    J --> K{"9. You choose a job"}
    K -- Dismiss --> X
    K -- Continue --> L["10. Confirm the job is still open and its location, pay and other conditions remain suitable"]

    L --> M{"11. Any important uncertainty?"}
    M -- Yes --> N["Ask you only for the missing decision"]
    N -- Not suitable --> X
    N -- Resolved --> O
    M -- No --> O["12. Create a tailored resume using only truthful, approved information"]

    O --> P["13. Check the resume against the job requirements"]
    P --> Q{"14. Strong enough and fully supported?"}
    Q -- No --> R["Improve it using existing approved experience, or clearly show an unresolvable gap"]
    R -- Improved --> P
    R -- Cannot resolve --> J
    Q -- Yes --> S["15. You review and approve the final resume"]

    S -- Request changes --> O
    S -- Approve --> T["16. Open the application in a visible browser"]
    T --> U["17. You sign in and complete any identity checks or CAPTCHAs"]
    U --> V["18. Fill approved answers and attach the tailored resume"]
    V --> W{"19. Missing, sensitive or uncertain question?"}
    W -- Yes --> Y["Leave it unanswered and ask you"]
    Y --> V
    W -- No --> AA["20. Stop at the employer's final review page"]

    AA --> AB["21. You review the complete application"]
    AB -- Make changes --> V
    AB -- Press Submit --> AC["22. Confirm success and record the application to prevent duplicates"]
```

## Agreed operating decisions

- Search runs automatically every Tuesday at 7:00 AM India time.
- Sources cover LinkedIn, Naukri, Glassdoor, broader job-search results, and
  company career pages.
- The system presents a ranked shortlist before preparing a resume.
- Varun chooses which job continues to resume and application preparation.
- Only approved, truthful profile information may be used.
- Missing, sensitive, uncertain, sign-in, one-time-code, and CAPTCHA steps
  remain with Varun.
- The system fills the application and attaches the correct resume but stops
  before final submission.
- After Varun submits, the system records confirmed success to prevent
  duplicate applications.

## Baseline change control

Every delivery must reference the affected step numbers and provide evidence
for any status change. Changing this flow requires Varun's explicit approval;
implementation work alone cannot silently change the baseline.
