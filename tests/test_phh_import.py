"""PHH (Poker Hand History) import (#381).

The fixtures under ``tests/fixtures/phh`` were played through PokerKit -- the reference
implementation of PHH -- which supplied their ``winnings`` / ``finishing_stacks`` and the
net result of every player (``pokerkit_results.json``). fpdb's own result for each player,
read back from the database, is checked against that independent one.
"""

from __future__ import annotations

import datetime
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy import Card
from fpdb_3_legacy.phh_import import (
    GAMES,
    MALFORMED,
    PARTIAL,
    PHH_SITE_ID,
    PHH_SITE_NAME,
    UNSUPPORTED,
    PHHDocument,
    PHHImportError,
    build_hand,
    hand_number,
    import_file,
    is_phh_path,
    iter_documents,
    mapping_for,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phh"
EXPECTED = json.loads((FIXTURES / "pokerkit_results.json").read_text(encoding="utf-8"))
FIXTURE_GAMES = {
    "nl_holdem_dwan_ivey": ("holdem", "nl"),
    "nl_holdem_heads_up": ("holdem", "nl"),
    "nl_holdem_side_pots": ("holdem", "nl"),
    "fl_holdem": ("holdem", "fl"),
    "ns_short_deck": ("6_holdem", "nl"),
    "pl_omaha": ("omahahi", "pl"),
    "fl_omaha_hilo_split": ("omahahilo", "fl"),
    "stud_hi": ("studhi", "fl"),
    "stud_hilo_split": ("studhilo", "fl"),
    "razz": ("razz", "fl"),
    "single_draw": ("27_1draw", "nl"),
    "triple_draw_yockey_arieh": ("27_3draw", "fl"),
    "badugi": ("badugi", "fl"),
    "nl_holdem_heads_up_bb_ante": ("holdem", "nl"),
    "triple_draw_all_in_runout": ("27_3draw", "fl"),
}

NT_HAND = """
variant = "NT"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [100, 100, 100]
actions = [
  "d dh p1 ????",
  "d dh p2 ????",
  "d dh p3 ????",
  "p3 cbr 6",
  "p1 f",
  "p2 f",
]
"""


def document(text: str, label: str = "hand") -> PHHDocument:
    import tomllib

    return PHHDocument("test.phh", label, 1, tomllib.loads(text))


def refusal(text: str) -> PHHImportError:
    with pytest.raises(PHHImportError) as caught:
        build_hand(document(text))
    return caught.value


def actions_of(hand: Any) -> list[tuple]:
    return [(street, *action[:3]) for street in hand.allStreets for action in hand.actions.get(street, [])]


# -- the mapping ------------------------------------------------------------------------


def test_every_phh_variant_is_mapped_to_an_fpdb_game_of_its_family() -> None:
    assert set(GAMES) == {"FT", "NT", "NS", "PO", "FO/8", "F7S", "F7S/8", "FR", "N2L1D", "F2L3D", "FB"}
    for mapping in GAMES.values():
        assert mapping.lossless
        assert Card.games[mapping.category][0] == mapping.base
        assert mapping.limit_type in ("nl", "pl", "fl")


@pytest.mark.parametrize(
    ("variant", "base"),
    [("NT", "hold"), ("FO/8", "hold"), ("F7S", "stud"), ("FR", "stud"), ("N2L1D", "draw"), ("FB", "draw")],
)
def test_hold_stud_and_draw_families_map_deterministically(variant: str, base: str) -> None:
    assert mapping_for(variant).base == base
    assert mapping_for(variant) is mapping_for(variant)


@pytest.mark.parametrize("variant", ["PO5", "OFC", "Drawmaha", "NO", "nt", ""])
def test_variants_without_an_fpdb_mapping_are_refused(variant: str) -> None:
    with pytest.raises(PHHImportError) as caught:
        mapping_for(variant)
    assert caught.value.kind == UNSUPPORTED
    assert repr(variant) in str(caught.value)


# -- every fixture, against PokerKit ------------------------------------------------------


@pytest.fixture
def imported(importer, fresh_db, tmp_path):
    for fixture in sorted(FIXTURES.glob("*.phh")):
        shutil.copy(fixture, tmp_path / fixture.name)
        assert importer.addImportFile(str(tmp_path / fixture.name))
    totals = importer.runImport()
    connection = sqlite3.connect(fresh_db.database)
    connection.row_factory = sqlite3.Row
    yield importer, totals, connection
    connection.close()


def test_every_fixture_is_imported(imported) -> None:
    importer, totals, _connection = imported
    stored, duplicates, partial, skipped, errors, _seconds = totals
    assert (stored, duplicates, partial, skipped, errors) == (len(EXPECTED), 0, 0, 0, 0)
    summary = importer.phh_summary()
    assert summary is not None
    assert (summary.discovered, summary.imported) == (len(EXPECTED), len(EXPECTED))


def test_each_player_result_matches_pokerkit(imported) -> None:
    _importer, _totals, connection = imported
    files = {row["id"]: row["file"] for row in connection.execute("SELECT * FROM Files")}
    file_of_hand = {row["id"]: files[row["fileId"]] for row in connection.execute("SELECT * FROM Hands")}
    results: dict[str, list[tuple[int, int]]] = {}
    for row in connection.execute("SELECT * FROM HandsPlayers"):
        results.setdefault(file_of_hand[row["handId"]], []).append((row["seatNo"], row["totalProfit"]))

    for name, expected in EXPECTED.items():
        cents = [round(payoff * 100) for payoff in expected["payoffs"]]
        assert [profit for _seat, profit in sorted(results[name])] == cents, name


def test_each_fixture_is_stored_as_its_fpdb_game(imported) -> None:
    _importer, _totals, connection = imported
    files = {row["id"]: row["file"] for row in connection.execute("SELECT * FROM Files")}
    games = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM Gametypes")}
    for hand in connection.execute("SELECT * FROM Hands"):
        game = games[hand["gametypeId"]]
        assert (game["category"], game["limitType"]) == FIXTURE_GAMES[files[hand["fileId"]]]
        assert game["siteId"] == PHH_SITE_ID


def test_hands_belong_to_the_phh_data_source_not_a_room(imported) -> None:
    _importer, _totals, connection = imported
    assert [dict(row) for row in connection.execute("SELECT * FROM Sites WHERE id = 150")] == [
        {"id": PHH_SITE_ID, "name": PHH_SITE_NAME, "code": "PH"}
    ]
    assert {row["site"] for row in connection.execute("SELECT * FROM Files")} == {PHH_SITE_NAME}


def test_importing_again_finds_only_duplicates(imported, tmp_path) -> None:
    importer, _totals, _connection = imported
    importer.clearFileList()
    for fixture in sorted(FIXTURES.glob("*.phh")):
        assert importer.addImportFile(str(tmp_path / fixture.name))

    stored, duplicates, *_rest = importer.runImport()

    assert (stored, duplicates) == (0, len(EXPECTED))


# -- actions, amounts and structure --------------------------------------------------------


def test_action_order_and_amounts_are_preserved() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "nl_holdem_dwan_ivey.phh")))

    assert actions_of(hand) == [
        ("BLINDSANTES", "Phil Ivey", "ante", 500),
        ("BLINDSANTES", "Patrik Antonius", "ante", 500),
        ("BLINDSANTES", "Tom Dwan", "ante", 500),
        ("BLINDSANTES", "Phil Ivey", "small blind", 1000),
        ("BLINDSANTES", "Patrik Antonius", "big blind", 2000),
        ("PREFLOP", "Tom Dwan", "raises", 5000),
        ("PREFLOP", "Phil Ivey", "raises", 16000),
        ("PREFLOP", "Patrik Antonius", "folds"),
        ("PREFLOP", "Tom Dwan", "calls", 16000),
        ("FLOP", "Phil Ivey", "bets", 35000),
        ("FLOP", "Tom Dwan", "calls", 35000),
        ("TURN", "Phil Ivey", "bets", 90000),
        ("TURN", "Tom Dwan", "raises", 142600),
        ("TURN", "Phil Ivey", "raises", 834500),
        # Dwan calls all in for what he has left (553,500 - 58,500 - 232,600), not the whole raise.
        ("TURN", "Tom Dwan", "calls", 262400),
    ]
    assert hand.board == {**hand.board, "FLOP": ["Jc", "3d", "5c"], "TURN": ["4h"], "RIVER": ["Jh"]}
    assert hand.tablename == "Million Dollar Cash Game"
    assert hand.gametype["currency"] == "USD"


