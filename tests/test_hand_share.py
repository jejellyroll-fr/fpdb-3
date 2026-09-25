"""Readable hand renderers for sharing (#400).

Each test reads a real hand history, or reads it back from a throwaway
database the way the Hand Viewer and the Replayer do, and checks what a
person pasting it into a forum would see.
"""

from __future__ import annotations

import datetime
import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.hand_share import ShareOptions, render_hand, supports_bb_amounts
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hands" / "pokerstars"
CASH = "holdem/cash_nl_6max.txt"
OPPONENTS = ("Player2", "Player3", "Player4", "Player5", "Player6")


def parse(config: Any, relative: str) -> Any:
    return PokerStars(config=config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]


@pytest.fixture
def cash_hand(legacy_config) -> Any:
    return parse(legacy_config, CASH)


def read_back(importer: Any, db: Any, config: Any, tmp_path: Path, relative: str) -> Any:
    source = FIXTURES / relative
    copy = tmp_path / source.name
    shutil.copy(source, copy)
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    return hand_factory(hand_id, config, db)


def test_a_holdem_hand_reads_like_the_issue_example(cash_hand) -> None:
    assert render_hand(cash_hand) == (
        "NL Hold'em 6-max - $0.50/$1.00\n"
        "\n"
        "Villain 1: SB - $100.00\n"
        "Villain 2: BB - $100.00\n"
        "Villain 3: LJ - $100.00\n"
        "Villain 4: HJ - $100.00\n"
        "Villain 5: CO - $100.00\n"
        "Hero: BTN - $100.00\n"
        "\n"
        "Hero [Ah Kh]\n"
        "\n"
        "Preflop\n"
        "Villain 1 posts SB $0.50\n"
        "Villain 2 posts BB $1.00\n"
        "Villain 3, Villain 4 and Villain 5 fold\n"
        "Hero raises to $3.00\n"
        "Villain 1 calls $2.50\n"
        "Villain 2 folds\n"
        "\n"
        "Flop [As Ks 2d] - Pot $7.00\n"
        "Villain 1 checks\n"
        "Hero bets $4.00\n"
        "Villain 1 calls $4.00\n"
        "\n"
        "Turn [As Ks 2d] [Td] - Pot $15.00\n"
        "Villain 1 checks\n"
        "Hero bets $10.00\n"
        "Villain 1 raises to $20.00\n"
        "Hero calls $10.00\n"
        "\n"
        "River [As Ks 2d Td] [Qh] - Pot $55.00\n"
        "Villain 1 bets $20.00\n"
        "Hero calls $20.00\n"
        "\n"
        "Summary\n"
        "Villain 1 shows [2s 2c] (three of a kind, Deuces)\n"
        "Hero shows [Ah Kh] (two pair, Aces and Kings)\n"
        "Villain 1 wins $95.00\n"
        "Total pot $95.00\n"
    )


def test_rendering_is_deterministic(cash_hand) -> None:
    options = ShareOptions(format="markdown", amounts="bb", anonymize="opponents")
    assert render_hand(cash_hand, options) == render_hand(cash_hand, options)


def test_by_default_no_name_or_identifier_leaks(cash_hand) -> None:
    text = render_hand(cash_hand)

    for name in ("Player1", *OPPONENTS):
        assert name not in text
    assert "PokerStars" not in text
    assert "Test Table" not in text
    assert str(cash_hand.handid) not in text
    assert "2023" not in text


def test_keeping_my_name_still_hides_every_opponent(cash_hand) -> None:
    text = render_hand(cash_hand, anonymize="opponents")

    assert "Player1: BTN" in text
    assert "Player1 [Ah Kh]" in text
    for name in OPPONENTS:
        assert name not in text


def test_an_opponent_keeps_one_alias_throughout_the_hand(cash_hand) -> None:
    text = render_hand(cash_hand, anonymize="opponents")

    # Player2 is the small blind: the same alias posts, calls and wins.
    assert "Villain 1: SB" in text
    assert "Villain 1 posts SB $0.50" in text
    assert "Villain 1 raises to $20.00" in text
    assert "Villain 1 shows [2s 2c]" in text
    assert "Villain 1 wins $95.00" in text


