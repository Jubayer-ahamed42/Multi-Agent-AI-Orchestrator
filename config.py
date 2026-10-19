import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Base Directories
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DB_PATH = BASE_DIR / "database" / "assistant_memory.db"
SANDBOX_PATH = BASE_DIR / os.getenv("SANDBOX_DIR", "sandbox")
SANDBOX_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Persistent Telegram Subscriber & Daily Schedule State Paths (Survives Render restarts)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SUBSCRIBERS_JSON_PATH = DATA_DIR / "telegram_subscribers.json"
DAILY_DISPATCH_STATE_PATH = DATA_DIR / "daily_dispatch_state.json"


def _build_default_subscriber_chat_ids() -> List[int]:
    """Builds the permanent list of subscriber Telegram chat_ids (never lost on Render container restarts)."""
    ids: List[int] = [6302370142]
    raw_env = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_SUBSCRIBER_IDS", "")
    for part in raw_env.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            cid = int(part)
            if cid not in ids:
                ids.append(cid)
    return ids


DEFAULT_SUBSCRIBER_CHAT_IDS: List[int] = _build_default_subscriber_chat_ids()

# Default LLM Settings (gemini-3.5-flash-lite provides 1,500 req/day quota on Free Tier vs 20 for flash)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini/gemini-3.5-flash-lite")
MAX_EVAL_RETRIES = int(os.getenv("MAX_EVAL_RETRIES", "3"))

# Supported Providers & Recommended Models
SUPPORTED_MODELS = {
    "Google Gemini": [
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-flash-latest",
        "gemini/gemini-3.5-flash",
        "gemini/gemini-3.6-flash"
    ],
    "OpenAI": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo"
    ],
    "Anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022"
    ]
}

def sanitize_model_name(model_name: str) -> str:
    """Sanitizes model name and ensures proper prefix."""
    m = model_name.strip() if model_name else DEFAULT_MODEL
    if "gemini-2.5" in m or "gemini-1.5" in m or "gemini-3.1" in m:
        return "gemini/gemini-3.5-flash"
    if m.startswith("gemini-"):
        return f"gemini/{m}"
    return m

def get_active_model() -> str:
    raw = os.getenv("ACTIVE_MODEL", DEFAULT_MODEL)
    return sanitize_model_name(raw)


def get_api_key_for_model(model_name: str) -> str:
    if "gemini" in model_name:
        key = os.getenv("GEMINI_API_KEY", "")
        return key.strip() if key else ""
    elif "gpt" in model_name:
        key = os.getenv("OPENAI_API_KEY", "")
        return key.strip() if key else ""
    elif "claude" in model_name:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        return key.strip() if key else ""
    return ""

def get_backup_api_key_for_model(model_name: str) -> str:
    if "gemini" in model_name:
        key = os.getenv("GEMINI_API_KEY_BACKUP", "")
        return key.strip() if key else ""
    return ""

def get_api_keys_pool(model_name: str) -> List[str]:
    """Returns a list of all configured API keys (primary + backup) for automatic failover."""
    keys = []
    primary = get_api_key_for_model(model_name)
    if primary:
        keys.append(primary)
    backup = get_backup_api_key_for_model(model_name)
    if backup and backup not in keys:
        keys.append(backup)
    return keys

def is_configured() -> bool:
    """Checks if at least one API key is present."""
    return bool(
        os.getenv("GEMINI_API_KEY") or 
        os.getenv("GEMINI_API_KEY_BACKUP") or
        os.getenv("OPENAI_API_KEY") or 
        os.getenv("ANTHROPIC_API_KEY") or
        os.getenv("SALES_CLOSER_GEMINI_KEY")
    )


# -------------------------------------------------------------
# Dedicated Sales Assistant Configuration ("Be Smart With AI")
# Zero collision with main project's API key
# -------------------------------------------------------------
SALES_CLOSER_GEMINI_KEY = os.getenv("SALES_CLOSER_GEMINI_KEY", "")
SALES_MODEL_NAME = os.getenv("SALES_MODEL_NAME", "gemini/gemini-3.5-flash")
MESSAGE_BUFFER_SECONDS = float(os.getenv("MESSAGE_BUFFER_SECONDS", "7.0"))
OWNER_TELEGRAM_CHAT_ID = os.getenv("OWNER_TELEGRAM_CHAT_ID", "6302370142")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
CRM_DATA_DIR = DATA_DIR / "crm"
CRM_DATA_DIR.mkdir(parents=True, exist_ok=True)
CRM_LEADS_CSV_PATH = CRM_DATA_DIR / "google_sheets_crm_leads.csv"
CRM_LEADS_JSON_PATH = CRM_DATA_DIR / "crm_leads.json"


def get_sales_api_key() -> str:
    """Returns the dedicated API key for smart_sales_assistant, strictly isolated from the main key."""
    key = os.getenv("SALES_CLOSER_GEMINI_KEY", "")
    return key.strip() if key else ""


def get_sales_model() -> str:
    """Returns the sanitized model name for smart_sales_assistant."""
    raw = os.getenv("SALES_MODEL_NAME", "gemini-3.5-flash")
    return sanitize_model_name(raw)


# -------------------------------------------------------------
# Official Facebook Page API Configuration ("Be Smart With AI")
# Source: Ahmad Personal Agent (Agent 1)
# -------------------------------------------------------------
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "1347013991822233")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
FB_APP_ID = os.getenv("FB_APP_ID", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")


def is_facebook_configured() -> bool:
    """Returns True if Facebook Page ID and Page Access Token are configured."""
    return bool(FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN)
