"""A GUI read must not leave a transaction open behind it.

Every filter query is a read, but a read still opens a transaction, and one
that is never ended keeps its connection in ``idle in transaction`` for the
life of the tab. Measured on the reporter's database before the fix, three
tabs left three such backends holding ACCESS SHARE on Gametypes, Hands,
HandsPlayers, Players and Sites (#271).

Two consequences, and the second is how this was found: autovacuum cannot
reclaim dead rows on the two tables that actually grow while fpdb is running,
and anything wanting a stronger lock queues behind the read -- which is what
made a schema migration hang the GUI in #249.

The fixes are at the two places that see every read: the filter buttons every
tab registers its refresh with, and the pooled connection every DbWorker
borrows. Both are pinned here, along with the order inside ``make_filter``,
where the rollback used to sit one call too early.
"""

from __future__ import annotations

import ast
import pathlib
import queue
from typing import Any

import pytest

import fpdb_3_legacy
from fpdb_3_legacy import Filters as filters_module
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Filters import Filters

FILTERS_SOURCE = pathlib.Path(fpdb_3_legacy.__file__).parent / "Filters.py"


def filters_tree() -> ast.Module:
    return ast.parse(FILTERS_SOURCE.read_text(encoding="utf-8"))


def function_named(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"Filters.{name} no longer exists")
    raise AssertionError  # unreachable, keeps the type checker happy


# ---------------------------------------------------------------------------
# The filter buttons: the one place that sees every tab's refresh
# ---------------------------------------------------------------------------


class RecordingFilters:
    """The wrapper under test, on a host reduced to what it touches."""

    _releasing_read_locks = Filters._releasing_read_locks

    def __init__(self) -> None:
        self.rollbacks = 0

    def end_read_transaction(self) -> None:
        self.rollbacks += 1


def test_a_refresh_ends_its_read_transaction() -> None:
    host = RecordingFilters()
    calls: list[tuple[Any, ...]] = []

    wrapped = host._releasing_read_locks(lambda *args: calls.append(args))
    wrapped(None)

    assert calls == [(None,)]
    assert host.rollbacks == 1


def test_a_refresh_that_raises_still_ends_its_read_transaction() -> None:
    """The failed refresh is the one that leaves a transaction behind.

    On PostgreSQL it is also left *aborted*, which makes every later query on
    that connection fail until something ends it.
    """
    host = RecordingFilters()

    def explode() -> None:
        msg = "the query blew up"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError):
        host._releasing_read_locks(explode)()

    assert host.rollbacks == 1


def test_the_callback_result_is_passed_through() -> None:
    host = RecordingFilters()

    assert host._releasing_read_locks(lambda: "graph")() == "graph"


@pytest.mark.parametrize("register", ["registerButton1Callback", "registerButton2Callback"])
def test_both_filter_buttons_connect_through_the_wrapper(register: str) -> None:
    """Connecting the raw callback again would reopen the leak for every tab."""
    node = function_named(filters_tree(), register)

    connects = [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "connect"
    ]

    assert connects, f"{register} no longer connects anything"
    for connect in connects:
        argument = connect.args[0]
        assert isinstance(argument, ast.Call), f"{register} connects a bare callback"
        assert isinstance(argument.func, ast.Attribute)
        assert argument.func.attr == "_releasing_read_locks"


def test_the_sidebar_ends_its_transaction_after_the_last_query() -> None:
    """``set_default_hero`` runs six more queries, so it must come first.

    The rollback was there all along -- on the line above ``set_default_hero``,
    which is to say before the queries that actually left the transaction open.
    """
    body = function_named(filters_tree(), "make_filter").body
    order = [
        index
        for index, statement in enumerate(body)
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr in {"set_default_hero", "end_read_transaction"}
    ]

    assert len(order) == 2
    first, second = (body[index].value.func.attr for index in order)  # type: ignore[union-attr]
    assert (first, second) == ("set_default_hero", "end_read_transaction")


def test_changing_hero_ends_its_transaction_too() -> None:
    """It reruns all six update_*_for_hero queries on every change."""
    node = function_named(filters_tree(), "update_filters_for_hero")

    assert [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "end_read_transaction"
    ]


# ---------------------------------------------------------------------------
# The worker pool: shared by every tab, and kept for the life of the process
# ---------------------------------------------------------------------------


class FakeConnection:
    def __init__(self, *, rollback_fails: bool = False) -> None:
        self.rollback_fails = rollback_fails
        self.rollbacks = 0
        self.closed = False

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_fails:
            msg = "connection is gone"
            raise RuntimeError(msg)

    def close(self) -> None:
        self.closed = True


class PoolHost:
    """``Database``'s return path, with a pool of its own."""

    _return_worker_connection = Database._return_worker_connection

    def __init__(self) -> None:
        self._worker_conn_pool: queue.Queue[Any] = queue.Queue()

    def pooled(self) -> list[Any]:
        return list(self._worker_conn_pool.queue)


def test_a_worker_connection_is_rolled_back_before_it_is_pooled() -> None:
    """Otherwise it idles in a transaction until fpdb exits, holding locks."""
    host = PoolHost()
    conn = FakeConnection()

    host._return_worker_connection(conn)

    assert conn.rollbacks == 1
    assert host.pooled() == [conn]


def test_a_connection_that_cannot_roll_back_is_dropped_not_pooled() -> None:
    """Pooling it hands the next borrower a connection that fails every query."""
    host = PoolHost()
    conn = FakeConnection(rollback_fails=True)

    host._return_worker_connection(conn)

    assert conn.closed is True
    assert host.pooled() == []


def test_no_connection_is_not_an_error() -> None:
    """SQLite ``:memory:`` yields None and falls back to the shared connection."""
    host = PoolHost()

    host._return_worker_connection(None)

    assert host.pooled() == []


@pytest.mark.parametrize(
    ("callback", "expected"),
    [
        (lambda: None, 0),
        (lambda _checked: None, 1),
        (lambda _checked=None: None, 1),
    ],
)
def test_the_wrapper_offers_only_the_arguments_the_callback_takes(callback, expected: int) -> None:
    """Qt sends a clicked slot the checked flag only if it has room for it.

    PySide works that out by inspecting the callable, which a wrapper hides.
    Both ``exportGraph`` methods and ``GuiTourneyPlayerStats.refreshStats``
    take no argument, so forwarding blindly makes their button raise
    TypeError instead of running.
    """
    assert filters_module._accepted_positional_count(callback) == expected


def test_a_callback_taking_nothing_survives_a_clicked_signal() -> None:
    host = RecordingFilters()
    ran: list[bool] = []

    wrapped = host._releasing_read_locks(lambda: ran.append(True))
    wrapped(False)  # what QPushButton.clicked delivers

    assert ran == [True]
    assert host.rollbacks == 1


def test_a_callback_taking_the_flag_still_receives_it() -> None:
    host = RecordingFilters()
    seen: list[Any] = []

    host._releasing_read_locks(lambda checked: seen.append(checked))(True)

    assert seen == [True]