def test_names_can_be_kept_on_request(cash_hand) -> None:
    text = render_hand(cash_hand, anonymize="none")

    assert "Player2 wins $95.00" in text
    assert "Villain" not in text
    assert "Hero" not in text


def test_identifiers_are_shown_only_when_asked(cash_hand) -> None:
    text = render_hand(cash_hand, site=True, table=True, hand_id=True, timestamp=True)

    assert text.splitlines()[1] == "PokerStars.COM | Table Test Table | Hand #1234567890 | 2023-10-27 16:00"


def test_stacks_results_and_rake_are_toggles(cash_hand) -> None:
    text = render_hand(cash_hand, stacks=False, results=False)
    assert "Villain 1: SB\n" in text
    assert "wins" not in text
    assert "shows" not in text

    assert "| Rake $0.00" in render_hand(cash_hand, rake=True)


def test_amounts_can_be_counted_in_big_blinds(cash_hand) -> None:
    text = render_hand(cash_hand, amounts="bb")

    # The stakes stay in money: they are what the big blinds are measured in.
    assert text.startswith("NL Hold'em 6-max - $0.50/$1.00 (amounts in BB)\n")
    assert "Hero: BTN - 100 BB" in text
    assert "Villain 1 posts SB 0.5 BB" in text
    assert "Hero raises to 3 BB" in text
    assert "River [As Ks 2d Td] [Qh] - Pot 55 BB" in text
    assert "$" not in text.split("\n", 1)[1]


def test_markdown_keeps_to_what_discord_and_github_both_render(cash_hand) -> None:
    text = render_hand(cash_hand, format="markdown")

    assert text.startswith("**NL Hold'em 6-max - $0.50/$1.00**\n")
    assert "- Villain 1: SB - $100.00" in text
    assert "**Flop [As Ks 2d] - Pot $7.00**" in text
    assert "|" not in text  # no tables: Discord does not render them


def test_markdown_escapes_player_names(cash_hand) -> None:
    for player in cash_hand.players:
        if player[1] == "Player2":
            player[1] = "big_*fish*"
    cash_hand.actions = {
        street: [(("big_*fish*",) + tuple(a[1:])) if a[0] == "Player2" else a for a in acts]
        for street, acts in cash_hand.actions.items()
    }

    text = render_hand(cash_hand, format="markdown", anonymize="none")

    assert "big\\_\\*fish\\*" in text


def test_bbcode_uses_forum_tags(cash_hand) -> None:
    text = render_hand(cash_hand, format="bbcode")

    assert text.startswith("[b]NL Hold'em 6-max - $0.50/$1.00[/b]\n")
    assert "[b]Summary[/b]" in text


def test_unknown_options_are_refused(cash_hand) -> None:
    with pytest.raises(ValueError, match="format"):
        render_hand(cash_hand, format="html")
    with pytest.raises(ValueError, match="anonymize"):
        render_hand(cash_hand, anonymize="some")


def test_omaha_renders_every_hole_card(legacy_config) -> None:
    text = render_hand(parse(legacy_config, "holdem/5card_omaha.txt"))

    hero_line = next(line for line in text.splitlines() if line.startswith("Hero ["))
    assert len(hero_line.split("[")[1].split()) == 5


def test_draw_shows_discards_and_later_draws(legacy_config) -> None:
    text = render_hand(parse(legacy_config, "draw/triple_draw.txt"), amounts="bb")

    assert "FL 2-7 Triple Draw" in text
    assert "Hero [8s Ts 8h 2s 3s]" in text
    assert "First draw - Pot 13.5 BB" in text
    assert "Villain 2 discards 2 cards" in text
    assert "Villain 5 stands pat" in text
    # The all-in shortfall went back before the third draw.
    assert "Third draw - Pot 21.1 BB" in text


