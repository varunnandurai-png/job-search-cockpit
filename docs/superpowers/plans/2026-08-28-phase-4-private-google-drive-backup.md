# Phase IV Private Google Drive Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Varun deliberately back up one unchanged, already-finalised
Phase III PDF/DOCX résumé pair to one private app-created Google Drive folder,
with narrow permission, safe manual recovery, and no unrelated Drive access.

**Architecture:** A new `FinalResumeDriveBackupService` accepts only an opaque
Phase III final-artifact ID and reuses Phase III's file and authority
revalidation before every external step. Small OAuth and Drive REST adapters
sit behind injected protocols, while an append-only Phase II store records
only bounded operation metadata and remote IDs. OAuth state, PKCE material,
access tokens, and resumable-upload URLs stay in memory; the refresh token is
kept only in macOS Keychain.

**Tech Stack:** Python 3.12, existing `httpx`, FastAPI/Jinja2, SQLAlchemy 2,
Alembic, SQLite, standard-library `secrets`/`hashlib`/`base64`/`subprocess`,
and the macOS `/usr/bin/security` command. No new Python package.

## Global Constraints

- Phase IV receives only an opaque `phase2_final_resume_artifacts.id`; it never
  accepts a typed path, filename, arbitrary bytes, draft, revision, generic
  résumé, source document, headshot, provider payload, or Phase I fact.
- Revalidate the complete Phase III artifact, its exact PDF/DOCX paths,
  lengths, SHA-256 values, canonical content, job/revision/attempt bindings,
  and current Phase I/II authority immediately before every external action
  and immediately before publishing local backup metadata.
- Request exactly `https://www.googleapis.com/auth/drive.file`; never request a
  broader Drive scope or another Google scope.
- Use OAuth 2.0 Authorization Code with S256 PKCE, a one-use random state, the
  active `127.0.0.1` loopback port, and a five-minute monotonic expiry.
- The Google OAuth client ID is configuration, not a secret. Never accept or
  use a client secret in this installed-app flow.
- Store the refresh token only in macOS Keychain under service
  `com.job-search-cockpit.google-drive` and account `drive.file`. Keep access
  tokens, authorization codes, PKCE values, OAuth state, and upload-session
  URLs in memory only.
- Contact only `accounts.google.com`, `oauth2.googleapis.com`, and
  `www.googleapis.com` over HTTPS. The OAuth loopback redirect is the sole HTTP
  exception and must use `127.0.0.1` with the current cockpit port.
- Create or reuse only one app-created folder named `Job Search Cockpit`.
  Create no permission, share, public link, collaborator, shortcut, message,
  conversion, overwrite, replacement, deletion, or unrelated Drive listing.
- Preserve the exact approved PDF/DOCX filenames and MIME types. Verify remote
  ID, name, parent, MIME type, byte length, `trashed=false`, `shared=false`,
  `isAppAuthorized=true`, and SHA-256 before recording success.
- Use pre-generated Drive IDs and resumable uploads. Treat third-party response
  bodies and the returned upload-session URL as untrusted; validate their exact
  shape and host before use.
- Record one immutable backup operation per final artifact and append-only
  bounded events. Store no résumé body, local absolute path, credential,
  authorization code, raw Google body, raw URL, or unrestricted exception.
- Initial backup and every retry require a visible authenticated user action.
  Add no scheduler, worker, startup retry, polling loop, notification, or
  background task.
- Automated tests use synthetic artifacts and injected fakes only. They never
  connect to Google, inspect a real Drive, read a real résumé, or upload a real
  file.
- A Codex Google Drive connector connection is separate from cockpit OAuth and
  cannot be reused as the cockpit's credential.
- Commit and push every accepted task as one logical increment on `Dev`; after
  each push compare `git rev-parse HEAD` with `git ls-remote origin
  refs/heads/Dev`.
- Stop and request a new decision before changing dependencies, permission
  scope, Google hosts, folder/name rules, retry behavior, metadata fields,
  retention, deletion, overwrite, multiple-account behavior, or real-user
  access.

## Reconciliation Findings and Execution Gates

1. Local `Dev` and `origin/Dev` start this plan at
   `47f0e93c7475eaa06a8dcb99cc716029c05794bc`; the worktree was clean before
   the written-approval record and this plan.
2. The verified baseline is Ruff clean, mypy clean, and `268 passed` with one
   existing Starlette/httpx deprecation warning.
3. Main Alembic head is `0002_phase1_contract`; Phase II head is
   `0015_match_assessment_band_inputs`.
4. Phase III already verifies current authority, canonical content, exact
   paths, byte lengths, and SHA-256 values in
   `LocalResumeFinalisationService.artifacts_for`, but its public artifact view
   does not yet expose the opaque final-artifact row ID.
5. The current FastAPI middleware requires a `SameSite=Strict` launch cookie
   for every non-launch route. Google returning from another site will not
   reliably send that cookie. The callback must therefore be the single exact
   cookie exception and must reveal nothing unless a live one-use OAuth state
   created by the authenticated session is consumed.
6. `Settings` has no Google OAuth client-ID configuration. Automated work can
   use an injected test value; a real cockpit connection later requires a
   separately approved Google Cloud desktop OAuth client and Drive API enablement.
7. The Codex Google Drive connector is connected by user confirmation. No
   repository code, database row, Drive file ID, or verified PDF/DOCX result
   currently exists for a cockpit upload, so real cockpit upload acceptance is
   not complete.
8. Explicit approval is required before Task 1 because implementation changes
   an external-service and callback authorization boundary. Real OAuth and real
   upload remain separately gated even after automated implementation passes.

## Official Implementation Sources

- Installed-app OAuth, loopback redirects, S256 PKCE, state, and token exchange:
  https://developers.google.com/identity/protocols/oauth2/native-app
- OAuth token storage and revocation guidance:
  https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- Exact `drive.file` scope and its per-file access model:
  https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Folder creation with the Drive folder MIME type:
  https://developers.google.com/workspace/drive/api/guides/folder
