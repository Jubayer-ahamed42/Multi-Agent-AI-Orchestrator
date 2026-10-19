"""Smart Sales Assistant Sub-Agent ("Be Smart With AI")
Founder & Chief Software Architect: Jubayer Ahamed (জুবায়ের আহমেদ)

Key Architectural Features:
1. Premium Dedicated Gemini Model with 1,500 daily quota tracking (Zero collision with main project key).
2. 5 to 10 seconds Smart Message Buffer / Debouncer (bundles rapid WhatsApp messages before AI reasoning).
3. Corporate Executive 'Sir' Protocol: strictly addresses client as 'স্যার', strictly forbids 'ভাই', and
   executes official owner notification handoff protocol.
4. Smart 3-Way Intent Classification:
   - BUYER: Consultative AI sales flow (needs, website link, traffic, high-converting package recommendation).
   - STUDENT / INFO_SEEKER: Concise, polite educational answers without sales push.
   - SPAM / WRONG NUMBER: Respectful agency identity verification.
5. Google Sheet CRM sync & Telegram Instant Hot-Lead Alert to Jubayer Ahamed Sir.
"""

import os
import re
import csv
import json
import time
import uuid
import urllib.request
import urllib.parse
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable, Awaitable

import litellm
from config import (
    SALES_CLOSER_GEMINI_KEY,
    SALES_MODEL_NAME,
    MESSAGE_BUFFER_SECONDS,
    OWNER_TELEGRAM_CHAT_ID,
    GOOGLE_SHEET_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    CRM_DATA_DIR,
    CRM_LEADS_CSV_PATH,
    CRM_LEADS_JSON_PATH,
    get_sales_api_key,
    get_sales_model,
    sanitize_model_name,
)
from database.memory import MemoryManager

litellm.suppress_debug_info = True
logger = logging.getLogger(__name__)

# Core Agency Branding & Metadata
AGENCY_NAME = "Be Smart With AI"
FOUNDER_NAME = "জুবায়ের আহমেদ"
FOUNDER_ENGLISH = "Jubayer Ahamed"
FOUNDER_ROLE = "প্রধান সফটওয়্যার আর্কিটেক্ট"
DAILY_FREE_QUOTA_LIMIT = 1500
QUOTA_TRACKER_PATH = CRM_DATA_DIR / "sales_quota_tracker.json"

# Mandatory Executive Handoff Statement
OWNER_HANDOFF_STATEMENT = (
    f"স্যার, আমি আমাদের {FOUNDER_ROLE} '{FOUNDER_NAME} স্যার'-কে আপনার চাহিদার বিস্তারিত "
    f"নোটিফিকেশন পাঠিয়ে দিয়েছি। স্যার আপনার প্রজেক্টটি পর্যালোচনা করে দ্রুতই আপনার সাথে কথা বলবেন।"
)


