"""Viva question generation (FR-4.4.x).

Two generators share one interface:
  * LLMGenerator      - LiteLLM (any provider) + Instructor, Pydantic-validated, auto-retry (FR-4.4.4)
  * TemplateGenerator - offline, deterministic; used when LLM_MODEL is empty or the LLM keeps failing.

The LLM only receives AST-derived insights + short flagged snippets, never the whole file
(FR-4.4.1, NFR-5.3.5).
"""
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, create_model, model_validator

from ..config import get_settings
from .analysis import FindingData, snippet

log = logging.getLogger("avg.questions")

Difficulty = Literal["easy", "medium", "hard"]


class VivaQuestion(BaseModel):
    """The schema from the SRS: {question_text, related_line, related_node_type, difficulty}."""

    target_id: str = Field(description="The id of the target this question is about, e.g. 'f2'.")
    question_text: str = Field(min_length=15, max_length=400)
    related_line: int = Field(ge=1)
    related_node_type: str
    difficulty: Difficulty


class GeneratedQuestion(BaseModel):
    target_key: str
    question_text: str
    related_line: int
    related_node_type: str
    difficulty: str


def _question_set_model(targets: list[FindingData]):
    """Build a response model whose validator enforces BR-3 for *these* targets.

    Any violation raises a ValidationError, which Instructor feeds back to the LLM and retries.
    """
    by_key = {t.key: t for t in targets}

    def check(self):
        keys = [q.target_id for q in self.questions]
        missing = set(by_key) - set(keys)
        unknown = set(keys) - set(by_key)
        if unknown:
            raise ValueError(f"Unknown target_id(s) {sorted(unknown)}; use only {sorted(by_key)}.")
        if missing:
            raise ValueError(f"Missing a question for target_id(s) {sorted(missing)}.")
        for q in self.questions:
            t = by_key[q.target_id]
            if not (t.start_line <= q.related_line <= t.end_line):
                raise ValueError(
                    f"Question for {q.target_id} has related_line {q.related_line}, but it must be between "
                    f"{t.start_line} and {t.end_line}.")
        return self

    return create_model(
        "VivaQuestionSet",
        questions=(list[VivaQuestion], Field(min_length=len(targets))),
        __validators__={"check_targets": model_validator(mode="after")(check)},
    )


# ------------------------------------------------------------------ templates
_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "recursion": [
        ("Your function {name}() on line {line} calls itself. What is its base case, and what happens to the "
         "call stack for a large input?", "medium"),
        ("Could {name}() (line {line}) be written iteratively instead of recursively? What would you gain or "
         "lose?", "hard"),
    ],
    "nested_loops": [
        ("The loops starting on line {line} in {name}() are nested. What is the time complexity, and can you "
         "reduce it?", "hard"),
        ("Walk me through how many times the inner loop near line {line} runs for an input of size n.", "medium"),
    ],
    "deep_nesting": [
        ("The code around line {line} in {name}() is nested several levels deep. Why did you structure it this "
         "way, and how could you flatten it?", "medium"),
        ("Explain the exact condition under which the innermost block near line {line} executes.", "hard"),
    ],
    "high_complexity": [
        ("{name}() (line {line}) has many decision points. Which paths through it would you test first, and "
         "why?", "hard"),
        ("How would you split {name}() starting at line {line} into smaller functions?", "medium"),
    ],
    "long_function": [
        ("{name}() starting on line {line} is quite long. Summarise what it does in three steps.", "easy"),
        ("Which part of {name}() (line {line}) would you extract into a helper function, and why?", "medium"),
    ],
    "while_loop": [
        ("You used a while loop on line {line}. Why not a for loop, and how do you guarantee it terminates?",
         "medium"),
        ("What value makes the while loop on line {line} stop? Trace it for a small example.", "easy"),
    ],
    "data_structure": [
        ("Why did you choose a {node} on line {line}? What would change if you used a list instead?", "medium"),
        ("What is the lookup cost of the {node} you create on line {line}, and why does it matter here?", "easy"),
    ],
    "general": [
        ("Explain in your own words what {name}() starting on line {line} does and what it returns.", "easy"),
        ("Which input would make {name}() (line {line}) fail or behave unexpectedly?", "medium"),
    ],
}


