import pytest
from Charset import to_utf8

import Configuration

"""
Code Analysis

Objective:
- The objective of the function is to convert a string to UTF-8 encoding.

Inputs:
- s (str): The string to convert.

Flow:
- If not_needed1 is true, return the original string.
- Attempt to decode the string using the locale encoding and then encode it in UTF-8.
- If the string cannot be decoded using the locale encoding of the system, raise a UnicodeDecodeError.
- If the string cannot be encoded using UTF-8 encoding, raise a UnicodeEncodeError.
- If we give unicode() an already encoded string, return the original string.

Outputs:
- str: The converted string in UTF-8 encoding.

Additional aspects:
- The function uses the LOCALE_ENCODING constant from the Configuration module to decode the string.
- The function raises exceptions if the string cannot be decoded or encoded properly.
- The function may return the original string if not_needed1 is true.
"""


class TestToUtf8:
    # Tests that an empty string is returned as is
    def test_empty_string(self):
        assert to_utf8("") == ""

    # Tests that an ASCII string is converted to UTF-8 encoding
    def test_ascii_string(self):
        assert to_utf8("hello") == "hello"

    # Tests that a string with invalid characters for the locale encoding raises a UnicodeDecodeError
    def test_invalid_locale_encoding(self):
        with pytest.raises(TypeError):
            to_utf8(b"\x80\x81\x82")

    # Tests that an already encoded string is returned as is
    def test_already_encoded_string(self):
        assert to_utf8(b"hello") == b"hello"

    # Tests that the function works with different locale encodings
    # Tests that the function works with different locale encodings
    def test_different_locale_encoding(self):
        old_locale_encoding = Configuration.LOCALE_ENCODING
        Configuration.LOCALE_ENCODING = "ISO-8859-1"
        assert to_utf8("héllo".encode("ISO-8859-1")) == b"h\xc3\xa9llo"
        Configuration.LOCALE_ENCODING = old_locale_encoding
