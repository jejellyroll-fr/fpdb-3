"""How long a Fast-Fold table waits for its players is the player's call.

The client log names a player only once they have acted, so a six-handed table
is named over several seconds -- +734ms, +3265ms, +15890ms in measured sessions.
Showing what is known so far means blocks appearing one at a time; waiting for
the ring means they appear together, later. Neither is right for everyone, and
the wait used to be 500ms with no way to say otherwise.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config


def _hud_ui(**attributes) -> Config:
    config = Config.__new__(Config)
    config.ui = SimpleNamespace(**attributes)
    return config


def _wait_ms(**attributes) -> int:
    config = _hud_ui(**attributes)
    # get_hud_ui_parameters reads many attributes; only ours is under test, and
    # the rest fall back to their own defaults through the same getattr guards.
    return Config.get_hud_ui_parameters(config)["fast_fold_seat_wait_ms"]


def test_the_default_is_what_the_hud_has_always_done() -> None:
    assert _wait_ms() == 500


def test_a_longer_wait_is_honoured() -> None:
    """Blocks together, later: the whole point of exposing this."""
    assert _wait_ms(fast_fold_seat_wait_ms="5000") == 5000


def test_zero_shows_the_first_player_at_once() -> None:
    assert _wait_ms(fast_fold_seat_wait_ms="0") == 0


def test_a_negative_wait_is_treated_as_none() -> None:
    assert _wait_ms(fast_fold_seat_wait_ms="-1") == 0


@pytest.mark.parametrize("bad", ["", "soon", "5s", None])
def test_an_unreadable_value_falls_back_to_the_default(bad) -> None:
    """A typo in the config must not stop a table getting a HUD."""
    assert _wait_ms(fast_fold_seat_wait_ms=bad) == 500


def _window_seats(**attributes) -> str:
    return Config.get_hud_ui_parameters(_hud_ui(**attributes))["fast_fold_window_seats"]


def test_the_window_reader_is_on_by_default() -> None:
    """It is what makes the seats arrive at once, where the client publishes them."""
    assert _window_seats() == "auto"


def test_the_window_reader_can_be_turned_off() -> None:
    """Each read is 94-218ms of GUI thread; a client that never answers is pure stutter."""
    assert _window_seats(fast_fold_window_seats="off") == "off"


@pytest.mark.parametrize("written", ["OFF", " Off ", "off"])
def test_the_value_is_read_the_way_a_person_writes_it(written) -> None:
    assert _window_seats(fast_fold_window_seats=written) == "off"


@pytest.mark.parametrize("bad", ["", "no", "false", None, 3])
def test_anything_unrecognised_leaves_the_reader_on(bad) -> None:
    """A typo must not silently cost the fast path where it works."""
    assert _window_seats(fast_fold_window_seats=bad) == "auto"
