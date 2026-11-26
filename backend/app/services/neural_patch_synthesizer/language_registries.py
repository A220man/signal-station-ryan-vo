"""Language registries for multi-language AST support."""

from typing import Any, Dict, List, Optional


class LanguageRegistry:
    """Registry of language parsers for multi-language AST diffing."""

    def __init__(self):
        # Map language names to parser/configuration
        self._language_parsers: Dict[str, "LanguageParser"] = {}
        self._registered: Dict[str, bool] = {}

    def register(self, language: str, parser_func) -> None:
        """Register a language parser for the given language name."""
        self._language_parsers[language] = parser_func
        self._registered[language] = True

    def get_parser(self, language: str) -> Optional["LanguageParser"]:
        """Get a parser for the given language."""
        if language in self._language_parsers:
            return self._language_parsers[language]()
        return None

    def list_languages(self) -> List[str]:
        """List registered languages."""
        return list(self._language_parsers.keys())


class LanguageParser:
    """Base class for language-specific AST parsers."""

    def parse(self, code: str) -> Any:
        """Parse code into an AST."""
        raise NotImplementedError

    def unparse(self, tree: Any) -> str:
        """Unparse an AST back to code."""
        raise NotImplementedError

    def find_node(self, tree: Any, node_type: str, **kwargs) -> List[Any]:
        """Find nodes of a given type in the AST."""
        raise NotImplementedError


def get_language_parser(language: str = "python") -> Optional[LanguageParser]:
    """Get a language parser for the specified language."""
    registry = LanguageRegistry()

    # Register Python parser using built-in ast module (default "python" language)
    import ast as ast_mod

    def python_parse(code: str) -> Any:
        try:
            return ast_mod.parse(code, mode="exec")
        except SyntaxError:
            return None

    def python_unparse(tree: Any) -> str:
        return ast_mod.unparse(tree) if tree else ""

    def python_find_node(tree: Any, node_type: str, **kwargs) -> List[Any]:
        results = []

        def walk(node):
            if isinstance(node, ast_mod.AST) and node_type in type(node).__name__:
                results.append(node)
            for child in ast_mod.iter_child_nodes(node):
                walk(child)

        walk(tree)
        return results

    registry.register("python", lambda: LanguageParserPython(
        python_parse, python_unparse, python_find_node))

    # Register Python parser using tree-sitter for enhanced semantic parsing
    try:
        from tree_sitter import Language as TSLanguage, Parser as TParser
        import tree_sitter_python

        def tree_sitter_parse(code: str) -> Any:
            parser = TParser()
            parser.language = TSLanguage(tree_sitter_python.language())
            tree = parser.parse(code.encode("utf-8"))
            return tree.root_node

        def tree_sitter_unparse(tree: Any) -> str:
            import ast
            node = tree.root_node if hasattr(tree, 'root_node') else tree
            if not node:
                return ""
            return ""

        def tree_sitter_find_node(tree: Any, node_type: str, **kwargs) -> List[Any]:
            """Find all nodes of a given type in a tree-sitter AST."""
            results = []

            def walk(node):
                if node.type == node_type:
                    results.append(node)
                for child in node.children:
                    walk(child)

            walk(tree)
            return results

        # Register tree-sitter Python parser
        try:
            ts_parser = LanguageParserPythonTreeSitter(
                tree_sitter_parse, tree_sitter_unparse, tree_sitter_find_node
            )
            registry.register("python_tree_sitter", lambda: ts_parser)
        except Exception:
            # tree-sitter may not be fully functional; skip registration
            pass

    except ImportError:
        # tree-sitter not available; skip registration
        pass

    # Try to get the parser
    parser_creator = registry._language_parsers.get(language)
    if parser_creator:
        return parser_creator()
    return None


class LanguageParserPython:
    """Python-specific AST parser using built-in ast module."""

    def __init__(self, parse_fn, unparse_fn, find_node_fn):
        self._parse = parse_fn
        self._unparse = unparse_fn
        self._find_node = find_node_fn

    def parse(self, code: str) -> Any:
        return self._parse(code)

    def unparse(self, tree: Any) -> str:
        return self._unparse(tree)

    def find_node(self, tree: Any, node_type: str, **kwargs) -> List[Any]:
        return self._find_node(tree, node_type, **kwargs)


class LanguageParserPythonTreeSitter:
    """Python-specific AST parser using tree-sitter for enhanced semantic parsing."""

    def __init__(self, parse_fn, unparse_fn, find_node_fn):
        self._parse = parse_fn
        self._unparse = unparse_fn
        self._find_node = find_node_fn

    def parse(self, code: str) -> Any:
        return self._parse(code)

    def unparse(self, tree: Any) -> str:
        return self._unparse(tree)

    def find_node(self, tree: Any, node_type: str, **kwargs) -> List[Any]:
        return self._find_node(tree, node_type, **kwargs)


# Keep backward-compatible export
get_language_parser.__module__ = __name__

