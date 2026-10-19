import pytest
from tools.code_tools import execute_python_code
from tools.file_tools import write_sandbox_file, read_sandbox_file, list_sandbox_files

def test_python_code_execution_success():
    code = "print('Integration Test Passed: 42')"
    result = execute_python_code(code)
    assert result["success"] is True
    assert "Integration Test Passed: 42" in result["stdout"]
    assert result["returncode"] == 0

def test_python_code_execution_error_capture():
    code = "raise ValueError('Controlled Test Failure')"
    result = execute_python_code(code)
    assert result["success"] is False
    assert "Controlled Test Failure" in result["stderr"]
    assert result["returncode"] != 0

def test_security_blocked_pattern():
    dangerous_code = "import os; os.system('del important.txt')"
    result = execute_python_code(dangerous_code)
    assert result["success"] is False
    assert "Security Violation" in result["stderr"]

def test_sandbox_file_lifecycle():
    filename = "test_artifact.txt"
    write_res = write_sandbox_file(filename, "Hello Sandbox Data")
    assert write_res["success"] is True

    read_res = read_sandbox_file(filename)
    assert read_res["success"] is True
    assert read_res["content"] == "Hello Sandbox Data"

    list_res = list_sandbox_files()
    assert list_res["success"] is True
    assert any(f["name"] == filename for f in list_res["files"])
