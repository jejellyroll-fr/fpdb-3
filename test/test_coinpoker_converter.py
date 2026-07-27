"""Tests for the CoinPoker protocol decoder and hand converter.

Fixture ``data/coinpoker_hand_events.json`` holds the decoded ``game.*`` events
of two real captured hands (player names anonymized). Hand 91426500343 is
complete; 91426500344 was still in progress when capture stopped and must be
rejected rather than imported truncated.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.coinpoker_hand_builder import (
    _collect_players,
    _detect_category,
    _extract_boards,
    _extract_cashout,
    _extract_collections,
    _extract_splash,
    _tournament_info,
    build_hands,
)
from fpdb_3_legacy.coinpoker_protocol import decode_frame, split_frames
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    _board_streets,
    build_fpdb_hand,
    import_fpdb_hand,
    render_fpdb_hand,
)
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.SQL import Sql

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"
STRADDLE_FIXTURE = Path(__file__).parent / "data" / "coinpoker_straddle_hand_events.json"


def _load_events() -> list[tuple]:
    raw = json.loads(FIXTURE.read_text())
    return [tuple(e) for e in raw]


def _hand(hand_id: str) -> dict:
    hands = build_hands(_load_events(), "PLO4")
    return next(h for h in hands if h["hand_id"] == hand_id)


def _load_straddle_events() -> list[tuple]:
    raw = json.loads(STRADDLE_FIXTURE.read_text())
    return [tuple(e) for e in raw]


def _straddle_hand() -> dict:
    return build_hands(_load_straddle_events(), "PLO4")[0]


# --- protocol decoder ---------------------------------------------------------


def test_decode_frame_tlv_map_with_string() -> None:
    # type 0x12 map, 1 field, key "c", type 0x08 string "hi".
    payload = b"\x12\x00\x01\x00\x01c\x08\x00\x02hi"
    assert decode_frame(0x80, payload) == {"c": "hi"}


def test_split_frames_reads_length_prefixed_frames() -> None:
    payload = b"\x12\x00\x00"  # empty map
    stream = b"\x80\x00\x03" + payload + b"\x80\x00\x03" + payload
    frames = split_frames(stream)
    assert len(frames) == 2
    assert all(flags == 0x80 and body == payload for flags, body in frames)


# --- hand conversion ----------------------------------------------------------


def test_builds_two_hands_from_fixture() -> None:
    hands = build_hands(_load_events(), "PLO4")
    assert {h["hand_id"] for h in hands} == {"91426500343", "91426500344"}
    assert all(h["collections"] for h in hands)  # both captured hands are complete


def test_complete_hand_maps_to_fpdb_hand() -> None:
    hand = build_fpdb_hand(_hand("91426500343"))
    assert hand.handid == "91426500343"
    assert hand.gametype["base"] == "hold"
    assert hand.gametype["category"] == "omahahi"
    assert len(hand.players) == 5


def test_tournament_hand_maps_mtt_metadata_to_fpdb_hand() -> None:
    events = _load_events()
    patched = []
    for name, hid, data in events:
        if name == "game.pre_hand_start_info" and isinstance(data, dict):
            data = {
                **data,
                "tableId": 1117675,
                "tableSize": 7,
                "isTournament": True,
                "tournamentId": 424242,
                "tournamentName": "Level Up Freeroll",
                "blindLevel": 12,
            }
        patched.append((name, hid, data))

    normalized = build_hands(patched, "NLHE")[0]
    assert normalized["gametype"]["type"] == "tour"
    assert normalized["gametype"]["currency"] == "T$"
    assert normalized["gametype"]["maxSeats"] == 7
    assert normalized["table_id"] == "424242 1117675"
    assert normalized["tournament"]["tour_no"] == "424242"

    hand = build_fpdb_hand(normalized)
    assert hand.gametype["type"] == "tour"
    assert hand.tourNo == "424242"
    assert hand.tourneyName == "Level Up Freeroll"
    assert hand.level == "12"


def test_tournament_hand_imports_into_sqlite() -> None:
    events = [
        (
            "game.tournament_message",
            None,
            {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
        ),
        *_load_events(),
    ]
    normalized = build_hands(events, "PLO4")[0]
    hand = build_fpdb_hand(
        normalized,
        config=HttpCaptureHandConfig(site_ids={"CoinPoker": 30, "default": 30}),
    )

    config = MagicMock()
    config.get_db_parameters.return_value = {
        "db-backend": 4,
        "db-server": "sqlite",
        "db-databaseName": ":memory:",
        "db-user": "",
        "db-password": "",
        "db-host": "",
        "db-port": "",
        "db-path": "",
    }
    config.get_import_parameters.return_value = {
        "saveActions": True,
        "callFpdbHud": False,
        "cacheSessions": False,
        "publicDB": False,
        "fastStoreHudCache": False,
        "sessionTimeout": 30,
    }
    config.get_general_params.return_value = {}
    config.get_site_id.return_value = 30
    db = Database(config, Sql(db_server="sqlite"))

    import_fpdb_hand(hand, db, file_id=1, doinsert=True, printtest=False, starting_hand_id=1)
    db.commit()
    cursor = db.get_cursor()
    cursor.execute("select count(*) from Hands")
    assert cursor.fetchone()[0] == 1
    cursor.execute("select count(*) from Tourneys")
    assert cursor.fetchone()[0] == 1


def test_nested_tournament_event_is_detected() -> None:
    events = [
        (
            "game.tournament_message",
            "H",
            {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
        ),
    ]
    assert _tournament_info(events, table_id="914265")["tour_no"] == "77"


def test_tournament_context_before_first_hand_is_preserved() -> None:
    events = [
        (
            "game.tournament_message",
            None,
            {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
        ),
        *_load_events(),
    ]
    hands = build_hands(events, "PLO4")
    assert hands
    assert all(hand["gametype"]["type"] == "tour" for hand in hands)
    assert all(hand["tournament"]["tour_no"] == "77" for hand in hands)


def test_tournament_transport_classifies_hand_without_lobby_metadata() -> None:
    events = []
    for name, hid, data in _load_events():
        if isinstance(data, dict):
            data = {**data, "_coinpokerServerPort": 3001}
        events.append((name, hid, data))

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["type"] == "tour"
    assert hand["gametype"]["currency"] == "T$"
    assert hand["table_id"] == f"{hand['tournament']['tour_no']} {hand['tournament']['table_id']}"


def test_complete_hand_renders_expected_narrative() -> None:
    text = render_fpdb_hand(build_fpdb_hand(_hand("91426500343")))
    assert "Omaha Pot Limit ($0.01/$0.02)" in text
    assert "Dealt to Hero [Js 8s 7s 4d]" in text
    assert "Villain2: raises $0.05 to $0.07" in text
    assert "*** FLOP *** [Qc 9s 6c]" in text
    assert "*** TURN *** [Qc 9s 6c] [5s]" in text
    assert "Villain4 collected $0.2" in text
    assert "Rake $0.01" in text


def test_coinpoker_explicit_straddle_is_normalized_as_forced_blind() -> None:
    actions = _straddle_hand()["actions"]

    assert actions[:3] == [
        {"type": "small blind", "player": "SmallBlind", "amount": "0.01"},
        {"type": "big blind", "player": "BigBlindWinner", "amount": "0.02"},
        {"type": "straddle", "player": "Straddler", "amount": "0.04"},
    ]
    assert not any(
        action["type"] == "raises" and action["player"] == "Straddler" and action.get("street") == "PREFLOP"
        for action in actions
    )


def test_coinpoker_snapshot_straddle_is_normalized_as_forced_blind() -> None:
    events = [event for event in _load_straddle_events() if event[0] != "game.dealer_chat_action"]
    actions = build_hands(events, "PLO4")[0]["actions"]

    assert {"type": "straddle", "player": "Straddler", "amount": "0.04"} in actions


def test_coinpoker_straddle_hand_conserves_pot_rake_and_player_results() -> None:
    hand = build_fpdb_hand(_straddle_hand())

    hand.totalPot()

    assert hand.pot.committed == {
        "Straddler": Decimal("0.28"),
        "SmallBlind": Decimal("0.01"),
        "BigBlindWinner": Decimal("0.28"),
    }
    assert hand.totalpot == Decimal("0.57")
    assert hand.totalcollected == Decimal("0.54")
    assert hand.rake == Decimal("0.03")

    hand.assembleHand()
    assert hand.handsplayers["Straddler"]["committed"] == 28
    assert hand.handsplayers["Straddler"]["totalProfit"] == -28
    assert hand.handsplayers["Straddler"]["flg_blind_k"] is True
    assert hand.handsplayers["BigBlindWinner"]["committed"] == 28
    assert hand.handsplayers["BigBlindWinner"]["totalProfit"] == 26
    assert sum(player["totalProfit"] for player in hand.handsplayers.values()) == -3

    text = render_fpdb_hand(hand)
    assert "Straddler: posts straddle $0.04" in text
    assert "Total pot $0.57 Main pot $0.03 Side pot $0.54. | Rake $0.03" in text
    assert PokerStars.re_post_straddle.search(text)


def test_hole_cards_and_board_are_mapped() -> None:
    h = _hand("91426500343")
    hero = next(hc for hc in h["holecards"] if hc["player"] == "Hero")
    assert hero["closed"] == ["Js", "8s", "7s", "4d"]
    assert h["community"]["FLOP"] == ["Qc", "9s", "6c"]
    assert h["community"]["TURN"] == ["5s"]


def _hole_cards_event(count: int) -> list[tuple]:
    values = ["ACE", "KING", "QUEEN", "JACK", "TEN", "NINE"]
    cards = [{"suit": "SPADES", "value": values[i]} for i in range(count)]
    return [("game.hole_cards", "H", {"holeCards": cards})]


def test_variant_detected_from_hero_hole_card_count() -> None:
    # The number of cards dealt to the hero identifies the Omaha variant; the
    # session-wide hint is ignored when the hero's cards are present.
    assert _detect_category(_hole_cards_event(2), "PLO4") == ("hold", "holdem")
    assert _detect_category(_hole_cards_event(4), "PLO5") == ("hold", "omahahi")
    assert _detect_category(_hole_cards_event(5), "PLO4") == ("hold", "5_omahahi")
    assert _detect_category(_hole_cards_event(6), "PLO4") == ("hold", "6_omahahi")


def test_variant_falls_back_to_hint_when_hero_cards_absent() -> None:
    # Observing a table (no hero hole cards captured): trust the GUI hint.
    assert _detect_category([("game.pre_hand_start_info", "H", {})], "PLO5") == ("hold", "5_omahahi")
    assert _detect_category([], "NLHE") == ("hold", "holdem")
    assert _detect_category([], "Shortdeck") == ("hold", "6_holdem")


def _two_card_hand(hole: list[tuple[str, str]], board: list[tuple[str, str]]) -> list[tuple]:
    def cards(pairs):
        return [{"value": v, "suit": s} for v, s in pairs]

    return [
        ("game.hole_cards", "H", {"holeCards": cards(hole)}),
        ("game.dealer_cards", "H", {"dealerCards": {"FLOP": cards(board)}}),
    ]


def test_shortdeck_detected_from_hint_when_no_low_cards() -> None:
    # Hold'em and short-deck both deal two cards, so the hint decides -- but only
    # when nothing in the hand contradicts a 36-card deck.
    hand = _two_card_hand([("ACE", "SPADES"), ("KING", "HEARTS")], [("TEN", "SPADES"), ("NINE", "CLUBS"), ("SEVEN", "HEARTS")])
    assert _detect_category(hand, "Shortdeck") == ("hold", "6_holdem")
    assert _detect_category(hand, "NLHE") == ("hold", "holdem")


def test_low_card_overrides_a_wrong_shortdeck_hint() -> None:
    # A 2-5 anywhere proves a full deck: it is regular Hold'em, hint notwithstanding.
    hand = _two_card_hand([("ACE", "SPADES"), ("KING", "HEARTS")], [("FOUR", "CLUBS"), ("TEN", "SPADES"), ("ACE", "DIAMONDS")])
    assert _detect_category(hand, "Shortdeck") == ("hold", "holdem")


def test_hand_start_time_uses_event_init_timestamp() -> None:
    # The protocol's own clock (epoch ms) must win over import wall-clock so
    # replayed captures keep their real dates.
    hand = _hand("91426500343")
    assert hand["timestamp"] is not None
    assert hand["timestamp"].year == 2026  # from the fixture's initTimeStamp, not 1970/now


def test_plo5_hand_keeps_its_fifth_card() -> None:
    # A 5-card hand imported under a stale "PLO4" hint must not be truncated.
    events = _load_events()
    patched = []
    for name, hid, data in events:
        if name == "game.hole_cards" and isinstance(data, dict) and data.get("holeCards"):
            cards = list(data["holeCards"])
            cards.append({"suit": "HEARTS", "value": "TWO"})  # 5th card
            data = {**data, "holeCards": cards}
        patched.append((name, hid, data))
    hand = next(h for h in build_hands(patched, "PLO4") if h["holecards"])
    assert hand["gametype"]["category"] == "5_omahahi"
    hero = next(hc for hc in hand["holecards"] if hc["player"] == "Hero")
    assert len(hero["closed"]) == 5


def test_seat_reuse_keeps_one_player_per_seat() -> None:
    # A seat's occupant changes within the captured window: fpdb must never get
    # two players in the same seat (previously raised FpdbHandPartial).
    evs = [
        ("game.seat", "H", {"seatId": 3, "userName": "Alice", "userChips": 2.0, "betAmout": 0}),
        ("game.seat", "H", {"seatId": 3, "userName": "Bob", "userChips": 1.0, "betAmout": 0}),
        ("game.seat", "H", {"seatId": 4, "userName": "Carol", "userChips": 3.0, "betAmout": 0}),
    ]
    players = _collect_players(evs)
    assert set(players) == {"Alice", "Carol"}
    seats = [p["seat"] for p in players.values()]
    assert len(seats) == len(set(seats))


# --- special hands: run-it-twice / double board / splash / cashout ------------

_VALUE_TO_WORD = {
    "2": "TWO", "3": "THREE", "4": "FOUR", "5": "FIVE", "6": "SIX", "7": "SEVEN",
    "8": "EIGHT", "9": "NINE", "T": "TEN", "J": "JACK", "Q": "QUEEN", "K": "KING", "A": "ACE",
}
_SUIT_TO_WORD = {"s": "SPADES", "h": "HEARTS", "d": "DIAMONDS", "c": "CLUBS"}


def _proto_cards(cards: str) -> list[dict]:
    """"3c 4s Qd" -> the protocol's list-of-dict card encoding."""
    return [{"value": _VALUE_TO_WORD[c[0]], "suit": _SUIT_TO_WORD[c[1]]} for c in cards.split()]


