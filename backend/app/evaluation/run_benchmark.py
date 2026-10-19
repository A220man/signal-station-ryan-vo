"""CLI command runner for reproducible AI/ML offline evaluation benchmark."""
import sys
import json
from app.core.database import init_db
from app.services.evaluation_service import EvaluationService

def main():
    print("=" * 70)
    print("Signal Station | Coding Agent Safety & Reasoning Evaluation Suite")
    print("=" * 70)
    
    # Initialize database if needed
    init_db()

    print("\n[1/3] Loading 20 labeled coding agent trajectories...")
    print("      - 8 Patch Resilience scenarios (indentation, CRLF, whitespace drift)")
    print("      - 6 Sandbox Boundary scenarios (breakout, forkbomb, exfil, safe CLI)")
    print("      - 6 Goal Verification scenarios (premature completion, budget checks)")

    print("\n[2/3] Executing deterministic benchmark harness...")
    metrics = EvaluationService.run_benchmark()

    print("\n[3/3] Measured Evaluation Results:")
    print("-" * 50)
    print(f"Total Scenarios Evaluated: {metrics['total_scenarios']}")
    print(f"Passed Scenarios:          {metrics['passed_scenarios']}")
    print(f"Overall Accuracy:          {metrics['accuracy'] * 100:.1f}%")
    print(f"Patch Application Success: {metrics['patch_success_rate'] * 100:.1f}%")
    print(f"Precision Score:           {metrics['precision_score']:.4f}")
    print(f"Recall Score:              {metrics['recall_score']:.4f}")
    print(f"F1 Score:                  {metrics['f1_score']:.4f}")
    print(f"Compaction Ratio:          {metrics['compaction_ratio']:.1f}% space reclaimed")
    print(f"Mean Step Latency:         {metrics['mean_latency_ms']:.2f} ms")
    print("-" * 50)
    print(f"\nEvaluation Run ID: {metrics['id']}")
    print(f"Timestamp:         {metrics['run_timestamp']}")
    print("\nBenchmark completed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
