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

## Development Commands

```bash
# Run tests
python -m pytest tests/

# Rebuild policy vector index
python index_db.py

# Evaluate against labeled test set
python evaluate.py
```

## Configuration

Use `.env` (copied from `.env.example`):

- `USE_OLLAMA`, `OLLAMA_MODEL`, `OLLAMA_URL`
- `GROQ_API_KEY`, `GROQ_MODEL`
- `GOOGLE_API_KEY`, `GEMINI_MODEL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `EMBEDDING_MODE` (`hash` recommended for deterministic local setup)
- `EMBEDDING_MODEL`

## Professional Repo Standards

- CI pipeline on `push` and `pull_request` to `main`.
- Generated artifacts are excluded from version control.
- Security, contribution, architecture, and changelog docs are included.
- Legacy reports are removed; new reports are generated on demand.

## Status

- Last repository refresh: `2026-02-25`
- Primary branch: `main`
- Remote: `https://github.com/Sasidhar-7302/Claims_Agent`

## Contact

Sasidhar Yepuri  
Email: `yepuri.sasi07@gmail.com`
