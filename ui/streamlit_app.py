"""
Streamlit UI for Warranty Claims Agent

Human review interface for processing warranty claims with pause/resume workflow.
Features persistent session state and processed claims tracking.
"""

import os
import sys
import json
import base64
import streamlit as st
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv, set_key
# Explicitly load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from app.state import create_initial_state
from app.graph import compile_workflow
from app.database import (
    save_claim, get_recent_claims, get_claim_by_email_id, 
    get_all_processed_email_ids, get_claim_decisions, 
    clear_all_claims, get_stats
)
from app.nodes.draft_response import draft_non_claim_response
from langgraph.checkpoint.memory import MemorySaver

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"
OUTBOX_DIR = BASE_DIR / "outbox"
SESSION_FILE = OUTBOX_DIR / "session_state.json"
ENV_PATH = BASE_DIR / ".env"
LLM_ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY"
}

# Page configuration
st.set_page_config(
    page_title="Warranty Claims Agent",
    page_icon="W",
    layout="wide",
    initial_sidebar_state="expanded"
)


def apply_custom_styles():
    """Apply modern enterprise CSS styles."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        :root {
            --primary: #F2542D;     /* Brand Orange */
            --primary-dark: #D13E1A;
            --brand-teal: #2C5559;  /* Brand Teal */
            --brand-teal-light: #E0EBEB;
            --secondary: #64748B;
            --bg-soft: #F1F5F9;
            --surface: #FFFFFF;
            --border: #E2E8F0;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #0F172A;
        }
        
        /* Sidebar branding */
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF;
        }
        
        h1, h2, h3 {
            color: var(--brand-teal) !important;
        }
        
        /* Main Container */
        .stApp {
            background-color: var(--bg-soft);
        }
        
        /* Cards */
        .claim-card {
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border-left: 4px solid var(--brand-teal);
        }
        .claim-card:hover {
            box-shadow: 0 10px 15px -3px rgba(44, 85, 89, 0.1);
            transform: translateY(-2px);
        }
        
        /* KPI Cards */
        .kpi-card {
            background-color: var(--surface);
            padding: 1.25rem;
            border-radius: 12px;
            border: 1px solid var(--border);
            text-align: center;
            border-bottom: 3px solid var(--primary);
        }
        .kpi-value {
            font-size: 2rem;
            font-weight: 800;
            color: var(--brand-teal);
            margin-bottom: 0.25rem;
        }
        .kpi-label {
            font-size: 0.8rem;
            color: var(--secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Status Badges */
        .status-badge {
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            display: inline-block;
            text-transform: uppercase;
        }
        .status-pending { background-color: #FFF7ED; color: #C2410C; border: 1px solid #FFEDD5; }
        .status-approve { background-color: #F0FDF4; color: #15803D; border: 1px solid #DCFCE7; }
        .status-reject { background-color: #FEF2F2; color: #B91C1C; border: 1px solid #FEE2E2; }
        .status-info { background-color: #F0F9FF; color: #0369A1; border: 1px solid #E0F2FE; }
        
        /* Buttons */
        .stButton button {
            border-radius: 6px;
            font-weight: 600;
            padding: 0.5rem 1.25rem;
            border: none;
            transition: all 0.2s;
        }
        /* Primary Button (Orange) */
        div[data-testid="stButton"] button[kind="primary"] {
            background-color: var(--primary);
            color: white;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover {
            background-color: var(--primary-dark);
        }
        </style>
    """, unsafe_allow_html=True)

apply_custom_styles()


def load_session_state():
    """Load persistent session state from file."""
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"processed_claims": [], "claim_decisions": {}}


