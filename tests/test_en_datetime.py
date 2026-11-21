"""English hand-history dates parse whatever the process locale is (#864).

``strptime`` reads ``%a %A %b %B %p`` through ``LC_TIME``, and ``QApplication``
sets ``LC_ALL`` from the environment on Unix. Under a French desktop every
Betfair and OnGame hand, the 2010 Full Tilt date format and the AM/PM summary
dates failed to import from the GUI, while the C-locale test suite stayed green.

The guard tests below set ``LC_TIME`` to a non-English locale themselves, so a
regression shows up without a QApplication. They skip when no such locale is
installed; the AST check at the end runs everywhere.
"""

from __future__ import annotations

import ast
import datetime
import locale
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from fpdb_3_legacy.en_datetime import parse_en_datetime

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "regression-test-files"
PACKAGE = ROOT / "fpdb_3_legacy"

NON_ENGLISH_LOCALES = ("fr_FR.UTF-8", "fr_FR.utf8", "fr_FR", "de_DE.UTF-8", "de_DE.utf8", "de_DE")


# --------------------------------------------------------------------------- helper


@pytest.mark.parametrize(
    ("text", "fmt", "expected"),
    [
        ("Sunday, October 18, 20:00:00 GMT 2009", "%A, %B %d, %H:%M:%S GMT %Y", (2009, 10, 18, 20, 0, 0)),
        ("2010/July/21 15:13", "%Y/%B/%d %H:%M", (2010, 7, 21, 15, 13, 0)),
        ("2010/Oct/02 09:05:07", "%Y/%b/%d %H:%M:%S", (2010, 10, 2, 9, 5, 7)),
        ("2014/1/2 12:05:00 AM", "%Y/%m/%d %I:%M:%S %p", (2014, 1, 2, 0, 5, 0)),
        ("2014/1/2 12:05:00 PM", "%Y/%m/%d %I:%M:%S %p", (2014, 1, 2, 12, 5, 0)),
        ("2014/1/2 11:45:57 PM", "%Y/%m/%d %I:%M:%S %p", (2014, 1, 2, 23, 45, 57)),
        ("2014/1/2 1:05:00 am", "%Y/%m/%d %I:%M:%S %p", (2014, 1, 2, 1, 5, 0)),
        ("Wed Jun 30 2010 7:05:00", "%a %b %d %Y %H:%M:%S", (2010, 6, 30, 7, 5, 0)),
        ("05/sept/10", "%d/%b/%y", (2010, 9, 5, 0, 0, 0)),
        ("100%  2010", "100%%  %Y", (2010, 1, 1, 0, 0, 0)),
    ],
)
def test_english_dates_parse(text: str, fmt: str, expected: tuple[int, ...]) -> None:
    assert parse_en_datetime(text, fmt) == datetime.datetime(*expected)  # noqa: DTZ001


@pytest.mark.parametrize(
    ("text", "fmt"),
    [
        ("2010/Juillet/21 15:13", "%Y/%B/%d %H:%M"),
        ("2010/July/21 15:13 extra", "%Y/%B/%d %H:%M"),
        ("2010/02/30 10:00", "%Y/%m/%d %H:%M"),
        ("2014/1/2 13:05:00 PM", "%Y/%m/%d %I:%M:%S %p"),
    ],
)
def test_what_strptime_refuses_is_refused(text: str, fmt: str) -> None:
    with pytest.raises(ValueError, match="does not match format"):
        parse_en_datetime(text, fmt)


@pytest.mark.parametrize("fmt", ["%Y %Z", "%Y/%m/%d %Y", "%Y %"])
def test_a_format_it_cannot_honour_is_rejected(fmt: str) -> None:
    # Unsupported, repeated or stray directives fail loudly rather than
    # silently ignoring part of the date.
    with pytest.raises(ValueError, match="format"):
        parse_en_datetime("2010 x", fmt)


# ------------------------------------------------------------ non-English LC_TIME


@pytest.fixture
def non_english_lc_time() -> Iterator[str]:
    """Run the test with a non-English LC_TIME, as the GUI does under fr_FR."""
    saved = locale.setlocale(locale.LC_TIME)
    for name in NON_ENGLISH_LOCALES:
        try:
            locale.setlocale(locale.LC_TIME, name)
        except locale.Error:
            continue
        break
    else:
        pytest.skip("no French or German locale installed")
    try:
        # Only meaningful when the trap is armed: strptime must have stopped
        # reading English month names (some platforms accept the name but
        # keep English, e.g. a stub locale).
        try:
            datetime.datetime.strptime("2010/July/21", "%Y/%B/%d")  # noqa: DTZ007
        except ValueError:
            yield name
        else:
            pytest.skip(f"{name} still reads English month names")
    finally:
        locale.setlocale(locale.LC_TIME, saved)


