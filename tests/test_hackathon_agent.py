import pytest
from unittest.mock import patch, MagicMock
from tools.hackathon_tools import fetch_devpost_hackathons, format_hackathon_summary, FEATURED_HACKATHONS
from agents.hackathon_agent import HackathonAgent
from agents.orchestrator import MasterOrchestrator

def test_fetch_devpost_hackathons_structure():
    """Verify fetch_devpost_hackathons returns well-formed hackathon items."""
    results = fetch_devpost_hackathons("AI", limit=3)
    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    for key in ["title", "url", "prize", "deadline", "platform"]:
        assert key in first, f"Missing key '{key}' in hackathon data"
        assert first[key] is not None

def test_format_hackathon_summary():
    """Verify format_hackathon_summary generates markdown with tables and links."""
    sample = [
        {
            "title": "Unit Test AI Hackathon 2026",
            "url": "https://test.devpost.com",
            "prize": "$25,000",
            "deadline": "2026-10-01",
            "themes": "Multi-agent testing",
            "platform": "Devpost",
            "mode": "Online"
        }
    ]
    summary = format_hackathon_summary(sample)
    assert "Unit Test AI Hackathon 2026" in summary
    assert "$25,000" in summary
    assert "https://test.devpost.com" in summary
    assert "| 🏆 হ্যাকাথন |" in summary

def test_format_hackathon_summary_empty():
    """Verify format_hackathon_summary handles empty list gracefully."""
    summary = format_hackathon_summary([])
    assert "কোনো সক্রিয় হ্যাকাথন খুঁজে পাওয়া যায়নি" in summary

def test_hackathon_agent_scouting_mode():
    """Verify HackathonAgent executes scouting mode and returns standardized contract."""
    agent = HackathonAgent()
    mock_llm_response = "### 🏆 শীর্ষ লাইভ হ্যাকাথন তালিকা\n1. Google Gemini Challenge"

    with patch("agents.hackathon_agent.call_llm", return_value=mock_llm_response) as mock_call:
        res = agent.run("Find me live AI hackathons")
        assert res["subagent"] == "Hackathon Scout & Mentor Specialist"
        assert res["output"] == mock_llm_response
        assert isinstance(res["sources"], list)
        assert isinstance(res["trajectory"], list)
        assert len(res["trajectory"]) > 0
        assert res["trajectory"][0]["action"] == "fetch_devpost_hackathons"

def test_hackathon_agent_mentoring_mode():
    """Verify HackathonAgent detects mentoring intent and outputs winning ideas and roadmap."""
    agent = HackathonAgent()
    mock_mentor_response = "### 💡 Top 3 Winning Ideas\n1. Autonomous Agent\n### ⏱️ 48-Hour Roadmap"

    with patch("agents.hackathon_agent.call_llm", return_value=mock_mentor_response) as mock_call:
        res = agent.run("Give me a 48h winning roadmap and project idea for Devpost AI hackathon")
        assert res["subagent"] == "Hackathon Scout & Mentor Specialist"
        assert res["output"] == mock_mentor_response
        assert res["trajectory"][0]["action"] == "mentoring_strategy_analysis"

def test_orchestrator_has_hackathon_specialist():
    """Verify MasterOrchestrator registers HackathonAgent in its squad."""
    orch = MasterOrchestrator()
    assert hasattr(orch, "hackathon_specialist")
    assert orch.hackathon_specialist.name == "Hackathon Scout & Mentor Specialist"

def test_telegram_bot_has_hackathon_handler():
    """Verify /hackathon and /briefing command handlers are registered in build_telegram_app."""
    from telegram_bot import build_telegram_app
    app = build_telegram_app("123456:FAKE_TOKEN_FOR_TEST")
    registered_commands = []
    for handler in app.handlers.get(0, []):
        if hasattr(handler, "commands"):
            registered_commands.extend(list(handler.commands))
    assert "hackathon" in registered_commands
    assert "briefing" in registered_commands
    assert "daily_hackathon" in registered_commands

def test_hackathon_agent_generate_daily_briefing():
    """Verify generate_daily_briefing produces structured 150-200 word briefing."""
    agent = HackathonAgent()
    mock_briefing = (
        "আসসালামু আলাইকুম স্যার! শুভ সকাল।\n\n"
        "📢 **তথ্য:** Google Gemini Global AI Challenge 2026, Devpost প্ল্যাটফর্মে অনুষ্ঠিত হচ্ছে। মোট প্রাইজ $1,000,000।\n"
        "🎯 **বিষয়বস্তু:** মাল্টিমোডাল এআই ও অটোনোমাস এজেন্টিক সিস্টেম তৈরি।\n"
        "💡 **আমাদের প্রজেক্ট সাজেশন:** আমরা একটি স্মার্ট ভয়েস-এনালাইসিস ভিত্তিক স্বাস্থ্যসেবা ট্রায়াজ এজেন্ট প্রজেক্ট তৈরি করতে পারি।\n\n"
        "স্যার, এই হ্যাকাথনের বিস্তারিত বিশ্লেষণ ও রোডম্যাপ জানতে নিচের বাটনে ক্লিক করুন।"
    )
    with patch("agents.hackathon_agent.call_llm", return_value=mock_briefing):
        res = agent.generate_daily_briefing()
        assert "briefing_text" in res
        assert "title" in res
        assert "url" in res
        assert res["briefing_text"] == mock_briefing
        assert len(res["briefing_text"].split()) <= 200

def test_register_daily_subscriber():
    """Verify register_daily_subscriber persists chat_id to SQLite memory."""
    from telegram_bot import register_daily_subscriber
    from database.memory import MemoryManager
    import json
    
    test_chat_id = 888777666
    register_daily_subscriber(test_chat_id)
    mem = MemoryManager()
    raw = mem.get_preference("daily_hackathon_subscribers", "[]")
    subscribers = json.loads(raw)
    assert test_chat_id in subscribers