- Pre-generated IDs:
  https://developers.google.com/workspace/drive/api/reference/rest/v3/files/generateIds
- Resumable upload initiation, single-request content upload, and interruption
  handling:
  https://developers.google.com/workspace/drive/api/guides/manage-uploads
- File create/get contracts and file metadata including SHA-256:
  https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create
  and https://developers.google.com/workspace/drive/api/reference/rest/v3/files

---

## File Structure

| File | Responsibility |
|---|---|
| `src/job_search_cockpit/phase2/finalisation.py` | Expose and revalidate an opaque Phase III final-artifact ID without accepting paths. |
| `src/job_search_cockpit/phase2/models.py` | Immutable Drive backup operation and event metadata. |
| `alembic_phase2/versions/0016_private_drive_backup.py` | Phase IV tables, constraints, indexes, and append-only triggers. |
| `src/job_search_cockpit/phase2/drive_backup.py` | Backup types, append-only store, derived status, and orchestration. |
| `src/job_search_cockpit/phase2/drive_auth.py` | PKCE/state lifecycle, token exchange/refresh, and Keychain adapter. |
| `src/job_search_cockpit/phase2/drive_api.py` | Exact-host Drive v3 ID, folder, resumable-upload, and metadata calls. |
| `src/job_search_cockpit/config.py` | Optional Google desktop OAuth client-ID configuration only. |
| `src/job_search_cockpit/launcher.py` | Load the optional public client ID at process startup without loading credentials. |
| `src/job_search_cockpit/phase2/runtime.py` | Construct injected Phase IV production boundaries; disabled safely without a client ID. |
| `src/job_search_cockpit/web/app.py` | Permit only the exact one-use OAuth callback through the strict-cookie gate. |
| `src/job_search_cockpit/web/routes/phase2.py` | Authenticated backup/retry POSTs and bounded OAuth callback GET. |
| `src/job_search_cockpit/web/templates/phase2_local_review.html` | Visible backup/retry actions and bounded status. |
| `src/job_search_cockpit/web/templates/drive_oauth_result.html` | Generic callback result with no artifact/account detail. |
| `tests/support/phase4.py` | Synthetic final pair, clocks, Keychain runner, OAuth transport, and Drive fake. |
| `tests/unit/test_drive_auth.py` | PKCE, state, scope, token validation, expiry/replay, and Keychain secrecy. |
| `tests/unit/test_drive_api.py` | Exact hosts, request shapes, response validation, IDs, folders, uploads, and reconciliation. |
| `tests/unit/test_drive_backup.py` | Artifact boundary, sequencing, partial results, manual retry, and derived status. |
| `tests/integration/test_phase4_database.py` | Migration head, constraints, append-only behavior, and prohibited fields. |
| `tests/integration/test_phase4_runtime.py` | Real SQLite plus synthetic Phase III/OAuth/Drive integration. |
| `tests/integration/test_phase4_routes.py` | Cookie/CSRF/origin/callback/UI/route-inventory security. |

## Task 1: Expose the Opaque Phase III Final-Artifact Boundary

**Files:**
- Modify: `src/job_search_cockpit/phase2/finalisation.py`
- Modify: `tests/integration/test_phase3_finalisation_runtime.py`
- Modify: `tests/integration/test_phase3_routes.py`

**Interfaces:**
- Consumes: existing `Phase2FinalResumeArtifact` rows and the complete
  `artifacts_for(attempt_id)` validation chain.
- Produces: `FinalResumeArtifact.artifact_id: str` and
  `FinalResumeArtifact.authority: FinalResumeAuthorityBinding`, plus
  `LocalResumeFinalisationService.artifact_by_id(artifact_id: str) -> FinalResumeArtifact`.

- [ ] **Step 1: Write the failing opaque-ID tests**

```python
def test_final_artifact_can_be_reloaded_only_by_its_opaque_row_id(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(finalise_command(review, runtime.headshot_path))
        assert artifact.artifact_id
        assert runtime.service.artifact_by_id(artifact.artifact_id) == artifact
        with pytest.raises(FinalisationError, match="unavailable"):
            runtime.service.artifact_by_id(str(artifact.docx_path))
    finally:
        runtime.close()


def test_artifact_by_id_rechecks_both_files_and_current_authority(tmp_path: Path) -> None:
    runtime, artifact = finalised_synthetic_artifact(tmp_path)
    artifact.pdf_path.write_bytes(b"changed")
    with pytest.raises(FinalisationError, match="failed verification"):
        runtime.service.artifact_by_id(artifact.artifact_id)
```

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run: `uv run pytest tests/integration/test_phase3_finalisation_runtime.py -k 'opaque_row_id or artifact_by_id' -q`

Expected: FAIL because `artifact_id` and `artifact_by_id` do not exist.

- [ ] **Step 3: Add the minimal boundary**

Add this frozen binding type and attach it to `FinalResumeArtifact` together
with `artifact_id: str`:

```python
@dataclass(frozen=True, slots=True)
class FinalResumeAuthorityBinding:
    requirement_ledger_fingerprint: str
    authorization_id: str
    authorization_nonce: str
    authorization_expires_at: datetime
    phase1_profile_fingerprint: str
    phase1_profile_generation: int
    phase1_readiness_fingerprint: str
    phase1_readiness_generation: int
    phase1_authority_fingerprint: str
    phase1_authority_generation: int
    phase1_restore_generation: int
    phase2_activation_generation: int
    phase2_restore_generation: int
```

Populate it only from the already-verified immutable Phase III attempt. Add
`artifact_by_id(artifact_id)` which loads only
`Phase2FinalResumeArtifact.id`, rejects blank/overlong IDs, then passes the
row through the same attempt, authorization, projection, canonical-content,
path-containment, size, SHA-256, DOCX-text, and PDF-text checks used by
`artifacts_for`. Extract one private `_verified_artifact(row)` helper so the two
public lookups cannot drift. Do not add a path-based lookup.

- [ ] **Step 4: Update the existing synthetic route artifact**

