"""Adapter between Subhadeep's AST engine (adaptive_viva_ast) and the backend.

The engine reports *every* loop/if as a flag. For highlighting and question generation
we only want the notable ones (FR-4.3.2 / FR-4.3.3), so this module turns the raw
engine output into a short list of `FindingData` and picks question targets.
Analysis stays decoupled from LLM code (NFR-5.4 Maintainability).
"""
import ast
from dataclasses import asdict, dataclass, field
from typing import Optional

from adaptive_viva_ast import analyze_code

from ..config import get_settings

# Lower number = more interesting for a viva question.
PRIORITY = {
    "recursion": 1,
    "nested_loops": 2,
    "deep_nesting": 3,
    "high_complexity": 4,
    "long_function": 5,
    "while_loop": 6,
    "data_structure": 7,
    "general": 9,
}


@dataclass
class FindingData:
    detector: str
    name: Optional[str]
    start_line: int
    end_line: int
    node_type: str
    reason: str
    severity: str = "info"
    # internal key so questions can be matched back to findings
    key: str = field(default="")

    def as_target(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisOutput:
    success: bool
    raw: dict
    findings: list[FindingData]
    syntax_error: Optional[str] = None
    functions: list[dict] = field(default_factory=list)


def syntax_check(code: str) -> Optional[str]:
    """FR-4.2.4 / FR-4.6.1: return a human message with line number, or None if it parses."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        where = f"line {e.lineno}" + (f", column {e.offset}" if e.offset else "")
        text = f": `{e.text.strip()}`" if e.text and e.text.strip() else ""
        return f"SyntaxError on {where}: {e.msg}{text}"
    except ValueError as e:  # e.g. null bytes in source
        return f"File could not be parsed: {e}"


def _contained(inner: FindingData, outer: FindingData) -> bool:
    return inner is not outer and outer.start_line <= inner.start_line and inner.end_line <= outer.end_line


def _keep_outermost(items: list[FindingData]) -> list[FindingData]:
    return [f for f in items if not any(_contained(f, o) for o in items)]


def _nested_loops(tree: ast.AST) -> list[FindingData]:
    """Extra detector: a loop directly or indirectly inside another loop (possible O(n^2))."""
    loops = (ast.For, ast.AsyncFor, ast.While)
    out: list[FindingData] = []

    def owner_name(stack: list[ast.AST]) -> Optional[str]:
        for n in reversed(stack):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return n.name
        return None

    def visit(node: ast.AST, stack: list[ast.AST]):
        if isinstance(node, loops):
            # only count loops in the same function scope
            outer = None
            for n in reversed(stack):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    break
                if isinstance(n, loops):
                    outer = n
            if outer is not None:
                out.append(
                    FindingData(
                        detector="nested_loops",
                        name=owner_name(stack),
                        start_line=outer.lineno,
                        end_line=getattr(outer, "end_lineno", outer.lineno),
                        node_type=type(outer).__name__,
                        reason=f"Loop on line {node.lineno} is nested inside the loop on line {outer.lineno} "
                               f"(possible O(n^2) or worse).",
                        severity="warning",
                    )
                )
        for child in ast.iter_child_nodes(node):
            visit(child, stack + [node])

    visit(tree, [])
    # one finding per outer loop
    uniq: dict[tuple, FindingData] = {}
    for f in out:
        uniq.setdefault((f.start_line, f.end_line), f)
    return _keep_outermost(list(uniq.values()))


def _has_memo_decorator(tree: ast.AST, func_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for d in node.decorator_list:
                target = d.func if isinstance(d, ast.Call) else d
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                if name in {"lru_cache", "cache", "memoize", "memoized"}:
                    return True
    return False


def analyse(code: str) -> AnalysisOutput:
    s = get_settings()
    result = analyze_code(code, max_nesting_depth=s.max_nesting_depth, max_function_lines=s.max_function_lines)
    raw = result.to_dict()
    if not result.success:
        se = result.syntax_error or {}
        return AnalysisOutput(
            success=False, raw=raw, findings=[],
            syntax_error=f"SyntaxError on line {se.get('line')}: {se.get('message')}",
        )

    tree = ast.parse(code)
    findings: list[FindingData] = []

    # 1. engine flags we care about
    deep: list[FindingData] = []
    for flag in result.flags:
        if flag.category == "recursive_function":
            memo = _has_memo_decorator(tree, flag.function_name or "")
            reason = f"'{flag.function_name}' calls itself" + (
                " (memoised with a cache decorator)." if memo else "; no memoisation detected."
            )
            findings.append(FindingData("recursion", flag.function_name, flag.line_start, flag.line_end,
                                        flag.node_type, reason, "info"))
        elif flag.category == "long_function":
            findings.append(FindingData("long_function", flag.function_name, flag.line_start, flag.line_end,
                                        flag.node_type, flag.description, flag.severity))
        elif flag.category == "deep_nesting":
            deep.append(FindingData("deep_nesting", flag.function_name, flag.line_start, flag.line_end,
                                    flag.node_type, flag.description, flag.severity))
    findings += _keep_outermost(deep)

    # 2. complexity from the engine's function info
    for fn in result.functions:
        if fn.complexity >= s.high_complexity:
            findings.append(FindingData(
                "high_complexity", fn.name, fn.line_start, fn.line_end, "FunctionDef",
                f"'{fn.name}' has an estimated cyclomatic complexity of {fn.complexity} "
                f"(threshold {s.high_complexity}).", "warning"))

    # 3. nested loops (extra detector)
    findings += _nested_loops(tree)

    # 4. implementation decisions: while-loops and dict/set choices, one per function
    seen: set[tuple] = set()
    for d in result.implementation_decisions:
        kind, fn, line = d.get("type"), d.get("function"), d.get("line", 1)
        if kind == "while_loop" and ("while", fn) not in seen:
            seen.add(("while", fn))
            node = next((n for n in ast.walk(tree) if isinstance(n, ast.While) and n.lineno == line), None)
            end = getattr(node, "end_lineno", line) if node else line
            findings.append(FindingData("while_loop", fn, line, end, "While",
                                        "A while loop is used instead of a for loop; termination depends on "
                                        "the loop condition.", "info"))
        elif kind in ("dictionary", "set") and (kind, fn) not in seen:
            seen.add((kind, fn))
            findings.append(FindingData("data_structure", fn, line, line,
                                        "Dict" if kind == "dictionary" else "Set",
                                        f"A {kind} is chosen as the data structure here.", "info"))

    # stable order + keys
    findings.sort(key=lambda f: (f.start_line, PRIORITY.get(f.detector, 8)))
    for i, f in enumerate(findings):
        f.key = f"f{i + 1}"

    return AnalysisOutput(success=True, raw=raw, findings=findings,
                          functions=[fn.to_dict() for fn in result.functions])


def pick_targets(findings: list[FindingData], functions: list[dict], n_questions: int) -> list[FindingData]:
    """Choose what to ask about (FR-4.4.2, FR-4.4.5, FR-4.6.2).

    Most interesting findings first; if there are too few, add general comprehension
    targets on the largest functions, and finally on the module itself.
    """
    s = get_settings()
    n = max(1, n_questions)
    ranked = sorted(findings, key=lambda f: (PRIORITY.get(f.detector, 8), f.start_line))
    targets = ranked[:n]

    want = min(max(s.min_questions, len(targets)), n)
    used = {(t.name, t.start_line) for t in targets}
    asked = {t.name for t in targets}
    # functions with no question yet come first, then the most complex / longest
    for fn in sorted(functions, key=lambda f: (f["name"] in asked, -f["complexity"],
                                               -(f["line_end"] - f["line_start"]))):
        if len(targets) >= want:
            break
        if (fn["name"], fn["line_start"]) in used:
            continue
        targets.append(FindingData(
            "general", fn["name"], fn["line_start"], fn["line_end"], "FunctionDef",
            f"General comprehension of function '{fn['name']}' ({fn['arguments']} parameters, "
            f"{fn['loops']} loops, {fn['conditionals']} conditionals).", "info", key=f"g{len(targets) + 1}"))
        used.add((fn["name"], fn["line_start"]))
    if not targets:
        targets.append(FindingData("general", None, 1, 1, "Module",
                                   "General comprehension of the overall program.", "info", key="g1"))
    return targets


def snippet(code: str, start: int, end: int) -> str:
    s = get_settings()
    lines = code.splitlines()
    end = min(end, start + s.llm_snippet_max_lines - 1, len(lines))
    return "\n".join(f"{i:>4}| {lines[i - 1]}" for i in range(max(1, start), end + 1))