def test_heads_up_the_first_player_posts_the_big_blind() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "nl_holdem_heads_up.phh")))

    assert actions_of(hand)[:2] == [("BLINDSANTES", "Alice", "big blind", 2), ("BLINDSANTES", "Bob", "small blind", 1)]
    assert hand.buttonpos == 2, "the last player has the button"
    assert hand.hero == "Alice"
    # 20:00 in New York on 1 September is midnight UTC on the 2nd.
    assert str(hand.startTime) == "2026-09-02 00:00:00"


def test_a_straddle_and_a_button_blind_are_posted_as_such() -> None:
    # The straddler, p3, acts last preflop: play starts after the last blind posted.
    straddle = build_hand(
        document(
            NT_HAND.replace("[1, 2, 0]", "[1, 2, 4]").replace(
                '"p3 cbr 6",\n  "p1 f",\n  "p2 f",', '"p1 cbr 12",\n  "p2 f",\n  "p3 f",'
            )
        )
    )
    assert actions_of(straddle)[2] == ("BLINDSANTES", "p3", "straddle", 4)

    button = build_hand(
        document(
            NT_HAND.replace("[0, 0, 0]", "[1, 1, 1]")
            .replace("[1, 2, 0]", "[0, 0, 2]")
            .replace('"p3 cbr 6",\n  "p1 f",\n  "p2 f",', '"p1 cbr 6",\n  "p2 f",\n  "p3 f",')
        )
    )
    assert ("BLINDSANTES", "p3", "button blind", 2) in actions_of(button)


def test_stud_brings_in_completes_and_deals_by_street() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "stud_hi.phh")))

    assert actions_of(hand)[3:7] == [
        ("THIRD", "p1", "bringin", 2),
        ("THIRD", "p2", "completes", 3),
        ("THIRD", "p3", "calls", 5),
        ("THIRD", "p1", "folds"),
    ]
    assert hand.holecards["THIRD"]["p2"] == (["9c"], ["Ah", "Ad"])
    assert hand.holecards["FOURTH"]["p3"] == (["Ks"], ["0x", "0x", "Kd"])


def test_draws_record_discards_stands_pat_and_the_cards_drawn() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "triple_draw_yockey_arieh.phh")))

    assert ("DRAWONE", "Bryce Yockey", "stands pat") in actions_of(hand)
    assert ("DRAWONE", "Josh Arieh", "discards", 2) in actions_of(hand)
    assert hand.discards["DRAWONE"]["Josh Arieh"] == {"As Qs"}
    # Kept cards closed, the two drawn open.
    assert hand.holecards["DRAWONE"]["Josh Arieh"] == [["2h", "Qh"], ["6s", "5c", "3c"]]
    assert [street for street in hand.allStreets if hand.actions.get(street)][-1] == "DRAWTHREE"


def test_a_split_pot_is_shared() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "fl_omaha_hilo_split.phh")))
    assert dict(hand.collectees) == {"p1": 14, "p2": 14}


def test_the_last_player_standing_takes_the_pot_when_no_result_is_given() -> None:
    hand = build_hand(document(NT_HAND))
    hand.totalPot()
    # The blinds and the 2 of the raise that was called; the other 4 go back uncalled.
    assert dict(hand.collectees) == {"p3": 5}
    assert hand.pot.returned == {"p3": 4}


def test_the_hand_number_is_its_content() -> None:
    first = document(NT_HAND)
    assert hand_number(first.data) == hand_number(document(NT_HAND, label="elsewhere").data)
    assert hand_number(first.data) != hand_number(document(NT_HAND.replace("cbr 6", "cbr 8")).data)
    assert 0 < hand_number(first.data) < 2**62


# -- refusals ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (('"p2 f",', '"p2 f",\n  "p2 cc",'), "acts after folding"),
        (('"p3 cbr 6",', '"p3 cbr 2",'), "does not exceed"),
        (('"p3 cbr 6",', '"p3 cbr 600",'), "behind"),
        (('"p3 cbr 6",', '"p9 cbr 6",'), "p9 is not one of the 3 players"),
        (('"p3 cbr 6",', '"p3 raise 6",'), "not a PHH action"),
        (('"p3 cbr 6",', '"p3 cc 6",'), "takes no amount"),
        (
            ('"p3 cbr 6",\n  "p1 f",\n  "p2 f",', '"p3 cc",\n  "p1 cc",\n  "p2 cc",\n  "d db AsKs",'),
            "the flop deals 3 cards",
        ),
        (('"p3 cbr 6",', '"p3 pb",'), "bring-in"),
        (('"p3 cbr 6",', '"p3 sd",'), "only draw games"),
        (('"d dh p1 ????",', '"d dh p1 Zz",'), "is not a list of cards"),
        (("starting_stacks = [100, 100, 100]", "starting_stacks = [100, 100]"), "one value per player"),
    ],
)
def test_malformed_hands_are_refused_with_their_reason(change: tuple[str, str], reason: str) -> None:
    error = refusal(NT_HAND.replace(*change))
    assert error.kind == MALFORMED
    assert reason in str(error)
    assert "test.phh:1" in str(error), "the file and line are named"


def test_more_than_three_boards_is_a_run_it_twice_and_unsupported() -> None:
    text = NT_HAND.replace(
        '"p1 f",\n  "p2 f",',
        '"p1 cc",\n  "p2 cc",\n  "d db AsKsQs",\n  "p1 cc",\n  "p2 cc",\n  "p3 cc",\n  "d db 2c",\n'
        '  "p1 cc",\n  "p2 cc",\n  "p3 cc",\n  "d db 3c",\n  "p1 cc",\n  "p2 cc",\n  "p3 cc",\n  "d db 4c",',
    )
    assert refusal(text).kind == UNSUPPORTED


CHECKED_DOWN = (
    '"p1 cc",\n  "p2 f",\n  "d db AsKsQs",\n  "p1 cc",\n  "p3 cc",\n  "d db 2c",\n  "p1 cc",\n  "p3 cc",\n'
    '  "d db 3c",\n  "p1 cc",\n  "p3 cc",'
)


def test_a_showdown_without_winnings_is_not_guessed() -> None:
    error = refusal(NT_HAND.replace('"p1 f",\n  "p2 f",', CHECKED_DOWN))
    assert error.kind == UNSUPPORTED
    assert "without guessing" in str(error)


@pytest.mark.parametrize(
    "actions",
    [
        "[]",  # nothing dealt yet
        '["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cbr 6"]',  # stops mid-street
        '["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cc", "p1 cc", "p2 cc", "d db AsKsQs"]',  # no river
    ],
)
def test_a_history_that_stops_before_the_end_is_partial(actions: str) -> None:
    start = NT_HAND.index("actions = [")
    error = refusal(NT_HAND[:start] + f"actions = {actions}\n")
    assert error.kind == PARTIAL
    assert "partial" in str(error)


