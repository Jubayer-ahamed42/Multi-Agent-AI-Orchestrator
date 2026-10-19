import logging
import warnings
from typing import List, Dict, Any

warnings.filterwarnings("ignore", category=RuntimeWarning, message=r".*duckduckgo_search.*renamed.*")

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

def _ddg_html_fallback(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Fallback HTML search against html.duckduckgo.com when DDGS library returns empty."""
    import re
    import html as html_lib
    import urllib.parse
    import urllib.request

    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw_html = resp.read(250_000).decode("utf-8", errors="ignore")

    items: List[Dict[str, str]] = []
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
        raw_html,
        re.DOTALL | re.IGNORECASE
    )
    for raw_href, raw_title, raw_snip in blocks:
        clean_url = raw_href
        uddg_match = re.search(r"[?&]uddg=([^&]+)", raw_href)
        if uddg_match:
            clean_url = urllib.parse.unquote(uddg_match.group(1))
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        snippet = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_snip or "")).strip()
        if title and clean_url.startswith("http"):
            items.append({"title": title, "url": clean_url, "snippet": snippet})
            if len(items) >= max_results:
                break
    return items


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Performs a live web search using DuckDuckGo to find real-time sources and facts.
    
    Args:
        query: Search query string.
        max_results: Maximum number of results to fetch (default: 5).
        
    Returns:
        List of dictionaries with title, url, and snippet.
    """
    formatted: List[Dict[str, str]] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })
    except Exception as e:
        logger.debug(f"Primary DDGS search note for '{query}': {e}")

    if not formatted:
        try:
            formatted = _ddg_html_fallback(query, max_results=max_results)
        except Exception as fb_err:
            logger.warning(f"Fallback search note for '{query}': {fb_err}")

    return formatted

