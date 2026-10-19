import json
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from agents.client_hunter_agent import (
    ClientHunterAgent,
    ScannedCompanyStore,
    BusinessXRayScanner,
    DigitalHealthAndRevenueCalculator,
    sanitize_whatsapp_number,
    OFFICIAL_SIGNATURE_BLOCK,
)
from agents.orchestrator import MasterOrchestrator
from telegram_bot import (
    build_telegram_app,
    hunt_command,
    execute_and_send_client_hunt,
    send_client_hunter_step1,
    send_client_hunter_step2,
)


def test_scanned_company_store_deduplication(tmp_path: Path):
    """Verify ScannedCompanyStore persists scanned companies and never allows duplicates."""
    db_file = tmp_path / "scanned_companies.json"
    store = ScannedCompanyStore(storage_path=db_file)

    assert not store.is_scanned("Popular Diagnostic Centre Ltd.", "https://www.populardiagnostic.com")

    store.mark_scanned({
        "name": "Popular Diagnostic Centre Ltd.",
        "website": "https://www.populardiagnostic.com",
        "category": "Diagnostic Center",
        "location": "Dhanmondi, Dhaka",
        "phone": "+8809613787801",
        "health_score": 34
    })

    # Must detect duplicate by name OR by domain
    assert store.is_scanned("Popular Diagnostic Centre Ltd.", "")
    assert store.is_scanned("Different Name", "https://populardiagnostic.com/")
    assert len(store.get_history()) == 1


def test_client_hunter_never_repeats_company(tmp_path: Path):
    """Verify consecutive hunts never return the same company twice."""
    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)

    seen_names = set()
    with patch.object(agent.scanner, "scan_website", return_value={"is_live": True, "http_status": 200, "has_ssl": True}):
        for _ in range(5):
            wf = agent.execute_hunt_workflow(query="", mark_as_scanned=True)
            comp_name = wf["company"]["name"]
            assert comp_name not in seen_names, f"Duplicate company returned: {comp_name}"
            seen_names.add(comp_name)


def test_business_xray_scanner_html_detection():
    """Verify BusinessXRayScanner detects Meta Pixel (fbq), Google Analytics (gtag/gtm), Chatbot, Viewport, SEO, and Booking signals."""
    sample_html = b"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Hospital & Diagnostic Dhaka</title>
        <meta name="description" content="Best private hospital and diagnostic center in Dhaka.">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script>
            fbq('init', '1234567890');
            gtag('config', 'G-ABCDEF1234');
        </script>
        <script type="application/ld+json">{"@type": "Hospital"}</script>
    </head>
    <body>
        <h1>Welcome to Test Hospital</h1>
        <a href="/book-now">Online Appointment</a>
        <a href="https://wa.me/8801711223344">WhatsApp Us</a>
        <a href="#">Broken Link 1</a>
        <script src="https://embed.tawk.to/12345/default"></script>
        <p>Contact: info@testhospitalbd.com | +880 1711-223344</p>
    </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_html
    mock_resp.status = 200
    mock_resp.headers = {"Strict-Transport-Security": "max-age=31536000"}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=mock_resp):
        scan = BusinessXRayScanner.scan_website("https://testhospitalbd.com")

    assert scan["is_live"] is True
    assert scan["has_ssl"] is True
    assert scan["has_meta_pixel"] is True
    assert scan["has_google_analytics"] is True
    assert scan["has_ai_chatbot"] is True
    assert scan["has_whatsapp_widget"] is True
    assert scan["has_viewport_meta"] is True
    assert scan["has_booking_or_order"] is True
    assert scan["has_title"] is True
    assert scan["has_meta_description"] is True
    assert scan["has_h1"] is True
    assert scan["has_schema_ld"] is True
    assert scan["empty_links_count"] == 1
    assert "info@testhospitalbd.com" in scan["discovered_emails"]


