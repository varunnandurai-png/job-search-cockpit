# Phase 1 Fact Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, local Job Search Cockpit that imports Varun's curated profile sources, requires review of risky or conflicting facts, preserves a locked job-search profile, and prevents unsupported information from becoming resume-eligible.

**Architecture:** A Python 3.12 FastAPI application serves minimalist, server-rendered pages only on `127.0.0.1`. SQLite stores versioned claims, evidence, decisions, audit events, and search-profile versions under the macOS Application Support directory; focused services own importing, conflict detection, review, readiness, backup, and security.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic, Jinja2, small vanilla JavaScript helpers, SQLite, pytest, HTTPX TestClient, Ruff, mypy, and Playwright for end-to-end browser checks.

## Global Constraints

- Run only on Python 3.12.
- Bind the application only to `127.0.0.1` and require a fresh launch token for every process.
- Keep the database, backups, and redacted logs under `~/Library/Application Support/JobSearchCockpit/`; never commit them.
- Do not call an external AI service or upload career facts during Phase 1.
- Treat the four curated source files as read-only.
- Use `job-search-profile-assessment.md` as the official source for the locked search profile.
- Always preserve Hyderabad, Bengaluru, and Singapore as the only eligible locations in version 1.
- Always preserve ₹46 LPA, ₹48 LPA, and S$120,000 base as the respective disclosed-compensation floors in version 1.
- Keep missing compensation as `unknown`; do not reject it automatically.
- Exclude JPMorganChase and the other role categories listed in the approved design.
- Require individual review for conflicts, numbers, dates, titles, team scope, and confidential claims.
- Keep factual approval separate from confidentiality.
- Never make an unresolved, rejected, unsupported, or unpermitted confidential claim resume-eligible.
- Never infer a missing fact or strengthen wording to improve a profile.
- Use plain-language interface copy and the approved minimalist visual direction.
- Preserve earlier decisions and profile versions; changes supersede history instead of deleting it.
- Use test-specific temporary folders and fixture copies so automated tests never touch Varun's live vault or source documents.

## File Structure

```text
job-search-cockpit/
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── README.md
├── Setup Job Search Cockpit.command
├── Start Job Search Cockpit.command
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/0001_phase_1_vault.py
├── src/job_search_cockpit/
│   ├── __init__.py
│   ├── config.py
│   ├── logging.py
│   ├── ports.py
│   ├── sources.py
│   ├── launcher.py
│   ├── storage/
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── backup.py
│   │   ├── recovery_ledger.py
│   │   ├── restore.py
│   │   └── mutation.py
│   ├── facts/
│   │   ├── types.py
│   │   ├── repository.py
│   │   ├── conflicts.py
│   │   ├── permissions.py
│   │   └── review.py
│   ├── imports/
│   │   ├── types.py
│   │   ├── grammar.py
│   │   ├── profile_json.py
│   │   ├── master_profile.py
│   │   ├── assessment.py
│   │   ├── workflow.py
│   │   └── service.py
│   ├── search_profile/
│   │   ├── catalog.py
│   │   └── service.py
│   ├── audit/service.py
│   ├── readiness/service.py
│   └── web/
│       ├── app.py
│       ├── security.py
│       ├── routes/
│       │   ├── home.py
│       │   ├── imports.py
│       │   ├── review.py
│       │   ├── search_profile.py
│       │   └── history.py
│       ├── templates/
│       │   ├── base.html
│       │   ├── home.html
│       │   ├── import_preview.html
│       │   ├── review_queue.html
│       │   ├── review_fact.html
│       │   ├── search_profile.html
│       │   └── history.html
│       └── static/app.css
└── tests/
    ├── conftest.py
    ├── support/
    │   ├── builders.py
    │   ├── database.py
    │   └── web.py
    ├── fixtures/sources/
    ├── unit/
    ├── integration/
    └── e2e/
```

Each package has one responsibility: importers read sources, fact services decide review behavior, the search-profile service owns the locked filters, storage owns durability, and web routes translate those services into plain-language screens.

## QA Hardening Requirements

These requirements are binding across every task and replace any narrower wording in an individual task.

### Profile-source precedence

- Version 1 contains both allocations from the assessment: location `40/45/15` and role difficulty `50/35/15`.
- JPMorganChase remains excluded because `job-search-cockpit-plan.md` makes it a hard gate and Varun explicitly confirmed it. This intentionally overrides the assessment's earlier internal-mobility suggestion.
- A sanitized golden profile fixture contains every version-1 field. A field-by-field test compares the seeded payload with that fixture; no field may be silently omitted.

### Durable records and attribution

The initial migration includes these additional immutable records:

- `import_runs` and `import_run_sources` for each final committed four-source snapshot.
- `import_attempts` for every apply outcome, including rejected, aborted, failed, and committed attempts. Idempotency applies to facts, revisions, and evidence—not attempts.
- `source_occurrences` and `import_run_occurrences` linking each run to the exact semantic occurrence that supports a claim. An occurrence uses source key, employer or subject, period, statement kind, and semantic anchor; it never uses bullet order, file line, or mutable claim value as identity.
- `conflict_resolutions` for selected or corrected revisions, reason, expected group version, decision time, and supersession or reopening.
- `named_uses` for immutable, non-reusable purpose descriptors.
- `confidential_permission_events` for append-only grant, revoke, expire, and supersede events tied to exact claim ID, revision ID, named-use ID, actor, confirmation, target event, and time.
- `claim_support_assertions` for immutable documentary or user-confirmed support attached to an exact revision, employer, and period.

`claim_revisions` also records immutable `employer_key`, `period_start`, and `period_end`. Support state is derived only from immutable `claim_support_assertions`; revisions are never updated in place. Unsupported revisions cannot become resume-eligible. A correction gains support only through a new assertion that names the actor, reason, employer, and time period and supersedes any earlier support assertion. Permissions bound to a different revision never carry forward.

`decisions` records `supersedes_decision_id`. Database triggers reject update and delete operations on claim revisions, decisions, audit events, conflict resolutions, import runs, import attempts, source occurrences, support assertions, named uses, and confidential-permission events. Reverting creates a new decision; it never changes the old row.

### Shared test harness

Task 1 owns `src/job_search_cockpit/ports.py`, `tests/conftest.py`, and the three `tests/support` modules. `ports.py` contains complete Protocol definitions used by both tests and implementations; tests do not create fake future production classes. The support modules define and document every shared name used by later tests:

- Configuration/database: `settings`, `vault_settings`, `session`, `mutation_coordinator`, `count_rows`, `failing_operation`, `running_instance_lock`, `migrated_wal_vault`, `sqlite_integrity`, `VaultHarness`, and `approved_vault`.
- Builders: `candidate`, `one`, `changed_profile`, `load_golden_profile_v1`, `MoneyFloor`, `FixedClock`, `fixed_clock`, `launch_session_id`, sanitized source specs, ordinary/conflicting/confidential claims, conflict groups, audit events, and import-run builders.
- Web/browser: `web_client`, `AuthenticatedClient`, `authenticated_client`, `parse_set_cookie`, `RunningApp`, `running_app`, `running_app_with_curated_fixtures`, `assert_accessible_page`, `assert_readiness_is_false`, and `resolve_all_fixture_reviews`.

Each fixture uses a temporary data directory and sanitized source copies, closes sessions and sockets in teardown, and asserts that no path resolves to the live Application Support directory or real curated documents. Every task that adds a helper must list the owning support file under **Files**, implement the helper before the test that consumes it, and preserve the helper's public name and teardown behavior.

### Import grammar and previews

- Each importer has a documented grammar for recognized headings, fields, lists, Unicode dashes, malformed input, and stable key derivation.
- Reordering bullets does not change identity. Claim and source-occurrence identity use source key, normalized employer or subject, period, statement kind, and semantic anchor. The anchor uses named product/capability plus normalized action/object tokens after removing numbers, dates, and presentation punctuation; mutable result values, bullet order, file line, document hash, and locator are excluded. Colliding or ambiguous anchors never auto-merge: the prior occurrence becomes stale and both candidates enter individual review.
- Revision identity uses claim identity, normalized semantic value, employer, and period. Source hash and locator are evidence attributes, not revision identity.
- Every latest committed run maps occurrences to claims. If an occurrence disappears, changes attribution, or loses all active evidence, the prior claim is marked stale and ineligible in the same import transaction. Ambiguous semantic replacement creates required review rather than automatic linkage.
- Semantic conflict families compare product years, titles, chronology, team scope, and metrics with employer and period attribution; comparison is not limited to identical canonical keys.
- Confidentiality classification is conservative. Contact details, personal identifiers, compensation, internal financial metrics, client/vendor names, and explicitly private text receive `POTENTIALLY_CONFIDENTIAL` and persisted sensitivity `UNREVIEWED`. `RiskFlag.POTENTIALLY_CONFIDENTIAL`, `Sensitivity.UNREVIEWED`, `NORMAL`, and `CONFIDENTIAL` are defined in Task 1. Unreviewed sensitivity blocks bulk approval, readiness, and eligibility. Changing sensitivity in either direction preserves factual status and history.
- An import preview is an immutable, single-use, ten-minute snapshot bound to the launch session, manifest version, exact source hashes, parsed candidate digest, and CSRF session.
- Apply rechecks every source hash before acquiring the mutation lock. A changed source, session mismatch, replay, expiry, restart, or manifest mismatch rejects the preview and performs no write.
- Conflict preview runs against the immutable candidate snapshot. Import apply rebuilds, closes, or reopens conflicts inside the same mutation transaction before the import run becomes committed. Readiness is calculated only from the latest complete committed `import_run`; historical successes never fill gaps in a newer run.
- Each apply produces one final immutable `import_attempts` row in a separate post-outcome transaction. A domain rollback is followed by a failed or aborted attempt row; if the database itself is unavailable, the same event is appended to the external hash-chained recovery ledger and imported into the attempt table after recovery. Readiness ignores attempts and uses only the newest committed import run.

