# Phase IV private Google Drive backup design

## Status

Approved as written by Varun on 2026-08-28 for implementation planning. The
approved implementation direction is a direct Google Drive REST integration
using the project's existing HTTP client, desktop OAuth with PKCE, the narrow
`drive.file` scope, and macOS Keychain for the refresh token.

This design does not authorize implementation, Google account connection,
OAuth consent, a real upload, a dependency change, or a retention change.
Each remains separately gated.

Varun also confirmed on 2026-08-28 that the Codex Google Drive connector is
connected. That connector connection does not grant the Job Search Cockpit its
own OAuth permission and is not evidence that the cockpit uploaded or verified
a Phase III final pair. Cockpit OAuth and real-upload acceptance therefore
remain subject to the gates below.

## Objective

Phase IV backs up one already-finalised Phase III PDF/DOCX resume pair to one
private Google Drive folder after a visible user action. It adds no resume
generation, provider access, job discovery, browser application assistance,
sharing, submission, scheduling, notification, or background work.

Success means the cockpit can prove that both unchanged final local files were
uploaded to its private Drive folder, while a cancellation, permission loss,
partial upload, timeout, or uncertain response leaves the local pair unchanged
and gives the user one clear manual recovery action.

## User experience

After Phase III finalisation, the local artifact view shows **Back up to
Google Drive**. Backup never begins merely because finalisation succeeded.

On the first request:

1. The cockpit opens Google's official sign-in and permission screen.
2. The user grants the narrow permission shown by Google.
3. The cockpit creates or reuses one private folder named `Job Search Cockpit`.
4. The cockpit uploads only the exact final PDF and DOCX pair.
5. The local artifact view displays the resulting backup state.

The user-visible states are:

- `not_requested`: no Drive backup was requested.
- `sign_in_required`: a visible Google permission flow is required.
- `in_progress`: a user-started upload is currently executing synchronously.
- `backed_up`: both files were uploaded and verified.
- `pending`: Drive was unavailable, one file remains missing, or the outcome
  needs a safe user-started retry.
- `permission_expired`: Google permission was removed, expired, or rejected.

Only the user-visible **Retry backup** action may retry a pending backup. There
is no scheduler, background worker, startup retry, automatic polling loop, or
notification.

## Authorization and least privilege

The integration is a Google desktop application using OAuth 2.0 Authorization
Code with PKCE. It requests only:

`https://www.googleapis.com/auth/drive.file`

It must not request broad Drive, Drive-readonly, Drive-metadata, Gmail, profile,
contacts, or other Google scopes. The `drive.file` scope limits the cockpit to
files it creates or files explicitly made available to it.

The authorization request uses a random one-use state value, a one-use PKCE
verifier, an exact loopback callback, and a short monotonic expiry. A missing,
expired, replayed, wrong-state, wrong-callback, or malformed response is
rejected. The cockpit never receives or stores the user's Google password,
multi-factor code, or browser session.

The refresh token is stored only in macOS Keychain under a dedicated service
name. Access tokens and PKCE material remain in memory only. SQLite,
configuration files, logs, backups, Git, templates, forms, and browser storage
must contain no Google token or authorization code.

Removing Google permission blocks future uploads. It does not delete the local
resume or an existing Drive copy. Drive deletion is not part of Phase IV.

## Trusted input boundary

Phase IV accepts an opaque Phase III final-artifact ID, not a user-supplied
file path, filename, Drive ID, or arbitrary byte stream.

Immediately before authorization, folder access, each upload, verification,
and metadata publication, the backup service calls the existing Phase III
artifact boundary and requires:

- a current, revalidated final-artifact record;
- the exact PDF and DOCX paths below the approved final-resume directory;
- matching byte lengths and SHA-256 fingerprints;
- the same job, revision, document-attempt, projection, and canonical-content
  bindings recorded at finalisation; and
- both files to remain readable and unchanged.

Any failed revalidation stops before the next external action. Phase IV never
reads an existing or generic resume and never accepts a draft, revision,
headshot, provider payload, source document, or Phase I fact directly.

## Drive folder and file rules

The cockpit creates one folder named `Job Search Cockpit` with the Google Drive
folder MIME type. The folder and every uploaded file are private by default.
The cockpit creates no permission, public link, collaborator, share, shortcut,
or external message.

The PDF and DOCX retain their approved Phase III filenames and native MIME
types. The cockpit does not convert them to Google Docs. One final pair is
retained per job; a later different job or role receives its own already-safe
Phase III filenames. Phase IV never overwrites an existing pair silently.

