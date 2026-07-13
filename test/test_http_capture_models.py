import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiReplayer import GuiReplayer
from fpdb_3_legacy.http_capture_analyze import analyze_raw_archive
from fpdb_3_legacy.http_capture_archive import JsonHandArchive, JsonlRawCaptureArchive
from fpdb_3_legacy.http_capture_build import build_capture_file
from fpdb_3_legacy.http_capture_db_import import import_http_capture_directory, import_http_capture_file
from fpdb_3_legacy.http_capture_diff import diff_snapshot_steps
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    build_fpdb_hand,
    build_hand_input,
    build_hand_operations,
    execute_hand_operations,
    import_fpdb_hand,
    plan_hand_build,
    render_fpdb_hand,
    summarize_fpdb_hand,
    validate_hand_operations,
)
from fpdb_3_legacy.http_capture_importability import evaluate_capture_importability
from fpdb_3_legacy.http_capture_models import RawCaptureMessage, swc_game_definition
from fpdb_3_legacy.http_capture_ofc import (
    build_ofc_hand,
    import_ofc_hand,
    load_ofc_hand,
    ofc_hand_from_dict,
    query_ofc_player_stats,
    reconstruct_ofc_rounds,
    render_ofc_hand_html,
    render_ofc_hand_text,
)
from fpdb_3_legacy.http_capture_refresh import refresh_normalized_hand
from fpdb_3_legacy.http_capture_registry import get_http_capture_adapter, registered_http_capture_sites
from fpdb_3_legacy.http_capture_replay import replay_raw_archive, replay_swc_raw_archive
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.swc_http_adapter import (
    SwCHttpAdapter,
    describe_socketio_frame,
    extract_game_state_from_socketio,
    extract_socketio_proxy_message,
    extract_swc_game_state_message,
)


def test_swc_holdem_maps_to_hand_gametype_and_streets():
    game = swc_game_definition(72)

    assert game.base == "hold"
    assert game.category == "holdem"
    assert game.limit_type == "nl"
    assert game.street_profile.to_dict() == {
        "allStreets": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        "actionStreets": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        "holeStreets": ["PREFLOP"],
        "communityStreets": ["FLOP", "TURN", "RIVER"],
        "discardStreets": ["PREFLOP"],
    }
    assert game.gametype(small_blind="0.01", big_blind="0.02")["sb"] == Decimal("0.01")


def test_swc_triple_draw_uses_draw_hand_streets():
    game = swc_game_definition(21)

    assert game.base == "draw"
    assert game.category == "27_3draw"
    assert game.street_profile.to_dict()["actionStreets"] == [
        "BLINDSANTES",
        "DEAL",
        "DRAWONE",
        "DRAWTWO",
        "DRAWTHREE",
    ]


def test_swc_stud_uses_stud_hand_streets():
    game = swc_game_definition(11)

    assert game.base == "stud"
    assert game.category == "studhilo"
    assert game.street_profile.to_dict()["holeStreets"] == [
        "THIRD",
        "FOURTH",
        "FIFTH",
        "SIXTH",
        "SEVENTH",
    ]


def test_swc_ofc_is_capture_only_not_fpdb_hand_supported():
    game = swc_game_definition(74)

    assert game.base == "ofc"
    assert game.category == "ofcp"
    assert game.fpdb_supported is False


def test_unknown_swc_game_is_explicitly_unsupported():
    game = swc_game_definition(9999)

    assert game.base == "unknown"
    assert game.category == "unknown"
    assert game.fpdb_supported is False


def test_observed_swc_capture_only_game_codes_are_named():
    six_card = swc_game_definition(50)
    assert six_card.label == "6 Card Omaha"
    assert six_card.base == "hold"
    assert six_card.category == "6_omahahi"
    assert six_card.fpdb_supported is True

    ofc_variant = swc_game_definition(77)
    assert ofc_variant.base == "ofc"
    assert ofc_variant.category == "ofcp"
    assert ofc_variant.fpdb_supported is False

    ofc_short_variant = swc_game_definition(84)
    assert ofc_short_variant.base == "ofc"
    assert ofc_short_variant.category == "ofc"
    assert ofc_short_variant.fpdb_supported is False


def _socketio_frame(game_state):
    return "42/poker/," + json.dumps(["proxy-message", json.dumps({"t": "GameState", "gameState": game_state})])


def _socketio_frame_with_events(game_state, events):
    return "42/poker/," + json.dumps(
        ["proxy-message", json.dumps({"t": "GameState", "gameState": game_state, "events": events})]
    )


def _socketio_proxy_frame(message):
    return "42/poker/," + json.dumps(["proxy-message", json.dumps(message)])


