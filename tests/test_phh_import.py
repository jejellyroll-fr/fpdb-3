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
from io import StringIO
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


def names_of(hand: Any) -> list[str]:
    return [str(player[1]) for player in hand.players]


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
    files = {row["id"]: Path(row["file"]).stem for row in connection.execute("SELECT * FROM Files")}
    file_of_hand = {row["id"]: files[row["fileId"]] for row in connection.execute("SELECT * FROM Hands")}
    results: dict[str, list[tuple[int, int]]] = {}
    for row in connection.execute("SELECT * FROM HandsPlayers"):
        results.setdefault(file_of_hand[row["handId"]], []).append((row["seatNo"], row["totalProfit"]))

    for name, expected in EXPECTED.items():
        cents = [round(payoff * 100) for payoff in expected["payoffs"]]
        assert [profit for _seat, profit in sorted(results[name])] == cents, name


def test_each_fixture_is_stored_as_its_fpdb_game(imported) -> None:
    _importer, _totals, connection = imported
    files = {row["id"]: Path(row["file"]).stem for row in connection.execute("SELECT * FROM Files")}
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


def test_the_hand_number_is_its_content_and_place() -> None:
    first = document(NT_HAND)
    assert hand_number(first.data, "a.phhs\x001") == hand_number(document(NT_HAND).data, "a.phhs\x001")
    assert hand_number(first.data, "a.phhs\x001") != hand_number(first.data, "a.phhs\x002")
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
    # [1-again] reads like [1] but sits at another table: a hand of its own, not a duplicate.
    assert (stored, duplicates, partial, skipped, errors) == (4, 0, 1, 1, 2)
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
  "d db Kc3d4h",
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
winnings = [4, 0]  # p1's kings; p2 mucks
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
    runout = (FIXTURES / "triple_draw_all_in_runout.phh").read_text(encoding="utf-8")
    # The history stops before p2's last replacement (and the showdown after it).
    draw = runout[: runout.index('  "d dh p2 7d",')] + "]\n" + runout[runout.index("winnings") :]
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
    # Shown in another order, the cards stay where they were dealt.
    assert build_hand(document(SHOWDOWN.replace('"p1 sm -"', '"p1 sm KsAs"'))).holecards["PREFLOP"]["p1"][1] == [
        "As",
        "Ks",
    ]
    other_cards = SHOWDOWN.replace('"p1 sm -"', '"p1 sm 7h6h"')
    assert "p1 shows 7h 6h, which the deal did not give them" in str(refusal(other_cards))
    half = SHOWDOWN.replace('"d dh p1 AsKs"', '"d dh p1 As??"').replace('"p1 sm -"', '"p1 sm 7h6h"')
    assert "which the deal did not give them" in str(refusal(half))
    too_many = SHOWDOWN.replace('"p1 sm -"', '"p1 sm AsKs2h"')
    assert "p1 shows 3 cards for 2 dealt" in str(refusal(too_many))


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
    assert "year '2026' is not an integer" in str(error)
    assert "is not a local time of day" in str(refusal(SHOWDOWN + 'time = "noon"\n'))


def test_seat_count_must_hold_every_seat() -> None:
    assert build_hand(document(SHOWDOWN + "seats = [1, 6]\nseat_count = 6\n")).maxseats == 6
    assert build_hand(document(SHOWDOWN + "seats = [1, 6]\n")).maxseats == 6
    assert "seat_count 2 does not hold seat 6" in str(refusal(SHOWDOWN + "seats = [1, 6]\nseat_count = 2\n"))
    assert "seat_count '9' is not an integer" in str(refusal(SHOWDOWN + 'seat_count = "9"\n'))


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


def test_a_repeated_hour_without_an_abbreviation_is_unsupported() -> None:
    night = SHOWDOWN + 'year = 2026\nmonth = 11\nday = 1\ntime = 01:30:00\ntime_zone = "America/New_York"\n'
    error = refusal(night)
    assert error.kind == UNSUPPORTED
    assert "2026-11-01 01:30 happens twice in America/New_York" in str(error)
    assert build_hand(document(night.replace("01:30:00", "02:30:00"))).startTime == datetime.datetime(
        2026, 11, 1, 7, 30
    )


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
    folded = SHOWDOWN.replace('"p2 cc",\n  "p1 cc",\n  "d db Kc3d4h",', '"p2 f",\n  "d db Kc3d4h",')
    assert "the hand is over: everyone but p1 folded" in str(refusal(folded))


# -- seventeenth review ---------------------------------------------------------------


def test_a_short_stack_ante_is_unsupported_only_when_trimmed() -> None:
    """PokerKit 0.7.6: untrimmed, one pot of 25 all three can win; trimmed, 15 and a side pot of 10."""
    short = NT_HAND.replace("antes = [0, 0, 0]", "antes = [10, 10, 10]").replace("[100, 100, 100]", "[5, 100, 100]")
    short = short.replace('  "p1 f",\n', "")  # p1 is all in from the ante
    assert refusal(short).kind == PARTIAL  # accepted: the history stops before the board
    error = refusal(short + "ante_trimming_status = true\n")
    assert error.kind == UNSUPPORTED
    assert "p1's ante is trimmed to a short stack" in str(error)


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


# -- nineteenth review ----------------------------------------------------------------


def test_a_phh_file_never_shares_the_files_row_of_a_same_named_room_file(importer, fresh_db, tmp_path) -> None:
    now = datetime.datetime(2026, 1, 1)
    with importer.database.transaction():
        room_id = importer.database.storeFile(["session", "PokerStars", now, now, 7, 7, 0, 0, 0, 0, 0, True])
    shutil.copy(FIXTURES / "fl_holdem.phh", tmp_path / "session.phh")
    assert importer.addImportFile(str(tmp_path / "session.phh"))
    importer.runImport()
    connection = sqlite3.connect(fresh_db.database)
    connection.row_factory = sqlite3.Row
    rows = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM Files")}
    file_ids = {row["fileId"] for row in connection.execute("SELECT * FROM Hands")}
    connection.close()

    (phh_id,) = file_ids
    assert phh_id != room_id
    assert (rows[phh_id]["file"], rows[phh_id]["site"]) == (f"PHH/{tmp_path / 'session.phh'}", PHH_SITE_NAME)
    assert (rows[room_id]["site"], rows[room_id]["hands"]) == ("PokerStars", 7)


def test_a_player_who_mucks_can_win_nothing() -> None:
    assert "p2" in build_hand(document(SHOWDOWN)).mucked  # p1 shows and wins: fine
    error = refusal(SHOWDOWN.replace("winnings = [4, 0]", "winnings = [0, 4]"))
    assert "p2 collects 4, more than a mucked hand can win (0)" in str(error)


# -- twentieth review -----------------------------------------------------------------


def test_same_named_phh_files_in_two_directories_have_their_own_files_rows(importer, fresh_db, tmp_path) -> None:
    for event, fixture in (("event-a", "fl_holdem.phh"), ("event-b", "pl_omaha.phh")):
        (tmp_path / event).mkdir()
        shutil.copy(FIXTURES / fixture, tmp_path / event / "1.phh")
        assert importer.addImportFile(str(tmp_path / event / "1.phh"))
    importer.runImport()
    connection = sqlite3.connect(fresh_db.database)
    files = {row[0] for row in connection.execute("SELECT fileId FROM Hands")}
    connection.close()
    assert len(files) == 2


def test_a_time_local_to_a_location_without_a_zone_is_unsupported() -> None:
    located = SHOWDOWN + 'year = 2026\ntime = 12:00:00\ncity = "Toronto"\nregion = "Ontario"\ncountry = "Canada"\n'
    error = refusal(located)
    assert error.kind == UNSUPPORTED
    assert "local to Toronto, Ontario, Canada" in str(error)
    zoned = located + 'time_zone = "America/Toronto"\n'
    assert build_hand(document(zoned)).startTime == datetime.datetime(2026, 1, 1, 17)
    assert build_hand(document(SHOWDOWN + 'year = 2026\ncity = "Toronto"\n')) is not None  # no time, no shift


def test_a_zone_is_checked_even_without_a_date() -> None:
    error = refusal(SHOWDOWN + 'time_zone = "America/New_Yrok"\n')
    assert error.kind == MALFORMED
    assert "'America/New_Yrok' is not a time zone" in str(error)
    assert build_hand(document(SHOWDOWN + 'time_zone = "America/New_York"\n')).startTime == datetime.datetime(
        1970, 1, 1
    )


# -- twenty-first review --------------------------------------------------------------


def test_cards_are_shown_only_at_the_showdown_or_in_an_all_in_runout() -> None:
    early = SHOWDOWN.replace('"d dh p2 QhQd",', '"d dh p2 QhQd",\n  "p1 sm -",').replace(
        '  "p1 sm -",\n  "p2 sm",', '  "p2 sm",'
    )
    assert "p1 shows or mucks before the showdown" in str(refusal(early))
    assert build_hand(next(iter_documents(FIXTURES / "triple_draw_all_in_runout.phh"))) is not None


# -- twenty-second review -------------------------------------------------------------


def test_an_all_in_player_cannot_fold() -> None:
    stud = STUD_SHORT_COMPLETION.format(to=6).replace('"p3 cbr 6"]', '"p3 cbr 6", "p2 f"]')
    assert "p2 is all in and cannot act" in str(refusal(stud))
    holdem = NT_HAND.replace("[100, 100, 100]", "[100, 100, 6]").replace('"p1 f",', '"p3 f",\n  "p1 f",')
    assert "p3 is all in and cannot act" in str(refusal(holdem))


# -- twenty-third review --------------------------------------------------------------


def test_the_hands_after_an_unclosed_value_are_recovered(tmp_path) -> None:
    path = tmp_path / "hands.phhs"
    path.write_text(f'[1]\n{SHOWDOWN}_x = [\n[2]\n{SHOWDOWN}[3]\n_n = """\n[4]\n{SHOWDOWN}', encoding="utf-8")
    items = list(iter_documents(path))
    # [1] leaves an array open and [3] a string: each is malformed, and the hand its value
    # swallowed comes back.
    assert [getattr(item, "label", None) or item.kind for item in items] == [MALFORMED, "2", MALFORMED, "4"]
    assert items[1].line == len(f"[1]\n{SHOWDOWN}_x = [\n".splitlines()) + 1
    assert build_hand(items[1]) is not None
    assert build_hand(items[3]) is not None


SHORT_BIG_BLIND = """
variant = "NT"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [100, 1, 100]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", {actions}]
"""


def test_a_short_big_blind_sets_the_call_at_what_it_posted() -> None:
    """PokerKit 0.7.6: a big blind of 2 posted all in for 1 is called for 1, raised to at least 3."""
    hand_text = SHORT_BIG_BLIND.format(actions='"p3 cc", "p1 cc"')
    assert refusal(hand_text).kind == PARTIAL
    assert "below the minimum of 3" in str(refusal(SHORT_BIG_BLIND.format(actions='"p3 cbr 2"')))


# -- twenty-fourth review -------------------------------------------------------------


def test_only_a_full_location_makes_the_time_local() -> None:
    timed = SHOWDOWN + "year = 2026\ntime = 12:00:00\n"
    assert build_hand(document(timed + 'city = "Toronto"\n')).startTime == datetime.datetime(2026, 1, 1, 12)
    full = timed + 'city = "Toronto"\nregion = "Ontario"\ncountry = "Canada"\n'
    assert refusal(full).kind == UNSUPPORTED


