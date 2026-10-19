import os
import io
import time
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    get_active_model,
    DEFAULT_SUBSCRIBER_CHAT_IDS,
    SUBSCRIBERS_JSON_PATH,
    DAILY_DISPATCH_STATE_PATH,
)
from database.memory import MemoryManager
from agents.orchestrator import MasterOrchestrator
from agents.hackathon_agent import HackathonAgent
from agents.client_hunter_agent import ClientHunterAgent
from tools.audio_tools import transcribe_audio_to_text
from tools.tts_tools import text_to_speech_bengali

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# User active modes dictionary (default is "auto" for smart automatic routing)
USER_MODES: Dict[int, str] = {}

# Stores the most recent generated proposal per chat_id for instant button preview or scheduled delivery
PENDING_PROPOSALS: Dict[int, Dict[str, Any]] = {}

# Tracks active delayed Step-2 asyncio tasks per chat_id to prevent duplicate or overlapping deliveries
ACTIVE_STEP2_TASKS: Dict[int, asyncio.Task] = {}

def get_session_id(user_id: int) -> str:
    """Returns a unique, persistent SQLite session ID for the Telegram user."""
    return f"telegram_{user_id}"

_DUMMY_TEST_CHAT_IDS = {12345, 777, 888777666, 999888777}

def _read_json_subscribers() -> List[int]:
    """Reads subscriber chat_ids from persistent JSON file."""
    try:
        if SUBSCRIBERS_JSON_PATH.exists():
            data = json.loads(SUBSCRIBERS_JSON_PATH.read_text(encoding="utf-8"))
            raw_list = data.get("subscribers", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            return [int(x) for x in raw_list if str(x).strip().lstrip("-").isdigit()]
    except Exception as e:
        logger.debug(f"Could not read subscribers JSON: {e}")
    return []

def _write_json_subscriber(chat_id: int):
    """Persists a real subscriber chat_id to data/telegram_subscribers.json."""
    if not chat_id or int(chat_id) in _DUMMY_TEST_CHAT_IDS:
        return
    try:
        SUBSCRIBERS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_json_subscribers()
        for def_id in DEFAULT_SUBSCRIBER_CHAT_IDS:
            if int(def_id) not in existing and int(def_id) not in _DUMMY_TEST_CHAT_IDS:
                existing.append(int(def_id))
        if int(chat_id) not in existing:
            existing.append(int(chat_id))
        payload = {
            "subscribers": existing,
            "updated_at": datetime.now(timezone(timedelta(hours=6))).isoformat()
        }
        SUBSCRIBERS_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not write subscribers JSON: {e}")

def register_daily_subscriber(chat_id: int):
    """Saves chat_id to SQLite memory and JSON file for automated 6:00 AM hackathon & 7:00 AM ClientHunter notifications."""
    if not chat_id:
        return
    mem = MemoryManager()
    try:
        raw = mem.get_preference("daily_hackathon_subscribers", "[]")
        subscribers = json.loads(raw) if raw else []
        if int(chat_id) not in subscribers:
            subscribers.append(int(chat_id))
            mem.set_preference("daily_hackathon_subscribers", json.dumps(subscribers))
    except Exception as e:
        logger.warning(f"Failed to register daily subscriber {chat_id}: {e}")
    _write_json_subscriber(int(chat_id))

def get_all_daily_subscribers(mem: Optional[MemoryManager] = None) -> List[int]:
    """Returns all real Telegram subscriber chat_ids from DEFAULT_SUBSCRIBER_CHAT_IDS, JSON file, SQLite preferences, and sessions."""
    mem = mem or MemoryManager()
    result_ids: List[int] = []

    # 1. Always include permanent default subscriber IDs (survives Render restarts)
    for def_cid in DEFAULT_SUBSCRIBER_CHAT_IDS:
        cid_int = int(def_cid)
        if cid_int not in _DUMMY_TEST_CHAT_IDS and cid_int not in result_ids:
            result_ids.append(cid_int)

    # 2. Merge from persistent JSON file (data/telegram_subscribers.json)
    for j_cid in _read_json_subscribers():
        if j_cid not in _DUMMY_TEST_CHAT_IDS and j_cid not in result_ids:
            result_ids.append(j_cid)

    # 3. Merge from SQLite user_preferences
    try:
        raw = mem.get_preference("daily_hackathon_subscribers", "[]")
        pref_ids = json.loads(raw) if raw else []
        for cid in pref_ids:
            cid_int = int(cid)
            if cid_int not in _DUMMY_TEST_CHAT_IDS and cid_int not in result_ids:
                result_ids.append(cid_int)
    except Exception:
        pass

    # 4. Merge from SQLite sessions table (telegram_<chat_id>)
    try:
        for sess in mem.get_all_sessions():
            sid = str(sess.get("id", ""))
            if sid.startswith("telegram_"):
                num_part = sid.replace("telegram_", "").strip()
                if num_part.isdigit():
                    cid_int = int(num_part)
                    if cid_int not in _DUMMY_TEST_CHAT_IDS and cid_int not in result_ids:
                        result_ids.append(cid_int)
    except Exception:
        pass
    return result_ids

def _get_last_dispatch_date(key: str, mem: MemoryManager) -> str:
    """Reads last dispatch date from SQLite or persistent JSON state file."""
    val = ""
    try:
        val = mem.get_preference(key, "") or ""
    except Exception:
        pass
    if val:
        return val
    try:
        if DAILY_DISPATCH_STATE_PATH.exists():
            data = json.loads(DAILY_DISPATCH_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return str(data.get(key, "") or "")
    except Exception:
        pass
    return ""

def _set_last_dispatch_date(key: str, today_str: str, mem: MemoryManager):
    """Persists last dispatch date to both SQLite and JSON state file."""
    try:
        mem.set_preference(key, today_str)
    except Exception:
        pass
    try:
        DAILY_DISPATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if DAILY_DISPATCH_STATE_PATH.exists():
            raw = DAILY_DISPATCH_STATE_PATH.read_text(encoding="utf-8")
            if raw.strip():
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    data = loaded
        data[key] = today_str
        data["updated_at"] = datetime.now(timezone(timedelta(hours=6))).isoformat()
        DAILY_DISPATCH_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not write dispatch state JSON: {e}")

def _is_direct_client_hunt_query(text: str) -> bool:
    """Detects if a free-text or voice message is asking for a Business X-Ray / ClientHunter operation."""
    if not text:
        return False
    lowered = text.lower()
    xray_keywords = [
        "এক্স-রে", "এক্স রে", "এক্সরে", "x-ray", "xray",
        "client hunter", "clienthunter", "ক্লায়েন্ট হান্টার", "ক্লায়েন্ট হান্টার",
        "বিজনেস অডিট", "business audit", "website audit", "লিড হান্ট"
    ]
    return any(kw in lowered for kw in xray_keywords)


async def safe_send_telegram_text(
    bot: Any,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    """Safely sends long Markdown messages in newline-aware chunks with automatic plain-text fallback."""
    if not text:
        return
    chunks: List[str] = []
    remaining = text
    while len(remaining) > 4000:
        split_at = remaining.rfind("\n", 0, 4000)
        if split_at <= 0:
            split_at = 4000
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip("\n")
    if remaining.strip():
        chunks.append(remaining.strip())

    for idx, chunk in enumerate(chunks):
        markup = reply_markup if idx == len(chunks) - 1 else None
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=markup
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_markup=markup
            )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command with greeting and mode picker."""
    user = update.effective_user
    user_id = user.id
    register_daily_subscriber(user_id)
    USER_MODES[user_id] = "auto"

    # Ensure session in SQLite
    mem = MemoryManager()
    mem.ensure_session(get_session_id(user_id), f"Telegram: {user.first_name}")

    keyboard = [
        [
            InlineKeyboardButton("✦ Auto মোড (স্মার্ট স্বয়ংক্রিয়)", callback_data="set_mode_auto"),
            InlineKeyboardButton("💬 Chat মোড (দ্রুত আলোচনা)", callback_data="set_mode_chat"),
        ],
        [
            InlineKeyboardButton("💼 Work মোড (এজেন্ট স্কোয়াড)", callback_data="set_mode_work"),
            InlineKeyboardButton("🏆 হ্যাকাথন সন্ধান ও মেন্টর", callback_data="trigger_hackathon"),
        ],
        [
            InlineKeyboardButton("🎯 ক্লায়েন্ট হান্টার ও বিজনেস এক্স-রে (/hunt)", callback_data="trigger_client_hunt"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 আসসালামু আলাইকুম স্যার!\n\n"
        "আমি আপনার **SMART AI ASSISTANT**। গুগল ২০২৬ আর্কিটেকচারে তৈরি আপনার একান্ত বিনয়ী, শ্রদ্ধাশীল ও স্বায়ত্তশাসিত ব্যক্তিগত সহকারী।\n\n"
        "✨ **স্যার, আমি কীভাবে আপনাকে সাহায্য করতে পারি?**\n"
        "• 🎙️ **ভয়েস নোট:** আমাকে সরাসরি বাংলায় ভয়েস মেসেজ পাঠান, আমি শুনে বাংলায় ভয়েসে উত্তর দেব!\n"
        "• 💬 **চ্যাট ও কথোপকথন:** যেকোনো সাধারণ আলোচনা বা প্রশ্নের ১-২ সেকেন্ডে দ্রুত উত্তর।\n"
        "• 🏆 **হ্যাকাথন স্কাউট ও মেন্টর (সকাল ৬:০০):** লাইভ এআই হ্যাকাথন সন্ধান, উইনিং আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ।\n"
        "• 🎯 **ক্লায়েন্ট হান্টার ও বিজনেস এক্স-রে (সকাল ৭:০০ ও ৭:১০):** রিয়েল বিজনেস ১০-পয়েন্ট অডিট, প্রাইসিং ও রেডিমেড প্রপোজাল লেটার (`/hunt` বা `/hunt fast`)।\n"
        "• 💻 **কোডিং ও ডাটা:** পাইথন কোড লেখা, স্যান্ডবক্স টেস্ট ও নিখুঁত অ্যানালাইসিস।\n\n"
        "👉 বর্তমান মোড: **✦ Auto (স্মার্ট স্বয়ংক্রিয় মোড)**\n"
        "যেকোনো প্রশ্ন লিখে বা মুখে কথা বলে পাঠান। মোড পরিবর্তন করতে নিচের বাটনে চাপ দিন অথবা `/auto` / `/work` / `/chat` / `/hackathon` / `/hunt` কমান্ড ব্যবহার করুন, স্যার।"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /mode command."""
    user_id = update.effective_user.id
    current = USER_MODES.get(user_id, "auto")

    keyboard = [
        [
            InlineKeyboardButton("✦ Auto মোড", callback_data="set_mode_auto"),
            InlineKeyboardButton("💬 Chat মোড", callback_data="set_mode_chat"),
            InlineKeyboardButton("💼 Work মোড", callback_data="set_mode_work"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"বর্তমান মোড: **{current.upper()}**\n\nস্যার, কোন মোডটি সক্রিয় করতে চান?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def set_auto_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick switch to Auto mode."""
    user_id = update.effective_user.id
    USER_MODES[user_id] = "auto"
    await update.message.reply_text("✅ **জি স্যার, Auto মোড সক্রিয় করা হয়েছে!**\nএখন সাধারণ কথপোকথনে দ্রুত উত্তর এবং কোডিং/হ্যাকাথন/ডাটা প্রশ্নে স্বয়ংক্রিয়ভাবে স্পেশালিস্ট সাব-এজেন্ট কাজ করবে।", parse_mode=ParseMode.MARKDOWN)

async def set_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick switch to Chat mode."""
    user_id = update.effective_user.id
    USER_MODES[user_id] = "chat"
    await update.message.reply_text("✅ **জি স্যার, Chat মোড সক্রিয় করা হয়েছে!**\nএখন যেকোনো সাধারণ প্রশ্ন ও কথপোকথনের ১-২ সেকেন্ডে দ্রুত উত্তর ও ভয়েস রিপ্লাই দেওয়া হবে।", parse_mode=ParseMode.MARKDOWN)

async def set_work_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick switch to Work mode."""
    user_id = update.effective_user.id
    USER_MODES[user_id] = "work"
    await update.message.reply_text("✅ **জি স্যার, Work মোড সক্রিয় করা হয়েছে!**\nএখন কোডিং, স্যান্ডবক্স টেস্ট, ডাটা, রিসার্চ ও হ্যাকাথনের জন্য স্পেশালিস্ট সাব-এজেন্ট স্কোয়াড সর্বদা প্রস্তুত।", parse_mode=ParseMode.MARKDOWN)

async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button clicks for mode selection and sub-agent actions."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else user_id
    if query.data == "set_mode_auto":
        USER_MODES[user_id] = "auto"
        await query.edit_message_text("✅ **জি স্যার, Auto মোড নির্বাচিত হয়েছে!**\nযেকোনো প্রশ্ন লিখে বা ভয়েস পাঠিয়ে নির্দেশ দিন।", parse_mode=ParseMode.MARKDOWN)
    elif query.data == "set_mode_chat":
        USER_MODES[user_id] = "chat"
        await query.edit_message_text("✅ **জি স্যার, Chat মোড নির্বাচিত হয়েছে!**\nযেকোনো প্রশ্ন লিখে বা মুখে কথা বলে পাঠান।", parse_mode=ParseMode.MARKDOWN)
    elif query.data == "set_mode_work":
        USER_MODES[user_id] = "work"
        await query.edit_message_text("✅ **জি স্যার, Work মোড নির্বাচিত হয়েছে!**\nস্পেশালিস্ট সাব-এজেন্ট স্কোয়াড এখন প্রস্তুত।", parse_mode=ParseMode.MARKDOWN)
    elif query.data == "trigger_hackathon":
        USER_MODES[user_id] = "work"
        await query.edit_message_text("🏆 **জি স্যার, হ্যাকাথন স্কাউট ও মেন্টর সক্রিয় করা হচ্ছে...**\nঅনুগ্রহ করে কোন ধরনের হ্যাকাথন বা আইডিয়া চান তা লিখে বা মুখে বলুন। অথবা `/hackathon` লিখুন।", parse_mode=ParseMode.MARKDOWN)
    elif query.data == "trigger_client_hunt":
        USER_MODES[user_id] = "work"
        await query.edit_message_text(
            "🎯 **জি স্যার, ClientHunter & Business X-Ray Sub-Agent সক্রিয় হচ্ছে...**\n"
            "যেকোনো সময় `/hunt` (১০ মিনিট পর ২য় মেসেজ), `/hunt fast` (১০ সেকেন্ড পর ২য় মেসেজ) অথবা `/hunt <category/location>` লিখে কমান্ড দিন। এখনই একটি লাইভ অডিট শুরু করা হচ্ছে...",
            parse_mode=ParseMode.MARKDOWN
        )
        await execute_and_send_client_hunt(context.application, chat_id, query_str="", delay_seconds=10)
    elif query.data == "send_proposal_now":
        pending = PENDING_PROPOSALS.get(chat_id)
        if pending:
            await send_client_hunter_step2(context.application, chat_id, pending)
        else:
            agent = ClientHunterAgent(model=get_active_model())
            workflow_data = await asyncio.to_thread(agent.execute_hunt_workflow, "", False)
            await send_client_hunter_step2(context.application, chat_id, workflow_data)
    elif query.data.startswith("deep_hackathon:"):
        hackathon_title = query.data.split("deep_hackathon:", 1)[1].strip()
        status = await query.message.reply_text(
            f"🏆 **জি স্যার, '{hackathon_title}' হ্যাকাথনের বিস্তারিত বিশ্লেষণ, উইনিং আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ তৈরি করা হচ্ছে...**",
            parse_mode=ParseMode.MARKDOWN
        )

        agent = HackathonAgent(model=get_active_model())
        task_prompt = f"চলমান হ্যাকাথন '{hackathon_title}'-এর বিস্তারিত বিচার বিশ্লেষণ, ৩টি উইনিং প্রজেক্ট আইডিয়া, টেক স্ট্যাক আর্কিটেকচার, ৪৮ ঘণ্টার মাইলফলক রোডম্যাপ এবং সাবমিশন গাইডেন্স দাও।"
        res = await asyncio.to_thread(agent.run, task_prompt)
        report = res.get("output", "")
        if not report or not report.strip():
            report = "আসসালামু আলাইকুম স্যার! হ্যাকাথনটির বিস্তারিত বিশ্লেষণ সফলভাবে তৈরি হয়েছে।"
        audio_bytes = await asyncio.to_thread(text_to_speech_bengali, report)

        try:
            await status.delete()
        except Exception:
            pass

        for chunk in [report[i:i+4000] for i in range(0, len(report), 4000)]:
            await query.message.reply_text(chunk)

        if audio_bytes:
            stream = io.BytesIO(audio_bytes)
            stream.name = "deep_hackathon_roadmap.mp3"
            await query.message.reply_voice(voice=stream, caption="🔊 বিস্তারিত হ্যাকাথন রোডম্যাপ অডিও")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears user session history."""
    user_id = update.effective_user.id
    mem = MemoryManager()
    new_sess = mem.create_session(f"Telegram: {update.effective_user.first_name}")
    await update.message.reply_text("🧹 জি স্যার, পূর্ববর্তী মেমরি পরিষ্কার করে নতুন ফ্রেশ সেশন শুরু করা হয়েছে!", parse_mode=ParseMode.MARKDOWN)

async def hackathon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /hackathon command to quickly scout competitions or brainstorm winning roadmaps."""
    user_id = update.effective_user.id
    register_daily_subscriber(user_id)
    USER_MODES[user_id] = "work"
    query_args = " ".join(context.args) if context.args else ""
    user_query = f"চলমান সেরা এআই হ্যাকাথনগুলো খুঁজে বের করো এবং উইনিং প্রজেক্ট আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ দাও {query_args}".strip()

    status_msg = await update.message.reply_text(
        "🏆 **হ্যাকাথন স্কাউট ও মেন্টর স্পেশালিস্ট সক্রিয় হচ্ছে...**\nDevpost, Kaggle ও Lablab.ai থেকে লাইভ হ্যাকাথন ও উইনিং আইডিয়া বিশ্লেষণ করা হচ্ছে...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        session_id = get_session_id(user_id)
        mem = MemoryManager()
        orch = MasterOrchestrator(memory_manager=mem, model=get_active_model())

        result = await asyncio.to_thread(
            orch.process_command,
            session_id=session_id,
            user_command=user_query,
            mode="work"
        )

        final_text = result.get("final_report", "").strip()
        if not final_text:
            final_text = "আসসালামু আলাইকুম স্যার! হ্যাকাথন সংক্রান্ত তথ্য ও বিশ্লেষণ সফলভাবে প্রস্তুত করা হয়েছে।"
        audio_bytes = result.get("audio_bytes")

        try:
            await status_msg.delete()
        except Exception:
            pass

        for chunk in [final_text[i:i+4000] for i in range(0, len(final_text), 4000)]:
            await update.message.reply_text(chunk)

        if audio_bytes:
            await update.message.chat.send_chat_action(ChatAction.RECORD_VOICE)
            voice_stream = io.BytesIO(audio_bytes)
            voice_stream.name = "hackathon_guide.mp3"
            await update.message.reply_voice(voice=voice_stream, caption="🔊 হ্যাকাথন গাইডেন্স অডিও")

    except Exception as e:
        logger.error(f"Hackathon command error: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ হ্যাকাথন তথ্য খুঁজতে ত্রুটি হয়েছে: {str(e)}")

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming Telegram voice notes and audio clips."""
    message = update.message
    user_id = update.effective_user.id
    register_daily_subscriber(user_id)
    session_id = get_session_id(user_id)
    mode = USER_MODES.get(user_id, "auto")

    await message.chat.send_chat_action(ChatAction.RECORD_VOICE)
    status_msg = await message.reply_text("🎧 আসসালামু আলাইকুম স্যার, আপনার ভয়েস শুনছি ও বিশ্লেষণ করছি...", parse_mode=ParseMode.MARKDOWN)

    try:
        # Download voice file
        voice = message.voice or message.audio
        voice_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        # Transcribe native audio
        transcribed_text = transcribe_audio_to_text(bytes(voice_bytes), mime_type="audio/ogg")
        if not transcribed_text or not transcribed_text.strip():
            await status_msg.edit_text("⚠️ কণ্ঠস্বর পরিষ্কার বোঝা যায়নি। দয়া করে আবার স্পষ্ট করে বলুন।")
            return

        await status_msg.edit_text(f"🗣️ **শনাক্তকৃত কথা:** \"_{transcribed_text}_\"\n\n🧠 উত্তর তৈরি হচ্ছে...", parse_mode=ParseMode.MARKDOWN)
        await message.chat.send_chat_action(ChatAction.TYPING)

        if _is_direct_client_hunt_query(transcribed_text):
            await execute_and_send_client_hunt(
                context.application,
                chat_id=message.chat_id,
                query_str=transcribed_text,
                delay_seconds=10
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
            return

        # Run multi-agent orchestrator in thread pool to avoid blocking asyncio event loop
        mem = MemoryManager()
        orch = MasterOrchestrator(memory_manager=mem, model=get_active_model())

        result = await asyncio.to_thread(
            orch.process_command,
            session_id=session_id,
            user_command=transcribed_text,
            mode=mode
        )

        final_text = result.get("final_report", "").strip()
        if not final_text:
            final_text = "আসসালামু আলাইকুম স্যার! আপনার ভয়েস নির্দেশটি সফলভাবে বিশ্লেষণ ও সম্পন্ন করা হয়েছে।"
        audio_bytes = result.get("audio_bytes")

        # Delete waiting status
        try:
            await status_msg.delete()
        except Exception:
            pass

        # Send text response (split if exceeds Telegram 4096 char limit)
        for chunk in [final_text[i:i+4000] for i in range(0, len(final_text), 4000)]:
            await message.reply_text(chunk)

        # Send spoken Bengali voice reply
        if audio_bytes:
            await message.chat.send_chat_action(ChatAction.RECORD_VOICE)
            voice_stream = io.BytesIO(audio_bytes)
            voice_stream.name = "response_voice.mp3"
            await message.reply_voice(voice=voice_stream, caption="🔊 বাংলা ভয়েস উত্তর")

    except Exception as e:
        logger.error(f"Telegram voice handling error: {e}", exc_info=True)
        await status_msg.edit_text(f"⚠️ আসসালামু আলাইকুম স্যার, ভয়েস প্রক্রিয়াকরণে ত্রুটি হয়েছে: {str(e)}")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming Telegram text messages."""
    message = update.message
    user_id = update.effective_user.id
    register_daily_subscriber(user_id)
    session_id = get_session_id(user_id)
    mode = USER_MODES.get(user_id, "auto")
    user_text = message.text.strip()

    if not user_text:
        return

    await message.chat.send_chat_action(ChatAction.TYPING)

    # Immediately acknowledge so user knows bot received their message and is working
    status_msg = await message.reply_text(
        "🧠 আসসালামু আলাইকুম স্যার, আপনার বার্তাটি বিশ্লেষণ ও সম্পন্ন করা হচ্ছে...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        if _is_direct_client_hunt_query(user_text):
            await execute_and_send_client_hunt(
                context.application,
                chat_id=message.chat_id,
                query_str=user_text,
                delay_seconds=10
            )
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            return

        mem = MemoryManager()
        orch = MasterOrchestrator(memory_manager=mem, model=get_active_model())

        result = await asyncio.to_thread(
            orch.process_command,
            session_id=session_id,
            user_command=user_text,
            mode=mode
        )

        final_text = result.get("final_report", "").strip()
        if not final_text:
            final_text = "আসসালামু আলাইকুম স্যার! আপনার নির্দেশটি সফলভাবে সম্পন্ন করা হয়েছে।"
        audio_bytes = result.get("audio_bytes")

        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

        # Send text response
        for chunk in [final_text[i:i+4000] for i in range(0, len(final_text), 4000)]:
            await message.reply_text(chunk)

        # Send spoken voice note
        if audio_bytes:
            await message.chat.send_chat_action(ChatAction.RECORD_VOICE)
            voice_stream = io.BytesIO(audio_bytes)
            voice_stream.name = "response_voice.mp3"
            await message.reply_voice(voice=voice_stream, caption="🔊 বাংলা ভয়েস উত্তর")

    except Exception as e:
        logger.error(f"Telegram text handling error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        await message.reply_text(
            f"⚠️ আসসালামু আলাইকুম স্যার, আপনার নির্দেশটি পালনে একটি সাময়িক সমস্যা হয়েছে:\n\n`{str(e)}`\n\n"
            f"স্যার, অনুগ্রহ করে পুনরায় চেষ্টা করুন অথবা ভিন্নভাবে প্রশ্ন করুন।"
        )

async def send_daily_hackathon_briefing(app: Application, chat_id: int):
    """Sends the 150-200 word morning hackathon briefing with an interactive detailed analysis button."""
    agent = HackathonAgent(model=get_active_model())
    briefing_data = await asyncio.to_thread(agent.generate_daily_briefing)

    text = briefing_data.get("briefing_text", "")
    h_title = briefing_data.get("title", "AI Hackathon")
    h_url = briefing_data.get("url", "https://devpost.com")

    # Interactive button: "🔍 বিস্তারিত জানতে চাই"
    keyboard = [
        [
            InlineKeyboardButton(
                "🔍 বিস্তারিত জানতে চাই",
                callback_data=f"deep_hackathon:{h_title[:45]}"
            )
        ],
        [
            InlineKeyboardButton("🌐 অফিশিয়াল রেজিস্ট্রেশন পেজ", url=h_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    header = "🌅 **দৈনিক সকাল ৬:০০ টার হ্যাকাথন সংবাদ ব্রিফিং**\n\n"
    full_message = f"{header}{text}"

    await app.bot.send_message(
        chat_id=chat_id,
        text=full_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

    # Spoken audio in Bengali
    try:
        audio_bytes = await asyncio.to_thread(text_to_speech_bengali, text)
        if audio_bytes:
            stream = io.BytesIO(audio_bytes)
            stream.name = "morning_hackathon_briefing.mp3"
            await app.bot.send_voice(chat_id=chat_id, voice=stream, caption="🔊 সকালের হ্যাকাথন সংবাদ অডিও")
    except Exception as audio_err:
        logger.warning(f"Morning briefing voice generation skipped: {audio_err}")

async def daily_briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """On-demand trigger for the daily 6:00 AM morning briefing format."""
    chat_id = update.effective_chat.id
    register_daily_subscriber(chat_id)
    status_msg = await update.message.reply_text(
        "🌅 **আসসালামু আলাইকুম স্যার, হ্যাকাথন সাব-এজেন্ট লাইভ হ্যাকাথন অনুসন্ধান ও সংবাদ ব্রিফিং তৈরি করছে...**",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        await send_daily_hackathon_briefing(context.application, chat_id)
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Daily briefing command error: {e}", exc_info=True)
        await status_msg.edit_text(f"⚠️ আসসালামু আলাইকুম স্যার, ব্রিফিং তৈরিতে সমস্যা হয়েছে: {str(e)}")

async def send_client_hunter_step1(app: Application, chat_id: int, workflow_data: Dict[str, Any], delay_seconds: int = 600):
    """Sends Step 1 Message (7:00 AM): Full 10-Point Business X-Ray Audit, Solutions & BDT Pricing Report."""
    PENDING_PROPOSALS[chat_id] = workflow_data
    report_text = workflow_data.get("audit_report_message", "")
    company_url = workflow_data.get("company", {}).get("website", "https://google.com")
    if not company_url.startswith(("http://", "https://")):
        company_url = "https://" + company_url

    delay_label = f"{delay_seconds} সেকেন্ড" if delay_seconds < 60 else f"{delay_seconds // 60} মিনিট"
    header = (
        f"🕖 **১ম মেসেজ: কোম্পানির পূর্ণাঙ্গ এক্স-রে অডিট, সমাধান ও প্রাইসিং রিপোর্ট**\n"
        f"*(২য় মেসেজ তথা রেডিমেড প্রপোজাল লেটার ঠিক {delay_label} পর স্বয়ংক্রিয়ভাবে আসবে)*\n\n"
    )
    full_msg = f"{header}{report_text}"

    keyboard = [
        [
            InlineKeyboardButton("📨 এখনই ২য় মেসেজ (প্রপোজাল লেটার) দেখুন", callback_data="send_proposal_now")
        ],
        [
            InlineKeyboardButton("🌐 টার্গেট কোম্পানির ওয়েবসাইট", url=company_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_send_telegram_text(app.bot, chat_id, full_msg, reply_markup=reply_markup)

async def send_client_hunter_step2(app: Application, chat_id: int, workflow_data: Dict[str, Any]):
    """Sends Step 2 Message (7:10 AM / after delay): Ready-Made High-Converting Smart Proposal Letter & 1-click WhatsApp link."""
    workflow_data["step2_sent"] = True
    proposal_text = workflow_data.get("proposal_letter_message", "")
    wa_url = workflow_data.get("company_whatsapp_url", "https://wa.me/8801700000000")
    company_name = workflow_data.get("company", {}).get("name", "টার্গেট কোম্পানি")

    header = f"🕙 **২য় মেসেজ: '{company_name}'-কে পাঠানোর রেডিমেড স্মার্ট প্রপোজাল লেটার**\n\n"
    full_msg = f"{header}{proposal_text}"

    keyboard = [
        [
            InlineKeyboardButton("📲 ১-ক্লিকে কোম্পানির WhatsApp-এ প্রপোজাল পাঠান", url=wa_url)
        ],
        [
            InlineKeyboardButton("🟢 আপনার অফিশিয়াল WhatsApp", url="https://wa.me/8801610594042")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_send_telegram_text(app.bot, chat_id, full_msg, reply_markup=reply_markup)

async def _delayed_step2_task(app: Application, chat_id: int, workflow_data: Dict[str, Any], delay_seconds: int):
    """Sleeps for delay_seconds (600s for 7:10 AM schedule, or 10s for /hunt fast) and automatically sends Step 2 Proposal Letter if not already sent."""
    try:
        await asyncio.sleep(delay_seconds)
        if workflow_data.get("step2_sent"):
            logger.info(f"Step 2 Proposal already viewed/sent for chat {chat_id}; skipping duplicate scheduled delivery.")
            return
        await send_client_hunter_step2(app, chat_id, workflow_data)
    except asyncio.CancelledError:
        logger.debug(f"Previous delayed Step 2 task cancelled for chat {chat_id}.")
    except Exception as e:
        logger.error(f"Delayed Step 2 Proposal send error for chat {chat_id}: {e}")

def _schedule_step2_for_chat(app: Application, chat_id: int, workflow_data: Dict[str, Any], delay_seconds: int):
    """Cancels any existing pending Step-2 timer for chat_id and schedules a fresh one."""
    prev_task = ACTIVE_STEP2_TASKS.get(chat_id)
    if prev_task and not prev_task.done():
        prev_task.cancel()
    ACTIVE_STEP2_TASKS[chat_id] = asyncio.create_task(
        _delayed_step2_task(app, chat_id, workflow_data, delay_seconds=delay_seconds)
    )

async def execute_and_send_client_hunt(
    app: Application,
    chat_id: int,
    query_str: str = "",
    delay_seconds: int = 600
) -> Dict[str, Any]:
    """Executes ClientHunterAgent, sends Message 1 immediately, and schedules Message 2 after delay_seconds."""
    agent = ClientHunterAgent(model=get_active_model())
    workflow_data = await asyncio.to_thread(agent.execute_hunt_workflow, query_str, True)

    await send_client_hunter_step1(app, chat_id, workflow_data, delay_seconds=delay_seconds)
    _schedule_step2_for_chat(app, chat_id, workflow_data, delay_seconds=delay_seconds)
    return workflow_data

async def hunt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /hunt, /hunt fast, and /hunt <category/location> commands."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    register_daily_subscriber(chat_id)
    USER_MODES[user_id] = "work"

    raw_args = list(context.args) if context.args else []
    is_fast = any(arg.lower() == "fast" for arg in raw_args)
    filtered_args = [arg for arg in raw_args if arg.lower() != "fast"]
    category_query = " ".join(filtered_args).strip()

    # 10 seconds delay in '/hunt fast' test mode, 600 seconds (10 minutes) in standard mode
    delay_seconds = 10 if is_fast else 600
    delay_desc = "১০ সেকেন্ড (`fast` টেস্ট মোড)" if is_fast else "১০ মিনিট (`600s` স্ট্যান্ডার্ড শিডিউল)"

    status_msg = await update.message.reply_text(
        f"🎯 **আসসালামু আলাইকুম স্যার! ClientHunter & Business X-Ray Sub-Agent সক্রিয় হয়েছে...**\n"
        f"🔍 রিয়েল টার্গেট বিজনেস খুঁজে তাদের ওয়েবসাইট, Meta Pixel (`fbq`), Google Analytics (`gtag`), AI Chatbot ও SEO লাইভ স্ক্যান করা হচ্ছে...\n"
        f"⏱️ ১ম মেসেজ এখনই আসবে এবং ২য় মেসেজ (প্রপোজাল লেটার) ঠিক **{delay_desc}** পর স্বয়ংক্রিয়ভাবে আসবে।",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await execute_and_send_client_hunt(
            context.application,
            chat_id=chat_id,
            query_str=category_query,
            delay_seconds=delay_seconds
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Hunt command error: {e}", exc_info=True)
        await status_msg.edit_text(f"⚠️ আসসালামু আলাইকুম স্যার, ক্লায়েন্ট হান্ট অডিটে ত্রুটি হয়েছে: {str(e)}")

async def daily_hackathon_scheduler_loop(app: Application):
    """Runs 24/7 in background to trigger daily hackathon briefing at or after 6:00 AM (UTC+6 / Bangladesh Time)
    with a Smart Catch-Up Window so delayed startups or sleeping containers never miss today's report.
    """
    logger.info("Daily 6:00 AM Hackathon Scheduler Loop initialized with Smart Catch-Up Window (UTC+6).")
    BD_TZ = timezone(timedelta(hours=6))
    mem = MemoryManager()

    while True:
        try:
            now_bd = datetime.now(BD_TZ)
            today_str = now_bd.strftime("%Y-%m-%d")
            last_sent = _get_last_dispatch_date("last_daily_hackathon_date", mem)

            # Smart Catch-Up Window: Trigger if 06:00 AM or later (UTC+6) and today's briefing has not been sent yet
            if now_bd.hour >= 6 and last_sent != today_str:
                logger.info(f"06:00 AM+ window active ({today_str})! Scouting hackathons and sending daily briefings...")
                subscribers = get_all_daily_subscribers(mem)
                sent_count = 0

                for cid in subscribers:
                    try:
                        await send_daily_hackathon_briefing(app, cid)
                        sent_count += 1
                    except Exception as sub_err:
                        logger.error(f"Failed to send 6:00 AM briefing to chat {cid}: {sub_err}")

                if sent_count > 0 or not subscribers:
                    _set_last_dispatch_date("last_daily_hackathon_date", today_str, mem)
                await asyncio.sleep(65)
        except Exception as loop_err:
            logger.error(f"Scheduler loop error: {loop_err}")

        await asyncio.sleep(25)

async def daily_client_hunter_scheduler_loop(app: Application):
    """Runs 24/7 in background to trigger ClientHunter & Business X-Ray every day at or after 7:00 AM (Asia/Dhaka, UTC+6)
    with a Smart Catch-Up Window, and automatically delivers the 2nd Proposal Letter message 10 minutes later (600s delay).
    """
    logger.info("Daily 7:00 AM / 7:10 AM ClientHunter & Business X-Ray Scheduler Loop initialized with Smart Catch-Up Window (UTC+6).")
    BD_TZ = timezone(timedelta(hours=6))
    mem = MemoryManager()

    while True:
        try:
            now_bd = datetime.now(BD_TZ)
            today_str = now_bd.strftime("%Y-%m-%d")
            last_hunt_date = _get_last_dispatch_date("last_daily_client_hunt_date", mem)

            # Smart Catch-Up Window: Trigger if 07:00 AM or later (Asia/Dhaka, UTC+6) and today's hunt report has not been sent yet
            if now_bd.hour >= 7 and last_hunt_date != today_str:
                logger.info(f"07:00 AM+ BD Time window active ({today_str})! Running Daily ClientHunter & Business X-Ray...")
                subscribers = get_all_daily_subscribers(mem)
                sent_count = 0

                if subscribers:
                    agent = ClientHunterAgent(model=get_active_model())
                    workflow_data = await asyncio.to_thread(agent.execute_hunt_workflow, "", True)

                    for cid in subscribers:
                        try:
                            chat_wf = dict(workflow_data)
                            chat_wf["step2_sent"] = False
                            # Step 1: Full Business X-Ray Audit, Solutions & Pricing Report
                            await send_client_hunter_step1(app, cid, chat_wf, delay_seconds=600)
                            # Step 2 scheduled for 10 minutes later (600 seconds)
                            _schedule_step2_for_chat(app, cid, chat_wf, delay_seconds=600)
                            sent_count += 1
                        except Exception as sub_err:
                            logger.error(f"Failed to send 7:00 AM ClientHunter report to chat {cid}: {sub_err}")

                if sent_count > 0 or not subscribers:
                    _set_last_dispatch_date("last_daily_client_hunt_date", today_str, mem)
                await asyncio.sleep(65)
        except Exception as loop_err:
            logger.error(f"ClientHunter scheduler loop error: {loop_err}")

        await asyncio.sleep(25)

def build_telegram_app(token: str) -> Application:
    """Builds and configures the Telegram Application."""
    async def post_init(application: Application):
        asyncio.create_task(daily_hackathon_scheduler_loop(application))
        asyncio.create_task(daily_client_hunter_scheduler_loop(application))

    app = Application.builder().token(token).post_init(post_init).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("auto", set_auto_mode))
    app.add_handler(CommandHandler("chat", set_chat_mode))
    app.add_handler(CommandHandler("work", set_work_mode))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("hackathon", hackathon_command))
    app.add_handler(CommandHandler("briefing", daily_briefing_command))
    app.add_handler(CommandHandler("daily_hackathon", daily_briefing_command))
    app.add_handler(CommandHandler("hunt", hunt_command))
    app.add_handler(CommandHandler("client_hunt", hunt_command))
    app.add_handler(CallbackQueryHandler(mode_callback))

    # Voice & Audio
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    # General Text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app

def run_telegram_bot():
    """Starts the bot via long-polling with resilient auto-reconnect."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.warning("TELEGRAM_BOT_TOKEN is not configured in .env. Bot worker will stay idle.")
        return

    logger.info("Starting Telegram Bot long-polling worker...")
    while True:
        try:
            app = build_telegram_app(token)
            app.run_polling(drop_pending_updates=False)
            break
        except Exception as e:
            logger.warning(f"Telegram polling transient error: {e}. Reconnecting in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    run_telegram_bot()

