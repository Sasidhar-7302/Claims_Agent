# Warranty Claims Agent

> [!TIP]
> **Quick Start (Windows)**: double-click `run_app.bat`.
> It will install dependencies, initialize the vector DB, and launch the app.

An AI-powered warranty claims processing system with human-in-the-loop review for HairTech Industries.

## Quick Start

### One-Click Run (Recommended)
```cmd
run_app.bat
```

### Manual Run
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Setup environment
copy .env.example .env

# 3. Build database (first time only)
python index_db.py

# 4. Run App
streamlit run ui/streamlit_app.py
```

---

## LLM Providers

### Local (Ollama)
- Install Ollama: https://ollama.com/
- Example: `ollama run qwen2.5:1.5b`
- Default in `.env`: `USE_OLLAMA=true`

### Cloud Providers (UI Selector)
Use the **LLM Provider** panel in the sidebar to select a provider and apply your API key.
- Groq: `GROQ_API_KEY`
- Gemini: `GOOGLE_API_KEY`
- OpenAI: `OPENAI_API_KEY`

If **Remember key on this machine** is checked, the key is saved to `.env` (local only).
If no provider is available, the UI runs in **View-Only Mode** and disables processing.

---

## Project Structure

```
Claims_Agent/
- app/
  - main.py           # CLI entry point
  - graph.py          # LangGraph workflow
  - state.py          # ClaimState TypedDict
  - llm.py            # LLM client (Ollama/Groq/Gemini/OpenAI)
  - nodes/            # Workflow nodes
- ui/
  - streamlit_app.py  # Human review interface
- data/
  - inbox/            # 15 sample claim emails
  - policies/         # 10 warranty policy docs
  - chroma_db/        # Local vector store (auto-created)
  - products.json     # Product catalog
  - testset.jsonl     # Evaluation test set
- outbox/             # Generated outputs (created on run)
- reports/
  - report.md
- index_db.py
- evaluate.py
- performance_test.py
- test_rag_node.py
- requirements.txt
- README.md
```

---

## Workflow

```mermaid
graph LR
    A[Ingest Email] --> B[Triage]
    B -->|CLAIM| C[Extract Fields]
    B -->|SPAM/NON_CLAIM| END1[End]
    C --> D[Select Policy]
    D --> E[Retrieve Excerpts]
    E --> F[Analyze]
    F --> G[Build Review Packet]
    G --> H[Human Review]
    H --> I[Draft Response]
    I -->|APPROVE| J[Generate Label]
    I -->|REJECT/NEED_INFO| K[Email Gate]
    J --> K
    K --> END2[Complete]
```

---

## UI Highlights
- Inbox dashboard with KPI cards
- Human review packet with facts, assumptions, and reasoning
- Email dispatch screen with editable draft
- Non-claim emails can receive a courteous response

---

## CLI Usage

```bash
# List inbox emails
python app/main.py --list

# Process a specific claim
python app/main.py --process claim_001

# Run test mode (auto-approve first email)
python app/main.py --test --auto-approve

# Watch inbox continuously (polling)
python app/main.py --watch --interval 15 --auto-approve
```

---

## Configuration

Environment variables (`.env`):
```bash
# Option 1: Ollama (LOCAL - no API key needed)
USE_OLLAMA=true
OLLAMA_MODEL=qwen2.5:1.5b

# Option 2: Groq (CLOUD - fast inference)
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile

# Option 3: Gemini (CLOUD - fallback)
GOOGLE_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash

# Option 4: OpenAI (CLOUD - general purpose)
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini

# RAG Embeddings
# Use hash to avoid external downloads. Default uses SentenceTransformer if available.
EMBEDDING_MODE=hash
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Priority (auto mode): Ollama > Groq > Gemini. OpenAI is available via the provider selector.

---

## Evaluation

### Test Set
See `data/testset.jsonl` for labeled test cases.

Run the evaluator:
```bash
python evaluate.py
python evaluate.py --limit 5
python evaluate.py --ids claim_001,claim_003
```

Latest evaluation (Ollama qwen2.5:1.5b):
- Score: 15/15 (100.0%)
- Triage Accuracy: 100.0%
- Decision Accuracy (claims only): 100.0%
- Coverage (approve/reject): 66.7%
- Avg Confidence (claims only): 0.90

---

## Testing

Run unit and integration tests:
```bash
python -m pytest tests/
```

---

## Validation & Performance

- Accuracy: 100% on the labeled test set (15/15).
- Reliability: unit tests pass when run locally.
- Latency: varies by model and hardware.

See full report: `reports/report.md`

---

## Contact

Sasidhar Yepuri
Email: yepuri.sasi07@gmail.com