def test_players_must_be_a_list_of_names() -> None:
    assert "players must be a list of names" in str(refusal(SHOWDOWN + 'players = "Am"\n'))
    assert "players must be a list of names" in str(refusal(SHOWDOWN + "players = [1, 2]\n"))
    assert build_hand(document(SHOWDOWN + 'players = ["Amy", ""]\n')) is not None


def test_a_long_phh_path_is_told_apart_within_what_mysql_indexes(tmp_path) -> None:
    from fpdb_3_legacy.phh_import import phh_file_name

    deep = tmp_path / ("d" * 120) / ("e" * 120)
    first, second = phh_file_name(deep / "a" / "1.phh"), phh_file_name(deep / "b" / "1.phh")
    assert len(first) <= 255 and len(second) <= 255
    assert first[:255] != second[:255]
    assert first.endswith("/1.phh")
    assert phh_file_name(tmp_path / "1.phh") == f"PHH/{tmp_path / '1.phh'}"


# -- twenty-fifth review --------------------------------------------------------------


def test_empty_players_or_seats_are_malformed() -> None:
    assert "do not have the same length" in str(refusal(SHOWDOWN + "players = []\n"))
    assert "do not have the same length" in str(refusal(SHOWDOWN + "seats = []\n"))
    assert "seats must be a list" in str(refusal(SHOWDOWN + "seats = 2\n"))


def test_a_table_numbered_0_keeps_its_number() -> None:
    assert build_hand(document(SHOWDOWN + 'table = 0\nevent = "WSOP"\n')).tablename == "0"
    assert build_hand(document(SHOWDOWN + 'event = "WSOP"\n')).tablename == "WSOP"


def test_a_stud_show_in_another_order_keeps_the_deal_s_places() -> None:
    text = STUD_HILO.replace('"d dh p1 Ad2d3c"', '"d dh p1 ????3c"').replace(
        '"p1 sm Ad2d3c4c9hTh6h"', '"p1 sm 6hTh9h4c3c2dAd"'
    )
    hand = build_hand(document(text + '_hero = "p1"\n'))
    assert hand.holecards["THIRD"]["p1"] == (["3c"], ["2d", "Ad"])
    assert hand.holecards["FOURTH"]["p1"][0] == ["4c"]
    assert hand.join_holecards("p1", asList=True)[2:] == P1_SEVEN[2:]


# -- twenty-sixth review --------------------------------------------------------------


def test_a_show_of_fewer_cards_is_partial() -> None:
    """PokerKit 0.7.6, cash game: ``sm As`` over ``????`` shows ``As ??``."""
    text = SHOWDOWN.replace('"d dh p1 AsKs"', '"d dh p1 ????"').replace('"p1 sm -"', '"p1 sm As"')
    assert build_hand(document(text)).holecards["PREFLOP"]["p1"][1] == ["As", "0x"]
    kept = SHOWDOWN.replace('"p1 sm -"', '"p1 sm Ks"')
    assert build_hand(document(kept)).holecards["PREFLOP"]["p1"][1] == ["As", "Ks"]


def test_a_player_shows_or_mucks_once() -> None:
    twice = SHOWDOWN.replace('"p1 sm -",', '"p1 sm -",\n  "p1 sm",')
    assert "p1 shows or mucks a second time" in str(refusal(twice))


# -- twenty-seventh review ------------------------------------------------------------


def test_a_player_does_not_act_twice_with_nothing_changed() -> None:
    stud = stud_fourth("F7S", "9d", 5).replace('"p2 cc",', '"p2 cbr 5",\n  "p2 cc",')
    assert "p2 acts again with nothing changed" in str(refusal(stud))
    checks = SHOWDOWN.replace('"d db 9s",\n  "p1 cc",\n  "p2 cc",', '"d db 9s",\n  "p1 cc",\n  "p1 cc",')
    assert "p1 acts again with nothing changed" in str(refusal(checks))


def test_two_hands_that_read_alike_in_one_file_are_both_imported(importer, fresh_db, tmp_path) -> None:
    path = tmp_path / "alike.phhs"
    path.write_text(f"[1]\n{SHOWDOWN}\n[2]\n{SHOWDOWN}", encoding="utf-8")
    assert importer.addImportFile(str(path))
    stored, duplicates, *_rest = importer.runImport()
    assert (stored, duplicates) == (2, 0)
    importer.clearFileList()  # the same file again...
    assert importer.addImportFile(str(path))
    stored, duplicates, *_rest = importer.runImport()
    assert (stored, duplicates) == (0, 2)  # ...finds both as duplicates


# -- twenty-eighth review -------------------------------------------------------------


def test_identical_hands_in_same_named_files_of_two_directories_are_both_kept(importer, fresh_db, tmp_path) -> None:
    for event in ("event-a", "event-b"):
        (tmp_path / event).mkdir()
        shutil.copy(FIXTURES / "fl_holdem.phh", tmp_path / event / "1.phh")
        assert importer.addImportFile(str(tmp_path / event / "1.phh"))
    stored, duplicates, *_rest = importer.runImport()
    assert (stored, duplicates) == (2, 0)


def test_a_line_that_is_not_utf8_makes_only_its_hand_malformed(tmp_path) -> None:
    path = tmp_path / "hands.phhs"
    good = SHOWDOWN.encode("utf-8")
    path.write_bytes(b"[1]\n" + good + b"[2]\n# caf\xe9\n" + good + b"[3]\n" + good)
    items = list(iter_documents(path))
    assert [getattr(item, "label", None) or item.kind for item in items] == ["1", MALFORMED, "3"]
    bad_line = len(good.splitlines()) + 3  # [1], its lines, [2], then the comment
    assert f"line {bad_line} is not UTF-8" in str(items[1])

    single = tmp_path / "hand.phh"
    single.write_bytes(b"# caf\xe9\n" + good)
    (error,) = list(iter_documents(single))
    assert isinstance(error, PHHImportError)
    assert error.kind == MALFORMED
    assert "not UTF-8 (byte 5)" in str(error)


# -- twenty-ninth review --------------------------------------------------------------


def test_the_hands_after_an_undecodable_unclosed_value_are_recovered(tmp_path) -> None:
    path = tmp_path / "hands.phhs"
    good = SHOWDOWN.encode("utf-8")
    path.write_bytes(b"[1]\n" + good + b"_x = [\xff\n[2]\n" + good + b"[3]\n" + good)
    items = list(iter_documents(path))
    assert [getattr(item, "label", None) or item.kind for item in items] == [MALFORMED, "2", "3"]
    assert "is not UTF-8" in str(items[0])


# -- thirtieth review -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("blinds", "stakes"),
    [
        ("[1, 2, 0]", (1, 2)),
        ("[1, 2, 4]", (1, 2)),  # a straddle is not the big blind
        ("[0, 2, 4]", (1, 2)),  # no small blind: half the big one
        ("[0, 0, 2]", (1, 2)),  # a button blind alone
    ],
)
def test_the_stakes_are_the_blinds_by_position(blinds: str, stakes: tuple[int, int]) -> None:
    from fpdb_3_legacy.phh_import import _Builder

    text = NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", f"blinds_or_straddles = {blinds}")
    builder = _Builder(document(text), mapping_for("NT"), None)
    gametype = builder._gametype(builder._per_player("blinds_or_straddles", 3))
    assert (gametype["sb"], gametype["bb"]) == stakes


# -- thirty-first review --------------------------------------------------------------


def test_a_fixed_limit_big_bet_other_than_twice_the_small_is_unsupported() -> None:
    error = refusal(stud_fourth("F7S", "9d", 5).replace("big_bet = 10", "big_bet = 12"))
    assert error.kind == UNSUPPORTED
    assert "bets of 5/12" in str(error)


def test_the_fixed_limit_small_bet_is_the_game_s_big_blind() -> None:
    """fpdb's fixed-limit game row has one size, and the small bet is it.

    A hold'em or draw table posts a big blind of its own, and it is the small bet -- the
    forty-third review refuses a table where it is not, rather than overwriting it here. A
    stud table has no blinds at all, so the small bet is the only thing that can give the
    game row its big blind.
    """
    from fpdb_3_legacy.phh_import import _Builder

    text = (
        FL_FOUR.format(last='"p3 cc"')
        .replace("blinds_or_straddles = [1, 2, 0, 0]", "blinds_or_straddles = [2, 4, 0, 0]")
        .replace("small_bet = 2", "small_bet = 4")
        .replace("big_bet = 4", "big_bet = 8")
    )
    builder = _Builder(document(text), mapping_for("FT"), None)
    gametype = builder._gametype(builder._per_player("blinds_or_straddles", 4))
    assert (gametype["sb"], gametype["bb"]) == (2, 4)

    stud = _Builder(document((FIXTURES / "stud_hi.phh").read_text(encoding="utf-8")), mapping_for("F7S"), None)
    gametype = stud._gametype(stud._per_player("blinds_or_straddles", 3))
    assert (gametype["sb"], gametype["bb"]) == (5, 5)


def test_a_draw_hand_is_shown_only_after_the_last_draw() -> None:
    runout = (FIXTURES / "triple_draw_all_in_runout.phh").read_text(encoding="utf-8")
    early = runout.replace('  "p1 cc",\n', '  "p1 cc",\n  "p1 sm 7h5c4d3s2c",\n', 1)
    assert "p1 shows or mucks before the showdown" in str(refusal(early))


# -- thirty-second review -------------------------------------------------------------


def test_time_is_a_local_time_of_day() -> None:
    error = refusal(SHOWDOWN + 'time = 2026-01-01T12:00:00Z\ntime_zone = "America/New_Yrok"\n')
    assert error.kind == MALFORMED
    assert "is not a local time of day" in str(error)
    assert "is not a local time of day" in str(refusal(SHOWDOWN + "time = 2026-01-01T12:00:00\n"))


def test_a_half_blind_finer_than_a_cent_is_unsupported() -> None:
    from fpdb_3_legacy.phh_import import _Builder

    text = NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [0, 0.01, 0]")
    builder = _Builder(document(text), mapping_for("NT"), None)
    with pytest.raises(PHHImportError) as raised:
        builder._gametype(builder._per_player("blinds_or_straddles", 3))
    assert raised.value.kind == UNSUPPORTED
    assert "a big blind of 0.01 has no small blind" in str(raised.value)


# -- thirty-third review --------------------------------------------------------------


def test_the_report_filters_offer_phh_players_heroes_first(imported) -> None:
    from fpdb_3_legacy.phh_import import phh_source_players

    _importer, _totals, connection = imported
    players = phh_source_players(connection.cursor(), "?")
    assert players[0] == "Alice"  # the file's _hero
    assert {"Phil Ivey", "Tom Dwan", "Bryce Yockey"} <= set(players)
    assert len(players) <= 50


