import json
import os
import tempfile
from unittest.mock import patch

from agents.research_agent import ResearchAgent
from agents.coding_agent import CodingAgent
from agents.data_agent import DataAgent
from agents.hackathon_agent import HackathonAgent
from agents.client_hunter_agent import ClientHunterAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.orchestrator import MasterOrchestrator
from database.memory import MemoryManager
from tools.hackathon_tools import _extract_filter_keywords


def test_subagent_1_research_agent_query_extraction_and_fallback():
    """Verify ResearchAgent query extraction, URL deduplication, and deterministic fallback."""
    agent = ResearchAgent()
    assert agent.model is not None

    # 1. Mixed/conversational JSON query extraction + deduplication
    raw_queries = 'Here are queries:\n["AI Hackathon 2026", {"query": "ai hackathon 2026"}, "Bangladesh Tech News"]'
    extracted = agent._extract_queries(raw_queries, "fallback query")
    assert len(extracted) == 2
    assert extracted[0] == "AI Hackathon 2026"
    assert extracted[1] == "Bangladesh Tech News"

    # 2. Fallback report when LLM returns quota warning
    fake_results = [
        {"title": "Result A", "url": "https://example.com/a", "content": "Details about A"},
        {"title": "Result A Duplicate", "url": "https://example.com/a", "content": "Duplicate URL"},
        {"title": "Result B", "url": "https://example.com/b", "content": "Details about B"},
    ]
    with patch("agents.research_agent.call_llm", return_value="⚠️ সকল AI মডেল ও ব্যাকআপ সার্ভারে কোটা সীমা অতিক্রম করেছে"):
        with patch("agents.research_agent.web_search", return_value=fake_results):
            res = agent.run("বাংলাদেশে এআই গবেষণা")
            assert res["subagent"] == "Research & Fact-Checking Specialist"
            assert "আসসালামু আলাইকুম স্যার!" in res["output"]
            assert len(res["sources"]) == 2  # Deduplicated URLs


def test_subagent_2_coding_agent_code_extraction_and_stdout_append():
    """Verify CodingAgent case-insensitive code extraction, non-blocking execution, and verified stdout output."""
    agent = CodingAgent()
    assert agent.model is not None

    # Case-insensitive ```Python block extraction
    sample_md = "আসসালামু আলাইকুম স্যার!\n```Python\nprint('CODING_VERIFIED_99')\n```"
    extracted = agent._extract_python_code(sample_md)
    assert extracted == "print('CODING_VERIFIED_99')"

    with patch("agents.coding_agent.call_llm", return_value=sample_md):
        res = agent.run("একটি পাইথন স্ক্রিপ্ট লেখো")
        assert res["execution_result"]["success"] is True
        assert "CODING_VERIFIED_99" in res["output"]
        assert "স্যান্ডবক্স ভেরিফিকেশন আউটপুট" in res["output"]
        assert not res["tool_errors"]


def test_subagent_3_data_agent_self_repair_and_verified_stdout():
    """Verify DataAgent self-repair loop on broken calculation script and inclusion of computed stdout in output."""
    agent = DataAgent()
    assert agent.model is not None

    broken_md = "আসসালামু আলাইকুম স্যার!\n```python\nprint(10 / 0)\n```"
    repaired_md = "আসসালামু আলাইকুম স্যার!\n```python\nprint('TOTAL_REVENUE_BDT=125000')\n```"

    with patch("agents.data_agent.call_llm", side_effect=[broken_md, repaired_md]):
        res = agent.run("মাসিক রেভিনিউ হিসাব করো")
        assert res["calculation_result"]["success"] is True
        assert not res["tool_errors"]
        assert "TOTAL_REVENUE_BDT=125000" in res["output"]
        assert "ভেরিফাইড ক্যালকুলেশন রেজাল্ট" in res["output"]