### Mutations, backup, and restore

- One lifetime `AppInstanceLock` owns the owner-only cross-process file lock from startup through shutdown and rejects a second cockpit process. One `MutationCoordinator`, constructed with the held lock capability, owns the process-local mutation mutex and every import, fact decision, conflict resolution, confidential permission, profile change, revert, migration install, and restore. It never reacquires the lifetime lock.
- The coordinator verifies caller versions, creates and verifies the immediate predecessor backup, then runs one database transaction. Shutdown stops requests, drains mutations, disposes the engine, and releases the lifetime lock last.
- Backup uses SQLite's online backup API against WAL mode, unique names with timestamp plus random suffix, SHA-256, and `PRAGMA integrity_check`. Each backup has an atomically written owner-only JSON manifest containing backup ID, checksum, vault ID, Alembic revision, creation time, and reason; restart discovery trusts only matching database/manifest pairs.
- Restore is only `MutationCoordinator.restore`. It drains requests, checkpoints WAL, closes sessions, disposes the engine, verifies and migrates a copied backup, creates a pre-restore backup, replaces the complete SQLite state without stale WAL/SHM files, recreates the engine, and rechecks integrity. Corruption, disk-full, permission, and migration failures leave the active vault unchanged.
- An owner-only append-only hash-chained `RecoveryLedger` outside SQLite stores typed events. Backup/restore events contain event ID, prior-event hash, backup/restore IDs, old/new vault IDs, checksums, actor, reason, and time. Import-attempt events contain attempt ID, preview ID, candidate digest, manifest version, outcome, four source statuses/hashes, failure class with redacted message, session fingerprint, and time. `reconcile_import_attempts(coordinator)` idempotently copies unreconciled ledger attempts into `import_attempts` using attempt ID, then appends a reconciliation event. Healthy startup completes reconciliation before serving requests. History reads the ledger alongside database audit events so post-backup activity remains traceable after restoring an older database.

### Conflict, bulk review, and confidential use

- Normal approval and grouped approval cannot close a conflict.
- `resolve_conflict(coordinator: MutationCoordinator, command: ResolveConflictCommand) -> ConflictResolutionView` is the single public interface. `ResolveConflictCommand` requires group ID, exactly one selected revision or corrected value, expected group version, reason, employer key, and applicable period. Changed evidence reopens the group through a new resolution record.
- Group approval accepts immutable `(claim_id, revision_id, expected_version)` items, recalculates risk and conflicts while holding the mutation lock, and fails the entire batch on any mismatch.
- Named uses are immutable records with ID, kind, external reference, description, creator, and time. Permission state is derived from append-only events. Grant, revoke, expire, and supersede services require actor, exact target IDs, confirmation or reason, and expected event version. Confidential eligibility requires an active grant for the exact claim revision and named use. Wrong claim, revision, use, expired, revoked, or superseded permission is denied.
- Evidence, employer/time attribution, open-conflict, and confidentiality gates apply equally to `approved` and `corrected` claims.

### Browser and file security

- Launch tokens expire after five minutes using a monotonic deadline, are single-use, and exist only in process memory.
- Session cookies are signed, process-specific, `HttpOnly`, `SameSite=Strict`, scoped to `/`, and expire when the process ends.
- Every private response uses `Cache-Control: no-store`, a restrictive Content Security Policy, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, and referrer suppression.
- Mutation requests validate Host, Origin or Fetch Metadata, session, and CSRF. Unsupported methods and websocket upgrades are rejected.
- Jinja autoescape remains enabled. Tests inject HTML and script-like source excerpts and prove they render as text.
- Production source paths are fixed from the approved manifest, resolve beneath the exact CV root, reject symlinks and non-regular files, and cannot be overridden by environment variables. Only test settings accept injected paths.
- The data directory and lock directory use mode `0700`; database, WAL, SHM, backup, lock, and log files use `0600`, including under a permissive umask.

### Startup and accessibility

- Startup refuses non-macOS systems, creates protected directories, acquires the lifetime instance lock, verifies or creates the database, checks integrity, seeds profile version 1 exactly once, wires one shared coordinator and services, pre-binds `127.0.0.1`, passes the prepared services and exact port into the application factory, and only then opens the browser.
- Existing-vault upgrades never run Alembic in place. Startup backs up the existing vault, migrates and validates a copy, and installs it through the same quiesced atomic replacement used by restore.
- A failed migration or integrity check does not start the web application and gives plain-language recovery instructions.
- Setup scripts give exact Homebrew installation commands when Python 3.12 or `uv` is missing; they do not silently install software.
- Browser acceptance uses schema-preserving sanitized golden fixtures. It covers every control by keyboard, focus restoration, accessible names, validation announcements, colour contrast, reduced motion, 200% zoom/reflow, and 390/768/1440 pixel layouts.
- Real curated sources may be previewed only as a separately authorized manual check. Automated acceptance never reads or changes them.

---

### Task 1: Project foundation, safe configuration, and shared test harness

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `src/job_search_cockpit/__init__.py`
- Create: `src/job_search_cockpit/config.py`
- Create: `src/job_search_cockpit/logging.py`
- Create: `src/job_search_cockpit/ports.py`
- Create: `src/job_search_cockpit/sources.py`
- Create: `src/job_search_cockpit/facts/types.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_logging.py`
- Create: `tests/conftest.py`
- Create: `tests/support/builders.py`
- Create: `tests/support/database.py`
- Create: `tests/support/web.py`

**Interfaces:**
- Produces: `SourceSpec`, `SourceKind`, fixed production `Settings`, `Settings.for_tests(data_dir: Path, source_root: Path) -> Settings`, `safe_open_source(spec: SourceSpec) -> OpenedSource`, `RiskFlag`, `Sensitivity`, `Clock`, `MonotonicClock`, `PreparedVault` and complete service Protocols, `configure_logging(settings: Settings) -> None`, and every shared test fixture named in QA Hardening Requirements.
- Consumes: no application interfaces.

- [ ] **Step 1: Write the failing configuration tests**

```python
def test_default_settings_keep_private_data_outside_repository():
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.data_dir == Path.home() / "Library/Application Support/JobSearchCockpit"
    assert settings.database_path == settings.data_dir / "vault.sqlite3"


def test_curated_source_manifest_is_exact():
    settings = Settings()
    assert [source.key for source in settings.sources] == [
        "assessment", "profile_json", "master_profile", "resume_workflow"
    ]
    assert all(source.read_only for source in settings.sources)


def test_log_redaction_removes_sensitive_values():
    message = redact_sensitive("email=person@example.com phone=+91 99999 99999 token=secret")
    assert "person@example.com" not in message
    assert "99999" not in message
    assert "secret" not in message


def test_test_settings_never_resolve_to_live_sources(vault_settings: Settings):
    live_root = Path("/Users/nandurivarun/Desktop/Documents/CV").resolve()
    assert all(not source.path.resolve().is_relative_to(live_root) for source in vault_settings.sources)
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_logging.py -v`

Expected: collection fails because `job_search_cockpit.config` does not exist.

- [ ] **Step 3: Add the package configuration and dependency manifest**

`pyproject.toml` must declare Python `>=3.12,<3.13`, the runtime dependencies named in the Tech Stack, and development groups for pytest, HTTPX, Ruff, mypy, and Playwright. Configure the `src` package layout, `pytest` test paths, Ruff line length `100`, and mypy strict mode.

Implement these exact public shapes in `config.py`:

```python
class SourceKind(StrEnum):
    ASSESSMENT = "assessment_markdown"
    PROFILE_JSON = "profile_json"
    MASTER_PROFILE = "master_profile_markdown"
    RESUME_WORKFLOW = "resume_workflow_markdown"


@dataclass(frozen=True, slots=True)
class SourceSpec:
    key: str
    kind: SourceKind
    path: Path
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class Settings:
    host: Literal["127.0.0.1"] = "127.0.0.1"
    data_dir: Path = Path.home() / "Library/Application Support/JobSearchCockpit"
    _source_root: Path = Path("/Users/nandurivarun/Desktop/Documents/CV")

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def database_path(self) -> Path:
        return self.data_dir / "vault.sqlite3"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def sources(self) -> Sequence[SourceSpec]:
        return (
            SourceSpec("assessment", SourceKind.ASSESSMENT, self.source_root / "Context/job-search-profile-assessment.md"),
            SourceSpec("profile_json", SourceKind.PROFILE_JSON, self.source_root / "Old Data/profile_bank/profile.json"),
            SourceSpec("master_profile", SourceKind.MASTER_PROFILE, self.source_root / "Old Data/profile_bank/Varun_Nanduri_Master_Profile.md"),
            SourceSpec("resume_workflow", SourceKind.RESUME_WORKFLOW, self.source_root / "Old Data/profile_bank/Varun_Nanduri_Resume_Workflow.md"),
        )

    @classmethod
    def for_tests(cls, data_dir: Path, source_root: Path) -> "Settings":
        return cls(data_dir=data_dir, _source_root=source_root)
```

