"""Losing the window seat reader must not be silent.

Fast-Fold seats are read from the table window; the client log can only name a
player once they have acted, so falling back to it makes the stat blocks appear
one at a time over the first betting round. That fallback is what a user
reports as "the Fast-Fold HUD is slow again".

Both ways of losing the reader were logged at INFO, or not logged at all. The
root logger is pinned to WARNING (loggingFpdb.DIAGNOSTIC_LEVEL_CAP) and
"hud_main" is persisted lower still, so neither line ever reached a user's log:
the HUD degraded to exactly the reported symptom and said nothing about it.
"""

from __future__ import annotations

import logging

import pytest

from fpdb_3_legacy import winamax_ax_seats


@pytest.fixture
def _no_usable_com(monkeypatch):
    """Make building the client fail, on any platform.

    Where comtypes is installed (a Windows dev box) the real GetModule would
    succeed, so it is made to raise; where it is not (Linux/macOS CI) the import
    inside _windows_uia raises on its own and reaches the same branch. Either
    way the test pins the behaviour rather than the machine it runs on.
    """
    try:
        import comtypes.client
    except ImportError:
        return
    monkeypatch.setattr(
        comtypes.client,
        "GetModule",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("COM is not available")),
    )


@pytest.fixture(autouse=True)
def _fresh_client():
    """The client is process-wide state; a test must not leak it into the next."""
    winamax_ax_seats.reset_windows_uia()
    yield
    winamax_ax_seats.reset_windows_uia()


def test_a_reader_that_cannot_be_built_says_so(monkeypatch, caplog, _no_usable_com) -> None:
    """COM refusing to start, or a frozen build that cannot generate the wrapper."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        assert winamax_ax_seats._windows_uia() is None

    assert "Fast-Fold seats will come from the client log" in caplog.text


def test_the_reader_is_not_re_reported_on_every_hand(monkeypatch, caplog, _no_usable_com) -> None:
    """The failure is remembered, so the warning must be once per process."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats._windows_uia()
        winamax_ax_seats._windows_uia()
        winamax_ax_seats._windows_uia()

    assert caplog.text.count("Fast-Fold seats will come from the client log") == 1


def test_a_build_without_comtypes_says_so_at_startup(monkeypatch, caplog) -> None:
    """The packaging failure the PyInstaller hook exists to prevent.

    prewarm() returned silently when is_ax_available() was False, so a build
    that had lost comtypes looked exactly like a healthy one.
    """
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "is_ax_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert "comtypes is not importable" in caplog.text


def test_a_healthy_reader_warns_about_nothing(monkeypatch, caplog) -> None:
    """A working session must stay quiet, or the warning means nothing."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "is_ax_available", lambda: True)
    monkeypatch.setattr(winamax_ax_seats, "_windows_uia", lambda: object())

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert caplog.text == ""


def test_nothing_is_warned_off_windows(monkeypatch, caplog) -> None:
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Darwin")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert caplog.text == ""
