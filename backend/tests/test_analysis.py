"""Unit tests for the analysis adapter and question generator (no API, no DB)."""
import pytest
from pydantic import ValidationError

from app.services.analysis import analyse, pick_targets, syntax_check
from app.services.questions import TemplateGenerator, _question_set_model, generate

NESTED = """def f(xs):
    for a in xs:
        if a:
            for b in xs:
                if b:
                    while a:
                        a -= 1
"""


def test_syntax_check_reports_line():
    assert syntax_check("x = 1\n") is None
    assert "line 2" in syntax_check("x = 1\ndef (:\n")


def test_nested_and_deep_nesting_deduplicated():
    r = analyse(NESTED)
    dets = [f.detector for f in r.findings]
    assert dets.count("nested_loops") == 1  # outermost only
    assert dets.count("deep_nesting") == 1
    assert "while_loop" in dets


def test_memoised_recursion_noted():
    code = "from functools import lru_cache\n@lru_cache\ndef f(n):\n    return n if n < 2 else f(n-1)\n"
    rec = next(f for f in analyse(code).findings if f.detector == "recursion")
    assert "memoised" in rec.reason


def test_targets_respect_limit_and_fallback():
    r = analyse(NESTED)
    assert len(pick_targets(r.findings, r.functions, 2)) == 2
    empty = analyse("x = 1\n")
    t = pick_targets(empty.findings, empty.functions, 5)
    assert t[0].detector == "general" and t[0].node_type == "Module"


def test_template_generator_one_per_target():
    r = analyse(NESTED)
    t = pick_targets(r.findings, r.functions, 5)
    qs = TemplateGenerator().generate(t, NESTED)
    assert [q.target_key for q in qs] == [x.key for x in t]


def test_llm_schema_validator_enforces_br3():
    r = analyse(NESTED)
    t = pick_targets(r.findings, r.functions, 1)
    M = _question_set_model(t)
    good = {"target_id": t[0].key, "question_text": "Why is this loop nested like this here?",
            "related_line": t[0].start_line, "related_node_type": "For", "difficulty": "hard"}
    M(questions=[good])
    with pytest.raises(ValidationError):
        M(questions=[{**good, "related_line": 999}])
    with pytest.raises(ValidationError):
        M(questions=[{**good, "target_id": "nope"}])


def test_llm_failure_falls_back(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("LLM_MODEL", "not-a-real-provider/model")
    get_settings.cache_clear()
    r = analyse(NESTED)
    qs, name = generate(pick_targets(r.findings, r.functions, 2), NESTED)
    assert name == "template (llm failed)" and len(qs) == 2
    get_settings.cache_clear()


def test_llm_path_retries_on_invalid_output(monkeypatch):
    """FR-4.4.4: a malformed/invalid LLM reply is rejected by the schema and retried (mocked LLM, no network)."""
    import json

    import litellm

    from app.config import get_settings
    from app.services.questions import LLMGenerator

    monkeypatch.setenv("LLM_MODE", "json")
    get_settings.cache_clear()
    code = "def f(n):\n    return f(n-1) if n else 0\n"
    r = analyse(code)
    t = pick_targets(r.findings, r.functions, 1)
    bad = {"target_id": t[0].key, "question_text": "Question pointing at a wrong line.", "related_line": 99,
           "related_node_type": "FunctionDef", "difficulty": "easy"}
    good = {**bad, "question_text": "What is the base case of f() on line 1?", "related_line": 1}
    replies = iter([json.dumps({"questions": [bad]}), json.dumps({"questions": [good]})])
    calls = []

    def fake_completion(**kw):
        calls.append(kw)
        return litellm.completion(model="gpt-4o-mini", messages=kw["messages"], mock_response=next(replies))

    qs = LLMGenerator("mock", completion=fake_completion).generate(t, code)
    assert len(calls) == 2
    assert qs[0].related_line == 1 and "base case" in qs[0].question_text
    # NFR-5.3.5: only the flagged snippet is sent, with the AST insight
    assert "detector=recursion" in str(calls[0]["messages"])
    get_settings.cache_clear()
