from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import patch

from fpdb_3_legacy.IdentifySite import IdentifySite
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary


def test_pokerstars_summary_detection_uses_skin_site() -> None:
    generic_site = SimpleNamespace(
        name="PokerStars.EU",
        filter_name="PokerStars",
        summary="PokerStarsSummary",
        re_Identify=re.compile(r"PokerStars Hand #"),
        re_SumIdentify=PokerStarsSummary.re_identify,
        re_HeroCards=None,
    )
    fr_site = SimpleNamespace(
        name="PokerStars.FR",
        filter_name="PokerStars",
        summary="PokerStarsSummary",
        re_Identify=re.compile(r"PokerStars Hand #"),
        re_SumIdentify=PokerStarsSummary.re_identify,
        re_HeroCards=None,
    )
    identifier = IdentifySite.__new__(IdentifySite)
    identifier.sitelist = {2: generic_site, 33: fr_site}

    text = """PokerStars Tournament #4006174726, No Limit Hold'em
Buy-In: €0.91/€0.09 EUR
3 players
Total Prize Pool: €9.50 EUR
"""

    with patch.object(identifier, "_select_pokerstars_skin_site", return_value=fr_site) as select_skin:
        fobj = identifier.idSite(
            "/Users/jde/Library/Application Support/PokerStarsFR/HandHistory/jeje_sat/"
            "TS20260605 T4006174726 No Limit Hold'em.txt",
            text,
            "utf8",
        )

    assert fobj.ftype == "summary"
    assert fobj.site.name == "PokerStars.FR"
    select_skin.assert_called_once()


def test_pokerstars_summary_detection_uses_detected_skin_when_config_lacks_site() -> None:
    generic_site = SimpleNamespace(
        name="PokerStars.EU",
        filter_name="PokerStars",
        summary="PokerStarsSummary",
        re_Identify=re.compile(r"PokerStars Hand #"),
        re_SumIdentify=PokerStarsSummary.re_identify,
        re_HeroCards=None,
    )
    identifier = IdentifySite.__new__(IdentifySite)
    identifier.config = None
    identifier.sitelist = {32: generic_site}

    text = """PokerStars Tournament #4006174726, No Limit Hold'em
Buy-In: €0.91/€0.09 EUR
3 players
Total Prize Pool: €9.50 EUR
"""

    with patch("fpdb_3_legacy.PokerStarsToFpdb.PokerStars") as pokerstars_cls:
        pokerstars_cls.return_value.detectPokerStarsSkin.return_value = ("PokerStars.FR", 33)
        fobj = identifier.idSite(
            "/Users/jde/Library/Application Support/PokerStarsFR/HandHistory/jeje_sat/"
            "TS20260605 T4006174726 No Limit Hold'em.txt",
            text,
            "utf8",
        )

    assert fobj.ftype == "summary"
    assert fobj.site.name == "PokerStars.FR"
    assert generic_site.name == "PokerStars.EU"