def test_step1_and_step2_messages_complete_formatting(tmp_path: Path):
    """Verify Step 1 (Audit Report) and Step 2 (Proposal Letter) contain all mandatory sections, BDT pricing, and Jubayer Ahamed's signature."""
    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)

    mock_scan = {
        "url": "https://www.populardiagnostic.com",
        "is_live": True,
        "http_status": 200,
        "load_time_sec": 3.4,
        "page_size_kb": 180.5,
        "has_ssl": True,
        "has_meta_pixel": False,
        "meta_pixel_signals": [],
        "has_google_analytics": False,
        "ga_signals": [],
        "has_ai_chatbot": False,
        "chatbot_signals": [],
        "has_whatsapp_widget": False,
        "has_viewport_meta": True,
        "has_booking_or_order": False,
        "booking_signals": [],
        "has_title": True,
        "title_text": "Popular Diagnostic Centre",
        "has_meta_description": False,
        "meta_description_text": "",
        "has_h1": True,
        "has_schema_ld": False,
        "empty_links_count": 5,
        "security_headers_present": [],
        "discovered_emails": ["info@populardiagnostic.com"],
        "discovered_phones": ["+880 9613-787801"],
        "scan_mode": "live_http"
    }

    with patch.object(agent.scanner, "scan_website", return_value=mock_scan):
        res = agent.execute_hunt_workflow(query="diagnostic", mark_as_scanned=True)

    msg1 = res["audit_report_message"]
    msg2 = res["proposal_letter_message"]

    # Check Persona & Greeting
    assert "আসসালামু আলাইকুম স্যার!" in msg1
    assert "SMART AI ASSISTANT" in msg1

    # Check all 5 mandatory sections in Message 1
    assert "১. কোম্পানির প্রোফাইল ও যোগাযোগ" in msg1
    assert "Decision-Maker Finder" in msg1
    assert "২. ১০-পয়েন্ট টেকনিক্যাল ও মার্কেটিং এক্স-রে" in msg1
    assert "fbq" in msg1 and "gtag" in msg1
    assert "24/7 AI Chatbot" in msg1
    assert "AI Review Analysis" in msg1
    assert "Active Ad-Spend Signal" in msg1
    assert "Side-by-Side Competitor Battle Card" in msg1
    assert "৩. বিজনেস হেলথ স্কোর ও টাকার অংকে মাসিক ক্ষতি" in msg1
    assert "/100" in msg1
    assert "BDT" in msg1
    assert "৪. আমাদের সমাধান" in msg1
    assert "৫. আমরা কত টাকা ডিমান্ড করব?" in msg1
    assert "প্রস্তাবিত ডিমান্ড প্রাইস (Recommended Asking Price)" in msg1
    assert "সর্বনিম্ন ক্লোজিং প্রাইস (Minimum Walk-Away Price)" in msg1
    assert "মাসিক মেইনটেন্যান্স চার্জ (Monthly Retainer)" in msg1

    # Check Message 2 (Proposal Letter + Official Signature + 1-click wa.me link)
    assert "আসসালামু আলাইকুম স্যার!" in msg2
    assert "**Jubayer Ahamed**" in msg2
    assert "*AI Automation, Software & Web Development Specialist | Be Smart With AI*" in msg2
    assert "https://wa.me/8801610594042" in msg2
    assert "+880 1610-594042" in msg2
    assert "https://www.facebook.com/besmartwithaipro" in msg2
    assert "https://github.com/Jubayer-ahamed42" in msg2
    assert res["company_whatsapp_url"] in msg2
    assert res["company_whatsapp_url"].startswith("https://wa.me/880")


def test_orchestrator_has_client_hunter():
    """Verify MasterOrchestrator registers ClientHunterAgent."""
    orch = MasterOrchestrator()
    assert hasattr(orch, "client_hunter")
    assert orch.client_hunter.name == "ClientHunter & Business X-Ray Sub-Agent"


def test_telegram_bot_registers_hunt_commands():
    """Verify /hunt and /client_hunt commands are registered in build_telegram_app."""
    app = build_telegram_app("123456:FAKE_TOKEN_FOR_TEST")
    registered_commands = []
    for handler in app.handlers.get(0, []):
        if hasattr(handler, "commands"):
            registered_commands.extend(list(handler.commands))
    assert "hunt" in registered_commands
    assert "client_hunt" in registered_commands


