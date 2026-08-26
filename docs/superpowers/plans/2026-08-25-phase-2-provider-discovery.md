# Phase II Provider Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manually triggered, bounded Apify and JSearch discovery pipeline that persistently records real public listings and can later issue a revalidated verified-job authorization.

**Architecture:** Provider adapters retrieve only public listings under fixed caps and write immutable source observations into the isolated Phase II catalog. A local discovery service normalizes and deduplicates observations, revalidates the active Phase I snapshot through the internal port, and leaves every candidate unverified until an explicit local verification service issues a one-use authorization.

**Tech Stack:** Python 3.12, SQLAlchemy, Alembic, Pydantic, HTTPX, FastAPI, SQLite.

## Global Constraints

- Never commit, print, persist, or return `APIFY_API_TOKEN` or `JSEARCH_API_KEY`; load them only from the git-ignored `.env` file or the process environment.
- Use HTTPS, exact provider host allowlists, fixed request timeouts, no redirects, and no retries, polling, webhooks, browser automation, sign-in, upload, sharing, or submission behavior.
- Provider discovery is manual only. Do not create a scheduler, background task, or automatic weekly run.
- The pilot limits are 40 LinkedIn listings, 25 Naukri listings, 25 Glassdoor listings, one JSearch request bounded to 25 listings, and a US$0.50 maximum Apify charge per Actor. The real-data micro-run verification is limited to five listings per Apify Actor, US$0.10 per Actor when supported, and one JSearch request bounded to 25 listings.
- Save only real public provider listings. Do not fabricate listings, create synthetic provider responses, or save live responses as test fixtures.
- Keep all Phase I access behind `Phase1MatchingPort`; do not read Phase I tables or hard-code locked search-profile values.
- A listing is a candidate, not an authorization. `VerifiedJobReadinessUnavailable` remains the normal runtime adapter until an explicit verification service produces a current authorization.
- Do not create résumés, PDFs, DOCX files, application drafts, submissions, or provider-side application actions in this work.
- Before every edit, show planned change / reason / risk / verification. Run focused tests after each increment, and run Ruff, mypy, `git diff --check`, and the allowed broader suite at milestones.
- Do not commit or push unless the user explicitly requests it.

---

## File structure

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/provider_config.py` | Strict local credential loading and bounded provider settings without secret output. |
| `src/job_search_cockpit/phase2/discovery_types.py` | Frozen provider, listing, run, candidate, and verification request/result types. |
| `src/job_search_cockpit/phase2/providers.py` | HTTPS-only Apify and JSearch adapters with fixed timeouts and no retry loop. |
| `src/job_search_cockpit/phase2/discovery.py` | Manual run orchestration, source-observation persistence, canonical identity keys, and revalidation. |
| `src/job_search_cockpit/phase2/verification.py` | Explicit candidate verification and one-use authorization issuance. |
| `src/job_search_cockpit/phase2/models.py` | Append-only provider, run, source-observation, job revision, and verification metadata models. |
| `alembic_phase2/versions/0006_provider_discovery.py` | Append-only Phase II discovery schema and triggers. |
| `src/job_search_cockpit/phase2/runtime.py` | Adds discovery services but retains the unavailable preparation port by default. |
| `tests/unit/test_provider_config.py` | Credential absence, malformed configuration, and secret-redaction tests without listing data. |
| `tests/integration/test_phase2_discovery_database.py` | Schema, append-only, foreign-key, and prohibited-column checks without fabricated listings. |
| `tests/integration/test_phase2_live_discovery.py` | Opt-in, user-authorized live micro-run verification; skipped unless explicitly enabled. |

## Task 1: Load credentials safely and define bounded provider contracts

**Files:**
- Create: `src/job_search_cockpit/phase2/provider_config.py`
- Create: `src/job_search_cockpit/phase2/discovery_types.py`
- Test: `tests/unit/test_provider_config.py`

**Consumes:** the local git-ignored `.env` file with `APIFY_API_TOKEN` and `JSEARCH_API_KEY`.

**Produces:** `ProviderCredentials`, `ProviderLimits`, `ProviderRequest`, and `ProviderListing` types for the adapters.

- [x] **Step 1: Write the failing no-secret configuration test**

```python
def test_provider_credentials_fail_closed_when_a_required_value_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    with pytest.raises(ProviderConfigurationError, match="Apify credentials are unavailable"):
        ProviderCredentials.from_environment()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_config.py::test_provider_credentials_fail_closed_when_a_required_value_is_absent -q`

Expected: FAIL because the provider-configuration module does not exist.

- [x] **Step 3: Implement the smallest fail-closed configuration boundary**

```python
@dataclass(frozen=True, slots=True)
class ProviderCredentials:
    apify_token: str
    jsearch_key: str

    @classmethod
    def from_environment(cls) -> "ProviderCredentials":
        apify_token = os.environ.get("APIFY_API_TOKEN", "")
        jsearch_key = os.environ.get("JSEARCH_API_KEY", "")
        if not apify_token:
            raise ProviderConfigurationError("Apify credentials are unavailable.")
        if not jsearch_key:
            raise ProviderConfigurationError("JSearch credentials are unavailable.")
        return cls(apify_token=apify_token, jsearch_key=jsearch_key)
