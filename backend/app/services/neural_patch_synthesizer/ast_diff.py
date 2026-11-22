"""AST diffing utilities for comparing and synthesizing code changes."""

import ast
from typing import List, Tuple


class ASTNodeInfo:
    """Information about an AST node with a unique identifier."""

    def __init__(self, node_id: str, node_type: str, node: ast.AST):
        self.id = node_id
        self.node_type = node_type
        self.node = node
        self.fields: dict = {}

        for field_name, field_value in ast.iter_fields(node):
            if isinstance(field_value, ast.AST):
                self.fields[field_name] = type(field_value).__name__
            elif isinstance(field_value, list):
                self.fields[field_name] = [
                    type(item).__name__ if isinstance(item, ast.AST) else str(item)
                    for item in field_value
                ]
            else:
                self.fields[field_name] = field_value


def _collect_nodes(tree: ast.AST) -> List[ASTNodeInfo]:
    """Collect all nodes in an AST with unique IDs."""
    nodes: List[ASTNodeInfo] = []
    counter = [0]

    def visit(node: ast.AST):
        node_id = f"{type(node).__name__}_{counter[0]}"
        counter[0] += 1
        info = ASTNodeInfo(node_id, type(node).__name__, node)
        nodes.append(info)

        for field_name, field_value in ast.iter_fields(node):
            if isinstance(field_value, ast.AST):
                visit(field_value)
            elif isinstance(field_value, list):
                for item in field_value:
                    if isinstance(item, ast.AST):
                        visit(item)

    visit(tree)
    return nodes


def _new_tree_from_code(code: str) -> ast.AST:
    """Parse code into an AST."""
    return ast.parse(code)


class ASTDiff:
    """Diff two Python ASTs and produce a semantic patch."""

    def diff(self, old_code: str, new_code: str) -> "DiffResult":
        """Diff two Python code strings and return a DiffResult."""
        try:
            old_tree = ast.parse(old_code)
        except SyntaxError as e:
            raise SyntaxError(f"Invalid old code: {e}") from e
        try:
            new_tree = ast.parse(new_code)
        except SyntaxError as e:
            raise SyntaxError(f"Invalid new code: {e}") from e

        return self._diff_trees(old_tree, new_code, old_code)

    def _diff_trees(
        self,
        old_tree: ast.AST,
        new_code: str,
        old_code: str,
    ) -> "DiffResult":
        """Diff two AST trees and produce a result."""
        old_nodes = _collect_nodes(old_tree)
        new_tree = _new_tree_from_code(new_code)

        # Find changed, added, removed nodes
        old_ids = {node.id for node in old_nodes}
        new_node_ids = {node.id for node in _collect_nodes(new_tree)}

        changed: List[Tuple[ASTNodeInfo, ASTNodeInfo]] = []
        added: List[ASTNodeInfo] = []
        removed: List[ASTNodeInfo] = []

        # Check for changed nodes (same id but different type or attributes)
        for old_node in old_nodes:
            matching_new = [n for n in _collect_nodes(new_tree) if n.id == old_node.id]
            if matching_new:
                new_node = matching_new[0]
                if type(old_node) != type(new_node) or old_node.fields != new_node.fields:
                    changed.append((old_node, new_node))
            else:
                removed.append(old_node)

        # Check for added nodes
        for new_node in _collect_nodes(new_tree):
            if new_node.id not in old_ids:
                added.append(new_node)

        return DiffResult(old_code, new_code, changed, added, removed)


class DiffResult:
    """Result of an AST diff operation."""

    def __init__(self, old_code: str, new_code: str, changed: List, added: List, removed: List):
        self.old_code = old_code
        self.new_code = new_code
        self.changed = changed
        self.added = added
        self.removed = removed
        self.change_count = len(changed)
        self.add_count = len(added)
        self.remove_count = len(removed)