def test_subagent_4_hackathon_agent_bengali_query_and_fresh_selection():
    """Verify HackathonAgent Bengali query keyword filtering, deduplication across days, and deterministic fallback."""
    agent = HackathonAgent()
    assert agent.model is not None

    # Bengali sentence without English topic keywords should not filter out English RSS items
    assert _extract_filter_keywords("চলমান সেরা হ্যাকাথনগুলো খুঁজে বের করো") == []
    # Bengali sentence with AI keyword should extract 'ai'
    assert "ai" in _extract_filter_keywords("চলমান সেরা এআই হ্যাকাথনগুলো খুঁজে বের করো")

    candidates = [
        {"title": "Hackathon One", "url": "https://devpost.com/h1", "prize": "$10,000", "deadline": "Open", "platform": "Devpost", "themes": "AI"},
        {"title": "Hackathon Two", "url": "https://devpost.com/h2", "prize": "$20,000", "deadline": "Open", "platform": "Devpost", "themes": "Web3"},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_file = os.path.join(tmpdir, "seen_hackathons.json")
        scoped_agent = HackathonAgent(seen_storage_path=seen_file)
        first_pick = scoped_agent._select_fresh_hackathon(candidates)
        second_pick = scoped_agent._select_fresh_hackathon(candidates)
        assert first_pick["url"] == "https://devpost.com/h1"
        assert second_pick["url"] == "https://devpost.com/h2"

        # Fallback daily briefing when LLM returns quota warning
        with patch("agents.hackathon_agent.call_llm", return_value="⚠️ কোটা শেষ"):
            with patch("agents.hackathon_agent.fetch_devpost_hackathons", return_value=candidates):
                brief = scoped_agent.generate_daily_briefing()
                assert "আসসালামু আলাইকুম স্যার!" in brief["briefing_text"]
                assert brief["hackathon"]["title"] in brief["briefing_text"]


def test_subagent_5_client_hunter_bengali_inflected_scoring():
    """Verify ClientHunterAgent handles Bengali inflected suffixes (ধানমন্ডির, সেন্টারের) without zeroing scores."""
    agent = ClientHunterAgent()
    assert agent.model is not None

    query = "ধানমন্ডির সেরা ডায়াগনস্টিক সেন্টারের লিড বের করো"
    candidate = {
        "name": "Popular Diagnostic Centre Ltd.",
        "category": "Healthcare & Diagnostics",
        "location": "Dhanmondi, Dhaka",
        "website": "https://www.populardiagnostic.com",
        "facebook": "https://www.facebook.com/populardiagnostic"
    }
    score = agent._score_candidate(candidate, query.lower())
    assert score > 0


def test_subagent_6_evaluator_agent_tier1_and_tier2_normalization():
    """Verify EvaluatorAgent Tier 1 empty/warning/case-insensitive AST checks and Tier 2 schema normalization."""
    ev = EvaluatorAgent()
    assert ev.model is not None

    # Empty output rejected in Tier 1
    res_empty = ev.evaluate_output("Test intent", "Research Specialist", "   ")
    assert res_empty["verdict"] == "REJECTED"
    assert res_empty["passed_deterministic"] is False

    # Unhandled LLM warning rejected in Tier 1
    res_warn = ev.evaluate_output("Test intent", "Research Specialist", "⚠️ সকল AI মডেল ব্যর্থ")
    assert res_warn["verdict"] == "REJECTED"
    assert res_warn["passed_deterministic"] is False

    # Case-insensitive ```Python syntax error caught in Tier 1
    res_py = ev.evaluate_output("Write code", "Code Specialist", "```Python\ndef broken(\n```")
    assert res_py["verdict"] == "REJECTED"
    assert any("Syntax Error" in c for c in res_py["critique"])

    # Tier 2 normalization when critique is a string instead of list
    raw_llm_json = json.dumps({
        "intent_score": "4.7",
        "factuality_score": 4.8,
        "structure_score": 4.9,
        "verdict": "approved",
        "critique": "Well structured output",
        "feedback_for_repair": ""
    })
    with patch("agents.evaluator_agent.call_llm", return_value=raw_llm_json):
        res_t2 = ev.evaluate_output("Explain AI", "Research Specialist", "আসসালামু আলাইকুম স্যার! এআই হলো...")
        assert res_t2["verdict"] == "APPROVED"
        assert isinstance(res_t2["critique"], list)
        assert res_t2["critique"] == ["Well structured output"]
        assert res_t2["intent_score"] == 4.7


def test_orchestrator_resilience_when_planner_or_synthesis_returns_warning():
    """Verify MasterOrchestrator preserves verified sub-agent output even if planner/synthesis LLM returns ⚠️."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        sess_id = mem.create_session("Resilience Test")
        orch = MasterOrchestrator(memory_manager=mem)

        with patch("agents.orchestrator.call_llm", return_value="⚠️ কোটা শেষ"), \
             patch("agents.coding_agent.call_llm", return_value="আসসালামু আলাইকুম স্যার!\n```python\nprint(2 + 2)\n```"), \
             patch("agents.evaluator_agent.call_llm", return_value="⚠️ কোটা শেষ"), \
             patch("agents.orchestrator.text_to_speech_bengali", return_value=b""):
            res = orch.process_command(sess_id, "পাইথন কোড দিয়ে ২+২ হিসাব করো", mode="work")
            assert res["final_report"]
            assert not res["final_report"].startswith("⚠️")
            assert "আসসালামু আলাইকুম স্যার!" in res["final_report"]
            assert "4" in res["final_report"]
    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except Exception:
                pass
