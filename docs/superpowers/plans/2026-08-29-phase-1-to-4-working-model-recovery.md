# Phase I–IV Working Model Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore bounded Apify/JSearch discovery and connect real candidates to the existing verification, Phase III finalisation, and Phase IV backup workflow.

**Architecture:** Recover the earlier provider contracts as isolated adapters, but integrate them into the current runtime through a profile-driven, partial-failure discovery orchestrator. Add one candidate workflow boundary that derives reviewable eligibility and a job-specific requirement ledger from persisted public listings, then expose manual discovery, verification, and resume-start actions through the existing local FastAPI UI. Preserve every current Phase I, Phase III, Phase IV, append-only, CSRF, authority-fence, and no-submission boundary.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy 2, SQLite/Alembic, httpx, pytest, Ruff, mypy, python-docx, WeasyPrint, Google Drive REST.

## Global Constraints

- Apify and JSearch are the production discovery sources; no Vanguard-only adapter is introduced.
- Provider discovery is manual only; no scheduler, background task, polling loop, or automatic retry is added.
- The acceptance micro-run is capped at five results and US$0.10 per enabled Apify Actor, plus one JSearch request capped at 25 listings.
- `APIFY_API_TOKEN` and `JSEARCH_API_KEY` are loaded only from environment or a strict git-ignored `.env`; they are never printed, logged, committed, persisted, or returned to the browser.
- A provider failure must not discard another provider's valid results.
- Every provider call and persistence boundary revalidates Phase I inputs and Phase II activation.
- No application form, employer contact, sign-in, submission, broad browser automation, or automatic Drive action is added.
- Phase IV real OAuth consent, Keychain storage, folder creation, and upload remain explicit user actions.
- Use `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache` for all `uv` commands.
- Preserve the original damaged repository; modify only `/private/tmp/job-search-cockpit-phase2-recovery`.

## File responsibility map

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/provider_config.py` | Strict provider secret loading and immutable caps. |
| `src/job_search_cockpit/phase2/discovery_types.py` | Provider request, listing, failure, and result contracts. |
| `src/job_search_cockpit/phase2/providers.py` | Apify/JSearch HTTPS request preparation and response normalization. |
| `src/job_search_cockpit/phase2/discovery.py` | Profile-driven plans, provider fault isolation, append-only persistence, status views. |
| `src/job_search_cockpit/phase2/candidates.py` | Current candidate read model, deterministic eligibility review, requirement-ledger issuance. |
| `src/job_search_cockpit/phase2/runtime.py` | Runtime wiring and provider client lifetime. |
| `src/job_search_cockpit/web/routes/phase2.py` | CSRF-protected manual discovery, verification, and resume-start routes. |
| `src/job_search_cockpit/web/templates/phase2_local_review.html` | Candidate list and enabled workflow actions. |
| `src/job_search_cockpit/web/static/app.css` | Accessible candidate/action layout using existing visual tokens. |
| `tests/unit/test_providers.py` | Provider contract, cap, redaction, URL, and schema tests. |
| `tests/unit/test_candidate_workflow.py` | Eligibility, requirement extraction, and ledger tests. |
| `tests/integration/test_phase2_discovery_runtime.py` | Authority fences, partial failures, persistence, and deduplication. |
| `tests/integration/test_phase2_discovery_routes.py` | Manual discovery and candidate action route tests. |
| `tests/e2e/test_phase1_to_phase4_working_model.py` | One deterministic Phase I→IV local workflow. |
| `docs/superpowers/reviews/2026-08-29-phase-1-to-4-working-model-acceptance.md` | Automated and live acceptance evidence without secrets. |

---

### Task 1: Recover strict provider contracts and adapters

**Files:**
- Create: `src/job_search_cockpit/phase2/provider_config.py`
- Create: `src/job_search_cockpit/phase2/discovery_types.py`
- Create: `src/job_search_cockpit/phase2/providers.py`
- Create: `tests/unit/test_providers.py`

**Interfaces:**
- Consumes: current `httpx` dependency and public Apify/JSearch contracts.
- Produces: `ProviderCredentials`, `ProviderLimits`, `ProviderRequest`, `ProviderListing`, `ProviderOutcome`, `ApifyProvider`, `JSearchProvider`, and `create_provider_http_client()`.

- [ ] **Step 1: Write failing secret and cap tests**

```python
def test_credentials_are_redacted_and_env_rejects_unknown_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    credentials = ProviderCredentials.from_environment({}, dotenv_path=env)
    assert "a" not in repr(credentials)
    assert "j" not in repr(credentials)

    env.write_text("HOME=x\n", encoding="utf-8")
    with pytest.raises(ProviderConfigurationError, match="unsupported key"):
        read_provider_env_file(env)


