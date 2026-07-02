"""Unit tests for fpdb_3_legacy.Exceptions."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fpdb_3_legacy import Exceptions


class TestFpdbError:
    def test_value_stored(self) -> None:
        e = Exceptions.FpdbError("boom")
        assert e.value == "boom"

    def test_str_is_repr_of_value(self) -> None:
        e = Exceptions.FpdbError("boom")
        assert str(e) == repr("boom")

    def test_str_with_non_string_value(self) -> None:
        e = Exceptions.FpdbError(42)
        assert str(e) == repr(42)

    def test_is_exception(self) -> None:
        assert isinstance(Exceptions.FpdbError("x"), Exception)

    def test_raisable(self) -> None:
        with pytest.raises(Exceptions.FpdbError):
            raise Exceptions.FpdbError("x")


class TestFpdbParseError:
    def test_defaults(self) -> None:
        e = Exceptions.FpdbParseError()
        assert e.value == ""
        assert e.hid == ""

    def test_value_only(self) -> None:
        e = Exceptions.FpdbParseError("oops")
        assert e.value == "oops"
        assert e.hid == ""
        assert str(e) == repr("oops")

    def test_with_hid(self) -> None:
        e = Exceptions.FpdbParseError("oops", hid="123")
        assert e.hid == "123"
        assert str(e) == repr("HID:123, oops")

    def test_is_fpdberror(self) -> None:
        assert isinstance(Exceptions.FpdbParseError(), Exceptions.FpdbError)


class TestDatabaseErrors:
    def test_fpdb_database_error_inherits(self) -> None:
        assert issubclass(Exceptions.FpdbDatabaseError, Exceptions.FpdbError)
        e = Exceptions.FpdbDatabaseError("db")
        assert e.value == "db"
        assert str(e) == repr("db")

    def test_fpdb_mysql_error_inherits(self) -> None:
        assert issubclass(Exceptions.FpdbMySQLError, Exceptions.FpdbDatabaseError)


@pytest.mark.parametrize(
    "cls",
    [
        Exceptions.FpdbMySQLAccessDeniedError,
        Exceptions.FpdbMySQLNoDatabaseError,
        Exceptions.FpdbPostgresqlAccessDeniedError,
        Exceptions.FpdbPostgresqlNoDatabaseError,
    ],
)
class TestValueErrmsgErrors:
    def test_defaults(self, cls) -> None:
        e = cls()
        assert e.value == ""
        assert e.errmsg == ""
        assert str(e) == repr(" ")

    def test_with_values(self, cls) -> None:
        e = cls("val", "msg")
        assert e.value == "val"
        assert e.errmsg == "msg"
        assert str(e) == repr("val msg")

    def test_inherits_database_error(self, cls) -> None:
        assert issubclass(cls, Exceptions.FpdbDatabaseError)


class TestHandErrors:
    def test_hand_error(self) -> None:
        assert issubclass(Exceptions.FpdbHandError, Exceptions.FpdbError)
        e = Exceptions.FpdbHandError("h")
        assert e.value == "h"

    def test_hand_duplicate(self) -> None:
        assert issubclass(Exceptions.FpdbHandDuplicateError, Exceptions.FpdbHandError)

    def test_hand_partial_is_parse_error(self) -> None:
        assert issubclass(Exceptions.FpdbHandPartialError, Exceptions.FpdbParseError)
        e = Exceptions.FpdbHandPartialError("p", hid="7")
        assert str(e) == repr("HID:7, p")

    def test_hand_skipped_is_parse_error(self) -> None:
        assert issubclass(Exceptions.FpdbHandSkippedError, Exceptions.FpdbParseError)
        e = Exceptions.FpdbHandSkippedError("s")
        assert e.hid == ""

    def test_end_of_file_is_hand_error(self) -> None:
        assert issubclass(Exceptions.FpdbEndOfFileError, Exceptions.FpdbHandError)


class TestAliases:
    @pytest.mark.parametrize(
        ("alias", "target"),
        [
            (Exceptions.FpdbMySQLAccessDenied, Exceptions.FpdbMySQLAccessDeniedError),
            (Exceptions.FpdbMySQLNoDatabase, Exceptions.FpdbMySQLNoDatabaseError),
            (Exceptions.FpdbPostgresqlAccessDenied, Exceptions.FpdbPostgresqlAccessDeniedError),
            (Exceptions.FpdbPostgresqlNoDatabase, Exceptions.FpdbPostgresqlNoDatabaseError),
            (Exceptions.FpdbHandDuplicate, Exceptions.FpdbHandDuplicateError),
            (Exceptions.FpdbHandPartial, Exceptions.FpdbHandPartialError),
            (Exceptions.FpdbHandSkipped, Exceptions.FpdbHandSkippedError),
            (Exceptions.FpdbEndOfFile, Exceptions.FpdbEndOfFileError),
        ],
    )
    def test_alias_identity(self, alias, target) -> None:
        assert alias is target