Set `artifact_id="final-artifact-1"` and a complete synthetic authority binding
in the route fake. Do not render this ID as a typed input; Phase IV will place
it only in its fixed form action.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/integration/test_phase3_finalisation_runtime.py tests/integration/test_phase3_routes.py -q
uv run ruff check src/job_search_cockpit/phase2/finalisation.py tests/integration/test_phase3_finalisation_runtime.py tests/integration/test_phase3_routes.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: expose verified final artifact identifier`

## Task 2: Add Immutable Phase IV Metadata

**Files:**
- Modify: `src/job_search_cockpit/phase2/models.py`
- Create: `alembic_phase2/versions/0016_private_drive_backup.py`
- Create: `tests/integration/test_phase4_database.py`

**Interfaces:**
- Consumes: Phase II migration head `0015_match_assessment_band_inputs` and
  `phase2_final_resume_artifacts.id`.
- Produces: `Phase2DriveBackupOperation` and `Phase2DriveBackupEvent`.

- [ ] **Step 1: Write the failing schema tests**

```python
TABLES = {"phase2_drive_backup_operations", "phase2_drive_backup_events"}
PROHIBITED = {
    "body", "wording", "absolute_path", "token", "authorization_code",
    "cookie", "password", "secret", "raw_response", "session_url",
}