def _dealer_event(dealer=None, rit=None, rit2=None, dbl=None) -> tuple:
    def board(streets):
        return {street: _proto_cards(cards) for street, cards in (streets or {}).items()}

    return (
        "game.dealer_cards",
        "H",
        {
            "dealerCards": board(dealer),
            "dealerCardsRit": board(rit),
            "dealerCardsRit2": board(rit2),
            "dealerCardsDoubleBoard": board(dbl),
        },
    )


def test_run_it_twice_boards_share_the_flop() -> None:
    # RIT: only the turn/river are re-dealt after an all-in, so both run boards
    # carry the single flop that was dealt once.
    evs = [
        _dealer_event(dealer={"FLOP": "3c 4s Qd", "TURN": "Qs", "RIVER": "6d"}, rit={"TURN": "9h", "RIVER": "5s"}),
        ("game.winnerInfo", "H", {"rit": True, "doubleBoard": False, "winnerDataList": []}),
    ]
    boards, run_it_times, double_board = _extract_boards(evs)
    assert run_it_times == 2
    assert double_board is False
    assert boards[0] == {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]}
    assert boards[1] == {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]}


def test_double_board_is_two_independent_boards() -> None:
    # Bomb pot: two full boards dealt from their own flops, not a re-run.
    evs = [
        _dealer_event(
            dealer={"FLOP": "7s 2c 7c", "TURN": "5s", "RIVER": "Qh"},
            dbl={"FLOP": "5h Qs 4s", "TURN": "2h", "RIVER": "6c"},
        ),
        ("game.winnerInfo", "H", {"rit": False, "doubleBoard": True, "winnerDataList": []}),
    ]
    boards, run_it_times, double_board = _extract_boards(evs)
    assert run_it_times == 1  # a double board is not "run it twice"
    assert double_board is True
    assert boards[0]["FLOP"] == ["7s", "2c", "7c"]
    assert boards[1]["FLOP"] == ["5h", "Qs", "4s"]  # independent flop


