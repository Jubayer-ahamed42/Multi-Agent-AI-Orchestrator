from pathlib import Path
from typing import List, Dict, Any, Optional
from config import BASE_DIR, SANDBOX_PATH

def _resolve_safe_path(rel_or_abs_path: str) -> Optional[Path]:
    """Resolves path and guarantees it strictly stays inside the sandbox or workspace."""
    # Strip any leading slashes or backslashes to prevent Windows root drive escapes
    clean_str = rel_or_abs_path.strip().lstrip("/\\")
    
    # If the user passed a path that starts relative to sandbox
    target = (SANDBOX_PATH / clean_str).resolve()
    
    # Safety boundary: only allow paths within BASE_DIR
    try:
        target.relative_to(BASE_DIR.resolve())
        return target
    except ValueError:
        return None

def write_sandbox_file(filename: str, content: str) -> Dict[str, Any]:
    """Writes text content to a file inside the sandbox."""
    safe_path = _resolve_safe_path(filename)
    if safe_path is None:
        return {"success": False, "error": f"Security restriction: Access outside workspace is forbidden: {filename}"}
    
    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(safe_path), "bytes_written": len(content.encode("utf-8"))}
    except Exception as e:
        return {"success": False, "error": str(e)}

def read_sandbox_file(filename: str) -> Dict[str, Any]:
    """Reads content from a file inside the sandbox or workspace."""
    safe_path = _resolve_safe_path(filename)
    if safe_path is None:
        return {"success": False, "error": f"Security restriction: Access outside workspace is forbidden: {filename}"}
    
    if not safe_path.exists():
        return {"success": False, "error": f"File not found: {filename}"}
    
    try:
        content = safe_path.read_text(encoding="utf-8")
        return {"success": True, "path": str(safe_path), "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_sandbox_files(subdir: str = "") -> Dict[str, Any]:
    """Lists files inside the sandbox directory."""
    target_dir = SANDBOX_PATH / subdir.strip().lstrip("/\\") if subdir else SANDBOX_PATH
    safe_path = _resolve_safe_path(str(target_dir))
    if safe_path is None or not safe_path.exists():
        return {"success": False, "files": [], "error": "Invalid or non-existent directory"}

    try:
        items = []
        for p in safe_path.glob("**/*"):
            if p.is_file():
                items.append({
                    "name": p.name,
                    "rel_path": str(p.relative_to(SANDBOX_PATH)),
                    "size_bytes": p.stat().st_size
                })
        return {"success": True, "files": items}
    except Exception as e:
        return {"success": False, "files": [], "error": str(e)}
