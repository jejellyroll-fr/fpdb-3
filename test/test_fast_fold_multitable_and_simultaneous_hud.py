"""Unit tests for FastFold multi-tabling key uniqueness and simultaneous ring rendering."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fpdb_3_legacy import HUD_main


def test_unique_temp_key_for_multitabling():
    """Verify that _ensure_fast_fold_hud creates distinct keys per window_id/table_no."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main.FAST_FOLD_MAX_SEATS = 6
    hud_main._winamax_site_id = 1
    hud_main._prepared_hands = {}
    hud_main._fast_fold_tables = set()
    hud_main._ff_trace = MagicMock()
    hud_main._create_new_hud = MagicMock()
    hud_main.winamax_pool_games = {}

    def mock_create(hand, key, info, site_id, max_seats, site_name, **kwargs):
        hud_main.hud_dict[key] = MagicMock()

    hud_main._create_new_hud.side_effect = mock_create

    update = SimpleNamespace(hand_id="hand123", table_no="3")

    mock_window = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592342,
        poker_game="holdem",
        description="Escape",
    )
    mock_reader = MagicMock()
    mock_reader.find_table_window.return_value = mock_window
    hud_main.winamax_ax_seats = mock_reader

    # First window
    res = hud_main._ensure_fast_fold_hud(update)
    assert res is not None
    key1 = res[0]
    assert key1 == "Colorado 8 #592342"

    # Second window (same pool / table_name, different window_id)
    mock_window2 = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592343,
        poker_game="holdem",
        description="Escape",
    )
    mock_reader.find_table_window.return_value = mock_window2
    update2 = SimpleNamespace(hand_id="hand124", table_no="4")

    res2 = hud_main._ensure_fast_fold_hud(update2)
    assert res2 is not None
    key2 = res2[0]
    assert key2 == "Colorado 8 #592343"

    # Keys must be distinct so multi-tabling does not collide!
    assert key1 != key2


def test_reuses_existing_hud_when_window_id_is_seen_again():
    """A resolver retry must not create a second HUD for one native window."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    existing = MagicMock()
    existing.table.number = 592342
    existing.is_loading = False
    hud_main.hud_dict = {"Colorado 8": existing}
    hud_main._fast_fold_aliases = {}
    hud_main._ff_trace = MagicMock()

    window = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592342,
        poker_game="holdem",
        description="Escape",
    )
    hud_main.winamax_ax_seats = MagicMock()
    hud_main.winamax_ax_seats.find_table_window.return_value = window

    result = hud_main._ensure_fast_fold_hud(SimpleNamespace(hand_id="hand125", table_no="3"))

    assert result == ("Colorado 8", existing)
    assert hud_main._ff_trace.call_args.args[1] == "hud-reused"


def _hud_main_with_loading_placeholder(placeholder_key):
    """A HudMain whose only HUD for the window is a loading placeholder."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    placeholder = MagicMock()
    placeholder.table.number = 592342
    placeholder.is_loading = True
    hud_main.hud_dict = {placeholder_key: placeholder}
    hud_main._fast_fold_aliases = {}
    hud_main._ff_trace = MagicMock()
    hud_main._fast_fold_tables = set()
    hud_main._prepared_hands = {}
    hud_main.FAST_FOLD_MAX_SEATS = 6
    hud_main._winamax_site_id = 1
    hud_main.winamax_pool_games = {}
    hud_main.idle_kill = MagicMock(side_effect=lambda key: hud_main.hud_dict.pop(key, None))
    hud_main._create_new_hud = MagicMock(
        side_effect=lambda hand, key, *a, **k: hud_main.hud_dict.__setitem__(key, MagicMock(is_loading=False)),
    )
    hud_main.winamax_ax_seats = MagicMock()
    hud_main.winamax_ax_seats.find_table_window.return_value = SimpleNamespace(
        table_name="Colorado 8",
        title="Winamax Colorado 8",
        window_id=592342,
        poker_game="holdem",
        description="Escape",
    )
    return hud_main, placeholder


def test_a_loading_placeholder_is_replaced_not_adopted():
    """The live log must build a real HUD over an import's placeholder.

    A ``loading=True`` HUD is created before its aux windows exist -- it shows
    "Loading HUD..." and nothing else. Adopting it because it holds the right
    native window leaves the log writing seats into a HUD with no windows, so
    the table never displays anything: exactly what was seen on a table whose
    first imported hand arrived before the first log line.
    """
    hud_main, placeholder = _hud_main_with_loading_placeholder("Colorado 8")

    result = hud_main._ensure_fast_fold_hud(SimpleNamespace(hand_id="hand125", table_no="3"))

    assert result is not None
    key, hud = result
    assert key == "Colorado 8 #592342"  # the real, window-qualified HUD
    assert hud is not placeholder
    assert getattr(hud, "is_loading", False) is False
    hud_main.idle_kill.assert_called_once_with("Colorado 8")
    assert "Colorado 8" not in hud_main.hud_dict  # nothing residual
    events = [call.args[1] for call in hud_main._ff_trace.call_args_list]
    assert "loading-replaced" in events


def test_a_placeholder_under_the_window_qualified_key_is_also_replaced():
    """The same placeholder reached by exact key, not by window lookup."""
    hud_main, placeholder = _hud_main_with_loading_placeholder("Colorado 8 #592342")

    result = hud_main._ensure_fast_fold_hud(SimpleNamespace(hand_id="hand125", table_no="3"))

    assert result is not None
    key, hud = result
    assert key == "Colorado 8 #592342"
    assert hud is not placeholder
    hud_main.idle_kill.assert_called_once_with("Colorado 8 #592342")


def test_the_alias_points_at_the_replacement():
    """A later imported hand must find the real HUD, not the dead placeholder."""
    hud_main, _placeholder = _hud_main_with_loading_placeholder("Colorado 8")

    hud_main._ensure_fast_fold_hud(SimpleNamespace(hand_id="hand125", table_no="3"))

    assert hud_main._fast_fold_aliases["Colorado 8"] == "Colorado 8 #592342"
