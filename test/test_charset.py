# test_charset.py
import pytest
import sys
import platform
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from Charset import to_utf8, to_db_utf8, to_gui, set_locale_encoding, initialize_encoders

# Tests for `to_utf8`
@pytest.mark.parametrize("input_value, expected_output", [
    # Test with string inputs (UTF-8 encoding)
    ("test string", b"test string"),
    ("string with accents éèà", b"string with accents \xc3\xa9\xc3\xa8\xc3\xa0"),
    ("テスト", b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88"),
    
    # Test with bytes (already encoded in UTF-8)
    (b"test string", b"test string"),
    (b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88", b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88"),
])
def test_to_utf8_valid(input_value, expected_output):
    assert to_utf8(input_value) == expected_output

@pytest.mark.parametrize("invalid_input", [
    12345,  # An integer is not supported
    12.34,  # A float is not supported
    [],     # A list is not supported
])
def test_to_utf8_invalid_type(invalid_input):
    with pytest.raises(TypeError):
        to_utf8(invalid_input)

# Tests for `to_db_utf8`
@pytest.mark.parametrize("input_value, expected_output", [
    ("test string", b"test string"),  # UTF-8 string
    ("テスト", b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88"),  # Japanese characters
    (b"test string", b"test string"),  # Bytes input
    (b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88", b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88"),  # UTF-8 bytes
])
def test_to_db_utf8(input_value, expected_output):
    assert to_db_utf8(input_value) == expected_output

@pytest.mark.parametrize("invalid_input", [
    12345,  # Integer should be converted to string then encoded
    12.34,  # Float should be converted to string then encoded
])
def test_to_db_utf8_non_string(invalid_input):
    result = to_db_utf8(invalid_input)
    assert isinstance(result, bytes)

# Tests for `to_gui`
@pytest.mark.parametrize("input_value, expected_output", [
    ("test string", "test string"),  # Already UTF-8 string
    (b"test string", "test string"),  # UTF-8 bytes
    ("テスト", "テスト"),  # Japanese characters
    (b"\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88", "テスト"),  # Japanese UTF-8 bytes
])
def test_to_gui(input_value, expected_output):
    assert to_gui(input_value) == expected_output

@pytest.mark.parametrize("invalid_input", [
    12345,  # Integer is not supported
    12.34,  # Float is not supported
])
def test_to_gui_invalid_type(invalid_input):
    with pytest.raises(TypeError):
        to_gui(invalid_input)

# Test for `set_locale_encoding` and initialization

def test_set_locale_encoding():
    from Charset import locale_encoding, set_locale_encoding
    
    # Save the initial system locale encoding
    initial_locale_encoding = locale_encoding
    
    # Change encoding to ASCII
    set_locale_encoding("ascii")
    
    # macOS might ignore this and stay UTF-8
    if platform.system() == "Darwin":
        assert locale_encoding == 'UTF-8'
    else:
        assert locale_encoding == 'ascii'
    
    # Restore the initial encoding after the test
    set_locale_encoding(initial_locale_encoding)

def test_initialize_encoders():
    initialize_encoders()  # Check that this function does not raise any errors

