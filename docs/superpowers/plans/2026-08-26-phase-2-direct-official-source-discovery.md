# Phase II Direct Official-Source Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace retired aggregator discovery with a local, read-only discovery path for explicitly approved public Greenhouse and Lever boards, plus a separately approved official-employer endpoint adapter.

**Architecture:** A durable provider-instance registry is the only authority for live source access. Each Greenhouse or Lever adapter receives an immutable approved instance and retrieves only its documented public board/feed; the official-page adapter is a parser registered per instance, never a generic browser. A transport containment layer validates DNS, every connection target, HTTPS URL, redirect hop, response size, and content type before any source observation enters the existing append-only Phase II catalog.

**Tech Stack:** Python 3.12, SQLAlchemy, Alembic, Pydantic, HTTPX, FastAPI, SQLite; no new dependency.

## Global Constraints

- This plan supersedes the Apify/JSearch portions of `2026-08-25-phase-2-provider-discovery-design.md`; the separately approved deprecation removed all aggregator adapters, credential loading, request types, and tests.
- Discover only real public listings from an explicitly approved exact employer/ATS instance. Do not fabricate listings, use saved response fixtures, write synthetic job-listing examples, scrape search engines, or call aggregators.
- Do not make a network request, enable an instance, collect a listing, or perform a smoke check while implementing this plan. Such live access requires a later per-instance user approval.
- Permit only `greenhouse_public_board`, `lever_public_board`, `official_page_read_only`, and `manual_official_url_read_only` adapter types; no provider type may be inferred from a URL.
- An instance approval records immutable employer identity, adapter type, exact initial hosts, path patterns, redirect-host allowlist, parser version, public-data scope, rate limit, approval actor, rationale, and approval time. The implementation must not insert an enabled instance itself.
- Require an active Phase II activation grant and revalidate it before DNS resolution, before request, after response receipt, before persistence, and before publication.
- Require HTTPS; reject credentials in URLs, IP-literal hosts, non-default ports, local file URLs, private/loopback/link-local/multicast/reserved/unspecified IPv4 and IPv6 addresses, unsafe redirects, non-allowlisted DNS answers, non-approved content types, oversized responses, and all HTML other than inert parser input.
- Use `httpx.Client(follow_redirects=False, transport=httpx.HTTPTransport(retries=0))`, exact per-instance timeout/rate constraints, no retry loop, polling, scheduler, browser automation, sign-in, upload, sharing, form action, or application submission.
- Never persist credentials, cookies, authorization headers, query strings containing sensitive parameters, raw HTTP headers, raw HTML, parser diagnostics containing listing prose, DNS answers, IP addresses, or any Phase I fact. Persist only approved public listing fields, safe source fingerprints, and append-only audit metadata already permitted by the Phase II catalog design.
- Keep every Phase I interaction behind `Phase1MatchingPort`; do not read Phase I tables. A discovered listing remains unverified and cannot create a preparation authorization, résumé, cover letter, PDF, DOCX, application draft, or submission.
- Tests must be static or use in-process transport stubs that prove containment only; they must not construct job-listing payloads. The later user-authorized smoke check is the only live verification and stores returned public listings only as production catalog records.
- Before each code edit, state planned change / reason / risk / verification. Use TDD, run focused tests after each increment, commit a small logical increment, push it to `origin/Dev`, and verify `HEAD == origin/Dev` after every push.

---