def test_extract_splash_and_mega_splash() -> None:
    plain = [("game.cumulativeWinnerInfo", "H", {"splashPotAmount": 0.04, "isMegaSplash": False})]
    assert _extract_splash(plain) == (4, False)
    mega = [("game.cumulativeWinnerInfo", "H", {"splashPotAmount": 1, "isMegaSplash": True})]
    assert _extract_splash(mega) == (100, True)
    assert _extract_splash([]) == (0, False)


def test_extract_cashout_records_insured_winner_fee() -> None:
    evs = [
        (
            "game.winnerInfo",
            "H",
            {
                "winnerDataList": [
                    {
                        "winnerDetails": {
                            "winnerList": [
                                {"playerName": "Hero", "winAmountFromPot": 0.30, "actualWinAmount": 0.20, "isInsured": True},
                                {"playerName": "Villain", "winAmountFromPot": 0.10, "actualWinAmount": 0.10, "isInsured": False},
                            ],
                        },
                    },
                ],
            },
        ),
    ]
    cashout = _extract_cashout(evs)
    assert cashout == [{"player": "Hero", "amount": "0.2", "fee": "0.1"}]


def test_insured_winner_uses_actual_payout_when_pot_amount_is_blank() -> None:
    details = {
        "playerName": "Hero",
        "winAmountFromPot": "",
        "actualWinAmount": "0.20",
        "isInsured": True,
    }
    evs = [("game.winnerInfo", "H", {"winnerDataList": [{"potAmountAfterRake": "", "winnerDetails": {"winnerList": [details]}}]})]

    assert _extract_cashout(evs) == [{"player": "Hero", "amount": "0.20", "fee": "0"}]


