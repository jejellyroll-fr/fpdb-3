"""bwin.fr moved from the PartyPoker network to iPoker (Entain France, 2026).

Covers the three pieces that make the new client work end to end:
- stale user configs (network="PartyPoker", converter="PartyPokerToFpdb") are
  migrated in place, including repointing HH_path to the new client data dir;
- the iPoker skin dispatcher recognises the Windows data directory
  (%LOCALAPPDATA%\\bwin Poker France\\...) so hands are attributed to
  "Bwin.fr Poker" instead of the generic "iPoker" site;
- installed-site detection probes the aliased directory name.
"""

from __future__ import annotations

import xml.dom.minidom
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import iPokerDetector
from fpdb_3_legacy.iPoker.dispatcher import detect_skin, get_parser_class_for_path
from fpdb_3_legacy.iPoker.skins.bwin_fr import BwinFrIPoker

STALE_CONFIG = """<FreePokerToolsConfig>
  <supported_sites>
    <site site_name="Bwin.fr Poker" enabled="True" screen_name="jejsat76"
          HH_path="C:\\Wrong\\PMU\\Tables" TS_path="C:\\Wrong\\PMU\\Tournaments"
          network="PartyPoker">
      <layout_set game_type="all" ls="party_default"/>
    </site>
    <site site_name="PMU Poker" enabled="True" screen_name="hero"
          HH_path="C:\\PMU\\Tables" network="iPoker"/>
  </supported_sites>
  <hhcs>
    <hhc site="Bwin.fr Poker" converter="PartyPokerToFpdb"/>
    <hhc site="PMU Poker" converter="iPokerToFpdb" summaryImporter="iPokerSummary"/>
  </hhcs>
  <layout_sets>
    <ls name="party_default"/>
    <ls name="ipoker_default"/>
  </layout_sets>
</FreePokerToolsConfig>"""

BWIN_WINDOWS_PATH = (
    r"C:\Users\jd\AppData\Local\bwin Poker France\data\jejesat76\History\Data\Tables\5869857694.xml"
)


def _shell_config() -> Config:
    """A Config instance without running __init__ (migration helpers only)."""
    return object.__new__(Config)


def _make_bwin_data_dir(root: Path, account: str = "accountdir") -> Path:
    tables = root / "bwin Poker France" / "data" / account / "History" / "Data" / "Tables"
    tables.mkdir(parents=True)
    (root / "bwin Poker France" / "data" / account / "History" / "Data" / "Tournaments").mkdir()
    return tables


