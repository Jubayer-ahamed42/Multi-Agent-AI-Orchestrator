import re
from typing import Dict, Any, List, Optional
from config import get_active_model
from tools.code_tools import execute_python_code
from agents.llm_client import call_llm


class DataAgent:
    """Specialist sub-agent for data analytics, statistical computation, and tabular metrics."""

    def __init__(self, model: Optional[str] = None):
        self.name = "Data Analytics & Calculations Specialist"
        self.model = model or get_active_model()

    @staticmethod
    def _extract_python_code(text: str) -> Optional[str]:
        """Extracts Python calculation script from ```python, ```py, or generic fenced blocks."""
        if not text:
            return None
        py_blocks = re.findall(r"```(?:python|py)\b\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if py_blocks and py_blocks[0].strip():
            return py_blocks[0].strip()
        return None

    def run(self, task_description: str, critique: Optional[str] = None) -> Dict[str, Any]:
        """Performs analytical reasoning, verifies computations using Python in the sandbox, and self-repairs if broken."""
        clean_task = (task_description or "").strip() or "Perform quantitative data analysis."
        trajectory: List[Dict[str, Any]] = []
        tool_errors: List[str] = []

        analysis_prompt = f"""You are the Principal Data Scientist and Quantitative Analyst of SMART AI ASSISTANT.
Task: {clean_task}

{f'CRITICAL CORRECTION REQUIRED: {critique}' if critique else ''}

Instructions:
1. Start politely with "আসসালামু আলাইকুম স্যার!" and address the user as "স্যার" (Sir).
2. If calculations, aggregations, or statistical transforms are required, write a self-contained Python script inside a ```python ... ``` block that prints the exact computed values.
3. NEVER use interactive `input()` or blocking GUI calls like `plt.show()`. Use standard library (`math`, `statistics`, `json`, `csv`) so it runs cleanly in a headless sandbox.
4. Present your findings in structured Markdown tables and bulleted key performance metrics.
"""
        initial_analysis = call_llm(
            messages=[{"role": "user", "content": analysis_prompt}],
            model=self.model,
            temperature=0.2
        )

        calc_script = self._extract_python_code(initial_analysis)
        exec_result = None

        if calc_script:
            trajectory.append({"action": "execute_data_calculation", "status": "running"})
            exec_result = execute_python_code(calc_script, timeout=15)
            if not exec_result["success"]:
                tool_errors.append(f"Calculation Error: {exec_result['stderr']}")
                trajectory.append({"action": "data_self_repair_attempt", "error": exec_result["stderr"]})

                repair_prompt = f"""The quantitative Python calculation script failed in the sandbox:
[ERROR LOG]:
{exec_result['stderr']}

[FAILED SCRIPT]:
{calc_script}

Fix the script (using Python standard library `math`/`statistics` without `input()` or `plt.show()`) and return the full corrected analysis starting with "আসসালামু আলাইকুম স্যার!" and the fixed ```python ... ``` block.
"""
                repaired_analysis = call_llm(
                    messages=[{"role": "user", "content": repair_prompt}],
                    model=self.model,
                    temperature=0.1
                )
                repaired_script = self._extract_python_code(repaired_analysis)
                if repaired_script:
                    re_exec = execute_python_code(repaired_script, timeout=15)
                    if re_exec["success"]:
                        initial_analysis = repaired_analysis
                        exec_result = re_exec
                        tool_errors.clear()
                        trajectory.append({"action": "calculation_repair_succeeded", "output": re_exec["stdout"]})
                    else:
                        tool_errors.append(f"Calculation repair also failed: {re_exec['stderr']}")
            else:
                trajectory.append({"action": "calculation_succeeded", "output": exec_result["stdout"]})

        if exec_result and exec_result.get("success") and exec_result.get("stdout"):
            stdout_val = exec_result["stdout"][:1500]
            if "ভেরিফাইড ক্যালকুলেশন রেজাল্ট" not in initial_analysis:
                initial_analysis = (
                    f"{initial_analysis.strip()}\n\n"
                    f"### 📊 ভেরিফাইড ক্যালকুলেশন রেজাল্ট (Verified Sandbox Computation):\n"
                    f"```text\n{stdout_val}\n```"
                )

        return {
            "subagent": self.name,
            "output": initial_analysis,
            "calculation_result": exec_result,
            "tool_errors": tool_errors,
            "trajectory": trajectory
        }

