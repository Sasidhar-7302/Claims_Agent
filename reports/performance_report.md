# Performance Test Report
Date: 2026-01-21 10:37:19
Environment: Local Windows (Ollama)

## Summary Metrics
| Metric | Result | Description |
| :--- | :--- | :--- |
| Pass Rate | 100.0% | (5/5 claims correctly processed) |
| Avg Latency | 14.64s | Average end-to-end processing time per claim |
| Throughput | 4.1 per min | Estimated claims processed per minute (sequential) |
| RAG Speed | 2ms | Vector database retrieval latency |
| Total Duration | 73.18s | Total wall-clock time for suite |

## Detailed Test Cases
| ID | Expected | Actual | Latency | Status |
| :--- | :--- | :--- | :--- | :--- |
| claim_001 | APPROVE | APPROVE | 20.78s | PASS |
| claim_002 | APPROVE | APPROVE | 17.29s | PASS |
| claim_003 | REJECT | REJECT | 9.00s | PASS |
| claim_004 | APPROVE | APPROVE | 16.87s | PASS |
| claim_005 | REJECT | REJECT | 9.23s | PASS |

## Observations
1. RAG performance is stable and low-latency in local tests.
2. The LLM is the dominant latency contributor for extraction and analysis.
3. Deterministic rules reduce LLM load for clear exclusions.