def test_micro_apify_request_rejects_cost_above_ten_cents() -> None:
    with pytest.raises(ValueError, match="micro-run cap"):
        ProviderRequest("apify-linkedin", "Senior Product Manager", "Hyderabad", 5,
                        Decimal("0.11"))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_providers.py -q`  
Expected: FAIL because the recovered provider modules do not exist.

- [ ] **Step 3: Implement strict configuration and frozen request types**

Implement an allowlist containing only `APIFY_API_TOKEN` and
`JSEARCH_API_KEY`; redact both dataclass fields with `repr=False`; reject empty,
duplicate, or unknown dotenv keys. Define these exact limits:

```python
@dataclass(frozen=True, slots=True)
class ProviderLimits:
    linkedin_listing_limit: int = 40
    naukri_listing_limit: int = 25
    glassdoor_listing_limit: int = 25
    jsearch_listing_limit: int = 25
    max_apify_charge_usd: Decimal = Decimal("0.50")
    micro_listing_limit: int = 5
    micro_apify_charge_usd: Decimal = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    provider_id: str
    listings: tuple[ProviderListing, ...] = ()
    failure_code: str | None = None
```

Validate non-empty queries/locations, per-provider item limits, and Apify cost
limits in `ProviderRequest.__post_init__`.

- [ ] **Step 4: Write failing adapter request and response tests**

Cover exact HTTPS endpoints, `maxItems`, `maxTotalChargeUsd`, no redirects,
10-second connect timeout, 90-second read timeout, listing-count overflow,
malformed JSON shapes, stable IDs, and canonical public listing hosts. Test both
the published JSearch v3 response envelope and a bounded compatibility envelope
only if the current API documentation confirms both.

```python
def test_apify_micro_request_contains_item_and_charge_caps() -> None:
    prepared = ApifyProvider(APIFY_LINKEDIN_ACTOR).prepare(
        ProviderRequest("apify-linkedin", "Senior Product Manager", "Hyderabad", 5,
                        Decimal("0.10"))
    )
    assert prepared.params["maxItems"] == "5"
    assert prepared.params["maxTotalChargeUsd"] == "0.10"
    assert prepared.url.startswith("https://api.apify.com/v2/acts/")


def test_jsearch_rejects_more_jobs_than_requested() -> None:
    response = httpx.Response(200, json={"data": [_job(index) for index in range(6)]})
    with pytest.raises(ProviderResponseError, match="listing limit"):
        JSearchProvider().parse(response, listing_limit=5, retrieved_at=NOW)