@pytest.mark.parametrize(
    ("module", "class_name", "relative", "expected_utc"),
    [
        (
            "BetfairToFpdb",
            "Betfair",
            "cash/Betfair/Flop/PLO-6max-USD-0.05-0.10-200909.All.in.river.splitpot.txt",
            datetime.datetime(2009, 10, 18, 20, 0, 0, tzinfo=datetime.UTC),
        ),
        (
            "FulltiltToFpdb",
            "Fulltilt",
            "cash/FTP/Flop/FT20100721 Flash - $0.02-$0.05 - No Limit Hold'em - dateformat change.txt",
            None,
        ),
        (
            "OnGameToFpdb",
            "OnGame",
            "cash/OnGame/Flop/LHE-9max-USD-0.50-1.00-201008.All-in.with.showdown.txt",
            datetime.datetime(2010, 8, 18, 18, 32, 32, tzinfo=datetime.UTC),
        ),
    ],
)
def test_hand_dates_import_under_a_non_english_locale(
    non_english_lc_time: str,
    module: str,
    class_name: str,
    relative: str,
    expected_utc: datetime.datetime | None,
) -> None:
    import importlib

    from fpdb_3_legacy.Configuration import Config

    parser_class = getattr(importlib.import_module(f"fpdb_3_legacy.{module}"), class_name)
    parser = parser_class(Config(), str(FIXTURES / relative), autostart=True)

    hands = parser.getProcessedHands()
    assert hands, f"no hand imported under {non_english_lc_time}"
    if expected_utc is not None:
        assert hands[0].startTime == expected_utc
    else:
        # 2010/July/21 15:13 ET
        assert hands[0].startTime.date() == datetime.date(2010, 7, 21)


@pytest.mark.usefixtures("non_english_lc_time")
def test_full_tilt_worded_summary_date_under_a_non_english_locale() -> None:
    from tests.test_summary_regression import SUMMARIES, fingerprint_of

    path = SUMMARIES / "FTP" / "NLHE-USD-SnG-6man-201007.Hero.wins.worded.date.format.txt"

    start = fingerprint_of("FTP", path)["tournament"]["startTime"]

    assert start is not None
    assert start.startswith("2010-07-"), start


def _html_summary_dates(site: str, relative: str) -> list[tuple[str | None, str | None]]:
    """Split an HTML summary page as the importer does and date every row."""
    from fpdb_3_legacy.Exceptions import FpdbSummaryNotFound
    from tests.helpers.summary_regression import make_summary, read_text
    from tests.test_summary_regression import SITES, SUMMARIES

    summary_class, sitename, site_id = SITES[site]
    text = read_text(SUMMARIES / site / relative)
    # On an instance: getSplitRe records the page type on whatever it is
    # called on, and the class must not keep it for the next test.
    splitter = summary_class.__new__(summary_class)
    chunks = re.split(splitter.getSplitRe(text), text)
    dates = []
    for chunk in chunks[1:]:
        summary = make_summary(summary_class, chunk, sitename, site_id, "html")
        summary.header = chunks[0]
        summary.import_parameters = {"timezone": "ET"}
        try:
            summary.parseSummary()
        except FpdbSummaryNotFound:
            continue
        dates.append((summary.startTime, summary.endTime))
    return dates


@pytest.mark.parametrize(
    ("site", "relative", "attribute"),
    [
        ("Stars", "PokerStars-MTT-Archive-201007.htm", 1),
        ("Winning", "PlayerTransactionHistory.html", 0),
    ],
)
def test_am_pm_summary_dates_under_a_non_english_locale(
    non_english_lc_time: str,
    site: str,
    relative: str,
    attribute: int,
) -> None:
    dates = [row[attribute] for row in _html_summary_dates(site, relative)]

    assert dates, f"no tournament row parsed under {non_english_lc_time}"
    assert all(date is not None and date.year > 2000 for date in dates), dates  # noqa: PLR2004


# ------------------------------------------------------------- source guard

LOCALE_DIRECTIVE = re.compile(r"%[aAbBp]")


def _locale_sensitive_strptime_calls(path: Path) -> list[int]:
    """Lines where strptime gets a format naming months, days or AM/PM."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    literals.setdefault(target.id, []).append(node.value.value)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "strptime"):
            continue
        fmt = node.args[1] if len(node.args) > 1 else None
        candidates: list[str] = []
        if isinstance(fmt, ast.Constant) and isinstance(fmt.value, str):
            candidates = [fmt.value]
        elif isinstance(fmt, ast.Name):
            candidates = literals.get(fmt.id, [])
        if any(LOCALE_DIRECTIVE.search(candidate) for candidate in candidates):
            hits.append(node.lineno)
    return hits


def test_no_parser_hands_strptime_a_locale_dependent_format() -> None:
    offenders = {
        str(path.relative_to(ROOT)): lines
        for path in sorted(PACKAGE.rglob("*.py"))
        if (lines := _locale_sensitive_strptime_calls(path))
    }

    assert not offenders, (
        "strptime reads %a %A %b %B %p through LC_TIME, which Qt sets from the "
        f"desktop locale; use en_datetime.parse_en_datetime instead: {offenders}"
    )


def test_the_source_guard_sees_both_literal_and_variable_formats(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import datetime\n"
        "fmt = '%Y/%B/%d'\n"
        "datetime.datetime.strptime(a, fmt)\n"
        "datetime.datetime.strptime(a, '%I %p')\n"
        "datetime.datetime.strptime(a, '%Y/%m/%d')\n",
        encoding="utf-8",
    )

    assert _locale_sensitive_strptime_calls(sample) == [3, 4]
