"""Unit tests for WinamaxLiveLogReader real-time log parsing."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader

POOL = "gf.cgmatchmaker.gf_1.t22754010.0"

HAND = f"1786129601014 inf [table] 1 {POOL} hand 22754010-6399-1786129600\n"
SB = f'1786129601015 inf [table] 1 {POOL} action SB login="Player01" amount="0.01"\n'
BB = f'1786129601015 inf [table] 1 {POOL} action BB login="Player-_-11" amount="0.02"\n'
CARDS = f'1786129601016 inf [table] 1 {POOL} cards login="Hero" As,8h,3h,4c\n'
FOLD = f'1786129619117 inf [table] 1 {POOL} action fold login="Hero"\n'


def test_parse_log_line_hand_start() -> None:
    parsed = WinamaxLiveLogReader().parse_log_line(HAND)

    assert parsed is not None
    assert parsed["event"] == "hand_start"
    assert parsed["table_no"] == "1"
    assert parsed["pool"] == POOL
    assert parsed["hand_id"] == "22754010-6399-1786129600"


def test_parse_log_line_action() -> None:
    parsed = WinamaxLiveLogReader().parse_log_line(SB)

    assert parsed is not None
    assert parsed["event"] == "action"
    assert parsed["action_type"] == "SB"
    assert parsed["login"] == "Player01"


def test_parse_log_line_cards_identifies_hero() -> None:
    parsed = WinamaxLiveLogReader().parse_log_line(CARDS)

    assert parsed is not None
    assert parsed["event"] == "cards"
    assert parsed["login"] == "Hero"


def test_ring_is_built_in_action_order_with_hero() -> None:
    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)

    for line in (HAND, SB, BB, CARDS, FOLD):
        reader.process_line(line)

    table = reader.get_table(POOL)
    assert table is not None
    assert table.hero == "Hero"
    assert table.ring == ["Player01", "Player-_-11", "Hero"]
    assert table.hand_id == "22754010-6399-1786129600"
    # The table id links the pool to an imported hand.
    assert table.table_id == "22754010"
    assert callback.called


def test_repeated_action_by_same_player_does_not_duplicate() -> None:
    reader = WinamaxLiveLogReader()
    raise_again = f'1786129619200 inf [table] 1 {POOL} action raise login="Player01" amount="0.06"\n'

    for line in (HAND, SB, BB, raise_again):
        reader.process_line(line)

    assert reader.get_table(POOL).ring == ["Player01", "Player-_-11"]


def test_new_hand_resets_the_ring() -> None:
    """A new hand in a Fast-Fold pool is a new table, so old players must go."""
    reader = WinamaxLiveLogReader()
    for line in (HAND, SB, BB, CARDS):
        reader.process_line(line)

    next_hand = f"1786129700000 inf [table] 1 {POOL} hand 22754010-6400-1786129700\n"
    reader.process_line(next_hand)

    table = reader.get_table(POOL)
    assert table.ring == []
    assert table.hero is None
    assert table.hand_id == "22754010-6400-1786129700"


def test_actions_before_first_hand_boundary_are_ignored() -> None:
    """Tailing can start mid-hand; the ring must anchor on the small blind."""
    reader = WinamaxLiveLogReader()
    reader.process_line(FOLD)

    assert reader.get_table(POOL) is None


def test_two_tables_are_tracked_independently() -> None:
    reader = WinamaxLiveLogReader()
    pool2 = "gf.cgmatchmaker.gf_1.t22754010.1"
    for line in (HAND, SB, BB):
        reader.process_line(line)
    reader.process_line(f"1786129601014 inf [table] 2 {pool2} hand 22754010-6401-1786129601\n")
    reader.process_line(f'1786129601015 inf [table] 2 {pool2} action SB login="Player12" amount="0.01"\n')

    assert reader.get_table(POOL).ring == ["Player01", "Player-_-11"]
    assert reader.get_table(pool2).ring == ["Player12"]


def test_hand_ids_are_mapped_to_the_window_they_were_dealt_on() -> None:
    """Several Escape windows share a pool name; only the log says which is which."""
    reader = WinamaxLiveLogReader()
    pool2 = "gf.cgmatchmaker.gf_1.t22754010.4"
    reader.process_line(HAND)
    reader.process_line(f"1786129700000 inf [table] 5 {pool2} hand 22754010-6500-1786129700\n")

    assert reader.table_no_for_hand("22754010-6399-1786129600") == "1"
    assert reader.table_no_for_hand("22754010-6500-1786129700") == "5"
    assert reader.table_no_for_hand("nope") is None


def test_hand_to_window_map_stays_bounded() -> None:
    reader = WinamaxLiveLogReader()
    reader.HAND_TABLE_HISTORY = 3
    for i in range(10):
        reader.process_line(f"178612960{i} inf [table] 1 {POOL} hand hand-{i}\n")

    assert reader.table_no_for_hand("hand-0") is None
    assert reader.table_no_for_hand("hand-9") == "1"
    assert len(reader._hand_tables) == 3


def test_fpdb_hand_id_matches_what_the_parser_stores() -> None:
    """WinamaxToFpdb joins the first two HandId fields; the log id must follow suit."""
    from fpdb_3_legacy.winamax_live_log_reader import fpdb_hand_id

    assert fpdb_hand_id("22754010-6356-1786128858") == "227540106356"
    # Leading zeros are dropped by the int() the parser applies.
    assert fpdb_hand_id("22754010-0042-1786128858") == "2275401042"
    assert fpdb_hand_id("no-dashes") is None
    assert fpdb_hand_id("single") is None


def test_hands_are_findable_by_the_id_fpdb_stores() -> None:
    """The import path only ever holds the normalised id, never the log's own."""
    reader = WinamaxLiveLogReader()
    reader.process_line(HAND)

    assert reader.table_no_for_hand("22754010-6399-1786129600") == "1"
    assert reader.table_no_for_hand("227540106399") == "1"


