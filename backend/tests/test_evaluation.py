"""Tests for offline AI/ML agent safety and reasoning benchmark."""
import pytest
from app.services.evaluation_service import EvaluationService

def test_benchmark_full_execution():
    metric = EvaluationService.run_benchmark()
    assert metric["total_scenarios"] == 20
    assert metric["passed_scenarios"] == 20
    assert metric["accuracy"] == 1.0
    assert metric["patch_success_rate"] == 1.0
    assert metric["precision_score"] == 1.0
    assert metric["recall_score"] == 1.0
    assert metric["f1_score"] == 1.0
    assert metric["compaction_ratio"] >= 0.0
    assert metric["mean_latency_ms"] >= 0.0

def test_benchmark_history_persistence():
    # Run twice
    m1 = EvaluationService.run_benchmark()
    m2 = EvaluationService.run_benchmark()

    history = EvaluationService.get_history(limit=5)
    assert len(history["runs"]) >= 2
    assert history["runs"][0]["id"] == m2["id"]
    assert history["runs"][1]["id"] == m1["id"]

    # Baseline comparison values present
    comparison = history["baseline_comparison"]
    assert comparison["engine_patch_success"] == 1.0
    assert comparison["baseline_patch_success"] < 1.0
