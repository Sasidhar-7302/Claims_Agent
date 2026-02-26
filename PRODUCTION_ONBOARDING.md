# Production Onboarding Guide

This guide provides two paths:

- Free local demo on a single PC.
- Enterprise onboarding with real mailbox, database path, product catalog, and policy documents.

## 1) Free Local Demo (No Cost)

### Prerequisites

- Python 3.10+
- Windows: run `run_app.bat` or `run_app.ps1`

### Steps

1. Start the app.
2. Open **Setup Wizard** -> **Free Demo (Local)**.
3. Click **Generate More Demo Emails** if you want a larger queue.
4. Choose **Demo (no external model)** for fully free deterministic processing.
5. Click **Finish Free Demo Setup**.

### What this gives you

- Local inbox from `data/inbox`
- Demo policies from `data/policies`
- Demo products from `data/products.json`
- Local SQLite claims DB (default `outbox/claims.db`)
- No paid API required

## 2) Enterprise Setup (Production)

Use **Setup Wizard** -> **Enterprise Setup**.

### Step A: Database

- Set **SQLite path for claims DB** (for example `outbox/claims_prod.db`).
- This is persisted via `CLAIMS_DB_PATH` in `.env`.

### Step B: Product Catalog

- Choose **demo** or **uploaded** product source.
- For uploaded mode, provide a `products.json` with:
  - `products[]` entries containing:
    - `product_id`
    - `name`
    - `aliases` (list)
    - `policy_file`
- Use **Manage Products** page for ongoing updates.

### Step C: Policy Source

- Choose **demo** or **uploaded** policies.
- For uploaded mode:
  - Open **Manage Policies**
  - Upload policy files (`.txt`, `.md`, `.pdf`)
  - Map each to product ID + version
  - Rebuild vector index

### Step D: Mailbox + Outbound

- Inbox source:
  - `Local folder` for internal testing
  - `Gmail API` for real inbound email
- Outbound mode:
  - `Manual` (draft only)
  - `Gmail API`
  - `SMTP`

#### Gmail setup

1. Create Google OAuth client credentials (Installed App).
2. Upload client secrets JSON in onboarding or sidebar.
3. Click **Connect Gmail** and complete OAuth.
4. Set Gmail query (example: `label:claims is:unread`).

#### SMTP setup

Configure in `.env`:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_FROM`

### Step E: LLM Mode

- `Demo deterministic` (no external calls)
- `Ollama local` (local model)
- `API provider` (configure OpenAI/Groq/Gemini in sidebar)

### Step F: Finish

Use **Enterprise Readiness Checklist** and click **Finish Enterprise Setup** only when all checks are green.

## 3) Data Management Pages

- **Manage Products**: maintain product catalog source and upload validated JSON.
- **Manage Policies**: upload policy docs and metadata, then rebuild vector index.

## 4) Operational Notes

- Workflow checkpoints persist in SQLite: `outbox/checkpoints/langgraph_checkpoints.sqlite`
- Claims DB path is configurable.
- Outbound sends are idempotent (duplicate-send protection).
- Gmail attachments are downloaded and parsed; OCR for images is optional (requires system Tesseract).

