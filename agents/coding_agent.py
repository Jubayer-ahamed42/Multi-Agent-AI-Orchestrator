import re
from typing import Dict, Any, List, Optional
from config import get_active_model
from tools.code_tools import execute_python_code
from tools.file_tools import write_sandbox_file
from agents.llm_client import call_llm


class CodingAgent:
    """Specialist sub-agent for software architecture, coding, testing, and debugging."""

    def __init__(self, model: Optional[str] = None):
        self.name = "Code & Automation Specialist"
        self.model = model or get_active_model()

    @staticmethod
    def _extract_python_code(text: str) -> Optional[str]:
        """Extracts Python code from ```python, ```py, or generic fenced code blocks."""
        if not text:
            return None
        py_blocks = re.findall(r"```(?:python|py)\b\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if py_blocks and py_blocks[0].strip():
            return py_blocks[0].strip()
        generic_blocks = re.findall(r"```(?:\w*)\n(.*?)```", text, re.DOTALL)
        if generic_blocks and generic_blocks[0].strip():
            return generic_blocks[0].strip()
        return None

    def run(self, task_description: str, critique: Optional[str] = None) -> Dict[str, Any]:
        """Generates code, runs it in the sandbox to verify functionality, and self-corrects if broken."""
        clean_task = (task_description or "").strip() or "Write a verified Python utility script."
        trajectory: List[Dict[str, Any]] = []
        tool_errors: List[str] = []

        code_prompt = f"""You are the Expert Software Engineer of SMART AI ASSISTANT.
Your goal is to write clean, complete, production-grade Python code for the following task:
Task: {clean_task}

{f'CRITICAL CORRECTION INSTRUCTIONS: {critique}' if critique else ''}

Rules:
1. Start your explanation politely with "আসসালামু আলাইকুম স্যার!" and address the user as "স্যার".
2. Provide the complete code inside a ```python ... ``` block.
3. NEVER use interactive `input()` calls—use sample arguments or test cases inside `if __name__ == '__main__':` so the script executes non-interactively in the sandbox.
4. Keep code modular, robust, and handle potential edge cases cleanly.
"""
        initial_solution = call_llm(
            messages=[{"role": "user", "content": code_prompt}],
            model=self.model,
            temperature=0.2
        )

        code_to_test = self._extract_python_code(initial_solution)
        exec_result = None

        if code_to_test:
            trajectory.append({"action": "execute_in_sandbox", "status": "running"})
            exec_result = execute_python_code(code_to_test, timeout=15)

            # If execution fails, try an automatic local self-repair cycle
            if not exec_result["success"]:
                tool_errors.append(f"Exit code {exec_result['returncode']}: {exec_result['stderr']}")
                trajectory.append({"action": "self_repair_attempt", "error": exec_result["stderr"]})

                repair_prompt = f"""The previous Python script failed execution in the sandbox with this error:
[ERROR LOG]:
{exec_result['stderr']}

[FAILED SCRIPT]:
{code_to_test}

Fix the script so it executes cleanly without error (do NOT use interactive `input()`).
Start with "আসসালামু আলাইকুম স্যার!" and return the corrected complete code in a ```python ... ``` block.
"""
                repaired_solution = call_llm(
                    messages=[{"role": "user", "content": repair_prompt}],
                    model=self.model,
                    temperature=0.1
                )
                repaired_code = self._extract_python_code(repaired_solution)
                if repaired_code:
                    re_exec = execute_python_code(repaired_code, timeout=15)
                    if re_exec["success"]:
                        initial_solution = repaired_solution
                        exec_result = re_exec
                        tool_errors.clear()
                        trajectory.append({"action": "self_repair_success", "stdout": re_exec["stdout"]})
                    else:
                        tool_errors.append(f"Repair attempt also failed: {re_exec['stderr']}")

        if exec_result and exec_result.get("success") and exec_result.get("stdout"):
            stdout_preview = exec_result["stdout"][:1500]
            if "স্যান্ডবক্স ভেরিফিকেশন আউটপুট" not in initial_solution:
                initial_solution = (
                    f"{initial_solution.strip()}\n\n"
                    f"### ✅ স্যান্ডবক্স ভেরিফিকেশন আউটপুট (Verified Execution Output):\n"
                    f"```text\n{stdout_preview}\n```"
                )

        return {
            "subagent": self.name,
            "output": initial_solution,
            "execution_result": exec_result,
            "tool_errors": tool_errors,
            "trajectory": trajectory
        }

