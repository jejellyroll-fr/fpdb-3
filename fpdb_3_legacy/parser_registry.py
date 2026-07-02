#!/usr/bin/env python
from __future__ import annotations

import importlib
import re
from functools import cache

from fpdb_3_legacy.AbsoluteToFpdb import Absolute
from fpdb_3_legacy.BetfairToFpdb import Betfair
from fpdb_3_legacy.BetOnlineToFpdb import BetOnline
from fpdb_3_legacy.BossToFpdb import Boss
from fpdb_3_legacy.BovadaSummary import BovadaSummary
from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.EnetToFpdb import Enet
from fpdb_3_legacy.EntractionToFpdb import Entraction
from fpdb_3_legacy.EverestToFpdb import Everest
from fpdb_3_legacy.EverleafToFpdb import Everleaf
from fpdb_3_legacy.FullTiltPokerSummary import FullTiltPokerSummary
from fpdb_3_legacy.FulltiltToFpdb import Fulltilt
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.iPokerSummary import iPokerSummary
from fpdb_3_legacy.iPokerToFpdb import iPoker
from fpdb_3_legacy.KingsClubToFpdb import KingsClub
from fpdb_3_legacy.MergeSummary import MergeSummary
from fpdb_3_legacy.MergeToFpdb import Merge
from fpdb_3_legacy.MicrogamingToFpdb import Microgaming
from fpdb_3_legacy.OnGameToFpdb import OnGame
from fpdb_3_legacy.PacificPokerSummary import PacificPokerSummary
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker
from fpdb_3_legacy.PkrToFpdb import Pkr
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.PokerTrackerSummary import PokerTrackerSummary
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs
from fpdb_3_legacy.TourneySummary import TourneySummary
from fpdb_3_legacy.UnibetSummary import UnibetSummary
from fpdb_3_legacy.UnibetToFpdb import Unibet
from fpdb_3_legacy.WinamaxSummary import WinamaxSummary
from fpdb_3_legacy.WinamaxToFpdb import Winamax
from fpdb_3_legacy.WinningSummary import WinningSummary
from fpdb_3_legacy.WinningToFpdb import Winning

LEGACY_MODULE_REGISTRY = {
    "AbsoluteToFpdb": "fpdb_3_legacy.AbsoluteToFpdb",
    "BetfairToFpdb": "fpdb_3_legacy.BetfairToFpdb",
    "BetOnlineToFpdb": "fpdb_3_legacy.BetOnlineToFpdb",
    "BossToFpdb": "fpdb_3_legacy.BossToFpdb",
    "BovadaSummary": "fpdb_3_legacy.BovadaSummary",
    "BovadaToFpdb": "fpdb_3_legacy.BovadaToFpdb",
    "CakeToFpdb": "fpdb_3_legacy.CakeToFpdb",
    "EnetToFpdb": "fpdb_3_legacy.EnetToFpdb",
    "EntractionToFpdb": "fpdb_3_legacy.EntractionToFpdb",
    "EverestToFpdb": "fpdb_3_legacy.EverestToFpdb",
    "EverleafToFpdb": "fpdb_3_legacy.EverleafToFpdb",
    "FullTiltPokerSummary": "fpdb_3_legacy.FullTiltPokerSummary",
    "FulltiltToFpdb": "fpdb_3_legacy.FulltiltToFpdb",
    "GGPokerToFpdb": "fpdb_3_legacy.GGPokerToFpdb",
    "KingsClubToFpdb": "fpdb_3_legacy.KingsClubToFpdb",
    "MergeSummary": "fpdb_3_legacy.MergeSummary",
    "MergeToFpdb": "fpdb_3_legacy.MergeToFpdb",
    "MicrogamingToFpdb": "fpdb_3_legacy.MicrogamingToFpdb",
    "OnGameToFpdb": "fpdb_3_legacy.OnGameToFpdb",
    "PacificPokerSummary": "fpdb_3_legacy.PacificPokerSummary",
    "PacificPokerToFpdb": "fpdb_3_legacy.PacificPokerToFpdb",
    "PartyPokerToFpdb": "fpdb_3_legacy.PartyPokerToFpdb",
    "PkrToFpdb": "fpdb_3_legacy.PkrToFpdb",
    "PokerStarsSummary": "fpdb_3_legacy.PokerStarsSummary",
    "PokerStarsToFpdb": "fpdb_3_legacy.PokerStarsToFpdb",
    "PokerTrackerSummary": "fpdb_3_legacy.PokerTrackerSummary",
    "PokerTrackerToFpdb": "fpdb_3_legacy.PokerTrackerToFpdb",
    "SealsWithClubsToFpdb": "fpdb_3_legacy.SealsWithClubsToFpdb",
    "TourneySummary": "fpdb_3_legacy.TourneySummary",
    "UnibetSummary": "fpdb_3_legacy.UnibetSummary",
    "UnibetToFpdb": "fpdb_3_legacy.UnibetToFpdb",
    "WinamaxSummary": "fpdb_3_legacy.WinamaxSummary",
    "WinamaxToFpdb": "fpdb_3_legacy.WinamaxToFpdb",
    "WinningSummary": "fpdb_3_legacy.WinningSummary",
    "WinningToFpdb": "fpdb_3_legacy.WinningToFpdb",
    "iPokerSummary": "fpdb_3_legacy.iPokerSummary",
    "iPokerToFpdb": "fpdb_3_legacy.iPokerToFpdb",
}