The cockpit records stable app-created Drive IDs and verifies the remote result
against the exact local file metadata. It does not search or list unrelated
Drive content. A stored folder or file ID is usable only when it belongs to the
same local artifact and the current app authorization.

## Partial, interrupted, and uncertain uploads

Google Drive does not provide a transaction spanning two files, so Phase IV
models each file result separately while presenting one pair-level status.

- If neither upload succeeds, the pair is `pending`.
- If one file succeeds, its immutable success metadata is retained and the
  pair remains `pending`.
- A retry uploads only the missing file after revalidating the complete local
  pair and checking the recorded Drive result.
- If a timeout or disconnect makes an upload outcome uncertain, the cockpit
  checks the preassigned app-created Drive ID before attempting another upload.
- A confirmed existing matching file is reused; a conflict or mismatch fails
  closed and creates no replacement or overwrite.
- No failure removes, changes, or renames either local file.

Errors shown to the user are bounded explanations such as sign-in required,
permission expired, Drive unavailable, local files changed, partial backup, or
verification failed. Raw Google responses, tokens, URLs containing codes,
resume text, local paths, and exception strings do not enter logs or audit
records.

## Local records and retention

Phase IV adds append-only metadata to the isolated Phase II catalog:

- one backup operation bound to the exact Phase III final-artifact ID;
- one event per user request, authorization outcome, folder outcome, file
  outcome, verification outcome, pending state, and completed state;
- the app-created folder ID and PDF/DOCX file IDs;
- local and remote byte lengths and file fingerprints;
- bounded status and reason codes; and
- Phase I, Phase II, Phase III, activation, restore, and policy fences needed
  to prove which final artifact was backed up.

The records contain no resume body, career wording, Google password, token,
authorization code, cookie, browser session, raw response, sharing metadata, or
unrestricted error text. Update and delete operations are rejected; corrections
or later outcomes append new events.

The Drive backup follows the approved Phase III final-pair retention boundary:
one final pair per job plus immutable audit metadata. Phase IV does not delete
local or Drive files, introduce a new purge period, retain drafts, or change
backup rotation. Any different retention or deletion behavior requires a new
explicit design and approval.

## Components and interfaces

Phase IV introduces small local boundaries behind the existing Phase II
runtime:

- `DriveAuthorizationService`: starts and completes one visible PKCE consent
  flow and obtains short-lived access through Keychain-backed permission.
- `DriveCredentialStore`: stores and removes only the refresh token through
  macOS Keychain; it has no SQLite implementation.
- `DriveApiClient`: calls only the approved Google OAuth and Drive API hosts,
  creates the app folder, uploads the two files, and reads only app-created
  result metadata.
- `FinalResumeDriveBackupService`: revalidates the Phase III artifact,
  coordinates the user-started pair upload, and appends local backup events.
- `DriveBackupStore`: writes and reads append-only backup metadata through the
  existing Phase II mutation coordinator.

The authenticated local UI adds only:

- a POST action to request backup for an exact final-artifact ID;
- a one-use GET callback for Google's authorization response;
- a POST action to retry an exact pending backup; and
- a read-only status on the existing artifact view.

The callback is not a general unauthenticated route. It accepts only the
unexpired one-use state created by the authenticated local session and reveals
no artifact or account data in its response.

## Dependencies and implementation direction

Phase IV uses Python 3.12, the existing `httpx` runtime dependency, the standard
library `secrets`, `hashlib`, and `base64` modules for PKCE and fingerprints,
the macOS `security` command for Keychain access, SQLAlchemy/Alembic for
metadata, and the existing FastAPI local session protections.

No new Python package is approved by this design. If official API behavior
cannot be implemented safely with these existing facilities, implementation
stops and requests a separate dependency decision rather than substituting a
package silently.

Authoritative implementation references are:

- Google Drive scopes:
  https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Google OAuth for desktop applications:
  https://developers.google.com/identity/protocols/oauth2/native-app
- Google OAuth security guidance:
  https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- Drive folder creation:
  https://developers.google.com/workspace/drive/api/guides/folder
- Drive upload behavior:
  https://developers.google.com/workspace/drive/api/guides/manage-uploads

## Testing strategy

Automated tests use an injected local fake for OAuth and Drive API responses.
They never connect to Google, inspect a real account, or upload a real file.

Tests must prove:

- no backup starts at finalisation or without a visible user request;
- only a revalidated Phase III final-artifact ID can reach Drive;
- typed paths, drafts, revisions, generic resumes, changed files, and wrong
  fingerprints are rejected;
- OAuth state, PKCE, callback, expiry, replay, cancellation, permission loss,
  and token-storage rules fail closed;
