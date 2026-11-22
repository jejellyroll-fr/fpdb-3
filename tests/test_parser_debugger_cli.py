"""``tools/parser_debugger.py`` (#903), driven in process."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools import parser_debugger as cli

ROOT = Path(__file__).resolve().parents[1]
SOKO = ROOT / "regression-test-files" / "unsupported-sites" / "soko" / "soko_2005_001_complete_anonymized.txt"
STARS = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt"


@pytest.fixture
def config_file(tmp_path) -> Path:
    path = tmp_path / "HUD_config.xml"
    shutil.copyfile(ROOT / "HUD_config.xml", path)
    return path


def test_the_path_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_json_and_bug_report_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["x.txt", "--json", "--bug-report"])


def test_a_missing_file_exits_2(capsys) -> None:
    assert cli.main(["does-not-exist.txt"]) == 2
    assert "No such file" in capsys.readouterr().err


def test_a_failing_file_exits_1(config_file, capsys) -> None:
    assert cli.main([str(SOKO), "--config", str(config_file)]) == 1
    assert "UnsupportedGame" in capsys.readouterr().out


def test_a_clean_file_exits_0(config_file, capsys) -> None:
    assert cli.main([str(STARS), "--config", str(config_file), "--lines"]) == 0
    out = capsys.readouterr().out
    assert "Verdict: OK" in out
    assert "re_player_info" in out


def test_json_output_and_compare(config_file, capsys, tmp_path) -> None:
    cli.main([str(STARS), "--config", str(config_file), "--json", "--no-trace"])
    saved = tmp_path / "report.json"
    saved.write_text(capsys.readouterr().out, encoding="utf-8")

    assert json.loads(saved.read_text(encoding="utf-8"))["verdict"] == "ok"
    cli.main([str(STARS), "--config", str(config_file), "--compare", str(saved), "--no-trace"])
    assert capsys.readouterr().out.strip() == "No change."


def test_bug_report_output(config_file, capsys) -> None:
    cli.main([str(STARS), "--config", str(config_file), "--bug-report", "--no-trace"])
    out = capsys.readouterr().out

    assert out.startswith("### Parser Debugger report")
    assert "AAALISAAAA" not in out


def test_direct_script_runs_without_pythonpath(tmp_path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "parser_debugger.py"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--config CONFIG" in result.stdout
