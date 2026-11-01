"""Skin attribution for the PartyPoker network.

Every Party skin shares ``PartyPokerToFpdb`` and its ``siteId = 9``, so
``IdentifySite.generateSiteList`` keys them all on 9 and only the last ``<hhc>``
of the config survives. Without a skin resolver, every Party import was filed
under that arbitrary survivor -- typically a room the user never played and has
disabled, which then never appears in the report filters, so the hands are
imported yet invisible in the Hand Viewer.
"""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET  # noqa: S405 -- building only; parsing goes through defusedxml

import defusedxml.ElementTree as DefusedET
import pytest

from fpdb_3_legacy.IdentifySite import IdentifySite

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = ROOT / "HUD_config.xml.example"
CASH_HAND = ROOT / "regression-test-files" / "cash" / "PartyPoker" / "Flop" / "NLHE-EUR-0.05-0.10-201011.Sample.txt"


def _config_site(name: str, hh_path: str, *, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        site_name=name,
        network="PartyPoker",
        HH_path=hh_path,
        TS_path="",
        enabled=enabled,
    )


def _selector(**sites: SimpleNamespace) -> IdentifySite:
    idsite = object.__new__(IdentifySite)
    idsite.config = SimpleNamespace(supported_sites={s.site_name: s for s in sites.values()})
    return idsite


class TestSkinSelection:
    def test_file_is_attributed_to_the_skin_whose_path_matches(self, tmp_path: Path) -> None:
        party_dir = tmp_path / "PartyPoker" / "HandHistory"
        pmu_dir = tmp_path / "PMU" / "PMUPoker" / "HandHistory"
        idsite = _selector(
            party=_config_site("PartyPoker", str(party_dir)),
            pmu=_config_site("PMU Poker (PartyPoker)", str(pmu_dir)),
        )
        fallback = SimpleNamespace(name="PartyPoker")

        chosen = idsite._select_partypoker_skin_site(str(pmu_dir / "hand.txt"), fallback)

        assert chosen.name == "PMU Poker (PartyPoker)"

    def test_unmatched_path_falls_back_to_the_enabled_skin(self, tmp_path: Path) -> None:
        """The reported bug: the arbitrary survivor is a disabled skin.

        A file outside every configured HH path must land on the room the user
        actually enabled, not on whichever ``<hhc>`` the config happened to end
        with.
        """
        idsite = _selector(
            party=_config_site("PartyPoker", str(tmp_path / "party")),
            pmu=_config_site("PMU Poker (PartyPoker)", str(tmp_path / "pmu"), enabled=False),
        )
        fallback = SimpleNamespace(name="PMU Poker (PartyPoker)")

        chosen = idsite._select_partypoker_skin_site(str(tmp_path / "elsewhere" / "hand.txt"), fallback)

        assert chosen.name == "PartyPoker"

    def test_unmatched_path_keeps_the_fallback_when_nothing_is_enabled(self, tmp_path: Path) -> None:
        idsite = _selector(
            pmu=_config_site("PMU Poker (PartyPoker)", str(tmp_path / "pmu"), enabled=False),
        )
        fallback = SimpleNamespace(name="PartyPoker")

        chosen = idsite._select_partypoker_skin_site(str(tmp_path / "elsewhere" / "hand.txt"), fallback)

        assert chosen.name == "PartyPoker"


def _config_with_two_party_skins(tmp_path: Path) -> Path:
    """Write a config where a disabled Party skin is the last <hhc>."""
    tree = DefusedET.parse(EXAMPLE_CONFIG)
    root = tree.getroot()

    sites = root.find("supported_sites")
    assert sites is not None
    party = next(s for s in sites.iter("site") if s.get("site_name") == "PartyPoker")
    party.set("network", "PartyPoker")
    party.set("enabled", "True")
    party.set("screen_name", "Hero")

    pmu = copy.deepcopy(party)
    pmu.set("site_name", "PMU Poker (PartyPoker)")
    pmu.set("enabled", "False")
    pmu.set("screen_name", "")
    pmu.set("HH_path", "")
    sites.append(pmu)

    hhcs = root.find("hhcs")
    assert hhcs is not None
    ET.SubElement(hhcs, "hhc", {"site": "PMU Poker (PartyPoker)", "converter": "PartyPokerToFpdb"})

    path = tmp_path / "HUD_config.xml"
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_import_lands_on_the_enabled_skin_not_the_last_hhc(tmp_path: Path) -> None:
    """End to end: identification of a real hand history through a full config."""
    from fpdb_3_legacy.Configuration import Config

    config = Config(file=str(_config_with_two_party_skins(tmp_path)))
    idsite = IdentifySite(config)

    # The collision itself is unchanged: both skins key on PartyPokerToFpdb.siteId.
    assert idsite.sitelist[9].name == "PMU Poker (PartyPoker)"

    path = str(CASH_HAND)
    idsite.processFile(path)

    assert idsite.filelist[path].site.name == "PartyPoker"
    assert config.get_site_id("PartyPoker") == 9


if __name__ == "__main__":
    pytest.main([__file__])
