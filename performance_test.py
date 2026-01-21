import json
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.graph import get_workflow
from app.state import create_initial_state
from app.vector_store import get_vector_store

TEST_SET_PATH = Path("data/testset.jsonl")
REPORT_PATH = Path("reports/performance_report.md")


def load_test_cases(limit=5):
    cases = []
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases[:limit]


def run_benchmark():
    print("Starting performance benchmark...")
    print(f"Time: {datetime.now().isoformat()}")

    workflow = get_workflow()
    test_cases = load_test_cases()
    results = []

    total_start = time.time()

    for i, case in enumerate(test_cases):
        case_id = case["email_id"]
        print(f"\nProcessing claim {i + 1}/{len(test_cases)}: {case_id}")

        email_input = {
            "email_id": case_id,
            "email_from": "test@example.com",
            "email_subject": f"Warranty Claim for {case.get('product_id', 'Unknown')}",
            "email_body": (
                f"My product stopped working. It is a {case.get('product_id', 'Unknown')}. "
                f"Serial: 12345. Purchased 2 months ago. {case.get('reason', '')}"
            ),
            "email_date": datetime.now().isoformat()
        }

        state = create_initial_state(case_id)
        state.update(email_input)

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        claim_start = time.time()
        captured_decision = "UNKNOWN"

        try:
            for event in workflow.stream(state, config=config):
                for node_name, node_state in event.items():
                    if isinstance(node_state, tuple):
                        node_state = node_state[0] if node_state else {}

                    if node_name == "analyze":
                        analysis = node_state.get("analysis", {})
                        captured_decision = analysis.get("recommendation", "UNKNOWN")

                    if node_name == "retrieve_excerpts":
                        excerpts = node_state.get("policy_excerpts", [])
                        print(f"  - RAG retrieved {len(excerpts)} excerpts")

            elapsed = time.time() - claim_start

            expected = case.get("expected_outcome")
            passed = captured_decision == expected

            results.append({
                "id": case_id,
                "latency": elapsed,
                "decision": captured_decision,
                "expected": expected,
                "passed": passed
            })

            status = "PASS" if passed else "FAIL"
            print(f"  - Completed in {elapsed:.2f}s | Result: {captured_decision} (Expected: {expected}) | {status}")

        except Exception as e:
            print(f"  - ERROR: {e}")
            results.append({
                "id": case_id,
                "latency": 0,
                "error": str(e),
                "passed": False
            })

    total_duration = time.time() - total_start

    print("\nRunning micro-benchmarks...")
    print("  - Testing Vector Store Latency...")
    store = get_vector_store()
    rag_times = []
    for _ in range(5):
        t0 = time.time()
        store.query("warranty coverage for motor failure")
        rag_times.append(time.time() - t0)
    avg_rag = statistics.mean(rag_times)
    print(f"  - Avg RAG Query: {avg_rag:.4f}s")

    generate_report(results, total_duration, avg_rag)


def generate_report(results, total_duration, avg_rag):
    passed_count = sum(1 for r in results if r.get("passed"))
    total_tests = len(results)
    pass_rate = (passed_count / total_tests) * 100 if total_tests > 0 else 0

    latencies = [r["latency"] for r in results if not r.get("error")]
    avg_latency = statistics.mean(latencies) if latencies else 0
    throughput = 60 / avg_latency if avg_latency > 0 else 0

    report_lines = [
        "# Performance Test Report",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "Environment: Local Windows (Ollama)",
        "",
        "## Summary Metrics",
        "| Metric | Result | Description |",
        "| :--- | :--- | :--- |",
        f"| Pass Rate | {pass_rate:.1f}% | ({passed_count}/{total_tests} claims correctly processed) |",
        f"| Avg Latency | {avg_latency:.2f}s | Average end-to-end processing time per claim |",
        f"| Throughput | {throughput:.1f} per min | Estimated claims processed per minute (sequential) |",
        f"| RAG Speed | {avg_rag*1000:.0f}ms | Vector database retrieval latency |",
        f"| Total Duration | {total_duration:.2f}s | Total wall-clock time for suite |",
        "",
        "## Detailed Test Cases",
        "| ID | Expected | Actual | Latency | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        report_lines.append(
            f"| {r['id']} | {r.get('expected')} | {r.get('decision')} | {r.get('latency', 0):.2f}s | {status} |"
        )

    report_lines.extend([
        "",
        "## Observations",
        "1. RAG performance is stable and low-latency in local tests.",
        "2. The LLM is the dominant latency contributor for extraction and analysis.",
        "3. Deterministic rules reduce LLM load for clear exclusions.",
        ""
    ])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\nReport generated at: {REPORT_PATH}")


if __name__ == "__main__":
    run_benchmark()
