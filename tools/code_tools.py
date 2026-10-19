import os
import sys
import uuid
import subprocess
import time
from pathlib import Path
from typing import Dict, Any
from config import SANDBOX_PATH

# Forbidden destructive patterns (Pillars 1 & 4 from Whitepaper 4)
DANGEROUS_PATTERNS = [
    "shutil.rmtree('c:",
    "shutil.rmtree(\"c:",
    "os.system('del",
    "os.system(\"del",
    "os.system('format",
    "os.system(\"format",
    "subprocess.popen(['rm",
    "subprocess.popen([\"rm",
    "ctypes.windll",
]

def execute_python_code(code: str, timeout: int = 15) -> Dict[str, Any]:
    """Executes Python code in an isolated sandbox environment with UTF-8 encoding support and security bounds.
    
    Args:
        code: Python source code to execute.
        timeout: Maximum execution time in seconds.
        
    Returns:
        Dict containing success (bool), stdout (str), stderr (str), returncode (int), execution_time_sec (float).
    """
    if not code or not code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "Empty Python code provided.",
            "returncode": -4,
            "execution_time_sec": 0.0
        }

    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in code.lower():
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Security Violation: Execution blocked due to dangerous pattern '{pattern}'",
                "returncode": -1,
                "execution_time_sec": 0.0
            }

    SANDBOX_PATH.mkdir(parents=True, exist_ok=True)
    script_path = SANDBOX_PATH / f"run_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}.py"
    try:
        # Guarantee UTF-8 writing for native language and symbols
        script_path.write_text(code, encoding="utf-8")
        start_time = time.time()

        # Enforce UTF-8 environment across Windows/Linux to prevent charmap/encoding crashes
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SANDBOX_PATH),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout
        )
        elapsed = time.time() - start_time

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "execution_time_sec": round(elapsed, 3)
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
            "returncode": -2,
            "execution_time_sec": float(timeout)
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"System Execution Error: {str(e)}",
            "returncode": -3,
            "execution_time_sec": 0.0
        }
    finally:
        # Keep sandbox clean
        if script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