def test_phase4_schema_is_append_only_metadata_only(phase2_settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    with sqlite3.connect(phase2_settings.database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0016_private_drive_backup",
        )
        for table in TABLES:
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns.intersection(PROHIBITED)
            triggers = trigger_names(connection, table)
            assert {f"prevent_{table}_update", f"prevent_{table}_delete"} <= triggers
```

Also assert `final_artifact_id` and `job_id` are independently unique, event
`operation_id` is indexed, UPDATE and DELETE fail with `append-only`, and
reason/ID/name/fingerprint columns have bounded lengths.

- [ ] **Step 2: Run the test and confirm failure**

Run: `uv run pytest tests/integration/test_phase4_database.py -q`

Expected: FAIL because migration `0016_private_drive_backup` does not exist.

- [ ] **Step 3: Add the operation table**

`phase2_drive_backup_operations` stores exactly: `id`, unique foreign key
`final_artifact_id`, `attempt_id`, independently unique `job_id`, `job_revision_id`,
`projection_fingerprint`, `content_fingerprint`, safe DOCX/PDF filenames,
their SHA-256 values and byte lengths, requirement-ledger fingerprint,
authorization ID/nonce/expiry, the Phase I profile/readiness/authority
fingerprints and generations, Phase I restore generation, Phase II activation
and restore generations, and `created_at`.

- [ ] **Step 4: Add the event table**

`phase2_drive_backup_events` stores: `id`, `operation_id`, `kind`, optional
bounded `reason_code`, optional `file_kind` constrained to `docx`/`pdf`,
optional `folder_id`, `file_id`, `remote_name`, `remote_mime_type`,
`remote_sha256`, `remote_byte_length`, and `created_at`.

Constrain `kind` to:

```python
DRIVE_EVENT_KINDS = (
    "requested", "authorization_required", "authorization_granted",
    "authorization_denied", "ids_reserved", "folder_verified",
    "file_verified", "pending", "permission_expired", "completed",
)
```

Create UPDATE/DELETE rejection triggers for both tables. Downgrade is
intentionally irreversible, matching the existing audit tables.

- [ ] **Step 5: Verify migration and constraints**

```bash
uv run pytest tests/integration/test_phase4_database.py tests/integration/test_phase2_database.py tests/integration/test_phase3_database.py -q
uv run alembic -c alembic_phase2.ini heads
uv run ruff check src/job_search_cockpit/phase2/models.py alembic_phase2/versions/0016_private_drive_backup.py tests/integration/test_phase4_database.py
uv run mypy src
git diff --check
```

Expected: exactly one Phase II head, `0016_private_drive_backup`.

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: add immutable Drive backup metadata`

## Task 3: Define Backup Types, Store, and Derived Status

**Files:**
- Create: `src/job_search_cockpit/phase2/drive_backup.py`
- Create: `tests/unit/test_drive_backup.py`
- Create: `tests/support/phase4.py`

**Interfaces:**
- Consumes: Task 1 `FinalResumeArtifact`, Task 2 models, and
  `Phase2MutationCoordinator`.
- Produces: `DriveBackupStore`, `DriveBackupView`, `DriveBackupOperation`,
  `DriveBackupEvent`, and `DriveBackupStatus`.

- [ ] **Step 1: Write failing store/status tests**

```python
def test_store_creates_one_operation_for_one_verified_artifact(phase4_runtime) -> None:
    artifact = phase4_runtime.final_artifact
    first = phase4_runtime.store.create_operation(artifact)
    second = phase4_runtime.store.create_operation(artifact)
    assert second.id == first.id
    assert phase4_runtime.store.view_for_artifact(artifact.artifact_id).status == "not_requested"


@pytest.mark.parametrize(
    ("events", "active", "expected"),
    [
        (("requested", "authorization_required"), False, "sign_in_required"),
        (("requested",), True, "in_progress"),
        (("requested", "pending"), False, "pending"),
        (("requested", "authorization_denied"), False, "permission_expired"),
        (("requested", "permission_expired"), False, "permission_expired"),
        (("requested", "completed"), False, "backed_up"),
    ],
)
def test_status_is_derived_from_append_only_events(events, active, expected) -> None:
    assert derive_drive_backup_status(events, active=active) == expected
```

Also test event order, bounded values, wrong operation/file kind rejection,
one `file_verified` result per Drive file ID, and that no event contains a
path, token, raw response, or exception text.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_drive_backup.py -q`

Expected: FAIL because the Phase IV types/store do not exist.

- [ ] **Step 3: Define exact public types**

```python
DriveBackupStatus = Literal[
    "not_requested", "sign_in_required", "in_progress",
    "backed_up", "pending", "permission_expired",
]

@dataclass(frozen=True, slots=True)
class DriveBackupView:
    operation_id: str | None
    final_artifact_id: str
    status: DriveBackupStatus
    reason_code: str
    folder_id: str | None
    docx_file_id: str | None
    pdf_file_id: str | None
    docx_name: str | None
    docx_sha256: str | None
    pdf_name: str | None
    pdf_sha256: str | None
    completed_at: datetime | None

@dataclass(frozen=True, slots=True)
class ReservedDriveIds:
    folder_id: str
    docx_file_id: str
    pdf_file_id: str
```

Keep OAuth tokens and remote response objects out of these dataclasses so their
`repr` cannot disclose credentials.

- [ ] **Step 4: Implement the append-only store and status fold**

`create_operation` must be idempotent only for the same exact immutable local
bindings; a collision with different bindings fails closed. `append_event`
accepts enumerated bounded fields only. `view_for_artifact` folds events in
creation order, treats an in-memory active-operation set as `in_progress`, and
treats an abandoned `requested` operation as `pending` rather than retrying it.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/unit/test_drive_backup.py tests/integration/test_phase4_database.py -q
uv run ruff check src/job_search_cockpit/phase2/drive_backup.py tests/unit/test_drive_backup.py tests/support/phase4.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: derive append-only Drive backup status`

## Task 4: Implement One-Use OAuth PKCE and Keychain Storage

**Files:**
- Create: `src/job_search_cockpit/phase2/drive_auth.py`
- Create: `tests/unit/test_drive_auth.py`
- Modify: `tests/support/phase4.py`

**Interfaces:**
- Consumes: configured desktop OAuth client ID, active loopback redirect URI,
  injected `httpx.Client`, monotonic clock, Keychain command runner, and a
  caller-supplied artifact-revalidation callback before every token POST.
- Produces: `DriveAuthorizationService.begin`, `complete`, and
  `access_token`; `MacOSKeychainCredentialStore`.

- [ ] **Step 1: Write failing PKCE and authorization tests**

```python
def test_begin_uses_exact_scope_s256_state_and_loopback() -> None:
    request = service.begin(
        operation_id="operation-1",
        session_id="launch-session-1",
        redirect_uri="http://127.0.0.1:8765/phase-2/drive-backups/oauth/callback",
    )
    query = parse_qs(urlsplit(request.authorization_url).query)
    assert urlsplit(request.authorization_url)._replace(query="").geturl() == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 43


def test_callback_state_is_one_use_short_lived_and_session_bound() -> None:
    started = service.begin("operation-1", "session-1", LOOPBACK_URI)
    service.complete(started.state, "code-1", "session-1", revalidate_artifact)
    with pytest.raises(DriveAuthorizationError, match="unavailable"):
        service.complete(started.state, "code-1", "session-1", revalidate_artifact)
```

Add cases for wrong/blank/expired state, a different launch-session ID,
duplicate code/error parameters, `access_denied`, wrong redirect
host/path/port, wrong returned scope, malformed JSON, oversized values,
timeout, `invalid_grant`, token absence, and sanitised errors.

- [ ] **Step 2: Write failing Keychain secrecy tests**

```python
def test_keychain_write_passes_refresh_token_on_stdin_not_argv(fake_runner) -> None:
    store = MacOSKeychainCredentialStore(fake_runner)
    store.store_refresh_token("refresh-secret")
    command = fake_runner.calls[0]
    assert "refresh-secret" not in command.args
    assert command.input == "refresh-secret\n"
    assert command.args[-1] == "-w"
```

Also prove lookup uses `find-generic-password -w`, deletion names only the exact
service/account, command output is never logged, and command timeout/failure
returns a bounded error.

- [ ] **Step 3: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_drive_auth.py -q`

Expected: FAIL because `drive_auth.py` does not exist.

- [ ] **Step 4: Implement PKCE and state lifecycle**

Define these exact methods:

- `begin(operation_id: str, session_id: str, redirect_uri: str) -> DriveAuthorizationRequest`
- `complete(state: str, code: str, session_id: str, before_request: Callable[[], None]) -> str`
- `access_token(before_request: Callable[[], None]) -> str | None`
- `deny(state: str, reason_code: str, session_id: str) -> str`

`complete` returns only the short-lived access token after storing any refresh
token in Keychain. `deny` consumes the state and returns the bound operation ID.

Use `secrets.token_urlsafe(64)` for the verifier, SHA-256 plus unpadded
URL-safe Base64 for the S256 challenge, `secrets.token_urlsafe(32)` for state,
and `time.monotonic() + 300.0` for expiry. Store pending entries only in a
locked in-memory dictionary, including the initiating launch-session ID. The
callback must supply the current app launch-session ID and it must match. Pop
the entry before token exchange so success or failure cannot replay it. Add
`access_type=offline` and `prompt=consent` to the visible authorization request
so a refresh token is explicitly requested.

Token POSTs go only to `https://oauth2.googleapis.com/token`, with a 10-second
connect and 30-second total timeout. Authorization-code exchange sends
`client_id`, `code`, `code_verifier`, exact `redirect_uri`, and
`grant_type=authorization_code`. Refresh sends `client_id`, `refresh_token`,
and `grant_type=refresh_token`. Invoke the supplied artifact-revalidation
callback immediately before each token POST. Never send a client secret.

- [ ] **Step 5: Implement the Keychain adapter**

Use only absolute `/usr/bin/security`. Add/update with:

```python
(
    "/usr/bin/security", "add-generic-password", "-U",
    "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w",
)
```

Pass the token plus newline through `subprocess.run(command,
input=f"{token}\n", timeout=5, capture_output=True, text=True)`. Read with
`("/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
"-a", KEYCHAIN_ACCOUNT, "-w")`; delete only with the corresponding
`delete-generic-password` command and those same exact service/account values.
Never include stdout/stderr in an exception or log.

- [ ] **Step 6: Verify the increment**

```bash
uv run pytest tests/unit/test_drive_auth.py -q
uv run ruff check src/job_search_cockpit/phase2/drive_auth.py tests/unit/test_drive_auth.py tests/support/phase4.py
uv run mypy src
git diff --check
```

- [ ] **Step 7: Commit, push, and compare refs**

Commit message: `feat: add one-use Drive OAuth permission flow`

## Task 5: Implement the Exact-Host Drive REST Client

**Files:**
- Create: `src/job_search_cockpit/phase2/drive_api.py`
- Create: `tests/unit/test_drive_api.py`
- Modify: `tests/support/phase4.py`

**Interfaces:**
- Consumes: one in-memory access token, app-approved local file metadata, and
  an injected `httpx.Client`, plus a caller-supplied artifact-revalidation
  callback.
- Produces: `generate_ids`, `create_or_verify_folder`, `upload_or_reconcile`,
  and validated `DriveFileMetadata`.

- [ ] **Step 1: Write failing exact-request tests**

```python
def test_generate_ids_uses_exact_drive_endpoint_and_drive_file_scope_transport() -> None:
    assert client.generate_ids("access-secret", 3) == ("folder-1", "docx-1", "pdf-1")
    request = transport.requests[0]
    assert request.url == (
        "https://www.googleapis.com/drive/v3/files/generateIds"
        "?count=3&space=drive&type=files"
    )
    assert request.headers["Authorization"] == "Bearer access-secret"


def test_upload_initiates_resumable_create_with_exact_id_parent_name_and_mime() -> None:
    result = client.upload_or_reconcile(
        access_token="access-secret",
        file_id="docx-1",
        folder_id="folder-1",
        path=synthetic_docx,
        expected_name="Varun_Resume_Acme.docx",
        expected_mime=DOCX_MIME,
        expected_size=synthetic_docx.stat().st_size,
        expected_sha256=sha256(synthetic_docx.read_bytes()).hexdigest(),
    )
    assert result.id == "docx-1"
    assert result.parents == ("folder-1",)
```

Add cases for HTTPS/host validation, disabled redirects, invalid JSON/types,
wrong IDs/names/parents/MIME/sizes/SHA-256, `trashed=true`, `shared=true`,
`isAppAuthorized=false`, unexpected upload-session hosts, 401/403 permission
loss, 404 reconciliation, timeout/5xx uncertainty, and no raw-body errors.
Every test transport request must also assert that the supplied revalidation
callback ran immediately before it.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_drive_api.py -q`

Expected: FAIL because `drive_api.py` does not exist.

- [ ] **Step 3: Add validated response types**

```python
@dataclass(frozen=True, slots=True)
class DriveFileMetadata:
    id: str
    name: str
    mime_type: str
    parents: tuple[str, ...]
    size: int | None
    sha256: str | None
    trashed: bool
    shared: bool
    app_authorized: bool
```

Parse only explicitly requested fields. Bound strings, require exact types,
reject extra parent IDs, and never preserve the raw mapping after validation.

- [ ] **Step 4: Implement exact Drive calls**

- IDs: `GET https://www.googleapis.com/drive/v3/files/generateIds`.
- Folder create: `POST https://www.googleapis.com/drive/v3/files` with
  `{"id": folder_id, "name": "Job Search Cockpit",
  "mimeType": "application/vnd.google-apps.folder"}`.
- Metadata reconcile: `GET
  https://www.googleapis.com/drive/v3/files/{quoted_id}` with only
  `id,name,mimeType,parents,size,sha256Checksum,trashed,shared,isAppAuthorized`.
- Upload initiation: `POST
  https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable` with
  exact ID/name/MIME/parent JSON and `X-Upload-Content-Type` plus
  `X-Upload-Content-Length`.
- Upload content: one `PUT` to the validated HTTPS session URL with exact bytes,
  `Content-Type`, and `Content-Length`.

Use `follow_redirects=False`. Validate a returned `Location` URL before using
it and keep it in a local variable only. On timeout, disconnect, or 5xx, GET
the pre-generated ID once. If it is not a confirmed exact match, return an
uncertain bounded result and require a future visible retry.

Every public Drive method receives `before_request: Callable[[], None]` and
invokes it immediately before each individual HTTP request, including upload
initiation, content PUT, and reconciliation GET. The orchestration layer passes
a callback that reloads the exact Phase III artifact by opaque ID.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/unit/test_drive_api.py -q
uv run ruff check src/job_search_cockpit/phase2/drive_api.py tests/unit/test_drive_api.py tests/support/phase4.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: add fail-closed Drive REST client`

## Task 6: Orchestrate a User-Started Complete Backup

**Files:**
- Modify: `src/job_search_cockpit/phase2/drive_backup.py`
- Modify: `tests/unit/test_drive_backup.py`
- Create: `tests/integration/test_phase4_runtime.py`
- Modify: `tests/support/phase4.py`

**Interfaces:**
- Consumes: Phase III `artifact_by_id`, `DriveAuthorizationService`,
  `DriveApiClient`, `DriveBackupStore`, and an opaque final-artifact ID.
- Produces: `FinalResumeDriveBackupService.request_backup` and a complete
  `backed_up` view when a Keychain refresh token is already valid.

- [ ] **Step 1: Write the failing successful-flow test**

```python
def test_visible_request_revalidates_before_every_external_step_and_backs_up_pair(
    phase4_runtime,
) -> None:
    view = phase4_runtime.service.request_backup(
        final_artifact_id=phase4_runtime.final_artifact.artifact_id,
        session_id="session-1",
        redirect_uri=LOOPBACK_URI,
    )
    assert view.status == "backed_up"
    assert all(
        call.preceded_by_artifact_revalidation
        for call in phase4_runtime.external_calls
    )
    assert phase4_runtime.drive.created_names == [
        "Job Search Cockpit",
        phase4_runtime.final_artifact.docx_path.name,
        phase4_runtime.final_artifact.pdf_path.name,
    ]
    assert phase4_runtime.drive.permission_calls == []
    assert [event.kind for event in phase4_runtime.store.events(view.operation_id)] == [
        "requested", "ids_reserved", "folder_verified",
        "file_verified", "file_verified", "completed",
    ]
```

Also test that a typed path, unknown ID, changed file, changed authority, wrong
fingerprint, or replay reaches zero Drive calls and leaves local files
unchanged.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py -q`

Expected: FAIL because the orchestration service does not exist.

- [ ] **Step 3: Define the service contract**

Define `BackupRequestResult` as a frozen slots dataclass with
`view: DriveBackupView` and `authorization_url: str | None = None`. Define
`FinalResumeDriveBackupService.request_backup(*, final_artifact_id: str,
session_id: str, redirect_uri: str) -> BackupRequestResult` and
`view_for_artifact(final_artifact_id: str) -> DriveBackupView`.

- [ ] **Step 4: Implement the successful sequence**

The method must: revalidate artifact; create/reuse the exact operation; append
`requested`; obtain a refreshed access token through the revalidation hook;
reuse a previously
verified app folder ID or generate exact missing IDs; append `ids_reserved`;
revalidate; create/reconcile folder; append `folder_verified`; revalidate and
upload/reconcile DOCX; append `file_verified`; revalidate and upload/reconcile
PDF; append `file_verified`; revalidate once more; append `completed`. Pass an
opaque-ID artifact reload callback to OAuth and Drive adapters so each
individual external request is immediately preceded by the same Phase III
boundary. Revalidate again after each external result and before appending its
local event.

Use an in-memory set protected by a lock to reject concurrent work for the same
operation. Always remove the active marker in `finally`. Map only enumerated
safe failures to `pending` or `permission_expired`; never persist `str(error)`.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py -q
uv run ruff check src/job_search_cockpit/phase2/drive_backup.py tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py tests/support/phase4.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: back up a verified final resume pair`

## Task 7: Add Consent Continuation, Partial Results, and Manual Retry

**Files:**
- Modify: `src/job_search_cockpit/phase2/drive_backup.py`
- Modify: `tests/unit/test_drive_backup.py`
- Modify: `tests/integration/test_phase4_runtime.py`

**Interfaces:**
- Consumes: Task 6 operation and OAuth state bound to its operation ID.
- Produces: `complete_authorization`, `retry_backup`, safe partial recovery,
  and no automatic retry.

- [ ] **Step 1: Write failing authorization-continuation tests**

```python
def test_missing_refresh_token_returns_one_visible_consent_url(phase4_runtime) -> None:
    result = phase4_runtime.service.request_backup(
        final_artifact_id=phase4_runtime.final_artifact.artifact_id,
        session_id="session-1",
        redirect_uri=LOOPBACK_URI,
    )
    assert result.view.status == "sign_in_required"
    assert result.authorization_url.startswith("https://accounts.google.com/")
    assert phase4_runtime.drive.calls == []


def test_completed_oauth_continues_only_the_bound_operation(phase4_runtime) -> None:
    started = request_without_token(phase4_runtime)
    view = phase4_runtime.service.complete_authorization(
        state=state_from(started.authorization_url),
        code="one-use-code",
        session_id="session-1",
    )
    assert view.status == "backed_up"
    assert phase4_runtime.credentials.load_refresh_token() == "refresh-from-google"
```

- [ ] **Step 2: Write failing partial/manual-retry tests**

```python
def test_partial_backup_records_docx_and_retry_uploads_only_pdf(phase4_runtime) -> None:
    phase4_runtime.drive.fail_pdf_once = True
    first = request_with_token(phase4_runtime)
    assert first.view.status == "pending"
    assert phase4_runtime.drive.uploaded_kinds == ["docx", "pdf"]

    assert phase4_runtime.service.view_for_artifact(
        phase4_runtime.final_artifact.artifact_id
    ).status == "pending"
    assert phase4_runtime.drive.uploaded_kinds == ["docx", "pdf"]

    retried = phase4_runtime.service.retry_backup(first.view.operation_id)
    assert retried.status == "backed_up"
    assert phase4_runtime.drive.uploaded_kinds == ["docx", "pdf", "pdf"]
```

Add cancellation, expired/replayed state, permission revocation, refresh
`invalid_grant`, uncertain folder/file creation, exact-ID reconciliation,
remote mismatch, duplicate user clicks, local drift before retry, and process
restart with no in-memory OAuth/upload session.

- [ ] **Step 3: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py -q`

Expected: focused new cases FAIL.

- [ ] **Step 4: Implement consent continuation and manual retry**

Add these exact service methods:

- `complete_authorization(*, state: str, code: str, session_id: str) -> DriveBackupView`
- `deny_authorization(*, state: str, reason_code: str, session_id: str) -> DriveBackupView`
- `retry_backup(operation_id: str) -> DriveBackupView`

OAuth completion obtains the operation ID only from consumed in-memory state,
stores only the refresh token in Keychain, and continues the same exact
operation. Retry loads the operation by opaque ID, revalidates the complete
local pair first, reconciles every recorded Drive ID, skips each confirmed
matching file, and uploads only a confirmed missing file. A mismatch appends
`pending` with `remote_verification_failed`; it never overwrites or allocates a
replacement ID.

An `invalid_grant`, explicit revocation, or rejected consent deletes only the
exact Keychain refresh-token item and appends `permission_expired`; it deletes
no local or Drive file. Cancellation/rejection consumes its one-use state and
cannot trigger Drive work.

No read method, startup hook, timer, or exception handler may call
`retry_backup`.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py -q
uv run ruff check src/job_search_cockpit/phase2/drive_backup.py tests/unit/test_drive_backup.py tests/integration/test_phase4_runtime.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: recover Drive backups by visible retry`

## Task 8: Wire Disabled-by-Default Production Configuration

**Files:**
- Modify: `src/job_search_cockpit/config.py`
- Modify: `src/job_search_cockpit/launcher.py`
- Modify: `src/job_search_cockpit/phase2/runtime.py`
- Modify: `tests/unit/test_config.py`
- Modify: `tests/integration/test_phase2_resume_runtime.py`
- Modify: `tests/support/web.py`

**Interfaces:**
- Consumes: environment key `JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID` and
  existing `httpx`.
- Produces: `Phase2Runtime.drive_backup_service: FinalResumeDriveBackupService | None`.

- [ ] **Step 1: Write failing configuration/runtime tests**

```python
def test_drive_backup_is_disabled_without_a_client_id(vault_settings) -> None:
    runtime = prepare_test_runtime(vault_settings, google_client_id="")
    assert runtime.drive_backup_service is None


def test_client_id_is_bounded_public_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID",
        "123.apps.googleusercontent.com",
    )
    assert Settings.from_environment(data_dir=tmp_path).google_oauth_client_id == (
        "123.apps.googleusercontent.com"
    )