`.gitignore` must include `.venv/`, `.DS_Store`, `*.sqlite3`, `*.sqlite3-*`, `backups/`, `logs/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `__pycache__/`, and Playwright output folders.

`configure_logging` must create `settings.data_dir / "logs"` with mode `0700`, write operational event names and exception types, and run every message through `redact_sensitive`. Redaction must cover email addresses, phone-like sequences, launch tokens, CSRF values, cookies, and claim values supplied through structured logging fields.

Create the complete structural Protocols for database sessions, mutation coordination, import preview/apply, review, readiness, and web startup in `ports.py`. Create shared builders against those Protocols rather than fake future production classes. `safe_open_source` must resolve the fixed root, use `lstat`, open without following symlinks, verify the descriptor with `fstat`, require a regular file, and return bytes plus descriptor-derived metadata. The import tasks must call it on every preview and apply read.

- [ ] **Step 4: Lock dependencies and run foundation checks**

Run: `uv lock && uv run pytest tests/unit/test_config.py tests/unit/test_logging.py -v && uv run ruff check src tests && uv run mypy src`

Expected: the configuration tests pass, the lockfile is created, and lint/type checks report no errors.

- [ ] **Step 5: Commit the foundation**

```bash
git add .gitignore .python-version pyproject.toml uv.lock src/job_search_cockpit tests/unit/test_config.py tests/unit/test_logging.py
git commit -m "build: establish Phase 1 Python foundation"
```

---

### Task 2: Versioned fact-vault database

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_phase_1_vault.py`
- Create: `src/job_search_cockpit/storage/database.py`
- Create: `src/job_search_cockpit/storage/models.py`
- Create: `tests/integration/test_database_schema.py`

**Interfaces:**
- Produces: `create_engine_for(settings: Settings) -> Engine`, `session_factory_for(engine: Engine) -> sessionmaker[Session]`, and `upgrade_database(database_url: str) -> None`.
- Produces tables: `source_documents`, `source_occurrences`, `import_runs`, `import_run_sources`, `import_run_occurrences`, `import_attempts`, `claims`, `claim_revisions`, `claim_evidence`, `claim_support_assertions`, `conflict_groups`, `conflict_members`, `conflict_resolutions`, `decisions`, `named_uses`, `confidential_permission_events`, `audit_events`, and `search_profile_versions`.
- Consumes: `Settings` from Task 1.

- [ ] **Step 1: Write a migration test against a temporary database**

```python
def test_initial_migration_creates_all_phase_1_tables(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'vault.sqlite3'}"
    upgrade_database(database_url)
    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert tables == {
        "alembic_version", "source_documents", "source_occurrences", "import_runs",
        "import_run_sources", "import_run_occurrences", "import_attempts", "claims",
        "claim_revisions", "claim_evidence", "claim_support_assertions",
        "conflict_groups", "conflict_members", "conflict_resolutions", "decisions",
        "named_uses", "confidential_permission_events", "audit_events",
        "search_profile_versions",
    }
```

- [ ] **Step 2: Run the migration test and verify it fails**

Run: `uv run pytest tests/integration/test_database_schema.py -v`

Expected: failure because the migration and storage modules do not exist.

- [ ] **Step 3: Implement the schema and migration**

Use string IDs generated with `uuid.uuid4()`, UTC ISO timestamps, JSON columns for structured values, and database constraints for allowed states.

The model contract must include:

```python
class ClaimStatus(StrEnum):
    UNRESOLVED = "unresolved"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class Sensitivity(StrEnum):
    UNREVIEWED = "unreviewed"
    NORMAL = "normal"
    CONFIDENTIAL = "confidential"


class Claim(Base):
    id: Mapped[str]
    canonical_key: Mapped[str]
    category: Mapped[str]
    subject: Mapped[str]
    status: Mapped[ClaimStatus]
    sensitivity: Mapped[Sensitivity]
    active_revision_id: Mapped[str | None]
    version: Mapped[int]


class ClaimRevision(Base):
    id: Mapped[str]
    claim_id: Mapped[str]
    value_json: Mapped[dict[str, object]]
    display_value: Mapped[str]
    origin: Mapped[str]
    employer_key: Mapped[str | None]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    created_at: Mapped[datetime]
```

Add unique constraints for `claims.canonical_key`, semantic source-occurrence identity, revision semantic identity, source `(path, content_hash)`, search-profile version number, and conflict membership. Foreign keys must prevent deleting evidence or decisions that are already referenced. Add database triggers that abort update or delete statements against the immutable tables listed in QA Hardening Requirements, and test those triggers through raw SQL as well as repository calls.

- [ ] **Step 4: Run schema and quality checks**

Run: `uv run pytest tests/integration/test_database_schema.py -v && uv run ruff check src tests && uv run mypy src`

Expected: migration test passes and quality checks report no errors.

- [ ] **Step 5: Commit the vault schema**

```bash
git add alembic.ini alembic src/job_search_cockpit/storage tests/integration/test_database_schema.py
git commit -m "feat: add versioned fact vault schema"
```

---

### Task 3: Serialized mutations, safety copies, and verified restore

**Files:**
- Create: `src/job_search_cockpit/storage/backup.py`
- Create: `src/job_search_cockpit/storage/recovery_ledger.py`
- Create: `src/job_search_cockpit/storage/restore.py`
- Create: `src/job_search_cockpit/storage/mutation.py`
- Modify: `src/job_search_cockpit/storage/database.py`
- Create: `tests/unit/test_backup.py`
- Create: `tests/integration/test_atomic_changes.py`
- Create: `tests/integration/test_restore.py`
- Create: `tests/integration/test_mutation_lock.py`
- Create: `tests/integration/test_recovery_ledger.py`
- Modify: `tests/support/database.py`

**Interfaces:**
- Produces: `AppInstanceLock.acquire(settings: Settings) -> AppInstanceLock`, `RecoveryLedger.append(event: RecoveryEvent) -> LedgerReceipt`, `RecoveryLedger.reconcile_import_attempts(coordinator: MutationCoordinator) -> ReconciliationResult`, `create_safety_copy(database_path: Path, backup_dir: Path, reason: str) -> BackupResult`, `MutationCoordinator.run(operation: Callable[[Session], T], reason: str, expected_version: int | None) -> T`, and `MutationCoordinator.restore(backup_id: str, actor: str, reason: str) -> RestoreResult`.
- Consumes: the database factory from Task 2.

- [ ] **Step 1: Write tests for successful backup, failed backup, and rollback**

```python
def test_safety_copy_has_timestamp_hash_and_reason(tmp_path: Path):
    source = migrated_wal_vault(tmp_path)
    result = create_safety_copy(source, tmp_path / "backups", "before_review")
    assert result.path.exists()
    assert result.manifest_path.exists()
    assert result.sha256 == sha256(result.path.read_bytes()).hexdigest()
    assert result.reason == "before_review"
    assert sqlite_integrity(result.path) == "ok"


def test_coordinator_rolls_back_when_operation_fails(
    mutation_coordinator: MutationCoordinator, vault_settings: Settings
):
    with pytest.raises(RuntimeError, match="simulated failure"):
        mutation_coordinator.run(failing_operation, "import", expected_version=None)
    assert count_rows(vault_settings.database_path, "claims") == 0


def test_second_process_cannot_open_same_vault(vault_settings: Settings):
    with running_instance_lock(vault_settings):
        with pytest.raises(VaultAlreadyOpen):
            AppInstanceLock.acquire(vault_settings)
```

- [ ] **Step 2: Run the tests and confirm both fail**

Run: `uv run pytest tests/unit/test_backup.py tests/integration/test_atomic_changes.py tests/integration/test_restore.py tests/integration/test_mutation_lock.py tests/integration/test_recovery_ledger.py -v`

Expected: failures because backup, lifetime lock, coordinator, and restore functions are missing.

- [ ] **Step 3: Implement safe-copy and transaction behavior**

`create_safety_copy` must satisfy the WAL, permission, integrity, unique-name, and failure behavior in QA Hardening Requirements and return:

```python
@dataclass(frozen=True, slots=True)
class BackupResult:
    backup_id: str
    path: Path
    manifest_path: Path
    sha256: str
    vault_id: str
    alembic_revision: str
    reason: str
    created_at: datetime
```

`AppInstanceLock` owns the cross-process lifetime lock. `MutationCoordinator` receives the held lock capability, owns only the process-local mutation mutex, creates and verifies the immediate predecessor backup, wraps ordinary operations in one SQLAlchemy transaction, and commits only after the operation returns successfully. Restore is available only through the coordinator and follows the quiesced engine/WAL/recovery-ledger sequence in QA Hardening Requirements. Tests cover restart discovery from JSON manifests, concurrent HTTP-equivalent mutations, concurrent backup names, active WAL writes, corrupted backups, permission failure, simulated disk-full failure, failed migration, restore chronology, and rollback.

