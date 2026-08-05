"""Unit tests for CoinPoker table-id resolution from process argv.

The live lookup (`table_id_for_pid`) shells out to `ps`, so these tests cover the
pure `extract_table_id` parser using representative CoinPoker command lines.
"""

from __future__ import annotations

import pytest

macos_process = pytest.importorskip("fpdb.infrastructure.platform.macos_process")

_ARGV_A = (
    "/Applications/CoinPoker.app/Contents/Resources/unity-resources-arm64/"
    "CoinPoker Game.app/Contents/MacOS/CoinPoker "
    "serverIp=poker-nlb.coinpoker.ai:7001 "
    "roomName=PLO 0.01-0.02 EV-INRIT-ANTE (A) 922564 isSuspectedFraud=false "
    "tableSize=6 lobbyId=1 pipeName=PLO 0.01-0.02 EV-INRIT-ANTE (A) 922564 "
    "mode=prod buildName=CoinPoker -screen-fullscreen 0 -screen-width 1640 "
    "-screen-height 1200 -logFile /Users/jde/Library/Logs/CoinPoker/table_922564.log"
)

_ARGV_B = (
    "/Applications/CoinPoker.app/.../CoinPoker "
    "serverIp=poker-nlb.coinpoker.ai:7001 "
    "roomName=PLO 0.01-0.02 EV-INRIT-BPR-RC-TB (B) 921973 tableSize=6 "
    "pipeName=PLO 0.01-0.02 EV-INRIT-BPR-RC-TB (B) 921973 "
    "-logFile /Users/jde/Library/Logs/CoinPoker/table_921973.log"
)


def test_extract_from_logfile():
    assert macos_process.extract_table_id(_ARGV_A) == "922564"
    assert macos_process.extract_table_id(_ARGV_B) == "921973"


def test_distinct_tables_distinct_ids():
    assert macos_process.extract_table_id(_ARGV_A) != macos_process.extract_table_id(_ARGV_B)


def test_extract_from_roomname_without_logfile():
    argv = "CoinPoker serverIp=x:7001 roomName=PLO 0.01-0.02 EV (A) 922564 tableSize=6"
    assert macos_process.extract_table_id(argv) == "922564"


def test_stake_digits_not_mistaken_for_table_id():
    # The 2-digit stake components (0.01/0.02) must not be picked over the id.
    argv = "CoinPoker roomName=PLO 0.01-0.02 (A) 922564"
    assert macos_process.extract_table_id(argv) == "922564"


def test_no_table_id_returns_none():
    assert macos_process.extract_table_id("CoinPoker mode=prod buildName=CoinPoker") is None
    assert macos_process.extract_table_id("") is None
