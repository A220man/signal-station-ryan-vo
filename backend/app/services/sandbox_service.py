"""Safety sandbox and boundary policy engine for coding agents."""
import os
import re
import shlex
import pathlib
import subprocess
from typing import Dict, Any, List, Tuple
from app.core.config import settings

# Dangerous commands and execution patterns that threaten host integrity or exfiltrate secrets
PROHIBITED_PATTERNS = [
    (r"\brm\s+-(?:rf|fr|r\s+-f|f\s+-r)\s+(?:/|/\*|~|~/\*|\$HOME)(?:\s|$)", "Destructive host deletion targeting root or home directory"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb process exhaustion"),
    (r"\b(?:nc|netcat|ncat)\b.*-(?:e|c)\b", "Reverse shell socket invocation"),
    (r"(?:/dev/tcp/|/dev/udp/)", "Raw bash network device socket escape"),
    (r"\b(?:mkfs|fdisk|parted|dd\s+if=/dev/zero)\b", "Direct block storage corruption or format operation"),
    (r"\b(?:chroot|mount|umount|iptables|sysctl)\b", "Host system namespace or kernel modification"),
    (r"\bcat\s+(?:/etc/shadow|/etc/sudoers|~/\.ssh/id_)", "Sensitive system credential exfiltration"),
    (r"\bcurl\b.*(?:\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b).*(?:token|secret|key|id_rsa)", "Exfiltration of secrets to external raw IP"),
    (r">\s*(?:/etc/|/boot/|/usr/|/bin/|/lib)", "Direct overwrite of system binaries or protected directories")
]

GUARDED_PATTERNS = [
    (r"\b(?:npm|yarn|pnpm)\s+install\b", "Package installation altering node_modules"),
    (r"\bpip(?:3)?\s+install\b", "Python package installation altering environment"),
    (r"\bgit\s+(?:push|reset\s+--hard|clean\s+-fd)\b", "Destructive Git history mutation or remote push"),
    (r"\bkill(?:all)?\s+-9\b", "Forceful process termination signal")
]

class SandboxService:
    @staticmethod
    def resolve_workspace(workspace_name_or_path: str) -> pathlib.Path:
        """Resolve workspace root safely inside the configured base workspace root."""
        base_dir = pathlib.Path(settings.workspace_root).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        
        target = pathlib.Path(workspace_name_or_path)
        if not target.is_absolute():
            target = base_dir / target
        
        target = target.resolve()
        
        # Verify target is contained in base_dir or is an authorized local testing directory
        try:
            target.relative_to(base_dir)
        except ValueError:
            repo_root = pathlib.Path(__file__).resolve().parents[3]
            try:
                target.relative_to(repo_root)
            except ValueError:
                import tempfile
                temp_dir = pathlib.Path(tempfile.gettempdir()).resolve()
                try:
                    target.relative_to(temp_dir)
                except ValueError:
                    raise ValueError(f"Workspace path '{workspace_name_or_path}' escapes authorized root.")
                
        target.mkdir(parents=True, exist_ok=True)
        return target

    @classmethod
    def verify_path_containment(cls, workspace_root: str, target_path: str) -> Tuple[bool, str, str]:
        """Verify that target_path strictly resolves within workspace_root without breakout."""
        try:
            root = cls.resolve_workspace(workspace_root)
            candidate = (root / target_path).resolve()
            
            # Check relative containment
            candidate.relative_to(root)
            
            # Check for symlink escaping out of root
            if candidate.is_symlink():
                real_dest = candidate.resolve()
                real_dest.relative_to(root)
                
            return True, str(candidate), "Path is strictly contained within authorized workspace."
        except ValueError:
            return False, "", "Path traversal violation: target escapes authorized workspace boundary."
        except Exception as e:
            return False, "", f"Path validation error: {str(e)}"

    @classmethod
    def analyze_command_risk(cls, command: str) -> Dict[str, Any]:
        """Analyze a command string and classify risk level into SAFE, GUARDED, or PROHIBITED."""
        clean_cmd = command.strip()
        if not clean_cmd:
            return {
                "command": command,
                "risk_level": "SAFE",
                "reason": "Empty command string.",
                "safe_to_execute": True,
                "flagged_patterns": []
            }

        flagged = []
        # Check prohibited rules
        for pattern, desc in PROHIBITED_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                flagged.append(desc)

        if flagged:
            return {
                "command": command,
                "risk_level": "PROHIBITED",
                "reason": f"Command rejected: matches prohibited patterns: {'; '.join(flagged)}.",
                "safe_to_execute": False,
                "flagged_patterns": flagged
            }

        # Check guarded rules
        for pattern, desc in GUARDED_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                flagged.append(desc)

        if flagged:
            return {
                "command": command,
                "risk_level": "GUARDED",
                "reason": f"Command flagged as guarded: {'; '.join(flagged)}. Requires operator permission.",
                "safe_to_execute": True,
                "flagged_patterns": flagged
            }

        return {
            "command": command,
            "risk_level": "SAFE",
            "reason": "Command passed security sandbox heuristic checks.",
            "safe_to_execute": True,
            "flagged_patterns": []
        }

    @classmethod
    def execute_sandboxed_command(
        cls,
        workspace_name_or_path: str,
        command: str,
        timeout_seconds: int = 15
    ) -> Dict[str, Any]:
        """Execute a shell command within the workspace sandbox directory if permitted."""
        risk = cls.analyze_command_risk(command)
        if not risk["safe_to_execute"]:
            return {
                "stdout": "",
                "stderr": f"SECURITY INTERCEPTION: {risk['reason']}",
                "exit_code": 126,
                "risk_assessment": risk
            }

        workspace_dir = cls.resolve_workspace(workspace_name_or_path)

        try:
            res = subprocess.run(
                command,
                cwd=str(workspace_dir),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={
                    **os.environ,
                    "WORKSPACE": str(workspace_dir),
                    "PYTHONPATH": f"{workspace_dir}:{os.environ.get('PYTHONPATH', '')}"
                }
            )
            return {
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
                "risk_assessment": risk
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout_seconds} seconds.",
                "exit_code": 124,
                "risk_assessment": risk
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}",
                "exit_code": 1,
                "risk_assessment": risk
            }