def save_session_state(processed_claims, claim_decisions):
    """Save session state to file for persistence."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed_claims": processed_claims,
            "claim_decisions": claim_decisions
        }, f, indent=2)


def get_saved_api_key(provider_key: str) -> str:
    """Load a saved API key from .env for the given provider."""
    env_key = LLM_ENV_KEYS.get(provider_key)
    if not env_key:
        return ""
    return os.getenv(env_key, "") or ""


def save_api_key(provider_key: str, api_key: str) -> bool:
    """Persist the API key to .env for reuse across sessions."""
    env_key = LLM_ENV_KEYS.get(provider_key)
    if not env_key:
        return False
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), env_key, api_key)
    os.environ[env_key] = api_key
    return True


def is_out_of_credits(error: Exception) -> bool:
    """Best-effort detection for quota/credit errors across providers."""
    message = str(error).lower()
    signals = [
        "insufficient_quota",
        "insufficient quota",
        "quota exceeded",
        "exceeded your current quota",
        "out of credits",
        "no credits",
        "credit balance",
        "billing",
        "resource_exhausted"
    ]
    return any(signal in message for signal in signals)


# Initialize session state with database persistence
if "initialized" not in st.session_state:
    # Load from database instead of JSON file
    from app.database import get_all_processed_email_ids, get_claim_decisions, get_recent_claims
    
    processed_ids = get_all_processed_email_ids()
    claim_decisions_db = get_claim_decisions()
    recent = get_recent_claims(50)  # Load up to 50 recent claims
    
    st.session_state.processed_claims = [
        {"email_id": c["email_id"], "decision": c["decision"], "timestamp": c.get("timestamp", "")}
        for c in recent
    ]
    st.session_state.claim_decisions = claim_decisions_db
    st.session_state.workflow = None
    st.session_state.checkpointer = MemorySaver()
    st.session_state.current_state = None
    st.session_state.current_email = None
    st.session_state.pending_dispatch = []
    st.session_state.workflow_stage = "select"
    st.session_state.initialized = True

if "pending_dispatch" not in st.session_state:
    st.session_state.pending_dispatch = []
if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = "Ollama (Local)"
if "llm_api_key_input" not in st.session_state:
    st.session_state.llm_api_key_input = ""
if "llm_key_provider" not in st.session_state:
    st.session_state.llm_key_provider = ""
if "llm_save_key" not in st.session_state:
    st.session_state.llm_save_key = False
if "llm_model" not in st.session_state:
    st.session_state.llm_model = ""
if "llm_active_config" not in st.session_state:
    st.session_state.llm_active_config = {
        "provider": "ollama",
        "api_key": "",
        "model": ""
    }
if "llm_force_refresh" not in st.session_state:
    st.session_state.llm_force_refresh = False
if "llm_available" not in st.session_state:
    st.session_state.llm_available = False
if "llm_error" not in st.session_state:
    st.session_state.llm_error = ""
if "non_claim_drafts" not in st.session_state:
    st.session_state.non_claim_drafts = {}


def load_inbox_emails():
    """Load all emails from inbox, with processed ones at the bottom."""
    emails = []
    # Get processed claims from database
    processed_ids = get_all_processed_email_ids()
    claim_decisions = get_claim_decisions()
    
    for f in sorted(INBOX_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                email_id = data.get("email_id", f.stem)
                is_processed = email_id in processed_ids
                decision = claim_decisions.get(email_id, None)
                
                emails.append({
                    "file": f.name,
                    "email_id": email_id,
                    "subject": data.get("subject", "No subject"),
                    "from": data.get("from", "Unknown"),
                    "date": data.get("date", "Unknown"),
                    "body": data.get("body", "")[:200],
                    "expected": data.get("metadata", {}).get("expected_outcome", "Unknown"),
                    "is_processed": is_processed,
                    "decision": decision
                })
        except Exception as e:
            st.error(f"Error loading {f.name}: {e}")
    
    # Sort: unprocessed first, then processed
    emails.sort(key=lambda x: (x["is_processed"], x["email_id"]))
    return emails


def run_workflow_to_review(email_id: str):
    """Run workflow until human review interrupt."""
    if not st.session_state.get("llm_available", False):
        st.error("LLM unavailable. Configure a provider in the sidebar.")
        return False
    try:
        initial_state = create_initial_state(email_id)
        print(f"[DEBUG] Starting workflow for email: {email_id}")
        
        workflow = compile_workflow(st.session_state.checkpointer)
        st.session_state.workflow = workflow
        
        config = {"configurable": {"thread_id": email_id}}
        
        # Check if we already have a state for this email to keep ID consistent
        initial_input = create_initial_state(email_id)
        try:
            snapshot = workflow.get_state(config)
            if snapshot and snapshot.values:
                # If we have a state, we resume with None input to keep existing claim_id
                 print(f"[DEBUG] Resuming existing workflow for email: {email_id} to keep ID stable")
                 initial_input = None
        except:
             pass

        last_state = None
        progress = st.progress(0)
        status_text = st.empty()
        
        steps = ["ingest", "triage", "extract", "select_policy", 
                 "retrieve_excerpts", "analyze", "review_packet"]
        step_count = 0
        
        for event in workflow.stream(initial_input, config):
            for node_name, node_output in event.items():
                print(f"[DEBUG] Completed node: {node_name}")
                step_count += 1
                step_idx = steps.index(node_name) if node_name in steps else step_count
                progress.progress(min((step_idx + 1) / len(steps), 1.0))
                status_text.text(f"Processing: {node_name}...")
                if not node_name.startswith("__"):
                    last_state = node_output
        
        progress.progress(1.0)
        status_text.empty()
        
        # Get state from checkpointer after interrupt
        try:
            snapshot = workflow.get_state(config)
            if snapshot and hasattr(snapshot, 'values') and snapshot.values:
                final_state = dict(snapshot.values)
                print(f"[DEBUG] Got state from snapshot: {final_state.get('workflow_status')}")
            elif last_state:
                final_state = last_state
            else:
                final_state = None
        except Exception as e:
            print(f"[DEBUG] Error getting snapshot: {e}")
            final_state = last_state
        
        if final_state:
            # Check if stopped at email gate
            if final_state.get("workflow_status") == "AWAITING_EMAIL":
                 st.session_state.current_state = final_state
                 st.session_state.current_email = email_id
                 st.session_state.workflow_stage = "dispatch"
                 return True
            
            st.session_state.current_state = final_state
            st.session_state.current_email = email_id
            st.session_state.workflow_stage = "review"
            return True
        else:
            st.error("Workflow completed but no state was returned")
            return False
        
    except Exception as e:
        print(f"[DEBUG] ERROR: {e}")
        import traceback
        traceback.print_exc()
        st.error(f"Error processing claim: {e}")
        st.session_state.workflow_stage = "select"
        return False


def resume_workflow_with_decision(decision: str, notes: str = ""):
    """Resume workflow after human decision."""
    try:
        email_id = st.session_state.current_email
        workflow = st.session_state.workflow
        config = {"configurable": {"thread_id": email_id}}
        
        print(f"[DEBUG] Resuming workflow for email: {email_id} with decision: {decision}")
        
        # Clear stale data and force re-run from human_review point
        workflow.update_state(
            config,
            {
                "human_decision": decision,
                "human_notes": notes,
                "human_reviewer": "streamlit_user",
                "human_review_timestamp": datetime.now().isoformat(),
                "return_label_path": None,      # Reset label so it must be regenerated
                "customer_email_draft": None,   # Reset draft
                "customer_email_path": None     # Reset draft path
            },
            as_node="human_review"
        )
        
        last_state = None
        with st.spinner("Finalizing claim..."):
            for event in workflow.stream(None, config):
                for node_name, node_output in event.items():
                    print(f"[DEBUG] Resume - Completed node: {node_name}")
                    if not node_name.startswith("__"):
                        last_state = node_output
        
        # Get final state from checkpointer
        snapshot = None
        try:
            snapshot = workflow.get_state(config)
            if snapshot and hasattr(snapshot, 'values') and snapshot.values:
                final_state = dict(snapshot.values)
            elif last_state:
                final_state = last_state
            else:
                final_state = {"human_decision": decision}
        except Exception as e:
            final_state = last_state if last_state else {"human_decision": decision}
        
        st.session_state.current_state = final_state
        
        awaiting_email = False
        if snapshot and snapshot.next and "email_gate" in snapshot.next:
            awaiting_email = True
        if final_state.get("workflow_status") == "AWAITING_EMAIL":
            awaiting_email = True
        
        # If stopped before email_gate, go to dispatch screen
        if awaiting_email:
             st.session_state.workflow_stage = "dispatch"
             st.session_state.current_email = email_id
             if email_id not in st.session_state.pending_dispatch:
                 st.session_state.pending_dispatch.append(email_id)
             # Do NOT save to processed_claims yet
             return True
        
        # Otherwise complete as before (e.g. for rejected without email)
        st.session_state.workflow_stage = "complete"
        
        # Save to database for persistence
        save_claim(final_state, decision, notes)
        
        # Update session state
        st.session_state.processed_claims.append({
            "email_id": email_id,
            "decision": decision,
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.claim_decisions[email_id] = decision
        
        return True
        
    except Exception as e:
        print(f"[DEBUG] Resume error: {e}")
        st.error(f"Error resuming workflow: {e}")
        import traceback
        traceback.print_exc()
        return False


def render_sidebar():
    """Render the application sidebar."""
    with st.sidebar:
        # Logo Area
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
            <div style="width: 40px; height: 40px; background-color: #F2542D; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                <span style="color: white; font-weight: 800; font-size: 24px;">o</span>
            </div>
            <div>
                <h2 style="margin: 0; font-size: 1.2rem; font-weight: 800; color: #2C5559;">orcaworks</h2>
                <div style="font-size: 0.7rem; color: #64748B; letter-spacing: 1px; font-weight: 600;">DIGITAL COWORKER</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### LLM Provider")
        provider_options = ["Ollama (Local)", "Groq", "Gemini", "OpenAI"]
        provider_map = {
            "Ollama (Local)": "ollama",
            "Groq": "groq",
            "Gemini": "gemini",
            "OpenAI": "openai"
        }
        model_placeholders = {
            "ollama": "qwen2.5:1.5b",
            "groq": "llama-3.3-70b-versatile",
            "gemini": "gemini-2.0-flash",
            "openai": "gpt-4o-mini"
        }
        with st.form("llm_config_form", clear_on_submit=False):
            provider_choice = st.selectbox("Provider", provider_options, key="llm_provider")
            provider_key = provider_map[provider_choice]
            saved_key = get_saved_api_key(provider_key)
            if st.session_state.llm_key_provider != provider_key:
                st.session_state.llm_api_key_input = saved_key
                st.session_state.llm_key_provider = provider_key
                st.session_state.llm_save_key = bool(saved_key)
            needs_key = provider_key in ("groq", "gemini", "openai")
            if needs_key:
                st.text_input(
                    "API key",
                    type="password",
                    key="llm_api_key_input",
                    help="Stored in memory for this session."
                )
                if saved_key and st.session_state.llm_api_key_input == saved_key:
                    st.caption("Loaded saved key from .env.")
                st.checkbox("Remember key on this machine", key="llm_save_key")
                st.caption("Saved keys are stored in .env (local only).")
            else:
                st.caption("Local Ollama uses your machine; no API key required.")
                st.checkbox("Remember key on this machine", key="llm_save_key", disabled=True)
            st.text_input(
                "Model override (optional)",
                key="llm_model",
                placeholder=model_placeholders.get(provider_key, "")
            )
            st.caption("Click Apply Provider to activate these settings.")
            submitted = st.form_submit_button("Apply Provider")
        if submitted:
            api_key = st.session_state.llm_api_key_input.strip() if needs_key else ""
            model = st.session_state.llm_model.strip()
            if needs_key and not api_key:
                st.error(f"{provider_choice} requires an API key.")
            else:
                previous_config = st.session_state.llm_active_config.copy()
                try:
                    from app.llm import get_llm
                    llm = get_llm(
                        provider=provider_key,
                        api_key=api_key or None,
                        model=model or None,
                        force_new=True
                    )
                    if provider_key != "ollama":
                        llm.generate("Reply with OK.", max_tokens=5)
                    st.session_state.llm_active_config = {
                        "provider": provider_key,
                        "api_key": api_key,
                        "model": model
                    }
                    st.session_state.llm_force_refresh = True
                    st.session_state.llm_available = True
                    st.session_state.llm_error = ""
                    if needs_key and st.session_state.llm_save_key:
                        save_api_key(provider_key, api_key)
                    st.success("LLM settings updated.")
                except Exception as e:
                    st.session_state.llm_active_config = previous_config
                    st.session_state.llm_force_refresh = True
                    st.session_state.llm_available = False
                    out_of_credits = is_out_of_credits(e)
                    if out_of_credits:
                        st.session_state.llm_error = f"{provider_choice} out of credits/quota."
                        st.error(f"{provider_choice} appears to be out of credits or quota.")
                    else:
                        st.session_state.llm_error = str(e)
                        st.error(f"Could not connect to {provider_choice}: {e}")

        st.markdown("---")
        st.write("**Recent Activity**")
        
        # Mini feed of recent actions (click to open)
        recent_claims = sorted(
            st.session_state.processed_claims,
            key=lambda c: c.get("timestamp", ""),
            reverse=True
        )[:5]
        if not recent_claims:
            st.caption("No recent activity yet.")
        for idx, claim in enumerate(recent_claims):
            decision = claim.get("decision", "DONE")
            label = f"{decision} - {claim.get('email_id', 'unknown')}"
            if st.button(label, key=f"recent_{idx}_{claim.get('email_id', 'unknown')}"):
                st.session_state.view_claim_id = claim.get("email_id")
                st.session_state.workflow_stage = "view_claim"
                st.rerun()
        
        if len(st.session_state.processed_claims) > 5:
            if st.button("📋 View All History", use_container_width=True):
                st.session_state.workflow_stage = "claim_history"
                st.rerun()

        st.markdown("---")
        if st.button("Reset Session", use_container_width=True):
            # Clear database
            clear_all_claims()
            # Clear persistent file
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
            st.session_state.processed_claims = []
            st.session_state.claim_decisions = {}
            st.session_state.current_email = None
            st.session_state.current_state = None
            st.session_state.view_claim_id = None
            st.session_state.workflow = None
            st.session_state.checkpointer = MemorySaver()
            st.session_state.workflow_stage = "select"
            st.session_state.emails = load_inbox_emails()
            st.rerun()




def render_claim_history():
    """Render the full claim history page with sorting and filtering."""
    st.markdown("## 📋 Claim History")
    st.markdown("View all processed claims. Click any row to see details.")
    
    claims = st.session_state.processed_claims
    
    if not claims:
        st.info("No processed claims yet.")
        if st.button("Back to Dashboard"):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return
    
    # Controls
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        sort_by = st.selectbox("Sort By", ["Date (Newest)", "Date (Oldest)", "Claim ID", "Decision"], key="history_sort")
    with col2:
        filter_decision = st.selectbox("Filter Decision", ["All", "APPROVE", "REJECT", "NEED_INFO", "SPAM"], key="history_filter")
    with col3:
        search_term = st.text_input("Search Claim ID", key="history_search", placeholder="e.g. claim_001")
    
    # Apply filters
    filtered = claims
    if filter_decision != "All":
        filtered = [c for c in filtered if c.get("decision") == filter_decision]
    if search_term:
        filtered = [c for c in filtered if search_term.lower() in c.get("email_id", "").lower()]
    
    # Apply sorting
    if sort_by == "Date (Newest)":
        filtered = sorted(filtered, key=lambda x: x.get("timestamp", ""), reverse=True)
    elif sort_by == "Date (Oldest)":
        filtered = sorted(filtered, key=lambda x: x.get("timestamp", ""))
    elif sort_by == "Claim ID":
        filtered = sorted(filtered, key=lambda x: x.get("email_id", ""))
    elif sort_by == "Decision":
        filtered = sorted(filtered, key=lambda x: x.get("decision", ""))
    
    st.caption(f"Showing {len(filtered)} of {len(claims)} claims")
    st.markdown("---")
    
    # Table header
    h_id, h_date, h_decision, h_action = st.columns([2, 2, 1.5, 1])
    with h_id:
        st.markdown("**Claim ID**")
    with h_date:
        st.markdown("**Processed**")
    with h_decision:
        st.markdown("**Decision**")
    with h_action:
        st.markdown("**Action**")
    
    # Table rows
    for idx, claim in enumerate(filtered):
        c_id, c_date, c_dec, c_act = st.columns([2, 2, 1.5, 1])
        with c_id:
            st.code(claim.get("email_id", "unknown"))
        with c_date:
            ts = claim.get("timestamp", "")
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                st.write(dt.strftime("%Y-%m-%d %H:%M"))
            except:
                st.write(ts[:19] if ts else "N/A")
        with c_dec:
            dec = claim.get("decision", "UNKNOWN")
            color = "#166534" if dec == "APPROVE" else "#991B1B" if dec == "REJECT" else "#1E40AF"
            st.markdown(f'<span style="color:{color}; font-weight:600">{dec}</span>', unsafe_allow_html=True)
        with c_act:
            if st.button("View", key=f"hist_{idx}_{claim.get('email_id')}"):
                st.session_state.view_claim_id = claim.get("email_id")
                st.session_state.workflow_stage = "view_claim"
                st.rerun()
        st.markdown("---")
    
    if st.button("← Back to Dashboard", use_container_width=True):
        st.session_state.workflow_stage = "select"
        st.rerun()

def render_email_selection():
    """Render the dashboard/inbox view."""
    
    st.markdown("## Warranty Claims Dashboard")
    st.markdown("Manage and process your incoming claim queue.")
    
    emails = st.session_state.emails
    processed_ids = [c["email_id"] for c in st.session_state.processed_claims]
    
    # KPI Section
    total = len(emails)
    done = len([e for e in emails if e['is_processed']])
    pending = total - done
    approvals = len([c for c in st.session_state.processed_claims if c['decision'] == 'APPROVE'])
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{total}</div><div class="kpi-label">Total Claims</div></div>', unsafe_allow_html=True)
    with kpi2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{pending}</div><div class="kpi-label">Pending</div></div>', unsafe_allow_html=True)
    with kpi3:
        st.markdown(f'<div class="kpi-card"><div class="kpi-value">{done}</div><div class="kpi-label">Processed</div></div>', unsafe_allow_html=True)
    with kpi4:
         st.markdown(f'<div class="kpi-card"><div class="kpi-value">{approvals}</div><div class="kpi-label">Approved</div></div>', unsafe_allow_html=True)
    
    st.markdown("### Incoming Queue")
    llm_ready = st.session_state.get("llm_available", False)
    if not llm_ready:
        st.warning("LLM unavailable. Configure a provider to process claims.")
    
    for email in emails:
        is_processed = email['email_id'] in processed_ids
        
        # ALWAYS HIDE processed claims from dashboard (User Request)
        # They can be accessed via Recent Activity sidebar
        if is_processed:
            continue
            
        with st.container():
            st.markdown("---")
            # Layout: Claim ID | Date | Subject & Email | Status | Action
            c_id, c_date, c_content, c_status, c_action = st.columns([1, 1.2, 3.5, 1, 1])
            
            with c_id:
                st.caption("ID")
                st.markdown(f"**`{email['email_id']}`**")
                
            with c_date:
                st.caption("Date")
                # Format date nicely if possible, distinct lines for date and time
                raw_date = email['date']
                try:
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    st.markdown(f"{dt.strftime('%Y-%m-%d')}")
                    st.caption(f"{dt.strftime('%H:%M')}")
                except:
                    st.markdown(f"{raw_date}")
            
            with c_content:
                st.caption("Claim & Customer")
                st.markdown(f"**{email['subject']}**")
                st.caption(f"From: {email['from']}")
                
            with c_status:
                st.caption("Status")
                if is_processed:
                    decision = st.session_state.claim_decisions.get(email['email_id'], "DONE")
                    badge = "approve" if decision == "APPROVE" else "reject" if decision == "REJECT" else "info"
                    st.markdown(f'<span class="status-badge status-{badge}">{decision}</span>', unsafe_allow_html=True)
                else:
                    if email['email_id'] in st.session_state.pending_dispatch:
                         st.markdown('<span class="status-badge status-approve">READY TO SEND</span>', unsafe_allow_html=True)
                    else:
                         st.markdown('<span class="status-badge status-pending">PENDING</span>', unsafe_allow_html=True)
            
            with c_action:
                st.caption("Action")
                if not is_processed:
                    if email['email_id'] in st.session_state.pending_dispatch:
                         if st.button("Resume", key=f"res_{email['email_id']}"):
                             st.session_state.current_email = email['email_id']
                             st.session_state.workflow_stage = "dispatch"
                             st.rerun()
                    else:
                         if st.button(
                             "Process",
                             key=f"btn_{email['email_id']}",
                             type="primary",
                             disabled=not llm_ready,
                             help="Configure an LLM provider to process claims."
                         ):
                             st.session_state.current_email = email['email_id']
                             # The original `run_workflow_to_review` handles setting current_state and workflow_stage
                             with st.spinner("Analyzing claim..."):
                                 success = run_workflow_to_review(email['email_id'])
                             if success:
                                 st.rerun()
                             else:
                                 st.error("Processing failed.")

    
def render_review_interface():
    """Render the human review interface."""
    state = st.session_state.current_state
    
    if not state:
        st.error("No claim state found")
        if st.button("Back to Inbox", use_container_width=True):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return

    if state.get("error_message"):
        st.warning(f"Processing warning: {state.get('error_message')}")
    
    # Check if triaged as non-claim
    triage_result = state.get("triage_result", "CLAIM")
    if triage_result != "CLAIM":
        st.markdown(f"""
        <div style="background-color: #F8FAFC; padding: 2rem; border-radius: 12px; text-align: center; border: 1px solid #E2E8F0; margin-bottom: 2rem;">
            <h2 style="color: #64748B; margin-top: 0;">Email Flagged as {triage_result}</h2>
            <p style="color: #475569; margin-bottom: 0;">{state.get('triage_reason', 'Analysis determined this is not a valid warranty claim.')}</p>
        </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 1, 1])
        
        with c1:
            if st.button("Confirm & Archive", use_container_width=True, type="primary"):
                # Save as processed so it disappears from queue
                save_claim(state, decision=triage_result, notes="Archived by user")
                st.session_state.processed_claims.append({
                    "email_id": state.get("email_id"),
                    "decision": triage_result,
                    "timestamp": datetime.now().isoformat()
                })
                st.session_state.claim_decisions[state.get("email_id")] = triage_result
                st.session_state.workflow_stage = "select"
                st.session_state.current_state = None
                st.success(f"Archived as {triage_result}")
                st.rerun()
                
        with c2:
            if st.button(
                "Not Spam - Force Process",
                use_container_width=True,
                disabled=not st.session_state.get("llm_available", False),
                help="Configure an LLM provider to process claims."
            ):
                with st.spinner("Overriding & analyzing..."):
                    # Manually force the next steps since graph stopped
                    from app.nodes.extract import extract_fields
                    from app.nodes.product_policy import select_product_policy
                    from app.nodes.retrieve_policy import retrieve_policy_excerpts
                    from app.nodes.analyze import analyze_claim
                    from app.nodes.review_packet import build_review_packet
                    
                    # Force type to CLAIM
                    state["triage_result"] = "CLAIM"
                    
                    # Run pipeline
                    state = extract_fields(state)
                    state = select_product_policy(state)
                    state = retrieve_policy_excerpts(state)
                    state = analyze_claim(state)
                    state = build_review_packet(state)
                    
                    st.session_state.current_state = state
                    st.rerun()

        with c3:
            if st.button("Return to Inbox", use_container_width=True):
                st.session_state.workflow_stage = "select"
                st.session_state.current_state = None
                st.rerun()

        if triage_result == "NON_CLAIM":
            st.markdown("---")
            st.markdown("### Customer Response")

            email_id = state.get("email_id")
            draft = st.session_state.non_claim_drafts.get(email_id)

            if st.button("Draft Response", use_container_width=True):
                extracted = state.get("extracted_fields", {}) or {}
                draft_data = draft_non_claim_response(
                    claim_id=state.get("claim_id", "UNKNOWN"),
                    customer_name=extracted.get("customer_name") or "",
                    email_subject=state.get("email_subject", ""),
                    email_from=state.get("email_from", "")
                )
                st.session_state.non_claim_drafts[email_id] = draft_data
                draft = draft_data
                st.success("Draft created.")

            if draft:
                st.caption(f"To: {draft.get('to') or 'unknown'}")
                edited = st.text_area(
                    "Review and edit response:",
                    value=draft.get("email_content", ""),
                    height=300,
                    key=f"non_claim_edit_{email_id}"
                )

                if edited != draft.get("email_content", ""):
                    draft["email_content"] = edited
                    try:
                        with open(draft.get("email_path", ""), "w", encoding="utf-8") as f:
                            f.write(edited)
                    except Exception as e:
                        st.error(f"Could not save draft: {e}")

                if st.button("Send Response", use_container_width=True, type="primary"):
                    sent_dir = OUTBOX_DIR / "sent"
                    sent_dir.mkdir(parents=True, exist_ok=True)
                    sent_path = sent_dir / f"{state.get('claim_id', 'UNKNOWN')}_non_claim_sent.txt"
                    try:
                        with open(sent_path, "w", encoding="utf-8") as f:
                            f.write(edited)
                    except Exception as e:
                        st.error(f"Could not write sent copy: {e}")
                        return

                    completed_state = {
                        **state,
                        "customer_email_draft": edited,
                        "customer_email_path": draft.get("email_path", ""),
                        "email_sent": True,
                        "human_decision": "NON_CLAIM",
                        "human_notes": "Non-claim response sent",
                        "human_reviewer": "streamlit_user",
                        "human_review_timestamp": datetime.now().isoformat()
                    }
                    save_claim(completed_state, decision="NON_CLAIM", notes="Non-claim response sent")
                    email_id_value = state.get("email_id")
                    if email_id_value:
                        if not any(c.get("email_id") == email_id_value for c in st.session_state.processed_claims):
                            st.session_state.processed_claims.append({
                                "email_id": email_id_value,
                                "decision": "NON_CLAIM",
                                "timestamp": datetime.now().isoformat()
                            })
                        st.session_state.claim_decisions[email_id_value] = "NON_CLAIM"
                    st.session_state.non_claim_drafts.pop(email_id, None)
                    st.session_state.current_state = None
                    st.session_state.workflow_stage = "select"
                    st.success("Response sent.")
                    st.rerun()
        return
    
    # Header
    st.markdown(f'<p class="main-header">Review Claim: {state.get("claim_id", "New Claim")}</p>', unsafe_allow_html=True)
    
    analysis = state.get("analysis", {})
    extracted = state.get("extracted_fields", {})
    
    # Recommendation Banner
    recommendation = analysis.get("recommendation", "N/A")
    confidence = analysis.get("confidence", 0)
    
    rec_color = "#DCFCE7" if recommendation == "APPROVE" else "#FEE2E2" if recommendation == "REJECT" else "#DBEAFE"
    rec_text_color = "#166534" if recommendation == "APPROVE" else "#991B1B" if recommendation == "REJECT" else "#1E40AF"
    
    st.markdown(f"""
    <div style="background-color: {rec_color}; padding: 1.5rem; border-radius: 12px; border: 1px solid {rec_text_color}40; margin-bottom: 2rem; display: flex; align-items: center; gap: 1rem;">
        <div style="font-size: 2rem;">{'APPROVE' if recommendation == 'APPROVE' else 'REJECT' if recommendation == 'REJECT' else 'INFO'}</div>
        <div>
            <div style="font-weight: 700; color: {rec_text_color}; font-size: 1.1rem;">SYSTEM RECOMMENDATION: {recommendation}</div>
            <div style="color: {rec_text_color}; opacity: 0.9;">Confidence Score: {confidence:.0%}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Main Content Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Executive Summary", "Evidence & Policy", "Customer Email", "Full Report"])
    
    with tab1:
        # Row 1: Profile & Issue
        r1_c1, r1_c2 = st.columns(2)
        with r1_c1:
            st.markdown("### Profile")
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border: 1px solid #E2E8F0; height: 100%;">
                <div><strong>Customer:</strong> {extracted.get('customer_name', 'N/A')}</div>
                <div><strong>Email:</strong> {extracted.get('customer_email', 'N/A')}</div>
                <div><strong>Product:</strong> {state.get('product_name', 'N/A')}</div>
                <div><strong>Purchased:</strong> {extracted.get('purchase_date', 'N/A')}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with r1_c2:
            st.markdown("### Issue")
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border: 1px solid #E2E8F0; height: 100%;">
                {extracted.get("issue_description", "No description provided.")}
            </div>
            """, unsafe_allow_html=True)

        st.markdown("") # Spacer

        with st.expander("View Reason & Logic", expanded=True):
            st.markdown(f"**Reasoning:** {analysis.get('reasoning', 'N/A')}")
            valid = analysis.get("warranty_window_valid")
            if valid is True:
                st.success(f"Valid Warranty ({analysis.get('warranty_window_details', '')})")
            elif valid is False:
                st.error(f"Warranty Expired ({analysis.get('warranty_window_details', '')})")
                
        st.markdown("### Decision")
        
        with st.form("decision_form"):
            notes = st.text_area("Reviewer Notes (Internal Only)", placeholder="Add context for this decision...")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                submitted_approve = st.form_submit_button("✅ Approve", type="primary", use_container_width=True)
            with c2:
                submitted_reject = st.form_submit_button("❌ Reject", type="secondary", use_container_width=True)
            with c3:
                submitted_info = st.form_submit_button("❓ Needs Info", type="secondary", use_container_width=True)
                
            if submitted_approve:
                resume_workflow_with_decision("APPROVE", notes)
                st.rerun()
            if submitted_reject:
                resume_workflow_with_decision("REJECT", notes)
                st.rerun()
            if submitted_info:
                resume_workflow_with_decision("NEED_INFO", notes)
                st.rerun()

    with tab2:
        st.markdown("### Evidence & Policy")
        
        col_ev_1, col_ev_2 = st.columns(2)
        with col_ev_1:
            st.markdown("#### Extraction Facts")
            facts = analysis.get("facts", [])
            if facts:
                for fact in facts:
                    st.markdown(f"- {fact}")
            else:
                st.caption("No facts recorded.")
                
            st.markdown("#### Assumptions")
            assumptions = analysis.get("assumptions", [])
            if assumptions:
                for assumption in assumptions:
                    st.markdown(f"- {assumption}")
            else:
                st.caption("No assumptions recorded.")

        with col_ev_2:
            st.markdown("#### Policy Details")
            st.markdown(f"**Policy ID:** `{state.get('policy_id', 'N/A')}`")
            st.markdown(f"**Reason:** {state.get('policy_selection_reason', 'N/A')}")
            
            exclusions = analysis.get("exclusions_triggered", [])
            if exclusions:
                st.warning("⚠️ Exclusions Triggered")
                for exclusion in exclusions:
                    st.markdown(f"- {exclusion}")

        st.markdown("---")
        excerpts = state.get("policy_excerpts", [])
        if excerpts:
            st.markdown("#### Relevant Policy Excerpts")
            for idx, excerpt in enumerate(excerpts, 1):
                title = excerpt.get("section_name") or f"Excerpt {idx}"
                with st.expander(title):
                    st.markdown(excerpt.get("content", ""))
                    st.caption(f"Source: {excerpt.get('policy_id')} | Score: {excerpt.get('distance', 'N/A')}")

    with tab3:
        st.markdown("### Original Email")
        st.markdown(f"**From:** {state.get('email_from', 'N/A')} | **Date:** {state.get('email_date', 'N/A')}")
        st.markdown(f"**Subject:** {state.get('email_subject', 'N/A')}")
        st.text_area("Body", value=state.get("email_body", ""), height=400, disabled=True)

    with tab4:
        st.markdown("### Full Audit Report")
        st.info("Complete markdown packet for archival purposes.")
        
        packet_content = state.get("review_packet_content")
        packet_path = state.get("review_packet_path")
        
        if packet_content:
            st.markdown(packet_content)
            if packet_path and Path(packet_path).exists():
                 with open(packet_path, "r", encoding="utf-8") as f:
                    st.download_button("Download Full Report", f.read(), file_name=Path(packet_path).name, mime="text/markdown", use_container_width=True)
        else:
            st.info("No report generated.")

    if st.button("Back to List", use_container_width=True):
        st.session_state.workflow_stage = "select"
        st.session_state.current_state = None
        st.rerun()