## File structure

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/provider_instances.py` | Immutable instance-approval types, exact URL policy, and approval validation. |
| `src/job_search_cockpit/phase2/safe_transport.py` | DNS/IP/URL/redirect/content-size containment and bounded HTTP transport. |
| `src/job_search_cockpit/phase2/official_providers.py` | Greenhouse, Lever, and per-instance official-page adapter contracts; no default instances. |
| `src/job_search_cockpit/phase2/discovery.py` | Replaces the retired aggregator planner with approved-instance planning and activation rechecks. |
| `src/job_search_cockpit/phase2/models.py` | Append-only provider-instance approval and instance health metadata models. |
| `alembic_phase2/versions/0009_official_provider_instances.py` | Immutable provider-instance schema and SQLite update/delete-rejection triggers. |
| `src/job_search_cockpit/phase2/runtime.py` | Wires disabled-by-default official discovery without enabling any instance. |
| `tests/unit/test_provider_instances.py` | Instance validation and absence of implicit/live configuration. |
| `tests/unit/test_safe_transport.py` | URL, DNS, redirect, MIME, body-size, and header-containment tests with no listing payloads. |
| `tests/unit/test_official_providers.py` | Adapter identity/endpoint selection and fail-closed parser dispatch tests with no listing payloads. |
| `tests/integration/test_phase2_official_provider_database.py` | Migration, append-only, forbidden-column, and disabled-runtime tests. |

## Task 1: Create immutable provider-instance approval types

**Files:**
- Create: `src/job_search_cockpit/phase2/provider_instances.py`
- Create: `tests/unit/test_provider_instances.py`

**Consumes:** Approved adapter-type names and the existing `Phase2ActivationService`.

**Produces:** `OfficialProviderKind`, `ApprovedProviderInstance`, `ProviderInstanceApproval`, and `ProviderInstanceUnavailable`.

- [ ] **Step 1: Write the failing invalid-instance test**

```python
def test_approved_provider_instance_rejects_wildcard_hosts_and_non_https_endpoint() -> None:
    with pytest.raises(ValueError, match="exact HTTPS host"):
        ApprovedProviderInstance(
            instance_id="employer-greenhouse-v1",
            kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
            employer_identity="Example Employer",
            hosts=("*.greenhouse.io",),
            endpoint_url="http://boards-api.greenhouse.io/v1/boards/example/jobs",
            redirect_hosts=(),
            path_prefixes=("/v1/boards/example/jobs",),
            parser_version="greenhouse-public-v1",
            max_response_bytes=1_000_000,
            min_request_interval_seconds=30,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_instances.py::test_approved_provider_instance_rejects_wildcard_hosts_and_non_https_endpoint -q`

Expected: FAIL because the instance model does not exist.

- [ ] **Step 3: Implement the smallest exact approval boundary**

```python
class OfficialProviderKind(StrEnum):
    GREENHOUSE_PUBLIC_BOARD = "greenhouse_public_board"
    LEVER_PUBLIC_BOARD = "lever_public_board"
    OFFICIAL_PAGE_READ_ONLY = "official_page_read_only"
    MANUAL_OFFICIAL_URL_READ_ONLY = "manual_official_url_read_only"

@dataclass(frozen=True, slots=True)
class ApprovedProviderInstance:
    instance_id: str
    kind: OfficialProviderKind
    employer_identity: str
    hosts: tuple[str, ...]
    endpoint_url: str
    redirect_hosts: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    parser_version: str
    max_response_bytes: int
    min_request_interval_seconds: int
```

Validate canonical lowercase DNS names with no wildcard, IP literal, or port; require an exact HTTPS endpoint whose hostname and path belong to the instance; reject userinfo/query/fragment; require unique non-empty tuple elements; bound response size to 1..2,000,000 bytes and interval to 1..86,400 seconds. Define a disabled empty registry as the runtime default, so no host or tenant is implicitly authorized.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/unit/test_provider_instances.py -q && uv run ruff check src/job_search_cockpit/phase2/provider_instances.py tests/unit/test_provider_instances.py && uv run mypy src`

Expected: all commands exit 0.

- [ ] **Step 5: Commit and push**

```bash
git add src/job_search_cockpit/phase2/provider_instances.py tests/unit/test_provider_instances.py
git commit -m "feat: define approved official provider instances"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical.

## Task 2: Add append-only approved-instance storage

**Files:**
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/0009_official_provider_instances.py`
- Create: `tests/integration/test_phase2_official_provider_database.py`

**Consumes:** `ApprovedProviderInstance` from Task 1 and migration `0008_match_scoring_shortlist`.

**Produces:** immutable `phase2_provider_instance_approvals` and `phase2_provider_instance_health_events` tables.

- [ ] **Step 1: Write the failing schema test**

```python
def test_official_provider_instance_schema_is_append_only_and_has_no_secret_columns(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(phase2_provider_instance_approvals)"
            )
        }

    assert "approval_fingerprint" in columns
    assert not columns & {"token", "key", "cookie", "authorization", "raw_html"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_phase2_official_provider_database.py::test_official_provider_instance_schema_is_append_only_and_has_no_secret_columns -q`

Expected: FAIL because the approval table does not exist.

- [ ] **Step 3: Implement immutable approval and health-event records**

Create UUID primary keys and `created_at` fields. Store only scalar approval inputs, JSON-encoded exact host/path tuples, `enabled` as an explicit approval-event state, parser version, bounded transport policy, approval actor/reason, activation/restore generations, and canonical approval fingerprint. Record health as append-only events with an opaque outcome code, request-start/request-finish times, and safe response fingerprint; never store an IP address, raw error, request URL query, response body, or headers. Add SQLite triggers rejecting `UPDATE` and `DELETE` on both tables; add the same guards to the ORM models.

- [ ] **Step 4: Run focused tests and migration checks**

Run: `uv run pytest tests/integration/test_phase2_official_provider_database.py -q && uv run ruff check src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0009_official_provider_instances.py tests/integration/test_phase2_official_provider_database.py && uv run mypy src && git diff --check`

Expected: all commands exit 0.

- [ ] **Step 5: Commit and push**

```bash
git add src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0009_official_provider_instances.py tests/integration/test_phase2_official_provider_database.py
git commit -m "feat: persist official provider instance approvals"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical.

## Task 3: Implement contained read-only transport

**Files:**
- Create: `src/job_search_cockpit/phase2/safe_transport.py`
- Create: `tests/unit/test_safe_transport.py`

**Consumes:** `ApprovedProviderInstance` from Task 1 and `Phase2ActivationService`.

**Produces:** `ContainedOfficialTransport.fetch(instance, url)` returning a bounded inert response only after all containment checks pass.

- [ ] **Step 1: Write the failing private-address test**

```python
def test_transport_rejects_a_private_dns_answer_before_request(
    approved_instance: ApprovedProviderInstance,
) -> None:
    transport = ContainedOfficialTransport(
        resolver=lambda _host: (ip_address("127.0.0.1"),),
        client_factory=forbidden_client_factory,
    )

    with pytest.raises(ProviderContainmentError, match="public address"):
        transport.fetch(approved_instance, approved_instance.endpoint_url)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_safe_transport.py::test_transport_rejects_a_private_dns_answer_before_request -q`

Expected: FAIL because the contained transport does not exist.

- [ ] **Step 3: Implement validation before each request and hop**

```python
class ContainedOfficialTransport:
    def fetch(
        self,
        instance: ApprovedProviderInstance,
        url: str,
    ) -> InertOfficialResponse: ...
```

Canonicalize URL hostnames with `urllib.parse`; accept only HTTPS, default port 443, no userinfo/fragment/sensitive query, approved exact hosts, and approved path prefixes. Resolve each hostname using an injected resolver immediately before its request; require a non-empty all-public answer set and reject IPv4/IPv6 private, loopback, link-local, multicast, reserved, unspecified, and IPv4-mapped unsafe addresses. Use a client with redirects disabled and retries zero. On a 301/302/303/307/308, accept at most two hops only when `Location` passes the same checks and has a host in `instance.hosts ∪ instance.redirect_hosts`; strip credential headers before any redirect. Stream the response and abort above `max_response_bytes`; accept only the instance’s exact declared MIME types. Return body bytes and a SHA-256 fingerprint to the adapter; do not log raw content.

- [ ] **Step 4: Add containment tests without listing data**

Add tests for non-HTTPS, URL userinfo, IP literal, unapproved host, DNS with one private answer, redirected off-allowlist host, redirect loop/cap, unacceptable content type, response too large, redirect header stripping, and activation-generation change before publication. Each stub response body must be empty or the harmless non-listing marker `b"{}"`.

- [ ] **Step 5: Run focused tests and static checks**

Run: `uv run pytest tests/unit/test_safe_transport.py -q && uv run ruff check src/job_search_cockpit/phase2/safe_transport.py tests/unit/test_safe_transport.py && uv run mypy src`

Expected: all commands exit 0.

- [ ] **Step 6: Commit and push**

```bash
git add src/job_search_cockpit/phase2/safe_transport.py tests/unit/test_safe_transport.py
git commit -m "feat: contain official provider transport"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical.

## Task 4: Define direct official-source adapters with no default instance

**Files:**
- Create: `src/job_search_cockpit/phase2/official_providers.py`
- Create: `tests/unit/test_official_providers.py`

**Consumes:** `ApprovedProviderInstance` and `ContainedOfficialTransport` from Tasks 1 and 3.

**Produces:** `OfficialProviderAdapter.fetch(instance)` and an adapter registry keyed by `OfficialProviderKind`.

- [ ] **Step 1: Write the failing adapter-dispatch test**

```python
def test_adapter_registry_rejects_an_instance_without_a_matching_kind() -> None:
    registry = OfficialProviderAdapterRegistry.empty()

    with pytest.raises(ProviderInstanceUnavailable, match="not registered"):
        registry.adapter_for(OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_official_providers.py::test_adapter_registry_rejects_an_instance_without_a_matching_kind -q`

Expected: FAIL because the registry does not exist.

- [ ] **Step 3: Implement strict adapter identity and endpoint rules**

Implement only these endpoint constructors: Greenhouse public board `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true` and Lever public postings `https://api.lever.co/v0/postings/{site}?mode=json`, where `board_token` or `site` is a validated immutable instance field and its derived URL equals the approved endpoint URL exactly. `official_page_read_only` and `manual_official_url_read_only` require a parser ID registered in code for that exact instance ID; absent registration raises `ProviderInstanceUnavailable`. Do not add a generic HTML parser, execute JavaScript, or infer selectors. Call the contained transport, pass inert bytes only to the matching adapter parser, reject an unknown schema or a record lacking a stable provider listing ID and canonical approved public URL, and ensure source observations retain exactly the existing `ProviderListing` permitted fields.

- [ ] **Step 4: Add static adapter tests**

Test no default adapter/instance exists; an incorrect Greenhouse board token or Lever site fails before transport; an unregistered official-page parser fails before transport; unsupported kind fails; and a request never reaches an aggregator adapter. Do not create a listing object or response fixture.

- [ ] **Step 5: Run focused tests and static checks**

Run: `uv run pytest tests/unit/test_official_providers.py -q && uv run ruff check src/job_search_cockpit/phase2/official_providers.py tests/unit/test_official_providers.py && uv run mypy src`

Expected: all commands exit 0.

- [ ] **Step 6: Commit and push**

```bash
git add src/job_search_cockpit/phase2/official_providers.py tests/unit/test_official_providers.py
git commit -m "feat: add bounded official source adapters"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical.

## Task 5: Replace aggregator planning with fail-closed approved-instance planning

**Files:**
- Modify: `src/job_search_cockpit/phase2/discovery.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `tests/unit/test_provider_config.py`
- Modify: `tests/integration/test_phase2_official_provider_database.py`

**Consumes:** approved-instance repository from Task 2, official adapter registry from Task 4, and current Phase I activation inputs.

**Produces:** discovery plans only for currently enabled, approved, compatible instances; a zero-instance registry blocks without network access.

- [ ] **Step 1: Write the failing no-instance test**

```python
def test_discovery_refuses_to_plan_when_no_official_instance_is_enabled(
    service: DiscoveryService,
    activation_inputs: Phase1ActivationInputs,
) -> None:
    with pytest.raises(ProviderConfigurationError, match="no approved official provider instances"):
        service._plans(activation_inputs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_config.py::test_discovery_refuses_to_plan_when_no_official_instance_is_enabled -q`

Expected: FAIL because discovery has no official-instance planner.

- [ ] **Step 3: Implement local planning without live execution**

Remove credentials/charge-limit arguments from the active planner and make it retrieve only immutable enabled approval records that match the current activation and restore generations. Sort eligible instances by stable instance ID. For each plan, verify adapter registration and build an instance-specific request with no provider credential. Revalidate Phase II activation and Phase I inputs immediately before plan construction and retain the existing rechecks around persistence. Keep `VerifiedJobReadinessUnavailable` as the runtime default; creating a discovery plan cannot issue an authorization.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/unit/test_provider_config.py tests/integration/test_phase2_official_provider_database.py -q && uv run ruff check src/job_search_cockpit/phase2/discovery.py src/job_search_cockpit/phase2/runtime.py tests/unit/test_provider_config.py tests/integration/test_phase2_official_provider_database.py && uv run mypy src && git diff --check`

Expected: all commands exit 0.

- [ ] **Step 5: Commit and push**

```bash
git add src/job_search_cockpit/phase2/discovery.py src/job_search_cockpit/phase2/runtime.py tests/unit/test_provider_config.py tests/integration/test_phase2_official_provider_database.py
git commit -m "feat: plan discovery from approved official instances"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical.

## Task 6: Verify the disabled local implementation and prepare the human gate

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-phase-2-provider-discovery-design.md`
- Modify: this plan
- Test: `tests/unit/test_provider_instances.py`

**Consumes:** completed Tasks 1–5.

**Produces:** a tested local-only direct-source implementation and an explicit record of the only next action: user review of a named provider instance before any live smoke check.

- [ ] **Step 1: Write the failing disabled-runtime test**

```python
def test_default_runtime_has_no_enabled_official_provider_instance(
    runtime: Phase2Runtime,
) -> None:
    with pytest.raises(ProviderConfigurationError, match="no approved official provider instances"):
        runtime.discovery_service._plans(runtime.phase1_activation_inputs())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_instances.py::test_default_runtime_has_no_enabled_official_provider_instance -q`

Expected: FAIL until the runtime has a deliberately empty registry.

- [ ] **Step 3: Update the superseded discovery design and plan decision log**

Replace its provider list, credential references, cost caps, and live micro-run terms with this direct-official-source design. State that the implementation has no enabled instances and that a later user approval must name one employer, adapter kind, exact board/endpoint URL, initial/redirect hosts, parser version, request rate, data scope, and the maximum listings for one read-only smoke check. Do not name an employer or endpoint as approved by default.

- [ ] **Step 4: Run full required verification**

Run:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
git diff --check
git status --short
```

Expected: all quality commands exit 0; the test suite contains no synthetic job listing or saved provider response; the only expected warning, if still present, is the existing FastAPI/Starlette `TestClient` deprecation warning.

- [ ] **Step 5: Commit and push**

```bash
git add docs/superpowers/specs/2026-08-25-phase-2-provider-discovery-design.md docs/superpowers/plans/2026-08-26-phase-2-direct-official-source-discovery.md tests/unit/test_provider_instances.py
git commit -m "docs: retire aggregator discovery design"
git push origin Dev
git rev-parse HEAD
git rev-parse origin/Dev
```

Expected: the two hashes are identical and `git status --short` is empty.

## Plan self-review

**Coverage:** Task 1 prevents implicit trust; Task 2 makes each instance approval auditable and immutable; Task 3 provides SSRF, redirect, MIME, and body-size containment; Task 4 prevents a generic scraper or default board; Task 5 makes discovery use only enabled approved instances; Task 6 proves the runtime remains disabled and records the human live-access gate.

**Scope:** The plan contains no real discovery request, employer selection, board configuration, aggregation, browser automation, application action, résumé generation, or Phase I table access. The original scoring/shortlist plan remains separate.

**Consistency:** Every adapter operates on `ApprovedProviderInstance`, every transport call is activation-revalidated and instance-contained, and every implementation increment has a focused test, commit, push, and local/remote SHA comparison.

## Execution record — 2026-08-27

Tasks 1–5 are implemented and pushed as `14a9221`, `d4b269f`, `3a38987`, `6a4eafa`, and `1061c0e`. The default runtime has an empty official-provider catalog and fails closed; no employer, endpoint, parser, executor, or live listing is configured.

Task 6 supersedes the aggregator-oriented discovery design with the direct-official-source design and adds the disabled-runtime integration check. The next action remains a user decision on one named official employer board before any external read-only smoke check.