def test_without_phh_hands_the_filters_offer_no_phh_player() -> None:
    from fpdb_3_legacy.phh_import import phh_source_players

    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE Sites (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    assert phh_source_players(connection.cursor(), "?") == []
    connection.execute("INSERT INTO Sites VALUES (150, 'Other', 'OT')")
    assert phh_source_players(connection.cursor(), "?") == []


def test_the_filters_list_the_phh_source_after_the_rooms() -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy.Filters import Filters

    rooms = SimpleNamespace(get_supported_sites=lambda: ["PokerStars"])
    assert Filters.filter_sites(SimpleNamespace(conf=rooms, siteid={"PokerStars": 32})) == ["PokerStars"]
    with_phh = SimpleNamespace(conf=rooms, siteid={"PokerStars": 32, "PHH": PHH_SITE_ID})
    assert Filters.filter_sites(with_phh) == ["PokerStars", "PHH"]


def test_a_currency_that_is_not_a_code_is_malformed() -> None:
    for value in ("true", "123"):
        assert "is not a string" in str(refusal(SHOWDOWN + f"currency = {value}\n"))
    for value in ('""', '"USDX"', '"usd"'):
        assert "is not an ISO 4217 code" in str(refusal(SHOWDOWN + f"currency = {value}\n"))
    assert build_hand(document(SHOWDOWN + 'currency = "USD"\n')).gametype["currency"] == "USD"
    assert build_hand(document(SHOWDOWN)).gametype["currency"] == "play"


# -- thirty-fifth review --------------------------------------------------------------

STUD_RUNOUT = """
variant = "F7S"
antes = [0, 0]
bring_in = 1
small_bet = 2
big_bet = 4
starting_stacks = [50, 2]
actions = [
  "d dh p1 AhKh2c",
  "d dh p2 ????9c",
  "p1 pb",
  "p2 cbr 2",
  "p1 cc",
  "p2 sm QsQd9c",
  "d dh p1 3c",
  "d dh p2 Qc",
  "d dh p1 4d",
  "d dh p2 8s",
  "d dh p1 6h",
  "d dh p2 7s",
  "d dh p1 Jd",
  "d dh p2 2h",
  "p1 sm -",
]
winnings = [0, 4]
"""


def test_a_stud_card_shown_in_an_all_in_runout_is_kept() -> None:
    hand = build_hand(document(STUD_RUNOUT))
    assert "p2" in hand.shown
    assert hand.join_holecards("p2", asList=True) == ["Qs", "Qd", "9c", "Qc", "8s", "7s", "2h"]


def test_an_iso_4217_code_is_one_the_standard_lists() -> None:
    assert "is not an ISO 4217 code" in str(refusal(SHOWDOWN + 'currency = "ZZZ"\n'))
    for code in ("USD", "EUR", "GBP", "FRF"):  # in use, or withdrawn (older datasets)
        assert build_hand(document(SHOWDOWN + f'currency = "{code}"\n')).gametype["currency"] == code


def test_a_seat_may_not_be_a_boolean() -> None:
    assert "seat True is not a seat number" in str(refusal(SHOWDOWN + "seats = [true, 2]\n"))


# -- thirty-sixth review --------------------------------------------------------------


def test_a_name_longer_than_32_characters_is_unsupported() -> None:
    """``Players.name`` holds 32 characters: a longer name is refused, one of 32 is not."""
    long = "a" * 32
    error = refusal(SHOWDOWN + f'players = ["{long}x", "b"]\n')
    assert error.kind == UNSUPPORTED
    assert "longer than the 32 characters" in str(error)
    assert build_hand(document(SHOWDOWN + f'players = ["{long}", "b"]\n')) is not None


@pytest.mark.parametrize(
    ("change", "what"),
    [
        (("min_bet = 2", 'min_bet = "2"'), "min_bet"),
        (("starting_stacks = [100, 100]", 'starting_stacks = ["100", 100]'), "starting_stacks[0]"),
        (("winnings = [4, 0]", 'winnings = ["4", 0]'), "winnings[0]"),
    ],
)
def test_amounts_written_as_strings_are_malformed(change: tuple[str, str], what: str) -> None:
    """Every array is checked entry by entry, so each one names its own index.

    A stack used to be named by its player (``starting stack of p1``), which read better, but
    that name came from the reader -- and an array whose reader a branch skips
    (``finishing_stacks`` beside ``winnings``) or never runs (``time_banks``) was checked
    nowhere. The check belongs to the field table, so all six arrays report the same way.
    """
    error = refusal(SHOWDOWN.replace(*change))
    assert error.kind == MALFORMED
    assert f"{what} is not a number" in str(error)


# -- thirty-seventh review ------------------------------------------------------------

STUD_CALLERS = """
variant = "F7S"
antes = [0, 0, 0]
bring_in = 1
small_bet = 4
big_bet = 8
starting_stacks = [100, 100, 100]
actions = ["d dh p1 ????2c", "d dh p2 ????8c", "d dh p3 ????9c", "p1 pb", "p2 cc", "p3 cbr 4", "p1 cc", "p2 cbr 8"]
"""


def test_a_completion_reopens_the_betting_to_who_called_the_bring_in() -> None:
    """PokerKit 0.7.6 accepts p2's raise: the completion is the street's first full bet."""
    assert refusal(STUD_CALLERS).kind == PARTIAL


# -- thirty-eighth review -------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("table = true", "table must be a string or an integer"),
        ("table = [1]", "table must be a string or an integer"),
        ("table = 1.5", "table must be a string or an integer"),
        ("event = true", "event True is not a string"),
        ("event = 3", "event 3 is not a string"),
    ],
)
def test_a_table_or_event_of_the_wrong_type_is_malformed(line: str, reason: str) -> None:
    """PHH gives ``table`` a string or an integer and ``event`` a string: anything else is
    metadata fpdb would otherwise store as its ``str()`` -- ``table = true`` as the table
    "True", splitting the imported hands into bogus table groups."""
    error = refusal(SHOWDOWN + line + "\n")
    assert error.kind == MALFORMED
    assert reason in str(error)


def test_the_table_label_is_the_table_then_the_event_then_the_file_name() -> None:
    assert build_hand(document(SHOWDOWN + 'table = "T1"\n')).tablename == "T1"
    # Zero is a table: only an absent one falls back.
    assert build_hand(document(SHOWDOWN + "table = 0\n")).tablename == "0"
    assert build_hand(document(SHOWDOWN + 'event = "Main Event"\n')).tablename == "Main Event"
    assert build_hand(document(SHOWDOWN)).tablename == "test"


# -- the accepted subset of PHH -------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        # A field fpdb reads for this game.
        ('ante_trimming_status = "yes"', "ante_trimming_status 'yes' is not a boolean"),
        ("ante_trimming_status = 1", "ante_trimming_status 1 is not a boolean"),
        ("city = 1", "city 1 is not a string"),
        ('time_limit = "30"', "time_limit is not a number"),
        # A field fpdb reads for another game, or never: still PHH's, so still checked.
        ('bring_in = "1"', "bring_in is not a number"),
        ("small_bet = true", "small_bet is not a number"),
        ("finishing_stacks = 5", "finishing_stacks must be a list"),
        ("author = 1", "author 1 is not a string"),
        ('level = "1"', "level '1' is not an integer"),
        ("time_banks = 5", "time_banks must be a list"),
        ("currency_symbol = 1", "currency_symbol 1 is not a string"),
        ("hand = true", "hand must be a string or an integer"),
        ('url = 1', "url 1 is not a string"),
        ("postal_code = 1", "postal_code 1 is not a string"),
    ],
)
def test_a_field_of_the_wrong_type_is_refused_whether_or_not_fpdb_reads_it(line: str, reason: str) -> None:
    """The boundary is the specification's field table, not the fields fpdb happens to use.

    A value of another type is a violation PHH asks a parser to report; storing it as its
    ``str()`` -- or reading a truthy string as a boolean -- would be a plausible but wrong
    value kept for good. A field PHH does not define is its user-defined space, left alone.
    """
    error = refusal(SHOWDOWN + line + "\n")
    assert error.kind == MALFORMED
    assert reason in str(error)


def test_a_user_defined_field_is_left_alone() -> None:
    hand = build_hand(document(SHOWDOWN + '_hero = "p1"\n_notes = [1, 2]\n'))
    assert hand.hero == "p1"


def test_an_ante_marked_untrimmed_is_not_read_as_a_truthy_string() -> None:
    """``bool("no")`` is true: the hand would have been refused as trimmed, or read as trimmed."""
    assert refusal(ANTES_HAND + 'ante_trimming_status = "no"\n').kind == MALFORMED
    assert refusal(ANTES_HAND + "ante_trimming_status = false\n").kind == PARTIAL
    assert refusal(ANTES_HAND + "ante_trimming_status = true\n").kind == UNSUPPORTED


# -- thirty-ninth review --------------------------------------------------------------


def test_names_differing_only_in_case_are_two_players() -> None:
    """``Players.name`` compares byte for byte (#417), so the two seats are two players.

    Before the column had an explicit binary collation, MySQL compared names with the
    server's default, which ignores case: ``Alice`` and ``alice`` left *one* row in
    ``Players`` and ``insertPlayer()`` handed the second seat the first player's id, their
    actions and results one player's for good. The collation is now binary on every backend.
    """
    assert names_of(build_hand(document(heads_up(["Alice", "alice"])))) == ["Alice", "alice"]


def test_names_differing_only_in_accents_are_two_players() -> None:
    """The default collation was accent-insensitive too: ``José`` and ``Jose`` were one row."""
    assert names_of(build_hand(document(heads_up(["José", "Jose"])))) == ["José", "Jose"]


def test_names_differing_by_a_ligature_or_a_stroke_are_two_players() -> None:
    """``Ø`` is ``o`` to a UCA collation and ``Æ`` is ``ae``; a binary one reads both."""
    for left, right in [("Łukasz", "Lukasz"), ("Ø", "O"), ("Æ", "AE"), ("ﬁn", "fin")]:
        assert names_of(build_hand(document(heads_up([left, right])))) == [left, right]


def test_the_whole_name_is_compared_to_its_full_length() -> None:
    """Two 32-character names that differ only in the last letter's accent are two players.

    The fold used to read every character of them, not the first 32 alone: names that long
    were refused before the storage stopped needing it.
    """
    head = "b" * 31
    left, right = head + "é", head + "e"
    assert names_of(build_hand(document(heads_up([left, right])))) == [left, right]


# -- fortieth review ------------------------------------------------------------------


def test_an_undated_hand_is_still_held_to_its_zone_and_abbreviation() -> None:
    """Leaving out the date is not a way past the checks a dated hand meets.

    The abbreviation is only readable against a wall time, and an undated hand has none: it is
    read against the epoch, which is the time the hand is stored at. The stored value itself
    does not move -- an undated hand starts at the epoch, not at the epoch shifted by its zone.
    """
    error = refusal(SHOWDOWN + 'time_zone_abbreviation = "EDT"\n')
    assert error.kind == UNSUPPORTED
    assert "without a time_zone cannot be converted" in str(error)

    error = refusal(SHOWDOWN + 'time_zone = "America/New_York"\ntime_zone_abbreviation = "PST"\n')
    assert error.kind == MALFORMED
    assert "is not America/New_York's abbreviation" in str(error)

    # The zone the abbreviation belongs to, and a zone on its own, still import at the epoch.
    assert build_hand(document(SHOWDOWN + 'time_zone = "America/New_York"\n')).startTime == datetime.datetime(1970, 1, 1)
    kept = SHOWDOWN + 'time_zone = "America/New_York"\ntime_zone_abbreviation = "EST"\n'
    assert build_hand(document(kept)).startTime == datetime.datetime(1970, 1, 1)


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (SHOWDOWN.replace("antes = [0, 0]", 'antes = ["0", "0"]'), "antes"),
        (SHOWDOWN.replace("blinds_or_straddles = [1, 2]", 'blinds_or_straddles = ["1", "2"]'), "blinds_or_straddles"),
        (SHOWDOWN.replace("starting_stacks = [100, 100]", 'starting_stacks = ["100", 100]'), "starting_stacks"),
        (SHOWDOWN.replace("winnings = [4, 0]", 'winnings = ["4", 0]'), "winnings"),
        (SHOWDOWN + 'finishing_stacks = ["4", "0"]\n', "finishing_stacks"),
        (SHOWDOWN + 'time_banks = ["30", "30"]\n', "time_banks"),
    ],
)
def test_every_numeric_array_is_checked_entry_by_entry(text: str, field: str) -> None:
    """Checked whether or not the hand goes on to read the array.

    ``time_banks`` is read by nothing, and ``finishing_stacks`` is skipped whenever ``winnings``
    is also given: checking an array where its entries are read left those two accepting a
    string entry, and the malformed hand was stored. The field table checks all six, in one
    place, so a reader that never runs cannot be the reason an entry goes unchecked.
    """
    error = refusal(text)
    assert error.kind == MALFORMED
    assert f"{field}[0] is not a number" in str(error)


