# Phase II assessment publication and shortlist-read design

## Status

Approved for implementation on 2026-08-27. This is a local-only continuation
of the approved Phase II scoring and shortlist plan.

## Purpose

Turn an already validated, opaque match assessment into append-only Phase II
metadata and make the local review route read only current, revalidated rows.
It does not discover jobs, parse public listing prose, call an external
service, create a résumé, issue readiness, or submit an application.

## Boundary

`AssessmentPublicationService` is an in-process service. Its input contains
only the exact job revision ID, opaque requirement/mapping identifiers,
bounded enums and reason codes, numeric score components, immutable
fingerprints, and the qualified-band inputs. It obtains authority only through
`AssessmentAuthorityService`, which in turn uses `Phase1MatchingPort` and the
Phase II activation service. It never reads Phase I tables.

The service captures authority before work and revalidates it immediately
before its single append-only transaction. Changed or unavailable authority,
incomplete fact sets, invalid mappings, or an invalid qualified band reject
publication without writing a current assessment.

## Persistence

One successful publication appends a job-gate assessment, zero or more
location paths, one match assessment, its seven components, requirement
mappings, and one shortlist decision. Every row receives the same authority
fence. The rows store only existing approved metadata fields: identifiers,
hashes, fingerprints, bounded reason codes, spans, scores, and booleans. They
never store job-description text, career wording, credentials, or artefact
paths.

Earlier rows remain immutable. The first implementation exposes only a
fail-closed current state; it does not invent reassessment, adjudication, or
history mutation behavior.

## Read path

`AssessmentReviewService` revalidates authority on every request before it
queries the append-only match-assessment records. It returns a compact,
non-sensitive view containing only current assessment IDs, score, band,
confidence, and shortlist state. If authority cannot be revalidated, it
returns the existing redacted unavailable state. The authenticated local route
continues to be read-only and cannot trigger collection, assessment mutation,
finalisation, upload, sharing, or submission.

## Testing

Tests use opaque identifiers and abstract assessment data only—never synthetic
job listings or career facts. They prove successful append-only metadata
publication, same-fence binding, authority drift rejection, invalid mapping or
band rejection, current-only read filtering, anonymous-route denial, and
redaction when authority is unavailable. Focused unit and integration tests
run before every increment; the full quality suite runs after completion.

## Deliberate exclusions

- Real listing collection and the required 30-item official corpus
- Requirement extraction from listing text and interpreter dispatch
- Readiness authorization or any Phase III behavior
- Changes to retention, output, or external-access design
