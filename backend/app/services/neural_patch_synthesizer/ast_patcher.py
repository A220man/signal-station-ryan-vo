"""AST patching synthesizer for semantic code replacement."""

from typing import Any, Dict, List, Optional, Tuple
import ast as ast_mod

from .ast_diff import ASTDiff, detect_semantic_changes, DiffResult, ASTNodeInfo, new_tree_from_code
from .language_registries import LanguageRegistry


class ASTSemanticChange:
    """Represents a semantic change between two AST nodes."""

    def __init__(
        self,
        old_node: ast_mod.AST,
        new_node: ast_mod.AST,
        change_type: str,
        description: str,
    ):
        self.old_node = old_node
        self.new_node = new_node
        self.change_type = change_type
        self.description = description


class PatchResult:
    """Result of applying an AST patch."""

    def __init__(
        self,
        success: bool,
        patched_code: str,
        changes: List[ASTSemanticChange],
        strategy: str = "ast_structural",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.patched_code = patched_code
        self.changes = changes
        self.strategy = strategy
        self.metadata = metadata or {}


class ASTPatcher:
    """Patches Python code using AST structural analysis and semantic change detection."""

    def __init__(self):
        self._language_registry = LanguageRegistry()

    def patch(
        self,
        original_code: str,
        target_snippet: str,
        replacement_code: str,
        strategy: str = "ast_structural",
    ) -> PatchResult:
        """Apply an AST-based patch from target snippet to replacement."""
        try:
            original_tree = ast_mod.parse(original_code)
        except SyntaxError as e:
            return PatchResult(False, original_code, [], "failed", {"error": str(e)})

        try:
            target_tree = ast_mod.parse(target_snippet)
        except SyntaxError as e:
            return PatchResult(False, original_code, [], "failed", {"target_error": str(e)})

        try:
            replacement_tree = ast_mod.parse(replacement_code)
        except SyntaxError as e:
            return PatchResult(False, original_code, [], "failed", {"replacement_error": str(e)})

        return self._apply_patch(
            original_tree, target_tree, replacement_tree, strategy
        )

    def _apply_patch(
        self,
        original_tree: ast_mod.AST,
        target_tree: ast_mod.AST,
        replacement_tree: ast_mod.AST,
        strategy: str,
    ) -> PatchResult:
        """Apply the patch based on the selected strategy."""

        if strategy == "ast_structural":
            return self._ast_structural_patch(original_tree, target_tree, replacement_tree)
        elif strategy == "semantic_change":
            return self._semantic_patch(original_tree, target_tree, replacement_tree)
        elif strategy == "expression_replace":
            return self._expression_replace_patch(original_tree, target_tree, replacement_tree)
        else:
            return PatchResult(False, ast_mod.unparse(original_tree) if original_tree else "", [], "unknown_strategy", {})

    def _unparse(self, tree: ast_mod.AST) -> str:
        """Unparse AST to code string."""
        try:
            return ast_mod.unparse(tree)
        except Exception:
            return ""

    def _ast_structural_patch(
        self,
        original: ast_mod.AST,
        target: ast_mod.AST,
        replacement: ast_mod.AST,
    ) -> PatchResult:
        """Patch by matching AST structure and replacing subtrees."""
        try:
            # Find the target node in the original and replace its subtree
            target_node = self._find_node_by_structure(original, target)
            if target_node is None:
                return PatchResult(False, self._unparse(original), [], "no_match", {})

            # Get replacement root
            replacement_root = replacement.body[0] if hasattr(replacement, 'body') and replacement.body else replacement

            # Replace the target subtree
            patched = self._replace_subtree(original, target_node, replacement_root)
            patched_code = self._unparse(patched)

            # Detect what changed
            changes = self._detect_changes(original, patched)

            return PatchResult(True, patched_code, changes, "ast_structural", {})
        except Exception as e:
            return PatchResult(False, self._unparse(original), [], "error", {"error": str(e)})

    def _find_node_by_structure(
        self, tree: ast_mod.AST, target: ast_mod.AST
    ) -> Optional[ast_mod.AST]:
        """Find a node in the tree matching the target's structure."""
        target_sig = self._get_node_signature(target)

        def walk_and_find(node: ast_mod.AST) -> Optional[ast_mod.AST]:
            sig = self._get_node_signature(node)
            if sig == target_sig:
                return node
            for child in ast_mod.iter_child_nodes(node):
                if isinstance(child, ast_mod.AST):
                    result = walk_and_find(child)
                    if result is not None:
                        return result
            return None

        return walk_and_find(tree)

    def _get_node_signature(self, node: ast_mod.AST) -> str:
        """Get a structural signature for a node."""
        kids = []
        for _, val in ast_mod.iter_fields(node):
            if isinstance(val, ast_mod.AST):
                kids.append(self._get_node_signature(val))
            elif isinstance(val, list):
                kid_sigs = []
                for item in val:
                    if isinstance(item, ast_mod.AST):
                        kid_sigs.append(self._get_node_signature(item))
                    else:
                        kid_sigs.append(str(item))
                kids.append(f"[{','.join(kid_sigs)}]")
            else:
                kids.append(str(val))
        return f"{type(node).__name__}({','.join(kids)})"

    def _replace_subtree(
        self, tree: ast_mod.AST, target: ast_mod.AST, replacement: ast_mod.AST
    ) -> ast_mod.AST:
        """Replace a target subtree within a tree with a replacement."""
        found, parent, is_left = self._find_parent_with_target(tree, target)

        if found is None:
            return tree

        if parent is not None:
            attr_name = 'left' if is_left else 'right'
            setattr(parent, attr_name, replacement)

        return tree

    def _find_parent_with_target(
        self, tree: ast_mod.AST, target: ast_mod.AST
    ) -> Tuple[Optional[ast_mod.AST], Optional[ast_mod.AST], bool]:
        """Find the target node and its parent."""
        target_sig = self._get_node_signature(target)

        def walk(node: ast_mod.AST, parent: Optional[ast_mod.AST], is_left: bool
                ) -> Tuple[Optional[ast_mod.AST], Optional[ast_mod.AST], bool]:
            sig = self._get_node_signature(node)
            if sig == target_sig:
                return node, parent, is_left
            for field_name, field_value in ast_mod.iter_fields(node):
                if isinstance(field_value, ast_mod.AST):
                    result = walk(field_value, node, field_name in ('left', 'right'))
                    if result[0] is not None:
                        return result
                elif isinstance(field_value, list):
                    for i, item in enumerate(field_value):
                        if isinstance(item, ast_mod.AST):
                            result = walk(item, node, i > 0)
                            if result[0] is not None:
                                return result
            return None, None, False

        return walk(tree, None, False)

    def _detect_changes(self, original: ast_mod.AST, patched: ast_mod.AST) -> List[ASTSemanticChange]:
        """Detect changes between original and patched code."""
        try:
            old_code = ast_mod.unparse(original)
            new_code = ast_mod.unparse(patched) if patched else ""

            diff = ASTDiff()
            result = diff.diff(old_code, new_code)

            changes: List[ASTSemanticChange] = []
            for old_node, new_node in result.changed:
                semantic = detect_semantic_changes(old_node.node, new_node.node)
                changes.extend(semantic)

            return changes
        except Exception:
            return []

    def _semantic_patch(
        self,
        original: ast_mod.AST,
        target: ast_mod.AST,
        replacement: ast_mod.AST,
    ) -> PatchResult:
        """Patch by detecting semantic changes and applying them."""
        try:
            # Detect changes between target and replacement
            changes = self._detect_target_replacement_changes(target, replacement)

            # Apply changes to original
            patched = self._apply_changes_to_original(original, changes)

            patched_code = self._unparse(patched) if patched else self._unparse(original)

            return PatchResult(
                True, patched_code, changes, "semantic_change", {"changes_detected": len(changes)}
            )
        except Exception as e:
            return PatchResult(False, self._unparse(original), [], "error", {"error": str(e)})

    def _detect_target_replacement_changes(
        self, target: ast_mod.AST, replacement: ast_mod.AST
    ) -> List[ASTSemanticChange]:
        """Detect semantic changes between target and replacement code."""
        changes: List[ASTSemanticChange] = []

        target_sig = self._get_node_signature(target)
        replacement_sig = self._get_node_signature(replacement)

        if target_sig != replacement_sig:
            if isinstance(target, ast_mod.FunctionDef) and isinstance(replacement, ast_mod.FunctionDef):
                from .ast_patcher import _detect_func_changes
                changes.extend(_detect_func_changes(target, replacement))
            elif isinstance(target, ast_mod.ClassDef) and isinstance(replacement, ast_mod.ClassDef):
                from .ast_patcher import _detect_class_changes
                changes.extend(_detect_class_changes(target, replacement))
            elif isinstance(target, ast_mod.arg) and isinstance(replacement, ast_mod.arg):
                from .ast_patcher import _detect_arg_changes
                changes.extend(_detect_arg_changes(target, replacement))
            else:
                changes.append(
                    ASTSemanticChange(target, replacement, "node_structure_change",
                                     "Node structure changed")
                )
        else:
            changes.extend(self._compare_node_children(target, replacement))

        return changes

    def _compare_node_children(self, old: ast_mod.AST, new: ast_mod.AST) -> List[ASTSemanticChange]:
        """Compare children of two nodes with the same signature."""
        changes: List[ASTSemanticChange] = []
        old_fields = {k: v for k, v in ast_mod.iter_fields(old)}
        new_fields = {k: v for k, v in ast_mod.iter_fields(new)}

        for field_name in set(list(old_fields.keys()) + list(new_fields.keys())):
            old_val = old_fields.get(field_name)
            new_val = new_fields.get(field_name)

            if field_name not in old_fields:
                changes.append(
                    ASTSemanticChange(old, new, "field_added", f"Field '{field_name}' added")
                )
            elif field_name not in new_fields:
                changes.append(
                    ASTSemanticChange(old, new, "field_removed", f"Field '{field_name}' removed")
                )
            elif isinstance(old_val, ast_mod.AST) and isinstance(new_val, ast_mod.AST):
                sub_changes = detect_semantic_changes(old_val, new_val)
                changes.extend(sub_changes)
            elif isinstance(old_val, list) and isinstance(new_val, list):
                if len(old_val) != len(new_val):
                    changes.append(
                        ASTSemanticChange(old, new, "field_list_length_change",
                                         f"Field '{field_name}' length changed")
                    )
                else:
                    for i, (old_item, new_item) in enumerate(zip(old_val, new_val)):
                        if isinstance(old_item, ast_mod.AST) and isinstance(new_item, ast_mod.AST):
                            sub_changes = detect_semantic_changes(old_item, new_item)
                            changes.extend(sub_changes)
            elif old_val != new_val:
                changes.append(
                    ASTSemanticChange(old, new, "field_value_change",
                                     f"Field '{field_name}' value changed")
                )

        return changes

    def _apply_changes_to_original(self, original: ast_mod.AST, changes: List[ASTSemanticChange]) -> ast_mod.AST:
        """Apply detected semantic changes to the original AST."""
        result = original

        for change in changes:
            if change.change_type == "parameter_rename":
                result = self._rename_parameter(result,
                    change.old_node.arg if hasattr(change.old_node, 'arg') else '',
                    change.new_node.arg if hasattr(change.new_node, 'arg') else '')
            elif change.change_type == "function_rename":
                result = self._rename_function(result,
                    change.old_node.name if hasattr(change.old_node, 'name') else '',
                    change.new_node.name if hasattr(change.new_node, 'name') else '')
            elif change.change_type == "value_change":
                result = self._replace_constant(result,
                    change.old_node.value if hasattr(change.old_node, 'value') else None,
                    change.new_node.value if hasattr(change.new_node, 'value') else None)

        return result

    def _rename_parameter(
        self, tree: ast_mod.AST, old_name: str, new_name: str
    ) -> ast_mod.AST:
        """Rename a parameter throughout the AST."""
        import copy

        tree = copy.deepcopy(tree)

        def walk(node: ast_mod.AST) -> ast_mod.AST:
            if isinstance(node, ast_mod.FunctionDef):
                new_args = []
                for arg in node.args.args:
                    if arg.arg == old_name:
                        new_arg = arg._replace(arg=new_name)
                        new_args.append(new_arg)
                    else:
                        new_args.append(arg)
                node = node._replace(args=node._args(_args=new_args))
            # Recurse into children
            for field_name, field_value in ast_mod.iter_fields(node):
                if isinstance(field_value, ast_mod.AST):
                    walk(field_value)
                elif isinstance(field_value, list):
                    for item in field_value:
                        if isinstance(item, ast_mod.AST):
                            walk(item)
            return node

        walk(tree)
        return tree

    def _rename_function(
        self, tree: ast_mod.AST, old_name: str, new_name: str
    ) -> ast_mod.AST:
        """Rename a function definition."""
        import copy

        tree = copy.deepcopy(tree)

        if isinstance(tree, ast_mod.FunctionDef) and tree.name == old_name:
            return tree._replace(name=new_name)

        def walk(node: ast_mod.AST) -> Optional[ast_mod.AST]:
            if isinstance(node, ast_mod.FunctionDef) and node.name == old_name:
                return node._replace(name=new_name)
            result = node
            for field_name, field_value in ast_mod.iter_fields(node):
                if isinstance(field_value, ast_mod.AST):
                    new_val = walk(field_value)
                    if new_val is not field_value:
                        pass
            return node

        walk(tree)
        return tree

    def _replace_constant(
        self, tree: ast_mod.AST, old_value: Any, new_value: Any
    ) -> ast_mod.AST:
        """Replace a constant value in the AST."""
        import copy

        tree = copy.deepcopy(tree)

        def walk(node: ast_mod.AST) -> ast_mod.AST:
            if isinstance(node, ast_mod.Constant) and node.value == old_value:
                return node._replace(value=new_value)
            for field_name, field_value in ast_mod.iter_fields(node):
                if isinstance(field_value, ast_mod.AST):
                    setattr(node, field_name, walk(field_value))
            return node

        return walk(tree)

    def _expression_replace_patch(
        self,
        original: ast_mod.AST,
        target: ast_mod.AST,
        replacement: ast_mod.AST,
    ) -> PatchResult:
        """Patch by replacing a specific expression in the original code."""
        try:
            # Find the target expression in the original
            target_expr = self._find_expression(original, target)
            if target_expr is None:
                return PatchResult(False, self._unparse(original), [], "no_match", {})

            # Replace with the replacement expression
            patched = self._replace_expression(original, target_expr, replacement)
            patched_code = self._unparse(patched)

            changes = [ASTSemanticChange(
                target, replacement, "expression_replace",
                f"Expression replaced: {ast_mod.unparse(target)} -> {ast_mod.unparse(replacement)}"
            )]

            return PatchResult(True, patched_code, changes, "expression_replace", {})
        except Exception as e:
            return PatchResult(False, self._unparse(original), [], "error", {"error": str(e)})

    def _find_expression(self, tree: ast_mod.AST, target: ast_mod.AST) -> Optional[ast_mod.AST]:
        """Find an expression in the tree matching the target."""
        target_sig = self._get_node_signature(target)

        def walk(node: ast_mod.AST) -> Optional[ast_mod.AST]:
            sig = self._get_node_signature(node)
            if sig == target_sig:
                return node
            for child in ast_mod.iter_child_nodes(node):
                if isinstance(child, ast_mod.AST):
                    result = walk(child)
                    if result is not None:
                        return result
            return None

        return walk(tree)

    def _replace_expression(
        self, tree: ast_mod.AST, target: ast_mod.AST, replacement: ast_mod.AST
    ) -> ast_mod.AST:
        """Replace a target expression in the tree with a replacement."""
        found, parent, field_name = self._find_parent_and_field(tree, target)

        if found is None or parent is None:
            return tree

        setattr(parent, field_name, replacement)  # type: ignore[attr-defined]
        return tree

    def _find_parent_and_field(
        self, tree: ast_mod.AST, target: ast_mod.AST
    ) -> Tuple[Optional[ast_mod.AST], Optional[ast_mod.AST], str]:
        """Find target node and its parent + field name."""
        target_sig = self._get_node_signature(target)

        def walk(node: ast_mod.AST, parent: Optional[ast_mod.AST], field: Optional[str]
                ) -> Optional[Tuple[ast_mod.AST, Optional[ast_mod.AST], str]]:
            sig = self._get_node_signature(node)
            if sig == target_sig:
                return node, parent, field or "unknown"  # type: ignore[return-value]
            for field_name, field_value in ast_mod.iter_fields(node):
                if isinstance(field_value, ast_mod.AST):
                    result = walk(field_value, node, field_name)
                    if result[0] is not None:
                        return result
                elif isinstance(field_value, list):
                    for i, item in enumerate(field_value):
                        if isinstance(item, ast_mod.AST):
                            result = walk(item, node, field_name if i == 0 else f"{field_name}[{i}]")
                            if result[0] is not None:
                                return result
            return None, None, "unknown"

        return walk(tree, None, None)


def patch_code(
    original: str,
    target: str,
    replacement: str,
    strategy: str = "ast_structural",
) -> PatchResult:
    """Convenience function to patch code using AST synthesis."""
    patcher = ASTPatcher()
    return patcher.patch(original, target, replacement, strategy)
