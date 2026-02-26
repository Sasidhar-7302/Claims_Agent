"""
Main entry point for the Warranty Claims Agent.

This module provides CLI functionality for testing and running the workflow.
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.state import create_initial_state
from app.graph import compile_workflow
from app.database import save_claim, get_all_processed_email_ids
from app.demo_data import generate_demo_emails, remove_generated_demo_emails


# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"
OUTBOX_DIR = BASE_DIR / "outbox"


def list_inbox_emails():
    """List all emails in the inbox directory."""
    emails = []
    for f in INBOX_DIR.glob("*.json"):
        with open(f, "r") as file:
            data = json.load(file)
            emails.append({
                "file": f.name,
                "email_id": data.get("email_id", f.stem),
                "subject": data.get("subject", "No subject"),
                "from": data.get("from", "Unknown")
            })
    return emails


def watch_inbox(auto_approve: bool = False, interval: int = 10):
    """Continuously poll inbox and process new emails."""
    processed = set(get_all_processed_email_ids())
    print("Watching inbox for new claims. Press Ctrl+C to stop.")
    try:
        while True:
            emails = list_inbox_emails()
            new_items = [e for e in emails if e["email_id"] not in processed]
            if not new_items:
                time.sleep(interval)
                continue

            for item in new_items:
                email_id = item["email_id"]
                state = process_single_claim(email_id, auto_approve=auto_approve)
                triage_result = state.get("triage_result") if state else None
                if state and (state.get("workflow_status") == "COMPLETED" or triage_result in ["SPAM", "NON_CLAIM"]):
                    processed.add(email_id)
                else:
                    print(f"Skipping {email_id} due to incomplete workflow.")
    except KeyboardInterrupt:
        print("\nWatcher stopped.")


def process_single_claim(email_id: str, auto_approve: bool = False):
    """
    Process a single warranty claim.
    
    Args:
        email_id: The email ID to process
        auto_approve: If True, auto-approve without human review (for testing)
    
    Returns:
        Final state after processing
    """
    print(f"\n{'='*60}")
    print(f"Processing claim: {email_id}")
    print(f"{'='*60}\n")
    
    # Create initial state
    initial_state = create_initial_state(email_id)
    
    # Get compiled workflow
    workflow = compile_workflow()
    
    # Configuration for checkpointing
    config = {"configurable": {"thread_id": email_id}}
    
    # Run workflow until human review interrupt
    print("Running workflow until human review...")
    state = None
    
    for event in workflow.stream(initial_state, config):
        for node_name, node_output in event.items():
            print(f"  Completed: {node_name}")
            if node_name.startswith("__"):
                continue
            if isinstance(node_output, tuple):
                node_output = node_output[0]
            state = node_output
    
    # Check if we're waiting for human review
    current_state = workflow.get_state(config)
    
    if current_state.next and "human_review" in current_state.next:
        print("\n" + "="*60)
        print("WORKFLOW PAUSED - Awaiting Human Review")
        print("="*60)
        
        # Display analysis summary
        if isinstance(state, tuple):
            state = state[0]
        analysis = state.get("analysis", {})
        print(f"\nRecommendation: {analysis.get('recommendation', 'N/A')}")
        print(f"Confidence: {analysis.get('confidence', 0):.0%}")
        print(f"\nReview packet: {state.get('review_packet_path', 'N/A')}")
        
        if auto_approve:
            print("\n[AUTO-APPROVE MODE] Approving claim...")
            human_decision = analysis.get('recommendation', 'APPROVE')
        else:
            print("\nEnter decision (APPROVE/REJECT/NEED_INFO): ", end="")
            human_decision = input().strip().upper()
            if human_decision not in ["APPROVE", "REJECT", "NEED_INFO"]:
                human_decision = "NEED_INFO"
        
        # Resume workflow with human decision
        resume_state = {
            "human_decision": human_decision,
            "human_notes": "CLI review",
            "human_reviewer": "cli_user",
            "human_review_timestamp": datetime.now().isoformat()
        }
        
        print(f"\nResuming workflow with decision: {human_decision}")
        workflow.update_state(config, resume_state)
        
        for event in workflow.stream(None, config):
            for node_name, node_output in event.items():
                print(f"  Completed: {node_name}")
                if node_name.startswith("__"):
                    continue
                if isinstance(node_output, tuple):
                    node_output = node_output[0]
                state = node_output
        snapshot = workflow.get_state(config)
        if snapshot and snapshot.next and "email_gate" in snapshot.next:
            print("\n[CLI] Auto-sending email and finalizing...")
            workflow.update_state(config, {"email_sent": True})
            for event in workflow.stream(None, config):
                for node_name, node_output in event.items():
                    print(f"  Completed: {node_name}")
                    if node_name.startswith("__"):
                        continue
                    if isinstance(node_output, tuple):
                        node_output = node_output[0]
                    state = node_output
    
    print("\n" + "="*60)
    print("WORKFLOW COMPLETED")
    print("="*60)
    
    print(f"\nFinal status: {state.get('workflow_status', 'N/A')}")
    print(f"Customer email: {state.get('customer_email_path', 'N/A')}")
    print(f"Return label: {state.get('return_label_path', 'N/A')}")

    if isinstance(state, tuple):
        state = state[0]
    triage_result = state.get("triage_result")
    if state.get("workflow_status") == "COMPLETED" or triage_result in ["SPAM", "NON_CLAIM"]:
        try:
            decision = state.get("human_decision") or triage_result or ""
            save_claim(state, decision, notes="CLI review")
        except Exception as e:
            print(f"[WARN] Could not save claim to database: {e}")
    
    return state


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Warranty Claims Agent CLI"
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all emails in inbox"
    )
    
    parser.add_argument(
        "--process", "-p",
        type=str,
        help="Process a specific email by ID"
    )
    
    parser.add_argument(
        "--auto-approve", "-a",
        action="store_true",
        help="Auto-approve claims (for testing)"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test mode with first email"
    )
    
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch inbox and process new emails continuously"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Polling interval in seconds for --watch"
    )

    parser.add_argument(
        "--generate-demo",
        type=int,
        default=0,
        help="Generate N additional demo claim emails (also creates non-claim/spam variants)."
    )

    parser.add_argument(
        "--clear-generated-demo",
        action="store_true",
        help="Remove generated demo emails (demo_gen_*.json)."
    )
    
    args = parser.parse_args()
    
    if args.clear_generated_demo:
        deleted = remove_generated_demo_emails(INBOX_DIR)
        print(f"Removed {deleted} generated demo emails from {INBOX_DIR}")
    elif args.generate_demo > 0:
        claim_count = max(args.generate_demo, 1)
        non_claim_count = max(claim_count // 3, 1)
        spam_count = max(claim_count // 3, 1)
        created = generate_demo_emails(
            inbox_dir=INBOX_DIR,
            claim_count=claim_count,
            non_claim_count=non_claim_count,
            spam_count=spam_count,
        )
        print(f"Generated {len(created)} demo emails in {INBOX_DIR}")
    elif args.watch:
        watch_inbox(auto_approve=args.auto_approve, interval=args.interval)
    elif args.list:
        print("\nEmails in inbox:")
        print("-" * 60)
        for email in list_inbox_emails():
            print(f"  {email['email_id']}: {email['subject']}")
            print(f"    From: {email['from']}")
        print()
        
    elif args.process:
        process_single_claim(args.process, args.auto_approve)
        
    elif args.test:
        emails = list_inbox_emails()
        if emails:
            process_single_claim(emails[0]["email_id"], auto_approve=True)
        else:
            print("No emails found in inbox")
            
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
