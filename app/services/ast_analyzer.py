"""Multi-language AST analyzer extracting code metrics."""

import asyncio
import logging
from typing import Literal

import tree_sitter
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript

from app.models.ast_summary import ASTSummary, FunctionMetrics

logger = logging.getLogger(__name__)

LanguageTag = Literal["python", "javascript", "typescript", "unknown"]


class ASTAnalyzer:
    """Extracts code structure metrics using tree-sitter."""

    def __init__(self) -> None:
        """Initialise tree-sitter parsers.

        Parsers are loaded once and kept in memory for performance.
        """
        self._parsers: dict[str, tree_sitter.Parser] = {}

        # Python
        try:
            py_lang = tree_sitter.Language(tree_sitter_python.language())
            self._parsers["python"] = tree_sitter.Parser(py_lang)
        except Exception as e:
            logger.error("Failed to load python parser: %s", e)

        # JavaScript
        try:
            js_lang = tree_sitter.Language(tree_sitter_javascript.language())
            self._parsers["javascript"] = tree_sitter.Parser(js_lang)
        except Exception as e:
            logger.error("Failed to load javascript parser: %s", e)

        # TypeScript
        try:
            ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            self._parsers["typescript"] = tree_sitter.Parser(ts_lang)
        except Exception as e:
            logger.error("Failed to load typescript parser: %s", e)

    def detect_language(self, file_path: str) -> LanguageTag:
        """Determine the language tag from the file extension.

        Args:
            file_path: Optional path to the file.

        Returns:
            Language tag. 'unknown' if not matched.
        """
        ext = file_path.lower().split(".")[-1] if "." in file_path else ""
        if ext == "py":
            return "python"
        if ext in ("js", "jsx"):
            return "javascript"
        if ext in ("ts", "tsx"):
            return "typescript"
        return "unknown"

    async def analyze(self, file_path: str, content: str) -> ASTSummary | None:
        """Analyze source code and extract metrics.

        Args:
            file_path: The filename being analyzed.
            content: The raw source code of the file.

        Returns:
            An ASTSummary object, or None if the language is unknown or parser fails.
        """
        lang = self.detect_language(file_path)
        if lang == "unknown":
            return None

        parser = self._parsers.get(lang)
        if not parser:
            logger.warning("Parser for %s not loaded.", lang)
            return None

        def _run() -> ASTSummary | None:
            try:
                tree = parser.parse(content.encode("utf-8"))
                return self._extract_metrics(file_path, lang, content, tree.root_node)
            except Exception as e:
                logger.error("Error parsing %s: %s", file_path, e)
                return None

        return await asyncio.to_thread(_run)

    def _extract_metrics(
        self,
        file_path: str,
        lang: str,
        content: str,
        root_node: tree_sitter.Node,
    ) -> ASTSummary:
        """Walk the AST to extract classes, functions, and imports."""
        functions: list[FunctionMetrics] = []
        classes: list[str] = []
        imports: list[str] = []

        total_lines = content.count("\n") + 1 if content else 0

        def _get_arg_count(func_node: tree_sitter.Node) -> int:
            """Count arguments/parameters for a function node."""
            params_node = func_node.child_by_field_name("parameters")
            if not params_node:
                for c in func_node.children:
                    if c.type in ("parameters", "formal_parameters", "identifier"):
                        params_node = c
                        break

            if not params_node:
                return 0

            # Arrow function with a single unparenthesised arg (e.g. `x => x + 1`)
            if params_node.type == "identifier":
                return 1

            count = 0
            for child in params_node.children:
                # We skip punctuation and comments, counting only actual params
                if child.type not in ("(", ")", ",") and "comment" not in child.type:
                    count += 1
            return count

        def _get_complexity(node: tree_sitter.Node) -> int:
            """Calculate an approximate cyclomatic complexity."""
            c = 1
            decision_types = frozenset(
                {
                    "if_statement",
                    "elif_clause",
                    "for_statement",
                    "while_statement",
                    "do_statement",
                    "switch_case",
                    "case_clause",
                    "catch_clause",
                    "and",
                    "or",
                    "&&",
                    "||",
                    "ternary_expression",
                    "conditional_expression",
                }
            )

            def walk(n: tree_sitter.Node) -> None:
                nonlocal c
                if n.type in decision_types:
                    c += 1
                for child in n.children:
                    walk(child)

            walk(node)
            return c

        def _build_func(n: tree_sitter.Node, name: str) -> FunctionMetrics:
            """Constructs the FunctionMetrics for a given callable node."""
            sl = n.start_point[0] + 1
            el = n.end_point[0] + 1
            return FunctionMetrics(
                name=name,
                start_line=sl,
                end_line=el,
                line_count=el - sl + 1,
                arg_count=_get_arg_count(n),
                cyclomatic_complexity=_get_complexity(n),
            )

        def visit(n: tree_sitter.Node) -> None:
            """Recursively visit AST nodes to collect metrics."""
            if n.type in ("import_statement", "import_from_statement"):
                text = (n.text or b"").decode("utf-8").strip()
                # Split and grab first line in case it spans multiple due to trailing nodes
                imports.append(text.split("\n")[0])

            elif n.type in ("class_definition", "class_declaration"):
                name_node = n.child_by_field_name("name")
                name = (name_node.text or b"").decode("utf-8") if name_node else "anonymous"
                classes.append(name)

            elif n.type in (
                "function_definition",
                "function_declaration",
                "method_definition",
            ):
                name_node = n.child_by_field_name("name")
                name = (name_node.text or b"").decode("utf-8") if name_node else "anonymous"
                functions.append(_build_func(n, name))

            elif n.type == "variable_declarator":
                # Check if this declarator contains an arrow function
                name_node = n.child_by_field_name("name")
                name = (name_node.text or b"").decode("utf-8") if name_node else "anonymous"
                has_arrow = False
                for c in n.children:
                    if c.type == "arrow_function":
                        functions.append(_build_func(c, name))
                        has_arrow = True
                        break
                if has_arrow:
                    return

            for c in n.children:
                visit(c)

        visit(root_node)

        return ASTSummary(
            file_path=file_path,
            language=lang,
            total_lines=total_lines,
            functions=functions,
            classes=classes,
            imports=imports,
        )