def test_a_new_hand_is_reported_immediately_with_an_empty_ring() -> None:
    """The hero has just been moved; whoever is on the overlay was left behind."""
    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)

    for line in (HAND, SB, BB, CARDS, FOLD):
        reader.process_line(line)
    callback.reset_mock()

    reader.process_line(f"1786129700000 inf [table] 1 {POOL} hand 22754010-6400-1786129700\n")

    callback.assert_called_once()
    reported = callback.call_args[0][0]
    assert reported.ring == []
    assert reported.hero is None


def test_priming_learns_pairings_without_reporting_dead_tables(tmp_path) -> None:
    """Hands from just before startup still need a window, but are long finished."""
    log_file = tmp_path / "1786128819.log"
    log_file.write_text("".join([HAND, SB, BB, CARDS, FOLD]), encoding="utf-8")

    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)
    with log_file.open(encoding="utf-8") as handle:
        reader._prime_from_tail(handle)

    # The pairing is what makes the backlog importable straight away...
    assert reader.table_no_for_hand("22754010-6399-1786129600") == "1"
    assert reader.table_no_for_hand("227540106399") == "1"
    # ...but none of it is current, so nothing is pushed to the HUD.
    assert not callback.called


def test_priming_reads_only_the_tail_of_a_long_log(tmp_path) -> None:
    log_file = tmp_path / "big.log"
    filler = f"1786129601000 inf [table] 1 {POOL} action check login=\"noise\"\n"
    log_file.write_text(filler * 5000 + HAND, encoding="utf-8")

    reader = WinamaxLiveLogReader()
    reader.PRIME_BYTES = 2_000
    with log_file.open(encoding="utf-8") as handle:
        reader._prime_from_tail(handle)

    assert reader.table_no_for_hand("22754010-6399-1786129600") == "1"


def test_live_lines_still_notify_after_priming(tmp_path) -> None:
    log_file = tmp_path / "x.log"
    log_file.write_text(HAND, encoding="utf-8")

    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)
    with log_file.open(encoding="utf-8") as handle:
        reader._prime_from_tail(handle)
    reader.process_line(SB)

    assert callback.called


def test_a_fold_by_the_hero_marks_the_table_as_left() -> None:
    """On a Fast-Fold pool a fold is a departure, not just an action."""
    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)

    for line in (HAND, SB, BB, CARDS):
        reader.process_line(line)
    assert reader.get_table(POOL).hero_left is False

    reader.process_line(FOLD)  # Hero folds

    assert reader.get_table(POOL).hero_left is True
    assert callback.call_args[0][0].hero_left is True


def test_a_fold_by_somebody_else_does_not_end_the_table() -> None:
    reader = WinamaxLiveLogReader()
    villain_folds = f'1786129619117 inf [table] 1 {POOL} action fold login="Player01"\n'

    for line in (HAND, SB, BB, CARDS, villain_folds):
        reader.process_line(line)

    assert reader.get_table(POOL).hero_left is False


def test_a_new_hand_clears_the_departure():
    reader = WinamaxLiveLogReader()
    for line in (HAND, SB, BB, CARDS, FOLD):
        reader.process_line(line)
    reader.process_line(f"1786129700000 inf [table] 1 {POOL} hand 22754010-6400-1786129700\n")

    assert reader.get_table(POOL).hero_left is False


def test_the_pot_being_awarded_ends_the_table() -> None:
    """Nobody is at the table between hands, so nothing should describe it."""
    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=callback)
    gain = f'1786128942358 inf [table] 1 {POOL} gain login="Player01" amount="0.15"\n'

    for line in (HAND, SB, BB, CARDS):
        reader.process_line(line)
    assert reader.get_table(POOL).finished is False

    reader.process_line(gain)

    table = reader.get_table(POOL)
    assert table.hand_over is True
    assert table.finished is True
    assert callback.call_args[0][0].finished is True


def test_a_new_hand_reopens_the_table() -> None:
    reader = WinamaxLiveLogReader()
    for line in (HAND, SB, BB, CARDS, FOLD):
        reader.process_line(line)
    assert reader.get_table(POOL).finished is True

    reader.process_line(f"1786129700000 inf [table] 1 {POOL} hand 22754010-6400-1786129700\n")

    assert reader.get_table(POOL).finished is False