```

- [ ] **Step 5: Implement minimal source adapters**

Recover useful parsing helpers from commits `73f4b05`, `a6d3b52`, `4f15d5b`,
`1f2613c`, and `79797f9`, then update them to the verified current contracts.
Authentication headers are constructed only inside `fetch()` and error messages
use bounded codes: `authentication_failed`, `quota_or_cost_limit`, `timeout`,
`provider_unavailable`, `schema_mismatch`, or `invalid_listing`.

- [ ] **Step 6: Verify Task 1 and commit**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_providers.py -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src/job_search_cockpit/phase2/provider_config.py src/job_search_cockpit/phase2/discovery_types.py src/job_search_cockpit/phase2/providers.py tests/unit/test_providers.py`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src/job_search_cockpit/phase2/provider_config.py src/job_search_cockpit/phase2/discovery_types.py src/job_search_cockpit/phase2/providers.py`

```bash
git add src/job_search_cockpit/phase2/provider_config.py src/job_search_cockpit/phase2/discovery_types.py src/job_search_cockpit/phase2/providers.py tests/unit/test_providers.py
git commit -m "feat: restore bounded Apify and JSearch adapters"
```

### Task 2: Restore profile-driven discovery with independent provider outcomes

**Files:**
- Modify: `src/job_search_cockpit/phase2/discovery.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Create: `tests/integration/test_phase2_discovery_runtime.py`
- Modify: `tests/integration/test_phase2_live_discovery.py`

**Interfaces:**
- Consumes: Task 1 provider interfaces; `Phase1ActivationInputs`; existing `Phase2MutationCoordinator` and discovery tables.
- Produces: `DiscoveryService.run_micro_pilot() -> DiscoveryResult`, `DiscoveryService.status_view() -> DiscoveryStatusView`, and `DiscoveryStatusView.provider_failures`.

- [ ] **Step 1: Write failing query-planning and partial-failure tests**

```python
def test_micro_plans_cover_active_profile_roles_and_locations(runtime) -> None:
    plans = runtime.discovery_service.plans_for_test(micro=True)
    assert {plan.request.location_id for plan in plans} == {
        "Hyderabad", "Bengaluru", "Singapore"
    }
    assert all(plan.request.listing_limit <= 5 for plan in plans if plan.provider_id.startswith("apify"))


def test_one_provider_failure_preserves_other_provider_results(runtime, fake_providers) -> None:
    fake_providers["apify-linkedin"].failure_code = "timeout"
    fake_providers["jsearch"].listings = (VALID_LISTING,)
    result = runtime.discovery_service.run_micro_pilot()
    assert result.provider_failures == {"apify-linkedin": "timeout"}
    assert result.observation_count == 1
```