# =====================================================================
# 1. Quota Tracker & Rate Limit Guard (1,500 Daily Free Quota)
# =====================================================================
class DailyQuotaTracker:
    """Monitors and persists daily API request consumption to optimize within the 1,500 req/day quota."""

    def __init__(self, tracker_path: Path = QUOTA_TRACKER_PATH, limit: int = DAILY_FREE_QUOTA_LIMIT):
        self.tracker_path = tracker_path
        self.limit = limit
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_today_str(self) -> str:
        # Timezone UTC+6 for Bangladesh Standard Time
        return datetime.now(timezone(timedelta(hours=6))).strftime("%Y-%m-%d")

    def _read_data(self) -> Dict[str, Any]:
        if self.tracker_path.exists():
            try:
                data = json.loads(self.tracker_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.warning(f"Could not read quota tracker: {e}")
        return {"date": self._get_today_str(), "count": 0}

    def _write_data(self, data: Dict[str, Any]):
        try:
            self.tracker_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist quota tracker: {e}")

    def get_count(self) -> int:
        data = self._read_data()
        today = self._get_today_str()
        if data.get("date") != today:
            return 0
        return int(data.get("count", 0))

    def can_request(self) -> bool:
        """Returns True if requests remain under the daily quota limit."""
        return self.get_count() < self.limit

    def increment(self) -> int:
        """Increments today's counter and returns updated count."""
        today = self._get_today_str()
        data = self._read_data()
        if data.get("date") != today:
            data = {"date": today, "count": 1}
        else:
            data["count"] = int(data.get("count", 0)) + 1
        data["last_updated"] = datetime.now(timezone(timedelta(hours=6))).isoformat()
        self._write_data(data)
        return data["count"]

    def reset_today(self):
        """Resets today's counter (useful for unit tests)."""
        data = {"date": self._get_today_str(), "count": 0}
        self._write_data(data)


# Global quota tracker instance
quota_tracker = DailyQuotaTracker()


# =====================================================================
# 2. Executive 'Sir' Protocol & Guardrail Functions
# =====================================================================
def enforce_sir_protocol(text: str) -> str:
    """Enforces the strict corporate Executive 'Sir' Protocol:
    1. Replaces colloquial words like 'ভাই', 'ভাইয়া', 'bhai', 'bro' with 'স্যার' / 'স্যারের' / 'স্যারদের'.
       Strictly preserves non-brother words such as 'ভাইরাস' (virus), 'ভাইরাল' (viral), 'ভাইস' (vice),
       'ভাইটামিন' (vitamin), 'ভাইব্রেশন' (vibration).
    2. Ensures the text addresses the client with honor as 'স্যার'.
    3. Guarantees polite Islamic greeting if not already present.
    """
    if not text:
        return "আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। স্যার, আমি আপনাকে কীভাবে সহায়তা করতে পারি?"

    cleaned = text

    # 1. Handle possessive and plural forms first
    cleaned = re.sub(r"(?<![\u0980-\u09FF])(ভাই(?:য়ের|য়ের))(?![\u0980-\u09FF])", "স্যারের", cleaned)
    cleaned = re.sub(r"(?<![\u0980-\u09FF])(ভাইদের)(?![\u0980-\u09FF])", "স্যারদের", cleaned)

    # 2. Replace colloquial brother forms without touching technical loanwords (ভাইরাস, ভাইরাল, ভাইস, ভাইব্রেশন, ইত্যাদি)
    cleaned = re.sub(
        r"(?<![\u0980-\u09FF])(ভাই(?:য়া|য়া|রে|রা|জান|সাব|ডি|টি|টিকে)?|ভায়া|ভায়েরা)(?![\u0980-\u09FF])",
        "স্যার",
        cleaned
    )

    # 3. Transliterated colloquial variations
    bhai_patterns = [
        (r"\bbhaiya\b", "স্যার"),
        (r"\bbhai\b", "স্যার"),
        (r"\bbhaia\b", "স্যার"),
        (r"\bvaiya\b", "স্যার"),
        (r"\bvai\b", "স্যার"),
        (r"\bvaia\b", "স্যার"),
        (r"\bbro\b", "স্যার"),
        (r"\bbroda\b", "স্যার"),
    ]
    for pattern, repl in bhai_patterns:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    # Clean any duplicate 'স্যার' created by consecutive replacements
    cleaned = re.sub(r"(?:স্যার[,\s]*){2,}", "স্যার, ", cleaned)

    # Double check for honorific 'স্যার'
    if "স্যার" not in cleaned:
        cleaned = f"স্যার, {cleaned.lstrip()}"

    # Ensure greeting starts with আসসালামু আলাইকুম
    if not re.search(r"আসসালামু\s+আলাইকুম", cleaned):
        cleaned = f"আসসালামু আলাইকুম স্যার। {cleaned}"

    return cleaned


# =====================================================================
# 3. Dedicated Sales LLM Client (Isolated Key, Quota Optimized)
# =====================================================================
def call_sales_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.4,
    max_tokens: int = 3000,
    max_retries: int = 3
) -> str:
    """Invokes LLM using the dedicated SALES_CLOSER_GEMINI_KEY strictly isolated from main project keys."""
    # Check daily quota limit
    if not quota_tracker.can_request():
        logger.error(f"[SALES AI] Daily quota limit of {DAILY_FREE_QUOTA_LIMIT} reached.")
        return (
            f"আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। "
            f"স্যার, আজকের ফ্রি কনসালটেশন স্লট পূর্ণ হয়ে গেছে। তবে আপনার বিষয়টি অত্যন্ত গুরুত্বপূর্ণ। "
            f"{OWNER_HANDOFF_STATEMENT}"
        )

    chosen_key = (api_key or get_sales_api_key()).strip()
    raw_model = model or get_sales_model()
    target_model = sanitize_model_name(raw_model)

    # If no key is set in development, return a realistic executive dry-run response without crashing
    if not chosen_key:
        logger.warning(
            "[SALES AI] SALES_CLOSER_GEMINI_KEY is not set in .env. "
            "Please configure SALES_CLOSER_GEMINI_KEY for live LLM inferences."
        )
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break
        return (
            f"আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। "
            f"আমি আমাদের প্রধান সফটওয়্যার আর্কিটেক্ট জুবায়ের আহমেদ স্যারের স্মার্ট সেলস অ্যাসিস্ট্যান্ট। "
            f"স্যার, আপনার ব্যবসার জন্য 24/7 AI WhatsApp Closer বা অটোমেশন সলিউশন সম্পর্কে জানাতে প্রস্তুত। "
            f"আপনার ব্যবসার ধরন, ওয়েবসাইটের লিংক ও বর্তমান ট্রাফিক সম্পর্কে একটু জানাবেন কি?"
        )

    kwargs: Dict[str, Any] = {
        "model": target_model,
        "messages": messages,
        "api_key": chosen_key,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = litellm.completion(**kwargs)
            quota_tracker.increment()
            content = resp.choices[0].message.content or ""
            return content.strip()
        except Exception as e:
            err_str = str(e).lower()
            last_err = e
            logger.warning(f"[SALES AI] Request attempt {attempt} failed: {e}")
            if "quota" in err_str or "resource_exhausted" in err_str:
                logger.error("[SALES AI] Quota exhausted on dedicated sales key.")
                break
            elif "429" in err_str or "503" in err_str or "unavailable" in err_str:
                time.sleep(attempt * 1.5)
            else:
                time.sleep(1.0)

    # If all retries failed, provide safe executive fallback
    logger.error(f"[SALES AI] All LLM calls failed: {last_err}")
    return (
        f"আসসালামু আলাইকুম স্যার। Be Smart With AI-তে স্বাগতম। "
        f"স্যার, সাময়িক নেটওয়ার্ক ব্যস্ততার কারণে উত্তর দিতে সামান্য বিলম্ব হচ্ছে। "
        f"{OWNER_HANDOFF_STATEMENT}"
    )


# =====================================================================
# 4. Smart Message Buffer / Debouncer (5 - 10 Seconds Window)
# =====================================================================
class MessageDebouncer:
    """Debounces rapid incoming WhatsApp messages from the same sender within 5-10 seconds.
    Bundles all consecutive messages into a single complete statement before invoking the AI.
    """

    def __init__(self, buffer_seconds: float = MESSAGE_BUFFER_SECONDS):
        self.buffer_seconds = max(5.0, min(10.0, float(buffer_seconds)))
        self._buffers: Dict[str, List[str]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._timestamps: Dict[str, float] = {}

    def get_buffered_messages(self, user_id: str) -> List[str]:
        return list(self._buffers.get(user_id, []))

    def add_message_sync(self, user_id: str, message: str) -> List[str]:
        """Synchronously appends message to the user's buffer (for non-async flows or testing)."""
        clean_msg = (message or "").strip()
        if clean_msg:
            if user_id not in self._buffers:
                self._buffers[user_id] = []
            self._buffers[user_id].append(clean_msg)
            self._timestamps[user_id] = time.time()
        return list(self._buffers.get(user_id, []))

    def flush(self, user_id: str) -> Tuple[str, List[str]]:
        """Pops and bundles all accumulated messages for the user.
        Safely avoids cancelling the currently executing worker task.
        """
        raw_msgs = self._buffers.pop(user_id, [])
        if user_id in self._tasks:
            t = self._tasks.pop(user_id)
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if t != current and not t.done():
                t.cancel()
        self._timestamps.pop(user_id, None)
        bundled_text = "\n".join(raw_msgs)
        return bundled_text, raw_msgs

    def clear(self, user_id: str):
        """Clears buffer and cancels pending timer for user."""
        self._buffers.pop(user_id, None)
        if user_id in self._tasks:
            t = self._tasks.pop(user_id)
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if t != current and not t.done():
                t.cancel()
        self._timestamps.pop(user_id, None)

    async def add_message_async(
        self,
        user_id: str,
        message: str,
        on_bundle_ready: Callable[[str, str, List[str]], Awaitable[Any]]
    ):
        """Asynchronously buffers message and resets debounce timer.
        When no new messages arrive for `buffer_seconds`, invokes `on_bundle_ready(user_id, bundled_text, raw_msgs)`.
        """
        self.add_message_sync(user_id, message)

        # Cancel any currently active timer task for this user
        existing_task = self._tasks.get(user_id)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        async def _timer_worker():
            try:
                await asyncio.sleep(self.buffer_seconds)
                # Pop and bundle
                bundled_text, raw_msgs = self.flush(user_id)
                if bundled_text:
                    await on_bundle_ready(user_id, bundled_text, raw_msgs)
            except asyncio.CancelledError:
                # Timer was reset by another incoming message
                pass
            except Exception as e:
                logger.error(f"[Debouncer Error for {user_id}]: {e}")

        self._tasks[user_id] = asyncio.create_task(_timer_worker())


# =====================================================================
# 5. Lead Extraction, Google Sheets CRM & Telegram Instant Alert
# =====================================================================
class GoogleSheetCRM:
    """Manages recording client leads to Google Sheets CRM with a persistent local CSV and JSON fallback."""

    def __init__(
        self,
        sheet_id: str = GOOGLE_SHEET_ID,
        service_account_path: str = GOOGLE_SERVICE_ACCOUNT_JSON,
        csv_path: Path = CRM_LEADS_CSV_PATH,
        json_path: Path = CRM_LEADS_JSON_PATH
    ):
        self.sheet_id = sheet_id
        self.service_account_path = service_account_path
        self.csv_path = csv_path
        self.json_path = json_path
        self._ensure_storage()

    def _ensure_storage(self):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["তারিখ-সময়", "নাম", "ফোন", "ওয়েবসাইট", "চাহিদা", "সারাংশ"])

        if not self.json_path.exists():
            self.json_path.write_text("[]", encoding="utf-8")

    def append_lead(
        self,
        name: str,
        phone: str,
        website: str,
        requirements: str,
        summary: str
    ) -> Dict[str, Any]:
        """Appends a new qualified lead row: [তারিখ-সময়, নাম, ফোন, ওয়েবসাইট, চাহিদা, সারাংশ]."""
        now_str = datetime.now(timezone(timedelta(hours=6))).strftime("%Y-%m-%d %I:%M:%S %p")
        row = [
            now_str,
            name or "Unknown / Unspecified",
            phone or "Unspecified",
            website or "None",
            requirements or "AI Automation / Website Consultation",
            summary or "Client inquiry regarding AI automation services."
        ]

        # 1. Local CSV append
        try:
            with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception as e:
            logger.error(f"[CRM] Failed to append to CSV: {e}")

        # 2. Local JSON append
        lead_dict = {
            "timestamp": now_str,
            "name": row[1],
            "phone": row[2],
            "website": row[3],
            "requirements": row[4],
            "summary": row[5]
        }
        try:
            existing = []
            if self.json_path.exists():
                try:
                    existing = json.loads(self.json_path.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    existing = []
            existing.append(lead_dict)
            self.json_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"[CRM] Failed to append to JSON: {e}")

        # 3. Google Sheets append (if configured)
        if self.sheet_id and self.service_account_path:
            try:
                import gspread
                gc = None
                if os.path.exists(self.service_account_path):
                    gc = gspread.service_account(filename=self.service_account_path)
                elif self.service_account_path.strip().startswith("{"):
                    gc = gspread.service_account_from_dict(json.loads(self.service_account_path))

                if gc:
                    sh = gc.open_by_key(self.sheet_id)
                    worksheet = sh.get_worksheet(0)
                    if len(worksheet.get_all_values()) == 0:
                        worksheet.append_row(["তারিখ-সময়", "নাম", "ফোন", "ওয়েবসাইট", "চাহিদা", "সারাংশ"])
                    worksheet.append_row(row)
                    logger.info(f"[CRM] Successfully appended lead to Google Sheet {self.sheet_id}")
            except Exception as gs_err:
                logger.warning(f"[CRM] Google Sheet API note: {gs_err} (saved to local CSV/JSON)")
        else:
            logger.info("[CRM] Lead securely recorded in local CRM store (CSV & JSON).")

        return lead_dict


def send_hot_lead_telegram_alert(lead_data: Dict[str, str], bot_token: Optional[str] = None) -> bool:
    """Dispatches instant Telegram notification to Jubayer Ahamed Sir.
    Exact Format from specification:
    "🚨 নতুন হট-লিড! নাম: [XYZ] | ফোন: [01...] | ওয়েবসাইট: [URL] | চাহিদা: [Summary]। স্যার, দ্রুত ক্লায়েন্টের সাথে যোগাযোগ করুন!"
    """
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = str(os.getenv("OWNER_TELEGRAM_CHAT_ID", OWNER_TELEGRAM_CHAT_ID)).strip()

    if not token or token == "your_telegram_bot_token_here":
        logger.warning("[Telegram Alert] TELEGRAM_BOT_TOKEN not configured. Alert logged locally.")
        return False

    name = lead_data.get("name") or "অজ্ঞাত"
    phone = lead_data.get("phone") or "প্রদান করেনি"
    website = lead_data.get("website") or "নেই"
    demand = lead_data.get("summary") or lead_data.get("requirements") or "এআই অটোমেশন"

    alert_text = (
        f"🚨 নতুন হট-লিড! নাম: {name} | ফোন: {phone} | ওয়েবসাইট: {website} | চাহিদা: {demand}। "
        f"স্যার, দ্রুত ক্লায়েন্টের সাথে যোগাযোগ করুন!"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": alert_text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if status in [200, 201]:
                logger.info(f"[Telegram Alert] Sent hot-lead alert to Jubayer Ahamed Sir ({chat_id})")
                return True
    except Exception as e:
        logger.warning(f"[Telegram Alert] Failed to dispatch Telegram alert: {e}")
    return False


# =====================================================================
# 6. Smart Intent Classifier & Lead Information Extractor
# =====================================================================
def classify_intent_rule_based(message: str) -> Optional[str]:
    """Fast deterministic intent detection for clear-cut queries.
    Priority: Spam -> Buyer / Commercial -> Student / General Educational.
    """
    m = message.lower().strip()

    # 1. Spam / Gibberish checks
    spam_triggers = [
        "lottery", "casino", "free crypto", "click here", "viagra", "poker",
        "sex", "xxx", "loan approved", "টাকা কামান ফ্রিতে", "লটারি", "ভুল নম্বর", "wrong number"
    ]
    if any(st in m for st in spam_triggers):
        return "SPAM"

    # 2. Buyer / Commercial intent (takes priority if user mentions business/pricing/websites)
    buyer_triggers = [
        "চাহিদা", "website", "bot", "বট", "অটোমেশন", "automation", "whatsapp bot",
        "হোয়াটসঅ্যাপ বট", "দাম কত", "খরচ কত", "price", "pricing", "cost", "service",
        "সার্ভিস", "এজেন্সি", "agency", "software", "কাস্টমার সাপোর্ট", "sales", "বিক্রয়",
        "ক্লায়েন্ট", "ক্লায়েন্ট", "ব্যবসা", "বিজনেস", "business", "e-commerce", "ecommerce",
        "traffic", "ট্রাফিক", "প্যাকেজ", "package", "অর্ডার", "order"
    ]
    if any(bt in m for bt in buyer_triggers):
        return "BUYER"

    # 3. Student / General educational inquiry
    student_triggers = [
        "what is ai", "ai কি", "এআই কি", "মেশিন লার্নিং কি", "লার্নিং রোডম্যাপ",
        "এসাইনমেন্ট", "assignment", "university project", "thesis", "থিসিস",
        "পড়াশোনা", "কিভাবে শিখব", "how to learn ai", "ai শেখার উপায়"
    ]
    if any(st in m for st in student_triggers):
        return "STUDENT"

    return None


def extract_lead_entities(text: str) -> Dict[str, Optional[str]]:
    """Extracts phone number, website URL, and personal name indicators from text using regex."""
    entities: Dict[str, Optional[str]] = {
        "phone": None,
        "website": None,
        "name": None
    }

    # Phone number extraction (Bangladeshi formats and international)
    phone_match = re.search(r"(?:\+?880|0)\s*1[3-9]\d{2}[-\s]?\d{6}\b", text)
    if phone_match:
        raw_p = phone_match.group(0)
        digits = re.sub(r"[^\d]", "", raw_p)
        if digits.startswith("880"):
            entities["phone"] = f"+{digits}"
        else:
            entities["phone"] = f"+88{digits}"
    else:
        intl_match = re.search(r"(?:\+|00)[1-9]\d{1,3}[-\s]?\d{4,12}\b", text)
        if intl_match:
            entities["phone"] = intl_match.group(0).strip()

    # Website extraction
    url_match = re.search(
        r"https?://[a-zA-Z0-9.\-_]+(?:\.[a-zA-Z]{2,})[^\s,।!?]*|(?:www\.)[a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}[^\s,।!?]*|[a-zA-Z0-9\-]+\.(?:com|org|net|com\.bd|ai|tech|co|io)\b[^\s,।!?]*",
        text,
        re.IGNORECASE
    )
    if url_match:
        url = url_match.group(0).strip()
        url = re.sub(r"[\s,।!?:;.]+$", "", url)
        if not url.startswith("http"):
            url = f"https://{url}"
        entities["website"] = url

    # Personal name extraction (excludes website/business names like 'ওয়েবসাইটের নাম')
    name_patterns = [
        r"(?:আমার\s+নাম|my\s+name\s+is)\s*[:=\-]?\s*([A-Za-z\u0980-\u09FF\s]{2,30})",
        r"(?<![^\s])(?:নাম|name)\s*[:=\-]\s*([A-Za-z\u0980-\u09FF\s]{2,30})",
    ]
    for pat in name_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw_name = m.group(1).strip()
            raw_name = re.split(
                r"[\n,\।!?]|(?:\s+(?:ফোন|মোবাইল|ওয়েবসাইট|ওয়েবসাইট|phone|mobile|website|email|mail|whatsapp)\b)",
                raw_name,
                flags=re.IGNORECASE
            )[0].strip()
            if raw_name and len(raw_name) >= 2 and not raw_name.lower().startswith(("http", "www")):
                entities["name"] = raw_name
                break

    return entities


# =====================================================================
# 7. Main Sub-Agent: SmartSalesAssistant
# =====================================================================
class SmartSalesAssistant:
    """Dedicated Modular Sales Assistant for 'Be Smart With AI'.
    Founder: Jubayer Ahamed.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        memory_manager: Optional[MemoryManager] = None,
        buffer_seconds: float = MESSAGE_BUFFER_SECONDS
    ):
        self.name = "Smart Sales Assistant"
        self.agency_name = AGENCY_NAME
        self.founder = FOUNDER_NAME
        self.founder_english = FOUNDER_ENGLISH
        self.founder_role = FOUNDER_ROLE
        self.api_key = api_key or get_sales_api_key()
        self.model = model or get_sales_model()
        self.temperature = 0.4
        self.memory = memory_manager or MemoryManager()
        self.crm = GoogleSheetCRM()
        self.debouncer = MessageDebouncer(buffer_seconds=buffer_seconds)

    def classify_intent(self, message: str, chat_history: List[Dict[str, str]]) -> str:
        """Classifies intent into BUYER, STUDENT, or SPAM."""
        rule_intent = classify_intent_rule_based(message)
        if rule_intent:
            return rule_intent

        history_summary = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in chat_history[-3:]])
        prompt = f"""You are the Intent Classifier for the AI agency "{self.agency_name}".
Analyze the customer's input and recent chat context:

Recent Context:
{history_summary}

User Input:
"{message}"

Categories:
1. "BUYER": Interested in AI automation, WhatsApp bots, website AI, software, consulting, pricing, or looking for business solutions.
2. "STUDENT": Seeking general academic knowledge, basic definitions, student assignments, learning roadmaps without buying intention.
3. "SPAM": Nonsense, spam links, insults, or completely unrelated wrong-number messages.

Respond ONLY with a JSON object:
{{"intent": "BUYER" | "STUDENT" | "SPAM"}}
"""
        try:
            raw = call_sales_llm(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                api_key=self.api_key,
                temperature=0.0
            )
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                intent = str(data.get("intent", "BUYER")).upper()
                if intent in ["BUYER", "STUDENT", "SPAM"]:
                    return intent
        except Exception as e:
            logger.warning(f"[Intent Classifier Note]: {e}")

        return "BUYER"

    def _generate_buyer_response(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]],
        lead_entities: Dict[str, Optional[str]],
        lead_already_saved: bool = False
    ) -> Tuple[str, bool]:
        """Generates consultative sales guidance, gathers requirements/website/traffic,
        and triggers owner handoff once sufficient details are captured.
        """
        history_formatted = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in chat_history[-4:]])

        # Check if client has provided significant lead details (phone or website or comprehensive requirements)
        has_phone = bool(lead_entities.get("phone"))
        has_website = bool(lead_entities.get("website"))
        clean_msg_lower = user_message.lower().strip()

        # Check if user mentioned business requirements or automation challenges
        has_requirements = has_website or (
            any(
                k in clean_msg_lower for k in [
                    "চাহিদা", "website", "bot", "বট", "অটোমেশন", "automation", "whatsapp",
                    "সার্ভিস", "প্যাকেজ", "দাম", "খরচ", "ব্যবসা", "বিজনেস", "ই-কমার্স", "ecommerce",
                    "traffic", "ট্রাফিক", "দোকান", "শপ", "সেলস", "sales", "দরকার", "লাগবে", "সলিউশন"
                ]
            ) and len(user_message.strip()) > 10
        )
        has_owner_mention = any(
            k in clean_msg_lower for k in [
                "জুবায়ের", "jubayer", "আর্কিটেক্ট", "architect", "মালিক", "owner",
                "founder", "কথা বলতে চাই", "কল দিন", "কল করবেন", "call me", "contact me"
            ]
        )

        is_ready_for_handoff = (
            has_owner_mention
            or (has_phone and has_website)
            or (has_phone and has_requirements)
            or (has_website and len(user_message) > 20)
        )

        handoff_instruction = ""
        if is_ready_for_handoff and not lead_already_saved:
            handoff_instruction = (
                f"\nCRITICAL: The client has provided their contact/project details! Conclude gracefully with the EXACT owner handoff statement:\n"
                f"\"{OWNER_HANDOFF_STATEMENT}\"\n"
            )

        system_prompt = f"""You are the Executive AI Sales Consultant of the premier AI agency "{self.agency_name}".
Our Founder & Chief Software Architect is "{self.founder}" ({self.founder_english}).

MANDATORY RULES:
1. ADDRESSING & TONE:
   - Always address the customer with highest honor and respect as "স্যার" (Sir) throughout your response.
   - NEVER use "ভাই", "ভাইয়া", or "bhai". Strictly forbidden!
   - Greet politely with "আসসালামু আলাইকুম স্যার। {self.agency_name}-তে স্বাগতম।" if this is the start of the conversation.
   - Demeanor: Sweet, polite, professional, confident, and consultative.

2. SALES CONSULTATION FLOW (BUYER):
   - Proactively understand their business model.
   - Inquire politely about:
     a) What type of business they run & what specific challenge they are facing.
     b) Their website link (if any).
     c) Their daily or monthly customer traffic/inquiries.
   - Present {self.agency_name}'s high-converting solutions:
     • 24/7 AI WhatsApp Closer Bot: Converts leads, handles orders, answers questions automatically 24 hours a day.
     • 24/7 AI Messenger & Website Chatbot: Instant zero-latency responses for visitors.
     • Automated CRM & Lead Qualification: Captures qualified hot-leads directly to Google Sheets and Telegram.
   - Keep answers clear, sweet, and engaging. Avoid long robotic walls of text.

