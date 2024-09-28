#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import locale

# Function to check if encoding is UTF-8
# This function checks if the given encoding name is 'utf-8' (case-insensitive).
def is_utf8_encoding(encoding_name):
    return encoding_name.lower() == 'utf-8'

# Initialization of encoders and locale encoding
# This function initializes global variables that check if the locale encoding is UTF-8.
# It uses the system's preferred encoding to set the 'locale_encoding' and then checks 
# if it's UTF-8 to set the global 'not_needed1', 'not_needed2', and 'not_needed3' variables.
def initialize_encoders():
    global not_needed1, not_needed2, not_needed3, locale_encoding
    locale_encoding = locale.getpreferredencoding()
    not_needed1 = not_needed2 = not_needed3 = is_utf8_encoding(locale_encoding)

# Call the initialization function when the script starts.
initialize_encoders()

# Function to convert a string to UTF-8 encoded bytes
# If the input is a string, it's encoded to UTF-8.
# If the input is already bytes, it returns the bytes as-is.
# For any other type, it raises a TypeError.
def to_utf8(s):
    if isinstance(s, str):
        return b'' if s == '' else s.encode('utf-8')
    elif isinstance(s, bytes):
        return s
    else:
        raise TypeError(f"Unsupported type for to_utf8: {type(s)}")


# Function to ensure data is ready for GUI display
# If the input is a string, it returns it unchanged.
# If the input is bytes, it decodes it to a string using UTF-8, replacing invalid characters.
# It raises a TypeError if the input is an integer or float, as they are unsupported.
def to_gui(s):
    if isinstance(s, str):
        return s
    elif isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    elif isinstance(s, (int, float)):
        raise TypeError(f"Unsupported type for to_gui: {type(s)}")
    else:
        return str(s)

# Function to convert a value to UTF-8 bytes for database storage
# If the system locale encoding is UTF-8 (not_needed2 is True), it will simply encode the string or return the bytes.
# If the encoding fails, it logs the error to stderr and raises an exception.
def to_db_utf8(s):
    if not_needed2:
        if isinstance(s, str):
            return s.encode('utf-8')
        elif isinstance(s, bytes):
            return s
        else:
            return str(s).encode('utf-8')

    try:
        # Convert to UTF-8 for the database
        return str(s).encode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        sys.stderr.write(f'Unable to convert: "{s!s}"\n')
        raise

# Function to set the locale encoding
# This function updates the global 'locale_encoding' and recalculates if UTF-8 conversion is needed 
# by updating the 'not_needed1', 'not_needed2', and 'not_needed3' variables.
def set_locale_encoding(encoding):
    global locale_encoding
    locale_encoding = encoding  # Update the locale encoding
    is_utf8_encoding(locale_encoding)
