# Job Search Cockpit — Phase 1

Job Search Cockpit is a private, local fact vault for reviewing the career information already stored in Varun's approved source documents. It runs only on `127.0.0.1` on one Mac. Original source files are read but never edited.

## Set up once

Double-click **Setup Job Search Cockpit.command**. It checks for macOS, Python 3.12, and `uv`, installs the project environment, and prepares Chromium for the built-in verification checks. If prerequisites are missing, follow the displayed Homebrew instructions; the script never installs system software silently.

## Start the cockpit

Double-click **Start Job Search Cockpit.command**. A private browser page opens with a fresh, single-use launch link. If the cockpit is already open, a second copy will refuse to use the same vault.

## Stop the cockpit

Return to the Terminal window and press **Control-C**. The server stops accepting requests, closes the database, and releases the vault lock. Closing only the browser tab does not stop the local process.

## Where private data stays

The SQLite vault, logs, recovery history, and safety copies stay under:

`~/Library/Application Support/JobSearchCockpit`

These files are restricted to the current macOS account and excluded from Git. Career facts are not sent to an external service during Phase 1.

## Create a safety copy

The cockpit automatically creates a timestamped, verified safety copy before every mutation that could affect decisions. Copies live in the private `backups` directory beside the vault. Keep the application-data directory in your normal encrypted Mac backup routine.

## Restore help

Do not replace or edit SQLite, manifest, WAL, SHM, or recovery files by hand. If startup reports an integrity, migration, or recovery-history problem, stop the cockpit, preserve the entire application-data directory, and choose a verified backup whose `.sqlite3` file and `.json` manifest remain together. Restore uses checksum, schema, and SQLite integrity checks and preserves the pre-restore vault.

## What Phase 1 does not do

Phase 1 does not search for jobs, scrape job boards, score roles, generate resumes, submit applications, or contact anyone. It imports the four curated sources read-only, surfaces disagreements, records explicit review decisions, protects confidential facts, locks the target search profile, and reports whether the verified vault is ready for Phase 2.

## Phase II-A: safe activation foundation

Phase II-A adds a separate local job-search catalog and a setup-only activation screen. It can use only immutable, approved Phase I readiness and locked-profile snapshots; it never reads Phase I tables directly.

Before Phase II setup can be enabled, the cockpit needs a durable Phase I acceptance receipt and the exact confirmation `ENABLE PHASE II`. The approval is reversible and automatically suspends if the approved Phase I state or either local catalog is restored or changes.

Phase II-A does not approve a provider, contact a job source, fetch a job, release career facts, score or shortlist jobs, create documents, or submit applications.

To verify the local foundation after setup:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -v
```