def test_a_missing_required_field_is_named() -> None:
    error = refusal(NT_HAND.replace("min_bet = 2\n", "").replace("antes = [0, 0, 0]\n", ""))
    assert "missing required field 'antes'" in str(error)


# -- files ------------------------------------------------------------------------------


def test_a_phhs_file_is_read_hand_by_hand_and_its_failures_counted(importer, fresh_db, tmp_path) -> None:
    parts = [
        f"[{index}]\n{(FIXTURES / name).read_text(encoding='utf-8')}"
        for index, name in enumerate(("razz.phh", "badugi.phh", "pl_omaha.phh"), start=1)
    ]
    parts.append(
        '[4]\nvariant = "PO5"\nantes = [0, 0]\nblinds_or_straddles = [1, 2]\nmin_bet = 2\n'
        "starting_stacks = [10, 10]\nactions = []\n"
    )
    acting_after_folding = NT_HAND.replace('"p2 f",', '"p2 f",\n  "p2 cc",')
    parts.append("[5]\n" + acting_after_folding)
    parts.append('[6]\nvariant = "NT\nthis is not TOML\n')
    parts.append(f"[1-again]\n{(FIXTURES / 'razz.phh').read_text(encoding='utf-8')}")
    parts.append("[7]\n" + NT_HAND[: NT_HAND.index("actions = [")] + "actions = []\n")  # stops before any deal
    dataset = tmp_path / "dataset.phhs"
    dataset.write_text("# a small dataset\n\n" + "\n".join(parts), encoding="utf-8")

    labels = [item.label if isinstance(item, PHHDocument) else item.kind for item in iter_documents(dataset)]
    assert labels == ["1", "2", "3", "4", "5", MALFORMED, "1-again", "7"]

    assert importer.addImportFile(str(dataset))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (3, 1, 1, 1, 2)
    summary = importer.phh_summary()
    assert summary is not None
    assert (summary.discovered, summary.partial, summary.unsupported, summary.malformed) == (8, 1, 1, 2)
    assert any("dataset.phhs" in error and "PO5" in error for error in summary.errors)
    assert any("not valid TOML" in error for error in summary.errors)


def test_content_before_the_first_table_is_reported_once(tmp_path) -> None:
    dataset = tmp_path / "loose.phhs"
    dataset.write_text('variant = "NT"\nantes = []\n[1]\n' + NT_HAND, encoding="utf-8")

    items = list(iter_documents(dataset))

    assert isinstance(items[0], PHHImportError)
    assert "before the first" in str(items[0])
    assert [item.label for item in items[1:]] == ["1"]


def test_phh_files_are_recognised_by_extension_only() -> None:
    assert is_phh_path("hands.phh")
    assert is_phh_path("/data/WSOP.PHHS")
    assert not is_phh_path("hands.txt")
    assert not is_phh_path("phh")


# -- what the user is told --------------------------------------------------------------


def _counts() -> Any:
    from fpdb_3_legacy.phh_import import PHHImportResult

    return PHHImportResult(
        discovered=7, imported=3, duplicates=1, unsupported=1, malformed=2, seconds=0.5, errors=["x.phhs:4: PO5"]
    )


def test_the_bulk_import_message_lists_the_phh_counts() -> None:
    from fpdb_3_legacy.GuiBulkImport import GuiBulkImport

    text = GuiBulkImport._phh_lines(_counts())

    for line in ("PHH hands found: 7", "Imported: 3", "Duplicates: 1", "Unsupported variants: 1", "Malformed: 2"):
        assert line in text


def test_the_command_line_prints_the_phh_counts_and_why(capsys) -> None:
    from fpdb_3_legacy.GuiBulkImport import _print_phh_summary

    _print_phh_summary(_counts(), quiet=False)
    _print_phh_summary(None, quiet=False)

    out = capsys.readouterr().out
    assert out.splitlines() == [
        "PHH: 7 hands found, 3 imported, 1 duplicates, 0 partial, 1 unsupported, 2 malformed, in 0.5s",
        "  x.phhs:4: PO5",
    ]


# -- review of the first version -------------------------------------------------------


def test_heads_up_antes_are_reversed_like_the_blinds_and_unnamed_players_get_pn() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "nl_holdem_heads_up_bb_ante.phh")))

    assert actions_of(hand)[:3] == [
        ("BLINDSANTES", "p1", "ante", 3),
        ("BLINDSANTES", "p1", "big blind", 2),
        ("BLINDSANTES", "p2", "small blind", 1),
    ]
    hand.totalPot()
    # The ante is dead money: only the 14 of the raise nobody matched goes back.
    assert hand.pot.returned == {"p1": 14}


def test_a_partly_named_table_keeps_its_names() -> None:
    hand = build_hand(document(NT_HAND + 'players = ["", "Bob", ""]\n'))
    assert [player[1] for player in hand.players] == ["p1", "Bob", "p3"]


def test_draws_with_no_betting_between_them_still_advance_the_street() -> None:
    hand = build_hand(next(iter_documents(FIXTURES / "triple_draw_all_in_runout.phh")))

    assert [action[:3] for action in actions_of(hand) if action[0].startswith("DRAW")] == [
        ("DRAWONE", "p1", "stands pat"),
        ("DRAWONE", "p2", "discards"),
        ("DRAWTWO", "p1", "stands pat"),
        ("DRAWTWO", "p2", "discards"),
        ("DRAWTHREE", "p1", "stands pat"),
        ("DRAWTHREE", "p2", "discards"),
    ]


def test_a_stud_completion_is_stored_as_a_completion(importer, fresh_db, tmp_path) -> None:
    shutil.copy(FIXTURES / "stud_hi.phh", tmp_path / "stud_hi.phh")
    assert importer.addImportFile(str(tmp_path / "stud_hi.phh"))
    importer.runImport()
    connection = sqlite3.connect(fresh_db.database)
    connection.row_factory = sqlite3.Row

    actions = {row["actionId"] for row in connection.execute("SELECT * FROM HandsActions")}
    connection.close()

    assert 14 in actions, "completes"


def test_without_a_toml_reader_phh_files_are_refused_not_crashed(monkeypatch) -> None:
    """Python 3.10 (the PyOxidizer builds) has no tomllib; without tomli PHH says so."""
    from fpdb_3_legacy import phh_import

    def missing() -> Any:
        raise ModuleNotFoundError("No module named 'tomli'")

    monkeypatch.setattr(phh_import, "toml_module", missing)

    [item] = list(iter_documents(FIXTURES / "razz.phh"))

    assert isinstance(item, PHHImportError)
    assert item.kind == UNSUPPORTED
    assert "tomli" in str(item)


def test_the_compat_toml_reader_is_tomllib_on_this_python() -> None:
    import tomllib

    from fpdb.compat import toml_module

    assert toml_module() is tomllib


def test_an_uncalled_all_in_bet_is_returned_even_when_the_board_runs_out() -> None:
    """Ivey's 572,100 nobody could call is returned, not booked as winnings (finishing_stacks)."""
    hand = build_hand(next(iter_documents(FIXTURES / "nl_holdem_dwan_ivey.phh")))
    hand.totalPot()

    assert dict(hand.collectees) == {"Tom Dwan": 1109500}
    assert hand.pot.returned == {"Phil Ivey": 572100}
    assert hand.totalpot == 1109500