```

Load `.env` only once at process startup with a strict allowlist for the two exact keys; ignore comments and blank lines, reject duplicate keys, and never execute the file as shell code. Make `ProviderRequest` contain only a provider ID, role-query ID, location ID, listing limit, and optional Apify charge limit. Make `ProviderListing` contain only provider listing ID, canonical URL, title, employer name, locations, posted time, public description, compensation text, and retrieval time.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `uv run pytest tests/unit/test_provider_config.py -q`

Expected: PASS; output must not contain either environment variable value.

- [x] **Step 5: Run static checks**

Run: `uv run ruff check src/job_search_cockpit/phase2/provider_config.py src/job_search_cockpit/phase2/discovery_types.py tests/unit/test_provider_config.py && uv run mypy src`

Expected: both commands exit 0.

## Task 2: Add append-only local discovery records

**Files:**
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/0006_provider_discovery.py`
- Create: `tests/integration/test_phase2_discovery_database.py`

**Consumes:** `Phase2ResumePreparationAttempt` and the current Phase II migration head.

**Produces:** `Phase2DiscoveryRun`, `Phase2SourceListingObservation`, `Phase2JobRecord`, `Phase2JobRevision`, and `Phase2JobVerification` tables.

- [x] **Step 1: Write the failing schema test**

```python
def test_provider_discovery_schema_is_append_only_and_has_no_secret_columns(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "phase2_discovery_runs",
        "phase2_source_listing_observations",
        "phase2_job_records",
        "phase2_job_revisions",
        "phase2_job_verifications",
    } <= tables
```

- [x] **Step 2: Run the schema test to verify it fails**

Run: `uv run pytest tests/integration/test_phase2_discovery_database.py::test_provider_discovery_schema_is_append_only_and_has_no_secret_columns -q`

Expected: FAIL because the tables do not exist.

- [x] **Step 3: Add the minimum immutable schema**

Create each record with a UUID primary key and `created_at`. Store only public listing content and hashes. Bind a discovery run to the current Phase I profile/readiness/authority fingerprints and Phase II activation/restore generations. Give each source observation a unique `(provider_id, source_listing_id, content_fingerprint)` tuple. Give each job revision a unique `(job_record_id, content_fingerprint)` tuple. Make a verification bind one job revision, one selected location path, the relevant source-observation fingerprint, the Phase I snapshot fingerprints, and its expiry. Add SQLite update/delete rejection triggers for every new table.

- [x] **Step 4: Run the focused schema tests to verify they pass**

Run: `uv run pytest tests/integration/test_phase2_discovery_database.py -q`

Expected: PASS; `PRAGMA table_info` must show no `token`, `key`, `cookie`, `session`, `password`, `otp`, `submission`, or answer-wording columns.

- [x] **Step 5: Verify migration quality**

Run: `uv run ruff check src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0006_provider_discovery.py tests/integration/test_phase2_discovery_database.py && uv run mypy src && git diff --check`

Expected: all commands exit 0.

## Task 3: Implement fail-closed, bounded provider adapters

**Files:**
- Create: `src/job_search_cockpit/phase2/providers.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_provider_config.py`

**Consumes:** `ProviderCredentials`, `ProviderLimits`, and `ProviderRequest` from Task 1.

**Produces:** `ApifyProvider.fetch()` and `JSearchProvider.fetch()` returning `tuple[ProviderListing, ...]`.

- [x] **Step 1: Write the failing invalid-request test**

```python
def test_provider_request_rejects_a_listing_limit_above_the_pilot_cap() -> None:
    with pytest.raises(ValueError, match="listing limit exceeds the approved pilot cap"):
        ProviderRequest(
            provider_id="apify-linkedin",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=41,
            max_charge_usd=Decimal("0.10"),
        )
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_config.py::test_provider_request_rejects_a_listing_limit_above_the_pilot_cap -q`

Expected: FAIL because `ProviderRequest` does not yet validate limits.

- [x] **Step 3: Implement adapters with exact transport constraints**