class TestConfigMigration:
    def test_stale_partypoker_entry_is_migrated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tables = _make_bwin_data_dir(tmp_path, account="jejesat76")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        doc = xml.dom.minidom.parseString(STALE_CONFIG)
        changed = _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        assert changed is True
        site = next(n for n in doc.getElementsByTagName("site") if n.getAttribute("site_name") == "Bwin.fr Poker")
        assert site.getAttribute("network") == "iPoker"
        assert site.getAttribute("HH_path") == str(tables)
        assert site.getAttribute("TS_path") == str(tables.parent / "Tournaments")
        assert site.getAttribute("screen_name") == "jejesat76"
        assert site.getAttribute("enabled") == "True"  # user choice preserved

        hhc = next(n for n in doc.getElementsByTagName("hhc") if n.getAttribute("site") == "Bwin.fr Poker")
        assert hhc.getAttribute("converter") == "iPokerToFpdb"
        assert hhc.getAttribute("summaryImporter") == "iPokerSummary"

        layout = site.getElementsByTagName("layout_set")[0]
        assert layout.getAttribute("ls") == "ipoker_default"

    def test_half_migrated_config_still_fixes_layout(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        half = STALE_CONFIG.replace(
            'network="PartyPoker"', 'network="iPoker"'
        ).replace('converter="PartyPokerToFpdb"', 'converter="iPokerToFpdb"')

        doc = xml.dom.minidom.parseString(half)
        changed = _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        assert changed is True
        site = next(n for n in doc.getElementsByTagName("site") if n.getAttribute("site_name") == "Bwin.fr Poker")
        assert site.getElementsByTagName("layout_set")[0].getAttribute("ls") == "ipoker_default"

    def test_layout_untouched_when_ipoker_default_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        no_ls = STALE_CONFIG.replace('<ls name="ipoker_default"/>', "")

        doc = xml.dom.minidom.parseString(no_ls)
        _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        site = next(n for n in doc.getElementsByTagName("site") if n.getAttribute("site_name") == "Bwin.fr Poker")
        assert site.getElementsByTagName("layout_set")[0].getAttribute("ls") == "party_default"

    def test_migration_is_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_bwin_data_dir(tmp_path)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        doc = xml.dom.minidom.parseString(STALE_CONFIG)
        config = _shell_config()
        assert config._migrate_entain_fr_sites_to_ipoker(doc) is True
        assert config._migrate_entain_fr_sites_to_ipoker(doc) is False

    def test_other_ipoker_sites_are_untouched(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        doc = xml.dom.minidom.parseString(STALE_CONFIG)
        _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        pmu = next(n for n in doc.getElementsByTagName("site") if n.getAttribute("site_name") == "PMU Poker")
        assert pmu.getAttribute("HH_path") == "C:\\PMU\\Tables"
        assert pmu.getAttribute("network") == "iPoker"

    def test_client_not_installed_keeps_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # empty: no bwin dir

        doc = xml.dom.minidom.parseString(STALE_CONFIG)
        changed = _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        assert changed is True  # network + converter still migrated
        site = next(n for n in doc.getElementsByTagName("site") if n.getAttribute("site_name") == "Bwin.fr Poker")
        assert site.getAttribute("network") == "iPoker"
        assert site.getAttribute("HH_path") == "C:\\Wrong\\PMU\\Tables"
        assert site.getAttribute("screen_name") == "jejsat76"

    def test_half_migrated_config_still_fixes_hhc(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        half = STALE_CONFIG.replace('network="PartyPoker"', 'network="iPoker"')

        doc = xml.dom.minidom.parseString(half)
        changed = _shell_config()._migrate_entain_fr_sites_to_ipoker(doc)

        assert changed is True
        hhc = next(n for n in doc.getElementsByTagName("hhc") if n.getAttribute("site") == "Bwin.fr Poker")
        assert hhc.getAttribute("converter") == "iPokerToFpdb"


class TestDispatcherPathDetection:
    def test_windows_data_dir_resolves_to_bwin_fr(self) -> None:
        assert detect_skin(BWIN_WINDOWS_PATH) == "Bwin.fr Poker"

    def test_parser_class_for_windows_path(self) -> None:
        assert get_parser_class_for_path(BWIN_WINDOWS_PATH) is BwinFrIPoker

    def test_macos_container_path_still_resolves(self) -> None:
        mac_path = (
            "/Users/x/Library/Containers/com.entainpt.bwinpokerfr.app/Data/Library/"
            "Application Support/Bwin.fr Online Poker/hero/History/Data/Tables/1.xml"
        )
        assert detect_skin(mac_path) == "Bwin.fr Poker"


class TestInstalledSiteDetection:
    def test_detect_skin_uses_windows_folder_alias(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_bwin_data_dir(tmp_path, account="jejesat76")
        monkeypatch.setattr(
            "fpdb_3_legacy.DetectInstalledSites.get_windows_paths",
            lambda: {"local_appdata": str(tmp_path), "appdata": str(tmp_path / "roaming")},
        )

        detector = object.__new__(iPokerDetector)
        detector.platform = "Windows"
        result = detector._detect_skin("Bwin.fr Poker")

        assert result["detected"] is True
        assert result["heroname"] == "jejesat76"
        assert result["hhpath"].endswith("Tables")
        assert "bwin Poker France" in result["hhpath"]


class TestIdentifySiteSkinSelection:
    @staticmethod
    def _config_site(name: str, hh_path: str, *, enabled: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            site_name=name,
            network="iPoker",
            HH_path=hh_path,
            TS_path="",
            enabled=enabled,
        )

    def test_ipoker_file_is_attributed_to_matching_skin(self, tmp_path: Path) -> None:
        from fpdb_3_legacy.IdentifySite import IdentifySite

        bwin_dir = tmp_path / "bwin" / "Tables"
        pmu_dir = tmp_path / "pmu" / "Tables"
        config = SimpleNamespace(
            supported_sites={
                "PMU Poker": self._config_site("PMU Poker", str(pmu_dir)),
                "Bwin.fr Poker": self._config_site("Bwin.fr Poker", str(bwin_dir)),
            },
        )
        idsite = object.__new__(IdentifySite)
        idsite.config = config
        fallback = SimpleNamespace(name="Redbet Poker")

        chosen = idsite._select_ipoker_skin_site(str(bwin_dir / "5869857694.xml"), fallback)

        assert chosen.name == "Bwin.fr Poker"

    def test_unmatched_path_keeps_fallback_when_nothing_enabled(self, tmp_path: Path) -> None:
        from fpdb_3_legacy.IdentifySite import IdentifySite

        config = SimpleNamespace(
            supported_sites={
                "PMU Poker": self._config_site("PMU Poker", str(tmp_path / "pmu"), enabled=False),
            },
        )
        idsite = object.__new__(IdentifySite)
        idsite.config = config
        fallback = SimpleNamespace(name="iPoker")

        chosen = idsite._select_ipoker_skin_site(str(tmp_path / "elsewhere" / "x.xml"), fallback)

        assert chosen.name == "iPoker"
