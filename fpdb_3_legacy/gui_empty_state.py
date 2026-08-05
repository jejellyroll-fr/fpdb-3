"""One explicit "there is nothing to show" popup, shared by every data GUI.

Every stats/graph tab failed the same silent way: when a filter resolved to
nothing (no site, no hero, no limit) the refresh callback logged a warning and
returned, so the user was left with an unchanged - usually empty - tab and no
explanation. Worse, right after recreating the tables the database is empty and
*every* tab did nothing at all. The few tabs that did say something duplicated
an untranslated "No data found for the selected filters." message box that
never named the actual cause.

This module centralises both halves: :func:`show_no_data` displays one popup
that names the reason and says what to do about it, and
:func:`missing_filter_reason` picks that reason from the filter values a tab has
just resolved.
"""

from __future__ import annotations

import contextlib
from enum import Enum
from typing import Any

from PySide6.QtWidgets import QApplication, QMessageBox

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_empty_state")


class NoDataReason(Enum):
    """Why a tab has nothing to display, from the most specific cause down."""

    EMPTY_DATABASE = "empty_database"
    NO_SITE = "no_site"
    NO_HERO = "no_hero"
    NO_LIMIT = "no_limit"
    NO_GAME = "no_game"
    NO_CURRENCY = "no_currency"
    NO_ROWS = "no_rows"


def _message(reason: NoDataReason) -> tuple[str, str]:
    """Return the (headline, what-to-do) pair for ``reason``, translated now.

    Built on each call so the strings go through the gettext catalog installed
    at runtime rather than the one (if any) present at import time.
    """
    messages = {
        NoDataReason.EMPTY_DATABASE: (
            _("Your database contains no hands yet."),
            _(
                "Nothing has been imported into this database — that is normal right "
                "after creating or recreating the tables.\n\n"
                "Import hand histories first (Import > Bulk Import, or start the "
                "auto-import), then refresh this tab.",
            ),
        ),
        NoDataReason.NO_SITE: (
            _("No site is selected in the filters."),
            _("Tick at least one site in the Sites section on the left, then refresh."),
        ),
        NoDataReason.NO_HERO: (
            _("No player matches the selected site and hero."),
            _(
                "Check the hero selected in the Heroes filter and make sure hands for "
                "that player were imported for the selected site.",
            ),
        ),
        NoDataReason.NO_LIMIT: (
            _("No limit is selected in the filters."),
            _("Tick at least one limit (stake) on the left, then refresh."),
        ),
        NoDataReason.NO_GAME: (
            _("No game type is selected in the filters."),
            _("Tick at least one game on the left, then refresh."),
        ),
        NoDataReason.NO_CURRENCY: (
            _("No currency is selected in the filters."),
            _("Tick at least one currency on the left, then refresh."),
        ),
        NoDataReason.NO_ROWS: (
            _("No hand matches the selected filters."),
            _(
                "The database holds hands, but none of them match this selection.\n\n"
                "Widen the filters (dates, limits, games, seats) and refresh.",
            ),
        ),
    }
    return messages[reason]


def missing_filter_reason(
    *,
    sites: Any = None,
    playerids: Any = None,
    limits: Any = None,
    games: Any = None,
    currencies: Any = None,
) -> NoDataReason | None:
    """Return the first filter that resolved to nothing, or ``None`` if all are set.

    Pass only the filters a tab actually uses; ``None`` means "not applicable"
    and is never reported (an empty list/dict is). ``sites`` is the raw filter
    selection and ``playerids`` the ids resolved from it, so a selected site
    whose hero has no imported hands is reported as :attr:`NoDataReason.NO_HERO`
    rather than as a missing site.
    """
    checks = (
        (sites, NoDataReason.NO_SITE),
        (playerids, NoDataReason.NO_HERO),
        (limits, NoDataReason.NO_LIMIT),
        (games, NoDataReason.NO_GAME),
        (currencies, NoDataReason.NO_CURRENCY),
    )
    for value, reason in checks:
        if value is not None and not value:
            return reason
    return None


def database_is_empty(db: Any, tables: tuple[str, ...] = ("Hands",)) -> bool | None:
    """Whether ``tables`` are all empty; ``None`` when the answer is unknown.

    Used to turn a generic "no data" into the far more actionable "you have not
    imported anything yet". Best effort: a missing table or a closed connection
    just means the caller keeps the reason it already had.
    """
    empty = True
    for table in tables:
        try:
            cursor = db.get_cursor()
            cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")  # noqa: S608 - fixed table names
            row = cursor.fetchone()
        except Exception as exc:  # noqa: BLE001 - introspection is advisory only
            log.debug("database_is_empty: could not count %s: %s", table, exc)
            return None
        finally:
            with contextlib.suppress(Exception):
                db.rollback()
        if row:
            empty = False
    return empty


def show_no_data(
    parent: Any,
    reason: NoDataReason = NoDataReason.NO_ROWS,
    *,
    context: str = "",
    db: Any = None,
    tables: tuple[str, ...] = ("Hands",),
) -> NoDataReason:
    """Tell the user, explicitly, why this tab has nothing to show.

    ``db`` (optional) upgrades a data-shaped reason to
    :attr:`NoDataReason.EMPTY_DATABASE` when the database holds no rows at all,
    which is the common case after a fresh install or a table recreate.
    ``context`` only labels the log line. Returns the reason finally reported,
    and stays silent (log only) when there is no running QApplication, so
    headless callers and tests can use it.
    """
    if db is not None and reason in (NoDataReason.NO_ROWS, NoDataReason.NO_HERO) and database_is_empty(db, tables):
        reason = NoDataReason.EMPTY_DATABASE

    headline, hint = _message(reason)
    log.warning("%s: no data (%s) - %s", context or "GUI", reason.value, headline)

    if QApplication.instance() is None:  # headless (tests, CLI import)
        return reason

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setWindowTitle(_("No data to display"))
    msg.setText(headline)
    msg.setInformativeText(hint)
    msg.exec()
    return reason