- [ ] **Step 4: Run focused and full storage tests**

Run: `uv run pytest tests/unit/test_backup.py tests/integration/test_atomic_changes.py tests/integration/test_restore.py tests/integration/test_mutation_lock.py tests/integration/test_recovery_ledger.py tests/integration/test_database_schema.py -v`

Expected: all storage tests pass.

- [ ] **Step 5: Commit safety behavior**

```bash
git add src/job_search_cockpit/storage tests/support/database.py tests/unit/test_backup.py tests/integration/test_atomic_changes.py tests/integration/test_restore.py tests/integration/test_mutation_lock.py tests/integration/test_recovery_ledger.py
git commit -m "feat: serialize, back up, and restore vault changes"
```

---

### Task 4: Locked target job-search profile

**Files:**
- Create: `src/job_search_cockpit/search_profile/catalog.py`
- Create: `src/job_search_cockpit/search_profile/service.py`
- Create: `tests/unit/test_search_profile_catalog.py`
- Create: `tests/integration/test_search_profile_versioning.py`

**Interfaces:**
- Produces: `SearchProfilePayload`, `build_profile_v1() -> SearchProfilePayload`, `profile_diff_digest(old: SearchProfilePayload, new: SearchProfilePayload) -> str`, `seed_profile_v1(coordinator: MutationCoordinator) -> SearchProfileVersion`, `get_active_profile(session: Session) -> SearchProfileVersion`, and `confirm_profile_change(coordinator: MutationCoordinator, payload: SearchProfilePayload, reason: str, confirmation: str, expected_active_version: int, expected_diff_digest: str) -> SearchProfileVersion`.
- Consumes: `SearchProfileVersion` storage model and audit table from Task 2 and the mutation coordinator from Task 3.

- [ ] **Step 1: Write exact catalog and versioning tests**

```python
def test_profile_v1_preserves_approved_hard_filters():
    profile = build_profile_v1()
    assert profile.locations == ("Hyderabad", "Bengaluru", "Singapore")
    assert profile.compensation_floors == {
        "Hyderabad": MoneyFloor("INR", 4_600_000, "annual_total"),
        "Bengaluru": MoneyFloor("INR", 4_800_000, "annual_total"),
        "Singapore": MoneyFloor("SGD", 120_000, "annual_base"),
    }
    assert profile.excluded_employers == ("JPMorganChase",)
    assert profile.notice_period_days == 60
    assert profile.location_allocation == {"Hyderabad": 40, "Bengaluru": 45, "Singapore": 15}
    assert profile.role_difficulty_allocation == {"direct_fit": 50, "stretch": 35, "aspirational": 15}


def test_profile_change_requires_exact_confirmation(coordinator: MutationCoordinator):
    with pytest.raises(ProfileConfirmationError):
        confirm_profile_change(
            coordinator,
            changed_profile(),
            "role update",
            "yes",
            expected_active_version=1,
            expected_diff_digest=profile_diff_digest(build_profile_v1(), changed_profile()),
        )


def test_profile_v1_matches_every_field_in_golden_fixture():
    assert build_profile_v1().model_dump(mode="json") == load_golden_profile_v1()
```

- [ ] **Step 2: Run the profile tests and verify failure**

Run: `uv run pytest tests/unit/test_search_profile_catalog.py tests/integration/test_search_profile_versioning.py -v`

Expected: failure because the catalog and service do not exist.

- [ ] **Step 3: Implement the approved profile as typed data**

`SearchProfilePayload` must contain immutable tuples for eligible roles, priority domains, excluded role patterns, eligible locations, both allocation dimensions, sponsorship requirements, compensation floors, excluded employers, notice period, and profile-change rules.

The version-1 constants must copy the approved design exactly, including the explicitly confirmed JPMorganChase exclusion and both allocations. The confirmation string must be `CREATE NEW SEARCH PROFILE VERSION`; any other text fails without changing the active profile. A successful change verifies the expected active version and old/new diff digest inside `MutationCoordinator`, deactivates the prior version, inserts the new version, and appends an audit event in one transaction. Tests submit stale sequential and simultaneous confirmed forms and prove both are rejected without creating a version.

- [ ] **Step 4: Run profile and schema tests**

Run: `uv run pytest tests/unit/test_search_profile_catalog.py tests/integration/test_search_profile_versioning.py -v`

Expected: catalog and versioning tests pass, including preservation of version 1.

- [ ] **Step 5: Commit the locked profile**

```bash
git add src/job_search_cockpit/search_profile tests/unit/test_search_profile_catalog.py tests/integration/test_search_profile_versioning.py
git commit -m "feat: seed locked target search profile"
```

---

### Task 5: Deterministic curated-source importers

**Files:**
- Create: `src/job_search_cockpit/imports/types.py`
- Create: `src/job_search_cockpit/imports/grammar.py`
- Create: `src/job_search_cockpit/imports/profile_json.py`
- Create: `src/job_search_cockpit/imports/master_profile.py`
- Create: `src/job_search_cockpit/imports/assessment.py`
- Create: `src/job_search_cockpit/imports/workflow.py`
- Create: `tests/fixtures/sources/assessment.md`
- Create: `tests/fixtures/sources/profile.json`
- Create: `tests/fixtures/sources/master_profile.md`
- Create: `tests/fixtures/sources/resume_workflow.md`
- Create: `tests/unit/test_importers.py`
- Modify: `tests/support/builders.py`

**Interfaces:**
- Produces: `CandidateClaim`, `EvidenceRef`, `ImportResult`, and `SourceImporter` protocol.
- Produces importers with `read(spec: SourceSpec) -> ImportResult`.
- Consumes: source manifest types, predeclared risks, and `safe_open_source` from Task 1.

- [ ] **Step 1: Create small sanitized fixtures and failing importer tests**

```python
def test_profile_json_importer_keeps_exact_source_locator(profile_json_spec: SourceSpec):
    result = ProfileJsonImporter().read(profile_json_spec)
    claim = one(result.claims, canonical_key="employment.jpmorgan.title")
    assert claim.display_value == "Senior Product Associate (Product Manager)"
    assert claim.evidence.locator == "$.experience[0].title"


def test_assessment_recommendations_do_not_become_career_facts(assessment_spec: SourceSpec):
    result = AssessmentImporter().read(assessment_spec)
    assert not any(claim.canonical_key.startswith("employment.") for claim in result.claims)
    assert result.search_profile is not None
```

- [ ] **Step 2: Run importer tests and verify missing importer failures**

Run: `uv run pytest tests/unit/test_importers.py -v`

Expected: collection fails because importer types and classes do not exist.

- [ ] **Step 3: Implement exact candidate and evidence contracts**

```python
@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_key: str
    source_path: Path
    source_hash: str
    locator: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    canonical_key: str
    category: str
    subject: str
    value: dict[str, object]
    display_value: str
    evidence: EvidenceRef
    employer_key: str | None
    period_start: date | None
    period_end: date | None
    semantic_family: str
    declared_risks: frozenset[RiskFlag] = frozenset()
```

The JSON importer must extract contact data, experience identity fields, each experience bullet, education, certifications, languages, summary, total years, and product years with JSONPath-like locators.

The master-profile importer must extract explicit facts under Contact, High-Impact Metrics, Professional Experience, Education, Certifications, and Languages. Positioning and headline options remain candidate wording, not approved employment facts.

The assessment importer must return the locked search-profile data and assessment claims such as stated years of direct product ownership. Recommendations and market commentary must not become career facts.

The workflow importer must return policy claims governing truthful evidence, ATS compatibility, and non-guaranteed outcomes; it must not create employment achievements.

`grammar.py` must implement and document the stable-key, Unicode, reordering, malformed-input, semantic-family, attribution, and conservative confidentiality rules in QA Hardening Requirements. Add tests for reordered and duplicate bullets, renamed headings, Unicode dashes, malformed JSON, malformed Markdown, the same metric under different employers, and different metrics under the same employer. Contact, compensation, internal metrics, vendor/client references, and explicitly private text must enter individual review as potentially confidential while remaining factually unresolved.

- [ ] **Step 4: Run importer tests and static checks**

Run: `uv run pytest tests/unit/test_importers.py -v && uv run ruff check src tests && uv run mypy src`

Expected: all importer tests pass and every candidate retains a source hash and locator.

- [ ] **Step 5: Commit deterministic importers**

```bash
git add src/job_search_cockpit/imports tests/fixtures/sources tests/support/builders.py tests/unit/test_importers.py
git commit -m "feat: parse curated profile sources deterministically"
```

---

### Task 6: Import orchestration, deduplication, and source changes

**Files:**
- Create: `src/job_search_cockpit/imports/service.py`
- Create: `tests/integration/test_import_service.py`
- Modify: `tests/support/builders.py`

**Interfaces:**
- Produces: `ImportService.preview(session_id: str, now: datetime) -> ImportPreview` and `ImportService.apply(preview_id: str, session_id: str, now: datetime) -> AppliedImport`.
- Consumes: Task 3 mutation coordinator, Task 5 importers, and Task 2 vault/import-run models.

- [ ] **Step 1: Write failing repeat-import and changed-source tests**