def test_an_unknown_starting_stack_is_still_unsupported_rather_than_malformed() -> None:
    """``inf`` is how PHH writes a stack it does not know: an unknown stack, not a type error."""
    error = refusal(SHOWDOWN.replace("starting_stacks = [100, 100]", "starting_stacks = [inf, 100]"))
    assert error.kind == UNSUPPORTED
    assert "a starting stack is unknown" in str(error)


# -- forty-first review ---------------------------------------------------------------


@pytest.mark.parametrize(
    "literal",
    ["true", "1", "1.5", '["NT"]', '{ name = "NT" }', "1970-01-01"],
)
def test_a_variant_that_is_not_a_string_is_malformed_not_unsupported(literal: str) -> None:
    """PHH gives ``variant`` as a string, so a value of another type is a broken hand.

    ``mapping_for`` looked the variant up through ``str()``, which turned every other type
    into a *variant fpdb has no mapping for*: the hand was counted as skipped, and
    ``importFiles`` files a file under ``failed=errors > 0`` -- the malformed count -- so a
    file whose only defect was ``variant = true`` was archived with the imported ones. A
    variant that is not a string is a specification violation and is counted as an error.
    """
    error = refusal(SHOWDOWN.replace('variant = "NT"', f"variant = {literal}"))
    assert error.kind == MALFORMED
    assert "is not a string" in str(error)


def test_a_variant_string_with_no_mapping_is_still_unsupported() -> None:
    """The control: the type check must not swallow the variants fpdb genuinely cannot hold.

    ``build_hand`` calls ``mapping_for`` outside its catch-all, so this is the path a string
    variant takes: it must still reach the mapping table and be refused there.
    """
    error = refusal(SHOWDOWN.replace('variant = "NT"', 'variant = "ZZ"'))
    assert error.kind == UNSUPPORTED
    assert "has no fpdb mapping" in str(error)


def test_a_file_whose_only_defect_is_its_variant_is_a_file_with_errors(importer, fresh_db, tmp_path) -> None:
    """The end of the chain: malformed is what sends the file to the failed directory.

    Counted as unsupported, the hand left the file looking clean and the file was archived
    with the imports. The two counts are what the caller acts on, so they are what is read.
    """
    broken = tmp_path / "broken.phh"
    broken.write_text(SHOWDOWN.replace('variant = "NT"', "variant = true"), encoding="utf-8")
    assert importer.addImportFile(str(broken))

    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()

    assert (stored, duplicates, partial, skipped, errors) == (0, 0, 0, 0, 1)
    summary = importer.phh_summary()
    assert summary is not None
    assert (summary.unsupported, summary.malformed) == (0, 1)
    assert any("is not a string" in error for error in summary.errors)


@pytest.mark.parametrize("literal", ['["Alice"]', '{ name = "Alice" }', "[1, 2]", "3", '"nobody"'])
def test_a_hero_that_cannot_name_a_seat_leaves_the_hand_without_one(literal: str) -> None:
    """``_hero`` is a name, and a name is a string: anything else names no seat.

    The membership test hashed the value, so a list or an inline table raised ``TypeError``
    and ``build_hand``'s catch-all reported a malformed hand. The field is one PHH does not
    define, which fpdb reads only to name a seat: a ``_hero`` that is not one of the players
    -- whatever its type -- means the hand has none, as it always has for a hashable value.
    """
    hand = build_hand(document(SHOWDOWN + f"_hero = {literal}\n"))
    assert hand.hero == ""


# -- forty-second review --------------------------------------------------------------


@pytest.mark.parametrize("pad", [" ", "  "])
def test_names_that_differ_only_in_trailing_spaces_are_unsupported(pad: str) -> None:
    """``utf8mb4_bin`` is PAD SPACE, so ``Alice`` and ``Alice `` are one row on MySQL.

    Measured on the real table and its unique index: inserting ``Alice`` then ``Alice `` runs
    ``ON DUPLICATE KEY UPDATE ... id=LAST_INSERT_ID(id)`` into the duplicate, leaving one row
    and handing back id 1 both times -- both seats one player. ``utf8mb4_0900_bin`` would keep
    them apart, but MariaDB has no equivalent, so the pair is refused rather than merged on the
    one backend that would. A space at the *front* is compared everywhere and still imports.
    """
    assert refusal(heads_up(["Alice", "Alice" + pad])).kind == UNSUPPORTED
    assert names_of(build_hand(document(heads_up(["Alice", " Alice"])))) == ["Alice", " Alice"]


@pytest.mark.parametrize("pad", ["\u00a0", "\u3000", "\t"])
def test_the_only_pad_character_is_the_ascii_space(pad: str) -> None:
    """The other characters a UCA collation reads past are compared by a binary one.

    Measured on the table: ``utf8mb4_bin`` merges ``Alice`` and ``Alice `` but keeps a
    trailing U+00A0, U+3000 or tab as a name of its own.
    """
    assert names_of(build_hand(document(heads_up(["Alice", "Alice" + pad])))) == [
        "Alice",
        "Alice" + pad,
    ]


@pytest.mark.parametrize("hidden", ["\u200b", "\u00ad", "\u200d", "\u0640", "\u0903"])
def test_names_that_differ_by_an_invisible_character_are_two_players(hidden: str) -> None:
    """A zero-width space, a soft hyphen, a joiner, a tatweel, a visarga: all are compared.

    The importer used to drop them, so the two seats met. A binary collation reads every
    codepoint as itself, and the two names are two players.
    """
    left, right = "Alice", "Ali" + hidden + "ce"
    assert names_of(build_hand(document(heads_up([left, right])))) == [left, right]


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (SHOWDOWN + "small_bet = 2\n", "small_bet"),
        (SHOWDOWN + "big_bet = 4\n", "big_bet"),
        (SHOWDOWN + "bring_in = 2\n", "bring_in"),
        (STUD_HILO + "min_bet = 4\n", "min_bet"),
        (STUD_HILO + "blinds_or_straddles = [0, 0, 0, 0, 0, 0]\n", "blinds_or_straddles"),
        (FIXTURES.joinpath("single_draw.phh").read_text(encoding="utf-8") + "bring_in = 2\n", "bring_in"),
    ],
)
def test_a_field_the_variant_must_not_carry_is_refused(text: str, field: str) -> None:
    """PHH says what a variant cannot have as clearly as what it needs.

    "The usage of bring-ins is mutually exclusive with blinds or straddles. In other words,
    both must never be defined together"; ``min_bet`` "must never be specified in fixed-limit
    games"; and ``small_bet`` and ``big_bet`` are "not a feature of pot-limit or no-limit
    games". Nothing reads the field the variant cannot have -- stud ignores blinds, the other
    families ignore ``min_bet`` and the bet sizes -- so the hand used to import with it
    dropped in silence, and a file that says two contradictory things about its own stakes was
    counted as a clean import.
    """
    error = refusal(text)
    assert error.kind == MALFORMED
    assert f"{field} is not a field of" in str(error)


def test_the_sizing_fields_the_variant_does_allow_still_import() -> None:
    """The control: the family's own sizing fields, and the fixtures that carry them."""
    assert build_hand(document(SHOWDOWN)) is not None  # min_bet, no limit
    assert build_hand(document(STUD_HILO)) is not None  # bring_in with small_bet and big_bet


# -- forty-third review ---------------------------------------------------------------

#: A showdown where p1's cards were never named, so every card p1 can show is unknown.
UNNAMED_SHOWDOWN = """
variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [100, 100]
actions = [
  "d dh p1 ????",
  "d dh p2 QhQd",
  "p2 cc",
  "p1 cc",
  "d db Kc3d4h",
  "p1 cc",
  "p2 cc",
  "d db 9s",
  "p1 cc",
  "p2 cc",
  "d db Jc",
  "p1 cc",
  "p2 cc",
  "p1 sm ????",
  "p2 sm -",
]
winnings = [0, 0]
finishing_stacks = [100, 100]
"""


@pytest.mark.parametrize("show", ["p1 sm ????", "p1 sm -"])
def test_a_player_who_shows_only_unknown_cards_has_shown(show: str) -> None:
    """PHH tells a show from the cardless ``sm``, and the cards are not what says so.

    ``p1 sm ????`` names four unknown cards and ``p1 sm -`` the cards the deal already named,
    which are unknown too: both say p1 showed. fpdb keeps the fact in ``shown``, which
    ``DerivedStats`` reads as ``showed`` for the report columns and the showdown section is
    written from, so a player left out of it is not a player without cards but a player
    without a show. The hand is accepted either way, and nothing is invented for the cards.
    """
    hand = build_hand(document(UNNAMED_SHOWDOWN.replace("p1 sm ????", show)))
    assert hand.shown == {"p1", "p2"}
    assert hand.mucked == set()
    assert hand.holecards["PREFLOP"].get("p1") is None


def test_a_show_that_names_no_card_leaves_the_muck_and_the_named_show_alone() -> None:
    """The controls: what the fix above must not change.

    ``sm`` alone is PHH's muck -- the cards go back unseen, and the claim to the pot with
    them -- so that player is still a mucker and not a shower. A show that does name cards
    records them, on the player and on the hand.
    """
    mucked = build_hand(document(UNNAMED_SHOWDOWN.replace('"p1 sm ????"', '"p1 sm"')))
    assert mucked.shown == {"p2"}
    assert mucked.mucked == {"p1"}

    named = build_hand(document(UNNAMED_SHOWDOWN.replace('"p1 sm ????"', '"p1 sm AsKs"')))
    assert named.shown == {"p1", "p2"}
    assert named.holecards["PREFLOP"]["p1"] == [[], ["As", "Ks"]]


def test_a_hand_whose_show_names_no_card_is_still_written_back() -> None:
    """Showing and holding the cards are two things, and the hand writer tells them apart.

    ``writeHand`` prints the cards of every player who showed and was not dealt to whenever
    the hand has no hero -- the usual PHH case, since ``_hero`` is optional -- so it reads
    ``holecards`` for players it has only seen in ``shown``. A player who showed with every
    card unknown has none on file and is skipped there rather than raising; the same state
    already arises in the draw games, where a known show is recorded on the street it was
    made on and never on the deal.
    """
    hand = build_hand(document(UNNAMED_SHOWDOWN))
    hand.rake = 0  # the import pipeline sets it before a hand is ever written back
    written = StringIO()
    hand.writeHand(written)
    assert "Dealt to p2 [Qh Qd]" in written.getvalue()
    assert "Dealt to p1" not in written.getvalue()