Promote `httpx` from the development group to runtime dependencies. Use a single `httpx.Client` per manual run with `follow_redirects=False`, a 10-second connect timeout, a 90-second read timeout (to accommodate the selected Naukri Actor), and no retry wrapper.

`ApifyProvider.fetch()` must call the documented Actor-run endpoint only for these fixed Actor IDs:

```python
APIFY_LINKEDIN_ACTOR = "curious_coder/linkedin-jobs-scraper"
APIFY_NAUKRI_ACTOR = "automation-lab/naukri-scraper"
APIFY_GLASSDOOR_ACTOR = "valig/glassdoor-jobs-scraper"
```

Pass the provider token only in an `Authorization: Bearer` header. For an Actor that supports it, pass `maxTotalChargeUsd` at most `0.10` for micro-runs and at most `0.50` for the approved pilot. Reject an Actor response that exceeds the requested listing limit or lacks a stable listing identifier or canonical public URL.

`JSearchProvider.fetch()` must use only the user-supplied RapidAPI JSearch host and documented search endpoint, with `X-RapidAPI-Key` and `X-RapidAPI-Host` headers. Before merging this task, manually verify the exact endpoint and response schema in the connected RapidAPI console; record only the host and endpoint constant, never the key or an example response.

- [x] **Step 4: Run static configuration tests**

Run: `uv run pytest tests/unit/test_provider_config.py -q`

Expected: PASS; no test constructs a listing or invokes a provider.

- [x] **Step 5: Verify dependency and source checks**

Run: `uv lock --check && uv run ruff check src/job_search_cockpit/phase2/providers.py src/job_search_cockpit/phase2/discovery_types.py && uv run mypy src`

Expected: all commands exit 0.

## Task 4: Persist and deduplicate real provider observations

**Files:**
- Create: `src/job_search_cockpit/phase2/discovery.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/phase2/activation.py`
- Create: `tests/integration/test_phase2_live_discovery.py`

**Consumes:** active `Phase2ActivationService`, `Phase1MatchingPort`, provider adapters, and the Task 2 catalog tables.

**Produces:** `DiscoveryService.run_micro_pilot()` and `DiscoveryService.run_weekly_pilot()`.

- [x] **Step 1: Write the failing fail-closed activation test**

```python
def test_discovery_is_denied_when_phase_two_activation_is_unavailable(
    phase2_settings: Phase2Settings,
) -> None:
    service = DiscoveryService.unavailable_for_tests(phase2_settings)

    with pytest.raises(Phase2ActivationUnavailable, match="provider access is unavailable"):
        service.run_micro_pilot()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/integration/test_phase2_live_discovery.py::test_discovery_is_denied_when_phase_two_activation_is_unavailable -q`

Expected: FAIL because `DiscoveryService` does not exist.

- [x] **Step 3: Implement the manual orchestration boundary**

`run_micro_pilot()` must revalidate the active Phase II grant and Phase I activation snapshot before every provider request. It must request at most five LinkedIn listings, five Naukri listings, and one JSearch response. `run_weekly_pilot()` must enforce the approved 40/25/one-request and US$0.50 caps.

Persist each returned real public listing in one coordinator transaction: create an immutable observation, derive a posting identity from canonical public URL plus provider listing ID, create or link a job record, and append a new revision only when the normalized public-content fingerprint changes. Do not merge records using title similarity alone. A changed Phase I or Phase II generation before persistence aborts the transaction and records no authorization.

Keep the existing runtime preparation port as `VerifiedJobReadinessUnavailable`; do not replace it in this task.

- [x] **Step 4: Run the static fail-closed test**

Run: `uv run pytest tests/integration/test_phase2_live_discovery.py::test_discovery_is_denied_when_phase_two_activation_is_unavailable -q`

Expected: PASS without provider access or a listing payload.

- [x] **Step 5: Run the user-authorized real-data micro-run**

Run only after the user explicitly reconfirms live provider access in that execution turn:

```bash
JOB_SEARCH_LIVE_DISCOVERY=1 uv run pytest tests/integration/test_phase2_live_discovery.py::test_live_micro_pilot -q
```

Expected: at most five records per Apify Actor and one JSearch response are stored as real catalog observations; the test reports counts and provider IDs only, never credentials or job-description text. Do not execute this step automatically.

## Task 5: Issue only explicit, revalidated verified-job authorizations

**Files:**
- Create: `src/job_search_cockpit/phase2/verification.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/phase2/resume_safety.py`
- Test: `tests/integration/test_phase2_live_discovery.py`

**Consumes:** a persisted job revision, source-observation provenance, `Phase1MatchingPort`, `Phase2ActivationService`, and an explicit `VerifyCandidateCommand`.

