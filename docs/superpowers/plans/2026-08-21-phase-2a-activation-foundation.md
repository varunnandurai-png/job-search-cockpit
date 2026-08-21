# Phase II-A Activation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the fail-closed Phase I contract and revocable Phase II activation foundation, without provider access, job ingestion, scoring, or document generation.

**Architecture:** Phase I remains the only owner of career facts, profile, readiness, and acceptance evidence. It exposes immutable, fingerprinted application snapshots through a typed internal `Phase1MatchingPort`; Phase II owns a separate owner-only SQLite catalog, recovery ledger, and activation grant. The browser only reports activation state and records an explicit user confirmation; it cannot enable providers or run discovery.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic, SQLite, Jinja2, pytest, Ruff, mypy, and Playwright.

## Global Constraints

- Keep Phase I's active search-profile snapshot authoritative; never hard-code its current version-2 ₹50L Hyderabad or ₹55L Bengaluru floor.
- Phase II must never read Phase I tables directly; only `Phase1MatchingPort` application-service calls may supply Phase I state.
- Phase II data, backups, recovery ledger, and locks remain owner-only under `~/Library/Application Support/JobSearchCockpit/` and stay out of Git.
- Bind only to `127.0.0.1`; retain existing launch-session, CSRF, Host, cache, CSP, and escaping protections.
- Do not contact providers, fetch URLs, use browser automation against job sources, dispatch Codex packets, ingest jobs, score jobs, shortlist jobs, or generate application material in this slice.
- An unavailable, malformed, stale, restored, or generation-mismatched Phase I snapshot denies activation and all future live actions.
- Phase I acceptance is durable, versioned, and user-confirmed. A chat acknowledgement alone is never silently reconstructed at runtime.
- Tests use synthetic Phase I fixtures and temporary Phase I/II directories only; they never read the live vault, Application Support vault, or real profile documents.
- Every state change is append-only or superseding, guarded by an expected version, preceded by a verified safety copy, and reflected in a hash-chained recovery ledger.

## File Structure

```text
src/job_search_cockpit/
├── phase1_contract/
│   ├── __init__.py
│   ├── snapshots.py              # Immutable snapshot models and canonical fingerprints
│   ├── service.py                # Phase I internal snapshot producer
│   └── matching_port.py          # Phase2-facing adapter; never exposes ORM tables
├── phase2/
│   ├── __init__.py
│   ├── config.py                 # Separate Phase II paths and contract constants
│   ├── database.py               # Phase II engine, migration, and permissions
│   ├── models.py                 # Phase II activation-only records
│   ├── mutation.py               # Phase II lock, backup, restore generation, serialization
│   ├── recovery_ledger.py        # Phase II hash-chained activation history
│   ├── activation.py             # Grant issuance, validation, suspension, views
│   └── types.py                  # Commands, errors, and immutable views
├── web/routes/phase2.py
└── web/templates/phase2_activation.html
alembic/versions/0002_phase1_contract.py
alembic_phase2/
├── env.py
└── versions/0001_phase2_activation.py
alembic_phase2.ini
tests/
├── fixtures/phase1_contract/
├── integration/test_phase1_contract.py
├── integration/test_phase2_activation.py
├── integration/test_phase2_restore.py
├── integration/test_phase2_activation_page.py
└── e2e/test_phase2_activation_flow.py
```

## Task 1: Isolate Phase II storage and test fixtures

**Files:**