def test_insurance_payout_is_not_counted_as_poker_pot_winnings() -> None:
    evs = [
        (
            "game.winnerInfo",
            "H",
            {
                "winnerDataList": [
                    {"winnerDetails": {"winnerList": [
                        {"playerName": "Hero", "actualWinAmount": 0.37, "winAmountFromPot": "", "isInsured": True},
                        {"playerName": "Villain", "winAmountFromPot": 2.15, "isInsured": False},
                    ]}},
                    # CoinPoker repeats the same winner snapshot after EV chop.
                    {"winnerDetails": {"winnerList": [
                        {"playerName": "Hero", "actualWinAmount": 0.37, "winAmountFromPot": "", "isInsured": True},
                        {"playerName": "Villain", "winAmountFromPot": 2.15, "isInsured": False},
                    ]}},
                ],
            },
        ),
    ]

    assert _extract_collections(evs) == [{"player": "Villain", "pot": "2.15"}]


def test_board_streets_suffixes_extra_boards() -> None:
    # The first board keeps the base street names; extra boards get numbered
    # streets that DerivedStats encodes into the Boards table.
    hand_data = {
        "boards": [
            {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]},
            {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]},
        ],
    }
    streets = _board_streets(hand_data)
    assert streets["FLOP"] == ["3c", "4s", "Qd"]
    assert streets["TURN"] == ["Qs"]
    assert streets["TURN2"] == ["9h"]
    assert streets["RIVER2"] == ["5s"]


def test_single_board_uses_plain_street_names() -> None:
    hand_data = {"boards": [{"FLOP": ["3c", "4s", "Qd"]}], "community": {"FLOP": ["3c", "4s", "Qd"]}}
    assert set(_board_streets(hand_data)) == {"FLOP"}


def _hand_with(**overrides) -> dict:
    hand = dict(_hand("91426500343"))
    hand.update(overrides)
    return hand


def test_run_it_twice_maps_to_hand_boards_and_run_count() -> None:
    hand = build_fpdb_hand(
        _hand_with(
            boards=[
                {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]},
                {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]},
            ],
            run_it_times=2,
        ),
    )
    assert hand.runItTimes == 2
    assert hand.board["FLOP"] == ["3c", "4s", "Qd"]
    assert hand.board["TURN2"] == ["9h"]
    assert hand.board["RIVER2"] == ["5s"]


