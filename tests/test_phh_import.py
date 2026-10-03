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
    straddle = build_hand(document(NT_HAND.replace("[1, 2, 0]", "[1, 2, 4]").replace("p3 cbr 6", "p3 cbr 12")))
    assert actions_of(straddle)[2] == ("BLINDSANTES", "p3", "straddle", 4)

    button = build_hand(
        document(
            NT_HAND.replace("[0, 0, 0]", "[1, 1, 1]")
            .replace("[1, 2, 0]", "[0, 0, 2]")
            .replace("p3 cbr 6", "p1 cbr 6")
            .replace('"p1 f",', '"p3 f",')
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
        (('"p3 cbr 6",', '"d db AsKs",'), "the flop deals 3 cards"),
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
        '"p1 cc",\n  "p2 cc",\n  "d db AsKsQs",\n  "d db 2c",\n  "d db 3c",\n  "d db 4c",',
    )
    assert refusal(text).kind == UNSUPPORTED


def test_a_showdown_without_winnings_is_not_guessed() -> None:
    text = NT_HAND.replace('"p1 f",\n  "p2 f",', '"p1 cc",\n  "p2 f",\n  "d db AsKsQs",\n  "d db 2c",\n  "d db 3c",')
    error = refusal(text)
    assert error.kind == UNSUPPORTED
    assert "without guessing" in str(error)


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
    dataset = tmp_path / "dataset.phhs"
    dataset.write_text("# a small dataset\n\n" + "\n".join(parts), encoding="utf-8")

    labels = [item.label if isinstance(item, PHHDocument) else item.kind for item in iter_documents(dataset)]
    assert labels == ["1", "2", "3", "4", "5", MALFORMED, "1-again"]

    assert importer.addImportFile(str(dataset))
    stored, duplicates, partial, skipped, errors, _seconds = importer.runImport()
    assert (stored, duplicates, partial, skipped, errors) == (3, 1, 0, 1, 2)
    summary = importer.phh_summary()
    assert summary is not None
    assert (summary.discovered, summary.unsupported, summary.malformed) == (7, 1, 2)
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
        "PHH: 7 hands found, 3 imported, 1 duplicates, 1 unsupported, 2 malformed, in 0.5s",
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
