# Architecture

This project is a human-in-the-loop warranty claims processing system.

## High-Level Components

- `ui/streamlit_app.py`: interactive operator interface.
- `app/graph.py`: LangGraph orchestration and interrupts.
- `app/nodes/*`: workflow nodes for triage, extraction, analysis, and output generation.
- `app/llm.py`: provider abstraction for Ollama, Groq, Gemini, and OpenAI.
- `app/vector_store.py`: policy indexing and retrieval using ChromaDB.
- `app/database.py`: SQLite persistence for processed claims.
- `app/checkpointing.py`: durable LangGraph checkpoint persistence (SQLite).
- `app/attachments.py`: attachment storage + text extraction/OCR helpers.
- `app/policy_manager.py`: policy document upload ingestion and index.json management.
- `app/product_catalog.py`: product catalog path selection, load/save, schema validation.
- `app/integrations/gmail.py`: Gmail OAuth + message fetch (inbound).
- `app/integrations/outbound_email.py`: idempotent outbound dispatch via Gmail API or SMTP.

## Workflow Lifecycle

1. Ingest email JSON from `data/inbox`.
2. Classify as claim/non-claim/spam.
3. Extract structured fields.
4. Select policy from product metadata.
5. Retrieve relevant policy chunks.
6. Analyze with deterministic checks and LLM reasoning.
7. Generate review packet.
8. Pause for human decision.
9. Draft response.
10. Pause before dispatch.
11. Send response (manual/gmail_api/smtp).
12. Finalize outputs and audit logs.

## Data and Outputs

- Input fixtures: `data/inbox`, `data/policies`, `data/products.json`.
- Configurable enterprise sources: `outbox/policies/*`, `outbox/products/products.json`, `CLAIMS_DB_PATH`.
- Runtime artifacts: `outbox/` (intentionally ignored by git).
- Evaluation fixtures: `data/testset.jsonl`.

## Demo vs Live

- Demo mode: deterministic triage/extraction/analysis, no external LLM required.
- Live mode: connect a real mailbox (Gmail) and process real emails; upload policies for your products.

## Reliability Notes

- Deterministic checks run before free-form LLM decisions where possible.
- Workflow supports pause/resume for operator review gates.
- Policy retrieval is scoped by selected product/policy metadata.
- Outbound delivery uses idempotency keys to prevent duplicate sends.
- Checkpoint and claim data persist in SQLite under `outbox/`.
