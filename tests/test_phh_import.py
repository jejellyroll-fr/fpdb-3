"""PHH (Poker Hand History) import (#381).

The fixtures under ``tests/fixtures/phh`` were played through PokerKit -- the reference
implementation of PHH -- which supplied their ``winnings`` / ``finishing_stacks`` and the
net result of every player (``pokerkit_results.json``). fpdb's own result for each player,
read back from the database, is checked against that independent one.
"""

from __future__ import annotations

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
    stud = (FIXTURES / "stud_hilo_split.phh").read_text(encoding="utf-8").replace('  "d dh p2 8d",\n', "")
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
