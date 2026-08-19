# Phase 1 Fact Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, local Job Search Cockpit that imports Varun's curated profile sources, requires review of risky or conflicting facts, preserves a locked job-search profile, and prevents unsupported information from becoming resume-eligible.

**Architecture:** A Python 3.12 FastAPI application serves minimalist, server-rendered pages only on `127.0.0.1`. SQLite stores versioned claims, evidence, decisions, audit events, and search-profile versions under the macOS Application Support directory; focused services own importing, conflict detection, review, readiness, backup, and security.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic Settings, Jinja2, small vanilla JavaScript helpers, SQLite, pytest, HTTPX TestClient, Ruff, mypy, and Playwright for end-to-end browser checks.

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
│   ├── launcher.py
│   ├── storage/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── backup.py
│   ├── facts/
│   │   ├── types.py
│   │   ├── repository.py
│   │   ├── conflicts.py
│   │   └── review.py
│   ├── imports/
│   │   ├── types.py
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
    ├── fixtures/sources/
    ├── unit/
    ├── integration/
    └── e2e/
```

Each package has one responsibility: importers read sources, fact services decide review behavior, the search-profile service owns the locked filters, storage owns durability, and web routes translate those services into plain-language screens.

---

### Task 1: Project foundation and safe configuration

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `src/job_search_cockpit/__init__.py`
- Create: `src/job_search_cockpit/config.py`
- Create: `src/job_search_cockpit/logging.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_logging.py`

**Interfaces:**
- Produces: `SourceSpec`, `SourceKind`, `Settings`, `Settings.for_tests(data_dir: Path, source_root: Path) -> Settings`, and `configure_logging(settings: Settings) -> None`.
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


class Settings(BaseSettings):
    host: Literal["127.0.0.1"] = "127.0.0.1"
    data_dir: Path = Path.home() / "Library/Application Support/JobSearchCockpit"
    source_root: Path = Path("/Users/nandurivarun/Desktop/Documents/CV")

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
        return cls(data_dir=data_dir, source_root=source_root)
```

