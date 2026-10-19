import os
import tempfile
import pytest
from pathlib import Path
from database.memory import MemoryManager

@pytest.fixture
def temp_memory():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = Path(f.name)
    manager = MemoryManager(db_path=temp_db)
    yield manager
    if temp_db.exists():
        try:
            os.remove(temp_db)
        except Exception:
            pass

def test_session_lifecycle(temp_memory):
    session_id = temp_memory.create_session("Test Work Session")
    assert session_id is not None
    
    sessions = temp_memory.list_sessions()
    assert any(s["id"] == session_id for s in sessions)
    
    # Message appending
    temp_memory.add_message(session_id, "user", "Hello agent")
    temp_memory.add_message(session_id, "assistant", "Hello! How can I help you?")
    
    msgs = temp_memory.get_messages(session_id)
    assert len(msgs) == 2
    assert msgs[0]["content"] == "Hello agent"
    assert msgs[1]["content"] == "Hello! How can I help you?"

def test_user_preferences(temp_memory):
    temp_memory.set_preference("tone", "strictly technical and formal")
    val = temp_memory.get_preference("tone")
    assert val == "strictly technical and formal"

def test_trajectory_and_evaluation_logging(temp_memory):
    session_id = temp_memory.create_session("Eval Session")
    traj_id = temp_memory.create_trajectory(session_id, "Analyze sales", {"tasks": 1})
    assert traj_id is not None

    temp_memory.log_evaluation(
        trajectory_id=traj_id,
        iteration=1,
        subagent_name="Data Specialist",
        score=4.5,
        verdict="APPROVED",
        critique="Good work",
        repaired_output="Final table"
    )

    temp_memory.complete_trajectory(traj_id, "Final pristine report", 1)