```

Also reject whitespace/control characters, values over 255 characters,
non-`apps.googleusercontent.com` suffixes, and any client-secret environment
setting. Tests must prove no network or Keychain command runs during startup.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run pytest tests/unit/test_config.py tests/integration/test_phase2_resume_runtime.py -q`

Expected: FAIL because the configuration and runtime field do not exist.

- [ ] **Step 3: Add the minimum configuration**

Add `google_oauth_client_id: str = ""` and a `Settings.from_environment`
constructor that reads only `JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID`. Keep
`Settings.for_tests` explicit so test settings never inherit a developer's
real client ID. Make `launcher.main` call `Settings.from_environment()` before
building the launch plan. Do not add a client-secret field.

- [ ] **Step 4: Construct the production service only when configured**

When the validated client ID is blank, set `drive_backup_service=None` and
show the feature as unavailable. When present, construct one shared
`httpx.Client(follow_redirects=False)`, Keychain store, authorization service,
Drive API client, backup store, and orchestration service. Close the HTTP client
from `Phase2Runtime.close`. Construction performs no external request and no
Keychain read.

- [ ] **Step 5: Verify the increment**

```bash
uv run pytest tests/unit/test_config.py tests/integration/test_phase2_resume_runtime.py tests/integration/test_launcher.py -q
uv run ruff check src/job_search_cockpit/config.py src/job_search_cockpit/launcher.py src/job_search_cockpit/phase2/runtime.py tests/unit/test_config.py tests/integration/test_phase2_resume_runtime.py tests/support/web.py
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `feat: wire optional private Drive backup runtime`

## Task 9: Add the Visible Local UI and One-Use Callback

**Files:**
- Modify: `src/job_search_cockpit/web/app.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_local_review.html`
- Create: `src/job_search_cockpit/web/templates/drive_oauth_result.html`
- Create: `tests/integration/test_phase4_routes.py`
- Modify: `tests/integration/test_phase3_routes.py`

**Interfaces:**
- Consumes: opaque `resume_artifact.artifact_id`, launch session ID, active
  loopback port, CSRF token, and Task 8 optional service.
- Produces: three Phase IV routes and bounded status on the existing artifact
  view.

- [ ] **Step 1: Write failing route-security tests**

```python
def test_backup_and_retry_require_cookie_origin_and_csrf(vault_settings, phase4_service) -> None:
    with configured_test_app(vault_settings, phase4_service) as client:
        assert client.post("/phase-2/drive-backups", data={"final_artifact_id": "a"}).status_code == 401
    with authenticated_phase4_app(vault_settings, phase4_service) as client:
        assert client.client.post(
            "/phase-2/drive-backups",
            data={"final_artifact_id": "artifact-1"},
            headers={"origin": client.origin},
        ).status_code == 403


