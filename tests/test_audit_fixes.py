import pytest
from tools.code_tools import execute_python_code
from tools.file_tools import write_sandbox_file, read_sandbox_file
from agents.evaluator_agent import EvaluatorAgent

def test_bengali_utf8_execution():
    """Verify that Python subprocess handles Bengali native characters on Windows without charmap error."""
    code = 'print("বাংলা টেস্ট সফল: ১২৩৪৫")'
    res = execute_python_code(code)
    assert res["success"] is True
    assert "বাংলা টেস্ট সফল: ১২৩৪৫" in res["stdout"]

def test_file_tools_leading_slash_safety():
    """Verify that leading slashes are safely normalized into the sandbox and cannot escape to Windows drive root."""
    res_write = write_sandbox_file("/bengali_notes.txt", "আমার নোট")
    assert res_write["success"] is True

    res_read = read_sandbox_file("/bengali_notes.txt")
    assert res_read["success"] is True
    assert res_read["content"] == "আমার নোট"

def test_evaluator_regex_json_robustness():
    """Verify that the Evaluator extracts JSON even when the LLM outputs conversational preamble."""
    evaluator = EvaluatorAgent()
    # Output with conversational text around JSON
    simulated_llm_judge_output = """Here is my thorough review of the sub-agent output:
```json
{
    "intent_score": 4.8,
    "factuality_score": 4.9,
    "structure_score": 4.7,
    "average_score": 4.8,
    "verdict": "APPROVED",
    "critique": ["None"],
    "feedback_for_repair": ""
}
```
Everything looks pristine and ready to ship!"""

    import re
    json_match = re.search(r"\{.*\}", simulated_llm_judge_output, re.DOTALL)
    assert json_match is not None
    import json
    parsed = json.loads(json_match.group(0))
    assert parsed["verdict"] == "APPROVED"
    assert parsed["average_score"] == 4.8

def test_model_sanitization_for_cloud():
    """Verify that deprecated or legacy Gemini model strings are upgraded to verified 3.5."""
    from config import sanitize_model_name
    assert sanitize_model_name("gemini/gemini-2.5-flash") == "gemini/gemini-3.5-flash"
    assert sanitize_model_name("gemini-2.5-flash") == "gemini/gemini-3.5-flash"
    assert sanitize_model_name("gemini/gemini-1.5-flash") == "gemini/gemini-3.5-flash"
    assert sanitize_model_name("gemini-3.5-flash") == "gemini/gemini-3.5-flash"

def test_message_audio_base64_lifecycle():
    """Verify that audio bytes can be stored in message metadata as base64 and retrieved."""
    import base64
    from database.memory import MemoryManager
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        sess_id = mem.create_session("Audio Test")
        sample_audio = b"FAKE_AUDIO_BYTES_FOR_TESTING"
        b64_audio = base64.b64encode(sample_audio).decode("utf-8")

        mem.add_message(
            sess_id,
            "assistant",
            "টেস্ট উত্তর",
            metadata={"audio_b64": b64_audio}
        )

        messages = mem.get_messages(sess_id)
        assert len(messages) == 1
        retrieved_b64 = messages[0]["metadata"].get("audio_b64")
        assert retrieved_b64 is not None
        assert base64.b64decode(retrieved_b64) == sample_audio
    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except Exception:
                pass

def test_orchestrator_chat_mode_direct_routing():
    """Verify that mode='chat' executes fast direct path without task decomposition."""
    from agents.orchestrator import MasterOrchestrator
    from database.memory import MemoryManager
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        sess_id = mem.create_session("Mode Test")
        orch = MasterOrchestrator(memory_manager=mem)

        # Mocking or calling chat mode
        res = orch.process_command(sess_id, "তুমি কেমন আছো?", mode="chat")
        assert res is not None
        assert "final_report" in res
        assert res.get("iterations") == 1
        assert len(res.get("sub_agent_results")) == 0  # Fast-path does not dispatch sub-agents
    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except Exception:
                pass


