import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from app.graph import get_workflow
from app.state import create_initial_state

# Suppress logging during evaluation
logging.getLogger("httpx").setLevel(logging.WARNING)

TEST_FILE = Path("data/testset.jsonl")


def load_test_cases(path: Path):
    if not path.exists():
        print(f"Error: {path} not found.")
        return []
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def format_confusion(matrix: Counter, labels, title: str):
    print(f"\n{title}")
    header = "exp\\act".ljust(12) + "".join(label.ljust(12) for label in labels)
    print(header)
    print("-" * len(header))
    for exp in labels:
        row = exp.ljust(12)
        for act in labels:
            row += str(matrix.get((exp, act), 0)).ljust(12)
        print(row)


def evaluate(limit=None, ids=None):
    print("Initializing Workflow Validation...")
    workflow = get_workflow()

    test_data = load_test_cases(TEST_FILE)
    if ids:
        id_set = set(ids)
        test_data = [c for c in test_data if c.get("email_id") in id_set]
    if limit:
        test_data = test_data[:limit]

    if not test_data:
        print("No test cases to evaluate.")
        return

    results = []
    triage_confusion = Counter()
    decision_confusion = Counter()
    triage_correct = 0
    decision_correct = 0
    decision_total = 0
    coverage_count = 0
    confidence_values = []

    print(f"Loaded {len(test_data)} test cases.\n")
    print(f"{'ID':<12} {'TRIAGE':<10} {'EXP_TRIAGE':<10} {'DECISION':<12} {'EXP_DECISION':<12} {'RESULT'}")
    print("-" * 75)

    for case in test_data:
        email_id = case["email_id"]
        exp_triage = case.get("expected_triage", "UNKNOWN")
        exp_outcome = case.get("expected_outcome")

        # Init state
        initial_state = create_initial_state(email_id)

        # Unique thread for each test
        config = {"configurable": {"thread_id": f"eval_{email_id}"}}

        try:
            # Run workflow
            final_state = workflow.invoke(initial_state, config)

            # Extract results
            act_triage = final_state.get("triage_result", "UNKNOWN")
            analysis = final_state.get("analysis", {}) or {}
            act_outcome = analysis.get("recommendation") or "-"
            if act_triage in ["SPAM", "NON_CLAIM"]:
                act_outcome = "-"

            exp_outcome_label = exp_outcome if exp_outcome else "-"

            triage_ok = (act_triage == exp_triage)
            outcome_ok = True
            if exp_triage == "CLAIM":
                decision_total += 1
                outcome_ok = (act_outcome == exp_outcome_label)
                decision_confusion[(exp_outcome_label, act_outcome)] += 1
                if act_outcome in ["APPROVE", "REJECT"]:
                    coverage_count += 1
                if analysis.get("confidence") is not None:
                    confidence_values.append(float(analysis.get("confidence", 0)))

            triage_confusion[(exp_triage, act_triage)] += 1
            if triage_ok:
                triage_correct += 1
            if outcome_ok and exp_triage == "CLAIM":
                decision_correct += 1

            passed = triage_ok and outcome_ok
            status = "PASS" if passed else "FAIL"

            print(f"{email_id:<12} {act_triage:<10} {exp_triage:<10} {act_outcome:<12} {exp_outcome_label:<12} {status}")

            results.append({
                "id": email_id,
                "passed": passed,
                "triage_ok": triage_ok,
                "outcome_ok": outcome_ok,
                "reason": case.get("reason", "")
            })

        except Exception as e:
            print(f"{email_id:<12} ERROR: {e}")
            results.append({"id": email_id, "passed": False, "error": str(e)})

    # Summary
    print("\n" + "=" * 30)
    passed_count = sum(1 for r in results if r.get("passed"))
    total = len(results)
    triage_acc = triage_correct / total if total else 0
    decision_acc = decision_correct / decision_total if decision_total else 0
    coverage = coverage_count / decision_total if decision_total else 0
    avg_conf = sum(confidence_values) / len(confidence_values) if confidence_values else 0

    print(f"SCORE: {passed_count}/{total} ({passed_count/total:.1%})")
    print(f"TRIAGE ACCURACY: {triage_acc:.1%}")
    print(f"DECISION ACCURACY (claims only): {decision_acc:.1%}")
    print(f"COVERAGE (approve/reject): {coverage:.1%}")
    print(f"AVG CONFIDENCE (claims only): {avg_conf:.2f}")
    print("=" * 30)

    format_confusion(
        triage_confusion,
        ["CLAIM", "NON_CLAIM", "SPAM", "UNKNOWN"],
        "Triage Confusion Matrix"
    )

    format_confusion(
        decision_confusion,
        ["APPROVE", "REJECT", "NEED_INFO", "-"],
        "Decision Confusion Matrix (Claims)"
    )

    if passed_count < total:
        print("\nFailures:")
        for r in results:
            if not r.get("passed"):
                reason = r.get("error", "Mismatch")
                print(f"- {r['id']}: {reason}")


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate warranty agent on testset.jsonl")
    parser.add_argument("--limit", type=int, help="Limit number of test cases")
    parser.add_argument("--ids", type=str, help="Comma-separated email IDs to evaluate")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    id_list = [s.strip() for s in args.ids.split(",")] if args.ids else None
    evaluate(limit=args.limit, ids=id_list)