**Produces:** `VerifiedJobAuthorizationService.verify()` and a runtime-only `VerifiedJobPreparationPort` implementation that returns authorizations only for verified current revisions.

- [x] **Step 1: Write the failing no-authorization-without-verification test**

```python
def test_unverified_discovery_cannot_authorize_resume_preparation(
    phase2_settings: Phase2Settings,
) -> None:
    port = CatalogVerifiedJobPreparationPort.unavailable(phase2_settings)

    with pytest.raises(ResumePreparationError, match="verified job readiness is unavailable"):
        port.authorization_for_resume("unknown-job")
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/integration/test_phase2_live_discovery.py::test_unverified_discovery_cannot_authorize_resume_preparation -q`

Expected: FAIL because the catalog-backed port does not exist.

- [x] **Step 3: Implement the explicit verification gate**

`VerifyCandidateCommand` must require the exact job revision ID, selected eligible location path, actor label, reason, and the confirmation text `VERIFY JOB FOR PHASE II PREPARATION`. The service must revalidate the active Phase I snapshot and Phase II activation generation, reject stale observations, profile changes, unresolved eligibility, unknown mandatory conditions, or a missing selected path, and append a verification record rather than updating prior state.

The produced `VerifiedJobPreparationAuthorization` must bind the catalog job/revision, authorization ID and nonce, expiry, selected location-path fingerprint, Phase I profile/readiness/authority fingerprints and generations, and Phase II activation/restore generations. Only this fully verified port may replace `VerifiedJobReadinessUnavailable` in runtime; if no current verification exists, it must return the identical unavailable error.

- [x] **Step 4: Run the focused static test**

Run: `uv run pytest tests/integration/test_phase2_live_discovery.py::test_unverified_discovery_cannot_authorize_resume_preparation -q`

Expected: PASS without a provider call or a listing payload.

- [x] **Step 5: Reconfirm a live verified listing manually**

Use only a persisted listing from the user-authorized micro-run. Show its safe public metadata in the authenticated local UI, obtain the exact verification confirmation, and run the focused integration check. Do not create a replacement listing, document, or application action.

## Task 6: Add local review surfaces and milestone verification

**Files:**
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_local_review.html`
- Modify: `tests/integration/test_phase2_activation_page.py`

**Consumes:** safe `DiscoveryRunSummary` and verification-status projections; no raw provider credential or full listing payload.

**Produces:** an authenticated read-only discovery status view and explicit verification action boundary. The existing finalisation control remains disabled without authorization.

- [x] **Step 1: Write the failing read-only route test**

```python
def test_review_page_shows_discovery_unavailable_without_a_verified_job(client) -> None:
    response = client.get("/phase-2/review")

    assert response.status_code == 200
    assert "Verified job readiness is unavailable" in response.text
    assert "Submit application" not in response.text
```

- [x] **Step 2: Run the route test to verify it fails only if the safe status projection is absent**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py::test_review_page_shows_discovery_unavailable_without_a_verified_job -q`

Expected: PASS initially or fail only after the route contract changes; do not alter the unavailable copy merely to force a red test.

- [x] **Step 3: Implement safe status display and CSRF verification action**

Display provider configuration status, last manual-run counts, and candidate/verification state through a service projection. Do not display credentials, full raw provider payloads, or provider request URLs containing query tokens. Add no provider-search POST route. The only state-changing route is candidate verification, protected by the existing local session and CSRF token; it can authorize neither an application submission nor document finalisation by itself.

- [x] **Step 4: Run focused route and safety checks**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py tests/integration/test_phase2_resume_runtime.py -q`

Expected: PASS; no route can submit an application or call a provider automatically.

- [x] **Step 5: Run milestone verification**

Run: `uv run ruff check src tests && uv run mypy src && git diff --check && uv run pytest -q`

Expected: Ruff, mypy, and whitespace checks exit 0. Report any launcher test blocked solely by the sandbox loopback-bind restriction separately from test failures.

## Plan self-review

- Spec coverage: Tasks 1–3 cover isolated credentials, bounded sources, and transport constraints; Tasks 2 and 4 cover immutable catalog persistence and deduplication; Task 5 covers explicit authorization; Task 6 covers authenticated status and no-submission behavior.
- Real-data rule: no task creates a listing payload or saved provider-response fixture. Only Task 4's explicit, user-reconfirmed micro-run contacts providers and stores returned public production records.
- Type consistency: Task 1 produces the types consumed by Tasks 3–4; Task 4 produces the persisted job revision consumed by Task 5; Task 5 produces the authorization consumed by existing Phase II safety services.