def test_bomb_pot_and_splash_map_to_hand_fields() -> None:
    hand = build_fpdb_hand(_hand_with(bomb_pot=30, splash_pot=4))
    assert hand.bombPot == 30
    assert hand.splashPot == 4


def test_cashout_maps_to_hand_cashout_fields() -> None:
    from decimal import Decimal

    hand = build_fpdb_hand(_hand_with(cashout=[{"player": "Hero", "amount": "0.20", "fee": "0.10"}]))
    assert hand.cashedOut is True
    assert hand.isCashOut is True
    assert hand.cashOutAmounts["Hero"] == Decimal("0.20")
    assert hand.cashOutFees["Hero"] == Decimal("0.10")


def test_derived_stats_encode_multiple_boards_and_pot_flags() -> None:
    # End-to-end through DerivedStats: a run-it-twice hand with a bomb/splash pot
    # must yield one encoded board per run plus the scalar pot flags that the
    # Hand Viewer filters query.
    hand = build_fpdb_hand(
        _hand_with(
            boards=[
                {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]},
                {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]},
            ],
            run_it_times=2,
            bomb_pot=30,
            splash_pot=4,
        ),
    )
    hand.totalPot()
    hand.assembleHand()
    assert hand.hands["runItTwice"] is True
    assert len(hand.hands["boards"]) == 2
    assert {b[0] for b in hand.hands["boards"]} == {1, 2}
    assert hand.hands["bombPot"] == 30
    assert hand.hands["splashPot"] == 4


def test_replayer_header_marks_bomb_and_splash_pots() -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy.GuiReplayer import GuiReplayer

    def _hand(**kw):
        data = {"gametype": {"currency": "USD"}, "bombPot": 0, "splashPot": 0}
        data.update(kw)
        return SimpleNamespace(**data)

    assert GuiReplayer._special_pot_suffix(_hand()) == ""
    assert "Bomb pot" in GuiReplayer._special_pot_suffix(_hand(bombPot=30))
    assert "Splash pot: 0.04USD" in GuiReplayer._special_pot_suffix(_hand(splashPot=4))
    both = GuiReplayer._special_pot_suffix(_hand(bombPot=30, splashPot=125))
    assert "Bomb pot" in both and "Splash pot: 1.25USD" in both


def test_incomplete_hand_is_rejected() -> None:
    # Drop the winner events of a hand (as if capture stopped before showdown):
    # no collection -> the hand must be rejected, not imported truncated.
    events = [
        e
        for e in _load_events()
        if not (e[1] == "91426500343" and e[0] in ("game.winnerInfo", "game.cumulativeWinnerInfo"))
    ]
    hand_data = next(h for h in build_hands(events, "PLO4") if h["hand_id"] == "91426500343")
    assert not hand_data["collections"]
    with pytest.raises(CaptureNotImportableError):
        build_fpdb_hand(hand_data)


# --- how many chairs are at the table -----------------------------------------
#
# The stream is searched for the spellings that name the table -- maxSeats and
# tableSize -- and every one of them is offered until a plausible number comes
# out, so a field carrying nonsense cannot hide a good one appearing later.
#
# maxPlayers is not among them: on a tournament table it answers with the
# entrants the tournament accepts. A large one breaks the import outright on
# MySQL, where Gametypes.maxSeats is a TINYINT ("Out of range value for column
# 'maxSeats'"); a small one is worse, since it looks exactly like a table size.

from fpdb_3_legacy.coinpoker_hand_builder import MAX_TABLE_SEATS, MIN_TABLE_SEATS, _seat_count


@pytest.mark.parametrize("seats", [MIN_TABLE_SEATS, 6, 9, MAX_TABLE_SEATS])
def test_a_plausible_seat_count_is_taken(seats) -> None:
    assert _seat_count(seats, source="test") == seats
    assert _seat_count(str(seats), source="test") == seats


@pytest.mark.parametrize(
    "entrants",
    [128, 180, 1000, 2500],
    ids=["just past a TINYINT", "a small MTT", "a big MTT", "a huge MTT"],
)
def test_a_tournament_entrant_count_is_not_a_seat_count(entrants) -> None:
    """The reported failure: a field naming the whole tournament, not the table."""
    assert _seat_count(entrants, source="test") is None


@pytest.mark.parametrize("odd", [0, 1, 11, -6, None, "", "six", "6.5"])
def test_anything_that_cannot_be_a_table_is_refused(odd) -> None:
    assert _seat_count(odd, source="test") is None


def test_the_refused_value_and_where_it_came_from_are_logged(caplog) -> None:
    # So a capture says which field carried it, rather than only that the
    # import failed.
    with caplog.at_level(logging.WARNING):
        _seat_count(1000, source="the tournament events")

    assert "1000" in caplog.text
    assert "the tournament events" in caplog.text


def test_a_quiet_refusal_is_not_logged(caplog) -> None:
    # An absent field is the normal case and says nothing.
    with caplog.at_level(logging.WARNING):
        _seat_count(None, source="the table events")

    assert caplog.text == ""


def _as_tournament(events: list[tuple], **fields) -> list[tuple]:
    """The same hand, announced as a tournament table carrying `fields`.

    The event goes through the real reader, so which fields it trusts is what
    is under test rather than something stood in for it.
    """
    announcement = ("game.tournament_info", events[0][1], {"tournamentId": "116039100002", **fields})
    return [announcement, *events]


