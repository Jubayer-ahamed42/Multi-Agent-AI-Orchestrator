import re
import json
import logging
from typing import Dict, Any, List, Optional
from config import get_active_model
from tools.search_tools import web_search
from agents.llm_client import call_llm

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Specialist sub-agent for information retrieval, web research, and fact-checking."""

    def __init__(self, model: Optional[str] = None):
        self.name = "Research & Fact-Checking Specialist"
        self.model = model or get_active_model()

    @staticmethod
    def _extract_queries(raw_response: str, fallback_task: str) -> List[str]:
        """Safely extracts 1-3 non-empty string search queries from LLM output."""
        if not raw_response or raw_response.strip().startswith("⚠️"):
            return [fallback_task.strip() or "latest technology news"]

        text = raw_response.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        candidate_str = match.group(0) if match else text

        try:
            parsed = json.loads(candidate_str)
            if isinstance(parsed, list):
                cleaned: List[str] = []
                seen = set()
                for item in parsed:
                    q_str = ""
                    if isinstance(item, str):
                        q_str = item.strip()
                    elif isinstance(item, dict):
                        q_str = str(item.get("query") or item.get("q") or "").strip()
                    if q_str and q_str.lower() not in seen:
                        seen.add(q_str.lower())
                        cleaned.append(q_str)
                if cleaned:
                    return cleaned[:3]
        except Exception as e:
            logger.debug(f"ResearchAgent query JSON parse fallback: {e}")

        return [fallback_task.strip() or "latest technology news"]

    @staticmethod
    def _build_fallback_report(task_description: str, search_results: List[Dict[str, str]]) -> str:
        """Deterministic fact-grounded report builder if LLM synthesis is unavailable or rate-limited."""
        lines = [
            "আসসালামু আলাইকুম স্যার!",
            "",
            f"আপনার নির্দেশিত বিষয় (**{task_description.strip()}**) নিয়ে লাইভ ওয়েব রিসার্চ ও ফ্যাক্ট-চেকিং সম্পন্ন করা হয়েছে স্যার। নিচে মূল তথ্য ও ফলাফল উপস্থাপন করা হলো:",
            ""
        ]
        if search_results:
            lines.append("### 🔍 প্রাপ্ত প্রধান তথ্য ও সোর্স বিশ্লেষণ:")
            for idx, item in enumerate(search_results[:6], 1):
                title = (item.get("title") or "তথ্যসূত্র").strip()
                snippet = (item.get("snippet") or "বিস্তারিত তথ্যের জন্য মূল লিংকটি দেখুন।").strip()
                url = (item.get("url") or "").strip()
                if url:
                    lines.append(f"{idx}. **{title}**\n   - **সারসংক্ষেপ:** {snippet}\n   - **সূত্র:** {url}")
                else:
                    lines.append(f"{idx}. **{title}** — {snippet}")
        else:
            lines.append("- স্যার, এই বিষয়ে তাৎক্ষণিক কোনো লাইভ ওয়েব সোর্স পাওয়া যায়নি, তবে প্রাসঙ্গিক বিশ্লেষণ প্রস্তুত করা হয়েছে।")

        lines.append("")
        lines.append("স্যার, এই বিষয়ে আরও গভীর কোনো নির্দিষ্ট তথ্য প্রয়োজন হলে আমাকে আদেশ করুন!")
        return "\n".join(lines)

    def run(self, task_description: str, critique: Optional[str] = None) -> Dict[str, Any]:
        """Executes research task using live web search and synthesizes findings."""
        clean_task = (task_description or "").strip() or "General Research Inquiry"
        trajectory: List[Dict[str, Any]] = []

        # 1. Generate targeted search queries
        query_plan_prompt = f"""You are a deep-research specialist. Given this research task, generate 2-3 optimal search queries.
Task: {clean_task}
{f'Previous Critique to Fix: {critique}' if critique else ''}

Respond ONLY with a JSON list of strings, e.g. ["query 1", "query 2"]
"""
        raw_queries = call_llm(
            messages=[{"role": "user", "content": query_plan_prompt}],
            model=self.model,
            temperature=0.1
        )
        queries = self._extract_queries(raw_queries, clean_task)

        # 2. Perform live search via tools with URL deduplication
        search_results: List[Dict[str, str]] = []
        seen_urls = set()
        for q in queries[:3]:
            trajectory.append({"action": "web_search", "query": q})
            results = web_search(q, max_results=3)
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                url = (r.get("url") or "").strip()
                dedup_key = url.lower() if url else (r.get("title") or "").strip().lower()
                if dedup_key and dedup_key not in seen_urls:
                    seen_urls.add(dedup_key)
                    search_results.append({
                        "title": str(r.get("title") or "").strip(),
                        "url": url,
                        "snippet": str(r.get("snippet") or "").strip()
                    })

        # 3. Synthesize findings into a structured research memo
        synth_prompt = f"""You are the Lead Research Analyst of SMART AI ASSISTANT.
Synthesize a comprehensive, fact-grounded research report for the following task.

Task: {clean_task}

Web Search Findings:
{json.dumps(search_results, ensure_ascii=False, indent=2)}

{f'CRITICAL: You must fix the previous issues identified by QA: {critique}' if critique else ''}

Mandatory Persona & Formatting Instructions:
- Start with "আসসালামু আলাইকুম স্যার!" and respectfully address the user as "স্যার" (Sir).
- Respond in the same language requested by the user (default to natural, clear Bengali if the prompt includes Bengali).
- Provide accurate, well-structured insights with bullet points and clear sections.
- Cite the source titles or URLs where relevant.
- State conclusions objectively and highlight key takeaways.
"""
        report = call_llm(
            messages=[{"role": "user", "content": synth_prompt}],
            model=self.model,
            temperature=0.3
        )

        if not report or not report.strip() or report.strip().startswith("⚠️"):
            report = self._build_fallback_report(clean_task, search_results)

        return {
            "subagent": self.name,
            "output": report,
            "sources": [r["url"] for r in search_results if r.get("url")],
            "trajectory": trajectory
        }

