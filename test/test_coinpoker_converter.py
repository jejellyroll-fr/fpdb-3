"""Tests for the CoinPoker protocol decoder and hand converter.

Fixture ``data/coinpoker_hand_events.json`` holds the decoded ``game.*`` events
of two real captured hands (player names anonymized). Hand 91426500343 is
complete; 91426500344 was still in progress when capture stopped and must be
rejected rather than imported truncated.
"""

from __future__ import annotations

import json
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
from fpdb_3_legacy.SQL import Sql

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"


def _load_events() -> list[tuple]:
    raw = json.loads(FIXTURE.read_text())
    return [tuple(e) for e in raw]


def _hand(hand_id: str) -> dict:
    hands = build_hands(_load_events(), "PLO4")
    return next(h for h in hands if h["hand_id"] == hand_id)


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
    assert _tournament_info(events)["tour_no"] == "77"


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