PARSER_CLASS_REGISTRY = {
    "Absolute": Absolute,
    "BetOnline": BetOnline,
    "Betfair": Betfair,
    "Boss": Boss,
    "Bovada": Bovada,
    "Cake": Cake,
    "Enet": Enet,
    "Entraction": Entraction,
    "Everest": Everest,
    "Everleaf": Everleaf,
    "Fulltilt": Fulltilt,
    "GGPoker": GGPoker,
    "KingsClub": KingsClub,
    "Merge": Merge,
    "Microgaming": Microgaming,
    "OnGame": OnGame,
    "PacificPoker": PacificPoker,
    "PartyPoker": PartyPoker,
    "Pkr": Pkr,
    "PokerStars": PokerStars,
    "PokerTracker": PokerTracker,
    "SealsWithClubs": SealsWithClubs,
    "Unibet": Unibet,
    "Winamax": Winamax,
    "Winning": Winning,
    "iPoker": iPoker,
}

SUMMARY_CLASS_REGISTRY = {
    "BovadaSummary": BovadaSummary,
    "FullTiltPokerSummary": FullTiltPokerSummary,
    "MergeSummary": MergeSummary,
    "PacificPokerSummary": PacificPokerSummary,
    "PokerStarsSummary": PokerStarsSummary,
    "PokerTrackerSummary": PokerTrackerSummary,
    "TourneySummary": TourneySummary,
    "UnibetSummary": UnibetSummary,
    "WinamaxSummary": WinamaxSummary,
    "WinningSummary": WinningSummary,
    "iPokerSummary": iPokerSummary,
}

_VALID_LEGACY_MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _unknown_key(kind: str, name: str, known: dict[str, type]) -> KeyError:
    return KeyError(f"Unknown {kind} '{name}'. Known values: {', '.join(sorted(known))}")


def get_parser_class(filter_name: str) -> type:
    try:
        return PARSER_CLASS_REGISTRY[filter_name]
    except KeyError:
        raise _unknown_key("parser filter_name", filter_name, PARSER_CLASS_REGISTRY) from None


def get_summary_class(summary_name: str) -> type:
    try:
        return SUMMARY_CLASS_REGISTRY[summary_name]
    except KeyError:
        raise _unknown_key("summary importer", summary_name, SUMMARY_CLASS_REGISTRY) from None


@cache
def import_fpdb_module(name: str):
    """Compatibility loader for scripts that still expect module objects."""
    if not _VALID_LEGACY_MODULE_NAME.fullmatch(name):
        exc = ModuleNotFoundError(f"Unsupported fpdb module name: {name!r}")
        exc.name = name
        raise exc

    module_name = LEGACY_MODULE_REGISTRY.get(name, f"fpdb_3_legacy.{name}")
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        return importlib.import_module(name)
