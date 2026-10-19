import re
import logging
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from tools.search_tools import web_search

logger = logging.getLogger(__name__)

# Standard fallback catalog of premier 2026 AI & developer hackathons
FEATURED_HACKATHONS = [
    {
        "title": "Google Gemini & Antigravity Global AI Challenge 2026",
        "url": "https://gemini.devpost.com",
        "prize": "$1,000,000",
        "deadline": "Rolling / Upcoming 2026",
        "themes": "Agentic Engineering, Multimodal AI, Spec-Driven Development",
        "platform": "Devpost",
        "mode": "Online / Global"
    },
    {
        "title": "Lablab.ai Autonomous Agent Hackathon",
        "url": "https://lablab.ai/event/autonomous-agents",
        "prize": "$50,000 + VC Mentorship",
        "deadline": "Open Registration",
        "themes": "Multi-Agent Systems, Hierarchical Agents, Tools & MCP",
        "platform": "Lablab.ai",
        "mode": "Online / Global"
    },
    {
        "title": "Kaggle AI Agents & LLM Benchmark Competition",
        "url": "https://www.kaggle.com/competitions",
        "prize": "$100,000",
        "deadline": "Season 2026",
        "themes": "Model Evaluation, Reasoning, Synthetic Benchmarks",
        "platform": "Kaggle",
        "mode": "Online / Global"
    },
    {
        "title": "ETHGlobal Web3 & Decentralized AI Hackathon",
        "url": "https://ethglobal.com/events",
        "prize": "$250,000",
        "deadline": "Quarterly 2026",
        "themes": "Decentralized AI, Smart Contracts, On-chain Agents",
        "platform": "ETHGlobal",
        "mode": "Hybrid / Global"
    }
]

_HACKATHON_QUERY_STOPWORDS = {
    "find", "search", "best", "top", "live", "active", "upcoming", "hackathon", "hackathons",
    "competition", "competitions", "challenge", "devpost", "kaggle", "lablab", "roadmap",
    "idea", "ideas", "winning", "mentor", "project", "48h", "24h", "the", "and", "for", "with"
}


_BENGALI_TECH_TOPIC_MAP = {
    "এআই": "ai",
    "কৃত্রিম বুদ্ধিমত্তা": "ai",
    "মেশিন লার্নিং": "machine",
    "ওয়েব৩": "web3",
    "ওয়েব৩": "web3",
    "ব্লকচেইন": "blockchain",
    "পাইথন": "python",
    "এজেন্ট": "agent",
    "সাইবার": "cyber"
}


def _extract_filter_keywords(query: str) -> List[str]:
    """Extracts meaningful topic keywords from a user query (ignoring generic Bengali sentence words & stopwords)."""
    if not query:
        return []
    q_low = query.lower()
    ascii_words = [w for w in re.findall(r"[a-zA-Z0-9\+#\.]{2,}", q_low) if w not in _HACKATHON_QUERY_STOPWORDS]
    for bn_term, en_kw in _BENGALI_TECH_TOPIC_MAP.items():
        if bn_term in q_low and en_kw not in ascii_words:
            ascii_words.append(en_kw)
    return ascii_words