def test_a_tournament_is_recognised_from_its_own_event() -> None:
    hand = build_hands(_as_tournament(_load_straddle_events()), "PLO4")[0]

    assert hand["gametype"]["type"] == "tour"
    assert hand["tournament"]["tour_no"] == "116039100002"


def test_the_entrants_a_tournament_accepts_are_not_its_table_size() -> None:
    """The reported failure, end to end through the real reader."""
    events = _as_tournament(_load_straddle_events(), maxPlayers=1000)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == max(len(hand["players"]), MIN_TABLE_SEATS)
    assert MIN_TABLE_SEATS <= hand["gametype"]["maxSeats"] <= MAX_TABLE_SEATS


def test_a_small_entrant_count_is_not_borrowed_either() -> None:
    """What a range check alone would have let through.

    A nine-entrant tournament on a six-max table gives a number that looks
    like a table size, so refusing it cannot be a matter of how large it is.
    """
    events = _as_tournament(_load_straddle_events(), maxPlayers=9)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] != 9
    assert hand["gametype"]["maxSeats"] == max(len(hand["players"]), MIN_TABLE_SEATS)


@pytest.mark.parametrize("spelling", ["maxSeats", "tableSize"])
def test_a_field_naming_the_table_is_believed(spelling) -> None:
    events = _as_tournament(_load_straddle_events(), **{spelling: 9})

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == 9


def test_the_table_is_believed_over_the_tournament() -> None:
    events = _as_tournament(_load_straddle_events(), maxSeats=6, maxPlayers=1000)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == 6


def test_an_out_of_range_table_field_is_still_refused() -> None:
    # The range check stays useful for a field that does name the table.
    events = _as_tournament(_load_straddle_events(), maxSeats=1000)

    hand = build_hands(events, "PLO4")[0]

    assert MIN_TABLE_SEATS <= hand["gametype"]["maxSeats"] <= MAX_TABLE_SEATS

def test_a_nonsense_field_does_not_hide_a_good_one() -> None:
    """Validation decides which candidate is used, not where it appears.

    Returning the first value found and checking it afterwards threw away a
    perfectly good tableSize because a maxSeats earlier in the stream was
    describing something else.
    """
    events = _as_tournament(_load_straddle_events(), maxSeats=1000, tableSize=6)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == 6


def test_the_order_the_fields_arrive_in_does_not_matter() -> None:
    events = _as_tournament(_load_straddle_events(), tableSize=1000, maxSeats=6)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == 6


def test_two_nonsense_fields_fall_back_to_the_players_seated() -> None:
    events = _as_tournament(_load_straddle_events(), maxSeats=1000, tableSize=2500)

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == max(len(hand["players"]), MIN_TABLE_SEATS)


def test_a_later_event_can_supply_the_seat_count() -> None:
    # The bad value and the good one need not be in the same event.
    events = _as_tournament(_load_straddle_events(), maxSeats=1000)
    events.insert(1, ("game.table_info", events[0][1], {"tableSize": 6}))

    hand = build_hands(events, "PLO4")[0]

    assert hand["gametype"]["maxSeats"] == 6


def test_the_field_that_was_refused_is_named_in_the_log(caplog) -> None:
    events = _as_tournament(_load_straddle_events(), maxSeats=1000, tableSize=6)

    with caplog.at_level(logging.WARNING):
        build_hands(events, "PLO4")

    assert "maxSeats" in caplog.text
    assert "1000" in caplog.text



def test_a_cash_hand_still_reports_its_table_size() -> None:
    hand = _hand("91426500343")

    assert MIN_TABLE_SEATS <= hand["gametype"]["maxSeats"] <= MAX_TABLE_SEATS


# --- staying on the same tournament across a table move ------------------------
#
# The room says which tournament a table belongs to when the table is joined,
# and says it again when the player is moved. Nothing else identifies it: a
# hand that has to fall back names itself after its own table, which changes
# with the move, and the HUD then builds a second window for what it reads as
# a second tournament.
#
# The shapes below are taken from a captured tournament. roomProperties.id is
# the tournament; parentTournamentId is a level above and is the id of a
# *different* tournament -- the parent of one step is the step below it.

from fpdb_3_legacy.coinpoker_hand_builder import TOURNAMENT_JOIN_EVENT


def _join(table: str, tournament: str, name: str = "Step [3] to 565 Main Event [1E]", parent: str = "81498") -> tuple:
    return (
        TOURNAMENT_JOIN_EVENT,
        None,
        {
            "tableName": f"{name} {table}",
            "previousTableName": None,
            "roomProperties": {"id": tournament, "parentTournamentId": parent, "tournamentName": name},
        },
    )


def _at_table(events: list[tuple], table: str) -> list[tuple]:
    """The same hand, played at `table`."""
    hid = f"{table}00001"
    return [(name, hid if h else h, data) for name, h, data in events]


def test_the_tournament_is_the_one_the_room_named_on_joining() -> None:
    hands = build_hands([_join("1160391", "81499"), *_at_table(_load_straddle_events(), "1160391")], "PLO4")

    assert hands[0]["tournament"]["tour_no"] == "81499"