- [ ] **Step 2: Run focused integration tests and verify RED**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase2_discovery_runtime.py -q`  
Expected: FAIL because current discovery always raises the official-instance error.

- [ ] **Step 3: Implement deterministic query planning**

Build queries from the active `SearchProfileSnapshot.payload`. Preserve profile
order, deduplicate identical role/location pairs, and allocate at most the
micro cap per provider call. Do not silently use only the first role/location.
Expose `plans_for_test(micro: bool)` only as a pure plan builder with no secret
loading or network access.

- [ ] **Step 4: Implement fault-isolated execution and append-only persistence**

For each plan: revalidate activation, call one adapter, convert its bounded
exception to one `ProviderOutcome`, and continue. Revalidate the complete Phase I
snapshot and Phase II generation inside the coordinator transaction. Persist a
run even when all outcomes are empty or failed, persist only accepted listings,
and return counts plus failure codes. Retain `_persist_listing()` identity and
content fingerprint behavior.

- [ ] **Step 5: Wire runtime configuration without leaking credentials**

`prepare_phase2_runtime()` passes `settings.data_dir / ".env"` only when present
and owns one provider HTTP client factory. `Phase2Runtime.close()` closes any
provider client created for a run. Configuration status may report available,
missing, or partial but never return a credential value.

- [ ] **Step 6: Verify Task 2 and commit**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit/test_providers.py tests/integration/test_phase2_discovery_runtime.py tests/integration/test_phase2_discovery_database.py tests/integration/test_phase2_live_discovery.py -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src/job_search_cockpit/phase2/discovery.py src/job_search_cockpit/phase2/runtime.py tests/integration/test_phase2_discovery_runtime.py tests/integration/test_phase2_live_discovery.py`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src`

```bash
git add src/job_search_cockpit/phase2/discovery.py src/job_search_cockpit/phase2/runtime.py tests/integration/test_phase2_discovery_runtime.py tests/integration/test_phase2_live_discovery.py
git commit -m "feat: restore profile-driven provider discovery"
```

### Task 3A: Add the Phase I local-manual fact-choice boundary

This task follows
`docs/superpowers/specs/2026-08-30-phase-2-local-manual-mapping-amendment.md`.
The earlier proposal to store `job.*` IDs in the Phase III ledger is retired.

**Files:**
- Modify: `src/job_search_cockpit/phase1_contract/snapshots.py`
- Create: `src/job_search_cockpit/phase1_contract/retrieval.py`
- Modify: `src/job_search_cockpit/phase1_contract/service.py`
- Modify: `src/job_search_cockpit/phase1_contract/matching_port.py`
- Modify: `src/job_search_cockpit/ports.py`
- Modify: `src/job_search_cockpit/storage/models.py`
- Create: `alembic/versions/<revision>_local_manual_disclosure_budget.py`
- Create: `tests/unit/test_phase1_matching_retrieval.py`
- Modify: `tests/integration/test_phase1_contract.py`

**Produces:** the approved job-level bounded semantic matching bundle, one
durable disclosure authorization, and a complete non-pageable relevant fact set
with at most 32 unique choices.

- [ ] Write RED contract tests for bounded taxonomy queries, stable ordering,
  confidential/stale/unsupported/unrelated exclusion, cap/incompleteness, and
  revalidation failure after authority or fact drift.
- [ ] Extend the frozen query/fact-set types additively with controlled semantic
  predicates, retrieval-policy metadata, completeness state, and fingerprints.
- [ ] Implement Phase I-owned relevance selection and eligibility filtering from
  the frozen taxonomy/retrieval policy and acceptance corpus.
- [ ] Enforce job/session-wide requirement, taxonomy, unique-fact, and relevance
  edge budgets. Count all authorization outcomes in a monotonic disclosure
  epoch across sessions. Record/reuse one exact disclosure authorization in the
  Phase I audit and recovery ledgers; reject a changed query for the same scope.
- [ ] Implement the wording-free retrieval manifest: opaque refs, relevance
  edges, safe-wording hashes, exact Phase I fence, and immutable fingerprint.
  Release safe wording only after the same logical payload digest is authorized
  by Phase II and Phase I, and verify every released wording hash.
- [ ] Add the explicit reason/confirmation-gated command that opens a new
  disclosure epoch without deleting earlier history.
- [ ] Expose the operations through `InternalPhase1MatchingPort` and the
  protocol without changing any existing method shape.
- [ ] Verify focused tests, Ruff, mypy, and `git diff --check`; commit and review.

### Task 3B: Build current candidates and constrained local-manual assessments

**Files:**
- Create: `src/job_search_cockpit/phase2/candidates.py`
- Create: `tests/unit/test_candidate_workflow.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/phase2/assessment.py`
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/<revision>_local_manual_mapping_attempts.py`
- Modify: `tests/integration/test_phase2_discovery_runtime.py`
- Create: `tests/integration/test_phase2_manual_mapping.py`

**Produces:** current candidate reviews, bounded public requirement extraction,
server-validated manual mappings, and append-only assessment publication.

- [ ] Write RED candidate gate and requirement-extraction tests.
- [ ] Apply locked profile rules without guessing; score, confidence, and gate
  state remain separate. Missing descriptions and uncertain mandatory clauses
  remain blocking.
- [ ] Derive stable public job-requirement IDs only for Phase II assessment.
- [ ] Accept only a Phase I choice or `none`, plus closed relation/reason pairs;
  reload the revision and choices and reject altered IDs or spans.
- [ ] Revalidate the selected Phase I projection, calculate the existing fixed
  score/band/confidence, and publish through `AssessmentPublicationService`.
- [ ] Bind publication to the exact expected matching/projection snapshot;
  validate mapping membership and revalidate immediately before and inside the
  mutation while persisting the expected authority fence.