@pytest.mark.asyncio
async def test_hunt_command_fast_and_standard_delay():
    """Verify /hunt fast uses 10s delay and standard /hunt uses 600s (10 min) delay."""
    update = MagicMock()
    update.effective_chat.id = 999888777
    update.effective_user.id = 999888777
    status_msg = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.application = MagicMock()

    # Case 1: /hunt fast restaurant
    context.args = ["fast", "restaurant"]
    with patch("telegram_bot.execute_and_send_client_hunt", new_callable=AsyncMock) as mock_exec:
        await hunt_command(update, context)
        mock_exec.assert_awaited_once_with(
            context.application,
            chat_id=999888777,
            query_str="restaurant",
            delay_seconds=10
        )

    # Case 2: /hunt hospital dhaka (standard 600s delay)
    context.args = ["hospital", "dhaka"]
    with patch("telegram_bot.execute_and_send_client_hunt", new_callable=AsyncMock) as mock_exec_std:
        await hunt_command(update, context)
        mock_exec_std.assert_awaited_once_with(
            context.application,
            chat_id=999888777,
            query_str="hospital dhaka",
            delay_seconds=600
        )


def test_sanitize_whatsapp_number_edge_cases():
    """Verify phone number normalization handles empty, local 01..., and +880 formats."""
    assert sanitize_whatsapp_number("") == "8801700000000"
    assert sanitize_whatsapp_number("01610-594042") == "8801610594042"
    assert sanitize_whatsapp_number("+880 1610-594042") == "8801610594042"
    assert sanitize_whatsapp_number("invalid_phone") == "8801700000000"


def test_scanner_empty_and_unreachable_urls():
    """Verify BusinessXRayScanner handles empty or unreachable URLs gracefully without raising."""
    empty_res = BusinessXRayScanner.scan_website("")
    assert empty_res["is_live"] is False
    assert empty_res["scan_mode"] == "no_website"

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Timed out")):
        timeout_res = BusinessXRayScanner.scan_website("https://unreachable-domain-test.com")
        assert timeout_res["is_live"] is False
        assert "TimeoutError" in timeout_res["scan_mode"]


def test_pool_exhaustion_dynamic_fallback(tmp_path: Path):
    """Verify that even if all 12 curated businesses are already scanned, agent generates unique dynamic fallback."""
    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)
    seen = set()
    with patch.object(agent.scanner, "scan_website", return_value={"is_live": False, "scan_mode": "offline"}):
        for _ in range(15):
            wf = agent.execute_hunt_workflow(query="", mark_as_scanned=True)
            name = wf["company"]["name"]
            assert name not in seen
            seen.add(name)
    assert len(seen) == 15


@pytest.mark.asyncio
async def test_telegram_step1_and_step2_delivery(tmp_path: Path):
    """Verify send_client_hunter_step1 and send_client_hunter_step2 send messages with proper reply_markup."""
    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)
    with patch.object(agent.scanner, "scan_website", return_value={"is_live": True, "http_status": 200, "has_ssl": True}):
        wf = agent.execute_hunt_workflow(query="hotel", mark_as_scanned=True)

    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()

    await send_client_hunter_step1(mock_app, chat_id=12345, workflow_data=wf, delay_seconds=10)
    assert mock_app.bot.send_message.await_count >= 1

    mock_app.bot.send_message.reset_mock()
    await send_client_hunter_step2(mock_app, chat_id=12345, workflow_data=wf)
    assert mock_app.bot.send_message.await_count >= 1
    assert wf["step2_sent"] is True
    sent_kwargs = mock_app.bot.send_message.await_args.kwargs
    assert "Jubayer Ahamed" in sent_kwargs["text"]
    assert "https://wa.me/" in sent_kwargs["text"]


@pytest.mark.asyncio
async def test_delayed_step2_skips_if_already_sent_via_button(tmp_path: Path):
    """Verify _delayed_step2_task does not send a duplicate 2nd message if user already clicked 'send_proposal_now'."""
    from telegram_bot import _delayed_step2_task

    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)
    with patch.object(agent.scanner, "scan_website", return_value={"is_live": True, "http_status": 200, "has_ssl": True}):
        wf = agent.execute_hunt_workflow(query="restaurant", mark_as_scanned=True)

    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()

    # Simulate user clicking "📨 এখনই ২য় মেসেজ দেখুন" immediately
    await send_client_hunter_step2(mock_app, chat_id=777, workflow_data=wf)
    assert wf["step2_sent"] is True
    initial_calls = mock_app.bot.send_message.await_count

    # Now when the background timer finishes, it must NOT send a duplicate message
    await _delayed_step2_task(mock_app, chat_id=777, workflow_data=wf, delay_seconds=0)
    assert mock_app.bot.send_message.await_count == initial_calls