```python
def test_identical_import_is_idempotent(
    import_service: ImportService, launch_session_id: str, fixed_clock: FixedClock
):
    first_preview = import_service.preview(launch_session_id, fixed_clock.now())
    first = import_service.apply(first_preview.id, launch_session_id, fixed_clock.now())
    second_preview = import_service.preview(launch_session_id, fixed_clock.now())
    second = import_service.apply(second_preview.id, launch_session_id, fixed_clock.now())
    assert second.created_claims == 0
    assert second.created_revisions == 0
    assert second.source_statuses == first.source_statuses
    assert second.attempt_id != first.attempt_id


def test_changed_source_creates_candidate_revision_without_overwriting_decision(
    approved_vault: VaultHarness,
):
    approved_vault.change_fixture("profile_json", "pm_years", 9)
    preview = approved_vault.preview_import()
    result = approved_vault.apply_import(preview)
    assert result.changed_claims == ("profile.product_years",)
    assert approved_vault.claim("profile.product_years").status == ClaimStatus.UNRESOLVED
    assert approved_vault.previous_approved_revision("profile.product_years").display_value == "8"
```

- [ ] **Step 2: Run import-service tests and verify failure**

Run: `uv run pytest tests/integration/test_import_service.py -v`

Expected: failure because `ImportService` does not exist.

- [ ] **Step 3: Implement preview/apply with content hashing**

`preview()` reads all available sources, reports missing or malformed files in plain language, stores no database rows, and creates the immutable session-bound in-memory snapshot specified in QA Hardening Requirements. The preview contains a random ID, session ID, manifest version, source hashes and statuses, candidate digest, creation time, monotonic expiry, and unused state.

`apply()` rechecks session, one-use state, monotonic expiry, manifest version, and every source through `safe_open_source` before acquiring `MutationCoordinator`. A successful apply writes an immutable import run, four per-source statuses, and run-to-occurrence links with the complete import in one transaction. Claim, occurrence, and revision identity follow QA Hardening Requirements; source hash and locator remain evidence only. For every exact imported revision with matching employer/period evidence, apply idempotently appends an active documentary `claim_support_assertion`. When all supporting occurrences disappear or attribution changes, it appends a superseding loss-of-support assertion and marks the claim stale and ineligible. Claims, revisions, evidence, and equivalent active support assertions are idempotent. After success or rollback, a separate small transaction appends the final immutable attempt row; if the vault is unavailable, it appends the complete typed import-attempt event to `RecoveryLedger` for reconciliation on next healthy startup.

The same transaction marks facts stale when their latest supporting occurrences disappear or change attribution. If one source is unreadable, valid sources may still apply after the explicit incomplete-import confirmation, but the committed run is incomplete and readiness remains blocked. On restart, readiness uses that latest run rather than older successful source rows. Add tests for documentary assertion creation, evidence-loss supersession, eligibility after approved imported evidence, value edits, unrelated source edits, bullet reorder, deleted facts, attribution changes, replacement by symlink/non-regular file between preview/apply, session mismatch, replay, restart, exact expiry boundary, manifest mismatch, latest-incomplete-after-historical-success, failed-attempt ledger durability and reconciliation, and rollback before a run becomes committed.

- [ ] **Step 4: Run import orchestration tests**

Run: `uv run pytest tests/integration/test_import_service.py tests/unit/test_importers.py -v`

Expected: idempotency, changed-source review, missing-source reporting, and atomic rollback tests pass.

- [ ] **Step 5: Commit import orchestration**

```bash
git add src/job_search_cockpit/imports/service.py tests/support/builders.py tests/integration/test_import_service.py
git commit -m "feat: import curated claims safely and idempotently"
```

---

### Task 7: Risk classification and conflict detection

**Files:**
- Modify: `src/job_search_cockpit/facts/types.py`
- Create: `src/job_search_cockpit/facts/conflicts.py`
- Modify: `src/job_search_cockpit/imports/service.py`
- Create: `tests/unit/test_risk_classification.py`
- Create: `tests/integration/test_conflicts.py`
- Modify: `tests/integration/test_import_service.py`
- Modify: `tests/support/builders.py`

**Interfaces:**
- Produces: `classify_risks(candidate: CandidateClaim) -> frozenset[RiskFlag]`, `normalize_for_comparison(candidate: CandidateClaim) -> str`, `analyze_candidate_conflicts(candidates: Sequence[CandidateClaim]) -> ConflictPreview`, `rebuild_conflicts(session: Session, import_run_id: str) -> ConflictSummary`, and `resolve_conflict(coordinator: MutationCoordinator, command: ResolveConflictCommand) -> ConflictResolutionView`.
- Consumes: candidate claims from Task 5, stored revisions from Task 6, and mutation coordinator from Task 3.

- [ ] **Step 1: Write tests for all mandatory individual-review rules**

```python
@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (candidate("metric.savings", "$5M annually"), RiskFlag.QUANTIFIED),
        (candidate("employment.walmart.dates", "July 2021 – June 2024"), RiskFlag.DATE),
        (candidate("employment.jpmorgan.title", "Senior Product Associate"), RiskFlag.TITLE),
        (candidate("employment.jpmorgan.team_count", "5 scrum teams"), RiskFlag.TEAM_SCOPE),
    ],
)
def test_risky_claims_require_individual_review(candidate: CandidateClaim, expected: RiskFlag):
    assert expected in classify_risks(candidate)
```

Add integration fixtures that surface product-years, team-count, title, chronology, and repeated-metric conflicts.

- [ ] **Step 2: Run risk and conflict tests and verify failure**

Run: `uv run pytest tests/unit/test_risk_classification.py tests/integration/test_conflicts.py -v`

Expected: failure because the classification and conflict functions do not exist.

- [ ] **Step 3: Implement deterministic classification and conflict groups**

Risk flags defined in Task 1 are `CONFLICT`, `QUANTIFIED`, `DATE`, `TITLE`, `TEAM_SCOPE`, and `POTENTIALLY_CONFIDENTIAL`. Classification uses canonical-key metadata first and conservative text detection second. Monetary values, percentages, counts, ranges, and values with `+` are quantified.

Conflict comparison must normalize whitespace, dashes, case, and equivalent date punctuation without erasing meaningful numeric differences. It uses both canonical identity and semantic conflict families with employer/period attribution. Distinct comparable values create an open conflict group and apply `CONFLICT` to every member. The service presents all versions and never selects a winner.

`ResolveConflictCommand` contains group ID, exactly one selected revision or corrected value, expected group version, reason, employer key, and time period. Resolution runs through `MutationCoordinator`, appends a `conflict_resolutions` row and decision, closes only that group version, and preserves all members. Normal approval and grouped approval reject open-conflict members. A changed-source reimport appends a reopened resolution and returns the claim to required review. Test selected-source resolution, corrected resolution, normal-approval denial, bulk denial, stale group version, and changed-evidence reopening.

Modify `ImportService` so preview obtains counts from `analyze_candidate_conflicts`, and apply calls `rebuild_conflicts` inside the same mutation transaction after occurrence/stale-state updates and before marking the import run committed. Readiness cannot observe the new run until its conflict state is complete.

- [ ] **Step 4: Run conflict and import tests together**

Run: `uv run pytest tests/unit/test_risk_classification.py tests/integration/test_conflicts.py tests/integration/test_import_service.py -v`

Expected: known conflicts are open and exact duplicates are not conflicts.

- [ ] **Step 5: Commit review-risk logic**

```bash
git add src/job_search_cockpit/facts src/job_search_cockpit/imports/service.py tests/support/builders.py tests/unit/test_risk_classification.py tests/integration/test_conflicts.py tests/integration/test_import_service.py
git commit -m "feat: classify risky facts and expose conflicts"
```

---

### Task 8: Review decisions, audit history, and resume eligibility

**Files:**
- Create: `src/job_search_cockpit/facts/repository.py`
- Create: `src/job_search_cockpit/facts/review.py`
- Create: `src/job_search_cockpit/facts/permissions.py`
- Create: `src/job_search_cockpit/audit/service.py`
- Create: `src/job_search_cockpit/readiness/service.py`
- Create: `tests/integration/test_review_service.py`
- Create: `tests/integration/test_readiness.py`
- Modify: `tests/support/builders.py`

**Interfaces:**
- Produces: `AttributionPolicy`, `ReviewService.approve`, `ReviewService.correct`, `ReviewService.confirm_corrected_support`, `ReviewService.reject`, `ReviewService.revert`, `ReviewService.set_sensitivity`, and `ReviewService.bulk_approve_low_risk`.
- Produces: `NamedUseService.create`, `PermissionService.grant`, `PermissionService.revoke`, `PermissionService.expire`, `PermissionService.expire_due`, `PermissionService.supersede`, `ReadinessService.report() -> ReadinessReport`, and `is_resume_eligible(session: Session, claim_id: str, revision_id: str, named_use_id: str, permission_event_id: str | None = None) -> EligibilityResult`.
- Consumes: claims, revisions, risks, conflicts, audit events, immutable permission records, and mutation coordinator from Tasks 2, 3, and 7.

- [ ] **Step 1: Write failing decision and eligibility tests**

