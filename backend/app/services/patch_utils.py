"""Utility functions for whitespace-tolerant patching."""
def is_empty_line(line: str) -> bool:
    """Return True if line contains only whitespace."""
    return line.strip() == ""

def detect_base_indent(lines):
    """Return common indentation of non-empty lines, or empty string if none."""
    import re
    indents = set()
    for line in lines:
        if line.strip():
            m = re.match(r'^\s*', line)
            if m:
                indents.add(m.group( Některé)
    return indents.pop() if len(indents) == 1 else ""