FL_BLINDS = """
variant = "FT"
antes = [0, 0, 0]
blinds_or_straddles = {blinds}
small_bet = {small_bet}
big_bet = {big_bet}
starting_stacks = [100, 100, 100]
actions = ["d dh p1 ????", "d dh p2 ????", "d dh p3 ????", "p3 cbr {raise_to}", "p1 f", "p2 f"]
"""


@pytest.mark.parametrize(
    ("blinds", "small_bet", "raise_to"),
    [
        ("[1, 3, 0]", 2, 5),  # a 3-chip big blind against 2/4 betting
        ("[1, 4, 0]", 2, 6),  # a 4-chip big blind against 2/4 betting
        ("[1, 2, 0]", 4, 6),  # a 2-chip big blind against 4/8 betting
    ],
)
def test_a_fixed_limit_big_blind_that_is_not_the_small_bet_is_unsupported(
    blinds: str, small_bet: int, raise_to: int
) -> None:
    """fpdb's game row has one fixed-limit size and the hand's blind is the other.

    ``_gametype`` takes the big blind of a fixed-limit game from ``small_bet`` -- fpdb stores
    the small bet as the big blind and the big bet as twice it -- while ``_post`` records the
    blind the hand itself posts. When the two disagree the hand is filed under one game row
    and posts another's blind: measured, ``[1, 3, 0]`` with ``small_bet = 2`` gave a gametype
    of 1/2 while the actions held a 3-chip big blind, so the hand would be grouped with the
    1/2 tables and every blind-normalised statistic read against the wrong stakes.
    """
    text = FL_BLINDS.format(blinds=blinds, small_bet=small_bet, big_bet=2 * small_bet, raise_to=raise_to)
    error = refusal(text)
    assert error.kind == UNSUPPORTED
    assert "is not the fixed-limit small bet" in str(error)


@pytest.mark.parametrize(("blinds", "small_bet", "raise_to"), [("[1, 2, 0]", 2, 4), ("[2, 4, 0]", 4, 8)])
def test_a_fixed_limit_big_blind_that_is_the_small_bet_still_imports(
    blinds: str, small_bet: int, raise_to: int
) -> None:
    """The control, and the fixture the importer was written against."""
    text = FL_BLINDS.format(blinds=blinds, small_bet=small_bet, big_bet=2 * small_bet, raise_to=raise_to)
    assert build_hand(document(text)).gametype["bb"] == small_bet
    assert build_hand(document((FIXTURES / "fl_holdem.phh").read_text(encoding="utf-8"))) is not None


# -- forty-fourth review --------------------------------------------------------------

#: Two seats where the file names only the second: the first is unnamed, so fpdb names it p1.
PARTLY_NAMED = """
variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [100, 100]
actions = [
  "d dh p1 ????",
  "d dh p2 ????",
  "p2 cc",
  "p1 cc",
  "d db Kc3d4h",
  "p1 cc",
  "p2 cc",
  "d db 9s",
  "p1 cc",
  "p2 cc",
  "d db Jc",
  "p1 cc",
  "p2 cc",
]
winnings = [0, 0]
finishing_stacks = [100, 100]
"""


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (["", "P1"], ["p1", "P1"]),  # P1 is a name of its own under a binary collation
        (["", "p1 "], ["p1#2", "p1 "]),  # the space is still a pad character, though
        (["", "", "P1"], ["p1", "p2", "P1"]),  # and the name is at another seat
        (["", "p1"], ["p1#2", "p1"]),  # the exact collision, as before
        (["p2", "", ""], ["p2", "p2#2", "p3"]),  # and that one, at another seat
        (["", "P2"], ["p1", "P2"]),  # the controls: nothing meets p1 here
        (["", "p1\u00a0"], ["p1", "p1\u00a0"]),  # not even a non-breaking space
        (["", "p1#2"], ["p1", "p1#2"]),
        (["", ""], ["p1", "p2"]),
    ],
)
def test_an_unnamed_player_steps_around_a_name_the_index_would_take(
    given: list[str], expected: list[str]
) -> None:
    """The generated name has to clear the bar ``_seats`` sets for the file's own names.

    An unnamed player is called ``pN``. The index files a generated ``p1`` and a supplied
    ``p1`` as one row, so the fallback steps aside to ``p1#2`` exactly as it always has; a
    supplied ``p1 `` is still ``p1`` to MySQL's PAD SPACE binary collation, and steps it aside
    too. ``P1`` and ``p1\u00a0`` are names of their own now (#417) and leave it alone.
    """
    from fpdb_3_legacy.phh_import import _player_names

    assert _player_names(given) == expected


@pytest.mark.parametrize("supplied", ["p1 ", "p1  "])
def test_a_hand_whose_unnamed_player_meets_a_named_one_on_a_space_still_imports(supplied: str) -> None:
    """Measured before the fix: this hand was refused ``unsupported`` for the name fpdb made up.

    The same hand with the name written ``p1`` imported -- it was only the collision between
    a supplied name and the generated one that was not stepped around. A supplied ``p1 `` is
    the same name to the one binary collation that pads with a space, so it steps aside too.
    """
    text = PARTLY_NAMED.replace('variant = "NT"', f'variant = "NT"\nplayers = ["", "{supplied}"]')
    hand = build_hand(document(text))
    assert names_of(hand) == ["p1#2", supplied]


@pytest.mark.parametrize("supplied", ["P2", "P1", "p1\u00a0", "p1\u200b", "x", "p1#2", "p3"])
def test_a_supplied_name_the_binary_collation_keeps_apart_leaves_the_fallback_alone(supplied: str) -> None:
    """The controls: a name the database keeps apart from ``p1`` does not move it."""
    text = PARTLY_NAMED.replace('variant = "NT"', f'variant = "NT"\nplayers = ["", "{supplied}"]')
    hand = build_hand(document(text))
    assert names_of(hand) == ["p1", supplied]


# -- forty-fifth review ---------------------------------------------------------------