def test_callback_is_the_only_cookie_exception_and_needs_live_one_use_state(
    vault_settings, phase4_service
) -> None:
    with configured_test_app(vault_settings, phase4_service) as client:
        assert client.get(
            "/phase-2/drive-backups/oauth/callback?state=wrong&code=secret"
        ).status_code == 400
        assert client.get("/phase-2/resume-reviews/attempt-1").status_code == 401
```

Add duplicate/missing/overlong query fields, cancellation, replay, Host
rejection, non-GET callback rejection, callback response no IDs/account/code,
no query values in logs, and unchanged CSP/cache/framing/referrer protections.

- [ ] **Step 2: Write failing user-flow and route-inventory tests**

Assert the final artifact page shows **Back up to Google Drive** only when the
service exists, the form posts the opaque artifact ID and opens the consent
flow in a separate tab, the original tab remains available for refresh, and
pending state shows only **Retry backup**. Exact allowed paths are:

```python
{
    "/phase-2/drive-backups",
    "/phase-2/drive-backups/oauth/callback",
    "/phase-2/drive-backups/{operation_id}/retry",
}
```

Assert no route contains `share`, `permission`, `delete`, `replace`,
`schedule`, `notify`, `apply`, or `submit`.

- [ ] **Step 3: Run tests and confirm failure**

Run: `uv run pytest tests/integration/test_phase4_routes.py tests/integration/test_phase3_routes.py -q`

Expected: FAIL because the Phase IV routes/UI do not exist and the old Phase III
test explicitly denies Drive paths.

- [ ] **Step 4: Add the exact middleware exception**

In `protect_local_session`, keep Host and method validation first. Define the
sole exception as:

```python
oauth_callback = (
    request.method == "GET"
    and request.url.path == "/phase-2/drive-backups/oauth/callback"
)
```

Require the launch cookie for every other route. The callback route itself
must consume a live one-use state before token exchange or Drive work. Do not
weaken `SameSite=Strict`, CSRF, Origin, Host, CSP, or Referrer-Policy.

- [ ] **Step 5: Add the three bounded routes**

- POST `/phase-2/drive-backups`: validate CSRF and a maximum-120-character
  artifact ID, build the exact active-port callback URI, call
  `request_backup`, and 303 to the Google URL only when authorization is needed.
- GET `/phase-2/drive-backups/oauth/callback`: accept one bounded `state` and
  either one bounded `code` or `error`; pass the current app launch-session ID
  to complete/deny through the service; show only a generic
  success/cancelled/pending result.
- POST `/phase-2/drive-backups/{operation_id}/retry`: validate cookie,
  Origin/CSRF, and bounded operation ID; call manual retry; redirect to the
  referring local résumé view only if it is an exact `127.0.0.1` same-origin
  path, otherwise redirect to `/phase-2/review`.

All route errors use fixed plain-language text. Never include an exception,
Google response, token, authorization code, local path, or remote ID.

- [ ] **Step 6: Add the status UI**

After a verified `resume_artifact` exists, ask the service for its read-only
view. Render only the six approved status labels. For `backed_up`, show only
the safe PDF/DOCX names, Drive file IDs, SHA-256 values, and completion time.
The initial form uses a button with `formtarget="_blank"` so the Google consent
tab can return to a generic result page while the local résumé page remains
open. Render no Drive URL or sharing control.

- [ ] **Step 7: Verify the increment**

```bash
uv run pytest tests/integration/test_phase4_routes.py tests/integration/test_phase3_routes.py tests/integration/test_web_security.py -q
uv run ruff check src/job_search_cockpit/web/app.py src/job_search_cockpit/web/routes/phase2.py tests/integration/test_phase4_routes.py tests/integration/test_phase3_routes.py
uv run mypy src
git diff --check
```

- [ ] **Step 8: Commit, push, and compare refs**

Commit message: `feat: add visible private Drive backup controls`

## Task 10: Close Security, Privacy, and No-Background Boundaries

**Files:**
- Modify: `tests/integration/test_phase4_runtime.py`
- Modify: `tests/integration/test_phase4_routes.py`
- Modify: `tests/integration/test_phase4_database.py`
- Modify: `tests/integration/test_startup_state.py`
- Modify: `tests/integration/test_phase2_restore.py`
- Modify: `tests/unit/test_logging.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete Tasks 1–9 behavior.
- Produces: automated Phase IV acceptance with no Google access and operator
  documentation for disabled-by-default configuration and approval gates.

