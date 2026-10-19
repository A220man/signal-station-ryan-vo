"""Tests for whitespace-tolerant code patch engine."""
import pytest
from app.services.patch_service import PatchService

def test_exact_patch_match():
    original = "def add(a, b):\n    return a + b\n"
    target = "    return a + b"
    replacement = "    return a + b + 0"

    ok, patched, strategy, diff = PatchService.apply_patch_string(original, target, replacement, "exact")
    assert ok is True
    assert strategy == "exact"
    assert "return a + b + 0" in patched
    assert "--- a/target_file" in diff

def test_normalized_whitespace_and_indentation():
    # Original has 2-space indentation and CRLF endings
    original = "def calculate_loss(pred, target):\r\n  diff = pred - target\r\n  return diff ** 2\r\n"
    # Target snippet has 4-space indentation and standard LF
    target = "    diff = pred - target\n    return diff ** 2"
    replacement = "    diff = pred - target\n    loss = diff ** 2\n    return loss"

    ok, patched, strategy, _ = PatchService.apply_patch_string(original, target, replacement, "normalized_whitespace")
    assert ok is True
    assert strategy == "normalized_whitespace"
    assert "return loss" in patched

def test_fuzzy_hunk_alignment():
    original = "# Header comment\nthreshold = 0.75\nmin_samples = 10\nverbose = True\n# Footer\n"
    target = "threshold = 0.75\nmin_samples = 10"
    replacement = "threshold = 0.85\nmin_samples = 25"

    ok, patched, strategy, _ = PatchService.apply_patch_string(original, target, replacement, "fuzzy_hunk")
    assert ok is True
    assert strategy in ("exact", "normalized_whitespace", "fuzzy_hunk")
    assert "threshold = 0.85" in patched

def test_patch_failure_when_unmatched():
    original = "def hello():\n    print('world')\n"
    target = "def completely_different():\n    return 42"
    replacement = "def new_function():\n    return 99"

    ok, _, strategy, msg = PatchService.apply_patch_string(original, target, replacement, "fuzzy_hunk")
    assert ok is False
    assert strategy == "none"
    assert "failed" in msg.lower()

def test_file_patch_disk_mutation(tmp_path):
    target_file = tmp_path / "script.py"
    target_file.write_text("x = 1\ny = 2\nz = x + y\n", encoding="utf-8")

    res = PatchService.apply_file_patch(
        target_file,
        target_snippet="z = x + y",
        replacement_snippet="z = x * y",
        tolerance_mode="normalized_whitespace"
    )
    assert res["success"] is True
    assert target_file.read_text(encoding="utf-8") == "x = 1\ny = 2\nz = x * y\n"
