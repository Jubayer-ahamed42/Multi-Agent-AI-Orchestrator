"""Comprehensive test suite for SmartSalesAssistant, MessageDebouncer,
Executive 'Sir' Protocol, 1500 Daily Quota, and CRM/Telegram notifications.
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agents.smart_sales_assistant import (
    SmartSalesAssistant,
    MessageDebouncer,
    DailyQuotaTracker,
    GoogleSheetCRM,
    enforce_sir_protocol,
    classify_intent_rule_based,
    extract_lead_entities,
    send_hot_lead_telegram_alert,
    AGENCY_NAME,
    FOUNDER_NAME,
    OWNER_HANDOFF_STATEMENT,
    DAILY_FREE_QUOTA_LIMIT,
)
from agents.orchestrator import MasterOrchestrator
from database.memory import MemoryManager
from config import get_sales_api_key, get_sales_model


# =====================================================================
# 1. Zero Collision & Config Isolation Tests
# =====================================================================
def test_sales_closer_gemini_key_isolation():
    """Verify SmartSalesAssistant uses dedicated SALES_CLOSER_GEMINI_KEY and never touches GEMINI_API_KEY."""
    with patch.dict(os.environ, {
        "GEMINI_API_KEY": "main_project_key_DO_NOT_USE",
        "SALES_CLOSER_GEMINI_KEY": "dedicated_sales_key_12345",
        "SALES_MODEL_NAME": "gemini-2.5-flash"
    }):
        assert get_sales_api_key() == "dedicated_sales_key_12345"
        agent = SmartSalesAssistant()
        assert agent.api_key == "dedicated_sales_key_12345"
        assert agent.api_key != os.environ["GEMINI_API_KEY"]
        assert agent.temperature == 0.4
        assert agent.agency_name == "Be Smart With AI"
        assert agent.founder == "জুবায়ের আহমেদ"


def test_sales_model_custom_and_default():
    """Verify sales model defaults and sanitization."""
    with patch.dict(os.environ, {"SALES_MODEL_NAME": "gemini-2.5-flash"}):
        assert "gemini" in get_sales_model()


# =====================================================================
# 2. Daily Quota Tracker (1,500 Daily Free Requests) Tests
# =====================================================================
def test_daily_quota_tracker_increment_and_limits(tmp_path: Path):
    """Verify quota tracking persists, increments, and enforces the 1500 daily quota limit."""
    tracker_file = tmp_path / "test_quota_tracker.json"
    tracker = DailyQuotaTracker(tracker_path=tracker_file, limit=1500)

    assert tracker.get_count() == 0
    assert tracker.can_request() is True

    # Increment requests
    c1 = tracker.increment()
    assert c1 == 1
    assert tracker.get_count() == 1

    # Simulate hitting quota limit
    tracker._write_data({"date": tracker._get_today_str(), "count": 1500})
    assert tracker.get_count() == 1500
    assert tracker.can_request() is False


def test_quota_exhaustion_graceful_reply(tmp_path: Path):
    """Verify assistant provides graceful executive response when 1500 daily quota is reached."""
    tracker_file = tmp_path / "test_quota_tracker.json"
    tracker = DailyQuotaTracker(tracker_path=tracker_file, limit=1500)
    tracker._write_data({"date": tracker._get_today_str(), "count": 1500})

    with patch("agents.smart_sales_assistant.quota_tracker", tracker):
        agent = SmartSalesAssistant(api_key="mock_key")
        res = agent.run("আমাদের ই-কমার্সের জন্য WhatsApp AI বট লাগবে")
        assert "স্লট পূর্ণ" in res["output"] or "জুবায়ের আহমেদ" in res["output"]
        assert "স্যার" in res["output"]


# =====================================================================
# 3. Smart Message Buffer / Debouncer (5 - 10 Seconds) Tests
# =====================================================================
def test_message_debouncer_sync_bundling():
    """Verify sync accumulation and flush of rapid short messages: 'Hi' -> 'bhai' -> 'website a ai lagbe'."""
    debouncer = MessageDebouncer(buffer_seconds=7.0)
    user_id = "8801712345678"

    debouncer.add_message_sync(user_id, "Hi")
    debouncer.add_message_sync(user_id, "bhai")
    debouncer.add_message_sync(user_id, "website a ai lagbe")

    assert debouncer.get_buffered_messages(user_id) == ["Hi", "bhai", "website a ai lagbe"]

    bundled_text, raw_msgs = debouncer.flush(user_id)
    assert bundled_text == "Hi\nbhai\nwebsite a ai lagbe"
    assert raw_msgs == ["Hi", "bhai", "website a ai lagbe"]
    assert debouncer.get_buffered_messages(user_id) == []


@pytest.mark.asyncio
async def test_message_debouncer_async_reset_and_trigger():
    """Verify async debounce timer resets on consecutive incoming messages and bundles them."""
    # Use short buffer for test speed
    debouncer = MessageDebouncer(buffer_seconds=5.0)
    debouncer.buffer_seconds = 0.08  # Fast debounce for unit test

    received_bundles = []

    async def on_bundle(uid: str, text: str, msgs: list):
        await asyncio.sleep(0.01)  # Real coroutine suspension point to test against self-cancellation
        received_bundles.append({"uid": uid, "text": text, "msgs": msgs})

    # Send 3 rapid messages
    await debouncer.add_message_async("user_test", "Hello", on_bundle)
    await asyncio.sleep(0.02)
    await debouncer.add_message_async("user_test", "vai", on_bundle)
    await asyncio.sleep(0.02)
    await debouncer.add_message_async("user_test", "need sales bot", on_bundle)

    # Initially before buffer expires, callback not fired
    assert len(received_bundles) == 0

    # Wait for debounce window to lapse
    await asyncio.sleep(0.12)

    # Now bundle must be fired exactly once with all 3 messages concatenated
    assert len(received_bundles) == 1
    assert received_bundles[0]["uid"] == "user_test"
    assert received_bundles[0]["text"] == "Hello\nvai\nneed sales bot"
    assert received_bundles[0]["msgs"] == ["Hello", "vai", "need sales bot"]


# =====================================================================
# 4. Executive 'Sir' Protocol & Guardrail Tests
# =====================================================================
def test_enforce_sir_protocol_cleans_bhai_and_adds_greeting():
    """Verify enforce_sir_protocol replaces colloquial 'ভাই', 'vaiya', 'bhai' and ensures 'স্যার'."""
    sample_text = "আচ্ছা ভাই, আপনার কোম্পানির প্যাকেজের দাম কত ভাইয়া?"
    cleaned = enforce_sir_protocol(sample_text)

    # Must NOT contain 'ভাই' or 'ভাইয়া'
    assert "ভাই" not in cleaned
    assert "ভাইয়া" not in cleaned
    # Must contain 'স্যার'
    assert "স্যার" in cleaned
    # Must contain 'আসসালামু আলাইকুম'
    assert "আসসালামু আলাইকুম" in cleaned


def test_enforce_sir_protocol_handles_transliterated_bhai():
    """Verify transliterated 'vai', 'bhai', 'bro' are eliminated."""
    sample_text = "Hello vai, eita kivabe kaj kore bro?"
    cleaned = enforce_sir_protocol(sample_text)

    assert "vai" not in cleaned.lower()
    assert "bro" not in cleaned.lower()
    assert "স্যার" in cleaned


def test_owner_handoff_statement_in_closing():
    """Verify the exact required owner handoff phrase is used."""
    assert "জুবায়ের আহমেদ স্যার" in OWNER_HANDOFF_STATEMENT
    assert "প্রধান সফটওয়্যার আর্কিটেক্ট" in OWNER_HANDOFF_STATEMENT
    assert "নোটিফিকেশন পাঠিয়ে দিয়েছি" in OWNER_HANDOFF_STATEMENT


# =====================================================================
# 5. Smart Intent Classification Tests
# =====================================================================
def test_intent_classification_rule_based():
    """Verify deterministic intent classification for buyer, student, and spam."""
    assert classify_intent_rule_based("আমাদের ওয়েবসাইটের জন্য একটি AI WhatsApp Bot লাগবে") == "BUYER"
    assert classify_intent_rule_based("সার্ভিসের দাম কত পড়বে?") == "BUYER"
    assert classify_intent_rule_based("what is ai and how does it work?") == "STUDENT"
    assert classify_intent_rule_based("এআই কি এবং মেশিন লার্নিং কিভাবে শিখব?") == "STUDENT"
    assert classify_intent_rule_based("Free crypto lottery click here") == "SPAM"
    assert classify_intent_rule_based("এটি ভুল নম্বর") == "SPAM"


def test_intent_classification_llm_fallback():
    """Verify LLM intent classification when rule-based returns None."""
    agent = SmartSalesAssistant(api_key="mock_key")
    with patch("agents.smart_sales_assistant.call_sales_llm", return_value='{"intent": "BUYER"}'):
        intent = agent.classify_intent("আমরা অটোমেশন করার কথা ভাবছি", [])
        assert intent == "BUYER"

    with patch("agents.smart_sales_assistant.call_sales_llm", return_value='{"intent": "STUDENT"}'):
        intent = agent.classify_intent("আমার ভার্সিটির একটা প্রজেক্টের ধারণা চাই", [])
        assert intent == "STUDENT"


# =====================================================================
# 6. Entity Extraction, Google Sheets CRM & Telegram Hot-Lead Tests
# =====================================================================
def test_extract_lead_entities():
    """Verify extraction of phone, website, and name from incoming user messages."""
    text = "আমার নাম কামরুল হাসান। ফোন: 01712-345678, ওয়েবসাইট: https://myfashionbd.com"
    entities = extract_lead_entities(text)
    assert entities["phone"] == "+8801712345678"
    assert entities["website"] == "https://myfashionbd.com"
    assert "কামরুল" in entities["name"]


def test_google_sheet_crm_storage(tmp_path: Path):
    """Verify CRM stores qualified leads in local CSV and JSON stores."""
    csv_file = tmp_path / "crm_leads.csv"
    json_file = tmp_path / "crm_leads.json"
    crm = GoogleSheetCRM(csv_path=csv_file, json_path=json_file)

    lead = crm.append_lead(
        name="Abdur Rahman",
        phone="+8801819999888",
        website="https://eshopbd.com",
        requirements="24/7 AI WhatsApp Closer Bot",
        summary="E-commerce store looking for 24/7 sales closer bot."
    )

    assert csv_file.exists()
    assert json_file.exists()

    # Check CSV contents
    content = csv_file.read_text(encoding="utf-8")
    assert "Abdur Rahman" in content
    assert "+8801819999888" in content
    assert "https://eshopbd.com" in content

    # Check JSON contents
    leads = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(leads) == 1
    assert leads[0]["name"] == "Abdur Rahman"


def test_telegram_hot_lead_alert_formatting():
    """Verify Telegram alert formatting matches exact piped specification:
    '🚨 নতুন হট-লিড! নাম: [XYZ] | ফোন: [01...] | ওয়েবসাইট: [URL] | চাহিদা: [Summary]। স্যার, দ্রুত ক্লায়েন্টের সাথে যোগাযোগ করুন!'
    """
    lead_data = {
        "name": "Zubair",
        "phone": "+8801711223344",
        "website": "https://zubairtech.com",
        "summary": "AI Customer Support & WhatsApp Lead Closer"
    }

    # Test with simulated HTTP 200
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.__enter__.return_value = fake_resp

    with patch("urllib.request.urlopen", return_value=fake_resp) as mock_url:
        success = send_hot_lead_telegram_alert(lead_data, bot_token="123456:FAKE_TOKEN")
        assert success is True
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        expected_text = (
            "🚨 নতুন হট-লিড! নাম: Zubair | ফোন: +8801711223344 | "
            "ওয়েবসাইট: https://zubairtech.com | চাহিদা: AI Customer Support & WhatsApp Lead Closer। "
            "স্যার, দ্রুত ক্লায়েন্টের সাথে যোগাযোগ করুন!"
        )
        assert payload["text"] == expected_text


def test_telegram_hot_lead_alert_safe_missing_token():
    """Verify Telegram alert safely returns False when token is missing without crashing."""
    lead_data = {"name": "Test", "phone": "017", "website": "", "summary": ""}
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}):
        res = send_hot_lead_telegram_alert(lead_data, bot_token="")
        assert res is False


# =====================================================================
# 7. Edge Cases & Guardrail Integrity Tests
# =====================================================================
def test_enforce_sir_protocol_preserves_technical_words():
    """Verify technical loanwords starting with 'ভাই' (ভাইরাস, ভাইরাল, ভাইস, ভাইব্রেশন) are NOT mangled."""
    samples = [
        "আমাদের ওয়েবসাইটে কি ভাইরাসের আক্রমণ হতে পারে?",
        "এআই ভিডিও কি ভাইরাল করা সম্ভব?",
        "ভাইস প্রেসিডেন্ট হিসেবে আমি দায়িত্ব পালন করছি।",
        "ভাইটামিন ও পুষ্টি সম্পর্কিত তথ্য দিন।",
    ]
    for text in samples:
        cleaned = enforce_sir_protocol(text)
        assert "ভাইরাস" in cleaned or "ভাইরাল" in cleaned or "ভাইস" in cleaned or "ভাইটামিন" in cleaned
        assert "স্যার আক্রমণ" not in cleaned
        assert "স্যার করা সম্ভব" not in cleaned


def test_intent_classification_priority_commercial_with_ai_ki():
    """Verify commercial intent is prioritized over general question starters like 'এআই কি'."""
    buyer_msg = "এআই কি আমাদের বিজনেসে কাজে লাগবে? আমাদের ওয়েবসাইটের জন্য খরচ কত?"
    intent = classify_intent_rule_based(buyer_msg)
    assert intent == "BUYER"


def test_initial_greeting_does_not_falsely_trigger_lead_or_handoff():
    """Verify a simple 'Hi' from WhatsApp does NOT prematurely save a lead or conclude with handoff."""
    agent = SmartSalesAssistant(api_key="mock_key")
    result = agent.run("Hi", sender_phone="+8801712345678", session_id="test_greeting_sess")

    assert result["intent"] == "BUYER"
    # Must NOT save incomplete lead for a greeting
    assert result["lead_saved"] is False
    assert result["lead_data"] is None
    # Must ask consultative questions, NOT prematurely claim handoff was sent
    assert "জুবায়ের আহমেদ স্যার-কে আপনার চাহিদার বিস্তারিত নোটিফিকেশন পাঠিয়ে দিয়েছি" not in result["output"]
    assert "স্যার" in result["output"]


def test_lead_deduplication_in_multi_turn_session(tmp_path: Path):
    """Verify subsequent turns in the same conversation do not spam duplicate CRM rows or duplicate alerts."""
    csv_file = tmp_path / "dedup_leads.csv"
    json_file = tmp_path / "dedup_leads.json"
    crm = GoogleSheetCRM(csv_path=csv_file, json_path=json_file)

    mem_db = tmp_path / "test_mem.db"
    mem = MemoryManager(db_path=mem_db)
    sess_id = mem.create_session("Multi-turn Lead Test")

    agent = SmartSalesAssistant(api_key="mock_key", memory_manager=mem)
    agent.crm = crm

    mock_llm_reply = "আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। আপনার বট তৈরি করতে পারব।"

    with patch("agents.smart_sales_assistant.call_sales_llm", return_value=mock_llm_reply), \
         patch("agents.smart_sales_assistant.send_hot_lead_telegram_alert", return_value=True) as mock_alert:

        # Turn 1: Client provides details
        t1_msg = "আমার নাম তারেক, ফোন 01711999888, ওয়েবসাইট: https://tarekstore.com। আমাদের WhatsApp বট লাগবে।"
        r1 = agent.run(t1_msg, session_id=sess_id)
        assert r1["lead_saved"] is True
        assert mock_alert.call_count == 1

        # Turn 2: Follow-up question in the same session
        t2_msg = "আচ্ছা, ডেলিভারি কতদিনে পাওয়া যাবে?"
        r2 = agent.run(t2_msg, session_id=sess_id)

        # Must NOT re-save duplicate row or re-alert Telegram
        assert r2["lead_saved"] is False
        assert mock_alert.call_count == 1  # Still 1, not 2!


def test_clean_entity_extraction_edge_cases():
    """Verify clean entity extraction handles website name vs personal name and stop words properly."""
    # 1. Website name should NOT be extracted as personal name
    res1 = extract_lead_entities("আমাদের ওয়েবসাইটের নাম https://myshop.com")
    assert res1["name"] is None
    assert res1["website"] == "https://myshop.com"

    # 2. Personal name followed by phone should not swallow 'ফোন'
    res2 = extract_lead_entities("আমার নাম তানভীর হোসেন ফোন 01712345678")
    assert res2["name"] == "তানভীর হোসেন"
    assert res2["phone"] == "+8801712345678"


def test_whatsapp_webhook_verification_and_router():
    """Verify WhatsApp webhook verification GET and router endpoints."""
    try:
        import fastapi
        from fastapi.testclient import TestClient
        has_fastapi = True
    except ImportError:
        has_fastapi = False

    from agents.whatsapp_webhook import create_whatsapp_app, create_whatsapp_router, WHATSAPP_VERIFY_TOKEN

    if not has_fastapi:
        # Verify graceful fallback when FastAPI is not present in runtime environment
        assert create_whatsapp_app() is None
        assert create_whatsapp_router() is None
    else:
        app = create_whatsapp_app()
        assert app is not None
        client = TestClient(app)

        # 1. GET Verification with correct token
        res = client.get("/webhook/whatsapp", params={
            "hub.mode": "subscribe",
            "hub.verify_token": WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE_ACCEPTED_123"
        })
        assert res.status_code == 200
        assert res.text == "CHALLENGE_ACCEPTED_123"

        # 2. GET Verification with wrong token -> 403
        res_bad = client.get("/webhook/whatsapp", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "FAIL"
        })
        assert res_bad.status_code == 403


# =====================================================================
# 8. Sub-Agent End-to-End Execution Tests
# =====================================================================
def test_buyer_flow_saves_lead_and_triggers_handoff(tmp_path: Path):
    """Verify buyer inquiry with phone/website extracts lead, records to CRM, and includes owner handoff."""
    csv_file = tmp_path / "test_leads.csv"
    json_file = tmp_path / "test_leads.json"
    crm = GoogleSheetCRM(csv_path=csv_file, json_path=json_file)

    mem = MemoryManager(db_path=tmp_path / "test_buyer_mem.db")
    agent = SmartSalesAssistant(api_key="mock_key", memory_manager=mem)
    agent.crm = crm

    mock_llm_reply = (
        "আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। "
        "স্যার, আপনার ই-কমার্স ওয়েবসাইটের জন্য আমাদের 24/7 AI WhatsApp Closer Bot নিখুঁত সমাধান।"
    )

    with patch("agents.smart_sales_assistant.call_sales_llm", return_value=mock_llm_reply), \
         patch("agents.smart_sales_assistant.send_hot_lead_telegram_alert", return_value=True):

        msg = "আমার নাম রফিক, ফোন: 01715-000000, ওয়েবসাইট: https://rafikstore.com। আমাদের WhatsApp Bot লাগবে।"
        result = agent.run(msg)

        assert result["intent"] == "BUYER"
        assert result["lead_saved"] is True
        assert result["lead_data"]["phone"] == "+8801715000000"
        assert result["lead_data"]["website"] == "https://rafikstore.com"
        # Must strictly have 'স্যার' and the owner handoff statement
        assert "স্যার" in result["output"]
        assert "জুবায়ের আহমেদ স্যার" in result["output"]
        assert "ভাই" not in result["output"]


def test_student_flow_no_sales_pitch():
    """Verify student flow politely answers the question without offering commercial packages."""
    agent = SmartSalesAssistant(api_key="mock_key")
    mock_student_reply = (
        "আসসালামু আলাইকুম স্যার। AI (Artificial Intelligence) বা কৃত্রিম বুদ্ধিমত্তা হলো "
        "কম্পিউটার বিজ্ঞানের একটি শাখা যা যন্ত্রকে মানুষের মতো চিন্তা ও সিদ্ধান্ত নেওয়ার ক্ষমতা প্রদান করে।"
    )

    with patch("agents.smart_sales_assistant.call_sales_llm", return_value=mock_student_reply):
        result = agent.run("স্যার, এআই কি এবং কিভাবে কাজ করে একটু বলবেন?")
        assert result["intent"] == "STUDENT"
        assert result["lead_saved"] is False
        assert "স্যার" in result["output"]
        assert "ভাই" not in result["output"]


def test_spam_flow_official_boundary():
    """Verify spam / wrong number query returns polite agency boundary."""
    agent = SmartSalesAssistant(api_key="mock_key")
    result = agent.run("Free crypto casino lottery click here")

    assert result["intent"] == "SPAM"
    assert "Be Smart With AI" in result["output"]
    assert "অফিশিয়াল সাপোর্ট ডেস্ক" in result["output"]
    assert "স্যার" in result["output"]


# =====================================================================
# 9. Orchestrator Integration Test
# =====================================================================
def test_orchestrator_routes_to_smart_sales():
    """Verify MasterOrchestrator can plan and dispatch to the new smart_sales subagent."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        sess_id = mem.create_session("Sales Route Test")
        orch = MasterOrchestrator(memory_manager=mem)

        assert hasattr(orch, "sales_assistant")
        assert orch.sales_assistant.agency_name == "Be Smart With AI"

        sales_plan = json.dumps({
            "summary": "ক্লায়েন্টের সাথে সেলস কনসালটেশন পরিচালনা",
            "subtasks": [{"agent": "smart_sales", "task_description": "Be Smart With AI সার্ভিসের বিস্তারিত ও দাম কত?"}]
        })

        mock_sales_output = (
            "আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। "
            "স্যার, আমাদের 24/7 AI WhatsApp Closer Bot আপনার ব্যবসার প্রতিটি লিড স্বয়ংক্রিয়ভাবে রূপান্তর করবে।"
        )

        with patch("agents.orchestrator.call_llm", return_value=sales_plan), \
             patch.object(orch.sales_assistant, "run", return_value={
                 "subagent": "Smart Sales Assistant",
                 "output": mock_sales_output,
                 "intent": "BUYER",
                 "lead_saved": False,
                 "tool_errors": []
             }), \
             patch("agents.evaluator_agent.call_llm", return_value=json.dumps({
                 "intent_score": 5.0,
                 "factuality_score": 5.0,
                 "structure_score": 5.0,
                 "verdict": "APPROVED",
                 "critique": ["Excellent sales consultation"],
                 "feedback_for_repair": ""
             })), \
             patch("agents.orchestrator.text_to_speech_bengali", return_value=b""):

            res = orch.process_command(sess_id, "Be Smart With AI সার্ভিসের বিস্তারিত ও দাম কত?", mode="work")
            assert res["final_report"]
            assert "Be Smart With AI" in res["final_report"]
            assert "স্যার" in res["final_report"]
    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except Exception:
                pass