- [ ] **Step 1: Write the failing end-to-end safety inventory**

Add tests proving:

```python
def test_phase4_has_no_automatic_or_expansive_behavior() -> None:
    source = phase4_source_inventory()
    assert "BackgroundTasks" not in source
    assert "add_event_handler" not in source
    assert "files.list" not in source
    assert "/permissions" not in source
    assert "files.delete" not in source
    assert "files.update" not in source
```

Also prove finalisation alone performs no Keychain/HTTP work; startup and
restore perform no retry; Phase I/II authority or restore drift blocks the next
external call; local files remain byte-identical after every failure; SQLite,
recovery ledgers, logs, HTML, and errors contain none of the synthetic token,
authorization code, résumé text, raw response, session URL, cookie, or
absolute local path.

- [ ] **Step 2: Run the acceptance tests and confirm new failures**

Run: `uv run pytest tests/integration/test_phase4_runtime.py tests/integration/test_phase4_routes.py tests/integration/test_phase4_database.py tests/integration/test_startup_state.py tests/integration/test_phase2_restore.py tests/unit/test_logging.py -q`

Expected: any uncovered safety inventory cases FAIL before final hardening.

- [ ] **Step 3: Make only the minimum hardening corrections**

Correct the responsible boundary directly. Do not add rate limiters,
schedulers, general URL fetchers, account pickers, Drive browsers, deletion,
sharing, or new dependencies. If a correction changes approved fields, scope,
retention, or retry semantics, stop for a new decision instead.

