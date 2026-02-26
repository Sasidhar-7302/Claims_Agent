# Warranty Claims Agent

[![CI](https://img.shields.io/github/actions/workflow/status/Sasidhar-7302/Claims_Agent/ci.yml?branch=main&label=CI)](https://github.com/Sasidhar-7302/Claims_Agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)](https://streamlit.io/)

AI-assisted warranty claim processing with human-in-the-loop review, policy retrieval (RAG), and auditable outputs.

## Overview

- LangGraph workflow for end-to-end claim handling.
- Streamlit UI for triage, review, decisioning, and dispatch.
- Multi-provider LLM support: Ollama, Groq, Gemini, OpenAI.
- SQLite claim history plus generated review packets, drafts, and labels.
- Deterministic policy checks (warranty window, exclusions, requirements) before LLM reasoning.
- Durable LangGraph checkpoints in SQLite (resume after restart).
- Optional real outbound delivery (Gmail API or SMTP) with idempotent send guards.
- Attachment pipeline with best-effort text extraction and optional OCR for images.

## Quick Start

### Windows one-click
```cmd
run_app.bat
```

### Manual setup
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python index_db.py
streamlit run ui/streamlit_app.py
```

## Demo And Onboarding

On first run, the app opens a Setup Wizard:

- Free Demo (Local): runs on `data/inbox` with deterministic heuristics (no external LLM required).
- Enterprise Setup: configures database path, mailbox connection, product catalog source, policy source, and outbound delivery.

You can switch modes later in the sidebar.

Detailed guide: see `PRODUCTION_ONBOARDING.md`.

## Gmail Connection

1. Create a Google Cloud OAuth client (installed app) and download the client secrets JSON.
2. In the app sidebar, set Inbox Source to Gmail and upload the client secrets JSON.
3. Click Connect Gmail and complete the OAuth flow in your browser.

Tokens and secrets are saved locally under `outbox/` and are ignored by git.

When Gmail outbound mode is enabled in the sidebar, customer responses are also sent through the connected Gmail account.

## Workflow

1. `ingest`: load email from `data/inbox`.
2. `triage`: classify `CLAIM`, `NON_CLAIM`, or `SPAM`.
3. `extract`: parse customer/product/issue fields.
4. `select_policy`: map product to policy metadata.
5. `retrieve_excerpts`: query policy chunks from Chroma.
6. `analyze`: apply deterministic rules + LLM recommendation.
7. `review_packet`: generate reviewer-facing summary.
8. `human_review` interrupt: reviewer confirms decision.
9. `draft_response`: prepare customer communication.
10. `email_gate` interrupt: final send checkpoint.
11. `outbox`: persist artifacts and final audit log.

## Repository Layout

```text
app/            Core workflow, nodes, state, LLM clients
ui/             Streamlit application
data/           Inbox samples, policies, catalog, test set
tests/          Unit and integration tests
reports/        Reporting templates (generated outputs are not committed)
```

## Policy Uploads

- Use the sidebar button Manage Policies to upload your own policy documents.
- Uploaded policies are stored locally under `outbox/policies` and indexed into ChromaDB.

## Product Catalog Uploads

- Use the sidebar button Manage Products to switch demo/uploaded product catalogs.
- Uploaded catalogs are stored locally under `outbox/products/products.json`.

## Attachments And OCR

- Gmail attachments are downloaded to `outbox/attachments/<message_id>/`.
- The workflow extracts text from `.txt/.md/.pdf/.json/.csv` attachments.
- Image OCR is supported when `pytesseract` and system Tesseract are available (`tesseract --version`).

## Development Commands

```bash
# Run tests
python -m pytest tests/

# Rebuild policy vector index
python index_db.py

# Evaluate against labeled test set
python evaluate.py

# Generate 20 additional demo claims (+ non-claim/spam variants)
python app/main.py --generate-demo 20
```

## Configuration

Use `.env` (copied from `.env.example`):

- `USE_OLLAMA`, `OLLAMA_MODEL`, `OLLAMA_URL`
- `GROQ_API_KEY`, `GROQ_MODEL`
- `GOOGLE_API_KEY`, `GEMINI_MODEL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `EMBEDDING_MODE` (`hash` recommended for deterministic local setup)
- `EMBEDDING_MODEL`
- `CLAIMS_DB_PATH` (optional SQLite DB override)
- `PRODUCTS_FILE` (optional product catalog path override)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM` (if using SMTP outbound)
- `EMAIL_FROM` (fallback sender identity)

## Professional Repo Standards

- CI pipeline on `push` and `pull_request` to `main`.
- Generated artifacts are excluded from version control.
- Security, contribution, architecture, and changelog docs are included.
- Legacy reports are removed; new reports are generated on demand.

## Status

- Last repository refresh: `2026-02-26`
- Primary branch: `main`
- Remote: `https://github.com/Sasidhar-7302/Claims_Agent`

## Contact

Sasidhar Yepuri  
Email: `yepuri.sasi07@gmail.com`