- [ ] Persist Phase II mapping attempts/events and the recovery-ledger
  authorization with attempt ID/nonce, exact payload digest, selected location,
  coverage, rubric/config/schema versions, both stores' generations, expiry,
  and one-use terminal lifecycle. Phase I and Phase II records must bind the
  same digest; consuming/terminal attempts deny replay.
- [ ] Treat retries as new attempt IDs/nonces/digests bound to the same immutable
  retrieval manifest. Only an unconsumed exact reload may re-release wording.
- [ ] Verify focused tests, Ruff, mypy, and `git diff --check`; commit and review.

### Task 3C: Issue an assessment-bound canonical Phase III ledger

**Files:**
- Modify: `src/job_search_cockpit/phase2/candidates.py`
- Modify: `src/job_search_cockpit/phase2/verification.py`
- Modify: `tests/unit/test_candidate_workflow.py`
- Modify: `tests/unit/test_phase2_verification.py`
- Modify: `tests/integration/test_phase2_manual_mapping.py`

**Produces:** idempotent `Phase2ResumeRequirementLedger` records containing only
revalidated Phase I canonical fact keys, bound to the current assessment and
mapping evidence through their fingerprint.

- [ ] Write RED tests proving `job.*` IDs never enter the resume ledger and an
  unsupported mandatory requirement blocks issuance.
- [ ] Load only current, authority-fenced assessment mappings; require direct
  approved evidence for every mandatory requirement.
- [ ] Dedupe canonical Phase I keys in first-requirement order and bind the
  fingerprint to job revision, assessment, mappings, evidence refs, canonical
  keys, and active Phase II generations.
- [ ] Reuse an identical ledger; issue a new ledger for a changed revision or
  assessment. Verification reloads this state and ignores posted eligibility.
- [ ] Verify all Task 3 tests, Phase II scoring/verification suites, Ruff, mypy,
  and `git diff --check`; commit and review.

### Task 4: Expose manual discovery and usable candidate actions in the local UI

**Files:**
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_local_review.html`
- Modify: `src/job_search_cockpit/web/static/app.css`
- Create: `tests/integration/test_phase2_discovery_routes.py`

**Interfaces:**
- Consumes: Tasks 2–3 services and current CSRF/session security.
- Produces: `POST /phase-2/discovery-runs`, candidate cards on
  `GET /phase-2/review`, constrained mapping GET/POST actions, existing
  `POST /phase-2/verify`, and existing `POST /phase-2/resume-reviews` as one
  visible workflow.

- [ ] **Step 1: Write failing route and UI tests**

```python
def test_manual_discovery_requires_csrf_and_renders_real_candidate(app) -> None:
    assert app.client.post("/phase-2/discovery-runs").status_code == 403
    response = app.post("/phase-2/discovery-runs", data={})
    assert response.status_code == 303
    page = app.get("/phase-2/review")
    assert "Senior Product Manager" in page.text
    assert "Map approved evidence" in page.text
    assert "Verify selected candidate" not in candidate_button_fragment(page.text)


def test_ineligible_candidate_has_no_verification_form(app) -> None:
    page = app.get("/phase-2/review")
    assert 'data-candidate="ineligible"' in page.text
    assert "Eligibility must be resolved" in page.text
```

- [ ] **Step 2: Run route tests and verify RED**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase2_discovery_routes.py -q`  
Expected: FAIL because no discovery route or candidate view exists.

- [ ] **Step 3: Add the manual discovery POST route**

Validate CSRF, call `run_micro_pilot()`, suppress no errors silently, and redirect
back to `/phase-2/review` with a bounded status code stored in the local session
or recomputed from durable run metadata. The browser never accepts arbitrary
provider, query, URL, item-count, or cost inputs.

- [ ] **Step 4: Render candidate cards and verification forms**

Each current candidate displays employer, title, location, source link, score,
confidence, gate state, and reason codes. Eligible candidates without a current
assessment/ledger render **Map approved evidence**. Only after mapping produces
a current assessment and canonical ledger does the server render the exact
verification form fields: revision ID, selected approved location, actor
`Varun`, user-written reason, and exact confirmation
`VERIFY JOB FOR PHASE II PREPARATION`. Eligibility and unknown codes are loaded
server-side, never trusted from hidden fields. After successful verification,
render **Prepare tailored resume** posting the stable job ID to
`/phase-2/resume-reviews`.

