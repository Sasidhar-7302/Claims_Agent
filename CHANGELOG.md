# Changelog

All notable repository-level changes are documented here.

## 2026-02-26

- Added durable SQLite LangGraph checkpoints (`langgraph-checkpoint-sqlite`) for pause/resume across restarts.
- Added outbound delivery integration with idempotent dispatch logging (`gmail_api`, `smtp`, `manual` modes).
- Added Gmail attachment download pipeline and attachment text extraction utilities with optional OCR support.
- Updated extraction flow to use attachment text as additional evidence.
- Fixed policy selection pathing to honor configured policy/index locations (demo vs uploaded policies).
- Expanded UI onboarding/sidebar settings for outbound mode and durable checkpoint visibility.
- Added tests for attachment extraction and outbound idempotency behavior.
- Updated README/ARCHITECTURE/.env docs for production configuration.
- Added free-demo data generation controls and CLI flags for synthetic inbox expansion.
- Added product catalog management (`demo` vs `uploaded`) with schema validation and onboarding wiring.
- Added enterprise onboarding checklist covering database path, mailbox, products, policies, outbound mode, and LLM mode.
- Added `PRODUCTION_ONBOARDING.md` with phase-by-phase rollout instructions.
- Added enterprise IMAP inbox support (Outlook/Exchange Online and other providers) with read-marking, attachment ingest, and onboarding/sidebar controls.
- Added outbound sidebar Gmail-connection flow for teams using Gmail API send mode without Gmail as inbox source.
- Added IMAP parsing unit tests and updated docs (`README`, `.env.example`, `ARCHITECTURE`, onboarding guide).

## 2026-02-25

- Refreshed repository documentation for professional presentation.
- Added `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `SECURITY.md`.
- Added GitHub Actions CI workflow for tests.
- Updated `.gitignore` to exclude generated artifacts and reports.
- Removed legacy static report files; replaced with report generation guidance.