def detect_semantic_changes(
    old_node: ast.AST,
    new_node: ast.AST,
) -> List["ASTSemanticChange"]:
    """Detect semantic changes between two similar AST nodes."""
    changes: List["ASTSemanticChange"] = []

    if type(old_node) != type(new_node):
        changes.append(
            ASTSemanticChange(
                old_node, new_node, "node_type_change",
                f"Node type changed from {type(old_node).__name__} to {type(new_node).__name__}"
            )
        )
        return changes

    # Only compare same-type nodes for semantic changes
    if not _same_type(old_node, new_node):
        return changes

    # Dispatch to type-specific comparers
    if isinstance(old_node, ast.Constant):
        changes.extend(_compare_constant_changes(old_node, new_node))
    elif isinstance(old_node, ast.Name):
        changes.extend(_compare_name_changes(old_node, new_node))
    elif isinstance(old_node, (ast.BoolOp, ast.BinOp, ast.UnaryOp)):
        changes.extend(_compare_op_changes(old_node, new_node))
    elif isinstance(old_node, ast.FunctionDef):
        changes.extend(_compare_func_changes(old_node, new_node))
    elif isinstance(old_node, ast.ClassDef):
        changes.extend(_compare_class_changes(old_node, new_node))
    elif isinstance(old_node, ast.arg):
        changes.extend(_compare_arg_changes(old_node, new_node))
    # If type matches but no specific handler, return empty

    return changes


def _same_type(old: ast.AST, new: ast.AST) -> bool:
    """Check if two nodes are the same type."""
    return type(old) is type(new)


def _compare_constant_changes(old: ast.Constant, new: ast.Constant) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if old.value != new.value:
        changes.append(
            ASTSemanticChange(old, new, "value_change",
                             f"Constant value changed from {repr(old.value)} to {repr(new.value)}")
        )
    return changes


def _compare_name_changes(old: ast.Name, new: ast.Name) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if old.id != new.id:
        changes.append(
            ASTSemanticChange(old, new, "variable_rename",
                             f"Variable renamed from '{old.id}' to '{new.id}'")
        )
    return changes


def _compare_op_changes(old, new) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if type(old) is not type(new):
        changes.append(
            ASTSemanticChange(old, new, "operator_change",
                             f"Operator changed from {type(old).__name__} to {type(new).__name__}")
        )
    return changes


def _compare_func_changes(old: ast.FunctionDef, new: ast.FunctionDef) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if old.name != new.name:
        changes.append(
            ASTSemanticChange(old, new, "function_rename",
                             f"Function renamed from '{old.name}' to '{new.name}'")
        )
    if len(old.args.args) != len(new.args.args):
        changes.append(
            ASTSemanticChange(old, new, "function_arg_count_change",
                             f"Function arg count changed from {len(old.args.args)} to {len(new.args.args)}")
        )
    if old.returns is None and new.returns is not None:
        changes.append(
            ASTSemanticChange(old, new, "function_returns_added", "Return type annotation added")
        )
    elif old.returns is not None and new.returns is None:
        changes.append(
            ASTSemanticChange(old, new, "function_returns_removed", "Return type annotation removed")
        )
    return changes


def _compare_class_changes(old: ast.ClassDef, new: ast.ClassDef) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if old.name != new.name:
        changes.append(
            ASTSemanticChange(old, new, "class_rename",
                             f"Class renamed from '{old.name}' to '{new.name}'")
        )
    return changes


def _compare_arg_changes(old: ast.arg, new: ast.arg) -> List["ASTSemanticChange"]:
    changes: List["ASTSemanticChange"] = []
    if old.arg != new.arg:
        changes.append(
            ASTSemanticChange(old, new, "parameter_rename",
                             f"Parameter renamed from '{old.arg}' to '{new.arg}'")
        )
    if old.annotation is None and new.annotation is not None:
        changes.append(
            ASTSemanticChange(old, new, "parameter_type_added", "Parameter type annotation added")
        )
    elif old.annotation is not None and new.annotation is None:
        changes.append(
            ASTSemanticChange(old, new, "parameter_type_removed", "Parameter type annotation removed")
        )
    return changes


class ASTSemanticChange:
    """Represents a semantic change between two AST nodes."""

    def __init__(
        self,
        old_node: ast.AST,
        new_node: ast.AST,
        change_type: str,
        description: str,
    ):
        self.old_node = old_node
        self.new_node = new_node
        self.change_type = change_type
        self.description = description
