import pytest
from agents.evaluator_agent import EvaluatorAgent

def test_evaluator_deterministic_syntax_rejection():
    evaluator = EvaluatorAgent()
    # Output containing invalid python syntax
    bad_output = """Here is the solution:
```python
def broken_syntax(
    print("missing closing paren"
```
"""
    result = evaluator.evaluate_output(
        user_intent="Write a python function",
        subagent_name="Code Specialist",
        draft_output=bad_output
    )

    assert result["verdict"] == "REJECTED"
    assert result["passed_deterministic"] is False
    assert any("Syntax Error" in c for c in result["critique"])

def test_evaluator_deterministic_execution_error_rejection():
    evaluator = EvaluatorAgent()
    valid_syntax_output = """Here is code:
```python
print("Hello world")
```
"""
    result = evaluator.evaluate_output(
        user_intent="Execute command",
        subagent_name="Code Specialist",
        draft_output=valid_syntax_output,
        execution_context={"tool_errors": ["Subprocess failed with exit code 1"]}
    )

    assert result["verdict"] == "REJECTED"
    assert result["passed_deterministic"] is False
    assert any("Tool Execution Error" in c for c in result["critique"])
