"""Whitespace-tolerant patch and edit resilience engine for coding agents."""
import difflib
import pathlib
import re
from typing import Dict, Any, Tuple, Optional, List

class PatchService:
    @staticmethod
    def normalize_line_endings(text: str) -> str:
        """Convert CRLF and CR to standard LF line endings."""
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def strip_line_trailing_whitespace(text: str) -> str:
        """Strip trailing spaces and tabs from each line."""
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines)

    @classmethod
    def apply_patch_string(
        cls,
        original_content: str,
        target_snippet: str,
        replacement_snippet: str,
        tolerance_mode: str = "normalized_whitespace"
    ) -> Tuple[bool, str, str, str]:
        """Apply replacement snippet to original content using tiered matching strategies."""
        orig_norm = cls.normalize_line_endings(original_content)
        target_norm = cls.normalize_line_endings(target_snippet)
        repl_norm = cls.normalize_line_endings(replacement_snippet)

        # Strategy 1: Exact string match
        if target_norm in orig_norm:
            patched = orig_norm.replace(target_norm, repl_norm, 1)
            diff = cls.generate_unified_diff(orig_norm, patched, "target_file")
            return True, patched, "exact", diff

        if tolerance_mode == "exact":
            return False, orig_norm, "none", "Exact match failed: target snippet not found."

        # Strategy 2: Normalized whitespace & indentation match
        success, patched, diff = cls._match_normalized_whitespace(orig_norm, target_norm, repl_norm)
        if success:
            return True, patched, "normalized_whitespace", diff

        if tolerance_mode == "normalized_whitespace":
            return False, orig_norm, "none", "Normalized whitespace match failed: snippet differs beyond spacing/indentation."

        # Strategy 3: Fuzzy hunk alignment
        success, patched, diff = cls._match_fuzzy_hunk(orig_norm, target_norm, repl_norm)
        if success:
            return True, patched, "fuzzy_hunk", diff

        return False, orig_norm, "none", "Fuzzy hunk match failed: no candidate region met alignment threshold (>=0.85)."

    @classmethod
    def _match_normalized_whitespace(
        cls,
        content: str,
        target: str,
        replacement: str
    ) -> Tuple[bool, str, str]:
        """Match lines ignoring differences in trailing whitespace and relative indentation style."""
        content_lines = content.split("\n")
        target_lines = [l.strip() for l in target.split("\n") if l.strip()]
        
        if not target_lines:
            return False, content, ""

        # Search for a contiguous block in content_lines whose stripped lines match target_lines
        window_size = len(target_lines)
        found_start = -1
        found_end = -1

        for i in range(len(content_lines) - window_size + 1):
            window_stripped = [l.strip() for l in content_lines[i : i + window_size] if l.strip()]
            if window_stripped == target_lines:
                found_start = i
                found_end = i + window_size
                break

        if found_start != -1:
            # Detect indentation of the target block
            matched_first_line = content_lines[found_start]
            indent_match = re.match(r"^(\s*)", matched_first_line)
            detected_indent = indent_match.group(1) if indent_match else ""

            # Re-indent replacement lines consistently
            replacement_lines = replacement.split("\n")
            adjusted_replacement = []
            for idx, r_line in enumerate(replacement_lines):
                if idx == 0:
                    adjusted_replacement.append(detected_indent + r_line.lstrip())
                else:
                    adjusted_replacement.append(r_line)

            new_lines = content_lines[:found_start] + adjusted_replacement + content_lines[found_end:]
            patched = "\n".join(new_lines)
            diff = cls.generate_unified_diff(content, patched, "target_file")
            return True, patched, diff

        return False, content, ""

    @classmethod
    def _match_fuzzy_hunk(
        cls,
        content: str,
        target: str,
        replacement: str,
        similarity_threshold: float = 0.85
    ) -> Tuple[bool, str, str]:
        """Align snippet using SequenceMatcher across sliding line windows."""
        content_lines = content.split("\n")
        target_lines = target.split("\n")
        window_size = len(target_lines)

        if window_size == 0 or len(content_lines) < window_size:
            return False, content, ""

        best_ratio = 0.0
        best_index = -1

        for i in range(len(content_lines) - window_size + 1):
            candidate_block = "\n".join(content_lines[i : i + window_size])
            ratio = difflib.SequenceMatcher(None, target, candidate_block).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_index = i

        if best_ratio >= similarity_threshold and best_index != -1:
            replacement_lines = replacement.split("\n")
            new_lines = content_lines[:best_index] + replacement_lines + content_lines[best_index + window_size:]
            patched = "\n".join(new_lines)
            diff = cls.generate_unified_diff(content, patched, "target_file")
            return True, patched, diff

        return False, content, ""

    @staticmethod
    def generate_unified_diff(original: str, modified: str, filename: str) -> str:
        """Produce standard unified diff text between two strings."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=3
        )
        return "".join(diff)

    @classmethod
    def apply_file_patch(
        cls,
        file_path: pathlib.Path,
        target_snippet: str,
        replacement_snippet: str,
        tolerance_mode: str = "normalized_whitespace"
    ) -> Dict[str, Any]:
        """Read target file, apply patch with selected tolerance mode, and rewrite safely."""
        if not file_path.is_file():
            return {
                "success": False,
                "strategy_applied": "none",
                "hunks_applied": 0,
                "total_hunks": 1,
                "diff_preview": "",
                "message": f"Target file '{file_path}' does not exist."
            }

        original_content = file_path.read_text(encoding="utf-8")
        success, patched_content, strategy, diff = cls.apply_patch_string(
            original_content,
            target_snippet,
            replacement_snippet,
            tolerance_mode
        )

        if success:
            file_path.write_text(patched_content, encoding="utf-8")
            return {
                "success": True,
                "strategy_applied": strategy,
                "hunks_applied": 1,
                "total_hunks": 1,
                "diff_preview": diff,
                "message": f"Successfully applied patch using '{strategy}' strategy."
            }
        else:
            return {
                "success": False,
                "strategy_applied": "none",
                "hunks_applied": 0,
                "total_hunks": 1,
                "diff_preview": "",
                "message": diff  # contains failure explanation
            }
