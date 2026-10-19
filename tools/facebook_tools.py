"""Facebook Official Graph API Tools for 'Be Smart With AI' Page.
Credentials migrated from Ahmad Personal Agent (C:/Personal Agent/Agent 1).
"""

import os
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional

from config import FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN, is_facebook_configured

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def get_facebook_page_info(page_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetches public profile information for the 'Be Smart With AI' Facebook Page."""
    pid = (page_id or os.getenv("FB_PAGE_ID", FB_PAGE_ID)).strip()
    token = (access_token or os.getenv("FB_PAGE_ACCESS_TOKEN", FB_PAGE_ACCESS_TOKEN)).strip()

    if not pid or not token:
        return {
            "success": False,
            "error": "FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not configured in .env."
        }

    url = f"{GRAPH_API_BASE}/{pid}?fields=id,name,category,link,about,phone,website&access_token={token}"
    req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "success": True,
                "page_id": data.get("id"),
                "name": data.get("name"),
                "category": data.get("category"),
                "link": data.get("link"),
                "about": data.get("about"),
                "phone": data.get("phone"),
                "website": data.get("website")
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        logger.error(f"[Facebook API] HTTP error {e.code}: {err_body}")
        return {"success": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        logger.error(f"[Facebook API] Network error: {e}")
        return {"success": False, "error": str(e)}


def publish_facebook_page_post(message: str, page_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
    """Publishes a text post to the Facebook Page feed."""
    clean_msg = (message or "").strip()
    if not clean_msg:
        return {"success": False, "error": "Post message cannot be empty."}

    pid = (page_id or os.getenv("FB_PAGE_ID", FB_PAGE_ID)).strip()
    token = (access_token or os.getenv("FB_PAGE_ACCESS_TOKEN", FB_PAGE_ACCESS_TOKEN)).strip()

    if not pid or not token:
        return {
            "success": False,
            "error": "FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not configured in .env."
        }

    url = f"{GRAPH_API_BASE}/{pid}/feed"
    payload = json.dumps({"message": clean_msg, "access_token": token}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            post_id = data.get("id")
            return {
                "success": True,
                "post_id": post_id,
                "post_url": f"https://www.facebook.com/{post_id}" if post_id else None
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        logger.error(f"[Facebook API Post] HTTP error {e.code}: {err_body}")
        return {"success": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        logger.error(f"[Facebook API Post] Error: {e}")
        return {"success": False, "error": str(e)}