```python
def test_conflicting_claim_cannot_be_bulk_approved(review_service: ReviewService, conflicting_claim: Claim):
    with pytest.raises(IndividualReviewRequired):
        review_service.bulk_approve_low_risk([
            BulkReviewItem(
                claim_id=conflicting_claim.id,
                revision_id=conflicting_claim.revisions[0].id,
                expected_version=conflicting_claim.version,
            )
        ])


def test_confidential_approved_claim_is_not_resume_eligible(
    review_service: ReviewService, ordinary_claim: Claim
):
    approved = review_service.approve(
        ordinary_claim.id, ordinary_claim.revisions[0].id, ordinary_claim.version
    )
    confidential = review_service.set_sensitivity(
        ordinary_claim.id, Sensitivity.CONFIDENTIAL, approved.version
    )
    result = is_resume_eligible(
        review_service.session,
        ordinary_claim.id,
        confidential.active_revision_id,
        "resume:fixture-1",
    )
    assert result.allowed is False
    assert result.reason == "Approved but confidential; explicit permission is required."
    assert confidential.status == ClaimStatus.APPROVED
```

Add tests for correction, immutable support confirmation, rejection, revert by superseding decision, stale-browser version conflicts, sensitivity-unreviewed blocking, sensitivity changes in both orders, append-only database triggers, readiness counts, explicit expiry-event creation, idempotent due-expiry scanning, and confidential permission denied for wrong claim, revision, named use, expiry, revocation, and supersession. Add attribution denial tests for missing required employer, wrong employer, non-overlapping period, and evidence copied across employers or career periods.

- [ ] **Step 2: Run review tests and verify failure**

Run: `uv run pytest tests/integration/test_review_service.py tests/integration/test_readiness.py -v`

Expected: failure because review and readiness services do not exist.

- [ ] **Step 3: Implement review commands with optimistic version checks**

Use these exact public method signatures: `approve(self, claim_id: str, revision_id: str, expected_version: int, reason: str = "") -> ClaimView`; `correct(self, claim_id: str, value: dict[str, object], display_value: str, employer_key: str | None, period_start: date | None, period_end: date | None, expected_version: int, reason: str) -> ClaimView`; `confirm_corrected_support(self, claim_id: str, revision_id: str, expected_version: int, actor: str, confirmation: str, reason: str) -> ClaimView`; `reject(self, claim_id: str, expected_version: int, reason: str) -> ClaimView`; `revert(self, claim_id: str, target_decision_id: str, expected_version: int, reason: str) -> ClaimView`; `set_sensitivity(self, claim_id: str, sensitivity: Sensitivity, expected_version: int, reason: str = "") -> ClaimView`; and `bulk_approve_low_risk(self, items: Sequence[BulkReviewItem]) -> BulkReviewResult`, where `BulkReviewItem` contains claim ID, revision ID, and expected version.

Every mutation goes through `MutationCoordinator`, checks expected versions, writes a decision and audit event, and increments the claim version in one transaction. Correction starts unsupported and ineligible. Support confirmation appends an immutable `claim_support_assertion` for the same exact revision; it never changes the revision row. Revert writes a new decision with `supersedes_decision_id`. Database triggers and repositories prevent revision, support, audit, or decision update/delete.

`AttributionPolicy` defines: employment titles, dates, responsibilities, achievements, team scope, and metrics require employer; employment responsibilities, achievements, team scope, and metrics also require an applicable period and evidence from the same employer with an overlapping period; contact facts require neither; education/certification facts require their institution or issuer subject; general skills require a subject but no employment period. Eligibility denies missing or mismatched required attribution.

`NamedUseService.create(kind, external_reference, description, actor)` creates the immutable use record. `PermissionService.grant(claim_id, revision_id, named_use_id, actor, confirmation, expires_at, expected_event_version)`, `revoke(permission_event_id, actor, reason, expected_event_version)`, `expire(permission_event_id, actor, reason, expected_event_version)`, and `supersede(permission_event_id, replacement_named_use_id, actor, confirmation, expires_at, expected_event_version)` append events and audit records. `expire_due(now, actor="system")` finds past-due active grants and idempotently appends expiry events through the coordinator. Eligibility denies a past-due grant immediately even before its event is materialized. `ReadinessReport.ready_for_phase_2` is true only when the latest committed import run has all four sources successful, no required factual or sensitivity review, stale claim, or open conflict remains, the locked profile exists, and every approved or corrected claim has an active documentary or user-confirmed support assertion. Eligibility validates status, exact active revision, support assertion, attribution, conflict resolution, sensitivity, and exact active permission event, returning an explicit reason for every denial.

- [ ] **Step 4: Run all domain and integration tests**

Run: `uv run pytest tests/unit tests/integration -v`

Expected: review, eligibility, audit, conflict, import, profile, and storage tests pass.

- [ ] **Step 5: Commit the trustworthy review workflow**

```bash
git add src/job_search_cockpit/facts src/job_search_cockpit/audit src/job_search_cockpit/readiness tests/support/builders.py tests/integration/test_review_service.py tests/integration/test_readiness.py
git commit -m "feat: enforce reviewed and traceable career facts"
```

---

### Task 9: Local session security, import preview, and application shell

**Files:**
- Create: `src/job_search_cockpit/web/security.py`
- Create: `src/job_search_cockpit/web/app.py`
- Create: `src/job_search_cockpit/web/routes/home.py`
- Create: `src/job_search_cockpit/web/routes/imports.py`
- Create: `src/job_search_cockpit/web/templates/base.html`
- Create: `src/job_search_cockpit/web/templates/home.html`
- Create: `src/job_search_cockpit/web/templates/import_preview.html`
- Create: `tests/integration/test_web_security.py`
- Create: `tests/integration/test_home_page.py`
- Modify: `tests/support/web.py`

**Interfaces:**
- Produces: `LaunchSession`, `create_app(settings: Settings, prepared: PreparedVault, launch_session: LaunchSession, active_port: int) -> FastAPI`, protected routes `GET /launch`, `GET /`, `GET /health`, `POST /imports/preview`, and `POST /imports/apply`.
- Consumes: settings, one prepared shared coordinator/service bundle, exact prebound port, import service, and readiness service.

- [ ] **Step 1: Write failing host, token, cookie, and CSRF tests**

```python
def test_protected_page_requires_launch_session(web_client: TestClient):
    response = web_client.get("/")
    assert response.status_code == 401


def test_launch_token_is_exchanged_for_secure_session_cookie(web_client: TestClient, launch: LaunchSession):
    response = web_client.get(f"/launch?token={launch.token}", follow_redirects=False)
    assert response.status_code == 303
    cookie = parse_set_cookie(response.headers["set-cookie"])
    assert cookie.httponly is True
    assert cookie.samesite.lower() == "strict"
    assert cookie.path == "/"
    assert launch.token not in response.headers["location"]
```

Add tests that reject non-loopback Host headers and reject state-changing requests without the matching CSRF token.

Add a test that `POST /imports/preview` shows each curated source as ready, missing, or unreadable without changing the vault, followed by a test that `POST /imports/apply` applies only the matching unexpired preview ID.

Add tests for the five-minute monotonic launch-token boundary, structured cookie attributes, cookie tampering, process restart, cross-session use, cross-localhost-port requests, missing or foreign Origin, forged Host variants, unsupported methods, websocket upgrades, non-cacheable back navigation, and HTML/script-like imported excerpts.

- [ ] **Step 2: Run web-security tests and verify failure**

Run: `uv run pytest tests/integration/test_web_security.py tests/integration/test_home_page.py -v`

Expected: failure because the web application and security layer do not exist.

- [ ] **Step 3: Implement process-local session protection**

```python
@dataclass(slots=True)
class LaunchSession:
    token: str
    cookie_secret: str
    csrf_secret: str
    issued_at: datetime
    monotonic_deadline: float
    consumed: bool

    @classmethod
    def fresh(cls, wall_clock: Clock, monotonic_clock: MonotonicClock) -> "LaunchSession":
        return cls(
            token=secrets.token_urlsafe(32),
            cookie_secret=secrets.token_urlsafe(32),
            csrf_secret=secrets.token_urlsafe(32),
            issued_at=wall_clock.now(),
            monotonic_deadline=monotonic_clock.now() + 300.0,
            consumed=False,
        )
```

`GET /launch` must compare tokens with `secrets.compare_digest`, enforce the injected monotonic deadline even when wall time jumps, create the fully scoped signed session cookie in QA Hardening Requirements, redirect without the token, and set consumed state. All mutation forms must include a signed CSRF value tied to the session. Middleware uses the injected active port to reject every Host other than `127.0.0.1:<active-port>`, validates Origin or Fetch Metadata on mutations, rejects unsupported methods and websocket upgrades, and adds the no-store, CSP, frame, MIME, and referrer headers to every private response. Jinja autoescape cannot be disabled.

Before rendering Home, the route calls idempotent `PermissionService.expire_due` with the current injected time so expiration events become visible during normal use. The Home page must show readiness counts, the next required action, import status, and one primary button. All text must be plain language.

The import preview page must show the four friendly source names, their status, candidate and conflict counts, and one `Import curated profile` action. It must state that originals remain unchanged. Applying an incomplete preview requires a second confirmation and leaves readiness blocked; a malformed preview cannot be applied.

- [ ] **Step 4: Run the security and Home tests**

Run: `uv run pytest tests/integration/test_web_security.py tests/integration/test_home_page.py -v`