def test_stud_shows_up_cards_and_is_gated_out_of_big_blinds(legacy_config) -> None:
    hand = parse(legacy_config, "stud/7stud.txt")
    text = render_hand(hand)

    assert "3rd street" in text
    assert "Villain 2 [5d]" in text  # an up card dealt on 4th street
    assert ": SB" not in text  # stud has no button positions
    assert not supports_bb_amounts(hand)
    with pytest.raises(ValueError, match="big blind"):
        render_hand(hand, amounts="bb")


def test_a_tournament_counts_chips_without_a_currency(legacy_config) -> None:
    text = render_hand(parse(legacy_config, "holdem/tournament_ko.txt"))

    assert "tournament - 10/20" in text
    # The fixture's button and blinds disagree, so only the stack is checked.
    assert any(line.startswith("Hero: ") and line.endswith(" - 1,500") for line in text.splitlines())
    assert "$" not in text


def fake_hand(seats: int) -> Any:
    players = [[seat, f"P{seat}", "100", None, None] for seat in range(1, seats + 1)]
    return SimpleNamespace(
        players=players,
        sitout=set(),
        buttonpos=seats,
        hero="",
        gametype={"base": "hold", "category": "holdem", "limitType": "nl", "type": "ring", "currency": "USD"},
        sym="$",
        sb=Decimal("0.5"),
        bb=Decimal(1),
        maxseats=seats,
        handText="",
        sitename="",
        tablename="",
        handid=0,
        startTime=datetime.datetime(2026, 1, 1),
        allStreets=["BLINDSANTES", "PREFLOP"],
        actions={"BLINDSANTES": [], "PREFLOP": []},
        board={},
        holeStreets=["PREFLOP"],
        holecards={"PREFLOP": {}},
        pot=SimpleNamespace(returned={}),
        shown=set(),
        mucked=set(),
        folded=set(),
        showdownStrings={},
        collectees={},
        collected=[],
        totalpot=None,
        rake=None,
    )


@pytest.mark.parametrize(
    ("seats", "positions"),
    [
        (2, ["BB", "BTN"]),
        (3, ["SB", "BB", "BTN"]),
        (6, ["SB", "BB", "LJ", "HJ", "CO", "BTN"]),
        (9, ["SB", "BB", "UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN"]),
        (10, ["SB", "BB", "UTG", "UTG+1", "UTG+2", "MP1", "LJ", "HJ", "CO", "BTN"]),
    ],
)
def test_positions_are_named_from_the_button(seats: int, positions: list[str]) -> None:
    text = render_hand(fake_hand(seats), stacks=False, anonymize="none")

    seat_lines = [line for line in text.splitlines() if line.startswith("P")]
    assert [line.split(": ")[1] for line in seat_lines] == positions


def test_a_hand_read_back_from_the_database_renders_the_same_story(
    importer, fresh_db, legacy_config, tmp_path
) -> None:
    hand = read_back(importer, fresh_db, legacy_config, tmp_path, CASH)
    text = render_hand(hand)

    # The database keeps a placeholder table size, so none is claimed.
    assert text.startswith("NL Hold'em - $0.50/$1.00\n")
    assert "Hero: BTN - $100.00" in text
    assert "River [As Ks 2d Td] [Qh] - Pot $55.00" in text
    # The stored hand does not say the hero showed; reaching showdown does.
    assert "Hero shows [Ah Kh]" in text
    assert "Villain 1 wins $95.00" in text


def test_a_returned_bet_leaves_the_pot_before_the_next_street(
    importer, fresh_db, legacy_config, tmp_path
) -> None:
    hand = read_back(importer, fresh_db, legacy_config, tmp_path, "holdem/tournament_ko.txt")
    text = render_hand(hand)

    assert "Uncalled 10 returned to Hero" in text
    assert "Flop [Kd Qd Jd] - Pot 3,020" in text
    assert "Total pot 3,020" in text
