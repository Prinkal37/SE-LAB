import ast
from typing import Optional, Iterator

from .models import ASTAnalysisResult, CodeFlag, FunctionInfo


_CONTROL_FLOW_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
)


def _walk_function_scope(root: ast.AST) -> Iterator[ast.AST]:
    """
    Walk a function body without entering nested functions, classes or lambdas.
    The root function itself is included.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        yield node

        if node is not root and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue

        children = list(ast.iter_child_nodes(node))
        stack.extend(reversed(children))


def _count_arguments(args: ast.arguments) -> int:
    """Count every declared parameter kind, including *args and **kwargs."""
    return (
        len(args.posonlyargs)
        + len(args.args)
        + len(args.kwonlyargs)
        + int(args.vararg is not None)
        + int(args.kwarg is not None)
    )


class ASTAnalyzer(ast.NodeVisitor):
    """Collect structural information and simple code-quality flags."""

    def __init__(
        self,
        max_nesting_depth: int = 3,
        max_function_lines: int = 50,
    ):
        if max_nesting_depth < 0:
            raise ValueError("max_nesting_depth cannot be negative.")
        if max_function_lines < 1:
            raise ValueError("max_function_lines must be at least 1.")

        self.max_nesting_depth = max_nesting_depth
        self.max_function_lines = max_function_lines
        self.flags: list[CodeFlag] = []
        self.functions: list[FunctionInfo] = []
        self.implementation_decisions: list[dict] = []
        self.current_function: Optional[str] = None
        self.current_nesting_depth = 0

    def add_flag(
        self,
        category: str,
        description: str,
        node: ast.AST,
        severity: str = "info",
        function_name: Optional[str] = None,
    ) -> None:
        line_start = getattr(node, "lineno", 1)
        line_end = getattr(node, "end_lineno", line_start)
        self.flags.append(
            CodeFlag(
                category=category,
                description=description,
                line_start=line_start,
                line_end=line_end,
                node_type=type(node).__name__,
                function_name=function_name,
                severity=severity,
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)

    def _analyze_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        previous_function = self.current_function
        previous_depth = self.current_nesting_depth
        self.current_function = node.name
        self.current_nesting_depth = 0

        end_line = getattr(node, "end_lineno", node.lineno)
        function_length = end_line - node.lineno + 1

        if function_length > self.max_function_lines:
            self.add_flag(
                "long_function",
                (
                    f"Function '{node.name}' contains {function_length} lines, "
                    f"exceeding the configured limit of "
                    f"{self.max_function_lines} lines."
                ),
                node,
                severity="warning",
                function_name=node.name,
            )

        scoped_nodes = list(_walk_function_scope(node))
        loops = sum(
            isinstance(child, (ast.For, ast.AsyncFor, ast.While))
            for child in scoped_nodes
        )
        conditionals = sum(
            isinstance(child, (ast.If, ast.Match))
            for child in scoped_nodes
        )
        recursive = self._detect_recursion(node, scoped_nodes)
        complexity = self._calculate_complexity(scoped_nodes)

        if recursive:
            self.implementation_decisions.append(
                {
                    "type": "recursion",
                    "function": node.name,
                    "line": node.lineno,
                    "description": f"Function '{node.name}' calls itself.",
                }
            )
            self.add_flag(
                "recursive_function",
                f"Function '{node.name}' uses recursion.",
                node,
                function_name=node.name,
            )

        self.functions.append(
            FunctionInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=end_line,
                arguments=_count_arguments(node.args),
                loops=loops,
                conditionals=conditionals,
                recursive=recursive,
                complexity=complexity,
            )
        )

        # Visit the body so flags/implementation decisions are collected.
        # The nested function visitor saves/restores the current function.
        for statement in node.body:
            self.visit(statement)

        self.current_function = previous_function
        self.current_nesting_depth = previous_depth

    def _detect_recursion(
        self, function_node: ast.FunctionDef | ast.AsyncFunctionDef,
        scoped_nodes: list[ast.AST],
    ) -> bool:
        for node in scoped_nodes:
            if not isinstance(node, ast.Call):
                continue

            called = node.func
            if isinstance(called, ast.Name) and called.id == function_node.name:
                return True

            # Recognize common instance-method recursion: self.method(...)
            if (
                isinstance(called, ast.Attribute)
                and called.attr == function_node.name
                and isinstance(called.value, ast.Name)
                and called.value.id == "self"
            ):
                return True

        return False

    @staticmethod
    def _calculate_complexity(scoped_nodes: list[ast.AST]) -> int:
        """
        Simplified cyclomatic-complexity estimate:
        1 + decision points (branches, loops, boolean operators, handlers,
        and match cases). It is not a full control-flow-graph calculation.
        """
        complexity = 1
        for node in scoped_nodes:
            if isinstance(
                node,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.ExceptHandler,
                ),
            ):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # n boolean operands represent n-1 additional decision points.
                complexity += max(0, len(node.values) - 1)
            elif isinstance(node, ast.Match):
                complexity += len(node.cases)
        return complexity

    def visit_For(self, node: ast.For) -> None:
        self._record_loop("for_loop", "A for loop is used for iteration.", node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._record_loop(
            "async_for_loop", "An async for loop is used for iteration.", node
        )

    def visit_While(self, node: ast.While) -> None:
        self._record_loop(
            "while_loop", "A while loop is used for iteration.", node
        )

    def _record_loop(self, kind: str, description: str, node: ast.AST) -> None:
        self.implementation_decisions.append(
            {
                "type": kind,
                "line": node.lineno,
                "function": self.current_function,
                "description": description,
            }
        )
        self.add_flag(
            "iteration",
            f"{kind.replace('_', ' ').capitalize()} detected.",
            node,
            function_name=self.current_function,
        )
        self._visit_control_flow_with_nesting(node)

    def visit_If(self, node: ast.If) -> None:
        self.add_flag(
            "conditional",
            "Conditional statement detected.",
            node,
            function_name=self.current_function,
        )
        self._visit_control_flow_with_nesting(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_control_flow_with_nesting(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_control_flow_with_nesting(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_control_flow_with_nesting(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._visit_control_flow_with_nesting(node)

    def _visit_control_flow_with_nesting(self, node: ast.AST) -> None:
        self.current_nesting_depth += 1
        if self.current_nesting_depth > self.max_nesting_depth:
            self.add_flag(
                "deep_nesting",
                (
                    f"Nested control-flow depth reached "
                    f"{self.current_nesting_depth}, exceeding the "
                    f"configured threshold of {self.max_nesting_depth}."
                ),
                node,
                severity="warning",
                function_name=self.current_function,
            )

        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self.current_nesting_depth -= 1

    def visit_List(self, node: ast.List) -> None:
        self._record_data_structure("list", "List data structure detected.", node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self._record_data_structure(
            "dictionary", "Dictionary data structure detected.", node
        )

    def visit_Set(self, node: ast.Set) -> None:
        self._record_data_structure("set", "Set data structure detected.", node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._record_data_structure("tuple", "Tuple data structure detected.", node)

    def _record_data_structure(
        self, kind: str, description: str, node: ast.AST
    ) -> None:
        self.implementation_decisions.append(
            {
                "type": kind,
                "line": node.lineno,
                "function": self.current_function,
                "description": description,
            }
        )
        self.generic_visit(node)


def analyze_code(
    source_code: str,
    max_nesting_depth: int = 3,
    max_function_lines: int = 50,
) -> ASTAnalysisResult:
    """Parse and analyze Python source code without executing it."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        return ASTAnalysisResult(
            success=False,
            language="python",
            syntax_error={
                "message": error.msg,
                "line": error.lineno,
                "column": error.offset,
                "text": error.text.strip() if error.text else None,
            },
        )

    analyzer = ASTAnalyzer(
        max_nesting_depth=max_nesting_depth,
        max_function_lines=max_function_lines,
    )
    analyzer.visit(tree)

    return ASTAnalysisResult(
        success=True,
        language="python",
        flags=analyzer.flags,
        functions=analyzer.functions,
        implementation_decisions=analyzer.implementation_decisions,
    )