Expected: unauthorized, wrong-host, reused-token, and missing-CSRF requests fail; a valid session sees the Home page and can preview and safely apply a curated import.

- [ ] **Step 5: Commit the secured local shell**

```bash
git add src/job_search_cockpit/web tests/support/web.py tests/integration/test_web_security.py tests/integration/test_home_page.py
git commit -m "feat: add secured local cockpit shell"
```

---

### Task 10: Review queue and fact-review screens

**Files:**
- Modify: `src/job_search_cockpit/web/app.py`
- Create: `src/job_search_cockpit/web/routes/review.py`
- Create: `src/job_search_cockpit/web/templates/review_queue.html`
- Create: `src/job_search_cockpit/web/templates/review_fact.html`
- Create: `src/job_search_cockpit/web/templates/confidential_permission.html`
- Create: `tests/integration/test_review_pages.py`
- Modify: `tests/support/web.py`

**Interfaces:**
- Produces routes: `GET /review`, `GET /review/{claim_id}`, `POST /review/{claim_id}/approve`, `POST /review/{claim_id}/correct`, `POST /review/{claim_id}/confirm-corrected-support`, `POST /review/{claim_id}/resolve-conflict`, `POST /review/{claim_id}/reject`, `POST /review/{claim_id}/revert`, `POST /review/{claim_id}/sensitivity`, `POST /review/bulk-approve`, `GET /review/{claim_id}/confidential-use/new`, `POST /review/{claim_id}/confidential-use`, `POST /confidential-use/{permission_event_id}/revoke`, and `POST /confidential-use/{permission_event_id}/supersede`.
- Consumes: the prepared service bundle, fact repository, review service, Task 7 conflict resolver, `NamedUseService`, and `PermissionService`. This task registers the review router in `web/app.py` against those shared service instances.

- [ ] **Step 1: Write failing route tests for the complete review flow**

```python
def test_conflict_page_shows_every_version_and_source(authenticated_client: TestClient, conflict: ConflictGroup):
    response = authenticated_client.get(f"/review/{conflict.claim_id}")
    assert response.status_code == 200
    assert "These sources disagree" in response.text
    for member in conflict.members:
        assert member.display_value in response.text
        assert member.source_label in response.text


def test_stale_review_form_does_not_overwrite_newer_decision(authenticated_client: TestClient, claim: Claim):
    response = authenticated_client.post(
        f"/review/{claim.id}/approve",
        data={
            "revision_id": claim.revisions[0].id,
            "expected_version": claim.version - 1,
            "csrf": authenticated_client.csrf,
        },
    )
    assert response.status_code == 409
    assert "This fact changed in another action" in response.text
```

- [ ] **Step 2: Run review-page tests and verify failure**

Run: `uv run pytest tests/integration/test_review_pages.py -v`

Expected: 404 responses because the review routes and templates do not exist.

- [ ] **Step 3: Implement queue filters and explicit review forms**

The queue defaults to required individual reviews ordered as conflicts, sensitivity-unreviewed, confidential, quantified, dates, titles, team scope, stale, and remaining unresolved claims. Filters are `needs_attention`, `conflicts`, `numbers`, `dates`, `titles`, `sensitivity_unreviewed`, `confidential`, `stale`, and `low_risk`.

The fact page must show the plain-language claim, all source values, employer/time attribution, source file label and locator, why individual review is required, current confidentiality, and one primary action. An open conflict offers only explicit conflict resolution, not normal approval. Correction requires a reason and a separate confirmation of employer/time-period support before eligibility. Rejection and revert require reasons. Marking confidential explains that later resumes cannot use the fact without an exact named-use permission.

Bulk forms submit claim ID, revision ID, and expected version for every visible item. The service recalculates eligibility while holding the mutation lock and rejects the whole batch if a source reimport or other action changed any item.

The confidential-use form first creates an immutable named use from purpose type, external reference, and description, then grants permission for the exact active revision with actor `Varun`, the explicit confirmation text, and optional expiry. It displays existing permission events and provides a reason-required revoke action. Tests cover grant, wrong revision, expired grant, revoke, supersede, CSRF, stale event version, and the fact that permission never changes factual approval or sensitivity.

Successful posts use Post/Redirect/Get. Domain errors render a clear message without losing submitted correction text.

- [ ] **Step 4: Run route and service tests together**

Run: `uv run pytest tests/integration/test_review_pages.py tests/integration/test_review_service.py -v`

Expected: the full review flow passes, including stale-form and CSRF protection.

- [ ] **Step 5: Commit fact-review screens**

```bash
git add src/job_search_cockpit/web/app.py src/job_search_cockpit/web/routes/review.py src/job_search_cockpit/web/templates/review_queue.html src/job_search_cockpit/web/templates/review_fact.html src/job_search_cockpit/web/templates/confidential_permission.html tests/support/web.py tests/integration/test_review_pages.py
git commit -m "feat: add guided fact review experience"
```

---

### Task 11: Locked profile and history screens

**Files:**
- Modify: `src/job_search_cockpit/web/app.py`
- Create: `src/job_search_cockpit/web/routes/search_profile.py`
- Create: `src/job_search_cockpit/web/routes/history.py`
- Create: `src/job_search_cockpit/web/templates/search_profile.html`
- Create: `src/job_search_cockpit/web/templates/history.html`
- Create: `src/job_search_cockpit/web/templates/history_event.html`
- Create: `tests/integration/test_search_profile_page.py`
- Create: `tests/integration/test_history_page.py`

**Interfaces:**
- Produces routes: `GET /search-profile`, `POST /search-profile/new-version`, `GET /history`, and `GET /history/{event_id}`.
- Consumes: search-profile service, append-only audit service, and recovery ledger reader. This task registers the search-profile and history routers in `web/app.py` against the prepared shared service bundle.

- [ ] **Step 1: Write failing page tests for locked values and readable history**

```python
def test_search_profile_page_shows_locked_filters(authenticated_client: TestClient):
    response = authenticated_client.get("/search-profile")
    assert "Hyderabad" in response.text
    assert "₹46 LPA minimum" in response.text
    assert "JPMorganChase" in response.text
    assert "Senior Product Manager" in response.text
    assert "Version 1" in response.text


def test_history_page_does_not_render_sensitive_values_in_list_view(
    authenticated_client: TestClient, confidential_event: AuditEvent
):
    response = authenticated_client.get("/history")
    assert confidential_event.summary in response.text
    assert confidential_event.sensitive_value not in response.text
```

- [ ] **Step 2: Run page tests and verify failure**

Run: `uv run pytest tests/integration/test_search_profile_page.py tests/integration/test_history_page.py -v`

Expected: 404 responses because these routes and templates do not exist.

- [ ] **Step 3: Implement profile display, confirmed revisions, and redacted history**

The profile page groups role level, domains, locations, both allocation dimensions, compensation, exclusions, and practical constraints. It states that filters are applied to every future discovery run. The revision form requires a reason, active version, old/new diff digest, and the exact confirmation phrase from Task 4; it previews old and new values before creation. Stale or simultaneous submissions are rejected through the mutation coordinator without creating a version.

The history page shows timestamp, action, area, source, and plain-language summary from both database audit events and the external recovery ledger. Confidential values are replaced with `Confidential value hidden`. The event-detail route shows safe before/after values, reason, source label, superseded event, and recovery-ledger context only for non-confidential events; confidential details remain redacted. Tests cover unknown IDs, confidential events, restore events that predate the restored database, and permission to view only through an authenticated local session.

- [ ] **Step 4: Run profile, history, and versioning tests**

Run: `uv run pytest tests/integration/test_search_profile_page.py tests/integration/test_history_page.py tests/integration/test_search_profile_versioning.py -v`

Expected: locked filters render exactly, profile changes create versions, and confidential values remain hidden in list view.

- [ ] **Step 5: Commit profile and history screens**

```bash
git add src/job_search_cockpit/web/app.py src/job_search_cockpit/web/routes/search_profile.py src/job_search_cockpit/web/routes/history.py src/job_search_cockpit/web/templates/search_profile.html src/job_search_cockpit/web/templates/history.html src/job_search_cockpit/web/templates/history_event.html tests/integration/test_search_profile_page.py tests/integration/test_history_page.py
git commit -m "feat: show locked profile and decision history"
```

---

### Task 12: Minimalist styling and accessible browser behavior

**Files:**
- Create: `src/job_search_cockpit/web/static/app.css`
- Modify: all templates under `src/job_search_cockpit/web/templates/`
- Create: `tests/e2e/test_accessibility_flow.py`
- Create: `tests/e2e/test_responsive_layout.py`
- Modify: `tests/support/web.py`

**Interfaces:**
- Produces: shared CSS tokens and consistent template components for navigation, cards, status marks, forms, confirmations, focus, and responsive layout.
- Consumes: all routes and templates from Tasks 9–11.

- [ ] **Step 1: Write browser checks for keyboard navigation and responsive layout**

```python
def test_primary_review_flow_is_keyboard_reachable(page: Page, running_app: RunningApp):
    page.goto(running_app.launch_url)
    page.keyboard.press("Tab")
    assert page.locator(":focus").get_attribute("href") == "#main-content"
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Review facts")).to_be_focused()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_home_has_no_horizontal_scroll(page: Page, running_app: RunningApp, width: int):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(running_app.launch_url)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
```