PO_HAND = """
variant = "PO"
antes = [0, 0, 0]
blinds_or_straddles = [50, 100, 0]
min_bet = 100
starting_stacks = [10000, 10000, 10000]
actions = ["d dh p1 ????????", "d dh p2 ????????", "d dh p3 ????????", "p3 cbr {raise_to}", "p1 f", "p2 f"]
"""

FL_HAND = """
variant = "FT"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
small_bet = 2
big_bet = 4
starting_stacks = [100, 100, {stack}]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cbr {raise_to}", "p1 f", "p2 f"]
"""


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (PO_HAND.format(raise_to=400), "at most to 350"),  # over the pot
        (FL_HAND.format(stack=100, raise_to=5), "goes to 4, not 5"),  # not the fixed size
        (NT_HAND.replace('"p3 cbr 6"', '"p3 cbr 3"'), "below the minimum of 4"),  # under a min-raise
    ],
)
def test_amounts_outside_the_variant_limits_are_refused(text: str, reason: str) -> None:
    error = refusal(text)
    assert error.kind == MALFORMED
    assert reason in str(error)


@pytest.mark.parametrize(
    "text",
    [
        PO_HAND.format(raise_to=350),  # exactly the pot
        PO_HAND.replace("[10000, 10000, 10000]", "[10000, 10000, 120]").format(raise_to=120),  # all in, under the pot
        FL_HAND.format(stack=3, raise_to=3),  # all in for less than a full raise
        NT_HAND.replace("[100, 100, 100]", "[100, 100, 3]").replace('"p3 cbr 6"', '"p3 cbr 3"'),  # all in, short
    ],
)
def test_amounts_within_the_limits_or_all_in_for_less_are_kept(text: str) -> None:
    assert build_hand(document(text)) is not None


# -- third review ---------------------------------------------------------------------

STOPPED_ON_THE_FLOP = (
    NT_HAND[: NT_HAND.index("actions = [")]
    + 'actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cc", "p1 cc", "p2 cc", "d db AsKsQs"]\n'
)


@pytest.mark.parametrize(
    "results",
    ["winnings = [0, 0, 0]", "finishing_stacks = [98, 98, 98]"],  # PHH's way of an ongoing hand
)
def test_an_unfinished_hand_with_results_so_far_is_still_partial(results: str) -> None:
    error = refusal(STOPPED_ON_THE_FLOP + results + "\n")
    assert error.kind == PARTIAL


ANTES_HAND = """
variant = "NT"
antes = [10, 10, 10]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [5, 100, 100]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cbr 6", "p2 f"]
"""


def test_a_trimmed_short_ante_is_unsupported() -> None:
    error = refusal(ANTES_HAND + "ante_trimming_status = true\n")
    assert error.kind == UNSUPPORTED
    assert "trimmed" in str(error)


def test_full_antes_with_trimming_on_are_imported() -> None:
    full = ANTES_HAND.replace("[5, 100, 100]", "[100, 100, 100]").replace('"p2 f"]', '"p1 f", "p2 f"]')
    hand = build_hand(document(full + "ante_trimming_status = true\n"))
    assert hand is not None


SHOWDOWN = """
variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [100, 100]
actions = [
  "d dh p1 AsKs",
  "d dh p2 QhQd",
  "p2 cc",
  "p1 cc",
  "d db 2c3d4h",
  "p1 cc",
  "p2 cc",
  "d db 9s",
  "p1 cc",
  "p2 cc",
  "d db Jc",
  "p1 cc",
  "p2 cc",
  "p1 sm -",
  "p2 sm",
]
winnings = [0, 4]
"""


def test_sm_dash_shows_the_dealt_cards_and_sm_alone_mucks() -> None:
    hand = build_hand(document(SHOWDOWN))

    assert "p1" in hand.shown
    assert hand.holecards["PREFLOP"]["p1"][1] == ["As", "Ks"]
    assert "p2" in hand.mucked
    assert "p2" not in hand.shown


# -- fourth review --------------------------------------------------------------------


def test_a_street_checked_by_only_some_players_is_not_finished() -> None:
    one_check = SHOWDOWN.replace('"p1 cc",\n  "p2 cc",\n  "p1 sm -",\n  "p2 sm",\n]', '"p1 cc",\n]')
    assert '"d db Jc",\n  "p1 cc",\n]' in one_check
    assert refusal(one_check).kind == PARTIAL


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (NT_HAND.replace("min_bet = 2\n", ""), "min_bet"),
        (FL_HAND.format(stack=100, raise_to=4).replace("small_bet = 2\n", ""), "small_bet"),
    ],
)
def test_the_variant_bet_size_fields_are_required(text: str, field: str) -> None:
    error = refusal(text)
    assert error.kind == MALFORMED
    assert f"missing required field '{field}'" in str(error)


STUD_FOURTH = """
variant = "{variant}"
antes = [1, 1]
bring_in = 2
small_bet = 5
big_bet = 10
starting_stacks = [100, 100]
actions = [
  "d dh p1 ????{p1_up}",
  "d dh p2 ????9c",
  "p{bring_in} pb",
  "p{caller} cc",
  "d dh p1 3h",
  "d dh p2 {fourth}",
  "p2 cbr {bet}",
  "p1 f",
]
"""


def stud_fourth(variant: str, fourth: str, bet: int) -> str:
    # Stud brings in on the lowest upcard (p1's 2c); razz on the highest (p2's 9c).
    p1_up, bring_in, caller = ("2c", 1, 2) if variant != "FR" else ("2c", 2, 1)
    return STUD_FOURTH.format(variant=variant, p1_up=p1_up, bring_in=bring_in, caller=caller, fourth=fourth, bet=bet)


def test_the_fourth_street_big_bet_needs_an_open_pair() -> None:
    assert build_hand(document(stud_fourth("F7S", "9d", 10))) is not None  # 9c 9d showing
    assert build_hand(document(stud_fourth("F7S", "9d", 5))) is not None  # the small bet stays allowed
    error = refusal(stud_fourth("F7S", "Kd", 10))
    assert "goes to 5, not 10" in str(error)


def test_razz_has_no_open_pair_big_bet() -> None:
    error = refusal(stud_fourth("FR", "9d", 10))
    assert "goes to 5, not 10" in str(error)


# -- fifth review ---------------------------------------------------------------------


def test_winnings_larger_than_the_pot_are_refused() -> None:
    error = refusal(NT_HAND + "winnings = [0, 0, 100]\n")
    assert error.kind == MALFORMED
    assert "collected from a pot of 5" in str(error)


def test_a_board_dealt_before_the_big_blind_has_acted_is_refused() -> None:
    skipped_option = NT_HAND.replace('"p3 cbr 6",\n  "p1 f",\n  "p2 f",', '"p3 f",\n  "p1 cc",\n  "d db AsKsQs",')
    error = refusal(skipped_option)
    assert "before its betting is over" in str(error)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (("min_bet = 2", "min_bet = 0"), "min_bet must be positive"),
        (("starting_stacks = [100, 100, 100]", "starting_stacks = [100, 0, 100]"), "p2 must be positive"),
    ],
)
def test_sizes_and_stacks_must_be_positive(change: tuple[str, str], field: str) -> None:
    assert field in str(refusal(NT_HAND.replace(*change)))


def test_a_short_deck_has_no_two_to_five() -> None:
    short = NT_HAND.replace('variant = "NT"', 'variant = "NS"').replace('"d dh p1 ????"', '"d dh p1 As5d"')
    error = refusal(short)
    assert "5d is not in a short deck" in str(error)


# -- sixth review ---------------------------------------------------------------------

