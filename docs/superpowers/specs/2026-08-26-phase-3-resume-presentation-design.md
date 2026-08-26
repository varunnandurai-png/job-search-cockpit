# Phase III resume presentation design

## Status

Approved by Varun on 2026-08-26 for Phase III local finalisation.

## Purpose

Define the visual presentation of the one final local PDF/DOCX resume pair
without changing Phase III evidence, authorisation, retention, or external
action boundaries.

## Approved visual direction

Use the **classic executive** direction:

- A navy header band with a restrained gold accent rule.
- A professional headshot in the header.
- A formal, readable hierarchy for profile, experience, education, and
  relevant achievements.
- Tables only where they improve scanning, such as a compact skills or
  qualifications section.
- Visual elements are subtle and professional; no decorative graphics,
  loud colour fields, infographics, or casual styling.
- The PDF and DOCX present the same canonical content and use the same
  visual-system tokens as closely as their formats permit.

## Headshot handling

- Automated tests and design previews use a synthetic placeholder headshot
  only.
- A real headshot is supplied directly by Varun only at real finalisation
  time; the cockpit does not read an existing resume, provider page, browser
  source, cloud drive, or online profile to obtain one.
- The real headshot is held only in memory or a private temporary directory
  during finalisation, embedded in the final PDF/DOCX pair, and removed from
  temporary storage on success and failure.
- No separate headshot file, photo metadata, or image bytes are persisted in
  the Phase II database.

## Content and safety boundaries

- The presentation layer never changes, invents, strengthens, reorders
  semantically, or selects career claims. It renders only the immutable
  canonical document model created from current approved Phase I wording and
  the verified Phase II requirement ledger.
- No file is generated before exact finalisation confirmation.
- No draft, design preview, or revision file is retained.
- No upload, sharing, provider activity, browser automation, Google Drive
  activity, or background task is added.

## Rendering requirements

- Apply explicit layout tokens in both output formats: US Letter portrait,
  deliberate margins, navy/gold palette, consistent typography, accessible
  contrast, non-clipping image frame, and readable table geometry.
- Verify both files structurally and through normalized content equivalence.
- Render every generated DOCX and PDF page to PNG for visual QA before a real
  pair is accepted.
- Visual QA rejects clipping, overlap, broken bullets or tables, missing
  images, low-contrast text, and mismatched section order.

## Filename and storage decisions

- The first final pair for a company is `Varun_Resume_<company_name>.docx`
  and `Varun_Resume_<company_name>.pdf`, with company names safely normalized
  for filesystem use.
- A later final pair for another role at the same company is
  `<role_name>_Varun_Resume_<company_name>.docx` and
  `<role_name>_Varun_Resume_<company_name>.pdf`, with both public values safely
  normalized for filesystem use. The service never overwrites an existing pair.
- Phase III saves final files only to the private local Job Search Cockpit
  output directory. Google Drive is a separate future phase and is not
  accessed here.
- Exact confirmation remains `FINALISE RESUME FOR THIS VERIFIED JOB`.