def test_the_parent_tournament_is_not_taken_for_the_tournament() -> None:
    """The parent of one step is the id of the step below it.

    Reading it would file two tournaments as one, and the places of the second
    would land on the players of the first.
    """
    hands = build_hands([_join("1160391", "81499", parent="81498"), *_at_table(_load_straddle_events(), "1160391")], "PLO4")

    assert hands[0]["tournament"]["tour_no"] != "81498"


def test_a_table_move_keeps_the_tournament_number() -> None:
    """The reported failure: two HUDs after being moved."""
    events = _load_straddle_events()
    carried: list[tuple] = []

    first = build_hands([_join("1160391", "81499"), *_at_table(events, "1160391")], "PLO4", session_context=carried)
    moved = build_hands([_join("1160377", "81499"), *_at_table(events, "1160377")], "PLO4", session_context=carried)

    assert first[0]["tournament"]["tour_no"] == moved[0]["tournament"]["tour_no"] == "81499"
    assert first[0]["table_id"] != moved[0]["table_id"]


def test_a_batch_after_the_join_still_knows_the_tournament() -> None:
    events = _load_straddle_events()
    carried: list[tuple] = []

    build_hands([_join("1160391", "81499")], "PLO4", session_context=carried)
    later = build_hands(_at_table(events, "1160391"), "PLO4", session_context=carried)

    assert later[0]["tournament"]["tour_no"] == "81499"


def test_two_tournaments_played_at_once_stay_apart() -> None:
    """A capture carries every table, so one identity for the session is wrong."""
    events = _load_straddle_events()
    carried: list[tuple] = []

    build_hands([_join("1160391", "81499"), _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]")],
                "PLO4", session_context=carried)
    step3 = build_hands(_at_table(events, "1160391"), "PLO4", session_context=carried)
    step2 = build_hands(_at_table(events, "1161142"), "PLO4", session_context=carried)

    assert step3[0]["tournament"]["tour_no"] == "81499"
    assert step2[0]["tournament"]["tour_no"] == "81498"


def test_a_table_nobody_joined_is_a_ring_game() -> None:
    """A ring table played alongside a tournament stays a ring table.

    Not merely "a different tournament number": a hand wrongly read as a
    tournament has its chips stored as tournament chips, joins a tournament
    that was never played, and shows up in tournament results.
    """
    events = _load_straddle_events()
    carried: list[tuple] = []

    build_hands([_join("1160391", "81499")], "PLO4", session_context=carried)
    (elsewhere,) = build_hands(_at_table(events, "981279"), "PLO4", session_context=carried)

    assert elsewhere["tournament"] is None
    assert elsewhere["gametype"]["type"] == "ring"
    assert elsewhere["gametype"]["currency"] == "USD"


def test_the_tournament_port_does_not_make_a_ring_table_a_tournament() -> None:
    """The lobby connection is the capture's, not the table's.

    Every event off the tournament port carries it, and those events name no
    table, so a capture watching a tournament lobby while a ring game is on
    would otherwise read the port as proof that the ring table is a
    tournament -- the same leak as the generic markers, through the one
    marker that is a property of the socket rather than of the hand.
    """
    events = _load_straddle_events()
    lobby = ("tournamentlobby.info", None, {"_coinpokerServerPort": 3001})

    (elsewhere,) = build_hands([lobby, *_at_table(events, "981279")], "PLO4")

    assert elsewhere["tournament"] is None
    assert elsewhere["gametype"]["type"] == "ring"
    assert elsewhere["gametype"]["currency"] == "USD"


