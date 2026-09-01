# Job Search Cockpit

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

## Phase I: establish approved facts

Phase I imports the four curated sources read-only, surfaces disagreements, records explicit review decisions, protects confidential facts, locks the target search profile, and reports whether the verified vault is ready for Phase II. It does not contact anyone or submit applications.

## Phase II–IV: local assisted workflow

Phase II uses a separate local job-search catalog and can use only immutable, approved Phase I snapshots through the contract boundary; it never reads Phase I tables directly.

Before discovery can be enabled, the cockpit needs a durable Phase I acceptance receipt and the exact confirmation `ENABLE PHASE II`. The approval is reversible and automatically suspends if the approved Phase I state or either local catalog is restored or changes.

1. On **Local review**, confirm provider configuration is available locally, then choose **Run manual discovery**. The button accepts no search parameters: the configured providers, role/location query, and safety limits are owned by the local service. A micro-run is capped at five listings and USD 0.10 for each Apify provider request. Missing or partial provider credentials leave discovery unavailable; do not place real credentials in Git.
2. Review a public candidate. Open the public source manually, then choose **Map approved evidence**. The temporary Phase I wording view is one-use and expires; map every visible requirement to approved evidence or explicitly record no approved evidence.
3. Choose **Verify selected candidate** only after manually checking the listing and eligible location. Type `VERIFY JOB FOR PHASE II PREPARATION`; this creates a job-specific authorization that expires after 15 minutes.
4. Choose **Prepare tailored résumé**, review the canonical local content, provide a local professional headshot, and type the displayed finalisation confirmation. The cockpit produces a local DOCX/PDF pair and displays hashes and the final file paths.
5. **Back up to Google Drive** is optional and always explicit. It requires your local Google consent. If consent is unavailable, denied, expired, or a remote verification is uncertain, the UI records a safe status and offers only the applicable manual retry. Google authorization and Drive actions are real manual actions outside the deterministic local test workflow.

Application submission, browser automation, uploading to job sites, and contacting employers remain unavailable. Complete those actions manually outside the cockpit.

To verify the local workflow:

```bash
uv run pytest tests/e2e/test_phase1_to_phase4_working_model.py -q
uv run ruff check .
uv run mypy src
```