- [ ] **Step 4A: Render and submit constrained local-manual mappings**

Add a CSRF-protected POST that obtains the wording-free Phase I retrieval
manifest, canonicalizes the logical payload, and creates the matching Phase II
mapping-attempt and Phase I disclosure authorizations. Verify the released
wording hashes, then redirect to an authenticated no-store mapping view for one
current revision and one server-loaded public requirement. Render only the
authorized complete Phase I relevant fact set, **No approved evidence**, and
closed relation/reason controls. Mapping POST reloads the revision, requirement,
authorization, and exact choice snapshot and rejects forged, consumed, expired,
or stale identifiers. Candidate verification remains absent until the resulting
current assessment and canonical ledger exist.

Add a separate authenticated/CSRF-protected disclosure-budget status and epoch
renewal action. Renewal requires a reason and exact confirmation and is never
performed automatically by discovery, mapping, retry, restart, or restore.

- [ ] **Step 5: Issue the requirement ledger before verification**

The verification route loads the current `CandidateReview`, rejects altered
hidden values, calls `issue_requirement_ledger()` for the same revision, then
calls the existing authorization service. Do not infer eligibility from form
input alone.

- [ ] **Step 6: Update stale UI wording and accessible layout**

Remove claims that Drive is unimplemented and that provider discovery is a
future system. Preserve semantic headings, form labels, keyboard focus, minimum
44px actions, current color contrast, responsive one-column fallback, and no
secret/raw-description rendering.

- [ ] **Step 7: Verify Task 4 and commit**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration/test_phase2_discovery_routes.py tests/integration/test_phase3_routes.py tests/integration/test_phase4_routes.py tests/integration/test_web_security.py -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py tests/integration/test_phase2_discovery_routes.py`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src`

```bash
git add src/job_search_cockpit/phase2/runtime.py src/job_search_cockpit/web/routes/phase2.py src/job_search_cockpit/web/templates/phase2_local_review.html src/job_search_cockpit/web/static/app.css tests/integration/test_phase2_discovery_routes.py
git commit -m "feat: connect discovery candidates to resume review"
```

### Task 5: Prove the complete local Phase I–IV workflow

**Files:**
- Create: `tests/e2e/test_phase1_to_phase4_working_model.py`
- Modify: `tests/support/phase3.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete local runtime and injected fake external providers/Drive clients.
- Produces: one deterministic acceptance test proving every internal handoff without network, Keychain, OAuth, or spend.

- [ ] **Step 1: Write the failing full-flow acceptance test**

```python
def test_phase1_to_phase4_working_model(authenticated_cockpit) -> None:
    assert authenticated_cockpit.get("/search-profile").status_code == 200
    authenticated_cockpit.post("/phase-2/discovery-runs", data={})
    review = authenticated_cockpit.get("/phase-2/review")
    revision_id, job_id = select_first_eligible_candidate(review)
    complete_local_manual_mapping(authenticated_cockpit, revision_id)
    authenticated_cockpit.post("/phase-2/verify", data=verification_form(revision_id))
    started = authenticated_cockpit.post("/phase-2/resume-reviews", data={"job_id": job_id})
    assert started.status_code == 303
    finalised = finalise_with_test_headshot(authenticated_cockpit, started)
    assert ".docx" in finalised.text and ".pdf" in finalised.text
    backup = request_fake_drive_backup(authenticated_cockpit, finalised)
    assert "backed_up" in backup.text
```

- [ ] **Step 2: Run the acceptance test and verify RED**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/e2e/test_phase1_to_phase4_working_model.py -q`  
Expected: FAIL at the earliest unconnected handoff.

- [ ] **Step 3: Add only missing test seams and repair the earliest failing gate**