- [ ] **Step 4: Document setup without performing it**

README must state, in plain language:

1. Phase IV is disabled when `JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID` is blank.
2. A real user must separately create/approve a Google desktop OAuth client,
   enable Drive API, and see exactly the `drive.file` scope.
3. The Codex Drive connector cannot substitute for cockpit OAuth.
4. Automated tests never access Google.
5. Real OAuth, a real upload, and real-user confirmation remain separately
   approved actions after implementation.

- [ ] **Step 5: Run focused security verification**

```bash
uv run pytest tests/integration/test_phase4_runtime.py tests/integration/test_phase4_routes.py tests/integration/test_phase4_database.py tests/integration/test_startup_state.py tests/integration/test_phase2_restore.py tests/unit/test_logging.py -q
uv run ruff check src tests
uv run mypy src
git diff --check
```

- [ ] **Step 6: Commit, push, and compare refs**

Commit message: `test: close Phase IV Drive safety boundaries`

## Final Automated Verification

- [ ] Run `uv run ruff check src tests`.
- [ ] Run `uv run mypy src`.
- [ ] Run `uv run pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Run `uv run alembic -c alembic.ini heads` and confirm
  `0002_phase1_contract`.
- [ ] Run `uv run alembic -c alembic_phase2.ini heads` and confirm
  `0016_private_drive_backup`.
- [ ] Confirm the worktree is clean.
- [ ] Push the final increment to `origin/Dev`.
- [ ] Confirm `git rev-parse HEAD` equals `git ls-remote origin
  refs/heads/Dev`.
- [ ] Report automated implementation as **Complete — awaiting user
  acceptance**, not as a completed real upload.

## Real-User Acceptance — Separate Future Approval

Do not perform these steps during automated implementation.

1. Ask for approval to create/use one Google Cloud desktop OAuth client and
   enable the Drive API if that external setup is not already verified.
2. Ask for approval to open the real consent page, displaying the exact
   `drive.file` scope first.
3. Require a verified real job and an already-accepted Phase III final pair.
4. Require Varun to press **Back up to Google Drive** for that exact pair.
5. Verify the app-created folder, exact PDF/DOCX IDs, safe names, byte lengths,
   SHA-256 values, private/unshared state, and completion time.
6. Ask Varun to confirm that the private `Job Search Cockpit` folder contains
   the correct pair and nothing unexpected.

Only after all six steps may cockpit real-upload acceptance be marked
**Complete**. GPT-5.6 Sol remains required for any real résumé creation or
finalisation; Phase IV must never create or finalise one.