SIDE_POT = """
variant = "NT"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [100, 100, 1]
actions = [
  "d dh p1 AsAd",
  "d dh p2 KsKd",
  "d dh p3 QsQd",
  "p3 cc",
  "p1 cbr 100",
  "p2 cc",
  "d db 2c3d4h",
  "d db 9s",
  "d db Jc",
  "p1 sm -",
  "p2 sm -",
  "p3 sm -",
]
"""


def test_a_short_stack_cannot_collect_beyond_the_main_pot() -> None:
    # 100 + 100 + 1 in: the all-in player is in the 3-chip main pot only.
    error = refusal(SIDE_POT + "winnings = [0, 0, 201]\n")
    assert "more than the pots they are in can win (3)" in str(error)
    assert build_hand(document(SIDE_POT + "winnings = [201, 0, 0]\n")) is not None


def test_a_folded_player_collects_nothing() -> None:
    error = refusal(NT_HAND + "winnings = [5, 0, 0]\n")
    assert "more than a folded player can win" in str(error)


def test_a_last_street_dealt_to_only_some_players_is_partial() -> None:
    whole = (FIXTURES / "stud_hilo_split.phh").read_text(encoding="utf-8")
    # The history stops after p1's seventh-street card: p2's never comes.
    stud = whole[: whole.index('  "d dh p2 8d",')] + "]\n" + whole[whole.index("finishing_stacks") :]
    assert refusal(stud).kind == PARTIAL
    draw = (FIXTURES / "triple_draw_all_in_runout.phh").read_text(encoding="utf-8").replace('  "d dh p2 7d",\n', "")
    assert refusal(draw).kind == PARTIAL


def test_actions_out_of_turn_are_refused() -> None:
    out_of_turn = NT_HAND.replace('"p3 cbr 6",\n  "p1 f",', '"p1 f",\n  "p3 cbr 6",')
    assert "out of turn: it is p3's turn" in str(refusal(out_of_turn))
    draw = (FIXTURES / "triple_draw_all_in_runout.phh").read_text(encoding="utf-8")
    swapped = draw.replace('  "p1 sd",\n  "p2 sd 9s",', '  "p2 sd 9s",\n  "p1 sd",', 1)
    assert "draws out of turn" in str(refusal(swapped))


def test_acting_again_after_the_round_is_over_is_refused() -> None:
    twice = SHOWDOWN.replace('"p1 cc",\n  "p2 cc",\n  "p1 sm -",', '"p1 cc",\n  "p2 cc",\n  "p1 cc",\n  "p1 sm -",')
    assert "after the betting on river is over" in str(refusal(twice))


@pytest.mark.parametrize(
    "change",
    [
        ('"d dh p2 QhQd"', '"d dh p2 AsQd"'),  # dealt to two players
        ('"d db Jc"', '"d db Ks"'),  # a hole card on the board
        ('"p2 sm"', '"p2 sm AsQd"'),  # shown, but dealt to the other player
    ],
)
def test_a_card_cannot_be_dealt_twice(change: tuple[str, str]) -> None:
    error = refusal(SHOWDOWN.replace(*change))
    assert "twice" in str(error) or "dealt elsewhere" in str(error)


def test_indented_hand_tables_are_read(tmp_path) -> None:
    dataset = tmp_path / "indented.phhs"
    dataset.write_text(
        "  [1]\n" + NT_HAND + "\n    [2]  # second\n" + NT_HAND.replace("cbr 6", "cbr 8"), encoding="utf-8"
    )

    assert [item.label for item in iter_documents(dataset)] == ["1", "2"]


# -- seventh review -------------------------------------------------------------------

BB_ANTE = """
variant = "NT"
antes = [0, 3, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [100, 100, 100]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 f", "p1 cc", "p2 f"]
"""


@pytest.mark.parametrize("results", ["", "winnings = [7, 0, 0]\n"])
def test_a_big_blind_ante_is_common_money_anyone_still_in_can_win(results: str) -> None:
    hand = build_hand(document(BB_ANTE + results))
    assert dict(hand.collectees) == {"p1": 7}


def test_a_partly_known_holding_keeps_its_known_cards(importer, fresh_db, tmp_path) -> None:
    text = NT_HAND.replace('"d dh p3 ????"', '"d dh p3 ??Ad"')
    assert build_hand(document(text)).holecards["PREFLOP"]["p3"] == [[], ["0x", "Ad"]]

    (tmp_path / "partly.phh").write_text(text, encoding="utf-8")
    assert importer.addImportFile(str(tmp_path / "partly.phh"))
    assert importer.runImport()[:5] == (1, 0, 0, 0, 0)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (NT_HAND.replace('"d dh p1 ????"', '"d dh p1 As"'), "deals 2 hole cards, not 1"),
        (PO_HAND.replace('"d dh p1 ????????"', '"d dh p1 ????"'), "deals 4 hole cards, not 2"),
        (
            (FIXTURES / "badugi.phh").read_text(encoding="utf-8").replace('"d dh p1 As2d3c4h"', '"d dh p1 As2d3c4h5s"'),
            "deals 4 hole cards, not 5",
        ),
    ],
)
def test_a_starting_hand_of_the_wrong_size_is_refused(text: str, reason: str) -> None:
    assert reason in str(refusal(text))


# -- eighth review --------------------------------------------------------------------

TWO_SHORT_STACKS = """
variant = "NT"
antes = [0, 0, 0, 0]
blinds_or_straddles = [1, 2, 0, 0]
min_bet = 2
starting_stacks = [1, 1, 100, 100]
actions = [
  "d dh p1 ????",
  "d dh p2 ????",
  "d dh p3 ????",
  "d dh p4 ????",
  "p3 cbr 100",
  "p4 cc",
  "d db 2c3d4h",
  "d db 9s",
  "d db Jc",
]
"""


def test_short_stacks_share_the_main_pot_rather_than_each_take_it() -> None:
    # 1 + 1 + 100 + 100: the main pot is 4, and both short stacks are held to it together.
    error = refusal(TWO_SHORT_STACKS + "winnings = [4, 4, 194, 0]\n")
    assert "8 is collected from pots of 4" in str(error)
    assert build_hand(document(TWO_SHORT_STACKS + "winnings = [2, 2, 198, 0]\n")) is not None


def test_every_live_stud_player_is_dealt_each_street() -> None:
    stud = (FIXTURES / "stud_hi.phh").read_text(encoding="utf-8").replace('  "d dh p3 Ks",\n', "", 1)
    assert "before p3 is dealt in" in str(refusal(stud))


SHORT_ALL_IN = """
variant = "NT"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [7, 100, 100]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cbr 6", "p1 cbr 7", {rest}]
"""


def test_an_all_in_for_less_does_not_reopen_the_betting() -> None:
    error = refusal(SHORT_ALL_IN.format(rest='"p2 cc", "p3 cbr 11"'))
    assert "p3 may only call or fold" in str(error)
    # p2 has not acted since the full raise: the short all-in leaves p2 free to raise.
    assert refusal(SHORT_ALL_IN.format(rest='"p2 cbr 20"')).kind == PARTIAL


def test_a_straddle_sets_the_minimum_raise() -> None:
    straddled = (
        NT_HAND.replace("antes = [0, 0, 0]", "antes = [0, 0, 0, 0]")
        .replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [1, 2, 4, 0]")
        .replace("[100, 100, 100]", "[100, 100, 100, 100]")
        .replace('"d dh p3 ????",\n  "p3 cbr 6",', '"d dh p3 ????",\n  "d dh p4 ????",\n  "p4 cbr 6",')
    )
    assert "below the minimum of 8" in str(refusal(straddled))
    assert refusal(straddled.replace('"p4 cbr 6"', '"p4 cbr 8"')).kind == PARTIAL