{handoff_instruction}

[RECENT CONVERSATION HISTORY]:
{history_formatted}

[CURRENT USER MESSAGE]:
{user_message}
"""
        raw_reply = call_sales_llm(
            messages=[{"role": "user", "content": system_prompt}],
            model=self.model,
            api_key=self.api_key,
            temperature=self.temperature
        )

        final_reply = enforce_sir_protocol(raw_reply)
        if is_ready_for_handoff and not lead_already_saved and OWNER_HANDOFF_STATEMENT not in final_reply:
            final_reply = f"{final_reply}\n\n{OWNER_HANDOFF_STATEMENT}"

        return final_reply, is_ready_for_handoff

    def _generate_student_response(self, user_message: str, chat_history: List[Dict[str, str]]) -> str:
        """Generates concise, polite educational answers without pushing any sales packages."""
        history_formatted = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in chat_history[-3:]])
        prompt = f"""You are an intelligent, humble, and polite AI assistant at "{self.agency_name}".
The user is a student or seeking general educational information.

RULES:
1. Always address the user with honor as "স্যার" (Sir).
2. Never use "ভাই" or "ভাইয়া".
3. Answer ONLY what the user asked concisely, clearly, and politely.
4. DO NOT pitch any sales services, packages, pricing, or agency offerings.
5. Maintain a humble, respectful, and helpful tone in fluent native Bengali.

