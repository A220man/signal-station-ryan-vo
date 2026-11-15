def test_empty_line_helper():
    from app.services.patch_utils import is_empty_line
    assert is_empty_line("") == True
    assert is_empty_line("   ") == True
    assert is_empty_line("  x  ") == False
    assert is_empty_line("x") == False

def test_detect_base_indent():
    from app.services.patch_utils import detect_base_indent
    assert detect_base_indent(["  a", "  b", "    c"]) == "  "
    assert detect_base_indent(["a", "b"]) == ""
    assert detect_base_indent([]) == ""