def test_dynamic_url_discovery_and_sector_enrichment(tmp_path: Path):
    """Verify subdomain URLs are parsed and dynamically enriched with sector intelligence from live HTML."""
    db_file = tmp_path / "scanned_companies.json"
    agent = ClientHunterAgent(storage_path=db_file)

    mock_scan = {
        "url": "https://www.unitedhospital.com.bd",
        "is_live": True,
        "http_status": 200,
        "load_time_sec": 1.8,
        "has_ssl": True,
        "has_title": True,
        "title_text": "United Hospital Limited | Best Tertiary Care Hospital in Dhaka",
        "has_meta_description": True,
        "meta_description_text": "Leading private hospital and diagnostic center in Gulshan Dhaka.",
        "discovered_phones": ["+880 1914-001234"],
        "discovered_emails": ["info@uhlbd.com"],
        "discovered_facebook": "https://www.facebook.com/uhlbd"
    }

    with patch.object(agent.scanner, "scan_website", return_value=mock_scan):
        wf = agent.execute_hunt_workflow(query="www.unitedhospital.com.bd", mark_as_scanned=True)

    assert "United Hospital Limited" in wf["company"]["name"]
    assert "হেলথকেয়ার" in wf["company"]["category"]
    assert wf["company"]["phone"] == "+880 1914-001234"
    assert wf["company"]["email"] == "info@uhlbd.com"
    assert wf["company"]["facebook"] == "https://www.facebook.com/uhlbd"


def test_calculator_safe_against_invalid_numeric_inputs():
    """Verify DigitalHealthAndRevenueCalculator handles None, 0, or non-numeric visitor/ticket values safely."""
    company = {
        "name": "Test Co",
        "category": "Real Estate",
        "avg_monthly_visitors": None,
        "avg_ticket_bdt": "invalid"
    }
    scan = {"is_live": False, "has_ssl": False}
    metrics = DigitalHealthAndRevenueCalculator.evaluate(company, scan)
    assert 22 <= metrics["health_score"] <= 68
    assert metrics["max_lost_bdt"] > metrics["min_lost_bdt"]


def test_evaluator_deterministic_approval_for_client_hunter(tmp_path: Path):
    """Verify EvaluatorAgent deterministically validates and approves complete ClientHunter outputs without LLM overhead."""
    from agents.evaluator_agent import EvaluatorAgent

    db_file = tmp_path / "scanned_companies.json"
    hunter = ClientHunterAgent(storage_path=db_file)
    with patch.object(hunter.scanner, "scan_website", return_value={"is_live": True, "http_status": 200, "has_ssl": True}):
        res = hunter.run("diagnostic center dhaka")

    evaluator = EvaluatorAgent()
    eval_res = evaluator.evaluate_output(
        user_intent="diagnostic center dhaka",
        subagent_name=hunter.name,
        draft_output=res["output"]
    )
    assert eval_res["verdict"] == "APPROVED"
    assert eval_res["average_score"] >= 4.8


def test_strictly_commercial_businesses_only():
    """Verify REAL_TARGET_BUSINESS_POOL and is_commercial_business strictly allow 100% commercial companies only."""
    from agents.client_hunter_agent import is_commercial_business, REAL_TARGET_BUSINESS_POOL

    for item in REAL_TARGET_BUSINESS_POOL:
        assert is_commercial_business(item["name"], item["website"]), f"Non-commercial item in pool: {item['name']}"

    assert is_commercial_business("Popular Diagnostic Centre Ltd.", "https://www.populardiagnostic.com") is True
    assert is_commercial_business("Sailor by Epyllion", "https://sailor.clothing") is True
    assert is_commercial_business("Ministry of Health", "https://mohfw.gov.bd") is False
    assert is_commercial_business("Charity Foundation", "https://examplefoundation.org") is False
    assert is_commercial_business("Random Blog", "https://myblog.wordpress.com") is False


def test_permanent_subscriber_survives_sqlite_reset(tmp_path: Path):
    """Verify get_all_daily_subscribers always returns permanent subscriber 6302370142 even on a fresh empty SQLite DB."""
    from telegram_bot import get_all_daily_subscribers
    from database.memory import MemoryManager

    fresh_mem = MemoryManager(db_path=tmp_path / "fresh_empty.db")
    subs = get_all_daily_subscribers(fresh_mem)
    assert 6302370142 in subs
