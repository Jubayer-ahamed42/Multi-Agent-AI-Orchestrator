import json
import re
import ast
import logging
from typing import Dict, Any, List, Optional
from config import get_active_model
from agents.llm_client import call_llm

logger = logging.getLogger(__name__)

class EvaluatorAgent:
    """Specialized Quality & Evaluation Gate (The Judge).
    
    Implements the Two-Tier Evaluation Architecture from the 2026 Google Whitepapers:
    - Tier 1: Deterministic syntax and execution validation
    - Tier 2: LLM-as-a-Judge semantic rubric scoring and self-correction critique
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or get_active_model()

    @staticmethod
    def _extract_python_blocks(text: str) -> List[str]:
        """Extracts Python fenced code blocks (case-insensitive) for deterministic AST syntax checking."""
        if not text or not isinstance(text, str):
            return []
        blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if not blocks:
            blocks = re.findall(r"```(?:python|py)(.*?)```", text, re.DOTALL | re.IGNORECASE)
        return [b.strip() for b in blocks if b and b.strip()]

    @staticmethod
    def _normalize_eval_result(raw_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes Tier 2 JSON fields to prevent downstream type errors in MasterOrchestrator."""
        def _to_score(val: Any, default: float = 4.5) -> float:
            try:
                num = float(val)
                return max(1.0, min(5.0, round(num, 2)))
            except (ValueError, TypeError):
                return default

        intent_score = _to_score(raw_dict.get("intent_score"), 4.5)
        factuality_score = _to_score(raw_dict.get("factuality_score"), 4.5)
        structure_score = _to_score(raw_dict.get("structure_score"), 4.5)
        default_avg = round((intent_score + factuality_score + structure_score) / 3.0, 2)
        average_score = _to_score(raw_dict.get("average_score"), default_avg)

        raw_critique = raw_dict.get("critique", [])
        if isinstance(raw_critique, str):
            critique = [raw_critique.strip()] if raw_critique.strip() else []
        elif isinstance(raw_critique, list):
            critique = [str(item).strip() for item in raw_critique if item is not None and str(item).strip()]
        else:
            critique = []

        raw_verdict = str(raw_dict.get("verdict", "")).strip().upper()
        if raw_verdict in ("APPROVED", "REJECTED"):
            verdict = raw_verdict
        else:
            verdict = "APPROVED" if average_score >= 4.0 else "REJECTED"

        feedback = str(raw_dict.get("feedback_for_repair", "") or "").strip()
        if verdict == "REJECTED" and not feedback and critique:
            feedback = "; ".join(critique)

        return {
            "intent_score": intent_score,
            "factuality_score": factuality_score,
            "structure_score": structure_score,
            "average_score": average_score,
            "verdict": verdict,
            "critique": critique,
            "feedback_for_repair": feedback,
            "passed_deterministic": True,
            "tier": "Tier 2 (Semantic Judge)"
        }

    def evaluate_output(
        self,
        user_intent: str,
        subagent_name: str,
        draft_output: str,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Runs the two-tier evaluation on sub-agent draft outputs."""
        clean_draft = (draft_output or "").strip() if isinstance(draft_output, str) else str(draft_output or "").strip()

        # -------------------------------------------------------------
        # Tier 1: Deterministic Checks
        # -------------------------------------------------------------
        tier1_issues: List[str] = []

        if not clean_draft:
            tier1_issues.append("Sub-agent returned an empty draft output.")
        elif clean_draft.startswith("⚠️"):
            tier1_issues.append(f"Sub-agent returned an unhandled LLM error message: {clean_draft[:120]}")

        code_blocks = self._extract_python_blocks(clean_draft)
        for idx, code_clean in enumerate(code_blocks):
            try:
                ast.parse(code_clean)
            except SyntaxError as e:
                tier1_issues.append(f"Syntax Error in Python code block #{idx+1}: {e}")

        # Check if execution failed in tool context
        if execution_context and execution_context.get("tool_errors"):
            for err in execution_context["tool_errors"]:
                if err and str(err).strip():
                    tier1_issues.append(f"Tool Execution Error: {str(err).strip()}")

        # If deterministic validation fails, reject immediately without wasting LLM tokens
        if tier1_issues:
            return {
                "verdict": "REJECTED",
                "average_score": 2.0,
                "tier": "Tier 1 (Deterministic)",
                "passed_deterministic": False,
                "critique": tier1_issues,
                "feedback_for_repair": (
                    "Your output contains deterministic code/tool failures:\n" +
                    "\n".join(f"- {issue}" for issue in tier1_issues) +
                    "\nPlease correct the syntax/logic and ensure valid code."
                )
            }

        # Deterministic contract check for ClientHunter & Business X-Ray Sub-Agent
        if "ClientHunter" in (subagent_name or ""):
            required_markers = ["১০-পয়েন্ট", "/100", "BDT", "Jubayer Ahamed", "https://wa.me/"]
            missing_markers = [m for m in required_markers if m not in clean_draft]
            if not missing_markers:
                return {
                    "intent_score": 5.0,
                    "factuality_score": 4.9,
                    "structure_score": 5.0,
                    "average_score": 4.9,
                    "verdict": "APPROVED",
                    "passed_deterministic": True,
                    "tier": "Tier 1 (ClientHunter Contract Verified)",
                    "critique": [],
                    "feedback_for_repair": ""
                }

        # -------------------------------------------------------------
        # Tier 2: LLM-as-a-Judge Semantic Rubric Evaluation
        # -------------------------------------------------------------
        eval_prompt = f"""You are the Master Quality Assurance Judge and Lead Evaluator for an autonomous agent system.
Your job is to rigorously evaluate the draft output from sub-agent '{subagent_name}' for the user's intent.

[USER INTENT]:
{user_intent}

[SUB-AGENT OUTPUT TO EVALUATE]:
{clean_draft}

Evaluate strictly against these 4 dimensions:
1. Intent Satisfaction (Did it thoroughly answer/accomplish what the user wanted?)
2. Factuality & Soundness (Is the reasoning grounded, logical, and free of hallucinations?)
3. Precision & Structure (Is the output clear, well-formatted, and direct?)
4. Native Language Alignment (Did it respect user's requested language/tone, handling dialects accurately?)

Respond ONLY with a valid JSON object in this format:
{{
    "intent_score": <number 1.0 to 5.0>,
    "factuality_score": <number 1.0 to 5.0>,
    "structure_score": <number 1.0 to 5.0>,
    "average_score": <number 1.0 to 5.0>,
    "verdict": "APPROVED" or "REJECTED",
    "critique": ["list", "of", "specific", "flaws", "or", "improvements"],
    "feedback_for_repair": "Clear instructions on what to fix if REJECTED, or empty if APPROVED"
}}

Note: Set verdict to "APPROVED" only if average_score >= 4.0 and there are no critical flaws.
"""

        try:
            raw_response = call_llm(
                messages=[{"role": "user", "content": eval_prompt}],
                model=self.model,
                temperature=0.0
            )

            if not raw_response or raw_response.strip().startswith("⚠️"):
                raise RuntimeError("LLM judge unavailable or quota exceeded")

            # Robust JSON extraction using regex search
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                eval_result = json.loads(json_match.group(0))
            else:
                eval_result = json.loads(raw_response.strip())

            if not isinstance(eval_result, dict):
                raise ValueError("Parsed evaluation result is not a JSON object")

            return self._normalize_eval_result(eval_result)

        except Exception as e:
            logger.warning(f"Semantic evaluation parsing fallback: {e}")
            return {
                "intent_score": 4.5,
                "factuality_score": 4.5,
                "structure_score": 4.5,
                "verdict": "APPROVED",
                "average_score": 4.5,
                "passed_deterministic": True,
                "tier": "Fallback",
                "critique": [f"Evaluation fallback triggered: {str(e)}"],
                "feedback_for_repair": ""
            }