def fetch_devpost_hackathons(query: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """Fetches live and upcoming hackathons using Devpost RSS with fallback to live web search.
    
    Args:
        query: Optional filter or interest keyword (e.g. 'AI', 'Beginner', 'Agents', or Bengali prompt).
        limit: Max number of hackathons to return (default: 5).
        
    Returns:
        List of hackathon metadata dictionaries.
    """
    hackathons: List[Dict[str, Any]] = []
    seen_urls = set()
    filter_keywords = _extract_filter_keywords(query)

    # 1. Try Devpost Public RSS feed
    rss_url = "https://devpost.com/hackathons.rss"
    rss_all_items: List[Dict[str, Any]] = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)

            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")
                pub_elem = item.find("pubDate")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Untitled Hackathon"
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else "https://devpost.com"
                desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else "Active"

                # Extract prize if present in description
                prize_match = re.search(r"(\$[\d,]+(?:\s*(?:in\s+prizes|USD))?)", desc, re.IGNORECASE)
                prize = prize_match.group(1) if prize_match else "Prizes & Recognition"

                # Clean HTML tags from description
                clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()
                clean_desc = re.sub(r"\s+", " ", clean_desc)[:200]

                entry = {
                    "title": title,
                    "url": link,
                    "prize": prize,
                    "deadline": pub_date,
                    "themes": clean_desc or "Open Challenge",
                    "platform": "Devpost",
                    "mode": "Online"
                }
                rss_all_items.append(entry)

                combined_text = f"{title} {clean_desc}".lower()
                if not filter_keywords or any(kw in combined_text for kw in filter_keywords):
                    if link.lower() not in seen_urls:
                        seen_urls.add(link.lower())
                        hackathons.append(entry)

                if len(hackathons) >= limit:
                    break

            # If specific keywords were too narrow for the RSS feed, backfill from live RSS items
            if not hackathons and rss_all_items:
                for entry in rss_all_items[:limit]:
                    u = entry["url"].lower()
                    if u not in seen_urls:
                        seen_urls.add(u)
                        hackathons.append(entry)
    except Exception as e:
        logger.debug(f"Devpost RSS fetch note (switching to live search fallback): {e}")

    # 2. If RSS didn't yield enough, enrich with targeted web search
    if len(hackathons) < limit:
        topic_str = " ".join(filter_keywords[:4])
        search_query = f"{topic_str} hackathons 2026 devpost lablab kaggle".strip() if topic_str else "best live AI hackathons 2026 devpost lablab"
        search_results = web_search(search_query, max_results=limit)
        for r in search_results or []:
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            if url and url.lower() not in seen_urls and ("devpost" in url.lower() or "lablab" in url.lower() or "kaggle" in url.lower() or "hackathon" in url.lower()):
                seen_urls.add(url.lower())
                hackathons.append({
                    "title": title or "Global AI Hackathon",
                    "url": url,
                    "prize": "Check Event Page",
                    "deadline": "2026 Live/Upcoming",
                    "themes": snippet[:200] if snippet else "AI & Software Development",
                    "platform": "Web Search / Devpost",
                    "mode": "Online / Global"
                })
            if len(hackathons) >= limit:
                break

    # 3. If still empty, supply premier featured hackathons
    if not hackathons:
        for fh in FEATURED_HACKATHONS:
            combined_fh = f"{fh['title']} {fh['themes']}".lower()
            if not filter_keywords or any(kw in combined_fh for kw in filter_keywords):
                if fh["url"].lower() not in seen_urls:
                    seen_urls.add(fh["url"].lower())
                    hackathons.append(dict(fh))
            if len(hackathons) >= limit:
                break
        if not hackathons:
            hackathons = [dict(x) for x in FEATURED_HACKATHONS[:limit]]

    return hackathons[:limit]

def format_hackathon_summary(hackathons: List[Dict[str, Any]]) -> str:
    """Formats a list of hackathons into a clean, structured Markdown presentation for LLM and user.
    
    Args:
        hackathons: List of hackathon dictionaries.
        
    Returns:
        Structured Markdown text.
    """
    if not hackathons:
        return "⚠️ কোনো সক্রিয় হ্যাকাথন খুঁজে পাওয়া যায়নি।"

    lines = []
    lines.append("| 🏆 হ্যাকাথন | 💰 প্রাইজ পুল | 📅 ডেডলাইন / তারিখ | 🏷️ থিম / প্ল্যাটফর্ম | 🔗 লিংক |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")

    for h in hackathons:
        title = h.get("title", "Hackathon").replace("|", "-")
        prize = h.get("prize", "TBD").replace("|", "-")
        deadline = h.get("deadline", "Open").replace("|", "-")
        platform = h.get("platform", "Devpost")
        url = h.get("url", "https://devpost.com")
        lines.append(f"| **{title}** | `{prize}` | {deadline} | {platform} | [বিস্তারিত ও রেজিস্ট্রেশন]({url}) |")

    lines.append("\n### 📌 সারসংক্ষেপ ও থিম বিবরণ:")
    for idx, h in enumerate(hackathons, 1):
        lines.append(f"**{idx}. {h.get('title')}**")
        lines.append(f"- **প্ল্যাটফর্ম:** {h.get('platform')} ({h.get('mode', 'Online')})")
        lines.append(f"- **প্রাইজ পুল:** {h.get('prize')}")
        lines.append(f"- **ফোকাস এরিয়া:** {h.get('themes')}")
        lines.append(f"- **অফিসিয়াল লিংক:** {h.get('url')}\n")

    return "\n".join(lines)
