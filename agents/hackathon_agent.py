import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import BASE_DIR, get_active_model
from tools.hackathon_tools import fetch_devpost_hackathons, format_hackathon_summary, FEATURED_HACKATHONS
from agents.llm_client import call_llm

logger = logging.getLogger(__name__)

SEEN_HACKATHONS_PATH = BASE_DIR / "data" / "seen_hackathons.json"


class HackathonAgent:
    """Specialist sub-agent for scouting live hackathons, mentoring, and crafting winning project roadmaps."""

    def __init__(self, model: Optional[str] = None, seen_storage_path: Optional[Path] = None):
        self.name = "Hackathon Scout & Mentor Specialist"
        self.model = model or get_active_model()
        self.seen_storage_path = Path(seen_storage_path) if seen_storage_path else SEEN_HACKATHONS_PATH

    def _select_fresh_hackathon(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Selects an unseen hackathon from candidates (or rotates cleanly if all were seen)."""
        pool = list(candidates or [])
        for fh in FEATURED_HACKATHONS:
            if not any(c.get("url") == fh["url"] for c in pool):
                pool.append(dict(fh))

        if not pool:
            return dict(FEATURED_HACKATHONS[0])

        seen_urls: List[str] = []
        try:
            if self.seen_storage_path.exists():
                raw = json.loads(self.seen_storage_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    seen_urls = [str(x).lower() for x in raw]
                elif isinstance(raw, dict):
                    seen_urls = [str(x).lower() for x in raw.get("seen_urls", [])]
        except Exception:
            seen_urls = []

        selected = None
        for item in pool:
            u = str(item.get("url") or "").strip().lower()
            if u and u not in seen_urls:
                selected = item
                break

        if selected is None:
            # All current candidates have been shown; reset cycle and pick next
            seen_urls = []
            selected = pool[0]

        sel_url = str(selected.get("url") or "").strip().lower()
        if sel_url and sel_url not in seen_urls:
            seen_urls.append(sel_url)
            try:
                self.seen_storage_path.parent.mkdir(parents=True, exist_ok=True)
                self.seen_storage_path.write_text(
                    json.dumps({"seen_urls": seen_urls[-50:]}, indent=2),
                    encoding="utf-8"
                )
            except Exception as e:
                logger.debug(f"Failed to persist seen_hackathons.json: {e}")

        return selected

    @staticmethod
    def _build_fallback_daily_briefing(top_hackathon: Dict[str, Any]) -> str:
        """Deterministic 150-200 word Bengali morning briefing if LLM is rate-limited."""
        title = top_hackathon.get("title", "Global AI Hackathon 2026")
        platform = top_hackathon.get("platform", "Devpost")
        prize = top_hackathon.get("prize", "Prizes & Recognition")
        deadline = top_hackathon.get("deadline", "Upcoming 2026")
        themes = top_hackathon.get("themes", "AI Agents, LLMs & Automation")
        url = top_hackathon.get("url", "https://devpost.com")
        return (
            f"আসসালামু আলাইকুম স্যার! শুভ সকাল।\n\n"
            f"📢 **তথ্য (Basic Info):**\n"
            f"আজকের সেরা আন্তর্জাতিক হ্যাকাথন হলো **{title}**। এটি **{platform}** প্ল্যাটফর্মে আয়োজিত হচ্ছে। "
            f"এর প্রাইজ পুল **{prize}** এবং ডেডলাইন/স্ট্যাটাস: **{deadline}** (লিংক: {url})।\n\n"
            f"🎯 **বিষয়বস্তু (What it's about):**\n"
            f"এই প্রতিযোগিতার মূল ফোকাস এরিয়া হলো—{themes}। এখানে বাস্তব জীবনের সমস্যার সমাধানে "
            f"অটোনোমাস এআই এজেন্ট এবং স্কেলেবল সফটওয়্যার প্রোটোটাইপ তৈরি করতে হবে।\n\n"
            f"💡 **আমাদের প্রজেক্ট সাজেশন (Our Project Suggestion):**\n"
            f"স্যার, আমরা আমাদের **Multi-Agent Orchestrator & Business X-Ray** আর্কিটেকচার ব্যবহার করে একটি "
            f"**Autonomous SME Growth & Voice Copilot** প্রজেক্ট সাবমিট করতে পারি, যা বিচারকদের কাছে অত্যন্ত ইউনিক ও হাই-ইমপ্যাক্ট হবে।\n\n"
            f"স্যার, এই হ্যাকাথনের বিস্তারিত বিশ্লেষণ ও রোডম্যাপ জানতে নিচের বাটনে ক্লিক করুন।"
        )

    def run(self, task_description: str, critique: Optional[str] = None) -> Dict[str, Any]:
        """Executes hackathon scouting or mentoring based on user task intent."""
        clean_task = (task_description or "").strip() or "চলমান সেরা এআই হ্যাকাথন ও রোডম্যাপ"
        trajectory: List[Dict[str, Any]] = []
        task_lower = clean_task.lower()

        mentoring_keywords = [
            "roadmap", "idea", "winning", "mentor", "pitch", "readme", "architecture",
            "stack", "48h", "24h", "রোডম্যাপ", "আইডিয়া", "আইডিয়া", "প্রজেক্ট", "পিচ", "জিতব", "পরিকল্পনা"
        ]
        is_mentoring = any(k in task_lower for k in mentoring_keywords)

        if is_mentoring:
            trajectory.append({"action": "mentoring_strategy_analysis", "target": clean_task})
            hackathons = fetch_devpost_hackathons(clean_task, limit=3)
            sources = [h["url"] for h in hackathons if h.get("url")]
            summary_md = format_hackathon_summary(hackathons)

            mentor_prompt = f"""You are the World's Leading Hackathon Mentor & Chief Judge of SMART AI ASSISTANT.
Analyze this hackathon challenge or topic and craft an elite, winning competition blueprint.
Task: {clean_task}

Context & Active Competitions:
{summary_md}

{f'CRITICAL - QA Critique to Fix from previous iteration: {critique}' if critique else ''}

Generate an exhaustive, highly practical blueprint containing:
1. 💡 **Top 3 Winning Project Ideas**:
   - Give each idea a catchy name, core problem statement, why it will stand out to judges (Novelty + Real-world Impact), and alignment with Google 2026 Whitepaper agentic architectures.
2. ⏱️ **48-Hour Milestone Execution Timeline**:
   - Hour 0–12: Spec-Driven Design, API keys, basic prototype.
   - Hour 12–24: Core multi-agent loop, tool integration, database.
   - Hour 24–36: Frontend UI, error handling, automated evaluation.
   - Hour 36–48: Demo video recording, polish, pitch deck, and submission.
3. 🛠️ **Recommended Tech Stack & Architecture**:
   - Best language, LLM/Agent SDK (Gemini 3.5, LiteLLM, LangGraph), UI (Streamlit / Next.js), and hosting.
4. 🎤 **Winning Pitch Deck Outline & Submission README Template**:
   - 7-slide pitch deck structure.
   - Markdown code snippet for the official GitHub/Devpost README.

Instructions:
- Start with "আসসালামু আলাইকুম স্যার!" and address the user respectfully as "স্যার" (Sir).
- Respond in clear, inspiring Bengali with technical terms in English where appropriate.
- Ensure ideas are realistic for a 24h-48h build while appearing visionary to hackathon judges.
"""
            report = call_llm(
                messages=[{"role": "user", "content": mentor_prompt}],
                model=self.model,
                temperature=0.4
            )
            if not report or not report.strip() or report.strip().startswith("⚠️"):
                report = (
                    f"আসসালামু আলাইকুম স্যার!\n\n"
                    f"আপনার নির্দেশিত হ্যাকাথন মেন্টরিং ও ৪৮ ঘণ্টার রোডম্যাপ নিচে প্রস্তুত করা হলো স্যার:\n\n"
                    f"{summary_md}\n\n"
                    f"### 💡 উইনিং প্রজেক্ট আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ:\n"
                    f"- **আইডিয়া ১:** Autonomous Multi-Agent Business Copilot (Gemini + Voice + Telegram)\n"
                    f"- **ঘণ্টা ০–১২:** প্রবলেম ডেফিনিশন ও কোর এজেন্ট আর্কিটেকচার সেটআপ।\n"
                    f"- **ঘণ্টা ১২–২৪:** লাইভ টুলস, স্যান্ডবক্স ও ডাটাবেজ ইন্টিগ্রেশন।\n"
                    f"- **ঘণ্টা ২৪–৩৬:** ড্যাশবোর্ড UI ও QA সেলফ-কারেকশন লুপ।\n"
                    f"- **ঘণ্টা ৩৬–৪৮:** ২ মিনিটের ডেমো ভিডিও, পিচ ডেক ও README সাবমিশন।"
                )

            return {
                "subagent": self.name,
                "output": report,
                "sources": sources,
                "trajectory": trajectory
            }

        else:
            trajectory.append({"action": "fetch_devpost_hackathons", "query": clean_task})
            hackathons = fetch_devpost_hackathons(clean_task, limit=5)
            sources = [h["url"] for h in hackathons if h.get("url")]
            summary_markdown = format_hackathon_summary(hackathons)

            scout_prompt = f"""You are the Elite Hackathon Scout and Talent Advisor of SMART AI ASSISTANT.
The user is looking for active, live, or upcoming hackathons and competitions.

User Request: {clean_task}

Raw Hackathon Data:
{summary_markdown}

{f'CRITICAL - QA Critique to Fix: {critique}' if critique else ''}

Instructions:
1. Start with "আসসালামু আলাইকুম স্যার!" and address the user respectfully as "স্যার" (Sir).
2. Present the structured comparative table of top hackathons (Name, Prize Pool, Deadline, Platform, Registration Link).
3. For each hackathon, explain:
   - What the challenge is about.
   - Why it is worth participating in.
   - Recommended preparation steps and eligibility.
4. Conclude with tailored recommendations on which hackathon best matches the user's profile and how our AI Assistant squad can mentor them to build a winning project.
5. Write fluently in clear, polite Bengali with professional formatting.
"""
            report = call_llm(
                messages=[{"role": "user", "content": scout_prompt}],
                model=self.model,
                temperature=0.3
            )
            if not report or not report.strip() or report.strip().startswith("⚠️"):
                report = (
                    f"আসসালামু আলাইকুম স্যার!\n\n"
                    f"আপনার নির্দেশ অনুযায়ী বর্তমানের সেরা লাইভ হ্যাকাথনগুলোর তালিকা ও বিশ্লেষণ নিচে পেশ করা হলো স্যার:\n\n"
                    f"{summary_markdown}\n"
                    f"স্যার, এর মধ্যে যেকোনো একটি হ্যাকাথন বেছে নিলে আমি সাথে সাথে সেটির পূর্ণাঙ্গ উইনিং প্রজেক্ট আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ তৈরি করে দেব!"
                )

            return {
                "subagent": self.name,
                "output": report,
                "sources": sources,
                "trajectory": trajectory
            }

    def generate_daily_briefing(self) -> Dict[str, Any]:
        """Generates a concise (150-200 words) daily morning hackathon briefing with fresh hackathon rotation."""
        hackathons = fetch_devpost_hackathons("", limit=8)
        top_hackathon = self._select_fresh_hackathon(hackathons)

        briefing_prompt = f"""You are SMART AI ASSISTANT's Elite Hackathon Scout.
Prepare the daily 6:00 AM Hackathon News Briefing for Sir ("স্যার").

[FEATURED HACKATHON DATA]:
Title: {top_hackathon.get('title')}
Platform: {top_hackathon.get('platform', 'Devpost')}
Prize Pool: {top_hackathon.get('prize', 'TBA')}
Deadline: {top_hackathon.get('deadline', 'Upcoming')}
Theme/Scope: {top_hackathon.get('themes', 'AI Agents, LLMs, Developer Tools')}
URL: {top_hackathon.get('url')}

MANDATORY RULES:
1. WORD LIMIT: Strictly within 150 to 200 words. Keep it crisp, sharp, inspiring, and fast to read in under 1 minute.
2. ETIQUETTE & GREETING:
   - Greet warmly: "আসসালামু আলাইকুম স্যার! শুভ সকাল।"
   - Address the user with highest respect as "স্যার" throughout the response.
3. THREE-PART STRUCTURE:
   - 📢 **তথ্য (Basic Info):** হ্যাকাথনের নাম, প্ল্যাটফর্ম, প্রাইজ মানি ও ডেডলাইন।
   - 🎯 **বিষয়বস্তু (What it's about):** এটি কী নিয়ে হবে এবং এর মূল চ্যালেঞ্জ কী।
   - 💡 **আমাদের প্রজেক্ট সাজেশন (Our Project Suggestion):** আমরা এই হ্যাকাথনে কী ধরনের উদ্ভাবনী প্রজেক্ট বা সল্যুশন নিয়ে কাজ করতে পারি।
4. CONCLUDING PROMPT:
   - শেষে এক লাইনে উল্লেখ করুন: "স্যার, এই হ্যাকাথনের বিস্তারিত বিশ্লেষণ ও রোডম্যাপ জানতে নিচের বাটনে ক্লিক করুন।"
5. Language: Fluent, elegant, natural Bengali with standard tech terms.
"""
        report = call_llm(
            messages=[{"role": "user", "content": briefing_prompt}],
            model=self.model,
            temperature=0.3,
            max_tokens=600
        )

        if not report or not report.strip() or report.strip().startswith("⚠️"):
            report = self._build_fallback_daily_briefing(top_hackathon)

        return {
            "briefing_text": report,
            "hackathon": top_hackathon,
            "title": top_hackathon.get("title", "AI Hackathon"),
            "url": top_hackathon.get("url", "https://devpost.com")
        }

