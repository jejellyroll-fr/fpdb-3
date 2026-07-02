from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.RegressionFileComparator import compare_importer_sidecars


class FakeImporter:
    def __init__(self, hands):
        self._hands = hands

    def getCachedHHC(self):
        return SimpleNamespace(getProcessedHands=lambda: self._hands)


def fake_hand(hands=None, handsplayers=None, gametype=None):
    stats = SimpleNamespace(
        getHands=lambda: hands or {"siteHandNo": "1", "boards": []},
        getHandsPlayers=lambda: handsplayers or {"Hero": {"position": 0, "tourneyTypeId": 9}},
    )
    return SimpleNamespace(stats=stats, gametyperow=gametype or [2, "USD", "ring"])


def test_compare_importer_sidecars_passes_matching_files(tmp_path):
    hand_file = tmp_path / "sample.txt"
    hand_file.write_text("hand", encoding="utf-8")
    (tmp_path / "sample.txt.hands").write_text("{'siteHandNo': '1'}", encoding="utf-8")
    (tmp_path / "sample.txt.hp").write_text("{'Hero': {'position': 0, 'tourneyTypeId': 0}}", encoding="utf-8")
    (tmp_path / "sample.txt.gt").write_text("[2, 'USD', 'ring']", encoding="utf-8")

    report = compare_importer_sidecars(hand_file, FakeImporter([fake_hand()]))

    assert report.passed is True
    assert report.compared == [".hands", ".hp", ".gt"]


def test_compare_importer_sidecars_reports_mismatches(tmp_path):
    hand_file = tmp_path / "sample.txt"
    hand_file.write_text("hand", encoding="utf-8")
    (tmp_path / "sample.txt.hp").write_text("{'Hero': {'position': 1}}", encoding="utf-8")

    report = compare_importer_sidecars(hand_file, FakeImporter([fake_hand()]))

    assert report.passed is False
    assert len(report.issues) == 1
    assert report.issues[0].sidecar == ".hp"
    assert report.issues[0].field == "position"
    assert report.issues[0].expected == 1
    assert report.issues[0].actual == 0