def _sample_game_state(**overrides):
    state = {
        "gi": 12345,
        "gt": 72,
        "ti": "table-1",
        "ts": 2,
        "m": {"di": 0, "sb": 1, "bb": 2},
        "d": {"c": "0;1;2", "p": 300},
        "s": [
            {"n": "alice", "c": 10000, "b": 100, "d": "48;49"},
            {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
        ],
    }
    state.update(overrides)
    return state


def _three_player_preflop_state(**overrides):
    state = {
        "gi": 555,
        "gt": 72,
        "ti": "table-2",
        "ts": 2,
        "m": {"di": 2, "sb": 0, "bb": 1},
        "d": {"c": "", "p": 300},
        "s": [
            {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
            {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    }
    state.update(overrides)
    return state


def _ofc_state(**overrides):
    state = {
        "gi": 777001,
        "gt": 77,
        "ti": "ofc-table",
        "ts": 2,
        "m": {"di": 0, "sb": -1, "bb": -1},
        "d": {"c": "", "p": 0},
        "s": [
            {"n": "alice", "c": 10000, "b": 0, "p": 0, "d": "0;1;2;3;4-1-2-2"},
            {"n": "bob", "c": 10000, "b": 0, "p": 0, "d": "13;14;15;16;17-1-2-2"},
        ],
    }
    state.update(overrides)
    return state


def test_swc_socketio_frame_extracts_game_state():
    state = _sample_game_state()
    adapter = SwCHttpAdapter()

    frame = _socketio_frame(state)
    assert extract_socketio_proxy_message(frame)["t"] == "GameState"
    assert extract_socketio_proxy_message(_socketio_proxy_frame({"t": "Action", "a": "call"})) == {"t": "Action", "a": "call"}
    assert describe_socketio_frame(frame)["message_type"] == "GameState"
    assert describe_socketio_frame('42/poker/,["client-action",{"a":"call"}]') == {
        "message_type": "socketio:client-action",
        "socketio_event": "client-action",
    }
    assert describe_socketio_frame("2") == {"message_type": "socketio_opcode_2"}
    assert extract_game_state_from_socketio(frame) == state
    assert extract_swc_game_state_message(_socketio_frame_with_events(state, [{"type": 9, "action": 2}])) == {
        "gameState": state,
        "events": [{"type": 9, "action": 2}],
        "proxy": {"t": "GameState", "gameState": state, "events": [{"type": 9, "action": 2}]},
    }
    assert adapter.identify_message(frame)
    assert adapter.extract_hand_id(frame) == 12345
    assert adapter.extract_game_definition(frame).category == "holdem"
    assert extract_game_state_from_socketio("noise") is None


def test_swc_adapter_reconstructs_explicit_game_state_events():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        d={"c": "", "p": 0},
        s=[
            {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
            {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    )
    second = _three_player_preflop_state(
        d={"c": "", "p": 0},
        s=[
            {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
            {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
            {"n": "carol", "c": 9600, "b": 400, "d": "40;41"},
        ],
    )
    third = _three_player_preflop_state(
        d={"c": "", "p": 900},
        s=[
            {"n": "alice", "c": 9700, "b": 0, "d": "48;49"},
            {"n": "bob", "c": 9800, "b": 0, "d": "44;45"},
            {"n": "carol", "c": 9600, "b": 0, "d": "40;41"},
        ],
    )

    adapter.process_socketio_frame(
        _socketio_frame_with_events(
            first,
            [
                {"type": 9, "action": 6, "amount": 100, "seat-idx": 0},
                {"type": 9, "action": 7, "amount": 200, "seat-idx": 1},
            ],
        ),
        raw_ref="raw:1",
    )
    adapter.process_socketio_frame(
        _socketio_frame_with_events(second, [{"type": 9, "action": 9, "amount": 400, "seat-idx": 2}]),
        raw_ref="raw:2",
    )
    result = adapter.process_socketio_frame(
        _socketio_frame_with_events(
            third,
            [
                {"type": 9, "action": 3, "amount": 300, "seat-idx": 0},
                {"type": 9, "action": 1, "amount": 0, "seat-idx": 1},
            ],
        ),
        raw_ref="raw:3",
    )

    hand = result.current_hand
    assert hand["actions"] == [
        {
            "street": "BLINDSANTES",
            "player": "alice",
            "source": "swc_game_state_event",
            "swc_event_type": 9,
            "swc_action": 6,
            "step_num": 1,
            "fpdb_action": True,
            "type": "small blind",
            "amount": "1",
        },
        {
            "street": "BLINDSANTES",
            "player": "bob",
            "source": "swc_game_state_event",
            "swc_event_type": 9,
            "swc_action": 7,
            "step_num": 1,
            "fpdb_action": True,
            "type": "big blind",
            "amount": "2",
        },
        {
            "street": "PREFLOP",
            "player": "carol",
            "source": "swc_game_state_event",
            "swc_event_type": 9,
            "swc_action": 9,
            "step_num": 2,
            "fpdb_action": True,
            "type": "raises",
            "amount": "4",
            "to": "4",
        },
        {
            "street": "PREFLOP",
            "player": "alice",
            "source": "swc_game_state_event",
            "swc_event_type": 9,
            "swc_action": 3,
            "step_num": 3,
            "fpdb_action": True,
            "type": "calls",
            "amount": "3",
        },
        {
            "street": "PREFLOP",
            "player": "bob",
            "source": "swc_game_state_event",
            "swc_event_type": 9,
            "swc_action": 1,
            "step_num": 3,
            "fpdb_action": True,
            "type": "folds",
        },
    ]
    assert hand["metadata"]["action_reconstruction"]["status"] == "complete"
    assert hand["metadata"]["action_reconstruction"]["source"] == "swc_game_state_events"


def test_swc_adapter_normalizes_ofc_rounds_and_result_without_hand_py_import():
    adapter = SwCHttpAdapter()
    adapter.process_socketio_frame(
        _socketio_frame_with_events(_ofc_state(), [{"type": 9, "action": 21, "amount": 0, "seat-idx": 0}]),
        raw_ref="raw:1",
    )
    final_state = _ofc_state(
        ts=0,
        ss={"hc": "Pair\tTwo Pair\tStraight\nHigh Card\tPair\tFlush"},
        s=[
            {
                "n": "alice",
                "c": 10500,
                "b": 0,
                "p": 5,
                "d": "0;1;2;3;4;5;6;7;8;9;10;11;12-3-5-5",
                "chihr": [{"e": 1, "h": [{"h": 0, "b": 2}, {"h": 1, "b": 3}, {"h": 2, "b": 4}]}],
            },
            {
                "n": "bob",
                "c": 9500,
                "b": 0,
                "p": -5,
                "d": "13;14;15;16;17;18;19;20;21;22;23;24;25-3-5-5",
                "chihr": [{"e": -1, "h": [{"h": 0, "b": 0}, {"h": 1, "b": 0}, {"h": 2, "b": 0}]}],
            },
        ],
    )

    result = adapter.process_socketio_frame(
        _socketio_frame_with_events(
            final_state,
            [{"type": 15, "action": 0, "amount": 0, "seat-idx": 0, "table-msg": '<nick s="0">alice</nick> wins <money a="500" mt="R">5</money>'}],
        ),
        raw_ref="raw:2",
    )

    hand = result.current_hand
    assert hand["game"]["base"] == "ofc"
    assert hand["ofc_variant"] == {
        "family": "ofc",
        "variant": "ofcp",
        "pineapple": True,
        "deuce_to_seven": False,
        "rows": {"top": 3, "middle": 5, "bottom": 5},
        "hand_py_importable": False,
    }
    assert hand["ofc_rounds"][0]["player"] == "alice"
    assert hand["ofc_rounds"][0]["placed"] == {"top": ["2c"], "middle": ["2d", "2h"], "bottom": ["2s", "3c"]}
    assert any(round_info["player"] == "alice" and round_info["placed"]["top"] == ["2d", "2h"] for round_info in hand["ofc_rounds"])
    assert hand["ofc_result"]["points_settled"] == {"alice": 5, "bob": -5}
    assert hand["ofc_result"]["rows"]["alice"]["top"] == "Pair"
    assert hand["ofc_result"]["points_breakdown"]["alice"]["total"] == 10
    assert hand["ofc_result"]["collections"] == [
        {"player": "alice", "pot": "5", "street": "UNKNOWN", "source": "swc_game_state_event", "step_num": 2}
    ]
    assert hand["ofc_validation"]["valid"] is True
    assert hand["metadata"]["ofc_reconstruction"]["status"] == "complete"
    assert hand["metadata"]["importability"] == {
        "importable": False,
        "status": "capture_only",
        "reasons": ["OFC requires a dedicated importer/replayer"],
    }


def test_swc_adapter_reports_ofc_layout_validation_errors():
    adapter = SwCHttpAdapter()

    result = adapter.process_game_state(
        _ofc_state(s=[{"n": "alice", "c": 10000, "b": 0, "p": 0, "d": "0;1;2;3-4-0-0"}]),
        captured_at="2026-06-28T10:00:00Z",
    )

    hand = result.current_hand
    assert hand["ofc_validation"]["valid"] is False
    assert hand["metadata"]["importability"] == {
        "importable": False,
        "status": "capture_only",
        "reasons": ["OFC layout validation failed", "OFC requires a dedicated importer/replayer"],
    }


def _normalized_complete_ofc_hand():
    adapter = SwCHttpAdapter()
    adapter.process_socketio_frame(
        _socketio_frame_with_events(_ofc_state(), [{"type": 9, "action": 21, "amount": 0, "seat-idx": 0}]),
        raw_ref="raw:1",
    )
    final_state = _ofc_state(
        ts=0,
        ss={"hc": "Pair\tTwo Pair\tStraight\nHigh Card\tPair\tFlush"},
        s=[
            {
                "n": "alice",
                "c": 10500,
                "b": 0,
                "p": 5,
                "d": "0;1;2;3;4;5;6;7;8;9;10;11;12-3-5-5",
                "chihr": [{"e": 1, "h": [{"h": 0, "b": 2}, {"h": 1, "b": 3}, {"h": 2, "b": 4}]}],
            },
            {
                "n": "bob",
                "c": 9500,
                "b": 0,
                "p": -5,
                "d": "13;14;15;16;17;18;19;20;21;22;23;24;25-3-5-5",
                "chihr": [{"e": -1, "h": [{"h": 0, "b": 0}, {"h": 1, "b": 0}, {"h": 2, "b": 0}]}],
            },
        ],
    )
    return adapter.process_socketio_frame(
        _socketio_frame_with_events(
            final_state,
            [{"type": 15, "action": 0, "amount": 0, "seat-idx": 0, "table-msg": '<nick s="0">alice</nick> wins <money a="500" mt="R">5</money>'}],
        ),
        raw_ref="raw:2",
    ).current_hand


def test_ofc_hand_model_and_visual_renderers_from_normalized_capture():
    ofc_hand = build_ofc_hand(_normalized_complete_ofc_hand())

    assert ofc_hand.hand_id == 777001
    assert ofc_hand.variant["variant"] == "ofcp"
    assert ofc_hand.players[0].name == "alice"
    assert ofc_hand.players[0].top == ["2c", "2d", "2h"]
    assert ofc_hand.players[0].middle == ["2s", "3c", "3d", "3h", "3s"]
    assert ofc_hand.players[0].bottom == ["4c", "4d", "4h", "4s", "5c"]
    assert ofc_hand.players[0].points == Decimal("5")
    assert ofc_hand.players[0].collected == Decimal("5")

    text = render_ofc_hand_text(ofc_hand)
    assert "OFC Hand #777001" in text
    assert "Top: 2c 2d 2h" in text
    assert "Rounds:" in text

    html = render_ofc_hand_html(ofc_hand)
    assert 'class="ofc-replayer"' in html
    assert "OFC Hand #777001" in html
    assert "2c 2d 2h" in html


@pytest.mark.parametrize("missing_key", ["site", "hand_id"])
def test_ofc_hand_requires_persistent_identity(missing_key):
    normalized = _normalized_complete_ofc_hand()
    normalized.pop(missing_key)

    with pytest.raises(ValueError, match="requires site and hand_id"):
        build_ofc_hand(normalized)

    serialized = build_ofc_hand(_normalized_complete_ofc_hand()).to_dict()
    serialized.pop(missing_key)
    with pytest.raises(ValueError, match="requires site and hand_id"):
        ofc_hand_from_dict(serialized)


def test_ofc_hand_imports_into_dedicated_sqlite_tables_and_stats():
    ofc_hand = build_ofc_hand(_normalized_complete_ofc_hand())
    db = Database(_memory_db_config(), Sql(db_server="sqlite"))

    row_id = import_ofc_hand(db, ofc_hand)

    assert row_id == 1
    cursor = db.get_cursor()
    cursor.execute("select count(*) from HttpOFCHands")
    assert cursor.fetchone()[0] == 1
    cursor.execute("select count(*) from HttpOFCPlayers")
    assert cursor.fetchone()[0] == 2
    cursor.execute("select count(*) from HttpOFCRounds")
    assert cursor.fetchone()[0] == len(ofc_hand.rounds)

    assert query_ofc_player_stats(db) == [
        {"player": "alice", "hands": 1, "points": Decimal("5.0"), "collected": Decimal("5.0")},
        {"player": "bob", "hands": 1, "points": Decimal("-5.0"), "collected": Decimal("0")},
    ]

    replacement_id = import_ofc_hand(db, ofc_hand)
    assert replacement_id == 2
    cursor.execute("select count(*) from HttpOFCHands")
    assert cursor.fetchone()[0] == 1
    cursor.execute("select count(*) from HttpOFCPlayers")
    assert cursor.fetchone()[0] == 2


def test_ofc_hand_loads_from_db_for_gui_replayer_entry():
    ofc_hand = build_ofc_hand(_normalized_complete_ofc_hand())
    db = Database(_memory_db_config(), Sql(db_server="sqlite"))
    row_id = import_ofc_hand(db, ofc_hand)

    loaded = load_ofc_hand(db, f"{row_id}")

    assert loaded.hand_id == ofc_hand.hand_id
    assert loaded.players[0].top == ["2c", "2d", "2h"]
    assert loaded.rounds == ofc_hand.rounds


def test_ofc_round_reconstruction_ignores_empty_non_actor_snapshots_and_keeps_slots():
    hand_data = {
        "steps": [
            {
                "step_num": 1,
                "placed": {
                    "Liqthenit": {
                        "top": ["--", "--", "--"],
                        "middle": ["2h", "--", "--", "--", "--"],
                        "bottom": ["Ah", "Kh", "Qh", "10h", "--"],
                        "active": [],
                    },
                    "Orcfi": {
                        "top": ["--", "--", "--"],
                        "middle": ["--", "--", "--", "--", "--"],
                        "bottom": ["--", "--", "--", "--", "--"],
                        "active": [],
                    },
                },
            },
            {
                "step_num": 2,
                "placed": {
                    "Liqthenit": {
                        "top": ["--", "--", "--"],
                        "middle": ["--", "--", "--", "--", "--"],
                        "bottom": ["--", "--", "--", "--", "--"],
                        "active": [],
                    },
                    "Orcfi": {
                        "top": ["Ac", "--", "--"],
                        "middle": ["Js", "6d", "3h", "--", "--"],
                        "bottom": ["Qs", "Qc", "9d", "--", "--"],
                        "active": [],
                    },
                },
            },
            {
                "step_num": 3,
                "placed": {
                    "Liqthenit": {
                        "top": ["--", "--", "--"],
                        "middle": ["8c", "2h", "--", "--", "--"],
                        "bottom": ["Ah", "Kh", "Qh", "Jh", "10h"],
                        "active": [],
                    }
                },
            },
        ]
    }

    rounds = reconstruct_ofc_rounds(hand_data)

    assert rounds[0]["placed"] == {"middle": ["2h"], "bottom": ["Ah", "Kh", "Qh", "10h"]}
    assert rounds[0]["placed_slots"]["middle"] == [{"index": 0, "card": "2h"}]
    assert rounds[2]["placed"] == {"middle": ["8c"], "bottom": ["Jh"]}
    assert rounds[2]["placed_slots"] == {
        "middle": [{"index": 0, "card": "8c"}],
        "bottom": [{"index": 3, "card": "Jh"}],
    }


def test_http_capture_ofc_file_import_returns_stable_db_replay_ref(tmp_path):
    hand_data = _normalized_complete_ofc_hand()
    source = tmp_path / "hand_777001.json"
    source.write_text(json.dumps(hand_data, default=str), encoding="utf-8")
    db = Database(_memory_db_config(), Sql(db_server="sqlite"))

    result = import_http_capture_file(db, source)

    assert result.status == "imported"
    assert result.kind == "ofc"
    assert result.site_hand_no == "777001"
    assert result.row_id == 1
    assert result.replay_ref == "ofc:777001"
    loaded = load_ofc_hand(db, result.replay_ref.split(":", 1)[1])
    assert loaded.hand_id == hand_data["hand_id"]


def test_http_capture_directory_import_imports_all_ofc_json_files(tmp_path):
    hand_data = _normalized_complete_ofc_hand()
    second = json.loads(json.dumps(hand_data, default=str))
    second["hand_id"] = 777002
    (tmp_path / "hand_777001.json").write_text(json.dumps(hand_data, default=str), encoding="utf-8")
    (tmp_path / "hand_777002.json").write_text(json.dumps(second, default=str), encoding="utf-8")
    db = Database(_memory_db_config(), Sql(db_server="sqlite"))

    results = import_http_capture_directory(db, tmp_path)

    assert [result.replay_ref for result in results] == ["ofc:777001", "ofc:777002"]
    assert load_ofc_hand(db, "777001").hand_id == 777001
    assert load_ofc_hand(db, "777002").hand_id == 777002


def test_gui_replayer_builds_ofc_replay_model_without_hand_factory():
    ofc_hand = build_ofc_hand(_normalized_complete_ofc_hand())

    assert GuiReplayer._is_ofc_replay_entry(None, ofc_hand)
    assert GuiReplayer._is_ofc_replay_entry(None, {"game": {"base": "ofc"}})
    assert GuiReplayer._is_ofc_replay_entry(None, "ofc:1")

    replayer = GuiReplayer.__new__(GuiReplayer)
    model = replayer._build_ofc_replay_model(ofc_hand)

    assert model.hand is ofc_hand
    assert model.info == "OFCP hand n° 777001 played on SealsWithClubs"
    assert len([state for state in model.states if state.phase == "place"]) == len(ofc_hand.rounds)
    assert len(model.states) >= len(ofc_hand.rounds) + 1
    first_player = ofc_hand.rounds[0]["player"]
    first_place_state = next(state for state in model.states if state.phase == "place")
    assert first_place_state.current_round == ofc_hand.rounds[0]
    assert {
        row: [card for card in cards if card != "--"]
        for row, cards in first_place_state.visible_rows[first_player].items()
    } == ofc_hand.rounds[0]["placed"]
    assert first_place_state.placed_cards == [card for cards in ofc_hand.rounds[0]["placed"].values() for card in cards]
    assert model.states[-1].phase == "result"
    assert all(
        not any(card and card != "--" for cards in rows.values() for card in cards)
        for player, rows in first_place_state.visible_rows.items()
        if player != first_player
    )
    assert "ROUND1" in model.seen_streets


def test_gui_replayer_uses_private_ofc_deal_phase_only_when_capture_has_dealt_cards():
    normalized = _normalized_complete_ofc_hand()
    normalized["ofc_rounds"] = [
        {
            "round": 1,
            "step_num": 1,
            "player": "alice",
            "dealt": ["2c", "2d", "2h"],
            "placed": {},
            "discarded": [],
            "active": ["2c", "2d", "2h"],
            "source": "test",
        },
        {
            "round": 2,
            "step_num": 2,
            "player": "alice",
            "dealt": [],
            "placed": {"top": ["2c"], "middle": ["2d"], "bottom": ["2h"]},
            "discarded": [],
            "active": [],
            "source": "test",
        },
    ]
    ofc_hand = build_ofc_hand(normalized)
    replayer = GuiReplayer.__new__(GuiReplayer)

    model = replayer._build_ofc_replay_model(ofc_hand)

    assert [state.phase for state in model.states] == ["deal", "place", "place", "result"]
    assert model.states[0].pending_cards == ["2c", "2d", "2h"]
    assert not any(
        card and card != "--"
        for row in ("top", "middle", "bottom")
        for card in model.states[0].visible_rows["alice"][row]
    )
    assert model.states[2].placed_cards == ["2c", "2d", "2h"]
    assert model.states[2].visible_rows["alice"] == {
        "top": ["2c", "--", "--"],
        "middle": ["2d", "--", "--", "--", "--"],
        "bottom": ["2h", "--", "--", "--", "--"],
    }


def test_gui_replayer_models_ofcp_public_initial_five_then_private_three():
    normalized = _normalized_complete_ofc_hand()
    normalized["ofc_variant"]["pineapple"] = True
    normalized["players"] = [{"name": "alice", "seat_idx": 0, "starting_stack": "100"}]
    normalized["ofc_rounds"] = [
        {
            "round": 1,
            "step_num": 1,
            "player": "alice",
            "dealt": [],
            "placed": {"top": ["As"], "middle": ["Kd"], "bottom": ["Qh", "Jh", "10h"]},
            "placed_slots": {
                "top": [{"index": 1, "card": "As"}],
                "middle": [{"index": 0, "card": "Kd"}],
                "bottom": [{"index": 0, "card": "Qh"}, {"index": 1, "card": "Jh"}, {"index": 2, "card": "10h"}],
            },
            "layout": {"top": ["--", "As", "--"], "middle": ["Kd", "--", "--", "--", "--"], "bottom": ["Qh", "Jh", "10h", "--", "--"]},
            "discarded": [],
            "active": [],
            "source": "test",
        },
        {
            "round": 2,
            "step_num": 2,
            "player": "alice",
            "dealt": [],
            "placed": {"middle": ["2c"], "bottom": ["3d"]},
            "placed_slots": {"middle": [{"index": 1, "card": "2c"}], "bottom": [{"index": 3, "card": "3d"}]},
            "layout": {"top": ["--", "As", "--"], "middle": ["Kd", "2c", "--", "--", "--"], "bottom": ["Qh", "Jh", "10h", "3d", "--"]},
            "discarded": [],
            "active": [],
            "source": "test",
        },
    ]
    ofc_hand = build_ofc_hand(normalized)
    replayer = GuiReplayer.__new__(GuiReplayer)

    model = replayer._build_ofc_replay_model(ofc_hand)

    assert [state.phase for state in model.states] == ["deal", "place", "deal", "place", "result"]
    assert model.states[0].pending_cards == ["As", "Kd", "Qh", "Jh", "10h"]
    assert model.states[0].private_pending is False
    assert model.states[2].pending_cards == ["0", "0", "0"]
    assert model.states[2].private_pending is True
    assert model.states[3].placed_cards == ["2c", "3d"]
    assert model.states[3].visible_rows["alice"]["middle"] == ["Kd", "2c", "--", "--", "--"]
    assert model.states[3].visible_rows["alice"]["bottom"] == ["Qh", "Jh", "10h", "3d", "--"]


def test_swc_adapter_extracts_collections_from_event_table_messages():
    adapter = SwCHttpAdapter()
    state = _three_player_preflop_state(d={"c": "", "p": 0})

    result = adapter.process_socketio_frame(
        _socketio_frame_with_events(
            state,
            [
                {"type": 9, "action": 6, "amount": 100, "seat-idx": 0},
                {"type": 9, "action": 7, "amount": 200, "seat-idx": 1},
                {
                    "type": 15,
                    "action": 0,
                    "amount": 0,
                    "seat-idx": 2,
                    "table-msg": "<nick s=\"2\">carol</nick> wins (<money a=\"300\" mt=\"R\">3</money>): doesn't show cards",
                },
            ],
        ),
        raw_ref="raw:1",
    )

    assert result.current_hand["collections"] == [
        {"player": "carol", "pot": "3", "street": "PREFLOP", "source": "swc_game_state_event", "step_num": 1}
    ]


def test_swc_adapter_finalizes_hands_per_table_not_globally():
    adapter = SwCHttpAdapter()

    table_a_hand_1 = _three_player_preflop_state(gi=101, ti="table-a")
    table_b_hand_1 = _three_player_preflop_state(gi=201, ti="table-b")
    table_a_hand_2 = _three_player_preflop_state(gi=102, ti="table-a")

    assert adapter.process_game_state(table_a_hand_1).finalized_hands == []
    assert adapter.process_game_state(table_b_hand_1).finalized_hands == []

    result = adapter.process_game_state(table_a_hand_2)

    assert [hand["hand_id"] for hand in result.finalized_hands] == [101]
    assert 201 in adapter.active_hands


def test_http_capture_registry_returns_swc_adapter():
    assert "swc" in registered_http_capture_sites()
    assert get_http_capture_adapter("SealsWithClubs").site == "SealsWithClubs"
    assert get_http_capture_adapter("swc").site == "SealsWithClubs"


def test_swc_adapter_emits_hand_py_aligned_snapshot_envelope():
    adapter = SwCHttpAdapter()

    result = adapter.process_game_state(_sample_game_state(), captured_at="2026-06-28T10:00:00Z", raw_ref="raw:1")

    assert result.hand_id == 12345
    hand = result.current_hand
    assert hand["site"] == "SealsWithClubs"
    assert hand["gametype"]["base"] == "hold"
    assert hand["gametype"]["category"] == "holdem"
    assert hand["gametype"]["currency"] == "mBTC"
    assert hand["gametype"]["sb"] == Decimal("2")
    assert hand["gametype"]["bb"] == Decimal("0")
    assert hand["gametype"]["maxSeats"] == 2
    assert hand["metadata"]["gametype_inference"] == {
        "currency": "mBTC",
        "small_blind_player": "bob",
        "big_blind_player": None,
        "small_blind": "2",
        "big_blind": "0",
        "max_seats": 2,
    }
    assert hand["streets"]["actionStreets"] == ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
    assert hand["raw_refs"] == ["raw:1"]
    assert hand["steps"][0]["street"] == "FLOP"
    assert hand["steps"][0]["board"] == ["2c", "2d", "2h"]
    assert hand["steps"][0]["placed"]["alice"]["cards"] == ["Ac", "Ad"]
    assert hand["steps"][0]["diff"] == {"kind": "initial_snapshot", "candidates": []}
    assert hand["actions"] == [
        {
            "street": "BLINDSANTES",
            "player": "bob",
            "type": "small blind",
            "amount": "2",
            "source": "snapshot_blind_index",
            "fpdb_action": True,
        }
    ]
    assert hand["action_evidence"] == [
        {"type": "unclassified_initial_commit", "street": "FLOP", "player": "alice", "amount": "1", "step_num": 1}
    ]
    assert hand["metadata"]["importability"] == {
        "importable": False,
        "status": "capture_only",
        "reasons": ["snapshot action reconstruction is incomplete", "pot collections are missing"],
    }


def test_swc_adapter_infers_preflop_street_when_board_is_empty():
    adapter = SwCHttpAdapter()

    result = adapter.process_game_state(_sample_game_state(d={"c": "", "p": 300}), captured_at="2026-06-28T10:00:00Z")

    assert result.current_hand["steps"][0]["street"] == "PREFLOP"


def test_snapshot_diff_records_conservative_candidates():
    previous = {
        "bets": {"alice": 1.0, "bob": 2.0},
        "stacks": {"alice": 99.0, "bob": 98.0},
        "board": ["2c", "2d", "2h"],
        "placed": {"alice": {"cards": ["Ac", "Ad"]}},
        "ts": 1,
    }
    current = {
        "bets": {"alice": 4.0, "bob": 2.0},
        "stacks": {"alice": 96.0, "bob": 98.0},
        "board": ["2c", "2d", "2h", "3c"],
        "placed": {"alice": {"cards": ["Ac", "Ad"]}},
        "ts": 2,
    }

    diff = diff_snapshot_steps(previous, current)

    assert {"type": "committed_delta", "player": "alice", "amount_delta": "3.0", "from": "1.0", "to": "4.0"} in diff[
        "candidates"
    ]
    assert {"type": "board_delta", "from": ["2c", "2d", "2h"], "to": ["2c", "2d", "2h", "3c"], "added": ["3c"]} in diff[
        "candidates"
    ]


def test_snapshot_diff_records_explicit_fold_delta():
    previous = {"folded": [], "bets": {"alice": 1}, "stacks": {"alice": 99}, "placed": {}, "board": [], "ts": 0}
    current = {"folded": ["alice"], "bets": {"alice": 1}, "stacks": {"alice": 99}, "placed": {}, "board": [], "ts": 0}

    assert {"type": "fold_delta", "player": "alice", "from": False, "to": True} in diff_snapshot_steps(previous, current)[
        "candidates"
    ]


def test_snapshot_diff_records_pot_delta():
    previous = {"pot": 10, "bets": {}, "stacks": {}, "placed": {}, "board": [], "ts": 2}
    current = {"pot": 0, "bets": {}, "stacks": {}, "placed": {}, "board": [], "ts": 3}

    assert {"type": "pot_delta", "amount_delta": "-10", "from": "10", "to": "0"} in diff_snapshot_steps(previous, current)[
        "candidates"
    ]


def test_swc_adapter_reconstructs_single_call_from_snapshot_delta():
    adapter = SwCHttpAdapter()
    adapter.process_game_state(_three_player_preflop_state(), captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=0,
            d={"c": "", "p": 500},
            s=[
                {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
                {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
                {"n": "carol", "c": 9800, "b": 200, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert result.current_hand["actions"] == [
        {
            "street": "BLINDSANTES",
            "player": "alice",
            "type": "small blind",
            "amount": "1",
            "source": "snapshot_blind_index",
            "fpdb_action": True,
        },
        {
            "street": "BLINDSANTES",
            "player": "bob",
            "type": "big blind",
            "amount": "2",
            "source": "snapshot_blind_index",
            "fpdb_action": True,
        },
        {
            "street": "PREFLOP",
            "player": "carol",
            "type": "calls",
            "amount": "2",
            "source": "snapshot_single_commit_delta",
            "fpdb_action": True,
        },
    ]
    assert result.current_hand["gametype"]["sb"] == Decimal("1")
    assert result.current_hand["gametype"]["bb"] == Decimal("2")
    assert not any(item.get("type") == "committed_delta" and item.get("player") == "carol" for item in result.current_hand["action_evidence"])
    assert not any(item.get("type") == "stack_delta" and item.get("player") == "carol" for item in result.current_hand["action_evidence"])


def test_swc_adapter_keeps_commit_delta_as_evidence_when_board_changes():
    adapter = SwCHttpAdapter()
    adapter.process_game_state(_three_player_preflop_state(), captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=0,
            d={"c": "0;1;2", "p": 500},
            s=[
                {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
                {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
                {"n": "carol", "c": 9800, "b": 200, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert not any(action.get("player") == "carol" and action.get("type") == "calls" for action in result.current_hand["actions"])
    assert any(item.get("type") == "committed_delta" and item.get("player") == "carol" for item in result.current_hand["action_evidence"])


def test_swc_adapter_reconstructs_single_raise_from_snapshot_delta():
    adapter = SwCHttpAdapter()
    adapter.process_game_state(_three_player_preflop_state(), captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=0,
            d={"c": "", "p": 900},
            s=[
                {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
                {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
                {"n": "carol", "c": 9400, "b": 600, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert {
        "street": "PREFLOP",
        "player": "carol",
        "type": "raises",
        "amount": "6",
        "to": "6",
        "source": "snapshot_single_commit_delta",
        "fpdb_action": True,
    } in result.current_hand["actions"]


def test_swc_adapter_reconstructs_single_bet_when_no_previous_commit():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        d={"c": "0;1;2", "p": 0},
        m={"di": 2, "sb": -1, "bb": -1},
        s=[
            {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
            {"n": "bob", "c": 10000, "b": 0, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    )
    adapter.process_game_state(first, captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            d={"c": "0;1;2", "p": 500},
            m={"di": 2, "sb": -1, "bb": -1},
            s=[
                {"n": "alice", "c": 9500, "b": 500, "d": "48;49"},
                {"n": "bob", "c": 10000, "b": 0, "d": "44;45"},
                {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert {
        "street": "FLOP",
        "player": "alice",
        "type": "bets",
        "amount": "5",
        "source": "snapshot_single_commit_delta",
        "fpdb_action": True,
    } in result.current_hand["actions"]


def test_swc_adapter_reconstructs_call_hidden_in_street_transition():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        ts=1,
        d={"c": "", "p": 0},
        m={"di": 2, "sb": -1, "bb": -1},
        s=[
            {"n": "alice", "c": 94_00, "b": 600, "d": "48;49"},
            {"n": "bob", "c": 88_00, "b": 1200, "d": "44;45"},
            {"n": "carol", "c": 97_00, "b": 300, "d": "40;41"},
        ],
    )
    adapter.process_game_state(first, captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=1,
            d={"c": "0;1;2", "p": 2700},
            m={"di": 2, "sb": -1, "bb": -1},
            s=[
                {"n": "alice", "c": 88_00, "b": 0, "d": "48;49"},
                {"n": "bob", "c": 88_00, "b": 0, "d": "44;45"},
                {"n": "carol", "c": 97_00, "b": 0, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert {
        "street": "PREFLOP",
        "player": "alice",
        "type": "calls",
        "amount": "6",
        "source": "snapshot_street_transition_call",
        "fpdb_action": True,
    } in result.current_hand["actions"]
    assert not any(item.get("type") == "stack_delta" and item.get("player") == "alice" for item in result.current_hand["action_evidence"])


def test_swc_adapter_reconstructs_check_from_turn_delta_without_commit():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        ts=0,
        d={"c": "0;1;2", "p": 0},
        m={"di": 2, "sb": -1, "bb": -1},
        s=[
            {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
            {"n": "bob", "c": 10000, "b": 0, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    )
    adapter.process_game_state(first, captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=1,
            d={"c": "0;1;2", "p": 0},
            m={"di": 2, "sb": -1, "bb": -1},
            s=[
                {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
                {"n": "bob", "c": 10000, "b": 0, "d": "44;45"},
                {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert {
        "street": "FLOP",
        "player": "alice",
        "type": "checks",
        "source": "snapshot_turn_delta_no_commit",
        "fpdb_action": True,
    } in result.current_hand["actions"]


def test_swc_adapter_reconstructs_explicit_fold_from_snapshot_delta():
    adapter = SwCHttpAdapter()
    adapter.process_game_state(_three_player_preflop_state(), captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=0,
            s=[
                {"n": "alice", "c": 9900, "b": 100, "d": "48;49"},
                {"n": "bob", "c": 9800, "b": 200, "d": "44;45"},
                {"n": "carol", "c": 10000, "b": 0, "d": "40;41", "folded": True},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert result.current_hand["actions"][-1] == {
        "street": "PREFLOP",
        "player": "carol",
        "type": "folds",
        "source": "snapshot_fold_delta",
        "fpdb_action": True,
    }


def test_swc_adapter_reconstructs_collection_from_pot_settlement_delta():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        ts=2,
        d={"c": "0;1;2;3;4", "p": 1000, "r": 50},
        m={"di": 2, "sb": -1, "bb": -1},
        s=[
            {"n": "alice", "c": 9000, "b": 0, "d": "48;49"},
            {"n": "bob", "c": 9000, "b": 0, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    )
    adapter.process_game_state(first, captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=3,
            d={"c": "0;1;2;3;4", "p": 0, "r": 50},
            m={"di": 2, "sb": -1, "bb": -1},
            s=[
                {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
                {"n": "bob", "c": 9000, "b": 0, "d": "44;45"},
                {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert result.current_hand["steps"][-1]["rake"] == 0.5
    assert result.current_hand["collections"] == [
        {
            "player": "alice",
            "pot": "10",
            "street": "RIVER",
            "source": "snapshot_pot_settlement_delta",
            "step_num": 2,
        }
    ]
    assert "pot collections are missing" not in result.current_hand["metadata"]["importability"]["reasons"]
    assert not any(item.get("type") in {"pot_delta", "stack_delta"} for item in result.current_hand["action_evidence"])


def test_refresh_normalized_hand_recomputes_collection_from_existing_steps():
    hand_data = {
        "game": {"base": "hold", "category": "holdem", "fpdb_supported": True},
        "gametype": {"base": "hold", "category": "holdem"},
        "metadata": {"state_model": "snapshot"},
        "players": [{"seat_idx": 0, "name": "alice"}, {"seat_idx": 1, "name": "bob"}],
        "actions": [],
        "collections": [],
        "steps": [
            {
                "step_num": 1,
                "board": ["2c", "3d", "4h", "5s", "6c"],
                "pot": 10,
                "bets": {"alice": 0, "bob": 0},
                "stacks": {"alice": 90, "bob": 90},
                "placed": {},
                "folded": [],
                "ts": 2,
                "street": "RIVER",
                "diff": {"kind": "old", "candidates": []},
            },
            {
                "step_num": 2,
                "board": ["2c", "3d", "4h", "5s", "6c"],
                "pot": 0,
                "bets": {"alice": 0, "bob": 0},
                "stacks": {"alice": 100, "bob": 90},
                "placed": {},
                "folded": [],
                "ts": 3,
                "street": "RIVER",
                "diff": {"kind": "old", "candidates": []},
            },
        ],
    }

    refreshed = refresh_normalized_hand(hand_data)

    assert refreshed["collections"] == [
        {
            "player": "alice",
            "pot": "10",
            "street": "RIVER",
            "source": "snapshot_pot_settlement_delta",
            "step_num": 2,
        }
    ]
    assert "pot collections are missing" not in refreshed["metadata"]["importability"]["reasons"]


def test_refresh_normalized_hand_remaps_observed_swc_game_type():
    hand_data = {
        "game_type": "Poker (Type 50)",
        "game": {"base": "unknown", "category": "unknown", "fpdb_supported": False},
        "gametype": {"type": "ring", "base": "unknown", "category": "unknown", "currency": "mBTC", "sb": "3", "bb": "6"},
        "metadata": {"state_model": "snapshot"},
        "players": [{"seat_idx": 0, "name": "alice"}],
        "actions": [],
        "steps": [],
        "collections": [{"player": "alice", "pot": "1"}],
    }

    refreshed = refresh_normalized_hand(hand_data)

    assert refreshed["game"]["base"] == "hold"
    assert refreshed["game"]["category"] == "6_omahahi"
    assert refreshed["game"]["fpdb_supported"] is True
    assert refreshed["gametype"]["category"] == "6_omahahi"


def test_swc_adapter_does_not_infer_check_when_player_faces_bet():
    adapter = SwCHttpAdapter()
    first = _three_player_preflop_state(
        ts=0,
        d={"c": "0;1;2", "p": 500},
        m={"di": 2, "sb": -1, "bb": -1},
        s=[
            {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
            {"n": "bob", "c": 9500, "b": 500, "d": "44;45"},
            {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
        ],
    )
    adapter.process_game_state(first, captured_at="2026-06-28T10:00:00Z")

    result = adapter.process_game_state(
        _three_player_preflop_state(
            ts=1,
            d={"c": "0;1;2", "p": 500},
            m={"di": 2, "sb": -1, "bb": -1},
            s=[
                {"n": "alice", "c": 10000, "b": 0, "d": "48;49"},
                {"n": "bob", "c": 9500, "b": 500, "d": "44;45"},
                {"n": "carol", "c": 10000, "b": 0, "d": "40;41"},
            ],
        ),
        captured_at="2026-06-28T10:00:01Z",
    )

    assert not any(action.get("player") == "alice" and action.get("type") == "checks" for action in result.current_hand["actions"])
    assert any(item.get("type") == "turn_delta" for item in result.current_hand["action_evidence"])


def test_swc_adapter_finalizes_showdown_once():
    adapter = SwCHttpAdapter()
    adapter.process_game_state(_sample_game_state(ts=2), captured_at="2026-06-28T10:00:00Z")
    final_state = _sample_game_state(
        ts=0,
        ss={"hc": "Pair\tHigh Card\tHigh Card\nHigh Card\tHigh Card\tHigh Card"},
    )

    first = adapter.process_game_state(final_state, captured_at="2026-06-28T10:00:01Z")
    second = adapter.process_game_state(final_state, captured_at="2026-06-28T10:00:02Z")

    assert len(first.finalized_hands) == 1
    assert first.finalized_hands[0]["showdown"]["rows"]["alice"]["top"] == "Pair"
    assert first.finalized_hands[0]["steps"][-1]["diff"]["kind"] == "snapshot_diff"
    assert second.finalized_hands == []


def test_raw_and_hand_archives_write_json(tmp_path):
    raw_archive = JsonlRawCaptureArchive(tmp_path)
    raw_ref = raw_archive.append(
        RawCaptureMessage(
            site="SealsWithClubs",
            transport="websocket",
            message_type="GameState",
            hand_id=12345,
            table_id="table-1",
            captured_at="2026-06-28T10:00:00Z",
            direction="received",
            payload={"hello": "world"},
        )
    )
    assert raw_ref == "raw_messages.jsonl:1"

    raw_line = (tmp_path / "raw_messages.jsonl").read_text(encoding="utf-8").strip()
    raw_data = json.loads(raw_line)
    assert raw_data["payload"] == {"hello": "world"}
    assert raw_data["direction"] == "received"

    hand_path = JsonHandArchive(tmp_path).write_hand({"hand_id": 12345, "gametype": {"sb": Decimal("0.01")}})
    assert json.loads(hand_path.read_text(encoding="utf-8"))["gametype"]["sb"] == "0.01"


def test_importability_gate_requires_supported_game_and_actions():
    capture_only = {
        "game": {"fpdb_supported": False},
        "metadata": {"state_model": "snapshot"},
        "players": [{"name": "alice"}],
        "steps": [{"step_num": 1}],
        "actions": [],
    }
    decision = evaluate_capture_importability(capture_only)
    assert decision.status == "capture_only"
    assert "game is not supported by FPDB Hand.py yet" in decision.reasons
    assert "snapshot action reconstruction is incomplete" in decision.reasons
    assert "snapshot actions have not been reconstructed" in decision.reasons
    assert "pot collections are missing" in decision.reasons

    importable = {
        "game": {"fpdb_supported": True},
        "metadata": {"state_model": "events"},
        "players": [{"name": "alice"}],
        "steps": [],
        "actions": [
            {"street": "PREFLOP", "player": "alice", "type": "checks"},
            {"player": "alice", "type": "collects", "amount": "1"},
        ],
    }
    assert evaluate_capture_importability(importable).importable is True


def test_hand_builder_plan_refuses_capture_only_and_maps_supported_base():
    capture_only = {
        "game": {"base": "ofc", "category": "ofcp", "fpdb_supported": False},
        "metadata": {"state_model": "snapshot"},
        "players": [{"name": "alice"}],
        "steps": [{"step_num": 1}],
        "actions": [],
    }
    try:
        plan_hand_build(capture_only)
    except CaptureNotImportableError as exc:
        assert "OFC requires a dedicated importer/replayer" in str(exc)
    else:
        raise AssertionError("capture-only hand should not get a Hand.py build plan")

    importable = {
        "site": "SealsWithClubs",
        "hand_id": 999,
        "table_id": "table-x",
        "game": {"base": "hold", "category": "holdem", "fpdb_supported": True},
        "gametype": {"base": "hold", "category": "holdem", "currency": "mBTC"},
        "metadata": {"state_model": "events"},
        "players": [{"name": "alice"}],
        "steps": [],
        "actions": [
            {"street": "PREFLOP", "player": "alice", "type": "checks"},
            {"player": "alice", "type": "collects", "amount": "1"},
        ],
    }

    plan = plan_hand_build(importable)
    assert plan.hand_class == "HoldemOmahaHand"
    assert plan.category == "holdem"

    build_input = build_hand_input(importable)
    assert build_input["hand_class"] == "HoldemOmahaHand"
    assert build_input["gametype"]["currency"] == "mBTC"
    assert build_input["actions"] == [
        {"street": "PREFLOP", "player": "alice", "type": "checks"},
        {"player": "alice", "type": "collects", "amount": "1"},
    ]
    assert build_input["operations"] == [
        {"method": "addPlayer", "args": [None, "alice", "0"], "source": "players"},
        {"method": "addCheck", "args": ["PREFLOP", "alice"], "source": "actions"},
        {"method": "addCollectPot", "args": ["alice", "1"], "source": "actions"},
    ]


def test_hand_operation_plan_maps_supported_actions_to_hand_methods():
    hand_data = {
        "players": [
            {"seat_idx": 0, "name": "alice", "starting_stack": 100},
            {"seat_idx": 1, "name": "bob", "starting_stack": 100},
        ],
        "actions": [
            {"street": "BLINDSANTES", "player": "alice", "type": "small blind", "amount": "1"},
            {"street": "BLINDSANTES", "player": "bob", "type": "big blind", "amount": "2"},
            {"street": "PREFLOP", "player": "alice", "type": "calls", "amount": "1"},
            {"street": "PREFLOP", "player": "bob", "type": "raises", "amount": "4", "to": "6"},
        ],
    }

    assert build_hand_operations(hand_data) == [
        {"method": "addPlayer", "args": [0, "alice", "100"], "source": "players"},
        {"method": "addPlayer", "args": [1, "bob", "100"], "source": "players"},
        {"method": "addBlind", "args": ["alice", "small blind", "1"], "source": "actions"},
        {"method": "addBlind", "args": ["bob", "big blind", "2"], "source": "actions"},
        {"method": "addCall", "args": ["PREFLOP", "alice", "1"], "source": "actions"},
        {"method": "addRaiseTo", "args": ["PREFLOP", "bob", "6"], "source": "actions"},
    ]
    assert validate_hand_operations(build_hand_operations(hand_data)) == []


def test_hand_operation_plan_maps_pot_collections_to_hand_method():
    hand_data = {
        "players": [{"seat_idx": 0, "name": "alice", "starting_stack": 100}],
        "actions": [{"player": "alice", "type": "collects", "amount": "3"}],
        "collections": [{"player": "alice", "pot": "2"}],
        "showdown": {"collections": [{"name": "alice", "collected": "1"}]},
    }

    assert build_hand_operations(hand_data) == [
        {"method": "addPlayer", "args": [0, "alice", "100"], "source": "players"},
        {"method": "addCollectPot", "args": ["alice", "3"], "source": "actions"},
        {"method": "addCollectPot", "args": ["alice", "2"], "source": "collections"},
        {"method": "addCollectPot", "args": ["alice", "1"], "source": "showdown.collections"},
    ]


def test_build_fpdb_hand_creates_real_holdem_hand_from_complete_event_capture():
    hand_data = {
        "site": "SealsWithClubs",
        "hand_id": 777,
        "table_id": "table-http",
        "buttonpos": 1,
        "game": {"base": "hold", "category": "holdem", "fpdb_supported": True},
        "gametype": {
            "type": "ring",
            "base": "hold",
            "category": "holdem",
            "limitType": "nl",
            "currency": "mBTC",
            "sb": "1",
            "bb": "2",
            "maxSeats": 2,
        },
        "streets": {
            "holeStreets": ["PREFLOP"],
            "communityStreets": ["FLOP", "TURN", "RIVER"],
        },
        "metadata": {"state_model": "events"},
        "players": [
            {"seat_idx": 1, "name": "alice", "starting_stack": "100", "cards": ["Ah", "Ad"]},
            {"seat_idx": 2, "name": "bob", "starting_stack": "100", "cards": ["Kh", "Kd"]},
        ],
        "board": ["2c", "3d", "4h", "5s", "6c"],
        "actions": [
            {"street": "BLINDSANTES", "player": "alice", "type": "small blind", "amount": "1"},
            {"street": "BLINDSANTES", "player": "bob", "type": "big blind", "amount": "2"},
            {"street": "PREFLOP", "player": "alice", "type": "calls", "amount": "1"},
            {"street": "PREFLOP", "player": "bob", "type": "checks"},
            {"street": "FLOP", "player": "alice", "type": "checks"},
            {"street": "FLOP", "player": "bob", "type": "checks"},
            {"street": "TURN", "player": "alice", "type": "checks"},
            {"street": "TURN", "player": "bob", "type": "checks"},
            {"street": "RIVER", "player": "alice", "type": "checks"},
            {"street": "RIVER", "player": "bob", "type": "checks"},
        ],
        "collections": [{"player": "alice", "pot": "4"}],
    }

    hand = build_fpdb_hand(hand_data)
    summary = summarize_fpdb_hand(hand)

    assert hand.__class__.__name__ == "HoldemOmahaHand"
    assert summary["hand_id"] == 777
    assert summary["table"] == "table-http"
    assert summary["board"]["FLOP"] == ["2c", "3d", "4h"]
    assert summary["board"]["TURN"] == ["5s"]
    assert summary["board"]["RIVER"] == ["6c"]
    assert summary["actions"]["PREFLOP"] == [
        ("alice", "calls", Decimal("1"), False),
        ("bob", "checks"),
    ]
    assert summary["collected"] == [["alice", "4"]]
    assert summary["totalcollected"] == "4.00"


def test_complete_swc_event_fixture_builds_real_fpdb_hand():
    fixture_path = Path(__file__).parent / "fixtures" / "http_capture" / "swc" / "complete_holdem_event_hand.json"
    hand_data = json.loads(fixture_path.read_text(encoding="utf-8"))

    hand = build_fpdb_hand(hand_data)
    summary = summarize_fpdb_hand(hand)

    assert summary["hand_id"] == 777
    assert summary["actions"]["BLINDSANTES"] == [
        ("alice", "small blind", Decimal("1"), False),
        ("bob", "big blind", Decimal("2"), False),
    ]
    assert summary["totalcollected"] == "4.00"


def test_http_capture_build_cli_helper_loads_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "http_capture" / "swc" / "complete_holdem_event_hand.json"

    hand = build_capture_file(fixture_path)

    assert hand.handid == 777
    assert hand.actions["RIVER"] == [("alice", "checks"), ("bob", "checks")]


def _memory_db_config():
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
    config.get_site_id.side_effect = lambda _site: 1
    return config


def test_complete_swc_event_fixture_imports_into_sqlite_memory_db():
    fixture_path = Path(__file__).parent / "fixtures" / "http_capture" / "swc" / "complete_holdem_event_hand.json"
    hand_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    hand = build_fpdb_hand(hand_data)
    db = Database(_memory_db_config(), Sql(db_server="sqlite"))

    import_fpdb_hand(hand, db, file_id=1, doinsert=True, printtest=False, starting_hand_id=1)
    db.commit()
    cursor = db.get_cursor()
    cursor.execute("select count(*) from Hands")
    assert cursor.fetchone()[0] == 1
    cursor.execute("select count(*) from HandsActions")
    assert cursor.fetchone()[0] == sum(len(actions) for actions in hand.actions.values())


def test_real_swc_capture_importable_hands_build_hand_py_when_capture_is_present():
    capture_path = Path("/Users/jde/Documents/SwC Poker/Capture/raw_messages.jsonl")
    if not capture_path.exists():
        pytest.skip("local SwC capture corpus is not present")

    with TemporaryDirectory() as output_dir:
        written = replay_swc_raw_archive(capture_path, Path(output_dir), include_active=False)
        hands = [json.loads(path.read_text(encoding="utf-8")) for path in written]

    importable = [hand for hand in hands if hand.get("metadata", {}).get("importability", {}).get("importable")]
    assert len(importable) >= 80
    failures = []
    for hand_data in importable:
        try:
            render_fpdb_hand(build_fpdb_hand(hand_data))
        except Exception as exc:  # pragma: no cover - assertion payload
            failures.append((hand_data.get("hand_id"), hand_data.get("game", {}).get("category"), str(exc)))

    assert failures == []


def test_hand_operation_validation_reports_malformed_operations():
    operations = [
        {"method": None, "args": [], "source": "actions"},
        {"method": "addCall", "args": ["UNKNOWN", "alice", "1"], "source": "actions"},
        {"method": "addBlind", "args": [None, "small blind", "1"], "source": "actions"},
    ]

    assert validate_hand_operations(operations) == [
        "operation 1: missing Hand.py method",
        "operation 2: addCall requires street and player",
        "operation 3: addBlind requires player",
    ]


def test_hand_operation_executor_replays_calls_in_order():
    class FakeHand:
        def __init__(self):
            self.calls = []

        def addPlayer(self, *args):
            self.calls.append(("addPlayer", args))

        def addBlind(self, *args):
            self.calls.append(("addBlind", args))

        def addCall(self, *args):
            self.calls.append(("addCall", args))

        def addCollectPot(self, *args):
            self.calls.append(("addCollectPot", args))

    hand = FakeHand()
    operations = [
        {"method": "addPlayer", "args": [0, "alice", "100"], "source": "players"},
        {"method": "addBlind", "args": ["alice", "small blind", "1"], "source": "actions"},
        {"method": "addCall", "args": ["PREFLOP", "alice", "1"], "source": "actions"},
        {"method": "addCollectPot", "args": ["alice", "2"], "source": "collections"},
    ]

    assert execute_hand_operations(hand, operations) is hand
    assert hand.calls == [
        ("addPlayer", (0, "alice", "100")),
        ("addBlind", ("alice", "small blind", "1")),
        ("addCall", ("PREFLOP", "alice", "1")),
        ("addCollectPot", ("alice", "2")),
    ]


def test_hand_operation_executor_reports_invalid_target_method():
    class FakeHand:
        def addPlayer(self, *args):
            pass

    operations = [
        {"method": "addPlayer", "args": [0, "alice", "100"], "source": "players"},
        {"method": "addCall", "args": ["PREFLOP", "alice", "1"], "source": "actions"},
    ]

    try:
        execute_hand_operations(FakeHand(), operations)
    except CaptureNotImportableError as exc:
        assert "operation 2: hand object has no callable addCall" in str(exc)
    else:
        raise AssertionError("executor should reject missing Hand.py methods")


def test_replay_swc_raw_archive_writes_normalized_hand(tmp_path):
    raw_archive = JsonlRawCaptureArchive(tmp_path)
    first_state = _sample_game_state(ts=2)
    final_state = _sample_game_state(
        ts=0,
        ss={"hc": "Pair\tHigh Card\tHigh Card\nHigh Card\tHigh Card\tHigh Card"},
    )
    for state in (first_state, final_state):
        raw_archive.append(
            RawCaptureMessage(
                site="SealsWithClubs",
                transport="websocket",
                message_type="GameState",
                hand_id=state["gi"],
                table_id=state["ti"],
                captured_at="2026-06-28T10:00:00Z",
                payload=_socketio_frame(state),
            )
        )

    written = replay_swc_raw_archive(tmp_path / "raw_messages.jsonl", tmp_path / "normalized")

    assert len(written) == 1
    normalized = json.loads(written[0].read_text(encoding="utf-8"))
    assert normalized["hand_id"] == 12345
    assert normalized["raw_refs"] == ["raw_messages.jsonl:1", "raw_messages.jsonl:2"]
    assert normalized["showdown"]["rows"]["alice"]["top"] == "Pair"


def test_generic_replay_uses_record_site_adapter(tmp_path):
    raw_archive = JsonlRawCaptureArchive(tmp_path)
    final_state = _sample_game_state(
        ts=0,
        ss={"hc": "Pair\tHigh Card\tHigh Card\nHigh Card\tHigh Card\tHigh Card"},
    )
    raw_archive.append(
        RawCaptureMessage(
            site="swc",
            transport="websocket",
            message_type="GameState",
            hand_id=final_state["gi"],
            table_id=final_state["ti"],
            captured_at="2026-06-28T10:00:00Z",
            payload=_socketio_frame(final_state),
        )
    )

    written = replay_raw_archive(tmp_path / "raw_messages.jsonl", tmp_path / "normalized", include_active=True)

    assert len(written) == 1
    assert json.loads(written[0].read_text(encoding="utf-8"))["site"] == "SealsWithClubs"


def test_analyze_raw_archive_summarizes_sites_games_and_hands(tmp_path):
    raw_archive = JsonlRawCaptureArchive(tmp_path)
    state = _sample_game_state()
    raw_archive.append(
        RawCaptureMessage(
            site="SealsWithClubs",
            transport="websocket",
            message_type="GameState",
            hand_id=state["gi"],
            table_id=state["ti"],
            captured_at="2026-06-28T10:00:00Z",
            payload=_socketio_frame(state),
            direction="received",
        )
    )
    raw_archive.append(
        RawCaptureMessage(
            site="SealsWithClubs",
            transport="websocket",
            message_type="Action",
            captured_at="2026-06-28T10:00:01Z",
            payload=_socketio_proxy_frame({"t": "Action", "a": "call"}),
            direction="sent",
        )
    )

    summary = analyze_raw_archive(tmp_path / "raw_messages.jsonl")

    assert summary["records"] == 2
    assert summary["sites"] == {"SealsWithClubs": 2}
    assert summary["message_types"] == {"GameState": 1, "Action": 1}
    assert summary["directions"] == {"received": 1, "sent": 1}
    assert summary["hands_by_site"] == {"SealsWithClubs": 1}
    assert summary["tables_by_site"] == {"SealsWithClubs": 1}
    assert summary["games_by_site"] == {"SealsWithClubs": {"hold/holdem/nl": 1}}
    assert summary["unrecognized_records"] == 0
