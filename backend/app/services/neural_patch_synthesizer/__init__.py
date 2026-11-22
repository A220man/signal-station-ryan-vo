"""Semantic AST Patch Synthesis using Python AST diffing and multi-language replacement.

Provides tree-sitter-like AST diffing and patch synthesis capabilities using
Python's built-in ast module as the foundation. This module forms the core
of the neural-patch-synthesizer feature for multi-language semantic replacement.
"""

from .ast_diff import ASTDiff, detect_semantic_changes
from .ast_patcher import ASTPatcher, PatchResult, ASTSemanticChange, patch_code
from .language_registries import LanguageRegistry

__all__ = [
    "ASTDiff",
    "ASTPatcher",
    "PatchResult",
    "ASTSemanticChange",
    "detect_semantic_changes",
    "patch_code",
    "LanguageRegistry",
]