#: The three-player hand above with one per-player array of the wrong length. PHH gives each
#: of these "length equal to the number of players", so three seats and two (or four) entries
#: is a broken hand, not a hand fpdb cannot hold.
WRONG_LENGTH = [
    (NT_HAND.replace("antes = [0, 0, 0]", "antes = [0]"), "antes"),
    (NT_HAND.replace("antes = [0, 0, 0]", "antes = [0, 0, 0, 0]"), "antes"),
    (NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [1, 2]"), "blinds_or_straddles"),
    (NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [1, 2, 0, 0]"), "blinds_or_straddles"),
    (NT_HAND + "winnings = [0, 0]\n", "winnings"),
    (NT_HAND + "winnings = [0, 0, 5, 0]\n", "winnings"),
    # Nothing reads time_banks, and _collected reads finishing_stacks only when winnings is
    # absent: the two arrays whose reader does not run, each short and each long.
    (NT_HAND + "time_banks = [30]\n", "time_banks"),
    (NT_HAND + "time_banks = [30, 30, 30, 30]\n", "time_banks"),
    (NT_HAND + "finishing_stacks = [100]\n", "finishing_stacks"),
    (NT_HAND + "finishing_stacks = [100, 100, 100, 100]\n", "finishing_stacks"),
    (NT_HAND + "winnings = [0, 0, 5]\nfinishing_stacks = [100]\n", "finishing_stacks"),
    (NT_HAND + "winnings = [0, 0, 5]\nfinishing_stacks = [100, 100, 100, 100]\n", "finishing_stacks"),
]


@pytest.mark.parametrize(("text", "field"), WRONG_LENGTH)
def test_a_per_player_array_of_the_wrong_length_is_malformed(text: str, field: str) -> None:
    """Every per-player array holds one entry per player, whether the importer reads it or not.

    Measured before the fix, in this three-player hand: ``time_banks = [30]`` imported -- the
    array is read by nothing, so nothing compared its length -- and so did a ``finishing_stacks``
    of the wrong length whenever ``winnings`` was also given, since ``_collected`` reads the
    first and skips the second. Both were stored with a zero malformed count, and
    ``importFiles`` files a file under ``failed=errors > 0``, so they were archived with the
    hands that imported.
    """
    error = refusal(text)
    assert error.kind == MALFORMED
    assert f"{field} must have one value per player" in str(error)


def test_the_per_player_arrays_of_the_right_length_still_import() -> None:
    """The controls: the same arrays, one entry per player, still import.

    ``time_banks`` is a time, not an amount -- PHH allows a fractional one and fpdb stores no
    time bank -- so the new rule is a length rule and does not put the field through the
    hundredth every amount is held to.
    """
    assert build_hand(document(NT_HAND)) is not None
    assert build_hand(document(NT_HAND + "time_banks = [30, 30, 30]\n")) is not None
    assert build_hand(document(NT_HAND + "time_banks = [30.5, 30.5, 30.5]\n")) is not None
    assert build_hand(document(NT_HAND + "winnings = [0, 0, 5]\nfinishing_stacks = [100, 100, 100]\n")) is not None


# -- forty-sixth review ---------------------------------------------------------------

#: A table that posts a small blind and no big blind: the array's first entry only. PHH's
#: blinds are "two positive values in the first two indices", and the first is the small one.
LONE_SMALL_BLIND = [
    NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [2, 0, 0]"),
    SHOWDOWN.replace("blinds_or_straddles = [1, 2]", "blinds_or_straddles = [2, 0]"),
]


@pytest.mark.parametrize("text", LONE_SMALL_BLIND)
def test_a_small_blind_with_no_big_blind_is_unsupported(text: str) -> None:
    """A lone first entry says nothing about the big blind, so the hand is refused, not filed.

    Measured before the fix: ``blinds_or_straddles = [2, 0, 0]`` imported, ``_stakes`` reading
    the lone blind as the big one (stakes 1/2) while ``_post`` labelled the same post a *small
    blind* of 2 -- so the hand carried a small blind equal to its game row's big blind, and
    every blind-normalised statistic read it against the wrong size. Heads-up, ``[2, 0]`` had
    the same mismatch. The first position is the small blind, so a big blind has to be given
    for the game row to have one.
    """
    error = refusal(text)

    assert error.kind == UNSUPPORTED
    assert "a small blind of 2 and no big blind" in str(error)


BLIND_LAYOUTS = [
    (NT_HAND, 3, (1, 2)),  # the small and the big blind
    (NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [0, 2, 0]"), 3, (1, 2)),
    (NT_HAND.replace("blinds_or_straddles = [1, 2, 0]", "blinds_or_straddles = [0, 0, 2]"), 3, (1, 2)),
    (SHOWDOWN, 2, (1, 2)),  # heads-up: the first two entries are assigned in reverse
    (SHOWDOWN.replace("blinds_or_straddles = [1, 2]", "blinds_or_straddles = [0, 2]"), 2, (1, 2)),
]


@pytest.mark.parametrize(("text", "count", "stakes"), BLIND_LAYOUTS)
def test_the_blind_layouts_that_name_a_big_blind_still_give_the_game_its_stakes(
    text: str, count: int, stakes: tuple[int, int]
) -> None:
    """The controls: the layouts around the refusal -- no small blind, a button blind, heads-up."""
    from fpdb_3_legacy.phh_import import _Builder

    builder = _Builder(document(text), mapping_for("NT"), None)
    gametype = builder._gametype(builder._per_player("blinds_or_straddles", count))

    assert (gametype["sb"], gametype["bb"]) == stakes


def test_the_big_blind_the_hand_posts_is_the_game_row_s_big_blind() -> None:
    """The invariant the lone-small-blind layout broke: the post and the game row agree."""
    hand = build_hand(document(NT_HAND))

    posted = [action[2] for action in hand.actions["BLINDSANTES"] if action[1] == "big blind"]
    assert posted == [hand.gametype["bb"]]


def test_a_header_inside_a_value_that_closed_is_not_a_table(tmp_path) -> None:
    """A value that closed swallowed nothing, so the hand that holds it is not cut at it.

    Measured before the fix: this file -- a hand whose multiline note holds ``[inside]`` and
    whose ``variant`` is given twice -- came back as two malformed hands. The note had closed,
    but its header-looking line stayed a suspect, and the unrelated TOML error sent the
    recovery through it, so both the discovered and the malformed counts were one hand too
    high and the first error named a string that was never left open.
    """
    path = tmp_path / "hands.phhs"
    hand = SHOWDOWN.lstrip("\n").replace('variant = "NT"\n', 'variant = "NT"\nnote = """\n[inside]\n"""\n', 1)
    path.write_text("[1]\n" + hand + 'variant = "NT"\n', encoding="utf-8")

    items = list(iter_documents(path))

    assert len(items) == 1
    assert isinstance(items[0], PHHImportError)
    assert items[0].kind == MALFORMED
    assert "Cannot overwrite a value" in str(items[0])


def test_a_header_inside_a_closed_value_is_just_text(tmp_path) -> None:
    """The control: the same note, and no unrelated error -- one hand, and it imports."""
    path = tmp_path / "hands.phhs"
    hand = SHOWDOWN.lstrip("\n").replace('variant = "NT"\n', 'variant = "NT"\nnote = """\n[inside]\n"""\n', 1)
    path.write_text("[1]\n" + hand, encoding="utf-8")

    items = list(iter_documents(path))

    assert [item.label for item in items] == ["1"]
    assert build_hand(items[0]) is not None


# -- forty-seventh review -------------------------------------------------------------


def test_a_draw_showdown_is_recorded_on_the_last_draw_not_on_the_deal() -> None:
    """The shown holding goes on the final draw street; the deal keeps the starting hands.

    Measured: ``DrawHand.addShownCards`` takes the last street that carries an action, and an
    all-in runout still records one on every draw -- ``stands pat`` or ``discards`` -- so here
    the target is DRAWTHREE and not DEAL. p1 stands pat throughout, so his DRAWTHREE entry can
    only come from the showdown; p2's is the merged holding (the four he kept and the ``7d`` he
    drew), while his DEAL entry still holds the five he was dealt. The replacement streets are
    untouched, and the deal is not overwritten.
    """
    hand = build_hand(next(iter_documents(FIXTURES / "triple_draw_all_in_runout.phh")))

    assert [street for street in hand.allStreets if hand.actions.get(street)][-1] == "DRAWTHREE"
    assert hand.holecards["DEAL"]["p1"] == [[], ["7h", "5c", "4d", "3s", "2c"]]
    assert hand.holecards["DEAL"]["p2"] == [[], ["9s", "8h", "6c", "3d", "2h"]]
    assert hand.holecards["DRAWTHREE"]["p1"] == [[], ["7h", "5c", "4d", "3s", "2c"]]
    assert hand.holecards["DRAWTHREE"]["p2"] == [[], ["8h", "6c", "3d", "2h", "7d"]]


def test_the_control_a_normal_draw_also_shows_on_its_last_draw() -> None:
    """The control: betting on the draws changes nothing -- the last draw street is still it."""
    hand = build_hand(next(iter_documents(FIXTURES / "triple_draw_yockey_arieh.phh")))

    assert [street for street in hand.allStreets if hand.actions.get(street)][-1] == "DRAWTHREE"
    assert hand.holecards["DEAL"]["Josh Arieh"] == [[], ["As", "Qs", "6s", "5c", "3c"]]
    assert hand.holecards["DRAWTHREE"]["Josh Arieh"] == [[], ["5c", "3c", "2h", "4d", "7c"]]


# -- forty-eighth review --------------------------------------------------------------

#: 4/8 stud, third street: a bring-in of 1, a call of 1, then two all-ins short of the small
#: bet -- 2 and 3. The first is the street's completion (the bring-in is forced, so it is the
#: street's first bet); the second is a short all-in raise over it.
STUD_ALL_IN_COMPLETION = """
variant = "F7S"
antes = [0, 0, 0, 0]
bring_in = 1
small_bet = 4
big_bet = 8
starting_stacks = [100, 100, 2, 3]
actions = [
  "d dh p1 ????2c",
  "d dh p2 ????8c",
  "d dh p3 ????9c",
  "d dh p4 ????Tc",
  "p1 pb",
  "p2 cc",
  "p3 cbr 2",
  "p4 cbr 3",
  "p1 cc",
  {last}
]
"""

#: The same street with the completion reaching the small bet (4) and a short all-in raise
#: over it (5): p3, who completed, has already bet and may not raise again.
STUD_SHORT_ALL_IN_RAISE = STUD_ALL_IN_COMPLETION.replace(
    "starting_stacks = [100, 100, 2, 3]", "starting_stacks = [100, 100, 100, 5]"
).replace('"p3 cbr 2",\n  "p4 cbr 3",', '"p3 cbr 4",\n  "p4 cbr 5",')


def test_an_all_in_completion_short_of_the_small_bet_reopens_for_the_bring_in_caller() -> None:
    """p2, who only called the forced bring-in, may raise over p3's all-in completion.

    PokerKit 0.7.6 applies p2's raise to 7 here. The bring-in is forced, so it does not set the
    street's yardstick for a full wager: that yardstick is 0 when the street opens and becomes
    the size of each completion, bet or raise *increment*. p3's all-in completion to 2 is an
    increment of 1, so 1 is the yardstick; p4's all-in to 3 is another increment of 1, and
    PokerKit drops its short-all-in tally as soon as the tally reaches the yardstick. By p2's
    turn the tally is empty and p2 is not among those who have acted, so its bar on raising
    cannot apply. The small bet (4) never enters that reckoning, which is why an all-in
    completion below it reopens while one that reaches it does not (the control below).
    """
    assert refusal(STUD_ALL_IN_COMPLETION.format(last='"p2 cbr 7"')).kind == PARTIAL
    assert refusal(STUD_ALL_IN_COMPLETION.format(last='"p2 cc"')).kind == PARTIAL
    # A raise is legal to 7 and nowhere else: 20 is refused for its size, not for reopening.
    assert "goes to 7, not 20" in str(refusal(STUD_ALL_IN_COMPLETION.format(last='"p2 cbr 20"')))


def test_the_control_a_short_all_in_raise_does_not_reopen_for_who_has_acted() -> None:
    """The other side of the same rule, kept: p3 completed, so the short all-in leaves it cold.

    p3's completion to 4 is an increment of 3 over the bring-in, so 3 is the street's yardstick.
    p4's all-in to 5 is an increment of 1, below it, so the tally stands and p3 has acted:
    PokerKit 0.7.6 answers p3's re-raise with "The player already acted and hence cannot raise
    in face of a non-full all-in wager", and takes its call.
    """
    assert "p3 may only call or fold" in str(refusal(STUD_SHORT_ALL_IN_RAISE.format(last='"p3 cbr 9"')))
    assert refusal(STUD_SHORT_ALL_IN_RAISE.format(last='"p3 cc"')).kind == PARTIAL


# -- forty-ninth review ---------------------------------------------------------------

#: Names that differ only in a supplementary character -- U+1F600 against U+1F601, two emoji,
#: U+20000 against U+20001 in CJK extension B, U+1D11E against U+1D122 in musical symbols --
#: and, last, U+1F600 against U+FFFD. A binary collation compares the codepoints, so each pair
#: is two names; the UCA collations the column used to inherit weighed every supplementary
#: character as one U+FFFD, which made each pair one name.
SUPPLEMENTARY_PAIRS = [
    ("Alice\U0001f600", "Alice\U0001f601"),
    ("\U0001f600", "\U0001f601"),
    ("Alice\U00020000", "Alice\U00020001"),
    ("Alice\U0001d11e", "Alice\U0001d122"),
    ("Alice\U0001f600", "Alice\ufffd"),
]


@pytest.mark.parametrize(("left", "right"), SUPPLEMENTARY_PAIRS)
def test_names_differing_only_in_a_supplementary_character_are_two_players(left: str, right: str) -> None:
    """A binary collation reads each supplementary character as itself, so both seats are kept.

    Measured before the schema change: inserting ``Alice😀`` then ``Alice😁`` ran
    ``ON DUPLICATE KEY UPDATE ... id=LAST_INSERT_ID(id)`` into the duplicate on
    ``utf8mb4_general_ci`` and on ``utf8mb4_unicode_ci``, leaving *one* row and handing back
    id 1 both times -- the second seat's actions and winnings filed under the first player.
    """
    assert names_of(build_hand(document(heads_up([left, right])))) == [left, right]


# -- fiftieth review ------------------------------------------------------------------

#: The spellings of one and the same top-level key: TOML reads ``[1]``, ``["1"]`` and ``[ 1 ]``
#: as the key ``1``, so any two of them in one file are one table declared twice.
REPEATED_KEY = [("[1]", "[1]"), ("[1]", '["1"]'), ("[1]", "[ 1 ]")]


@pytest.mark.parametrize(("first", "second"), REPEATED_KEY)
def test_a_table_the_file_declares_twice_is_malformed_not_a_second_hand(
    first: str, second: str, tmp_path, importer
) -> None:
    """TOML refuses a repeated table; the splitter used to read it as a second hand.

    Measured on a live import before the fix: two ``[1]`` sections holding two different hands
    stored *two* hands, counted no duplicates and *no* malformed -- and the hand number is a
    hash of the section's contents, so the two sections really were two hands to fpdb, in the
    reports as much as in ``Hands``. TOML itself says "Cannot declare ('1',) twice" (the two
    spellings meet in the key TOML decodes, which is why they are one name here too). The hand
    the name first declared is kept: it is a hand like any other, and the repetition is what
    the document cannot say.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    badugi = (FIXTURES / "badugi.phh").read_text(encoding="utf-8")
    text = f"{first}\n{razz}\n{second}\n{badugi}\n"
    path = tmp_path / "twice.phhs"
    path.write_text(text, encoding="utf-8")

    items = list(iter_documents(path))
    assert [item.label for item in items if isinstance(item, PHHDocument)] == ["1"]
    assert len(items) == 2
    error = items[1]
    assert isinstance(error, PHHImportError)
    assert error.kind == MALFORMED
    assert "the table [1] is declared twice" in str(error)
    # The repetition is what is reported, on its own line.
    repeated_on = text[: text.rindex(second)].count("\n") + 1
    assert f":{repeated_on}" in str(error)

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (1, 0, 0, 0, 1)


def test_a_repeated_table_with_the_same_contents_is_malformed_not_a_duplicate(tmp_path, importer) -> None:
    """The same defect where it used to look harmless: two identical ``[1]`` sections.

    Measured before the fix: the second section was stored as a *duplicate* of the first, so the
    file imported with no malformed hand and the repetition went unreported. TOML refuses the
    declaration itself, whatever the sections hold.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    path = tmp_path / "alike.phhs"
    path.write_text(f"[1]\n{razz}\n[1]\n{razz}\n", encoding="utf-8")

    items = list(iter_documents(path))
    assert len(items) == 2
    assert isinstance(items[1], PHHImportError)
    assert "is declared twice" in str(items[1])

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (1, 0, 0, 0, 1)


def test_names_a_file_does_not_repeat_still_read_as_their_own_hands(tmp_path) -> None:
    """The control: only a repetition is refused, and a sub-table is not a repetition.

    ``[2]`` beside ``[1]`` is two hands, as it always was; ``[1.notes]`` is a sub-table of the
    hand ``[1]`` -- TOML accepts it, and the splitter leaves the line to that hand rather than
    reading it as a second declaration of ``1``.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    badugi = (FIXTURES / "badugi.phh").read_text(encoding="utf-8")

    distinct = tmp_path / "distinct.phhs"
    distinct.write_text(f"[1]\n{razz}\n[2]\n{badugi}\n", encoding="utf-8")
    assert [item.label for item in iter_documents(distinct)] == ["1", "2"]

    nested = tmp_path / "nested.phhs"
    nested.write_text(f"[1]\n{razz}\n[1.notes]\n_x = 1\n", encoding="utf-8")
    items = list(iter_documents(nested))
    assert [item.label for item in items] == ["1"]
    assert build_hand(items[0]) is not None


# -- fifty-first review ---------------------------------------------------------------

#: One key, two spellings that differ only in how TOML writes an escape: decoded they are one
#: name, so the second spelling is a repetition of the first -- ``[1]`` and ``["\u0031"]`` are
#: both the key ``1``. The last element is the name TOML reads, which both must decode to.
ESCAPED_KEY = [
    ("[1]", '["\\u0031"]', "1", "a four-digit escape"),
    ("[1]", '["\\U00000031"]', "1", "an eight-digit escape"),
    ('["\\t1"]', '["\\u00091"]', "\t1", "a short escape against its code point"),
    ('["a\\\\b"]', '["a\\u005Cb"]', "a\\b", "an escaped backslash against its code point"),
]


@pytest.mark.parametrize(
    ("first", "second", "key", "what"), ESCAPED_KEY, ids=[case[3] for case in ESCAPED_KEY]
)
def test_a_key_written_with_an_escape_is_the_key_toml_reads(
    first: str, second: str, key: str, what: str, tmp_path, importer
) -> None:
    """The escaped spelling of a key is the same name, so it is the same declaration twice.

    Measured on a live import before the fix: ``[1]`` then ``["\\u0031"]`` stored *two* hands,
    counted no duplicates and *no* malformed. The duplicate check read the header's raw text --
    the escape undecoded -- so the two spellings were two names to it, while TOML, which decodes
    a basic string's escapes before it compares keys, refuses the document: "Cannot declare
    ('1',) twice". Both sections did read as the same ``PHHDocument.label`` -- that one is taken
    from the parsed TOML -- which is what made the file look like two hands named alike rather
    than one name declared twice.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    badugi = (FIXTURES / "badugi.phh").read_text(encoding="utf-8")
    text = f"{first}\n{razz}\n{second}\n{badugi}\n"
    path = tmp_path / "escaped.phhs"
    path.write_text(text, encoding="utf-8")

    items = list(iter_documents(path))
    assert [item.label for item in items if isinstance(item, PHHDocument)] == [key]
    assert len(items) == 2
    error = items[1]
    assert isinstance(error, PHHImportError)
    assert error.kind == MALFORMED
    # The name reported is the one TOML reads, as the document's own label is.
    assert f"the table [{key}] is declared twice" in str(error)
    assert error.hand == key
    repeated_on = text[: text.rindex(second)].count("\n") + 1
    assert f":{repeated_on}" in str(error)

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (1, 0, 0, 0, 1)


def test_a_literal_keys_backslash_is_not_an_escape(tmp_path) -> None:
    """The mirror of the same defect: read raw, two *different* names collide and one is refused.

    ``["\\u0031"]`` is the key ``1`` and ``['\\u0031']`` is the six-character name ``\\u0031`` --
    two different tables, which TOML accepts side by side. Read raw, both headers spell the same
    backslash-u-0-0-3-1, so the duplicate check took the second for a repetition of the first and
    refused a hand TOML never refused. Decoding a basic key, and only a basic key, is what tells
    the two apart: a literal key has no escapes.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    badugi = (FIXTURES / "badugi.phh").read_text(encoding="utf-8")
    path = tmp_path / "literal.phhs"
    path.write_text(f"[\"\\u0031\"]\n{razz}\n['\\u0031']\n{badugi}\n", encoding="utf-8")

    items = list(iter_documents(path))
    assert [item.label for item in items if isinstance(item, PHHDocument)] == ["1", "\\u0031"]
    assert not any(isinstance(item, PHHImportError) for item in items)


def test_keys_an_escape_does_not_join_still_read_as_their_own_hands(tmp_path) -> None:
    """The control: decoding joins the spellings of one key, it does not join two keys.

    ``["\\u0032"]`` is the key ``2`` -- decoded, and *not* the key ``1`` beside it, in either
    direction. This one reads the same before and after the fix; it is here to say that the
    guards above fail for the reason claimed and not because every escaped key is refused.
    """
    razz = (FIXTURES / "razz.phh").read_text(encoding="utf-8")
    badugi = (FIXTURES / "badugi.phh").read_text(encoding="utf-8")
    path = tmp_path / "another.phhs"
    path.write_text(f"[1]\n{razz}\n[\"\\u0032\"]\n{badugi}\n", encoding="utf-8")

    items = list(iter_documents(path))
    assert [item.label for item in items if isinstance(item, PHHDocument)] == ["1", "2"]
    assert not any(isinstance(item, PHHImportError) for item in items)


# -- fifty-second review --------------------------------------------------------------

SINGLE_DRAW = (FIXTURES / "single_draw.phh").read_text(encoding="utf-8")
HEADS_UP = (FIXTURES / "nl_holdem_heads_up.phh").read_text(encoding="utf-8")


def test_a_card_discarded_a_moment_ago_is_not_dealt_back() -> None:
    """A discard is out of play, not gone -- but the stub has to run out before it comes back.

    The single-draw fixture has p3 discard ``9s`` and draw ``Kh``. Dealing ``9s`` back instead
    was *accepted* before this: the discard left the cards-in-play set, so nothing stopped the
    very next deal from handing the same card out again, with 37 cards still in the stub.
    PokerKit's simulation shuffles the discards in only on the draw that exhausts the stub, so
    a card discarded a moment ago cannot be the card drawn.
    """
    error = refusal(SINGLE_DRAW.replace('"d dh p3 Kh"', '"d dh p3 9s"'))
    assert error.kind == MALFORMED
    assert "9s was discarded" in str(error)
    assert "action 10" in str(error)


def test_a_card_nobody_has_discarded_is_still_dealt() -> None:
    """The control: only a discarded card is held back, and a card in play is still refused.

    ``As`` is in nobody's hand and in no discard pile, so it is a card of the stub and is dealt;
    ``2c`` is still p1's, which the check that was already there refuses.
    """
    assert build_hand(document(SINGLE_DRAW.replace('"d dh p3 Kh"', '"d dh p3 As"'))) is not None
    assert "2c is dealt twice" in str(refusal(SINGLE_DRAW.replace('"d dh p3 Kh"', '"d dh p3 2c"')))


#: A six-player single draw whose stub runs out. Thirty cards are dealt and all thirty are
#: discarded, so the stub holds 22; the first four players draw 20 of those, leaving ``Ks``
#: ``As``. p5's and p6's draws are the ones a reshuffled stub answers, so they legitimately
#: draw back cards the earlier players discarded -- which is what the guard above must not
#: refuse, and the reason the discards are tracked at all.
_SIX_STUB = ("7h8h9hThJh", "7s8s9sTsJs", "QcKcAc", "QdKdAd", "QhKhAh", "QsKsAs")
_SIX_DEAL = {
    "p1": "2c3c4c5c6c",
    "p2": "2d3d4d5d6d",
    "p3": "2h3h4h5h6h",
    "p4": "2s3s4s5s6s",
    "p5": "7c8c9cTcJc",
    "p6": "7d8d9dTdJd",
}
#: What each player is dealt on the first draw: the stub, in order, for the first four, and for
#: p5 and p6 the cards of the discards that the reshuffle is what makes available.
_SIX_FIRST_DRAW = {
    "p1": _SIX_STUB[0],
    "p2": _SIX_STUB[1],
    "p3": "QcKcAcQdKd",
    "p4": "AdQhKhAhQs",
    "p5": "KsAs2c3c4c",
    "p6": "5c6c2d3d4d",
}


def six_player_draw(p5_draw: str = "KsAs2c3c4c") -> str:
    """The six-player hand above, with *p5_draw* as the fifth player's replacement cards."""
    drawn = {**_SIX_FIRST_DRAW, "p5": p5_draw}
    return "\n".join(
        [
            'variant = "N2L1D"',
            "antes = [0, 0, 0, 0, 0, 0]",
            "blinds_or_straddles = [5, 10, 0, 0, 0, 0]",
            "min_bet = 10",
            "starting_stacks = [500, 500, 500, 500, 500, 500]",
            "actions = [",
            *[f'  "d dh {seat} {cards}",' for seat, cards in _SIX_DEAL.items()],
            *[f'  "{seat} cc",' for seat in ("p3", "p4", "p5", "p6", "p1", "p2")],
            *[f'  "{seat} sd {cards}",' for seat, cards in _SIX_DEAL.items()],
            *[f'  "d dh {seat} {cards}",' for seat, cards in drawn.items()],
            '  "p1 f",',
            '  "p2 f",',
            '  "p3 f",',
            '  "p4 f",',
            '  "p5 cbr 100",',
            '  "p6 f",',
            "]",
            'players = ["p1", "p2", "p3", "p4", "p5", "p6"]',
        ]
    )


def test_a_discarded_card_is_dealt_back_once_the_stub_has_run_out() -> None:
    """The control the guard above must not break: a reshuffled stub deals the discards again.

    p5's draw of five is the first that cannot come from the stub, which holds two: ``Ks`` and
    ``As`` are its, and ``2c`` ``3c`` ``4c`` are p1's discards, which the reshuffle is what
    makes available. Refusing this would refuse a hand PokerKit plays.
    """
    assert build_hand(document(six_player_draw())) is not None
    # And the same draw while the stub still holds cards is refused, one draw earlier.
    error = refusal(six_player_draw().replace('"d dh p1 7h8h9hThJh"', '"d dh p1 2c3c4c5c6c"'))
    assert error.kind == MALFORMED
    assert "2c 3c 4c 5c 6c was discarded" in str(error)


#: One TOML date, time or datetime, and the *string* that ``str()`` writes it as -- which is
#: the spelling the old encoding collapsed it to. A datetime's text is space-separated, so the
#: ``T`` spelling of the same instant is another string and was never the colliding one.
_TYPED_HERO = [
    ("1970-01-01", "1970-01-01", "a date"),
    ("1970-01-01T00:00:00", "1970-01-01 00:00:00", "a datetime"),
    ("00:00:00", "00:00:00", "a time"),
]


@pytest.mark.parametrize(
    ("spelled", "text", "what"), _TYPED_HERO, ids=[case[2] for case in _TYPED_HERO]
)
def test_a_hand_that_changes_a_fields_type_is_another_hand(spelled: str, text: str, what: str) -> None:
    """A TOML date, time or datetime is not the string that spells it, and the hash says so.

    ``json.dumps(..., default=str)`` wrote the value as its own text, which is also what a
    string of that text writes: ``_hero = 1970-01-01`` and ``_hero = "1970-01-01"`` were one
    hand number, so a file corrected from one to the other kept its number and was skipped as
    a duplicate of itself. ``_hero`` is a user-defined field, so both spellings are accepted
    and both are reachable; the hand's content differs and the number must too.
    """
    value = document(f"_hero = {spelled}\n")
    as_text = document(f'_hero = "{text}"\n')
    assert hand_number(value.data, "a.phhs\x001") != hand_number(as_text.data, "a.phhs\x001")
    # The same hand, read twice, is still one number.
    assert hand_number(value.data, "a.phhs\x001") == hand_number(document(f"_hero = {spelled}\n").data, "a.phhs\x001")


def test_a_number_is_not_the_string_that_spells_it() -> None:
    """The control: the types the old encoding did keep apart are still apart."""
    for left, right in [("1", '"1"'), ("true", '"true"'), ("1.5", '"1.5"')]:
        assert hand_number(document(f"_hero = {left}\n").data, "a.phhs\x001") != hand_number(
            document(f"_hero = {right}\n").data, "a.phhs\x001"
        )


def heads_up(names: list[str], *, raise_size: int = 18) -> str:
    """The heads-up fixture with *names* for its two players and that raise size.

    The raise size is what makes the second hand of a file a hand of its own: the same content
    is a duplicate of the first, and a duplicate is not what these tests are about.
    """
    text = HEADS_UP.replace('players = ["Alice", "Bob"]', f"players = {json.dumps(names, ensure_ascii=False)}")
    text = text.replace('_hero = "Alice"', f'_hero = "{names[0]}"')
    return text.replace("cbr 18", f"cbr {raise_size}")


_PHH_PLAYERS_SQL = "SELECT name FROM Players WHERE siteId = %s ORDER BY id"


def phh_players(db: Any) -> list[str]:
    """The names in ``Players`` for the PHH source, in the order they were stored."""
    cursor = db.get_cursor()
    cursor.execute(_PHH_PLAYERS_SQL.replace("%s", db.sql.query.get("placeholder", "%s")), (PHH_SITE_ID,))
    return [str(name) for (name,) in cursor.fetchall()]


@pytest.mark.parametrize("second", ["alice", "Álice"], ids=["another case", "another accent"])
def test_a_name_the_database_holds_in_another_case_or_accent_is_another_player(
    second: str, tmp_path, importer
) -> None:
    """The index compares a stored name byte for byte, so the later hand adds a player.

    Measured before the schema change: MySQL's usual collation, which compares names without
    case or accents, put ``alice`` and ``Álice`` in Alice's row -- ``insertPlayer`` upserts on
    the unique ``(name, siteId)`` index and handed back the existing id, so the two hands'
    actions and winnings became one player's. The column is binary now (#417) and both names
    are rows of their own, whichever hand saw them first.
    """
    path = tmp_path / "names.phhs"
    path.write_text(
        f"[1]\n{heads_up(['Alice', 'Bob'])}\n[2]\n{heads_up([second, 'Bob'], raise_size=20)}\n",
        encoding="utf-8",
    )

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (2, 0, 0, 0, 0)
    assert phh_players(importer.database) == ["Alice", "Bob", second]


def test_two_seats_differing_only_in_case_are_stored_as_two_players(tmp_path, importer) -> None:
    """One hand may seat ``Alice`` and ``alice``: the column keeps them apart (#417).

    The importer refused this hand before the schema change -- MySQL's default collation would
    have filed both seats in one row, their actions and winnings one player's. On the binary
    column they are two players, and the hand imports.
    """
    path = tmp_path / "case.phhs"
    path.write_text(f"[1]\n{heads_up(['Alice', 'alice'])}\n", encoding="utf-8")

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (1, 0, 0, 0, 0)
    assert phh_players(importer.database) == ["Alice", "alice"]


def test_a_database_that_has_not_migrated_the_collation_refuses_the_file(tmp_path, importer) -> None:
    """Refusing beats the merge the old column would perform (#417).

    The migration that gives ``Players.name`` its binary collation is best-effort: another
    connection holding the table makes it log and retry on the next connection. Accepting the
    hand meanwhile would be worse than refusing it -- ``insertPlayer`` would upsert ``alice``
    onto Alice's row and the two seats' actions would be one player's for good -- so the file
    is refused whole and nothing is written.
    """
    path = tmp_path / "unmigrated.phhs"
    path.write_text(f"[1]\n{heads_up(['Alice', 'alice'])}\n", encoding="utf-8")
    importer.database.players_name_compares_binary = lambda: False

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (0, 0, 0, 1, 0)
    assert phh_players(importer.database) == []
    summary = importer.phh_summary()
    assert summary is not None
    assert "does not compare names byte for byte" in summary.errors[0]


def test_the_same_name_in_another_hand_is_the_same_player(tmp_path, importer) -> None:
    """The control: a name the database already holds *as spelled* is that player, not a new one.

    Every dataset names its players again in every hand, so this is the case the guard must let
    through -- only a name that meets a stored one on a trailing space is refused.
    """
    path = tmp_path / "same.phhs"
    path.write_text(
        f"[1]\n{heads_up(['Alice', 'Bob'])}\n[2]\n{heads_up(['Alice', 'Bob'], raise_size=20)}\n",
        encoding="utf-8",
    )

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (2, 0, 0, 0, 0)
    assert phh_players(importer.database) == ["Alice", "Bob"]


# -- fifty-third review ---------------------------------------------------------------

#: A name as long as ``Players.name`` holds (``VARCHAR(32)``), and two that run past it.
_LONG_NAME = "a" * 32


def test_names_the_database_would_cut_short_are_refused_in_every_hand(tmp_path, importer) -> None:
    """``insertPlayer`` keeps 32 characters of a name, so two names alike that far are one row.

    ``a…ax`` and ``a…ay`` are two players whose names agree in every character the database
    keeps: ``insertPlayer`` sends ``name[:32]``, the unique index on ``(name, siteId)`` finds the
    row the first hand made, and ``ON DUPLICATE KEY UPDATE ... id=LAST_INSERT_ID(id)`` answers
    with that row's id, so the second hand's actions and winnings become the first player's.
    The row holds nothing that tells the second player from the first named again, so neither
    hand is stored: a name longer than the column is refused wherever it appears.
    """
    path = tmp_path / "long.phhs"
    path.write_text(
        f"[1]\n{heads_up([f'{_LONG_NAME}x', 'Bob'])}\n"
        f"[2]\n{heads_up([f'{_LONG_NAME}y', 'Bob'], raise_size=20)}\n",
        encoding="utf-8",
    )

    assert importer.addImportFile(str(path))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (0, 0, 0, 2, 0)
    assert phh_players(importer.database) == []


def test_a_32_character_name_is_one_player_across_imports(tmp_path, importer) -> None:
    """The control: a name the column holds whole is the same player in a later import.

    That is what refusing longer names buys. Accepting them, the second import's hand could
    not have been told from a second player's -- it would have had to be refused, or merged.
    """
    first, second = tmp_path / "first.phh", tmp_path / "second.phh"
    first.write_text(heads_up([_LONG_NAME, "Bob"]), encoding="utf-8")
    second.write_text(heads_up([_LONG_NAME, "Bob"], raise_size=20), encoding="utf-8")

    assert importer.addImportFile(str(first))
    assert importer.runImport()[0] == 1
    assert importer.addImportFile(str(second))
    assert importer.runImport()[0] == 1
    assert phh_players(importer.database) == [_LONG_NAME, "Bob"]


_SIX_ORDER = ("p1", "p2", "p3", "p4", "p5", "p6")
#: The second draw round of the six-player hand: one card back each, and one taken from the 22
#: cards the first draw's reshuffle left in the stub. p1's is what the guard below varies.
_SECOND_DISCARD = {"p1": "7h", "p2": "7s", "p3": "Qd", "p4": "Qs", "p5": "4c", "p6": "4d"}
_SECOND_DRAW = {"p1": "5d", "p2": "6d", "p3": "2h", "p4": "2s", "p5": "7c", "p6": "7d"}


def six_player_triple_draw(p1_second_draw: str = "5d") -> str:
    """The six-player hand above carried on to a second draw round, *p1_second_draw* aside.

    The first draw is the one that exhausts the stub, so the second draws from the 22 cards the
    reshuffle left: p1's ``5d``, p2's ``6d`` and so on are those cards.
    """
    drawn = {**_SECOND_DRAW, "p1": p1_second_draw}
    actions = [
        *[f'  "d dh {seat} {cards}",' for seat, cards in _SIX_DEAL.items()],
        *[f'  "{seat} cc",' for seat in ("p3", "p4", "p5", "p6", "p1", "p2")],
        *[f'  "{seat} sd {cards}",' for seat, cards in _SIX_DEAL.items()],
        *[f'  "d dh {seat} {cards}",' for seat, cards in _SIX_FIRST_DRAW.items()],
        *[f'  "{seat} cc",' for seat in _SIX_ORDER],
        *[f'  "{seat} sd {cards}",' for seat, cards in _SECOND_DISCARD.items()],
        *[f'  "d dh {seat} {cards}",' for seat, cards in drawn.items()],
        *[f'  "{seat} cc",' for seat in _SIX_ORDER],
        *[f'  "{seat} sd",' for seat in _SIX_ORDER],
        *[f'  "{seat} f",' for seat in _SIX_ORDER[:5]],
    ]
    return "\n".join(
        [
            'variant = "F2L3D"',
            "antes = [0, 0, 0, 0, 0, 0]",
            "blinds_or_straddles = [5, 10, 0, 0, 0, 0]",
            "small_bet = 10",
            "big_bet = 20",
            "starting_stacks = [500, 500, 500, 500, 500, 500]",
            "actions = [",
            *actions,
            "]",
            'players = ["p1", "p2", "p3", "p4", "p5", "p6"]',
        ]
    )


def test_a_card_discarded_after_the_reshuffle_is_not_dealt_back() -> None:
    """The pile the reshuffle made is the stub, and what a later draw discards is out of play.

    The first draw is the one that exhausts the stub -- p5 wants five cards and it holds two --
    so the discards are shuffled in and the 22 cards left of that pile *are* the stub. p1 gives
    back the ``7h`` on the second draw and is dealt it straight back: that needs the discards
    shuffled in again, which a stub of 22 cards has not earned. Left in ``self.discarded``, the
    pile stayed counted out of play for the rest of the hand, so ``_stub()`` read zero and the
    check could not fire however the hand went on.
    """
    error = refusal(six_player_triple_draw("7h"))
    assert error.kind == MALFORMED
    assert "7h was discarded" in str(error)
    assert "action 37" in str(error)


@pytest.mark.parametrize("drawn", ["5d", "3h"], ids=["the card it was played with", "another of the pile"])
def test_a_card_the_reshuffle_returned_is_still_dealt(drawn: str) -> None:
    """The control: the second draw is answered by that pile, and dealing from it is the hand.

    ``5d`` is what p1 was dealt, ``3h`` another card the pile holds that no hand does: both are
    the stub after the reshuffle, so both are dealt. Refusing either would refuse a hand
    PokerKit plays, which is what the discard pile is tracked for in the first place.
    """
    assert build_hand(document(six_player_triple_draw(drawn))) is not None
