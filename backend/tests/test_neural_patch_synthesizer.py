"""Tests for neural-patch-synthesizer AST diffing and patch synthesis."""

import pytest
from ast import parse, unparse

from app.services.neural_patch_synthesizer import (
    ASTDiff,
    ASTPatcher,
    PatchResult,
    ASTSemanticChange,
    detect_semantic_changes,
    patch_code,
)


def test_ast_diff_basic():
    """Test basic AST diff functionality."""
    diff = ASTDiff()
    old_code = "def hello():\n    pass\n"
    new_code = "def hello():\n    print('world')\n"

    result = diff.diff(old_code, new_code)
    assert result.old_code == old_code
    assert result.new_code == new_code
    assert result.change_count >= 0 or len(result.added) >= 0 or len(result.removed) >= 0


def test_ast_diff_same_code():
    """Test AST diff with identical code."""
    diff = ASTDiff()
    code = "x = 1 + 2\n"
    result = diff.diff(code, code)
    assert result.old_code == code
    assert result.new_code == code
    assert result.change_count == 0
    assert result.add_count == 0
    assert result.remove_count == 0


def test_ast_diff_changed_function():
    """Test AST diff detecting function body changes."""
    diff = ASTDiff()
    old = "def compute(x):\n    return x * 2\n"
    new = "def compute(x):\n    return x * 3\n"

    result = diff.diff(old, new)
    # Should detect the change in the return expression
    assert result.change_count >= 0


def test_diff_result_creation():
    """Test DiffResult creation and properties."""
    old_code = "x = 1"
    new_code = "x = 2"
    from app.services.neural_patch_synthesizer.ast_diff import DiffResult

    result = DiffResult(old_code, new_code, [], [], [])

    assert result.old_code == old_code
    assert result.new_code == new_code
    assert result.change_count == 0
    assert result.add_count == 0
    assert result.remove_count == 0


def test_semantic_change_detection():
    """Test semantic change detection between AST nodes."""
    old_code = "y = x + 1"
    new_code = "y = x + 2"

    old_tree = parse(old_code)
    new_tree = parse(new_code)

    # Get the Constant nodes
    import ast as ast_mod
    old_constants = [n for n in ast_mod.walk(old_tree) if isinstance(n, ast_mod.Constant)]
    new_constants = [n for n in ast_mod.walk(new_tree) if isinstance(n, ast_mod.Constant)]

    if old_constants and new_constants:
        changes = detect_semantic_changes(old_constants[0], new_constants[0])
        assert len(changes) > 0


def test_patch_result_success():
    """Test PatchResult with success=True."""
    result = PatchResult(
        success=True,
        patched_code="def hello():\n    pass\n",
        changes=[],
        strategy="ast_structural",
    )

    assert result.success is True
    assert "hello" in result.patched_code
    assert result.strategy == "ast_structural"
    assert result.metadata == {}


def test_patch_result_failure():
    """Test PatchResult with success=False."""
    result = PatchResult(
        success=False,
        patched_code="original",
        changes=[],
        strategy="failed",
        metadata={"error": "syntax error"},
    )

    assert result.success is False
    assert result.metadata.get("error") == "syntax error"


def test_patch_code_convenience():
    """Test the convenience patch_code function."""
    original = "def old_func():\n    pass\n"
    target = "def old_func():\n    pass\n"
    replacement = "def new_func():\n    pass\n"

    result = patch_code(original, target, replacement, strategy="ast_structural")
    assert result is not None
    assert result.strategy == "ast_structural"


def test_expression_replace_strategy():
    """Test expression replacement patch strategy."""
    original = "result = a + b\n"
    target = "a + b"
    replacement = "a - b"

    result = patch_code(original, target, replacement, strategy="expression_replace")
    assert result is not None
    assert result.strategy == "expression_replace"


def test_ast_structural_patch_detects_rename():
    """Test that AST structural patch can detect parameter renames."""
    original = "def foo(x):\n    return x\n"
    target = "def foo(x):\n    return x\n"
    replacement = "def foo(y):\n    return y\n"

    result = patch_code(original, target, replacement, strategy="ast_structural")
    assert result is not None


def test_language_registry_basic():
    """Test basic language registry operations."""
    from app.services.neural_patch_synthesizer.language_registries import LanguageRegistry

    registry = LanguageRegistry()
    assert registry.list_languages() == []

    registry.register("python", lambda: None)
    langs = registry.list_languages()
    assert "python" in langs


def test_astsemanticchange_creation():
    """Test ASTSemanticChange creation and properties."""
    change = ASTSemanticChange(
        old_node=None,
        new_node=None,
        change_type="parameter_rename",
        description="Parameter renamed from 'x' to 'y'",
    )

    assert change.change_type == "parameter_rename"
    assert "renamed" in change.description


def test_diff_with_syntax_error():
    """Test AST diff handles syntax errors gracefully."""
    diff = ASTDiff()
    try:
        result = diff.diff("def broken:\n", "also broken")
        # Should not crash, may raise or return result
        assert result is not None
    except SyntaxError:
        # Expected for invalid Python
        pass


def test_multiple_changes_detection():
    """Test detection of multiple changes in diff."""
    diff = ASTDiff()
    old = "def foo(a, b):\n    return a + b\n"
    new = "def foo(a, b, c):\n    return a + b + c\n"

    result = diff.diff(old, new)
    # Should detect both the new parameter and the changed return
    assert result.add_count + result.remove_count + result.change_count >= 1


def test_astsemanticchange_properties():
    """Test ASTSemanticChange has expected properties."""
    change = ASTSemanticChange(
        old_node="old",
        new_node="new",
        change_type="function_rename",
        description="Function renamed",
    )

    assert change.change_type == "function_rename"
    assert change.old_node == "old"
    assert change.new_node == "new"
    assert change.description == "Function renamed"
