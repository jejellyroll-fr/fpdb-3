"""tools/anonymize_hh.py renames real players in hand histories without changing anything else (#735)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools import anonymize_hh

ROOT = Path(__file__).resolve().parents[1]
UNIBET = ROOT / "tests" / "fixtures" / "hands" / "unibet"
HANDS = UNIBET / "manual_export_power_spin_025_2026.txt"
SUMMARIES = ROOT / "tests" / "fixtures" / "summaries" / "unibet" / "manual_export_power_spin_025_2026.txt"
CASH = UNIBET / "automatic_plo_cash_2026.txt"
# The fixtures are anonymised already; a token of their own makes them "real".
REAL_TOKEN = "deadbeefdeadbeef"
FAKE_TOKEN = "0000000000000001"


def _seat_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        if line.startswith("Seat ") and " (" in line:
            names.add(line.split(": ", 1)[1].split(" (", 1)[0].split("[", 1)[0])
    return names


@pytest.fixture
def export(tmp_path: Path) -> Path:
    """A Manual export, hands and summaries, as the client names it."""
    folder = tmp_path / "in"
    folder.mkdir()
    for source, name in ((HANDS, "hands.txt"), (SUMMARIES, "summaries.txt")):
        text = source.read_text(encoding="utf-8").replace(FAKE_TOKEN, REAL_TOKEN)
        (folder / f"19247-{REAL_TOKEN}-20260717_095605-{name}").write_text(text, encoding="utf-8")
    return folder


def test_players_and_tokens_are_renamed_and_the_hands_still_parse(export: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    mapping_file = tmp_path / "map.json"
    real_names = _seat_names((export / f"19247-{REAL_TOKEN}-20260717_095605-hands.txt").read_text(encoding="utf-8"))

    results = anonymize_hh.run("Unibet", [export], out, mapping_file)

    assert sorted((result.target.name, result.hands) for result in results) == [
        (f"19247-{FAKE_TOKEN}-20260717_095605-hands.txt", 2),
        (f"19247-{FAKE_TOKEN}-20260717_095605-summaries.txt", 0),
    ]
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    assert mapping["tokens"] == {REAL_TOKEN: FAKE_TOKEN}
    # The hero, named by the account token, stays Hero; everyone else is renamed.
    assert mapping["names"]["Hero"] == "Hero"
    assert real_names <= set(mapping["names"])
    hands = (out / f"19247-{FAKE_TOKEN}-20260717_095605-hands.txt").read_text(encoding="utf-8")
    assert _seat_names(hands) == {mapping["names"][name] for name in real_names}
    summaries = (out / f"19247-{FAKE_TOKEN}-20260717_095605-summaries.txt").read_text(encoding="utf-8")
    assert REAL_TOKEN not in hands + summaries
    # A summary names the same players as the hands, renamed alike.
    winner = next(line for line in summaries.splitlines() if line.startswith("1: ") and "Unibet_" not in line)
    assert winner.split()[1] in set(mapping["names"].values())


def test_a_second_run_reuses_the_mapping(export: Path, tmp_path: Path) -> None:
    mapping_file = tmp_path / "map.json"
    anonymize_hh.run("Unibet", [export], tmp_path / "first", mapping_file)
    first = mapping_file.read_text(encoding="utf-8")

    anonymize_hh.run("Unibet", [export], tmp_path / "second", mapping_file)

    assert mapping_file.read_text(encoding="utf-8") == first
    for path in (tmp_path / "first").iterdir():
        assert path.read_bytes() == (tmp_path / "second" / path.name).read_bytes()


def test_line_endings_and_byte_order_mark_are_kept(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    text = CASH.read_text(encoding="utf-8").replace("\n", "\r\n")
    (folder / "cash.txt").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))

    anonymize_hh.run("Unibet", [folder], tmp_path / "out", tmp_path / "map.json")

    raw = (tmp_path / "out" / "cash.txt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\r\n") == text.count("\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_names_are_replaced_in_one_pass() -> None:
    # Real "alice" becoming "bob" while real "bob" becomes "alice" must not
    # turn both into the same player.
    anonymizer = anonymize_hh.Anonymizer.__new__(anonymize_hh.Anonymizer)
    anonymizer.mapping = anonymize_hh.Mapping(names={"alice": "bob", "bob": "alice", "Jo": "carol"})

    assert anonymizer.rewrite("alice raises, bob calls, Jo128 folds, Jo checks") == (
        "bob raises, alice calls, Jo128 folds, carol checks"
    )


def test_nothing_is_written_when_a_name_would_survive(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(anonymize_hh.Anonymizer, "rewrite", lambda self, text: text)

    with pytest.raises(ValueError, match="would survive"):
        anonymize_hh.run("Unibet", [export], tmp_path / "out", tmp_path / "map.json")

    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "map.json").exists()


def test_the_mapping_is_never_written_inside_the_repository(export: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="outside the repository"):
        anonymize_hh.run("Unibet", [export], tmp_path / "out", ROOT / "unibet-map.json")

    assert not (ROOT / "unibet-map.json").exists()


def test_the_cli_reports_each_file(export: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = anonymize_hh.main(
        ["--room", "Unibet", "--out", str(tmp_path / "out"), "--map", str(tmp_path / "map.json"), str(export)]
    )

    assert code == 0
    assert "2 hands" in capsys.readouterr().out
    shutil.rmtree(tmp_path / "out")
