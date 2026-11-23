from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CodeFlag:
    """A notable implementation decision or structural code finding."""

    category: str
    description: str
    line_start: int
    line_end: int
    node_type: str
    function_name: Optional[str] = None
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "node_type": self.node_type,
            "function_name": self.function_name,
            "severity": self.severity,
        }


@dataclass
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    arguments: int
    loops: int
    conditionals: int
    recursive: bool
    complexity: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "arguments": self.arguments,
            "loops": self.loops,
            "conditionals": self.conditionals,
            "recursive": self.recursive,
            "complexity": self.complexity,
        }


@dataclass
class ASTAnalysisResult:
    success: bool
    language: str
    flags: list[CodeFlag] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    implementation_decisions: list[dict[str, Any]] = field(default_factory=list)
    syntax_error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "language": self.language,
            "flags": [flag.to_dict() for flag in self.flags],
            "functions": [function.to_dict() for function in self.functions],
            "implementation_decisions": self.implementation_decisions,
            "syntax_error": self.syntax_error,
        }
