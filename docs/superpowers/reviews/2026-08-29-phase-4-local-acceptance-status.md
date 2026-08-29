# Phase IV local acceptance status

## Status

**Complete — awaiting user acceptance** for local implementation and simulated
verification. The remaining browser E2E check is a user-performed manual
acceptance item because this task has no controllable isolated browser runtime.

## Automated evidence

- Unit tests: 128 passed.
- Integration tests: 167 passed (one existing Starlette/httpx deprecation
  warning).
- Ruff and mypy passed.
- Phase II migration has one head: `0017_drive_reserved_file_ids`.
- Recovery checkout was clean and its `HEAD` matched `origin/Dev` at
  `420a813097e66067006ffa56ef5de00c86d3f6a3` when verified.

## Manual browser acceptance

Before approving browser E2E verification, use the cockpit only on localhost
with its normal local launch session. Confirm that an authoritative final
artifact shows **Back up to Google Drive**, a pending backup shows only
**Retry backup**, and callback failures show generic text without any OAuth
codes, account information, Drive identifiers, paths, or resume content.

Do not open the Google consent page, sign in, create a Keychain credential,
create a Drive folder, or upload a resume as part of this check. Those remain
separate real-user approval gates.