- Modify: `src/job_search_cockpit/config.py`
- Create: `src/job_search_cockpit/phase2/__init__.py`
- Create: `src/job_search_cockpit/phase2/config.py`
- Create: `src/job_search_cockpit/phase2/database.py`
- Create: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2.ini`
- Create: `alembic_phase2/env.py`
- Create: `alembic_phase2/versions/0001_phase2_activation.py`
- Modify: `tests/conftest.py`
- Modify: `tests/support/database.py`
- Create: `tests/integration/test_phase2_database.py`

**Interfaces:**

- Produces: `Phase2Settings`, `phase2_database_path`, `phase2_backup_dir`, `phase2_lock_path`, `create_phase2_engine(settings) -> Engine`, `upgrade_phase2_database(url: str) -> None`, and temporary `phase2_settings` test fixtures.
- Consumes: `Settings.data_dir` only for the protected parent directory; no Phase I model, engine, session, or table object.

- [ ] **Step 1: Write failing isolation tests**

```python
def test_phase2_database_is_separate_and_owner_only(phase2_settings: Phase2Settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    assert phase2_settings.database_path != Settings(data_dir=phase2_settings.data_dir).database_path
    assert stat.S_IMODE(phase2_settings.database_path.stat().st_mode) == 0o600
    assert sqlite_integrity(phase2_settings.database_path) == "ok"


def test_phase2_schema_has_no_phase1_tables(phase2_settings: Phase2Settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    with sqlite3.connect(phase2_settings.database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "claims" not in tables
    assert {"phase2_authority_state", "phase2_activation_grants"} <= tables
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `uv run pytest tests/integration/test_phase2_database.py -v`

Expected: collection fails because `job_search_cockpit.phase2` does not exist.

- [ ] **Step 3: Implement the minimal separate catalog schema**

Create a Phase II Alembic environment that uses `Phase2Base.metadata`, not `storage.models.Base.metadata`. `Phase2Settings` resolves `job_catalog.sqlite3`, `job-catalog-backups/`, `job-catalog.lock`, and `job-catalog-recovery.jsonl` beneath the protected Application Support directory. The initial migration creates only:

```python
class Phase2AuthorityState(Phase2Base):
    __tablename__ = "phase2_authority_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    restore_generation: Mapped[int] = mapped_column(default=0)
    revocation_generation: Mapped[int] = mapped_column(default=0)
    activation_generation: Mapped[int] = mapped_column(default=0)


class Phase2ActivationGrant(Phase2Base):
    __tablename__ = "phase2_activation_grants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))  # active, suspended, revoked
    snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    snapshot_fingerprint: Mapped[str] = mapped_column(String(64))
    confirmation: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))
    expected_activation_generation: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

Add database constraints that allow only one active grant and reject `UPDATE` or `DELETE` on grant rows. Later tasks add append-only event tables; no provider, job, or fact table belongs in this migration.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/integration/test_phase2_database.py -v && uv run ruff check src tests && uv run mypy src`

Expected: pass.

- [ ] **Step 5: Commit the isolated storage foundation**

```bash
git add src/job_search_cockpit/config.py src/job_search_cockpit/phase2 alembic_phase2 alembic_phase2.ini tests/conftest.py tests/support/database.py tests/integration/test_phase2_database.py
git commit -m "feat: add isolated Phase II catalog foundation"
```

## Task 2: Persist Phase I acceptance and produce immutable snapshots

**Files:**

- Modify: `src/job_search_cockpit/storage/models.py`
- Create: `alembic/versions/0002_phase1_contract.py`
- Create: `src/job_search_cockpit/phase1_contract/__init__.py`
- Create: `src/job_search_cockpit/phase1_contract/snapshots.py`
- Create: `src/job_search_cockpit/phase1_contract/service.py`
- Modify: `src/job_search_cockpit/ports.py`
- Modify: `src/job_search_cockpit/launcher.py`
- Modify: `tests/support/web.py`
- Create: `tests/integration/test_phase1_contract.py`

**Interfaces:**

- Produces: `Phase1AcceptanceReceiptSnapshot`, `Phase1ReadinessSnapshot`, `SearchProfileSnapshot`, `Phase1ContractUnavailable`, `Phase1ContractService.record_acceptance(...)`, and `Phase1ContractService.snapshot_activation_inputs() -> Phase1ActivationInputs`.
- Consumes: Phase I `ReadinessService`, `SearchProfileService`, recovery-ledger high-water mark, current schema, and current committed import state through Phase I application services only.

- [ ] **Step 1: Write failing snapshot tests**

```python
def test_acceptance_snapshot_binds_exact_verified_state(approved_vault) -> None:
    contract = Phase1ContractService(approved_vault.coordinator, build_metadata("test-build"))
    receipt = contract.record_acceptance(
        acceptance_run_id="run-118-pass",
        result_fingerprint="a" * 64,
        actor="Varun",
        confirmation="I accept the Phase I acceptance receipt.",
    )
    inputs = contract.snapshot_activation_inputs()
    assert inputs.acceptance_receipt.id == receipt.id
    assert inputs.readiness.ready_for_phase_2 is True
    assert inputs.profile.version_number == 2
    assert len(inputs.readiness.source_hashes) == 4


def test_any_missing_or_incomplete_phase1_input_fails_closed(vault_settings) -> None:
    contract = unaccepted_contract(vault_settings)
    with pytest.raises(Phase1ContractUnavailable, match="acceptance"):
        contract.snapshot_activation_inputs()
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `uv run pytest tests/integration/test_phase1_contract.py -v`

Expected: collection fails because `job_search_cockpit.phase1_contract` does not exist.

- [ ] **Step 3: Add the Phase I durable contract records and canonical snapshot types**

Create `phase1_acceptance_receipts` and singleton `phase1_authority_state` in migration `0002_phase1_contract.py`. An acceptance receipt must contain application build, schema revision, suite version, successful run ID, result, result fingerprint, restore high-water mark, actor, confirmation, and acceptance time. It is immutable; supersession creates another row and increments the authority generation.

Use frozen Pydantic models with canonical JSON serialization:

```python
class Phase1ReadinessSnapshot(BaseModel, frozen=True):
    contract_version: Literal["phase1.matching.v1"]
    ready_for_phase_2: bool
    import_run_id: UUID
    source_hashes: dict[str, str]
    active_profile_version: int
    readiness_generation: int
    authority_high_water_mark: int
    restore_generation: int
    fingerprint: str


class SearchProfileSnapshot(BaseModel, frozen=True):
    version_number: int
    payload: SearchProfilePayload
    active_profile_generation: int
    fingerprint: str
```

The producer queries its own Phase I store internally, rejects any missing latest complete four-source run or readiness blocker, and returns only immutable views. It must never put career claim wording, confidential data, or a SQLAlchemy row in an activation snapshot.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/integration/test_phase1_contract.py tests/integration/test_readiness.py tests/integration/test_search_profile_versioning.py -v && uv run ruff check src tests && uv run mypy src`

Expected: pass.

- [ ] **Step 5: Commit the durable Phase I contract**

```bash
git add src/job_search_cockpit/storage/models.py alembic/versions/0002_phase1_contract.py src/job_search_cockpit/phase1_contract src/job_search_cockpit/ports.py src/job_search_cockpit/launcher.py tests/support/web.py tests/integration/test_phase1_contract.py
git commit -m "feat: expose immutable Phase I activation snapshots"
```

## Task 3: Prove the internal Phase1MatchingPort boundary

**Files:**

- Create: `src/job_search_cockpit/phase1_contract/matching_port.py`
- Modify: `src/job_search_cockpit/ports.py`
- Modify: `src/job_search_cockpit/launcher.py`
- Modify: `tests/support/builders.py`
- Modify: `tests/support/web.py`
- Modify: `tests/integration/test_phase1_contract.py`
- Create: `tests/unit/test_phase1_matching_port.py`

**Interfaces:**

- Produces: `Phase1MatchingPort.activation_inputs() -> Phase1ActivationInputs`, `Phase1MatchingPort.revalidate_activation_inputs(expected: Phase1ActivationInputs) -> Phase1ActivationInputs`, and typed fail-closed errors.
- Consumes: `Phase1ContractService` only; no Phase II service may import `storage.models`, open the Phase I SQLite path, or receive a Phase I `Session`/`Engine`.

- [ ] **Step 1: Write failing boundary tests**

```python
def test_phase2_receives_only_snapshots(approved_vault) -> None:
    port = build_matching_port(approved_vault)
    inputs = port.activation_inputs()
    assert isinstance(inputs.readiness, Phase1ReadinessSnapshot)
    assert not hasattr(inputs, "engine")
    assert "Claim" not in repr(inputs)


def test_revalidation_rejects_profile_or_import_aba_change(approved_vault) -> None:
    port = build_matching_port(approved_vault)
    captured = port.activation_inputs()
    create_confirmed_profile_change(approved_vault)
    with pytest.raises(Phase1ContractUnavailable, match="profile generation"):
        port.revalidate_activation_inputs(captured)
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/unit/test_phase1_matching_port.py tests/integration/test_phase1_contract.py -v`

Expected: fail because the adapter does not exist.

- [ ] **Step 3: Implement the port with a narrow allowlist**

Add this Protocol to `ports.py` and make `ServiceBundle.phase1_matching_port` required once migration 0002 is available:

```python
class Phase1MatchingPort(Protocol):
    def activation_inputs(self) -> Phase1ActivationInputs: ...

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs: ...
```

The concrete adapter compares receipt, import-run, source hashes, readiness/profile/authority/restore generations, schema, contract version, and every snapshot fingerprint. Any mismatch raises `Phase1ContractUnavailable`; it never returns a partially refreshed object. It exposes no generic query, ORM row, fact enumeration, or direct-database escape hatch. Matching-fact queries and disclosure authorization are deliberately deferred to the next approved Phase II plan.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/unit/test_phase1_matching_port.py tests/integration/test_phase1_contract.py tests/integration/test_web_security.py -v && uv run ruff check src tests && uv run mypy src`

Expected: pass.

- [ ] **Step 5: Commit the proven boundary**

```bash
git add src/job_search_cockpit/phase1_contract/matching_port.py src/job_search_cockpit/ports.py src/job_search_cockpit/launcher.py tests/support/builders.py tests/support/web.py tests/unit/test_phase1_matching_port.py tests/integration/test_phase1_contract.py
git commit -m "feat: add fail-closed Phase I matching port"
```

## Task 4: Issue, validate, and suspend the Phase II activation grant

**Files:**

- Create: `src/job_search_cockpit/phase2/types.py`
- Create: `src/job_search_cockpit/phase2/recovery_ledger.py`
- Create: `src/job_search_cockpit/phase2/mutation.py`
- Create: `src/job_search_cockpit/phase2/activation.py`
- Modify: `src/job_search_cockpit/phase2/models.py`
- Modify: `alembic_phase2/versions/0001_phase2_activation.py`
- Modify: `tests/support/database.py`
- Create: `tests/integration/test_phase2_activation.py`
- Create: `tests/integration/test_phase2_restore.py`

**Interfaces:**

- Produces: `ActivationCommand`, `Phase2ActivationView`, `Phase2ActivationService.activate(command)`, `validate_current()`, `suspend(reason)`, `revalidate_before(action: Phase2Action)`, and `Phase2ActivationUnavailable`.
- Consumes: `Phase1MatchingPort` and `Phase2MutationCoordinator`; all persisted input is the canonical activation snapshot, never copied Phase I rows.

- [ ] **Step 1: Write failing activation tests**

```python
def test_activation_requires_exact_user_confirmation(phase2_service) -> None:
    with pytest.raises(Phase2ActivationUnavailable, match="confirmation"):
        phase2_service.activate(ActivationCommand(actor="Varun", confirmation="proceed"))


def test_activation_binds_and_revalidates_all_phase1_generations(phase2_service) -> None:
    grant = phase2_service.activate(
        ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
    )
    assert grant.state == "active"
    phase2_service.phase1_port.mutate_fixture_readiness_generation()
    assert phase2_service.validate_current().state == "suspended"


def test_restore_suspends_grants_and_advances_generation(phase2_service) -> None:
    grant = activate(phase2_service)
    phase2_service.restore(backup_id=known_backup, actor="Varun", reason="test")
    assert phase2_service.activation_view().state == "suspended"
    assert phase2_service.activation_view().restore_generation > grant.restore_generation
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/integration/test_phase2_activation.py tests/integration/test_phase2_restore.py -v`

Expected: collection fails because the activation service does not exist.

- [ ] **Step 3: Implement serialized grant lifecycle and recovery history**

Require the literal confirmation `ENABLE PHASE II`; store the user-visible confirmation text and actor. Before issuance, call `port.activation_inputs()`. Persist a canonical snapshot with: Phase I receipt, schema/build/suite/run/result fingerprints, complete source import, profile version/generation/fingerprint, readiness/authority/restore generations/fingerprint, and Phase II restore/revocation/activation generations.

The Phase II recovery ledger reuses the hash-chain format but lives at the Phase II path. Record `activation_issued`, `activation_suspended`, `activation_revoked`, `phase2_backup_created`, and `phase2_restore_completed` events. `validate_current()` revalidates the complete Phase I snapshot through the port, increments revocation generation and writes a suspension event on any denial, and returns a non-actionable historical view. `revalidate_before()` initially accepts only `Phase2Action.ACTIVATION_VIEW`; provider, URL, discovery, packet, scoring, publication, and handoff actions must be declared but denied with `not_implemented` until their later approved plans.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/integration/test_phase2_activation.py tests/integration/test_phase2_restore.py tests/integration/test_recovery_ledger.py -v && uv run ruff check src tests && uv run mypy src`

Expected: pass.

- [ ] **Step 5: Commit the activation service**

```bash
git add src/job_search_cockpit/phase2 tests/support/database.py tests/integration/test_phase2_activation.py tests/integration/test_phase2_restore.py
git commit -m "feat: add revocable Phase II activation grant"
```

## Task 5: Add the local activation screen without live operations

**Files:**

- Create: `src/job_search_cockpit/web/routes/phase2.py`
- Create: `src/job_search_cockpit/web/templates/phase2_activation.html`
- Modify: `src/job_search_cockpit/web/app.py`
- Modify: `src/job_search_cockpit/web/routes/home.py`
- Modify: `src/job_search_cockpit/web/templates/base.html`
- Modify: `src/job_search_cockpit/web/templates/home.html`
- Modify: `src/job_search_cockpit/web/static/app.css`
- Create: `tests/integration/test_phase2_activation_page.py`
- Create: `tests/e2e/test_phase2_activation_flow.py`

**Interfaces:**

- Produces: authenticated `GET /phase-2` and CSRF-protected `POST /phase-2/activate`; a plain-language `Phase2ActivationView` with current blockers and a no-provider-access statement.
- Consumes: `Phase2ActivationService` from app state; no provider adapter, URL, job catalog content, Phase I claim, or raw source text.

- [ ] **Step 1: Write failing browser and route tests**

```python
def test_phase2_page_is_disabled_without_a_durable_receipt(vault_settings) -> None:
    with authenticated_test_app(vault_settings) as client:
        page = client.get("/phase-2")
        assert "Phase II is not enabled" in page.text
        assert "No job sources have been contacted" in page.text


def test_phase2_activation_uses_prg_and_csrf(activated_test_app) -> None:
    response = activated_test_app.post(
        "/phase-2/activate",
        data={"confirmation": "ENABLE PHASE II", "reason": "Start Phase II"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_phase2_activation_is_keyboard_accessible(page, phase2_test_app) -> None:
    page.goto(phase2_test_app.launch_url)
    page.get_by_role("link", name="Phase II").press("Enter")
    expect(page.get_by_role("heading", name="Phase II activation")).to_be_visible()
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py tests/e2e/test_phase2_activation_flow.py -v`

Expected: route-not-found failures.

- [ ] **Step 3: Implement only the activation UI**

Show the captured Phase I receipt ID, current profile version, four-source completeness, and activation state using safe metadata only. If state is active, state clearly: “Phase II is enabled for setup only. No providers are approved or contacted.” If suspended, show the exact non-sensitive blocker and a single repair action. Activation requires exact confirmation and uses POST/Redirect/GET. Add no discovery control, external link, provider configuration, job card, score, or live fetch control.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py tests/e2e/test_phase2_activation_flow.py tests/e2e/test_accessibility_flow.py -v && uv run ruff check src tests && uv run mypy src`

Expected: pass.

- [ ] **Step 5: Commit the activation UI**

```bash
git add src/job_search_cockpit/web tests/integration/test_phase2_activation_page.py tests/e2e/test_phase2_activation_flow.py
git commit -m "feat: show Phase II activation state"
```

## Task 6: Verify the Phase II-A activation gate and create the next-plan boundary

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-20-phase-2-job-discovery-match-scoring-design.md`
- Create: `tests/e2e/test_phase2a_acceptance.py`
- Modify: `tests/integration/test_web_security.py`
- Modify: `tests/integration/test_startup_state.py`

**Interfaces:**

- Produces: a documented Phase II-A verification command and an explicit boundary stating that provider inventory, provider approval, source retrieval, normalization, scoring, and manual interpreter controls require the next approved plan.
- Consumes: all prior tasks; no external service.

- [ ] **Step 1: Write the failing end-to-end acceptance test**

```python
def test_phase2a_is_fail_closed_and_never_contacts_a_provider(page, phase2_test_app) -> None:
    page.goto(phase2_test_app.launch_url)
    page.get_by_role("link", name="Phase II").click()
    expect(page.get_by_text("No job sources have been contacted")).to_be_visible()
    assert phase2_test_app.provider_request_count == 0
    page.get_by_role("button", name="Enable Phase II setup").click()
    expect(page.get_by_text("enabled for setup only")).to_be_visible()
    assert phase2_test_app.provider_request_count == 0
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `uv run pytest tests/e2e/test_phase2a_acceptance.py -v`

Expected: fail until the activation UI and test harness expose the required safe state.

- [ ] **Step 3: Document the safe operating boundary**

Update the README with the Phase II-A verification command and make these statements explicit: activation is revocable; it does not approve a provider; no job is fetched; no facts are released; no document is created. Amend the Phase II design status to distinguish implemented activation foundation from unimplemented discovery and scoring systems.

- [ ] **Step 4: Run the complete quality suite**

Run:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -v
```

Expected: all existing and new tests pass; browser coverage proves setup-only activation never starts external work.

- [ ] **Step 5: Commit the verified Phase II-A slice**

```bash
git add README.md docs/superpowers/specs/2026-08-20-phase-2-job-discovery-match-scoring-design.md tests/e2e/test_phase2a_acceptance.py tests/integration/test_web_security.py tests/integration/test_startup_state.py
git commit -m "test: verify Phase II activation remains setup-only"
```

## Plan Self-Review

- Spec coverage: this plan covers the required first executable Phase II task—the strict Phase I application boundary and revocable activation grant—plus isolated storage, recovery, and a no-live-work UI. It deliberately excludes provider inventory, provider approval, retrieval, job normalization, matching-fact taxonomy/query support, extraction, scoring, shortlist, retention, and Phase III handoff; each requires a subsequent approved plan.
- Failure behavior: every Phase I mismatch, missing receipt, restore, malformed snapshot, or unavailable port is denied and suspends the grant. No fallback table access or cached authority exists.
- Scope: the plan makes setup possible but deliberately makes all provider and scoring actions unavailable. It cannot contact live job providers.
- Consistency: `Phase1MatchingPort`, `Phase1ActivationInputs`, profile/readiness/restore generations, and canonical fingerprints are named consistently across tasks. The plan uses profile version 2 only as a current fixture; runtime values come from the active snapshot.
