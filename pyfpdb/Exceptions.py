#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2009-2011 Matt Turnbull 
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

class FpdbError(Exception):
    """Base exception class for Fpdb-related errors."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class FpdbParseError(FpdbError):
    """Exception class for parsing errors in Fpdb."""
    def __init__(self, value='', hid=''):
        self.value = value
        self.hid = hid

    def __str__(self):
        return repr(f"HID:{self.hid}, {self.value}") if self.hid else repr(self.value)


class FpdbDatabaseError(FpdbError):
    """Exception class for Fpdb database errors."""
    pass


class FpdbMySQLError(FpdbDatabaseError):
    """Exception class for MySQL database errors in Fpdb."""
    pass


class FpdbMySQLAccessDenied(FpdbDatabaseError):
    """Exception class for MySQL access denied errors in Fpdb."""
    def __init__(self, value='', errmsg=''):
        self.value = value
        self.errmsg = errmsg

    def __str__(self):
        return repr(f"{self.value} {self.errmsg}")


class FpdbMySQLNoDatabase(FpdbDatabaseError):
    """Exception class for MySQL database not found errors in Fpdb."""
    def __init__(self, value='', errmsg=''):
        self.value = value
        self.errmsg = errmsg

    def __str__(self):
        return repr(f"{self.value} {self.errmsg}")


class FpdbPostgresqlAccessDenied(FpdbDatabaseError):
    """Exception class for PostgreSQL access denied errors in Fpdb."""
    def __init__(self, value='', errmsg=''):
        self.value = value
        self.errmsg = errmsg

    def __str__(self):
        return repr(f"{self.value} {self.errmsg}")


class FpdbPostgresqlNoDatabase(FpdbDatabaseError):
    """Exception class for PostgreSQL database not found errors in Fpdb."""
    def __init__(self, value='', errmsg=''):
        self.value = value
        self.errmsg = errmsg

    def __str__(self):
        return repr(f"{self.value} {self.errmsg}")


class FpdbHandError(FpdbError):
    """Exception class for Fpdb poker hand errors."""
    pass


class FpdbHandDuplicate(FpdbHandError):
    """Exception class for duplicate poker hands in Fpdb."""
    pass


class FpdbHandPartial(FpdbParseError):
    """Exception class for partially parsed poker hands in Fpdb."""
    pass


class FpdbHandSkipped(FpdbParseError):
    """Exception class for skipped poker hands in Fpdb."""
    pass


class FpdbEndOfFile(FpdbHandError):
    """Exception class for end-of-file errors in Fpdb."""
    pass
