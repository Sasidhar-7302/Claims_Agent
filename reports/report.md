# Warranty Claims Agent - Project Report

## 1. Problem Framing & Assumptions
The goal was to build an Agentic AI system to automate high-volume warranty claims for HairTech Industries. The core challenge is balancing automation scale with human oversight.

**Key Assumptions:**
*   **Warranty Window**: STRICT 3-month window from purchase date.
*   **Data Source**: Input is a simulated "Inbox" (folder of JSON files) to mimic email ingestion.
*   **Policy Retrieval**: RAG is used to fetch specific policy sections, assuming policies are available as text/markdown.
*   **Single Product per Email**: Each claim references exactly one product.
*   **Attachments**: Attachments are mocked; no OCR is performed.
*   **Human Oversight**: Every claim requires explicit human approval; the AI provides a *recommendation*, not a final decision.
*   **Mocked Outputs**: Email dispatch and label generation are simulated by writing files to an `outbox` directory.

## 2. System Design (Architecture)
The system is built using **LangGraph** for orchestration and **Streamlit** for the human-in-the-loop UI.

**Agent Roles / Workflow Nodes:**
1.  **Ingest**: Reads JSON email files.
2.  **Triage** (LLM): Filters Spam vs. Valid Claims vs. Non-Claim inquiries.
3.  **Extract** (LLM): Structured extraction of Customer, Product, Issue, Dates, and evidence hints.
4.  **Policy Selection** (Deterministic): Maps product name to specific policy ID.
5.  **Retrieve** (RAG/VectorDB): Fetches relevant warranty clauses (exclusions, coverage) for the specific product.
6.  **Analyze** (LLM): Synthesizes extracted facts against policy rules to determine validity.
7.  **Review Packet**: Generates a Markdown summary for the human reviewer.
8.  **Human Gate**: **[INTERRUPT]** - The workflow pauses state here and waits for UI interaction.
9.  **Draft Response**: Pre-writes the email (Approval or Rejection with reasoning).
10. **Email Gate**: **[INTERRUPT]** - Pauses again to allow manual edit/send of the final email.
11. **Outbox**: Finalizes the process, saving logs and artifacts.

## 3. Policy Selection & Rationale
We implemented a two-stage approach for high accuracy:
1.  **Selection**: Deterministic mapping (exact string matching/fuzzy matching) extracts the "Product Name" to select the correct Policy Document ID. This avoids hallucination.
2.  **Retrieval**: Using a vector store (ChromaDB), we search *only* within that specific policy document for relevant clauses (e.g., "water damage", "cord fraying").

**Decision Rationale:**
The `Analyze` node produces a structured output separating **Facts** (Purchase Date: Jan 12), **Assumptions** (User didn't misuse product), and **Reasoning** (Date is within 3 months, no exclusions triggered).

## 4. Human-in-the-Loop Flow
The **Streamlit UI** provides a professional dashboard for reviewers:
*   **Inbox View**: KPI cards showing Pending/Processed counts.
*   **Split-Screen Review**: Left side shows "Context" (Customer/Product), Right side shows "Analysis" (Recommendation, Confidence Score).
*   **Actionable Decisions**: Buttons for Approve, Reject, or Request Info.
*   **Email Dispatch**: A dedicated "Ready to Send" stage allows the reviewer to edit the generated email and inspect the return label (PDF stub) before final dispatch.

## 5. Evaluation Plan
To ensure production readiness:

**Offline Evaluation**:
*   Script: `evaluate.py`
*   Dataset: `data/testset.jsonl` (15 labeled examples covering valid, expired, exclusion, spam, and non-claim cases).
*   Metrics: Triage Accuracy, Decision Accuracy (claims only), Coverage (approve/reject), and Average Confidence.

**Offline Results (Ollama qwen2.5:1.5b)**:
*   **Score**: 15/15 (100.0%)
*   **Triage Accuracy**: 100.0%
*   **Decision Accuracy (claims only)**: 100.0%
*   **Coverage (approve/reject)**: 66.7%
*   **Avg Confidence (claims only)**: 0.90

**Online Monitoring (Proposed)**:
*   **Human Override Rate**: How often does the human disagree with the AI recommendation? (Target < 10%)
*   **Processing Efficiency**: Time saved per claim vs full manual review.
*   **Drift Detection**: Monitor confidence scores over time to detect new product issues not covered by policies.

## 6. What's Next & Limitations
**Missing / Future Work**:
*   **Real Email Integration**: Replace file ingestion with IMAP/Gmail API triggers.
*   **OCR**: Add vision capabilities to process photo attachments (receipts, damage photos).
*   **CRM Integration**: Sync customer data with a real CRM (Salesforce/HubSpot).
*   **Confidence Calibration**: Use historical labels to tune thresholds for auto-escalation.

**Intentionally Skipped**:
*   **Live SMTP**: To avoid spamming real addresses, we write to `outbox/`.
*   **Full Auth**: The UI is currently open; production would require SSO/Login.
*   **Real Attachments**: Proof-of-purchase images are mocked for this take-home exercise.
