# Final audit repair report

Date: 2026-09-02

The final audit closes six Phase II regressions:

1. Phase II writes its append-only mapping attempt and recovery witness before it asks
   Phase I to authorize disclosure or release wording.
2. Listings with more than 32 assessable public clauses fail closed instead of silently
   truncating their requirement set.
3. A fresh retry has a fresh attempt ID, nonce, and payload digest while retaining the
   same authority-fenced preflight manifest.
4. Verification readiness now derives only from current, persisted, revalidated
   assessment/mapping evidence. Mandatory mappings must be direct; durable résumé
   readiness also revalidates its ledger fingerprint against the current evidence.
5. The mapping page shows the relevant public listing clause and citation, and each
   requirement exposes only Phase I facts connected by its approved relevance edge.
6. Candidate mapping and verification use an eligible location that is present on the
   specific listing; service verification independently enforces that listing boundary.

Additional regression coverage pins assessment timestamps so the stale-ledger test
actually selects the newly appended assessment.

Verification evidence:

- Focused Phase I/II audit tests: 61 passed.
- Unit suite: 186 passed.
- Integration suite: passed with temporary localhost-socket permission.
- E2E and document suite: 19 passed with local Chromium permission.
- `ruff check .`, `mypy src`, `alembic -c alembic_phase2.ini heads`, and
  `git diff --check`: passed.
