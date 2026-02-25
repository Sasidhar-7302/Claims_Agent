# Architecture

This project is a human-in-the-loop warranty claims processing system.

## High-Level Components

- `ui/streamlit_app.py`: interactive operator interface.
- `app/graph.py`: LangGraph orchestration and interrupts.
- `app/nodes/*`: workflow nodes for triage, extraction, analysis, and output generation.
- `app/llm.py`: provider abstraction for Ollama, Groq, Gemini, and OpenAI.
- `app/vector_store.py`: policy indexing and retrieval using ChromaDB.
- `app/database.py`: SQLite persistence for processed claims.

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
11. Finalize outputs and audit logs.

## Data and Outputs

- Input fixtures: `data/inbox`, `data/policies`, `data/products.json`.
- Runtime artifacts: `outbox/` (intentionally ignored by git).
- Evaluation fixtures: `data/testset.jsonl`.

## Reliability Notes

- Deterministic checks run before free-form LLM decisions where possible.
- Workflow supports pause/resume for operator review gates.
- Policy retrieval is scoped by selected product/policy metadata.