class TemplateGenerator:
    name = "template"

    def generate(self, targets: list[FindingData], code: str, avoid: Optional[str] = None,
                 variant: int = 0) -> list[GeneratedQuestion]:
        out = []
        for t in targets:
            options = _TEMPLATES.get(t.detector, _TEMPLATES["general"])
            text, diff = options[variant % len(options)]
            if avoid and text.format(**self._fmt(t)) == avoid:
                text, diff = options[(variant + 1) % len(options)]
            out.append(GeneratedQuestion(
                target_key=t.key, question_text=text.format(**self._fmt(t)), related_line=t.start_line,
                related_node_type=t.node_type, difficulty=diff))
        return out

    @staticmethod
    def _fmt(t: FindingData) -> dict:
        node = {"Dict": "dictionary", "Set": "set"}.get(t.node_type, t.node_type)
        return {"name": t.name or "the program", "line": t.start_line, "node": node}


# ------------------------------------------------------------------ LLM
SYSTEM_PROMPT = """You are an examiner preparing an oral viva for a university programming assignment.
You receive structural insights extracted from a student's code by static (AST) analysis, each with an id,
line range, and a short code snippet. Write exactly ONE question per target.

Rules:
- Each question must be about that specific code element and mention the function name and/or line number.
- Ask about the student's reasoning: why they chose this approach, trade-offs, complexity, edge cases,
  what would happen if something changed. Do not ask trivia or generic textbook questions.
- related_line must be a line inside the target's line range.
- 15 to 400 characters per question. Mix difficulties (easy / medium / hard).
- Never include the answer in the question."""


def _user_prompt(targets: list[FindingData], code: str, avoid: Optional[str]) -> str:
    s = get_settings()
    parts = ["Targets:"]
    for t in targets:
        parts.append(
            f"\n[id={t.key}] detector={t.detector} function={t.name or '-'} node={t.node_type} "
            f"lines={t.start_line}-{t.end_line}\nwhy flagged: {t.reason}")
        if s.llm_send_snippets:
            parts.append("snippet:\n" + snippet(code, t.start_line, t.end_line))
    if avoid:
        parts.append(f"\nThe instructor rejected this previous question; write a clearly different one:\n{avoid}")
    return "\n".join(parts)


class LLMGenerator:
    def __init__(self, model: str, completion=None):
        self.model = model
        self.name = f"llm:{model}"
        self._completion = completion  # injectable for tests

    def generate(self, targets: list[FindingData], code: str, avoid: Optional[str] = None,
                 variant: int = 0) -> list[GeneratedQuestion]:
        import instructor  # imported lazily so tests/offline mode don't need network libs
        import litellm

        s = get_settings()
        mode = instructor.Mode.JSON if s.llm_mode.lower() == "json" else instructor.Mode.TOOLS
        client = instructor.from_litellm(self._completion or litellm.completion, mode=mode)
        model_cls = _question_set_model(targets)
        result = client.chat.completions.create(
            model=self.model,
            response_model=model_cls,
            max_retries=s.llm_max_retries,  # FR-4.4.4: malformed output -> automatic retry
            timeout=s.llm_timeout_seconds,
            temperature=0.7 if avoid else 0.4,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(targets, code, avoid)},
            ],
        )
        seen: set[str] = set()
        out = []
        for q in result.questions:
            if q.target_id in seen:  # keep one per target
                continue
            seen.add(q.target_id)
            out.append(GeneratedQuestion(target_key=q.target_id, question_text=q.question_text.strip(),
                                         related_line=q.related_line, related_node_type=q.related_node_type,
                                         difficulty=q.difficulty))
        return out


def generate(targets: list[FindingData], code: str, avoid: Optional[str] = None,
             variant: int = 0) -> tuple[list[GeneratedQuestion], str]:
    """Return (questions, generator_name). Falls back to templates if the LLM is off or fails."""
    s = get_settings()
    if s.llm_model:
        try:
            gen = LLMGenerator(s.llm_model)
            return gen.generate(targets, code, avoid, variant), gen.name
        except Exception as e:  # network, auth, retries exhausted...
            log.warning("LLM generation failed, using templates: %s", e)
            return TemplateGenerator().generate(targets, code, avoid, variant), "template (llm failed)"
    return TemplateGenerator().generate(targets, code, avoid, variant), "template"