`.gitignore` must include `.venv/`, `.DS_Store`, `*.sqlite3`, `*.sqlite3-*`, `backups/`, `logs/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `__pycache__/`, and Playwright output folders.

`configure_logging` must create `settings.data_dir / "logs"` with mode `0700`, write operational event names and exception types, and run every message through `redact_sensitive`. Redaction must cover email addresses, phone-like sequences, launch tokens, CSRF values, cookies, and claim values supplied through structured logging fields.

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
- Produces tables: `source_documents`, `claims`, `claim_revisions`, `claim_evidence`, `conflict_groups`, `conflict_members`, `decisions`, `audit_events`, and `search_profile_versions`.
- Consumes: `Settings` from Task 1.

- [ ] **Step 1: Write a migration test against a temporary database**

```python
def test_initial_migration_creates_all_phase_1_tables(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'vault.sqlite3'}"
    upgrade_database(database_url)
    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert tables == {
        "alembic_version", "source_documents", "claims", "claim_revisions",
        "claim_evidence", "conflict_groups", "conflict_members", "decisions",
        "audit_events", "search_profile_versions",
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
    created_at: Mapped[datetime]
```

Add unique constraints for `claims.canonical_key`, source `(path, content_hash)`, search-profile version number, and conflict membership. Foreign keys must prevent deleting evidence or decisions that are already referenced.

- [ ] **Step 4: Run schema and quality checks**

Run: `uv run pytest tests/integration/test_database_schema.py -v && uv run ruff check src tests && uv run mypy src`

Expected: migration test passes and quality checks report no errors.

- [ ] **Step 5: Commit the vault schema**

```bash
git add alembic.ini alembic src/job_search_cockpit/storage tests/integration/test_database_schema.py
git commit -m "feat: add versioned fact vault schema"
```

---

### Task 3: Safety copies and all-or-nothing changes

**Files:**
- Create: `src/job_search_cockpit/storage/backup.py`
- Modify: `src/job_search_cockpit/storage/database.py`
- Create: `tests/unit/test_backup.py`
- Create: `tests/integration/test_atomic_changes.py`

**Interfaces:**
- Produces: `create_safety_copy(database_path: Path, backup_dir: Path, reason: str) -> BackupResult`.
- Produces: `run_guarded_change(settings: Settings, operation: Callable[[Session], T], reason: str) -> T`.
- Consumes: the database factory from Task 2.

- [ ] **Step 1: Write tests for successful backup, failed backup, and rollback**

```python
def test_safety_copy_has_timestamp_hash_and_reason(tmp_path: Path):
    source = tmp_path / "vault.sqlite3"
    source.write_bytes(b"vault")
    result = create_safety_copy(source, tmp_path / "backups", "before_review")
    assert result.path.exists()
    assert result.sha256 == sha256(b"vault").hexdigest()
    assert result.reason == "before_review"


def test_guarded_change_rolls_back_when_operation_fails(vault_settings: Settings):
    with pytest.raises(RuntimeError, match="simulated failure"):
        run_guarded_change(vault_settings, failing_operation, "import")
    assert count_rows(vault_settings.database_path, "claims") == 0
```

- [ ] **Step 2: Run the tests and confirm both fail**

Run: `uv run pytest tests/unit/test_backup.py tests/integration/test_atomic_changes.py -v`

Expected: failures because backup and guarded-change functions are missing.

- [ ] **Step 3: Implement safe-copy and transaction behavior**

`create_safety_copy` must use SQLite's online backup API when a database exists, create the destination directory with mode `0700`, calculate SHA-256 after copying, and return:

```python
@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    sha256: str
    reason: str
    created_at: datetime
```

`run_guarded_change` must refuse the operation if the required safety copy fails, wrap the operation in one SQLAlchemy transaction, and commit only after the operation returns successfully.

- [ ] **Step 4: Run focused and full storage tests**

Run: `uv run pytest tests/unit/test_backup.py tests/integration/test_atomic_changes.py tests/integration/test_database_schema.py -v`

Expected: all storage tests pass.

- [ ] **Step 5: Commit safety behavior**

```bash
git add src/job_search_cockpit/storage tests/unit/test_backup.py tests/integration/test_atomic_changes.py
git commit -m "feat: protect vault changes with safety copies"
```

---

### Task 4: Locked target job-search profile

**Files:**
- Create: `src/job_search_cockpit/search_profile/catalog.py`
- Create: `src/job_search_cockpit/search_profile/service.py`
- Create: `tests/unit/test_search_profile_catalog.py`
- Create: `tests/integration/test_search_profile_versioning.py`

**Interfaces:**
- Produces: `SearchProfilePayload`, `seed_profile_v1(session: Session) -> SearchProfileVersion`, `get_active_profile(session: Session) -> SearchProfileVersion`, and `confirm_profile_change(session: Session, payload: SearchProfilePayload, reason: str, confirmation: str) -> SearchProfileVersion`.
- Consumes: `SearchProfileVersion` storage model and audit table from Task 2.

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


def test_profile_change_requires_exact_confirmation(session: Session):
    with pytest.raises(ProfileConfirmationError):
        confirm_profile_change(session, changed_profile(), "role update", "yes")
```

- [ ] **Step 2: Run the profile tests and verify failure**

Run: `uv run pytest tests/unit/test_search_profile_catalog.py tests/integration/test_search_profile_versioning.py -v`

Expected: failure because the catalog and service do not exist.

- [ ] **Step 3: Implement the approved profile as typed data**

`SearchProfilePayload` must contain immutable tuples for eligible roles, priority domains, excluded role patterns, eligible locations, search allocation, sponsorship requirements, compensation floors, excluded employers, notice period, and profile-change rules.

The version-1 constants must copy the approved design exactly. The confirmation string must be `CREATE NEW SEARCH PROFILE VERSION`; any other text fails without changing the active profile. A successful change deactivates the prior version, inserts the new version, and appends an audit event in one transaction.

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
- Create: `src/job_search_cockpit/imports/profile_json.py`
- Create: `src/job_search_cockpit/imports/master_profile.py`
- Create: `src/job_search_cockpit/imports/assessment.py`
- Create: `src/job_search_cockpit/imports/workflow.py`
- Create: `tests/fixtures/sources/assessment.md`
- Create: `tests/fixtures/sources/profile.json`
- Create: `tests/fixtures/sources/master_profile.md`
- Create: `tests/fixtures/sources/resume_workflow.md`
- Create: `tests/unit/test_importers.py`

**Interfaces:**
- Produces: `CandidateClaim`, `EvidenceRef`, `ImportResult`, and `SourceImporter` protocol.
- Produces importers with `read(spec: SourceSpec) -> ImportResult`.
- Consumes: source manifest types from Task 1.

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
    declared_risks: frozenset[RiskFlag] = frozenset()
```

The JSON importer must extract contact data, experience identity fields, each experience bullet, education, certifications, languages, summary, total years, and product years with JSONPath-like locators.

The master-profile importer must extract explicit facts under Contact, High-Impact Metrics, Professional Experience, Education, Certifications, and Languages. Positioning and headline options remain candidate wording, not approved employment facts.

The assessment importer must return the locked search-profile data and assessment claims such as stated years of direct product ownership. Recommendations and market commentary must not become career facts.

The workflow importer must return policy claims governing truthful evidence, ATS compatibility, and non-guaranteed outcomes; it must not create employment achievements.

- [ ] **Step 4: Run importer tests and static checks**

Run: `uv run pytest tests/unit/test_importers.py -v && uv run ruff check src tests && uv run mypy src`

Expected: all importer tests pass and every candidate retains a source hash and locator.

- [ ] **Step 5: Commit deterministic importers**

```bash
git add src/job_search_cockpit/imports tests/fixtures/sources tests/unit/test_importers.py
git commit -m "feat: parse curated profile sources deterministically"
```

---

### Task 6: Import orchestration, deduplication, and source changes

**Files:**
- Create: `src/job_search_cockpit/imports/service.py`
- Create: `tests/integration/test_import_service.py`

**Interfaces:**
- Produces: `ImportService.preview() -> ImportPreview` and `ImportService.apply(preview_id: str) -> AppliedImport`.
- Consumes: Task 3 guarded changes, Task 5 importers, and Task 2 vault models.

- [ ] **Step 1: Write failing repeat-import and changed-source tests**

```python
def test_identical_import_is_idempotent(import_service: ImportService):
    first = import_service.apply(import_service.preview().id)
    second = import_service.apply(import_service.preview().id)
    assert second.created_claims == 0
    assert second.created_revisions == 0
    assert second.source_statuses == first.source_statuses


def test_changed_source_creates_candidate_revision_without_overwriting_decision(
    approved_vault: VaultHarness,
):
    approved_vault.change_fixture("profile_json", "pm_years", 9)
    result = approved_vault.import_service.apply(approved_vault.import_service.preview().id)
    assert result.changed_claims == ("profile.product_years",)
    assert approved_vault.claim("profile.product_years").status == ClaimStatus.UNRESOLVED
    assert approved_vault.previous_approved_revision("profile.product_years").display_value == "8"
```

- [ ] **Step 2: Run import-service tests and verify failure**

Run: `uv run pytest tests/integration/test_import_service.py -v`

Expected: failure because `ImportService` does not exist.

- [ ] **Step 3: Implement preview/apply with content hashing**

`preview()` reads all available sources, reports missing or malformed files in plain language, stores no database rows, and returns counts plus a random preview ID held in process memory.

`apply()` verifies the preview has not expired, creates a safety copy, and writes the complete import in one transaction. Claim identity is `canonical_key`; revision identity is the SHA-256 of canonical key, normalized value, source hash, and source locator. The service must not duplicate identical source documents, claims, revisions, or evidence.

If one source is unreadable, valid sources may still apply, but the result must mark the import incomplete and readiness must remain blocked until all four source statuses are successful.

- [ ] **Step 4: Run import orchestration tests**

Run: `uv run pytest tests/integration/test_import_service.py tests/unit/test_importers.py -v`

Expected: idempotency, changed-source review, missing-source reporting, and atomic rollback tests pass.

- [ ] **Step 5: Commit import orchestration**

```bash
git add src/job_search_cockpit/imports/service.py tests/integration/test_import_service.py
git commit -m "feat: import curated claims safely and idempotently"
```

---

### Task 7: Risk classification and conflict detection

**Files:**
- Create: `src/job_search_cockpit/facts/types.py`
- Create: `src/job_search_cockpit/facts/conflicts.py`
- Create: `tests/unit/test_risk_classification.py`
- Create: `tests/integration/test_conflicts.py`

**Interfaces:**
- Produces: `RiskFlag`, `classify_risks(candidate: CandidateClaim) -> frozenset[RiskFlag]`, `normalize_for_comparison(candidate: CandidateClaim) -> str`, and `rebuild_conflicts(session: Session) -> ConflictSummary`.
- Consumes: candidate claims from Task 5 and stored revisions from Task 6.

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

Risk flags are `CONFLICT`, `QUANTIFIED`, `DATE`, `TITLE`, `TEAM_SCOPE`, and `CONFIDENTIAL`. Classification uses canonical-key metadata first and conservative text detection second. Monetary values, percentages, counts, ranges, and values with `+` are quantified.

Conflict comparison must normalize whitespace, dashes, case, and equivalent date punctuation without erasing meaningful numeric differences. Distinct normalized values for one canonical key create an open conflict group and apply `CONFLICT` to every member. The service presents all versions and never selects a winner.

- [ ] **Step 4: Run conflict and import tests together**

Run: `uv run pytest tests/unit/test_risk_classification.py tests/integration/test_conflicts.py tests/integration/test_import_service.py -v`

Expected: known conflicts are open and exact duplicates are not conflicts.

- [ ] **Step 5: Commit review-risk logic**

```bash
git add src/job_search_cockpit/facts tests/unit/test_risk_classification.py tests/integration/test_conflicts.py
git commit -m "feat: classify risky facts and expose conflicts"
```

---

### Task 8: Review decisions, audit history, and resume eligibility

**Files:**
- Create: `src/job_search_cockpit/facts/repository.py`
- Create: `src/job_search_cockpit/facts/review.py`
- Create: `src/job_search_cockpit/audit/service.py`
- Create: `src/job_search_cockpit/readiness/service.py`
- Create: `tests/integration/test_review_service.py`
- Create: `tests/integration/test_readiness.py`

**Interfaces:**
- Produces: `ReviewService.approve`, `ReviewService.correct`, `ReviewService.reject`, `ReviewService.set_sensitivity`, and `ReviewService.bulk_approve_low_risk`.
- Produces: `ReadinessService.report() -> ReadinessReport` and `is_resume_eligible(session: Session, claim_id: str, permission: ConfidentialUsePermission | None = None) -> EligibilityResult`.
- Consumes: claims, revisions, risks, conflicts, audit events, and guarded changes from Tasks 2, 3, and 7.

- [ ] **Step 1: Write failing decision and eligibility tests**

```python
def test_conflicting_claim_cannot_be_bulk_approved(review_service: ReviewService, conflicting_claim: Claim):
    with pytest.raises(IndividualReviewRequired):
        review_service.bulk_approve_low_risk([conflicting_claim.id])


def test_confidential_approved_claim_is_not_resume_eligible(
    review_service: ReviewService, ordinary_claim: Claim
):
    review_service.approve(ordinary_claim.id, ordinary_claim.revisions[0].id, ordinary_claim.version)
    review_service.set_sensitivity(ordinary_claim.id, Sensitivity.CONFIDENTIAL, ordinary_claim.version + 1)
    result = is_resume_eligible(review_service.session, ordinary_claim.id)
    assert result.allowed is False
    assert result.reason == "Approved but confidential; explicit permission is required."
```

Add tests for correction, rejection, stale-browser version conflicts, confidential permission, append-only history, and readiness counts.

- [ ] **Step 2: Run review tests and verify failure**

Run: `uv run pytest tests/integration/test_review_service.py tests/integration/test_readiness.py -v`

Expected: failure because review and readiness services do not exist.

- [ ] **Step 3: Implement review commands with optimistic version checks**

Use these exact public method signatures: `approve(self, claim_id: str, revision_id: str, expected_version: int, reason: str = "") -> ClaimView`; `correct(self, claim_id: str, value: dict[str, object], display_value: str, expected_version: int, reason: str) -> ClaimView`; `reject(self, claim_id: str, expected_version: int, reason: str) -> ClaimView`; `set_sensitivity(self, claim_id: str, sensitivity: Sensitivity, expected_version: int, reason: str = "") -> ClaimView`; and `bulk_approve_low_risk(self, claim_ids: Sequence[str]) -> BulkReviewResult`.

Every mutation creates a safety copy, checks `expected_version`, writes a decision and audit event, and increments the claim version in one transaction. Correction creates a user-confirmed revision linked to the source revisions it clarifies. Audit rows have no update or delete service.

`ReadinessReport.ready_for_phase_2` is true only when all four sources imported successfully, no required review remains, the locked profile exists, and every approved claim has evidence. The eligibility function must return an explicit reason for every denial.

- [ ] **Step 4: Run all domain and integration tests**

Run: `uv run pytest tests/unit tests/integration -v`

Expected: review, eligibility, audit, conflict, import, profile, and storage tests pass.

- [ ] **Step 5: Commit the trustworthy review workflow**

```bash
git add src/job_search_cockpit/facts src/job_search_cockpit/audit src/job_search_cockpit/readiness tests/integration/test_review_service.py tests/integration/test_readiness.py
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

**Interfaces:**
- Produces: `LaunchSession`, `create_app(settings: Settings, launch_session: LaunchSession) -> FastAPI`, protected routes `GET /launch`, `GET /`, `GET /health`, `POST /imports/preview`, and `POST /imports/apply`.
- Consumes: settings, import service, and readiness service.

- [ ] **Step 1: Write failing host, token, cookie, and CSRF tests**

```python
def test_protected_page_requires_launch_session(web_client: TestClient):
    response = web_client.get("/")
    assert response.status_code == 401


def test_launch_token_is_exchanged_for_secure_session_cookie(web_client: TestClient, launch: LaunchSession):
    response = web_client.get(f"/launch?token={launch.token}", follow_redirects=False)
    assert response.status_code == 303
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert launch.token not in response.headers["location"]
```

Add tests that reject non-loopback Host headers and reject state-changing requests without the matching CSRF token.

Add a test that `POST /imports/preview` shows each curated source as ready, missing, or unreadable without changing the vault, followed by a test that `POST /imports/apply` applies only the matching unexpired preview ID.

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

    @classmethod
    def fresh(cls) -> "LaunchSession":
        return cls(
            token=secrets.token_urlsafe(32),
            cookie_secret=secrets.token_urlsafe(32),
            csrf_secret=secrets.token_urlsafe(32),
            issued_at=datetime.now(UTC),
        )
```

`GET /launch` must compare tokens with `secrets.compare_digest`, create a signed `HttpOnly`, `SameSite=Strict` session cookie, redirect without the token, and make the launch token single-use. All mutation forms must include a signed CSRF value tied to the session. Middleware must reject Host values other than `127.0.0.1:<active-port>`.

The Home page must show readiness counts, the next required action, import status, and one primary button. All text must be plain language.

The import preview page must show the four friendly source names, their status, candidate and conflict counts, and one `Import curated profile` action. It must state that originals remain unchanged. Applying an incomplete preview requires a second confirmation and leaves readiness blocked; a malformed preview cannot be applied.

- [ ] **Step 4: Run the security and Home tests**

Run: `uv run pytest tests/integration/test_web_security.py tests/integration/test_home_page.py -v`

Expected: unauthorized, wrong-host, reused-token, and missing-CSRF requests fail; a valid session sees the Home page and can preview and safely apply a curated import.

- [ ] **Step 5: Commit the secured local shell**

```bash
git add src/job_search_cockpit/web tests/integration/test_web_security.py tests/integration/test_home_page.py
git commit -m "feat: add secured local cockpit shell"
```

---

### Task 10: Review queue and fact-review screens

**Files:**
- Create: `src/job_search_cockpit/web/routes/review.py`
- Create: `src/job_search_cockpit/web/templates/review_queue.html`
- Create: `src/job_search_cockpit/web/templates/review_fact.html`
- Create: `tests/integration/test_review_pages.py`

**Interfaces:**
- Produces routes: `GET /review`, `GET /review/{claim_id}`, `POST /review/{claim_id}/approve`, `POST /review/{claim_id}/correct`, `POST /review/{claim_id}/reject`, `POST /review/{claim_id}/sensitivity`, and `POST /review/bulk-approve`.
- Consumes: fact repository and review service from Task 8.

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
        data={"revision_id": claim.revisions[0].id, "expected_version": claim.version - 1, "csrf": valid_csrf()},
    )
    assert response.status_code == 409
    assert "This fact changed in another action" in response.text
```

- [ ] **Step 2: Run review-page tests and verify failure**

Run: `uv run pytest tests/integration/test_review_pages.py -v`

Expected: 404 responses because the review routes and templates do not exist.

- [ ] **Step 3: Implement queue filters and explicit review forms**

The queue defaults to required individual reviews ordered as conflicts, confidential, quantified, dates, titles, team scope, and remaining unresolved claims. Filters are `needs_attention`, `conflicts`, `numbers`, `dates`, `titles`, `confidential`, and `low_risk`.

The fact page must show the plain-language claim, all source values, source file label and locator, why individual review is required, current confidentiality, and one primary action. Correction requires a reason. Rejection requires a reason. Marking confidential explains that later resumes cannot use the fact without explicit permission.

Successful posts use Post/Redirect/Get. Domain errors render a clear message without losing submitted correction text.

- [ ] **Step 4: Run route and service tests together**

Run: `uv run pytest tests/integration/test_review_pages.py tests/integration/test_review_service.py -v`

Expected: the full review flow passes, including stale-form and CSRF protection.

- [ ] **Step 5: Commit fact-review screens**

```bash
git add src/job_search_cockpit/web/routes/review.py src/job_search_cockpit/web/templates/review_queue.html src/job_search_cockpit/web/templates/review_fact.html tests/integration/test_review_pages.py
git commit -m "feat: add guided fact review experience"
```

---

### Task 11: Locked profile and history screens

**Files:**
- Create: `src/job_search_cockpit/web/routes/search_profile.py`
- Create: `src/job_search_cockpit/web/routes/history.py`
- Create: `src/job_search_cockpit/web/templates/search_profile.html`
- Create: `src/job_search_cockpit/web/templates/history.html`
- Create: `tests/integration/test_search_profile_page.py`
- Create: `tests/integration/test_history_page.py`

**Interfaces:**
- Produces routes: `GET /search-profile`, `POST /search-profile/new-version`, and `GET /history`.
- Consumes: search-profile service and append-only audit service.

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

The profile page groups role level, domains, locations, compensation, exclusions, and practical constraints. It states that filters are applied to every future discovery run. The revision form requires a reason and the exact confirmation phrase from Task 4; it previews old and new values before creation.

The history page shows timestamp, action, area, source, and plain-language summary. Confidential values are replaced with `Confidential value hidden`; exact source paths are displayed as friendly labels unless the user opens a specific non-confidential event.

- [ ] **Step 4: Run profile, history, and versioning tests**

Run: `uv run pytest tests/integration/test_search_profile_page.py tests/integration/test_history_page.py tests/integration/test_search_profile_versioning.py -v`

Expected: locked filters render exactly, profile changes create versions, and confidential values remain hidden in list view.

- [ ] **Step 5: Commit profile and history screens**

```bash
git add src/job_search_cockpit/web/routes/search_profile.py src/job_search_cockpit/web/routes/history.py src/job_search_cockpit/web/templates/search_profile.html src/job_search_cockpit/web/templates/history.html tests/integration/test_search_profile_page.py tests/integration/test_history_page.py
git commit -m "feat: show locked profile and decision history"
```

---

### Task 12: Minimalist styling and accessible browser behavior

**Files:**
- Create: `src/job_search_cockpit/web/static/app.css`
- Modify: all templates under `src/job_search_cockpit/web/templates/`
- Create: `tests/e2e/test_accessibility_flow.py`
- Create: `tests/e2e/test_responsive_layout.py`

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

- [ ] **Step 2: Run the browser checks before styling**

Run: `uv run playwright install chromium && uv run pytest tests/e2e/test_accessibility_flow.py tests/e2e/test_responsive_layout.py -v`

Expected: tests fail because skip links, focus order, and responsive styles are absent.

- [ ] **Step 3: Implement the approved visual system**

Use system fonts, `#f5f5f7` page background, `#ffffff` surfaces, `#1d1d1f` primary text, `#6e6e73` secondary text, and `#0066cc` for the single action accent. Use a maximum content width of `72rem`, generous spacing, 44-pixel minimum interactive targets, visible two-pixel focus outlines, and no decorative animation.

Each screen must have one `h1`, one visually dominant action, semantic landmarks, associated form labels, clear validation summaries, and details hidden behind native `details` elements when they are not needed for the current decision. Never use colour as the only status signal.

- [ ] **Step 4: Run all page and browser checks, then capture review screenshots**

Run: `uv run pytest tests/integration/test_home_page.py tests/integration/test_review_pages.py tests/integration/test_search_profile_page.py tests/integration/test_history_page.py tests/e2e -v`

Expected: all interface tests pass at 390, 768, and 1440 pixel widths. Save screenshots to the ignored Playwright output folder for visual inspection; verify no clipping, overlapping text, dense panels, or hidden focus indicators.

- [ ] **Step 5: Commit the approved minimalist interface**

```bash
git add src/job_search_cockpit/web tests/e2e
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
- Create: `tests/e2e/test_phase_1_acceptance.py`

**Interfaces:**
- Produces: `main() -> int`, a one-time setup launcher, a normal start launcher, and the complete Phase 1 dry run.
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
    page.get_by_role("button", name="Import curated profile").click()
    expect(page.get_by_text("These sources disagree")).to_be_visible()
    resolve_all_fixture_conflicts(page)
    expect(page.get_by_text("Your verified profile is ready for Phase 2")).to_be_visible()
```

- [ ] **Step 2: Run launcher and acceptance tests and verify failure**

Run: `uv run pytest tests/integration/test_launcher.py tests/e2e/test_phase_1_acceptance.py -v`

Expected: failure because the launcher, scripts, and complete dry run do not exist.

- [ ] **Step 3: Implement one-time setup and normal start**

`launcher.py` must pre-bind an available socket on `127.0.0.1`, create a fresh `LaunchSession`, start Uvicorn with the pre-bound socket, and open the single-use launch URL in the default browser. It must print only plain-language start, stop, and error messages; it must not print the launch token after opening the browser.

`Setup Job Search Cockpit.command` changes to its own directory, verifies Python 3.12 and `uv`, runs `uv sync --frozen`, installs Chromium for Playwright-based verification, and prints a clear success message. `Start Job Search Cockpit.command` changes to its own directory and runs `uv run python -m job_search_cockpit.launcher`. Both files must be executable and quote paths containing spaces.

`README.md` must contain non-technical sections: Set up once, Start the cockpit, Stop the cockpit, Where private data stays, Create a safety copy, Restore help, and What Phase 1 does not do. It must state that original sources are never edited and no job search occurs yet.

- [ ] **Step 4: Run the complete quality and acceptance suite**

Run: `uv run ruff check src tests && uv run mypy src && uv run pytest -v`

Expected: lint, type checking, all unit tests, all integration tests, all browser tests, and the Phase 1 dry run pass.

Then run: `git status --short`

Expected: only intentionally ignored local outputs are absent from status; no database, backup, log, token, or Playwright artifact is tracked.

- [ ] **Step 5: Commit launch and acceptance deliverables**

```bash
git add README.md "Setup Job Search Cockpit.command" "Start Job Search Cockpit.command" src/job_search_cockpit/launcher.py tests/integration/test_launcher.py tests/e2e/test_phase_1_acceptance.py
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
- [ ] Import the four real curated sources in preview mode and inspect the reported counts before applying.
- [ ] Confirm product-years, team-count, title, chronology, and metric conflicts appear for review.
- [ ] Confirm no source document timestamp or hash changes after import.
- [ ] Confirm the locked profile matches the approved assessment values exactly.
- [ ] Confirm an unresolved, rejected, or confidential-without-permission claim is not resume-eligible.
- [ ] Confirm the Home screen gives one clear next action in plain language.
- [ ] Review the five screens at narrow, medium, and wide browser sizes.
- [ ] Confirm the Git history contains no database, backup, log, token, or private source copy.
- [ ] Produce the final readiness report and record any remaining user decisions without guessing them.