def test_a_partial_show_keeps_its_known_card() -> None:
    hand = build_hand(document(SHOWDOWN.replace('"d dh p2 QhQd"', '"d dh p2 ????"').replace('"p2 sm"', '"p2 sm ??Qd"')))
    assert "p2" in hand.shown
    assert "Qd" in hand.holecards["PREFLOP"]["p2"][1]


# -- ninth review ---------------------------------------------------------------------


def test_an_unnamed_player_never_takes_a_supplied_name() -> None:
    hand = build_hand(document(NT_HAND + 'players = ["p2", "", ""]\n'))
    assert [player[1] for player in hand.players] == ["p2", "p2#2", "p3"]


@pytest.mark.parametrize("card", ["A?", "?s"])
def test_a_half_known_card_is_refused(card: str) -> None:
    assert "is not a list of cards" in str(refusal(NT_HAND.replace('"d dh p1 ????"', f'"d dh p1 {card}Kd"')))


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (('"d dh p2 ????"', '"d dh p1 ????"'), "p1 is dealt twice"),
        (('"d dh p1 ????",\n  "d dh p2 ????",', '"d dh p2 ????",\n  "d dh p1 ????",'), "dealt out of turn: p1 is next"),
        (('  "d dh p3 ????",\n', ""), "before p3 is dealt in"),
    ],
)
def test_hold_em_deals_go_once_round_the_table_before_the_betting(change: tuple[str, str], reason: str) -> None:
    assert reason in str(refusal(NT_HAND.replace(*change)))


def test_a_card_cannot_be_discarded_twice() -> None:
    draw = (FIXTURES / "single_draw.phh").read_text(encoding="utf-8").replace('"p3 sd 9s"', '"p3 sd 9s9s"')
    assert "discards the same card twice" in str(refusal(draw))


# -- tenth review ---------------------------------------------------------------------


def test_a_runout_cannot_start_before_the_hole_cards() -> None:
    all_in_from_the_blinds = """
variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [2, 1]
actions = ["d db AsKsQs", "d db 2c", "d db 3c"]
winnings = [3, 0]
"""
    assert "before p1, p2 is dealt in" in str(refusal(all_in_from_the_blinds))


def test_a_second_bring_in_is_refused() -> None:
    stud = (FIXTURES / "stud_hi.phh").read_text(encoding="utf-8").replace('"p2 cbr 5",', '"p2 pb",', 1)
    assert "already posted" in str(refusal(stud))


SINGLE_DRAW = (FIXTURES / "single_draw.phh").read_text(encoding="utf-8")


def test_a_mixed_discard_removes_the_named_card_and_an_unknown_one() -> None:
    text = (
        SINGLE_DRAW.replace('"d dh p1 7h5c4d3s2c"', '"d dh p1 7h5c4d3s??"')
        .replace('"p1 sd",', '"p1 sd 7h??",')
        .replace('"d dh p3 Kh",', '"d dh p1 KcQc",\n  "d dh p3 Kh",')
    )
    hand = build_hand(document(text))

    assert hand.holecards["DRAWONE"]["p1"] == [["Kc", "Qc"], ["5c", "4d", "3s"]]
    assert hand.discards["DRAWONE"]["p1"] == {"7h"}


def test_an_unnamed_discard_from_a_fully_known_hand_is_refused() -> None:
    text = SINGLE_DRAW.replace('"p1 sd",', '"p1 sd ??",')
    assert "unnamed card from a hand whose cards are all known" in str(refusal(text))


def test_the_hero_s_newly_shown_card_is_kept() -> None:
    text = SHOWDOWN.replace('"d dh p2 QhQd"', '"d dh p2 ????"').replace('"p2 sm"', '"p2 sm ??Qd"') + '_hero = "p2"\n'
    hand = build_hand(document(text))

    assert hand.hero == "p2"
    assert hand.holecards["PREFLOP"]["p2"][1] == ["0x", "Qd"]
    assert "p2" in hand.shown


# -- eleventh review ------------------------------------------------------------------

FOUR_HANDED = """
variant = "NT"
antes = [0, 0, 0, 0]
blinds_or_straddles = [1, 2, 0, 0]
min_bet = 2
starting_stacks = {stacks}
actions = ["d dh p1 AsKs", "d dh p2 QhQd", "d dh p3 7c2d", "d dh p4 8c3d", {actions}]
"""


def test_short_all_ins_that_add_up_to_a_full_raise_reopen_the_betting() -> None:
    """The three cases PokerKit was asked about: it accepts the first and third, refuses the second."""
    cumulative = FOUR_HANDED.format(
        stacks="[7, 10, 100, 100]", actions='"p3 cbr 6", "p4 cc", "p1 cbr 7", "p2 cbr 10", "p3 cbr 20"'
    )
    assert refusal(cumulative).kind == PARTIAL  # accepted: the history simply stops there

    single = FOUR_HANDED.format(
        stacks="[7, 100, 100, 100]", actions='"p3 cbr 6", "p4 cc", "p1 cbr 7", "p2 f", "p3 cbr 20"'
    )
    assert "p3 may only call or fold" in str(refusal(single))
    assert refusal(single.replace('"p3 cbr 20"', '"p3 cc"')).kind == PARTIAL


def test_a_raise_with_everyone_else_all_in_is_refused() -> None:
    three = NT_HAND.replace("[100, 100, 100]", "[7, 10, 100]").replace(
        '"p3 cbr 6",\n  "p1 f",\n  "p2 f",', '"p3 cbr 6",\n  "p1 cbr 7",\n  "p2 cbr 10",\n  "p3 cbr 20",'
    )
    assert "only a call is possible" in str(refusal(three))


def test_a_draw_street_bets_only_once_everyone_has_drawn() -> None:
    early_bet = SINGLE_DRAW.replace('"p1 sd",\n  "p3 sd 9s",', '"p1 sd",\n  "p1 cbr 100",\n  "p3 sd 9s",')
    assert "before p3 is dealt in" in str(refusal(early_bet))


def test_a_partial_show_keeps_what_the_deal_already_said() -> None:
    text = SHOWDOWN.replace('"d dh p2 QhQd"', '"d dh p2 Qh??"').replace('"p2 sm"', '"p2 sm ??Qd"')
    hand = build_hand(document(text))
    assert hand.holecards["PREFLOP"]["p2"][1] == ["Qh", "Qd"]


# -- twelfth review -------------------------------------------------------------------


def test_a_show_must_agree_with_the_deal() -> None:
    assert build_hand(document(SHOWDOWN.replace('"p1 sm -"', '"p1 sm KsAs"'))).holecards["PREFLOP"]["p1"][1] == [
        "Ks",
        "As",
    ]
    other_cards = SHOWDOWN.replace('"p1 sm -"', '"p1 sm 7h6h"')
    assert "p1 shows 7h 6h, which the deal did not give them" in str(refusal(other_cards))
    half = SHOWDOWN.replace('"d dh p1 AsKs"', '"d dh p1 As??"').replace('"p1 sm -"', '"p1 sm 7h6h"')
    assert "which the deal did not give them" in str(refusal(half))
    too_few = SHOWDOWN.replace('"p1 sm -"', '"p1 sm As"')
    assert "p1 shows 1 cards for 2 dealt" in str(refusal(too_few))


def test_an_unknown_card_discarded_as_another_player_s_card_is_refused() -> None:
    text = SINGLE_DRAW.replace('"d dh p1 7h5c4d3s2c"', '"d dh p1 7h5c4d3s??"').replace('"p1 sd",', '"p1 sd 8h",')
    assert "p1 discards 8h, which is dealt elsewhere" in str(refusal(text))