Add browser tests that tab through every control on all five screens, restore focus after validation, announce errors through an accessible live region, pass the `assert_accessible_page` semantic/label/landmark audit owned by `tests/support/web.py`, meet computed contrast requirements, honor reduced motion, and reflow without two-dimensional scrolling at 200% zoom.

- [ ] **Step 2: Run the browser checks before styling**

Run: `uv run playwright install chromium && uv run pytest tests/e2e/test_accessibility_flow.py tests/e2e/test_responsive_layout.py -v`

Expected: tests fail because skip links, complete focus behavior, accessible validation, and responsive styles are absent.

- [ ] **Step 3: Implement the approved visual system**

Use system fonts, `#f5f5f7` page background, `#ffffff` surfaces, `#1d1d1f` primary text, `#6e6e73` secondary text, and `#0066cc` for the single action accent. Use a maximum content width of `72rem`, generous spacing, 44-pixel minimum interactive targets, visible two-pixel focus outlines, and no decorative animation.

Each screen must have one `h1`, one visually dominant action, semantic landmarks, associated form labels, clear validation summaries, and details hidden behind native `details` elements when they are not needed for the current decision. Never use colour as the only status signal.

- [ ] **Step 4: Run all page and browser checks, then capture review screenshots**

Run: `uv run pytest tests/integration/test_home_page.py tests/integration/test_review_pages.py tests/integration/test_search_profile_page.py tests/integration/test_history_page.py tests/e2e -v`

Expected: all interface tests pass at 390, 768, and 1440 pixel widths. Save screenshots to the ignored Playwright output folder for visual inspection; verify no clipping, overlapping text, dense panels, or hidden focus indicators.

- [ ] **Step 5: Commit the approved minimalist interface**

```bash
git add src/job_search_cockpit/web tests/support/web.py tests/e2e
git commit -m "feat: apply minimalist accessible cockpit design"
```

---

### Task 13: Non-technical setup, launch, and end-to-end acceptance

**Files:**
- Create: `src/job_search_cockpit/launcher.py`
- Create: `Setup Job Search Cockpit.command`
- Create: `Start Job Search Cockpit.command`
- Create: `README.md`
- Create: `tests/integration/test_launcher.py`
- Create: `tests/integration/test_startup_state.py`
- Create: `tests/e2e/test_phase_1_acceptance.py`
- Modify: `tests/support/database.py`
- Modify: `tests/support/web.py`

**Interfaces:**
- Produces: `LaunchPlan`, `build_launch_plan(settings: Settings) -> LaunchPlan`, `prepare_vault(settings: Settings) -> PreparedVault`, `main() -> int`, a one-time setup launcher, a normal start launcher, and the complete Phase 1 dry run.
- Consumes: every completed Phase 1 service and route.

- [ ] **Step 1: Write failing launcher and acceptance tests**

```python
def test_launcher_binds_preopened_loopback_socket(monkeypatch: MonkeyPatch, settings: Settings):
    launch = build_launch_plan(settings)
    assert launch.socket.getsockname()[0] == "127.0.0.1"
    assert launch.url.startswith("http://127.0.0.1:")
    assert "/launch?token=" in launch.url


def test_phase_1_dry_run(page: Page, running_app_with_curated_fixtures: RunningApp):
    page.goto(running_app_with_curated_fixtures.launch_url)
    page.get_by_role("button", name="Preview curated profile").click()
    expect(page.get_by_text("Your original files will not be changed")).to_be_visible()
    page.get_by_role("button", name="Import curated profile").click()
    expect(page.get_by_text("These sources disagree")).to_be_visible()
    assert_readiness_is_false(page)
    resolve_all_fixture_reviews(page)
    expect(page.get_by_text("Your verified profile is ready for Phase 2")).to_be_visible()
```

- [ ] **Step 2: Run launcher and acceptance tests and verify failure**

Run: `uv run pytest tests/integration/test_launcher.py tests/e2e/test_phase_1_acceptance.py -v`

Expected: failure because the launcher, scripts, and complete dry run do not exist.

- [ ] **Step 3: Implement one-time setup and normal start**

`launcher.py` must pre-bind an available socket on `127.0.0.1`, create a fresh `LaunchSession` from injected wall and monotonic clocks, call `create_app(settings, prepared, launch_session, active_port)`, start Uvicorn with the pre-bound socket, and open the single-use launch URL in the default browser. It must print only plain-language start, stop, and error messages; it must not print the launch token after opening the browser.

Before creating the launch plan, `prepare_vault` enforces `sys.platform == "darwin"`, creates and verifies owner-only directories and files, acquires and retains `AppInstanceLock`, validates or creates the database, runs `PRAGMA integrity_check`, seeds locked profile version 1 exactly once, reconciles unreconciled import-attempt ledger events idempotently, materializes due permission-expiry events, and returns `PreparedVault(instance_lock, coordinator, engine, services)`. For an existing older schema, it creates a verified backup, migrates and validates a copy, and asks the coordinator to install the copy through the restore-safe quiesced replacement sequence. A failed platform check, lock, migration, integrity, or recovery-ledger hash check returns a plain-language recovery action and never starts Uvicorn. Shutdown drains requests and mutations, disposes the engine, and releases the instance lock last.

`Setup Job Search Cockpit.command` changes to its own directory, verifies macOS, Python 3.12, and `uv`, runs `uv sync --frozen`, installs Chromium for Playwright-based verification, and prints a clear success message. When prerequisites are missing, it prints `brew install python@3.12 uv` and the Homebrew installation website, then exits without modifying the system. `Start Job Search Cockpit.command` changes to its own directory and runs `uv run python -m job_search_cockpit.launcher`. Both files must be executable and quote paths containing spaces.

`test_startup_state.py` covers a fresh vault, existing healthy vault, profile seed idempotency, backed-up copy migration, failed migration with unchanged original, failed integrity check, locked vault, second instance, exact lock release ordering, recovery-ledger attempt reconciliation without duplicates, due permission expiry, corrupted ledger refusal, permissive umask permissions, and non-macOS refusal. Source replacement and symlink tests remain owned by the import service because each read must revalidate the descriptor.

`README.md` must contain non-technical sections: Set up once, Start the cockpit, Stop the cockpit, Where private data stays, Create a safety copy, Restore help, and What Phase 1 does not do. It must state that original sources are never edited and no job search occurs yet.

The dry run must prove each incomplete state: preview alone is not imported; imported conflicts keep readiness false; resolving conflicts alone remains false while risky or sensitivity-unreviewed facts remain; each risky fact receives individual review; sensitivity is explicitly chosen; only eligible low-risk facts are grouped; stale and unsupported facts remain denied; readiness becomes true only after every required fixture decision is complete.

- [ ] **Step 4: Run the complete quality and acceptance suite**

Run: `uv run ruff check src tests && uv run mypy src && uv run pytest -v`

Expected: lint, type checking, all unit tests, all integration tests, all browser tests, and the Phase 1 dry run pass.

Then run: `git status --short`

Expected: only intentionally ignored local outputs are absent from status; no database, backup, log, token, or Playwright artifact is tracked.

- [ ] **Step 5: Commit launch and acceptance deliverables**

```bash
git add README.md "Setup Job Search Cockpit.command" "Start Job Search Cockpit.command" src/job_search_cockpit/launcher.py tests/support/database.py tests/support/web.py tests/integration/test_launcher.py tests/integration/test_startup_state.py tests/e2e/test_phase_1_acceptance.py
git commit -m "feat: complete Phase 1 local cockpit workflow"
```

---

## Final Verification Checklist

- [ ] Run `uv run ruff check src tests` with no findings.
- [ ] Run `uv run mypy src` with no errors.
- [ ] Run `uv run pytest -v` with all tests passing.
- [ ] Start the application using `Start Job Search Cockpit.command`.
- [ ] Confirm the application is unreachable through a non-loopback interface.
- [ ] Confirm an invalid, reused, or expired launch token cannot open the cockpit.
- [ ] With Varun's separate authorization, preview the four real curated sources and inspect counts without applying changes during QA.
- [ ] Confirm product-years, team-count, title, chronology, and metric conflicts appear for review.
- [ ] Confirm sanitized source-document timestamps and hashes do not change after import; compare real source hashes only during the separately authorized preview.
- [ ] Confirm the locked merged golden profile contains the assessment targets, both allocations, and the explicitly confirmed JPMorganChase exclusion override.
- [ ] Confirm an unresolved, rejected, or confidential-without-permission claim is not resume-eligible.
- [ ] Confirm wrong-claim, wrong-revision, wrong-use, expired, revoked, and superseded confidential permissions are denied.
- [ ] Confirm a newer incomplete import remains incomplete after restart even when an older run succeeded.
- [ ] Confirm simultaneous mutations are serialized and a second cockpit process is refused.
- [ ] Restore a verified sanitized-fixture backup and confirm a corrupted backup leaves the active vault unchanged.
- [ ] Confirm the Home screen gives one clear next action in plain language.
- [ ] Review every primary and supporting screen at narrow, medium, and wide browser sizes.
- [ ] Confirm the Git history contains no database, backup, log, token, or private source copy.
- [ ] Produce the final readiness report and record any remaining user decisions without guessing them.