def test_a_carried_tournament_id_does_not_reach_another_table() -> None:
    """The lobby says "tournament 77" without saying whose table.

    It travels with every hand of the capture, so read as a number it would
    file a ring game's hands under a tournament that was never played -- and,
    between two tournaments, put one's hands under the other's number. Only
    the join names a table, and a table-less marker is read only when there
    is a single table for it to be about.
    """
    events = _load_straddle_events()
    lobby = (
        "game.tournament_message",
        None,
        {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
    )

    hands = build_hands(
        [lobby, *_at_table(events, "1160391"), *_at_table(events, "981279")],
        "PLO4",
    )

    by_table = {hand["tournament"]["table_id"] if hand["tournament"] else None: hand for hand in hands}
    assert by_table[None]["gametype"]["type"] == "ring"
    assert by_table[None]["gametype"]["currency"] == "USD"
    assert "77" not in {(hand["tournament"] or {}).get("tour_no") for hand in hands}


def test_a_lone_hand_in_a_sweep_is_not_a_lone_table() -> None:
    """Most sweeps hold one hand, whatever is being played.

    The capture re-reads its buffer every twenty events, so a batch carrying a
    single table is the normal case, not evidence that the capture has one.
    Deciding on the batch let a carried marker name the tournament of whatever
    hand happened to be alone in that sweep -- a ring hand included.
    """
    events = _load_straddle_events()
    lobby = (
        "game.tournament_message",
        None,
        {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
    )
    carried: list[tuple] = []
    tables: set[str] = set()

    # Sweep one: the tournament table, and the marker arrives with it.
    build_hands([lobby, *_at_table(events, "1160391")], "PLO4", session_context=carried, session_tables=tables)
    # Sweep two: a ring hand, alone in its batch.
    (elsewhere,) = build_hands(
        _at_table(events, "981279"),
        "PLO4",
        session_context=carried,
        session_tables=tables,
    )

    assert elsewhere["tournament"] is None
    assert elsewhere["gametype"]["type"] == "ring"
    assert elsewhere["gametype"]["currency"] == "USD"


def test_a_carried_tournament_id_still_names_a_lone_table() -> None:
    # The control: with one table there is nothing for the marker to be
    # confused with, and a room that never sends a join still has its
    # tournament recognised.
    events = _load_straddle_events()
    lobby = (
        "game.tournament_message",
        None,
        {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
    )

    (alone,) = build_hands([lobby, *_at_table(events, "1160391")], "PLO4")

    assert alone["tournament"]["tour_no"] == "77"


def test_the_joined_table_is_still_a_tournament_alongside_it() -> None:
    # The control: the same context must not stop the joined table being one.
    events = _load_straddle_events()
    carried: list[tuple] = []

    build_hands([_join("1160391", "81499")], "PLO4", session_context=carried)
    (joined,) = build_hands(_at_table(events, "1160391"), "PLO4", session_context=carried)

    assert joined["tournament"]["tour_no"] == "81499"
    assert joined["gametype"]["type"] == "tour"
    assert joined["gametype"]["currency"] == "T$"


def test_rejoining_a_table_replaces_what_it_was_told_before() -> None:
    events = _load_straddle_events()
    carried: list[tuple] = []

    build_hands([_join("1160391", "81499")], "PLO4", session_context=carried)
    build_hands([_join("1160391", "90000")], "PLO4", session_context=carried)
    hands = build_hands(_at_table(events, "1160391"), "PLO4", session_context=carried)

    assert hands[0]["tournament"]["tour_no"] == "90000"
    assert len(carried) == 1


def test_a_capture_given_no_list_still_reads_its_own_batch() -> None:
    hands = build_hands([_join("1160391", "81499"), *_at_table(_load_straddle_events(), "1160391")], "PLO4")

    assert hands[0]["tournament"]["tour_no"] == "81499"


def test_naming_a_hand_after_its_table_is_logged(caplog) -> None:
    # A tournament that never named itself: the table's number stands in, and
    # that leaves the HUD identity unstable, so it is not silent.
    events = _load_straddle_events()
    hid = "116039100001"
    nameless = [("game.tournament_state", hid, {"level": 3}), *_at_table(events, "1160391")]

    with caplog.at_level(logging.WARNING):
        hands = build_hands(nameless, "PLO4")

    assert hands[0]["tournament"]["tour_no"] == "1160391"
    assert "1160391" in caplog.text


# --- where everyone finished ---------------------------------------------------
#
# The room announces the finishing places once the tournament closes, in an
# event of its own carrying no hand id, after the last hand has been played.
# The shapes below are taken from a captured tournament: a satellite paying 35
# places, every one of them a seat in another tournament rather than money.

from fpdb_3_legacy.coinpoker_hand_builder import TOURNAMENT_RESULT_EVENT, tournament_results


def _winner_event(*winners: dict) -> tuple:
    return (TOURNAMENT_RESULT_EVENT, None, {"winnerList": list(winners), "initTimeStamp": "1785155715131"})


def _winner(rank: int, name: str, prize: str = "Ticket") -> dict:
    return {
        "rank": rank,
        "name": name,
        "prize": prize,
        "coinTypeId": 8,
        "playerId": 166755,
        "dealMakingAccepted": False,
        "isPlayerBubbleProtected": False,
        "bountyAmount": "0",
    }


def test_the_finishing_places_are_read() -> None:
    events = [_winner_event(_winner(1, "jeje1976"), _winner(2, "Alisey"))]

    assert [(r["player"], r["rank"]) for r in tournament_results(events)] == [("jeje1976", 1), ("Alisey", 2)]


def test_what_was_won_is_named_rather_than_valued() -> None:
    """Only the place is reported, whatever the prize looks like.

    fpdb stores winnings as an integer number of cents in a named currency,
    and nothing in the capture says what a number here would be denominated
    in. A wrong unit reads as a real result; no number reads as no number.
    """
    (ticket,) = tournament_results([_winner_event(_winner(1, "jeje1976", prize="Ticket"))])
    (money,) = tournament_results([_winner_event(_winner(1, "jeje1976", prize="565.50"))])

    assert ticket == {"player": "jeje1976", "rank": 1, "prize": "Ticket"}
    assert money == {"player": "jeje1976", "rank": 1, "prize": "565.50"}
    assert "winnings" not in ticket


def test_an_entry_without_a_place_is_skipped() -> None:
    events = [_winner_event({"name": "jeje1976"}, _winner(2, "Alisey"))]

    assert [r["player"] for r in tournament_results(events)] == ["Alisey"]


def test_an_entry_without_a_name_is_skipped() -> None:
    events = [_winner_event(_winner(1, ""), _winner(2, "Alisey"))]

    assert [r["player"] for r in tournament_results(events)] == ["Alisey"]


def test_a_stream_that_never_announces_anything_reports_nothing() -> None:
    assert tournament_results(_load_straddle_events()) == []


def test_hands_and_places_are_read_from_the_same_stream() -> None:
    # The announcement carries no hand id, so it must not disturb the hands.
    events = [*_load_straddle_events(), _winner_event(_winner(1, "jeje1976"))]

    assert len(build_hands(events, "PLO4")) == 1
    assert len(tournament_results(events)) == 1