Inject provider and Drive fakes through runtime constructors; do not add
production bypass flags. Re-run after each change until the test reaches the
next gate. Use valid accepted Phase I facts and a public test listing, and assert
that the produced requirement ledger maps only through the existing Phase I
projection boundary.

- [ ] **Step 4: Document the user workflow and manual boundaries**

Update README launcher instructions, provider configuration status, micro-run
caps, discovery button, candidate verification, 15-minute authorization,
headshot selection, finalisation, and optional Drive consent/retry. Clearly mark
application submission as unavailable and real Google actions as manual.

- [ ] **Step 5: Run all local quality gates**

Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/unit -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/integration -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run pytest tests/e2e tests/document -q`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run ruff check .`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run mypy src`  
Run: `UV_CACHE_DIR=/private/tmp/job-search-cockpit-uv-cache uv run alembic -c alembic_phase2.ini heads`  
Run: `git diff --check`

Expected: every command exits zero; Alembic reports exactly one Phase II head.

- [ ] **Step 6: Commit the local working model**

```bash
git add tests/e2e/test_phase1_to_phase4_working_model.py tests/support/phase3.py README.md
git commit -m "test: prove Phase I through IV working model"
```

### Task 6: Run bounded live acceptance and start the cockpit

**Files:**
- Create: `docs/superpowers/reviews/2026-08-29-phase-1-to-4-working-model-acceptance.md`
- Modify only if a real contract defect is proven: provider files and their tests.

**Interfaces:**
- Consumes: local git-ignored credentials, current accepted profile, active Phase II grant, and Task 5 passing build.
- Produces: persisted real public listing observations, a running local cockpit, and a redacted acceptance record.

- [ ] **Step 1: Migrate credentials without exposing them**

Verify only the names `APIFY_API_TOKEN` and `JSEARCH_API_KEY` exist in the
original local `.env`. Copy that file to the recovery workspace with mode 0600,
ensure `.gitignore` excludes it, and confirm `git status --short` does not list
it. Never display or shell-source its contents.

- [ ] **Step 2: Confirm live caps and active profile before spending**

Use a read-only plan/status command to record enabled providers, query count,
locations, five-item Apify cap, US$0.10 per-Actor cap, and 25-item JSearch cap.
Abort if any request lacks an explicit cap or uses a location outside the active
profile.

- [ ] **Step 3: Run one live manual micro discovery**

Start the cockpit, trigger exactly one micro-run through the same service used
by the UI, and record only provider outcome codes, counts, revision count, and
timestamp. Do not print raw payloads or secrets. If an Actor contract has drifted,
fix its adapter and fixture first, rerun all Task 1–5 gates, then retry only that
provider within the same cap.

- [ ] **Step 4: Complete one real candidate through local Phase III acceptance**

Open `/phase-2/review`, choose one current eligible candidate, confirm the
location and eligibility judgment, provide the verification reason and exact
phrase, review supported/gap requirements, and finalise only after the user
approves the resume wording and supplies the local headshot path. Confirm the
PDF and DOCX exist and their recorded sizes/hashes match.

- [ ] **Step 5: Leave real Drive acceptance at its explicit user boundary**

Show the existing **Back up to Google Drive** action. Perform OAuth consent and
upload only if the user initiates them in the browser. Otherwise verify the
local mocked Phase IV suite and record the real Drive check as manual pending,
not as failed development and not as completed.

- [ ] **Step 6: Write the redacted acceptance record and final verification**

Record commit, test totals, lint/type/migration results, provider counts and
bounded failures, selected job/revision metadata, Phase III artifact metadata,
Drive state, manual steps, and launcher status. Exclude secrets, raw payloads,
resume text, OAuth data, and unrestricted paths.

Run: `git status --short --branch`  
Run: `git diff --check`  
Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<active-port>/health`

- [ ] **Step 7: Commit the acceptance record**

```bash
git add docs/superpowers/reviews/2026-08-29-phase-1-to-4-working-model-acceptance.md
git commit -m "docs: record Phase I-IV working model acceptance"
```