- the requested scope is exactly `drive.file`;
- only approved Google hosts are contacted;
- the dedicated folder is created or reused without listing unrelated files;
- both final files are uploaded with exact names and MIME types;
- complete, partial, failed, interrupted, and uncertain outcomes are recorded
  correctly without duplicates or overwrites;
- retry occurs only after the user presses **Retry backup**;
- no sharing, public link, collaborator, automatic retry, scheduler, browser
  application assistance, or submission path exists;
- SQLite and logs contain no token, authorization code, resume text, raw
  response, credential, cookie, or unrestricted error; and
- activation, restore, artifact, or file drift invalidates unsafe work.

Route tests retain the existing local authentication, Host, Origin, CSRF,
cache, CSP, framing, and escaping protections. A route inventory rejects
unapproved upload targets, sharing, deletion, scheduling, application, or
submission actions.

## Real-user acceptance gate

Implementation completion does not authorize a real Google connection.
Real-user acceptance requires, in order:

1. The complete local test, lint, type, migration, security, and route suite
   passes with no Google access.
2. The user separately approves one visible Google OAuth connection in that
   execution turn after seeing the exact `drive.file` scope.
3. The source artifact is an already-accepted real Phase III final pair for a
   verified job. Phase IV does not create or finalise that resume.
4. The user presses **Back up to Google Drive** for that exact pair.
5. The cockpit verifies both app-created Drive files and reports their safe
   names, file IDs, fingerprints, and completion time.
6. The user confirms that the private `Job Search Cockpit` folder contains the
   correct PDF/DOCX pair and no unexpected file or sharing state.

The real check performs no application action, upload outside the dedicated
folder, sharing, public linking, notification, scheduling, or background retry.

## Approval boundaries

### Always

- Revalidate the exact Phase III final pair before every external action.
- Require a visible authenticated user action for initial backup and retry.
- Use only `drive.file`, PKCE, Keychain, app-created Drive IDs, append-only
  metadata, and bounded safe errors.
- Preserve local files unchanged on every Drive outcome.

### Ask first

- Beginning implementation from the written plan.
- Adding or changing a dependency.
- Connecting a real Google account or opening the real OAuth consent flow.
- Uploading a real final pair.
- Changing OAuth scopes, Google hosts, folder name, output filenames, retry
  behavior, metadata fields, or retention.
- Adding deletion, overwrite, replacement, multiple-account, migration,
  reconciliation, or account-switching behavior.

### Never

- Request broad Drive access or inspect unrelated Drive content.
- Store passwords, multi-factor codes, tokens, authorization codes, cookies,
  browser sessions, resume bodies, or raw Google responses in SQLite or logs.
- Upload drafts, revisions, rejected resumes, source documents, headshots, or
  arbitrary user-selected paths.
- Create shares, public links, collaborators, messages, or Google Docs
  conversions.
- Retry in the background, schedule work, submit an application, bypass an
  access restriction, or combine Phase IV with browser application assistance.

## Acceptance criteria

1. Backup is available only for one current, unchanged Phase III final PDF/DOCX
   pair and only after a visible authenticated request.
2. The application requests exactly `drive.file` through desktop OAuth with
   PKCE and stores the refresh token only in macOS Keychain.
3. The cockpit creates or reuses only its private `Job Search Cockpit` folder
   and accesses only app-created folder/file IDs.
4. It uploads the exact final filenames without conversion, sharing, public
   links, silent overwrite, or duplicate creation.
5. Complete, partial, failed, interrupted, uncertain, cancelled, expired, and
   revoked outcomes preserve the local pair and produce a bounded status.
6. Retry occurs only after the visible **Retry backup** action and uploads only
   a missing file after safe remote reconciliation.
7. Local metadata is append-only, contains no document body or credential, and
   remains fenced to the exact artifact and current authority generations.
8. Automated acceptance performs no Google access and proves the complete
   security, privacy, failure, duplicate, route, and no-background boundaries.
9. Real-user acceptance remains separately gated by a real verified job, an
   already-finalised accepted pair, explicit OAuth approval, a visible backup
   action, and user confirmation of the private Drive result.
10. Phase IV adds no scheduling, notifications, application-browser support,
    form filling, submission, Drive deletion, sharing, or Phase V behavior.

## Alternatives considered

Google's Python client libraries were not selected because they add several
runtime dependencies without changing the user-visible permission or safety
model. Manual browser upload was not selected because it cannot provide a
reliable in-cockpit backup result and is easier to forget. Both alternatives
require a new design decision if reconsidered.