def complete_workflow_and_send():
    """Resume from email_gate to completion."""
    try:
        email_id = st.session_state.current_email
        workflow = st.session_state.workflow
        config = {"configurable": {"thread_id": email_id}}
        
        # Update state with 'email_sent' flag
        workflow.update_state(
            config,
            {"email_sent": True}
        )
        
        last_state = None
        with st.spinner("Sending email and finalizing..."):
            for event in workflow.stream(None, config):
                 for node_name, node_output in event.items():
                    print(f"[DEBUG] Finalizing - Completed node: {node_name}")
                    if not node_name.startswith("__"):
                        last_state = node_output
        
        # Get final completed state
        try:
            snapshot = workflow.get_state(config)
            if snapshot and hasattr(snapshot, 'values') and snapshot.values:
                final_state = dict(snapshot.values)
            else:
                final_state = last_state
        except:
             final_state = last_state

        st.session_state.current_state = final_state
        st.session_state.workflow_stage = "complete"
        
        # NOW we save to database as processed
        decision = final_state.get("human_decision", "UNKNOWN")
        notes = final_state.get("human_notes", "")
        save_claim(final_state, decision, notes)
        
        st.session_state.processed_claims.append({
            "email_id": email_id,
            "decision": decision,
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.claim_decisions[email_id] = decision
        if email_id in st.session_state.pending_dispatch:
            st.session_state.pending_dispatch.remove(email_id)
        return True

    except Exception as e:
        st.error(f"Error finalizing workflow: {e}")
        return False


def render_email_dispatch():
    """Render the email dispatch screen (Ready to Send)."""
    state = st.session_state.current_state
    
    if state is None:
        st.error("No claim state found")
        if st.button("Back to Inbox", use_container_width=True):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return
        
    decision = state.get("human_decision", "N/A")
    claim_id = state.get("claim_id", "UNKNOWN")
    
    # 1. Status Banner
    if decision == "APPROVE":
        st.markdown('<div style="background-color: #F0FDF4; padding: 1.5rem; border-radius: 12px; border: 1px solid #DCFCE7; margin-bottom: 2rem; color: #166534; font-weight: 600; text-align: center; font-size: 1.2rem;">✅ CLAIM APPROVED - PENDING EMAIL DISPATCH</div>', unsafe_allow_html=True)
    elif decision == "REJECT":
        st.markdown('<div style="background-color: #FEF2F2; padding: 1.5rem; border-radius: 12px; border: 1px solid #FECACA; margin-bottom: 2rem; color: #991B1B; font-weight: 600; text-align: center; font-size: 1.2rem;">🛑 CLAIM REJECTED - PENDING EMAIL DISPATCH</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="background-color: #F1F5F9; padding: 1.5rem; border-radius: 12px; border: 1px solid #E2E8F0; margin-bottom: 2rem; color: #475569; font-weight: 600; text-align: center; font-size: 1.2rem;">ℹ️ DECISION: {decision} - PENDING DISPATCH</div>', unsafe_allow_html=True)
    
    label_path = state.get("return_label_path")
    
    st.write("Review the generated email below. For approved claims, generate and attach the return label before sending.")
    st.markdown("---")
    
    # 2. Email Editor
    st.markdown("### 1. Review Customer Email")
    
    # Attachment Visual (Shows status inside the editor context)
    if label_path and Path(label_path).exists():
        st.markdown(f"""
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 0.5rem 1rem; border-radius: 6px; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; color: #475569;">
            <span style="font-size: 1.2rem;">📎</span>
            <span style="font-weight: 500;">Attachment:</span>
            <span style="font-family: monospace;">{Path(label_path).name}</span>
            <span style="background-color: #DCFCE7; color: #166534; font-size: 0.75rem; padding: 0.1rem 0.5rem; border-radius: 99px; font-weight: 600;">ATTACHED</span>
        </div>
        """, unsafe_allow_html=True)
    elif decision == "APPROVE":
        st.markdown(f"""
        <div style="background-color: #FFFBEB; border: 1px solid #FCD34D; padding: 0.5rem 1rem; border-radius: 6px; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; color: #92400E;">
            <span style="font-size: 1.2rem;">⚠️</span>
            <span style="font-weight: 500;">Missing Attachment:</span>
            <span>Return Label requires generation (see below)</span>
        </div>
        """, unsafe_allow_html=True)

    email_path = state.get("customer_email_path")
    email_content = state.get("customer_email_draft", "")
    
    if email_path and Path(email_path).exists():
        try:
             with open(email_path, "r", encoding="utf-8") as f:
                 email_content = f.read()
        except:
             pass
    
    # Auto-append attachment footer if label exists
    if label_path and Path(label_path).exists():
        # Check if we already added it to avoid duplicates
        attachment_notice = "ATTACHMENT: Return Shipping Label"
        if attachment_notice not in email_content:
            email_content += f"\n\n---\n{attachment_notice}\n- File: {Path(label_path).name}\nPlease print this label and attach it to your return package."

             
    edited_email = st.text_area(
        "Edit Message Body:",
        value=email_content,
        height=400,
        key=f"dispatch_edit_{claim_id}"
    )
    
    if email_path:
         with open(email_path, "w", encoding="utf-8") as f:
             f.write(edited_email)
    
    st.markdown("---")

    # 3. Artifacts / Attachments Section (Moved Below)
    if decision == "APPROVE":
        st.markdown("### 2. Attachments")
        
        col_art_1, col_art_2 = st.columns([1, 2])
        
        with col_art_1:
             st.write("**Return Shipping Label**")
             st.caption("Required for approval")
        
        with col_art_2:
             if label_path and Path(label_path).exists():
                 st.success("✅ Return Label Generated & Attached")
                 st.caption(f"File: `{Path(label_path).name}`")
                 
                 # Preview Button
                 if "show_dispatch_preview" not in st.session_state:
                     st.session_state.show_dispatch_preview = False
                 
                 if st.button("👁️ Preview Label" if not st.session_state.show_dispatch_preview else "❌ Close Preview", key="btn_preview_toggle"):
                     st.session_state.show_dispatch_preview = not st.session_state.show_dispatch_preview
                     st.rerun()
                 
                 if st.session_state.show_dispatch_preview:
                     try:
                         with open(label_path, "rb") as f:
                             base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                         pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="400" style="border-radius: 8px; border: 1px solid #E2E8F0;"></iframe>'
                         st.markdown(pdf_display, unsafe_allow_html=True)
                     except Exception as e:
                         st.error(f"Error displaying PDF: {e}")
             else:
                 st.warning("⚠️ Label Not Generated")
                 if st.button("🏷️ Generate & Attach Label", type="primary", key="gen_label_dispatch"):
                     from app.nodes.return_label import generate_return_label
                     with st.spinner("Generating PDF label..."):
                         updated_state = generate_return_label(st.session_state.current_state)
                         st.session_state.current_state = updated_state
                         
                         if st.session_state.workflow and st.session_state.current_email:
                             try:
                                 conf = {"configurable": {"thread_id": st.session_state.current_email}}
                                 st.session_state.workflow.update_state(
                                     conf, 
                                     {"return_label_path": updated_state.get("return_label_path")}
                                 )
                             except Exception as e:
                                 print(f"Error updating checkpoint: {e}")
                         st.rerun()
        st.markdown("---")

    # 4. Action Buttons
    c1, c2, c3 = st.columns([1, 1.5, 2.5])
    with c1:
        # Validation
        can_send_email = True
        label_exists = state.get("return_label_path") and Path(state.get("return_label_path")).exists()
        
        if decision == "APPROVE" and not label_exists:
            can_send_email = False
            
        if can_send_email:
            if st.button("🚀 Confirm & Send", type="primary", use_container_width=True):
                 if complete_workflow_and_send():
                     st.balloons()
                     st.rerun()
        else:
             st.button("🚫 No Label", disabled=True, use_container_width=True, help="You must generate a return label before confirming approval.")
    
    with c2:
        if st.button("🔄 Revise Decision", use_container_width=True):
            # Remove from pending dispatch and go back to review
            email_id = st.session_state.current_email
            if email_id in st.session_state.pending_dispatch:
                st.session_state.pending_dispatch.remove(email_id)
            st.session_state.workflow_stage = "review"
            st.rerun()

    with c3:
        if st.button("Cancel & Return to Inbox", use_container_width=True):
             # Remove from pending dispatch so it returns to 'Process' state instead of 'Resume'
             email_id = st.session_state.current_email
             if email_id in st.session_state.pending_dispatch:
                 st.session_state.pending_dispatch.remove(email_id)
             st.session_state.workflow_stage = "select"
             st.rerun()



def render_completion():
    """Render completion screen."""
    state = st.session_state.current_state
    
    if state is None:
        st.error("No claim state found")
        if st.button("Back to Inbox", use_container_width=True):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return
    
    # Handle tuple state (sometimes returns (state, config))
    if isinstance(state, tuple):
        state = state[0] if state else {}
    
    decision = state.get("human_decision", "N/A")
    claim_id = state.get("claim_id", "UNKNOWN")
    
    # Status Banner
    st.markdown("### Claim Processed Successfully")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.markdown(f"**Decision:**")
        if decision == "APPROVE":
            st.markdown('<span class="status-badge status-approve">APPROVED</span>', unsafe_allow_html=True)
        elif decision == "REJECT":
            st.markdown('<span class="status-badge status-reject">REJECTED</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="status-badge status-info">{decision}</span>', unsafe_allow_html=True)
            
    with col2:
        st.markdown("**Claim ID:**")
        st.markdown(f"`{claim_id}`")
        
    with col3:
        st.markdown("**Processed At:**")
        st.markdown(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    st.markdown("---")
    
    # Email Section (Read Only Summary)
    st.markdown("### Customer Communication")
    
    extracted = state.get("extracted_fields", {})
    customer_email = extracted.get("customer_email", "unknown@email.com")
    
    st.success(f"✅ Email successfully sent to **{customer_email}**")
    
    with st.expander("View Sent Message", expanded=True):
        email_content = state.get("customer_email_draft", "No email content draft found.")
        email_path = state.get("customer_email_path")
        
        # Try to read the actual FINAL file if possible (which has the label appended)
        if email_path and Path(email_path).exists():
            try:
                with open(email_path, "r", encoding="utf-8") as f:
                    email_content = f.read()
            except:
                pass
        
        if not email_content or email_content == "No content":
             st.info("Email content preview unavailable.")
        else:
             st.text_area("Final Email Message", value=email_content, height=400, disabled=True)
    
    st.markdown("---")
    
    # Generated Artifacts
    st.markdown("### Generated Artifacts")
    
    ac1, ac2 = st.columns(2)
    
    with ac1:
        label_path = state.get("return_label_path")
        if label_path and Path(label_path).exists():
            st.markdown(f"""
            <div style="background-color: #F0FDF4; padding: 1rem; border-radius: 8px; border: 1px solid #DCFCE7;">
                <h4 style="margin:0; color: #166534;">✅ Shipping Label Attached</h4>
                <p style="color:#166534; font-size:0.9rem; margin: 0.5rem 0 0 0;">(Sent with email)</p>
            </div>
            """, unsafe_allow_html=True)
            with open(label_path, "rb") as f:
                st.download_button(
                    "📥 Download PDF",
                    f.read(),
                    file_name=Path(label_path).name,
                    use_container_width=True
                )
        elif decision == "APPROVE":
             st.warning("No label found")

    with ac2:
        packet_path = state.get("review_packet_path")
        if packet_path and Path(packet_path).exists():
            st.markdown(f"""
            <div style="background-color: white; padding: 1rem; border-radius: 8px; border: 1px solid #E2E8F0;">
                <h4 style="margin:0;">Review Packet</h4>
                <p style="color:#64748B; font-size:0.9rem;">Audit trail document (MD)</p>
            </div>
            """, unsafe_allow_html=True)
            try:
                with open(packet_path, "r", encoding="utf-8") as f:
                    st.download_button(
                        "📥 Download Packet",
                        f.read(),
                        file_name=Path(packet_path).name,
                        mime="text/markdown",
                        use_container_width=True
                    )
            except:
                pass

    st.markdown("---")
    
    if st.button("Process Next Claim", use_container_width=True):
        st.session_state.workflow_stage = "select"
        st.session_state.current_state = None
        st.session_state.current_email = None
        st.rerun()



def render_claim_detail():
    """Render detailed view of a processed claim from database."""
    email_id = st.session_state.get("view_claim_id")
    
    if not email_id:
        st.error("No claim selected")
        if st.button("Back to List"):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return
    
    claim = get_claim_by_email_id(email_id)
    
    if not claim:
        st.error(f"Claim {email_id} not found in database")
        if st.button("Back to List"):
            st.session_state.workflow_stage = "select"
            st.rerun()
        return
    
    # Header area
    st.markdown(f'<p class="main-header">Claim Record: {email_id}</p>', unsafe_allow_html=True)
    
    # Decision Banner
    decision = claim.get("decision", "N/A")
    rec_color = "#DCFCE7" if decision == "APPROVE" else "#FEE2E2" if decision == "REJECT" else "#DBEAFE"
    rec_text_color = "#166534" if decision == "APPROVE" else "#991B1B" if decision == "REJECT" else "#1E40AF"
    
    st.markdown(f"""
    <div style="background-color: {rec_color}; padding: 1.5rem; border-radius: 12px; border: 1px solid {rec_text_color}40; margin-bottom: 2rem; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 1rem;">
            <div style="font-size: 2rem;">{'APPROVE' if decision == 'APPROVE' else 'REJECT' if decision == 'REJECT' else 'INFO'}</div>
            <div>
                <div style="font-weight: 700; color: {rec_text_color}; font-size: 1.1rem;">DECISION: {decision}</div>
                <div style="color: {rec_text_color}; opacity: 0.9;">Processed on {claim.get('timestamp', '')[:10]}</div>
            </div>
        </div>
        <div style="font-size: 0.9rem; color: {rec_text_color}; font-weight: 600;">FINAL</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["Customer and Product", "Analysis Audit", "Communication", "Raw Data"])
    
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Customer Information")
            st.info(f"""
            **Name:** {claim.get('customer_name', 'N/A')}  
            **Email:** {claim.get('customer_email', 'N/A')}  
            **Address:** {claim.get('customer_address', 'N/A')}
            """)
            
            st.markdown("### Product Details")
            st.success(f"""
            **Product:** {claim.get('product_name', 'N/A')}  
            **Serial:** {claim.get('product_serial', 'N/A')}  
            **Purchase Date:** {claim.get('purchase_date', 'N/A')}
            """)
            
        with col2:
            st.markdown("### Issue Reported")
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border: 1px solid #E2E8F0; min-height: 100px;">
                {claim.get("issue_description", "No description provided.")}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### Warranty Status")
            if claim.get("warranty_valid"):
                st.success(f"Valid: {claim.get('warranty_details', '')}")
            else:
                st.error(f"Expired: {claim.get('warranty_details', '')}")
    
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### AI Recommendation")
            rec = claim.get("recommendation", "N/A")
            conf = claim.get("confidence", 0)
            
            st.markdown(f"""
            <div style="padding: 1rem; background-color: white; border-radius: 8px; border: 1px solid #E2E8F0; margin-bottom: 1rem;">
                <strong>Recommendation:</strong> {rec}<br>
                <strong>Confidence:</strong> {conf:.0%}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### Reasoning")
            st.info(claim.get("reasoning", "No reasoning provided"))
            
        with col2:
            st.markdown("### Risk Assessment")
            exclusions = claim.get("exclusions", [])
            assumptions = claim.get("assumptions", [])
            
            if not exclusions and not assumptions:
                st.success("No risks identified.")
            
            if exclusions:
                for exc in exclusions:
                    st.error(f"Exclusion: {exc}")
            
            if assumptions:
                for assumption in assumptions:
                    st.warning(f"Assumption: {assumption}")
    
    with tab3:
        st.markdown("### Email Sent to Customer")
        email_draft = claim.get("email_draft", "")
        if email_draft:
            st.markdown(f'<div class="email-preview">{email_draft}</div>', unsafe_allow_html=True)
        else:
            st.info("No email draft available")

    with tab4:
        st.json(claim)
    
    st.markdown("---")
    if st.button("Back to Dashboard", use_container_width=True):
        st.session_state.workflow_stage = "select"
        st.rerun()
        
        # Download files
        st.markdown("### Generated Files")
        col1, col2 = st.columns(2)
        
        with col1:
            label_path = claim.get("label_path")
            if label_path and Path(label_path).exists():
                st.success("Return Label")
                with open(label_path, "rb") as f:
                    st.download_button("Download Label PDF", f.read(), 
                                      file_name=Path(label_path).name)
        
        with col2:
            packet_path = claim.get("packet_path")
            if packet_path and Path(packet_path).exists():
                st.success("Review Packet")
                try:
                    with open(packet_path, "r", encoding="utf-8") as f:
                        st.download_button("Download Review Packet", f.read(),
                                          file_name=Path(packet_path).name, mime="text/markdown")
                except:
                    pass
        
        if claim.get("notes"):
            st.markdown("### Reviewer Notes")
            st.info(claim.get("notes"))
    
    st.markdown("---")
    
    if st.button("Back to Inbox", use_container_width=True):
        st.session_state.workflow_stage = "select"
        st.session_state.view_claim_id = None
        st.rerun()


def main():
    """Main Streamlit app."""
    # Load emails first so they are available for sidebar statistics if needed
    if "emails" not in st.session_state:
        st.session_state.emails = load_inbox_emails()
        
    render_sidebar()
    
    # Check LLM availability
    try:
        from app.llm import get_llm
        llm_config = st.session_state.get("llm_active_config", {"provider": "ollama", "api_key": "", "model": ""})
        force_new = st.session_state.llm_force_refresh
        st.session_state.llm_force_refresh = False
        llm = get_llm(
            provider=llm_config.get("provider") or "ollama",
            api_key=llm_config.get("api_key") or None,
            model=llm_config.get("model") or None,
            force_new=force_new
        )
        st.session_state.llm_available = True
        st.session_state.llm_error = ""
        provider_labels = {
            "ollama": "Ollama",
            "groq": "Groq",
            "gemini": "Gemini",
            "openai": "OpenAI",
            "auto": "Auto"
        }
        provider_label = provider_labels.get(llm_config.get("provider"), "LLM")
        with st.sidebar:
            st.caption(f"Using: {provider_label}/{llm.model_name}")
    except Exception as e:
        st.session_state.llm_available = False
        st.session_state.llm_error = str(e)
        with st.sidebar:
            st.error(f"⚠️ AI Offline")
            st.caption(f"Error: {e}")
            st.warning("Running in View-Only Mode")
        # st.stop() removed to allow view-only access
    
    # Route to appropriate view
    stage = st.session_state.workflow_stage
    
    if stage == "select":
        render_email_selection()
    elif stage == "processing":
        st.info("Processing claim...")
    elif stage == "review":
        render_review_interface()
    elif stage == "claim_history":
        render_claim_history()
    elif stage == "dispatch":
        render_email_dispatch()
    elif stage == "complete":
        render_completion()
    elif stage == "view_claim":
        render_claim_detail()


if __name__ == "__main__":
    main()