def test_amounts_finer_than_a_hundredth_are_unsupported() -> None:
    error = refusal(NT_HAND.replace("[100, 100, 100]", "[100.005, 100, 100]"))
    assert error.kind == UNSUPPORTED
    assert "two decimal places" in str(error)
    assert build_hand(document(NT_HAND.replace("[100, 100, 100]", "[100.25, 100, 100]")))


def test_an_impossible_date_is_malformed() -> None:
    error = refusal(SHOWDOWN + "year = 2026\nmonth = 2\nday = 30\n")
    assert error.kind == MALFORMED
    assert "2026-2-30 is not a date" in str(error)


# -- thirteenth review ----------------------------------------------------------------

STUD_HILO = (FIXTURES / "stud_hilo_split.phh").read_text(encoding="utf-8")
P1_SEVEN = ["Ad", "2d", "3c", "4c", "9h", "Th", "6h"]


def test_a_misspelled_time_zone_is_malformed() -> None:
    error = refusal(SHOWDOWN + 'year = 2026\nmonth = 2\nday = 3\ntime_zone = "America/New_Yrok"\n')
    assert error.kind == MALFORMED
    assert "'America/New_Yrok' is not a time zone" in str(error)


def test_third_street_opens_with_the_bring_in_or_a_completion() -> None:
    folds = stud_fourth("F7S", "9d", 5).replace('"p1 pb"', '"p1 f"')
    assert "p1 folds before the bring-in is posted" in str(refusal(folds))
    checks = stud_fourth("F7S", "9d", 5).replace('"p1 pb"', '"p1 cc"')
    assert "p1 checks before the bring-in is posted" in str(refusal(checks))


def test_completing_in_place_of_the_bring_in_is_a_completion() -> None:
    hand = build_hand(document(stud_fourth("F7S", "9d", 5).replace('"p1 pb"', '"p1 cbr 5"')))
    assert [action for action in actions_of(hand) if action[0] == "THIRD"] == [
        ("THIRD", "p1", "completes", 5),
        ("THIRD", "p2", "calls", 5),
    ]


def test_stud_hi_lo_has_no_open_pair_big_bet() -> None:
    assert "goes to 5, not 10" in str(refusal(stud_fourth("F7S/8", "9d", 10)))


def test_the_stud_hero_s_seventh_card_is_where_fpdb_reads_it() -> None:
    hand = build_hand(document(STUD_HILO + '_hero = "p1"\n'))
    assert hand.join_holecards("p1", asList=True) == P1_SEVEN


def test_a_stud_hero_s_shown_down_cards_are_kept() -> None:
    text = STUD_HILO.replace('"d dh p1 Ad2d3c"', '"d dh p1 ????3c"') + '_hero = "p1"\n'
    hand = build_hand(document(text))
    assert hand.join_holecards("p1", asList=True) == P1_SEVEN
    assert "p1" in hand.shown