[RECENT HISTORY]:
{history_formatted}

[USER QUESTION]:
{user_message}
"""
        reply = call_sales_llm(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            api_key=self.api_key,
            temperature=self.temperature
        )
        return enforce_sir_protocol(reply)

    def _generate_spam_response(self) -> str:
        """Returns polite agency boundary message for spam or wrong numbers."""
        return enforce_sir_protocol(
            f"আসসালামু আলাইকুম স্যার। এটি '{self.agency_name}'-এর অফিশিয়াল সাপোর্ট ডেস্ক। "
            f"স্যার, আমরা বিভিন্ন ব্যবসা ও প্রতিষ্ঠানের জন্য 24/7 AI WhatsApp Closer ও অটোমেশন সলিউশন তৈরি করি। "
            f"স্যার, আপনি কি কোনো এআই সমাধান বা বিজনেস অটোমেশন সম্পর্কে জানতে চাচ্ছেন?"
        )

    def run(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_phone: Optional[str] = None,
        critique: Optional[str] = None
    ) -> Dict[str, Any]:
        """Main execution entry point for SmartSalesAssistant."""
        clean_text = (user_message or "").strip()

        # Extract entities first so phone can be used for session identification
        lead_entities = extract_lead_entities(clean_text)
        if sender_phone and not lead_entities.get("phone"):
            lead_entities["phone"] = sender_phone
        if sender_name and not lead_entities.get("name"):
            lead_entities["name"] = sender_name

        effective_phone = sender_phone or lead_entities.get("phone")
        sid = session_id or (f"sales_{sender_phone}" if sender_phone else f"sales_adhoc_{uuid.uuid4().hex[:8]}")

        # Fetch recent chat memory
        chat_history = []
        try:
            chat_history = self.memory.get_messages(sid)[-6:]
        except Exception:
            pass

        # Check if a lead was already captured/saved in this session
        lead_already_saved = False
        try:
            for m in chat_history:
                meta = m.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                if isinstance(meta, dict) and meta.get("lead_saved") is True:
                    lead_already_saved = True
                    break
        except Exception:
            pass

        # Classify Intent
        intent = self.classify_intent(clean_text, chat_history)

        lead_saved = False
        lead_data_record = None

        if intent == "BUYER":
            reply_text, is_handoff = self._generate_buyer_response(
                clean_text,
                chat_history,
                lead_entities,
                lead_already_saved=lead_already_saved
            )

            # Persist to CRM & alert Telegram only when qualified and not already recorded for this session
            if is_handoff and not lead_already_saved:
                lead_demand = clean_text if len(clean_text) > 15 else "AI Automation & Website Consultation"
                lead_data_record = self.crm.append_lead(
                    name=lead_entities.get("name") or sender_name or "Client",
                    phone=lead_entities.get("phone") or sender_phone or "",
                    website=lead_entities.get("website") or "None",
                    requirements=lead_demand,
                    summary=f"Inquiry regarding AI automation. Details: {clean_text[:120]}"
                )
                lead_saved = True
                # Trigger instant notification to Jubayer Ahamed Sir
                send_hot_lead_telegram_alert(lead_data_record)

        elif intent == "STUDENT":
            reply_text = self._generate_student_response(clean_text, chat_history)
        else:  # SPAM
            reply_text = self._generate_spam_response()

        # Update SQLite memory
        try:
            self.memory.add_message(sid, "user", clean_text)
            self.memory.add_message(
                sid,
                "assistant",
                reply_text,
                metadata={
                    "agent": self.name,
                    "intent": intent,
                    "lead_saved": lead_saved
                }
            )
        except Exception as mem_err:
            logger.debug(f"[Memory Update Note]: {mem_err}")

        return {
            "subagent": self.name,
            "agency": self.agency_name,
            "founder": self.founder,
            "intent": intent,
            "output": reply_text,
            "lead_saved": lead_saved,
            "lead_data": lead_data_record,
            "session_id": sid,
            "tool_errors": []
        }

    def handle_bundled_message(
        self,
        sender_id: str,
        bundled_text: str,
        sender_name: Optional[str] = None,
        sender_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes bundled messages after debouncer window expires."""
        phone = sender_phone or (sender_id if sender_id.replace("+", "").isdigit() else None)
        return self.run(
            user_message=bundled_text,
            session_id=f"sales_{sender_id}",
            sender_name=sender_name,
            sender_phone=phone
        )

    async def receive_message(
        self,
        sender_id: str,
        message: str,
        sender_name: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        """Asynchronous interface with 5-10s smart debounce buffering.
        Waits for consecutive messages, bundles them, runs AI consultation, and triggers callback.
        """
        async def _on_bundle_ready(uid: str, bundled_text: str, raw_msgs: List[str]):
            logger.info(f"[Debouncer] Bundled {len(raw_msgs)} messages for {uid}: '{bundled_text}'")
            res = await asyncio.to_thread(self.handle_bundled_message, uid, bundled_text, sender_name)
            if callback:
                await callback(res)

        await self.debouncer.add_message_async(sender_id, message, _on_bundle_ready)
