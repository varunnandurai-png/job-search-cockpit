# Phase II provider discovery and verified-job authorization design

## Status

The earlier Apify/JSearch pilot is retired. Its aggregator adapters, credential loading, request types, and tests were removed and must not be reintroduced under this design.

The implemented local-only foundation supports direct official sources only:

- `greenhouse_public_board`
- `lever_public_board`
- `official_page_read_only`
- `manual_official_url_read_only`

No provider instance is enabled by default. No external request, job collection, parser, executor, résumé, document, draft, application, upload, sharing action, or submission has occurred during implementation.

## Purpose

Phase II provides a bounded local path that can eventually discover real public jobs and issue a verified, short-lived preparation authorization. A source listing is only a candidate: it cannot authorize résumé preparation, document generation, or an application submission.

## Approval model

Adapter-type support does not authorize a source. Each provider instance requires an immutable, append-only local approval event that records:

- Exact employer identity, adapter kind, initial hosts, redirect hosts, endpoint, allowed path prefixes, and immutable source identifier where the public board protocol requires one.
- Exact parser version and content-type allowlist.
- Bounded response size and request interval.
- Enabled/disabled state, actor, reason, current activation/restore generations, timestamp, and safe approval fingerprint.

The discovery planner considers only the newest event for an instance ID. It accepts that instance only when the event is enabled and matches the current Phase II activation and restore generations. A zero-instance catalog fails closed before credential loading, executor construction, parsing, persistence, or network access.

## Direct-source containment

A contained transport requires a revalidation callback and an injected pinned executor. There is no default HTTP client, browser, credential, or fallback transport.

Before DNS resolution, before executor delegation, and immediately after response receipt, it revalidates Phase II authority. It rejects non-HTTPS URLs, userinfo, fragments, unsafe or sensitive query parameters, non-default ports, unapproved hosts and paths, DNS answers that include non-public addresses, response connections outside the validated address set, too-large bodies, unexpected status codes, unexpected MIME types, and redirect chains outside the exact instance allowlist.

At most two redirects are allowed. The transport accepts only the MIME types declared in the immutable approval record. Response material remains inert bytes for an exact registered parser; no generic HTML parser, JavaScript execution, selector inference, browser automation, sign-in, upload, sharing, or submission exists.

## Adapter contracts

Greenhouse and Lever adapters derive their public endpoint from the immutable source identifier and require exact equality with the approved endpoint:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
- Lever: `https://api.lever.co/v0/postings/{site}?mode=json`

Official-page and manual-URL adapters use the already-approved endpoint and require a parser registered for the exact instance ID and parser version. A missing or version-mismatched parser blocks before transport. This code contains no configured employer, endpoint, parser, executor, or listing response fixture.

## Data minimization and retention

The Phase II catalog stores only approved public listing fields after a separately approved real retrieval, source provenance, immutable revision fingerprints, assessment metadata, and authorization metadata. It never stores provider credentials, cookies, authorization headers, raw HTTP headers, raw HTML, IP addresses, DNS answers, sessions, passwords, OTPs, answer wording, résumé text, application submission state, or Phase I facts.

Listings and approval events are append-only. Changed or closed listings create new observations/revisions; they are never rewritten in place.

## Required future user gate

Before any live smoke check, the user must approve one named provider instance with all of:

1. Employer identity and adapter kind.
2. Exact board or endpoint URL, source identifier where applicable, initial host allowlist, redirect-host allowlist, and path policy.
3. Parser version, declared MIME types, response-size cap, and request interval.
4. The exact read-only executor implementation and a maximum listing count for one manual smoke check.

That approval authorizes only the named instance and bounded read-only check. It does not authorize search engines, aggregators, browser automation, account sign-in, application drafting, résumé preparation, document finalisation, upload, sharing, or submission.

## Testing and deferred work

Static and local database tests cover approval validation, append-only storage, latest/current approval selection, registry/parser gating, endpoint derivation, DNS/query/MIME/address containment, activation revalidation, and disabled runtime behavior. They contain no synthetic job listings or saved provider responses.

A later explicit user-approved live check may retain returned public listings only as production catalog records. Real discovery, requirement extraction, scoring, shortlist publication, and verified-job authorization remain separately gated.