def test_a_site_150_that_is_not_phh_is_refused(tmp_path) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE Sites (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    connection.execute("INSERT INTO Sites VALUES (150, 'Other', 'OT')")

    class FakeDb:
        sql = type("Sql", (), {"query": {"placeholder": "?"}})()

        def get_cursor(self) -> Any:
            return connection.cursor()

        def commit(self) -> None:
            connection.commit()

    path = tmp_path / "hand.phh"
    path.write_text(SHOWDOWN, encoding="utf-8")
    result = import_file(FakeDb(), None, path)
    assert (result.imported, result.unsupported) == (0, 1)
    assert "site id 150 is 'Other' ('OT')" in result.errors[0]


def test_an_infinite_starting_stack_is_unsupported() -> None:
    error = refusal(NT_HAND.replace("[100, 100, 100]", "[inf, 100, 100]"))
    assert error.kind == UNSUPPORTED
    assert "a starting stack is unknown" in str(error)


# -- fourteenth review ----------------------------------------------------------------


def test_a_quoted_table_name_with_a_dot_is_a_hand_and_a_dotted_one_a_sub_table(tmp_path) -> None:
    path = tmp_path / "hands.phhs"
    path.write_text(f"[1]\n{SHOWDOWN}\n[1.notes]\nseen = true\n['session.1']\n{SHOWDOWN}", encoding="utf-8")
    documents = list(iter_documents(path))
    assert [document.label for document in documents] == ["1", "session.1"]
    assert documents[0].data["notes"] == {"seen": True}


def test_a_partial_date_keeps_what_it_gives_and_a_mistyped_one_is_malformed() -> None:
    assert build_hand(document(SHOWDOWN + "year = 2009\n")).startTime == datetime.datetime(2009, 1, 1)
    assert build_hand(document(SHOWDOWN + "year = 2009\nmonth = 7\n")).startTime == datetime.datetime(2009, 7, 1)
    assert build_hand(document(SHOWDOWN + "month = 7\nday = 3\n")).startTime == datetime.datetime(1970, 7, 3)
    error = refusal(SHOWDOWN + 'year = "2026"\nmonth = 2\nday = 3\n')
    assert error.kind == MALFORMED
    assert "are not a date" in str(error)
    assert "is not a time" in str(refusal(SHOWDOWN + 'time = "noon"\n'))


def test_seat_count_must_hold_every_seat() -> None:
    assert build_hand(document(SHOWDOWN + "seats = [1, 6]\nseat_count = 6\n")).maxseats == 6
    assert build_hand(document(SHOWDOWN + "seats = [1, 6]\n")).maxseats == 6
    assert "seat_count 2 does not hold seat 6" in str(refusal(SHOWDOWN + "seats = [1, 6]\nseat_count = 2\n"))
    assert "does not hold seat" in str(refusal(SHOWDOWN + 'seat_count = "9"\n'))


def test_a_sub_table_of_another_hand_is_malformed(tmp_path) -> None:
    path = tmp_path / "hands.phhs"
    path.write_text(f"[1]\n{SHOWDOWN}\n[2.notes]\nseen = true\n", encoding="utf-8")
    (error,) = list(iter_documents(path))
    assert isinstance(error, PHHImportError)
    assert error.kind == MALFORMED
    assert "tables of another hand: '2'" in str(error)


# -- fifteenth review -----------------------------------------------------------------


def test_a_header_inside_a_multiline_string_is_text(tmp_path) -> None:
    notes = (
        '_notes = """\n[second]\nstill the note, with a \\""" quote\n[third]\n"""\n'
        "_literal = '''\n[fourth]\n'''\n"
        '_single = "\\"\\"\\" is not a multiline string" # nor is """ in a comment\n'
    )
    path = tmp_path / "hands.phhs"
    path.write_text(f"[1]\n{SHOWDOWN}{notes}[2]\n{SHOWDOWN}", encoding="utf-8")
    documents = list(iter_documents(path))
    assert [document.label for document in documents] == ["1", "2"]
    assert documents[0].data["_notes"] == '[second]\nstill the note, with a """ quote\n[third]\n'
    assert documents[0].data["_literal"] == "[fourth]\n"


def test_a_time_zone_abbreviation_alone_is_unsupported_unless_utc() -> None:
    dated = SHOWDOWN + "year = 2026\nmonth = 7\nday = 3\ntime = 12:00:00\n"
    error = refusal(dated + 'time_zone_abbreviation = "EDT"\n')
    assert error.kind == UNSUPPORTED
    assert "'EDT' without a time_zone" in str(error)
    hand = build_hand(document(dated + 'time_zone_abbreviation = "UTC"\n'))
    assert hand.startTime == datetime.datetime(2026, 7, 3, 12)
    both = dated + 'time_zone = "America/New_York"\ntime_zone_abbreviation = "EDT"\n'
    assert build_hand(document(both)).startTime == datetime.datetime(2026, 7, 3, 16)


# -- sixteenth review -----------------------------------------------------------------

FL_FOUR = """
variant = "FT"
antes = [0, 0, 0, 0]
blinds_or_straddles = [1, 2, 0, 0]
small_bet = 2
big_bet = 4
starting_stacks = [100, 100, 100, 5]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "d dh p4 ????", "p3 cbr 4", "p4 cbr 5", "p1 f", "p2 cc", {last}]
"""


def test_a_fixed_limit_all_in_for_less_does_not_reopen_the_betting() -> None:
    """PokerKit 0.7.6 refuses p3's re-raise and accepts the call."""
    assert "p3 may only call or fold" in str(refusal(FL_FOUR.format(last='"p3 cbr 7"')))
    assert refusal(FL_FOUR.format(last='"p3 cc"')).kind == PARTIAL


def test_the_bring_in_player_may_raise_over_a_completion() -> None:
    text = stud_fourth("F7S", "9d", 5).replace('"p2 cc",', '"p2 cbr 5",\n  "p1 cbr 10",\n  "p2 cc",')
    assert ("THIRD", "p1", "raises", 5) in actions_of(build_hand(document(text)))


def test_a_time_without_a_date_keeps_its_clock_and_zone() -> None:
    text = SHOWDOWN + 'time = 12:30:00\ntime_zone = "America/New_York"\n'
    assert build_hand(document(text)).startTime == datetime.datetime(1970, 1, 1, 17, 30)


def test_a_time_zone_that_is_not_a_string_is_malformed() -> None:
    error = refusal(SHOWDOWN + "year = 2026\ntime_zone = 123\n")
    assert error.kind == MALFORMED
    assert "time_zone 123 is not a string" in str(error)


def test_the_abbreviation_picks_the_repeated_hour() -> None:
    night = SHOWDOWN + 'year = 2026\nmonth = 11\nday = 1\ntime = 01:30:00\ntime_zone = "America/New_York"\n'
    assert build_hand(document(night + 'time_zone_abbreviation = "EDT"\n')).startTime == datetime.datetime(
        2026, 11, 1, 5, 30
    )
    assert build_hand(document(night + 'time_zone_abbreviation = "EST"\n')).startTime == datetime.datetime(
        2026, 11, 1, 6, 30
    )
    assert "'PST' is not America/New_York's abbreviation" in str(refusal(night + 'time_zone_abbreviation = "PST"\n'))


def test_every_live_player_draws_before_the_next_draw() -> None:
    draw = (FIXTURES / "triple_draw_all_in_runout.phh").read_text(encoding="utf-8")
    skipped = draw.replace('  "p1 sd",\n  "p2 sd Kh",\n  "d dh p2 Qd",\n', '  "p1 sd",\n', 1)
    assert "the next draw comes before p2 has drawn on this one" in str(refusal(skipped))


def test_replacements_are_dealt_in_order_once_everyone_has_drawn() -> None:
    both = SINGLE_DRAW.replace('"p1 sd",', '"p1 sd 2c",')
    out_of_order = both.replace('"d dh p3 Kh",', '"d dh p3 Kh",\n  "d dh p1 Kc",')
    assert "p3 is dealt out of turn: p1 is next" in str(refusal(out_of_order))
    early = both.replace('"p3 sd 9s",\n  "d dh p3 Kh",', '"d dh p1 Kc",\n  "p3 sd 9s",\n  "d dh p3 Kh",')
    assert "replacements are dealt once everyone has drawn: p3 has not" in str(refusal(early))


def test_no_street_is_dealt_after_a_fold_out() -> None:
    folded = SHOWDOWN.replace('"p2 cc",\n  "p1 cc",\n  "d db 2c3d4h",', '"p2 f",\n  "d db 2c3d4h",')
    assert "the hand is over: everyone but p1 folded" in str(refusal(folded))


# -- seventeenth review ---------------------------------------------------------------


def test_a_short_stack_ante_is_unsupported_trimmed_or_not() -> None:
    short = NT_HAND.replace("antes = [0, 0, 0]", "antes = [10, 10, 10]").replace("[100, 100, 100]", "[5, 100, 100]")
    error = refusal(short)
    assert error.kind == UNSUPPORTED
    assert "p1's ante is short for a short stack" in str(error)
    assert "is trimmed for a short stack" in str(refusal(short + "ante_trimming_status = true\n"))


def test_every_date_field_given_is_kept() -> None:
    assert build_hand(document(SHOWDOWN + "year = 2009\nday = 15\n")).startTime == datetime.datetime(2009, 1, 15)
    assert build_hand(document(SHOWDOWN + "day = 15\n")).startTime == datetime.datetime(1970, 1, 15)


def test_after_the_fourth_street_big_bet_every_raise_is_big() -> None:
    big_then = stud_fourth("F7S", "9d", 10).replace('"p1 f",', '"p1 cbr {raise_to}",')
    assert "goes to 20, not 15" in str(refusal(big_then.replace("{raise_to}", "15")))
    assert refusal(big_then.replace("{raise_to}", "20")).kind == PARTIAL
    small_then_big = stud_fourth("F7S", "9d", 5).replace('"p1 f",', '"p1 cbr 15",\n  "p2 cbr 25",\n  "p1 f",')
    assert build_hand(document(small_then_big)) is not None  # 5, raised by the big bet, then by it again


# -- eighteenth review ----------------------------------------------------------------


def test_a_header_inside_an_array_or_inline_table_is_a_value(tmp_path) -> None:
    values = '_x = [\n  [1],\n  { a = "[2]" },\n]\n'
    path = tmp_path / "hands.phhs"
    path.write_text(f"[1]\n{SHOWDOWN}{values}[2]\n{SHOWDOWN}", encoding="utf-8")
    documents = list(iter_documents(path))
    assert [document.label for document in documents] == ["1", "2"]
    assert documents[0].data["_x"] == [[1], {"a": "[2]"}]


def test_a_wall_time_the_clocks_skip_is_malformed() -> None:
    gap = SHOWDOWN + 'year = 2026\nmonth = 3\nday = 8\ntime = 02:30:00\ntime_zone = "America/New_York"\n'
    error = refusal(gap)
    assert error.kind == MALFORMED
    assert "2026-03-08 02:30 does not exist in America/New_York" in str(error)
    after = gap.replace("02:30:00", "03:30:00")
    assert build_hand(document(after)).startTime == datetime.datetime(2026, 3, 8, 7, 30)


def test_a_shared_stud_card_is_unsupported() -> None:
    error = refusal(stud_fourth("F7S", "9d", 5).replace('"d dh p2 9d",', '"d db 9d",'))
    assert error.kind == UNSUPPORTED
    assert "a shared stud card" in str(error)


STUD_SHORT_COMPLETION = """
variant = "F7S"
antes = [0, 0, 0]
bring_in = 1
small_bet = 4
big_bet = 8
starting_stacks = [50, 2, 50]
actions = ["d dh p1 ????2c", "d dh p2 ????8c", "d dh p3 ????9c", "p1 pb", "p2 cbr 2", "p3 cbr {to}"]
"""


def test_after_a_short_all_in_completion_the_next_one_adds_a_small_bet() -> None:
    """PokerKit 0.7.6: after the bring-in of 1 and an all-in to 2, the minimum is 6, not 4."""
    assert "goes to 6, not 4" in str(refusal(STUD_SHORT_COMPLETION.format(to=4)))
    assert refusal(STUD_SHORT_COMPLETION.format(to=6)).kind == PARTIAL
