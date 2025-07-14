# Copyright 2009-2011 Matt Turnbull
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.

"""FPDB custom exceptions module.

This module defines custom exceptions used throughout the FPDB application.
"""

from typing import Any


class FpdbError(Exception):
    """Base exception class for FPDB errors."""

    def __init__(self, value: Any) -> None:
        """Initialize FpdbError with a value.

        Args:
            value: The error value or message.
        """
        self.value = value

    def __str__(self) -> str:
        """Return string representation of the error."""
        return repr(self.value)


class FpdbParseError(FpdbError):
    """Exception for parsing errors."""

    def __init__(self, value: str = "", hid: str = "") -> None:
        """Initialize FpdbParseError.

        Args:
            value: The error message.
            hid: The hand ID if applicable.
        """
        self.value = value
        self.hid = hid

    def __str__(self) -> str:
        """Return string representation of the parse error."""
        if self.hid:
            return repr("HID:" + self.hid + ", " + self.value)
        return repr(self.value)


class FpdbDatabaseError(FpdbError):
    """Exception for database errors."""



class FpdbMySQLError(FpdbDatabaseError):
    """Exception for MySQL database errors."""



class FpdbMySQLAccessDeniedError(FpdbDatabaseError):
    """Exception for MySQL access denied errors."""

    def __init__(self, value: str = "", errmsg: str = "") -> None:
        """Initialize FpdbMySQLAccessDeniedError.

        Args:
            value: The error value.
            errmsg: The error message.
        """
        self.value = value
        self.errmsg = errmsg

    def __str__(self) -> str:
        """Return string representation of the MySQL access denied error."""
        return repr(self.value + " " + self.errmsg)


class FpdbMySQLNoDatabaseError(FpdbDatabaseError):
    """Exception for MySQL no database errors."""

    def __init__(self, value: str = "", errmsg: str = "") -> None:
        """Initialize FpdbMySQLNoDatabaseError.

        Args:
            value: The error value.
            errmsg: The error message.
        """
        self.value = value
        self.errmsg = errmsg

    def __str__(self) -> str:
        """Return string representation of the MySQL no database error."""
        return repr(self.value + " " + self.errmsg)


class FpdbPostgresqlAccessDeniedError(FpdbDatabaseError):
    """Exception for PostgreSQL access denied errors."""

    def __init__(self, value: str = "", errmsg: str = "") -> None:
        """Initialize FpdbPostgresqlAccessDeniedError.

        Args:
            value: The error value.
            errmsg: The error message.
        """
        self.value = value
        self.errmsg = errmsg

    def __str__(self) -> str:
        """Return string representation of the PostgreSQL access denied error."""
        return repr(self.value + " " + self.errmsg)


class FpdbPostgresqlNoDatabaseError(FpdbDatabaseError):
    """Exception for PostgreSQL no database errors."""

    def __init__(self, value: str = "", errmsg: str = "") -> None:
        """Initialize FpdbPostgresqlNoDatabaseError.

        Args:
            value: The error value.
            errmsg: The error message.
        """
        self.value = value
        self.errmsg = errmsg

    def __str__(self) -> str:
        """Return string representation of the PostgreSQL no database error."""
        return repr(self.value + " " + self.errmsg)


class FpdbHandError(FpdbError):
    """Exception for hand processing errors."""



class FpdbHandDuplicateError(FpdbHandError):
    """Exception for duplicate hand errors."""



class FpdbHandPartialError(FpdbParseError):
    """Exception for partial hand errors."""



class FpdbHandSkippedError(FpdbParseError):
    """Exception for skipped hand errors."""



class FpdbEndOfFileError(FpdbHandError):
    """Exception for end of file errors."""



# Aliases for backward compatibility
FpdbMySQLAccessDenied = FpdbMySQLAccessDeniedError
FpdbMySQLNoDatabase = FpdbMySQLNoDatabaseError
FpdbPostgresqlAccessDenied = FpdbPostgresqlAccessDeniedError
FpdbPostgresqlNoDatabase = FpdbPostgresqlNoDatabaseError
FpdbHandDuplicate = FpdbHandDuplicateError
FpdbHandPartial = FpdbHandPartialError
FpdbHandSkipped = FpdbHandSkippedError
FpdbEndOfFile = FpdbEndOfFileError
