"""CoinPoker table-id resolution from process argv (shared parser + Windows).

The pure ``extract_table_id`` parser is shared by macOS and Windows; the Windows
``table_id_for_pid`` reads argv via psutil, mocked here so the test is portable.
"""

from __future__ import annotations

from unittest.mock import patch

from fpdb.infrastructure.platform.coinpoker_process import (
    extract_latest_table_id,
    extract_log_path,
    extract_table_id,
    resolve_current_table_id,
)

# A real Windows CoinPoker Unity command line (quotes dropped by argv splitting).
_WIN_ARGV = (
    r'C:\Program Files\CoinPoker\resources\unity-resources-win-x64\CoinPoker Game\CoinPoker.exe '
    "serverIp=poker-nlb.coinpoker.ai:7003 roomName=NL 0.01-0.02 EV-INRIT-(A) 930357 "
    "isSuspectedFraud=false tableSize=6 lobbyId=1 pipeName=NL 0.01-0.02 EV-INRIT-(A) 930357 "
    r"-logFile C:\Users\jd\AppData\Roaming\CoinPoker\logs\table_930357.log"
)


def test_extract_prefers_logfile_anchor() -> None:
    assert extract_table_id(_WIN_ARGV) == "930357"


def test_extract_from_roomname_without_logfile() -> None:
    argv = "CoinPoker serverIp=x:7003 roomName=NL 0.01-0.02 EV-INRIT-(A) 166755 tableSize=6"
    assert extract_table_id(argv) == "166755"


def test_stake_digits_not_mistaken_for_id() -> None:
    assert extract_table_id("CoinPoker roomName=PLO 0.01-0.02 (A) 922564") == "922564"


def test_no_id_returns_none() -> None:
    assert extract_table_id("CoinPoker --type=renderer --user-data-dir=x") is None
    assert extract_table_id("") is None


def test_latest_mtt_room_id_wins_after_table_balance(tmp_path) -> None:
    log_path = tmp_path / "table_1117675.log"
    log_path.write_text(
        "[UNITY] -> Initializing table with Address - host:3001, RoomName - Level Up Freeroll 1117675\n"
        "[UNITY] -> Initializing table with Address - host:3000, RoomName - Level Up Freeroll 1117827\n",
        encoding="utf-8",
    )
    argv = f"CoinPoker roomName=Level Up Freeroll 1117675 -logFile {log_path}"

    assert extract_log_path(argv) == str(log_path)
    assert extract_latest_table_id(log_path.read_text(encoding="utf-8")) == "1117827"
    assert resolve_current_table_id(argv) == "1117827"


def test_windows_table_id_for_pid_reads_argv_via_psutil() -> None:
    from fpdb.infrastructure.platform import windows_process

    windows_process._cache.clear()
    with patch.object(windows_process, "_argv_for_pid", return_value=_WIN_ARGV):
        assert windows_process.table_id_for_pid(956) == "930357"


def test_windows_table_id_for_pid_handles_bad_pid_and_errors() -> None:
    from fpdb.infrastructure.platform import windows_process

    windows_process._cache.clear()
    assert windows_process.table_id_for_pid(0) is None
    assert windows_process.table_id_for_pid("nope") is None
    with patch.object(windows_process, "_argv_for_pid", side_effect=OSError("no such process")):
        assert windows_process.table_id_for_pid(4242) is None
