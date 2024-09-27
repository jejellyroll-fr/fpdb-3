import sys
import locale
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import pytest
import Configuration
Configuration.LOCALE_ENCODING = 'utf-8'  
from Charset import to_utf8

class TestToUtf8:
    
    @pytest.fixture(scope="function", autouse=True)
    def set_locale(self):
        try:
            if sys.platform == "win32":
                locale.setlocale(locale.LC_ALL, "English_United States.1252")
            else:
                locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
        except locale.Error:
            print("Skipping locale setting due to unsupported locale.")

    def test_empty_string(self):
        assert to_utf8('') == b''

    def test_ascii_string(self):
        assert to_utf8('hello') == b'hello'

    def test_invalid_locale_encoding(self):
        with pytest.raises(UnicodeDecodeError):
            to_utf8(b'\xff')  # This byte is invalid in UTF-8

    def test_already_encoded_string(self):
        assert to_utf8(b'hello') == b'hello'

    def test_different_locale_encoding(self):
        # Temporarily change LOCALE_ENCODING to 'ISO-8859-1' for this test
        original_locale_encoding = Configuration.LOCALE_ENCODING
        try:
            Configuration.LOCALE_ENCODING = 'ISO-8859-1'
            valid_str = 'héllo'
            encoded_str = valid_str.encode('ISO-8859-1')
            expected_output = valid_str.encode('utf-8')  # This is equivalent to b'h\xc3\xa9llo'
            result = to_utf8(encoded_str)
            assert result == expected_output, f"Expected {expected_output!r}, but got {result!r}"
        finally:
            Configuration.LOCALE_ENCODING = original_locale_encoding
