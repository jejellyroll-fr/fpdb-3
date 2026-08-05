from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from fpdb_3_legacy.iPoker.base import iPoker

log = get_logger("ipoker_dispatcher")


@dataclass(frozen=True, slots=True)
class IPokerSkin:
    indicators: tuple[str, ...]
    site_name: str
    module_name: str
    default_site_id: int | None = None
    parser_class_name: str | None = None

    @property
    def class_name(self) -> str:
        if self.parser_class_name:
            return self.parser_class_name
        return "".join(part.capitalize() for part in self.module_name.split("_")) + "IPoker"


IPOKER_SKINS: tuple[IPokerSkin, ...] = (
    IPokerSkin(("redbet",), "Redbet Poker", "redbet", 91, "RedbetIPoker"),
    IPokerSkin(("pmu",), "PMU Poker", "pmu", 56, "PMUIPoker"),
    IPokerSkin(("fdj", "en ligne"), "FDJ Poker", "fdj", 57, "FDJIPoker"),
    IPokerSkin(("betclic",), "Betclic Poker", "betclic", 131, "BetclicIPoker"),
    IPokerSkin(
        # "bwin poker france" is the Windows client's data directory
        # (%LOCALAPPDATA%\bwin Poker France\data\<account>\History\...),
        # "bwinfr" its install/roaming directory name.
        ("bwinpokerfr", "bwin.fr", "bwin.fr online poker", "bwin poker france", "bwinfr"),
        "Bwin.fr Poker",
        "bwin_fr",
        40,
        "BwinFrIPoker",
    ),
    IPokerSkin(("partypokerfr", "partypoker.fr", "partypoker.fr online poker"), "PartyPoker.fr", "partypoker_fr", 44, "PartyPokerFrIPoker"),
    IPokerSkin(("netbet",), "NetBet Poker", "netbet", 59),
    IPokerSkin(("poker770",), "Poker770", "poker770", 58),
    IPokerSkin(("barriere",), "Barrière Poker", "barriere", 60),
    IPokerSkin(("titan",), "Titan Poker", "titan", 62),
    IPokerSkin(("bet365",), "Bet365 Poker", "bet365", 63),
    IPokerSkin(("william hill", "williamhill"), "William Hill Poker", "william_hill", 64),
    IPokerSkin(("paddy power", "paddypower"), "Paddy Power Poker", "paddy_power", 65),
    IPokerSkin(("betfair",), "Betfair Poker", "betfair", 66),
    IPokerSkin(("coral",), "Coral Poker", "coral", 67),
    IPokerSkin(("genting",), "Genting Poker", "genting", 68),
    IPokerSkin(("mansion",), "Mansion Poker", "mansion", 69),
    IPokerSkin(("winner",), "Winner Poker", "winner", 70),
    IPokerSkin(("ladbrokes",), "Ladbrokes Poker", "ladbrokes", 71),
    IPokerSkin(("sky",), "Sky Poker", "sky", 72),
    IPokerSkin(("sisal",), "Sisal Poker", "sisal", 73),
    IPokerSkin(("lottomatica",), "Lottomatica Poker", "lottomatica", 74),
    IPokerSkin(("eurobet",), "Eurobet Poker", "eurobet", 75),
    IPokerSkin(("snai",), "Snai Poker", "snai", 76),
    IPokerSkin(("goldbet",), "Goldbet Poker", "goldbet", 77),
    IPokerSkin(("casino barcelona",), "Casino Barcelona Poker", "casino_barcelona", 78),
    IPokerSkin(("sportium",), "Sportium Poker", "sportium", 79),
    IPokerSkin(("marca",), "Marca Apuestas Poker", "marca", 80),
    IPokerSkin(("everest",), "Everest Poker", "everest", 81),
    IPokerSkin(("bet-at-home",), "Bet-at-home Poker", "bet_at_home", 82),
    IPokerSkin(("mybet",), "Mybet Poker", "mybet", 83),
    IPokerSkin(("betsson",), "Betsson Poker", "betsson", 84),
    IPokerSkin(("betsafe",), "Betsafe Poker", "betsafe", 85),
    IPokerSkin(("nordicbet",), "NordicBet Poker", "nordicbet", 86),
    IPokerSkin(("unibet",), "Unibet Poker", "unibet", 87),
    IPokerSkin(("maria",), "Maria Casino Poker", "maria", 88),
    IPokerSkin(("leovegas",), "LeoVegas Poker", "leovegas", 89),
    IPokerSkin(("mr green",), "Mr Green Poker", "mr_green", 90),
    IPokerSkin(("expekt",), "Expekt Poker", "expekt"),
    IPokerSkin(("coolbet",), "Coolbet Poker", "coolbet"),
    IPokerSkin(("chilipoker",), "Chilipoker", "chilipoker"),
    IPokerSkin(("dafa", "dafabet"), "Dafabet Poker", "dafabet"),
    IPokerSkin(("fun88",), "Fun88 Poker", "fun88"),
    IPokerSkin(("betfred",), "Betfred Poker", "betfred"),
    IPokerSkin(("guts",), "Guts Poker", "guts"),
    IPokerSkin(("sportingbet",), "Sportingbet Poker", "sportingbet"),
    IPokerSkin(("multipoker",), "MultiPoker", "multipoker"),
    IPokerSkin(("red star", "redstar"), "Red Star Poker", "red_star"),
)

_SKINS_BY_SITE_NAME = {skin.site_name: skin for skin in IPOKER_SKINS}


class IPokerSkinDispatcher:
    def __init__(self, skins: tuple[IPokerSkin, ...] = IPOKER_SKINS) -> None:
        self.skins = skins

    def detect(self, path: str) -> IPokerSkin | None:
        path_lower = path.lower()
        for skin in self.skins:
            if any(indicator in path_lower for indicator in skin.indicators):
                log.info("Detected iPoker skin: %s from path: %s", skin.site_name, path)
                return skin
        log.info("No specific iPoker skin detected from path: %s, using default 'iPoker'", path)
        return None

    def detect_site_name(self, path: str) -> str:
        skin = self.detect(path)
        return skin.site_name if skin else "iPoker"

    def get_by_site_name(self, site_name: str) -> IPokerSkin:
        try:
            return _SKINS_BY_SITE_NAME[site_name]
        except KeyError:
            known = ", ".join(sorted(_SKINS_BY_SITE_NAME))
            raise KeyError(f"Unknown iPoker skin site_name '{site_name}'. Known values: {known}") from None


DEFAULT_DISPATCHER = IPokerSkinDispatcher()


def detect_skin(path: str) -> str:
    return DEFAULT_DISPATCHER.detect_site_name(path)


def get_parser_class_for_skin(skin: IPokerSkin | None) -> type[iPoker]:
    if skin is None:
        from fpdb_3_legacy.iPoker.base import iPoker

        return iPoker

    module = import_module(f"fpdb_3_legacy.iPoker.skins.{skin.module_name}")
    return getattr(module, skin.class_name)


def get_parser_class_for_path(path: str) -> type[iPoker]:
    return get_parser_class_for_skin(DEFAULT_DISPATCHER.detect(path))


def resolve_site_id(config: Any, site_name: str) -> int:
    if site_name == "iPoker":
        return 14

    skin = _SKINS_BY_SITE_NAME.get(site_name)
    configured_site_ids = getattr(config, "site_ids", None)
    if configured_site_ids and site_name in configured_site_ids and hasattr(config, "get_site_id"):
        return config.get_site_id(site_name)

    if skin and skin.default_site_id is not None:
        return skin.default_site_id

    if hasattr(config, "get_site_id"):
        return config.get_site_id(site_name)
    return 14
