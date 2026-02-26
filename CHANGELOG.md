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

## 2026-02-25

- Refreshed repository documentation for professional presentation.
- Added `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `SECURITY.md`.
- Added GitHub Actions CI workflow for tests.
- Updated `.gitignore` to exclude generated artifacts and reports.
- Removed legacy static report files; replaced with report generation guidance.
