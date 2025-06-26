#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2011 Gimick bbtgaf@googlemail.com
# Updated 2024 - Modernized version with improved site detection
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.

"""
Modernized poker site detection module.

Detects installed poker sites by scanning common installation paths and
hand history directories. Supports multiple platforms (Windows, Linux, macOS)
and handles multiple hero names per site.

Features:
- Support for PokerStars (all regions: .com, .fr, .it, .es, .pt)
- Winamax detection with account-specific paths
- iPoker network (all major skins including French FDJ, PMU, Italian, etc.)
- Americas Cardroom (ACR) and WPN network
- SealsWithClubs (SwC)
- Improved error handling and logging
- Cross-platform compatibility
- Multiple hero detection
- Archive folder filtering

Usage:
    detector = DetectInstalledSites()  # Detect all sites
    detector = DetectInstalledSites("PokerStars")  # Detect specific site
"""

import glob
import os
import platform
from typing import Dict, List, Optional

import Configuration
from loggingFpdb import get_logger

log = get_logger("config")


# Platform-specific path helpers
def get_windows_paths():
    """Get Windows-specific paths"""
    return {
        "program_files": os.getenv("ProgramFiles", "C:\\Program Files"),
        "program_files_x86": os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        "local_appdata": os.getenv("LOCALAPPDATA", ""),
        "appdata": os.getenv("APPDATA", ""),
        "userprofile": os.getenv("USERPROFILE", ""),
    }


def get_linux_paths():
    """Get Linux-specific paths (Wine)"""
    home = os.path.expanduser("~")
    return {
        "wine_drive_c": os.path.join(home, ".wine", "drive_c"),
        "wine_program_files": os.path.join(home, ".wine", "drive_c", "Program Files"),
        "wine_program_files_x86": os.path.join(
            home, ".wine", "drive_c", "Program Files (x86)"
        ),
        "wine_users": os.path.join(home, ".wine", "drive_c", "users"),
    }


def get_mac_paths():
    """Get macOS-specific paths"""
    home = os.path.expanduser("~")
    return {
        "applications": "/Applications",
        "app_support": os.path.join(home, "Library", "Application Support"),
        "documents": os.path.join(home, "Documents"),
    }


class SiteDetector:
    """Base class for site-specific detectors"""

    def __init__(self, config):
        self.config = config
        self.os_family = config.os_family
        self.platform = platform.system()

    def detect(self) -> Dict[str, any]:
        """Override in subclasses"""
        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _find_heroes_in_path(
        self, path: str, exclude_dirs: List[str] = None
    ) -> List[str]:
        """Find hero directories in a given path, excluding common non-hero folders"""
        if exclude_dirs is None:
            exclude_dirs = [
                "archive",
                "backup",
                "old",
                "temp",
                "XMLHandHistory",
                "TournSummary",
                "Replayer",
                "Avatars",
                "Sounds",
            ]

        heroes = []
        if os.path.exists(path):
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if (
                        os.path.isdir(item_path)
                        and item.lower() not in [d.lower() for d in exclude_dirs]
                        and not item.startswith(".")
                    ):
                        heroes.append(item)
            except (OSError, PermissionError) as e:
                log.debug(f"Cannot access {path}: {e}")

        return heroes

    def _check_path_exists(self, *paths) -> Optional[str]:
        """Check if any of the given paths exist and return the first one found"""
        for path in paths:
            if path and os.path.exists(path):
                return path
        return None


class PokerStarsDetector(SiteDetector):
    """PokerStars detector supporting all regions (.com, .fr, .it, .es, .pt)"""

    def detect(self) -> Dict[str, any]:
        # Platform-specific variant names
        if self.platform == "Darwin":  # macOS
            pokerstars_variants = [
                "PokerStars",
                "PokerStarsFR",  # macOS uses no dot
                "PokerStarsIT",
                "PokerStarsES",
                "PokerStarsPT",
                "PokerStarsEU",
            ]
        else:  # Windows and Linux
            pokerstars_variants = [
                "PokerStars",
                "PokerStars.FR",
                "PokerStars.IT",
                "PokerStars.ES",
                "PokerStars.PT",
                "PokerStars.EU",
            ]

        # Detecting all installed variants
        detected_variants = []
        for variant in pokerstars_variants:
            result = self._detect_variant(variant)
            if result["detected"]:
                detected_variants.append(result)

        # Return the first found for compatibility, but store all the variants detected
        if detected_variants:
            # Store all detected variants for future use
            self.all_detected_variants = detected_variants
            return detected_variants[0]

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_variant(self, variant: str) -> Dict[str, any]:
        """Detect a specific PokerStars variant"""
        hhpath = None
        tspath = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            # Modern Windows (Vista+)
            hhpath = self._check_path_exists(
                os.path.join(paths["local_appdata"], variant, "HandHistory"),
                os.path.join(paths["appdata"], variant, "HandHistory"),
                os.path.join(paths["program_files"], variant, "HandHistory"),
                os.path.join(paths["program_files_x86"], variant, "HandHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["local_appdata"], variant, "TournSummary"),
                os.path.join(paths["appdata"], variant, "TournSummary"),
                os.path.join(paths["program_files"], variant, "TournSummary"),
                os.path.join(paths["program_files_x86"], variant, "TournSummary"),
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Wine installation
            hhpath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], variant, "HandHistory"),
                os.path.join(paths["wine_program_files_x86"], variant, "HandHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], variant, "TournSummary"),
                os.path.join(paths["wine_program_files_x86"], variant, "TournSummary"),
            )

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            # macOS paths - check both with and without dots for compatibility
            base_variant = variant.replace(".", "")  # Remove dots for macOS paths
            hhpath = self._check_path_exists(
                os.path.join(paths["app_support"], variant, "HandHistory"),
                os.path.join(paths["app_support"], base_variant, "HandHistory"),
                # Alternative paths that might exist
                os.path.join(paths["documents"], variant, "HandHistory"),
                os.path.join(paths["documents"], base_variant, "HandHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["app_support"], variant, "TournSummary"),
                os.path.join(paths["app_support"], base_variant, "TournSummary"),
                os.path.join(paths["documents"], variant, "TournSummary"),
                os.path.join(paths["documents"], base_variant, "TournSummary"),
            )

        if hhpath:
            heroes = self._find_heroes_in_path(hhpath)
            if heroes:
                hero = heroes[0]  # Take first hero found
                final_hhpath = os.path.join(hhpath, hero)
                final_tspath = os.path.join(tspath, hero) if tspath else ""

                return {
                    "detected": True,
                    "hhpath": final_hhpath,
                    "heroname": hero,
                    "tspath": final_tspath,
                    "variant": variant,
                }

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class WinamaxDetector(SiteDetector):
    """Winamax detector with account-specific path handling"""

    def detect(self) -> Dict[str, any]:
        base_path = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            base_path = self._check_path_exists(
                os.path.join(paths["appdata"], "Winamax", "accounts"),
                os.path.join(paths["local_appdata"], "Winamax", "accounts"),
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Check for Wine installation TODO: new native linux app
            wine_appdata = os.path.join(
                paths["wine_users"], "*", "AppData", "Roaming", "Winamax", "accounts"
            )
            wine_paths = glob.glob(wine_appdata)
            if wine_paths:
                base_path = wine_paths[0]

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            base_path = self._check_path_exists(
                os.path.join(paths["app_support"], "Winamax", "documents", "accounts"),
                os.path.join(paths["app_support"], "Winamax", "accounts"),
            )

        if base_path and os.path.exists(base_path):
            try:
                # Look for account folders
                accounts = os.listdir(base_path)
                for account in accounts:
                    account_path = os.path.join(base_path, account)
                    if os.path.isdir(account_path):
                        history_path = os.path.join(account_path, "history")
                        if os.path.exists(history_path):
                            return {
                                "detected": True,
                                "hhpath": history_path,
                                "heroname": account,
                                "tspath": "",  # Winamax doesn't separate tournament summaries
                            }
            except (OSError, PermissionError) as e:
                log.error(f"Error detecting Winamax: {e}")

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class iPokerDetector(SiteDetector):
    """iPoker network detector supporting all major skins including French, Italian, Spanish"""

    def detect(self) -> Dict[str, any]:
        ipoker_skins = [
            # Fech Skins
            "PMU Poker",
            "FDJ Poker",
            "Poker770",  # old skin
            "NetBet Poker",  # old skin
            "Barrière Poker",  # old skin
            "Winamax Poker",  # old skin
            # Skins UK
            "Red Star Poker",
            "Titan Poker",
            "Bet365 Poker",
            "William Hill Poker",
            "Paddy Power Poker",
            "Betfair Poker",
            "Coral Poker",
            "Genting Poker",
            "Mansion Poker",
            "Winner Poker",
            "Ladbrokes Poker",
            "Sky Poker",
            # Skins IT
            "Sisal Poker",
            "Lottomatica Poker",
            "Eurobet Poker",
            "Snai Poker",
            "Goldbet Poker",
            # Skins ES
            "Casino Barcelona Poker",
            "Sportium Poker",
            "Marca Apuestas Poker",
            # Skins GE
            "Everest Poker",
            "Bet-at-home Poker",
            "Mybet Poker",
            # Skins nordics
            "Betsson Poker",
            "Betsafe Poker",
            "NordicBet Poker",
            # other
            "Unibet Poker",
            "Maria Casino Poker",
            "LeoVegas Poker",
            "Mr Green Poker",
            "Redbet Poker",
            # Skins network
            "iPoker",
            "Playtech Poker",
        ]

        for skin in ipoker_skins:
            result = self._detect_skin(skin)
            if result["detected"]:
                return result

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_skin(self, skin: str) -> Dict[str, any]:
        """Detect a specific iPoker skin"""
        base_path = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            base_path = self._check_path_exists(
                os.path.join(paths["local_appdata"], skin, "data"),
                os.path.join(paths["appdata"], skin, "data"),
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            wine_path = os.path.join(
                paths["wine_users"], "*", "AppData", "Local", skin, "data"
            )
            wine_paths = glob.glob(wine_path)
            if wine_paths:
                base_path = wine_paths[0]

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            base_path = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "data")
            )

        if base_path and os.path.exists(base_path):
            try:
                # Look for player ID folders (usually numeric)
                for item in os.listdir(base_path):
                    if item.isdigit():
                        player_path = os.path.join(base_path, item)
                        hhpath = os.path.join(player_path, "History", "Data", "Tables")
                        tspath = os.path.join(
                            player_path, "History", "Data", "Tournaments"
                        )

                        if os.path.exists(hhpath):
                            return {
                                "detected": True,
                                "hhpath": hhpath,
                                "heroname": item,
                                "tspath": tspath if os.path.exists(tspath) else "",
                                "skin": skin,
                            }
            except (OSError, PermissionError) as e:
                log.error(f"Error detecting iPoker ({skin}): {e}")

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class ACRDetector(SiteDetector):
    """Americas Cardroom (ACR) and WPN network detector"""

    def detect(self) -> Dict[str, any]:
        wpn_skins = [
            "Americas Cardroom",
            "ACR Poker",
            "WinningPoker",
            "BlackChipPoker",
            "TruePoker",
            "Ya Poker",
        ]

        for skin in wpn_skins:
            result = self._detect_skin(skin)
            if result["detected"]:
                return result

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_skin(self, skin: str) -> Dict[str, any]:
        """Detect a specific WPN skin"""
        hhpath = None
        tspath = None

        if self.platform == "Windows":
            # ACR typically installs to C:\ACR Poker\ or similar
            hhpath = self._check_path_exists(
                f"C:\\{skin}\\handHistory\\",
                "C:\\ACR Poker\\handHistory\\",
                f"C:\\Program Files\\{skin}\\handHistory\\",
                f"C:\\Program Files (x86)\\{skin}\\handHistory\\",
            )
            tspath = self._check_path_exists(
                f"C:\\{skin}\\TournamentSummary\\",
                "C:\\ACR Poker\\TournamentSummary\\",
                f"C:\\Program Files\\{skin}\\TournamentSummary\\",
                f"C:\\Program Files (x86)\\{skin}\\TournamentSummary\\",
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            hhpath = self._check_path_exists(
                os.path.join(paths["wine_drive_c"], skin, "handHistory"),
                os.path.join(paths["wine_drive_c"], "ACR Poker", "handHistory"),
                os.path.join(paths["wine_program_files"], skin, "handHistory"),
                os.path.join(paths["wine_program_files_x86"], skin, "handHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["wine_drive_c"], skin, "TournamentSummary"),
                os.path.join(paths["wine_drive_c"], "ACR Poker", "TournamentSummary"),
                os.path.join(paths["wine_program_files"], skin, "TournamentSummary"),
                os.path.join(
                    paths["wine_program_files_x86"], skin, "TournamentSummary"
                ),
            )

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            hhpath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "handHistory"),
                os.path.join(paths["app_support"], "ACR Poker", "handHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "TournamentSummary"),
                os.path.join(paths["app_support"], "ACR Poker", "TournamentSummary"),
            )

        if hhpath:
            heroes = self._find_heroes_in_path(hhpath)
            if heroes:
                hero = heroes[0]
                final_hhpath = os.path.join(hhpath, hero)
                final_tspath = os.path.join(tspath, hero) if tspath else ""

                return {
                    "detected": True,
                    "hhpath": final_hhpath,
                    "heroname": hero,
                    "tspath": final_tspath,
                    "skin": skin,
                }

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class SealsWithClubsDetector(SiteDetector):
    """SealsWithClubs (SwC) detector"""

    def detect(self) -> Dict[str, any]:
        hhpath = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            hhpath = self._check_path_exists(
                os.path.join(
                    paths["userprofile"], "Documents", "SwC Poker", "Hand History"
                ),
                os.path.join(
                    paths["userprofile"], "Documents", "SealsWithClubs", "Hand History"
                ),
                "C:\\Program Files\\SealsWithClubs\\handhistories",
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            wine_docs = os.path.join(
                paths["wine_users"], "*", "Documents", "SwC Poker", "Hand History"
            )
            wine_paths = glob.glob(wine_docs)
            if wine_paths:
                hhpath = wine_paths[0]
            else:
                hhpath = self._check_path_exists(
                    os.path.join(
                        paths["wine_program_files"], "SealsWithClubs", "handhistories"
                    )
                )

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            hhpath = self._check_path_exists(
                os.path.join(paths["documents"], "SwC Poker", "Hand History"),
                os.path.join(paths["documents"], "SealsWithClubs", "Hand History"),
                os.path.join(paths["app_support"], "SealsWithClubs", "Hand History"),
            )

        if hhpath and os.path.exists(hhpath):
            # SwC typically doesn't use separate hero folders
            # Check if there are any .txt files (hand histories)
            try:
                files = os.listdir(hhpath)
                txt_files = [f for f in files if f.endswith(".txt")]
                if txt_files:
                    return {
                        "detected": True,
                        "hhpath": hhpath,
                        "heroname": "Hero",  # SwC uses generic hero name
                        "tspath": "",
                    }
            except (OSError, PermissionError) as e:
                log.error(f"Error detecting SealsWithClubs: {e}")

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class PartyGamingDetector(SiteDetector):
    """PartyGaming/PartyPoker network detector supporting all major skins"""

    def detect(self) -> Dict[str, any]:
        partygaming_skins = [
            # PartyPoker main brand
            "PartyPoker",
            "Party Poker",
            # PartyGaming network skins
            "Bwin Poker",
            "Bwin.fr Poker",
            "Bwin.it Poker",
            "Bwin.es Poker",
            "Bwin.de Poker",
            # European skins
            "PartyPoker.fr",
            "PartyPoker.it",
            "PartyPoker.es",
            "PartyPoker.de",
            # Other PartyGaming brands
            "Gamebookers Poker",
            "Empire Poker",
            "Intertops Poker",
            "MultiPoker",
            "PokerRoom",
            # Regional variants
            "PartyPoker NJ",
            "BorgataPoker",
            "Borgata Poker",
            # Legacy skins
            "PartyGaming",
            "Party Gaming",
        ]

        for skin in partygaming_skins:
            result = self._detect_skin(skin)
            if result["detected"]:
                return result

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_skin(self, skin: str) -> Dict[str, any]:
        """Detect a specific PartyGaming skin"""
        hhpath = None
        tspath = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            # PartyPoker typically installs to Program Files
            hhpath = self._check_path_exists(
                os.path.join(paths["local_appdata"], skin, "HandHistory"),
                os.path.join(paths["appdata"], skin, "HandHistory"),
                os.path.join(paths["program_files"], skin, "HandHistory"),
                os.path.join(paths["program_files_x86"], skin, "HandHistory"),
                # Alternative paths for PartyPoker
                os.path.join(paths["userprofile"], "Documents", skin, "HandHistory"),
                os.path.join(paths["userprofile"], "My Documents", skin, "HandHistory"),
                # Legacy paths
                f"C:\\{skin}\\HandHistory\\",
                "C:\\PartyGaming\\PartyPoker\\HandHistory\\",
                "C:\\Program Files\\PartyGaming\\PartyPoker\\HandHistory\\",
                "C:\\Program Files (x86)\\PartyGaming\\PartyPoker\\HandHistory\\",
            )
            tspath = self._check_path_exists(
                os.path.join(paths["local_appdata"], skin, "TournSummary"),
                os.path.join(paths["appdata"], skin, "TournSummary"),
                os.path.join(paths["program_files"], skin, "TournSummary"),
                os.path.join(paths["program_files_x86"], skin, "TournSummary"),
                os.path.join(paths["userprofile"], "Documents", skin, "TournSummary"),
                os.path.join(
                    paths["userprofile"], "My Documents", skin, "TournSummary"
                ),
                f"C:\\{skin}\\TournSummary\\",
                "C:\\PartyGaming\\PartyPoker\\TournSummary\\",
                "C:\\Program Files\\PartyGaming\\PartyPoker\\TournSummary\\",
                "C:\\Program Files (x86)\\PartyGaming\\PartyPoker\\TournSummary\\",
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Wine installation paths
            hhpath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], skin, "HandHistory"),
                os.path.join(paths["wine_program_files_x86"], skin, "HandHistory"),
                os.path.join(paths["wine_drive_c"], skin, "HandHistory"),
                os.path.join(
                    paths["wine_program_files"],
                    "PartyGaming",
                    "PartyPoker",
                    "HandHistory",
                ),
                os.path.join(
                    paths["wine_program_files_x86"],
                    "PartyGaming",
                    "PartyPoker",
                    "HandHistory",
                ),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], skin, "TournSummary"),
                os.path.join(paths["wine_program_files_x86"], skin, "TournSummary"),
                os.path.join(paths["wine_drive_c"], skin, "TournSummary"),
                os.path.join(
                    paths["wine_program_files"],
                    "PartyGaming",
                    "PartyPoker",
                    "TournSummary",
                ),
                os.path.join(
                    paths["wine_program_files_x86"],
                    "PartyGaming",
                    "PartyPoker",
                    "TournSummary",
                ),
            )

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            hhpath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "HandHistory"),
                os.path.join(paths["documents"], skin, "HandHistory"),
                os.path.join(
                    paths["app_support"], "PartyGaming", "PartyPoker", "HandHistory"
                ),
                os.path.join(
                    paths["documents"], "PartyGaming", "PartyPoker", "HandHistory"
                ),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "TournSummary"),
                os.path.join(paths["documents"], skin, "TournSummary"),
                os.path.join(
                    paths["app_support"], "PartyGaming", "PartyPoker", "TournSummary"
                ),
                os.path.join(
                    paths["documents"], "PartyGaming", "PartyPoker", "TournSummary"
                ),
            )

        if hhpath:
            heroes = self._find_heroes_in_path(hhpath)
            if heroes:
                hero = heroes[0]  # Take first hero found
                final_hhpath = os.path.join(hhpath, hero)
                final_tspath = os.path.join(tspath, hero) if tspath else ""

                return {
                    "detected": True,
                    "hhpath": final_hhpath,
                    "heroname": hero,
                    "tspath": final_tspath,
                    "skin": skin,
                }

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class CPNDetector(SiteDetector):
    """CPN/Everygame network detector (anciennement Cake Poker Network)"""

    def detect(self) -> Dict[str, any]:
        cpn_skins = [
            # Network
            "Everygame Poker",
            "Everygame",
            # old Cake
            "Cake Poker",
            "Cake",
            # Skins netork CPN/Everygame
            "Juicy Stakes",
            "Juicy Stakes Poker",
            "JuicyStakes",
            # Skins EU
            "RedStar Poker",
            "Red Star Poker",
            "RedStar",
            # Skins US
            "Sportsbetting.ag Poker",
            "Sportsbetting Poker",
            "SportsBetting.ag",
            # other
            "BetOnline Poker",
            "BetOnline.ag",
            "Tiger Gaming",
            "TigerGaming",
            # Skins old
            "Doyles Room",
            "DoylesRoom",
            "Poker4Ever",
            "Poker 4 Ever",
            # Skins locals
            "PlayersOnly",
            "Players Only",
            "SunPoker",
            "Sun Poker",
            # Variants
            "CPN",
            "Cake Poker Network",
        ]

        for skin in cpn_skins:
            result = self._detect_skin(skin)
            if result["detected"]:
                return result

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_skin(self, skin: str) -> Dict[str, any]:
        """Detect a specific CPN/Everygame skin"""
        hhpath = None
        tspath = None

        if self.platform == "Windows":
            paths = get_windows_paths()
            # CPN/Everygame typically installs to Program Files or AppData
            hhpath = self._check_path_exists(
                os.path.join(paths["local_appdata"], skin, "HandHistory"),
                os.path.join(paths["appdata"], skin, "HandHistory"),
                os.path.join(paths["program_files"], skin, "HandHistory"),
                os.path.join(paths["program_files_x86"], skin, "HandHistory"),
                # Alternative paths for Everygame/Cake
                os.path.join(paths["userprofile"], "Documents", skin, "HandHistory"),
                os.path.join(paths["userprofile"], "My Documents", skin, "HandHistory"),
                # Legacy Cake paths
                f"C:\\{skin}\\HandHistory\\",
                "C:\\Cake Poker\\HandHistory\\",
                "C:\\Everygame Poker\\HandHistory\\",
                "C:\\Program Files\\Cake Poker\\HandHistory\\",
                "C:\\Program Files (x86)\\Cake Poker\\HandHistory\\",
                "C:\\Program Files\\Everygame Poker\\HandHistory\\",
                "C:\\Program Files (x86)\\Everygame Poker\\HandHistory\\",
            )
            tspath = self._check_path_exists(
                os.path.join(paths["local_appdata"], skin, "TournSummary"),
                os.path.join(paths["appdata"], skin, "TournSummary"),
                os.path.join(paths["program_files"], skin, "TournSummary"),
                os.path.join(paths["program_files_x86"], skin, "TournSummary"),
                os.path.join(paths["userprofile"], "Documents", skin, "TournSummary"),
                os.path.join(
                    paths["userprofile"], "My Documents", skin, "TournSummary"
                ),
                f"C:\\{skin}\\TournSummary\\",
                "C:\\Cake Poker\\TournSummary\\",
                "C:\\Everygame Poker\\TournSummary\\",
                "C:\\Program Files\\Cake Poker\\TournSummary\\",
                "C:\\Program Files (x86)\\Cake Poker\\TournSummary\\",
                "C:\\Program Files\\Everygame Poker\\TournSummary\\",
                "C:\\Program Files (x86)\\Everygame Poker\\TournSummary\\",
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Wine installation paths
            hhpath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], skin, "HandHistory"),
                os.path.join(paths["wine_program_files_x86"], skin, "HandHistory"),
                os.path.join(paths["wine_drive_c"], skin, "HandHistory"),
                os.path.join(paths["wine_program_files"], "Cake Poker", "HandHistory"),
                os.path.join(
                    paths["wine_program_files_x86"], "Cake Poker", "HandHistory"
                ),
                os.path.join(
                    paths["wine_program_files"], "Everygame Poker", "HandHistory"
                ),
                os.path.join(
                    paths["wine_program_files_x86"], "Everygame Poker", "HandHistory"
                ),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["wine_program_files"], skin, "TournSummary"),
                os.path.join(paths["wine_program_files_x86"], skin, "TournSummary"),
                os.path.join(paths["wine_drive_c"], skin, "TournSummary"),
                os.path.join(paths["wine_program_files"], "Cake Poker", "TournSummary"),
                os.path.join(
                    paths["wine_program_files_x86"], "Cake Poker", "TournSummary"
                ),
                os.path.join(
                    paths["wine_program_files"], "Everygame Poker", "TournSummary"
                ),
                os.path.join(
                    paths["wine_program_files_x86"], "Everygame Poker", "TournSummary"
                ),
            )

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            hhpath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "HandHistory"),
                os.path.join(paths["documents"], skin, "HandHistory"),
                os.path.join(paths["app_support"], "Cake Poker", "HandHistory"),
                os.path.join(paths["documents"], "Cake Poker", "HandHistory"),
                os.path.join(paths["app_support"], "Everygame Poker", "HandHistory"),
                os.path.join(paths["documents"], "Everygame Poker", "HandHistory"),
            )
            tspath = self._check_path_exists(
                os.path.join(paths["app_support"], skin, "TournSummary"),
                os.path.join(paths["documents"], skin, "TournSummary"),
                os.path.join(paths["app_support"], "Cake Poker", "TournSummary"),
                os.path.join(paths["documents"], "Cake Poker", "TournSummary"),
                os.path.join(paths["app_support"], "Everygame Poker", "TournSummary"),
                os.path.join(paths["documents"], "Everygame Poker", "TournSummary"),
            )

        if hhpath:
            heroes = self._find_heroes_in_path(hhpath)
            if heroes:
                hero = heroes[0]  # Take first hero found
                final_hhpath = os.path.join(hhpath, hero)
                final_tspath = os.path.join(tspath, hero) if tspath else ""

                return {
                    "detected": True,
                    "hhpath": final_hhpath,
                    "heroname": hero,
                    "tspath": final_tspath,
                    "skin": skin,
                }

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


class DetectInstalledSites:
    """Main class for detecting installed poker sites"""

    def __init__(self, sitename="All"):
        self.config = Configuration.Config()
        self.sitestatusdict = {}
        self.sitename = sitename
        self.heroname = ""
        self.hhpath = ""
        self.tspath = ""
        self.detected = ""

        # Modern supported sites with priority order
        self.supported_sites = [
            "PokerStars",
            "Winamax",
            "iPoker",
            "ACR",
            "SealsWithClubs",
            # Legacy sites (keeping for compatibility)
            "PartyPoker",
            "PartyGaming",
            "Merge",
            "Full Tilt Poker",
            "PacificPoker",
            "Cake",
            "CPN",
            "Everygame",
            "Bovada",
            "GGPoker",
            "Unibet",
            "KingsClub",
            "BetOnline",
        ]

        # Initialize detectors
        self.detectors = {
            "PokerStars": PokerStarsDetector(self.config),
            "Winamax": WinamaxDetector(self.config),
            "iPoker": iPokerDetector(self.config),
            "ACR": ACRDetector(self.config),
            "SealsWithClubs": SealsWithClubsDetector(self.config),
            "PartyGaming": PartyGamingDetector(self.config),
            "PartyPoker": PartyGamingDetector(self.config),
            "CPN": CPNDetector(self.config),
            "Cake": CPNDetector(self.config),
            "Everygame": CPNDetector(self.config),
        }

        # Run detection
        if sitename == "All":
            for site in self.supported_sites:
                self.sitestatusdict[site] = self.detect(site)
        else:
            self.sitestatusdict[sitename] = self.detect(sitename)
            if sitename in self.sitestatusdict:
                result = self.sitestatusdict[sitename]
                self.heroname = result["heroname"]
                self.hhpath = result["hhpath"]
                self.tspath = result["tspath"]
                self.detected = result["detected"]

    def detect(self, site_name: str) -> Dict[str, any]:
        """Detect a specific poker site"""
        if site_name in self.detectors:
            try:
                result = self.detectors[site_name].detect()
                if result["detected"]:
                    log.info(
                        f"Detected {site_name}: {result['heroname']} at {result['hhpath']}"
                    )
                return result
            except Exception as e:
                log.error(f"Error detecting {site_name}: {e}")
                return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}
        else:
            # Fallback to legacy detection for unsupported sites
            return self._legacy_detect(site_name)

    def _legacy_detect(self, site_name: str) -> Dict[str, any]:
        """Legacy detection method for older sites"""
        # This would contain the old detection logic for sites not yet modernized
        # For now, return not detected
        log.debug(f"Legacy detection not implemented for {site_name}")
        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def get_detected_sites(self) -> List[str]:
        """Get list of detected sites"""
        return [
            site for site, status in self.sitestatusdict.items() if status["detected"]
        ]

    def get_site_info(self, site_name: str) -> Optional[Dict[str, any]]:
        """Get detection info for a specific site"""
        return self.sitestatusdict.get(site_name)

    def get_all_pokerstars_variants(self) -> List[Dict[str, any]]:
        """Get all detected PokerStars variants"""
        if "PokerStars" in self.detectors:
            detector = self.detectors["PokerStars"]
            if hasattr(detector, "all_detected_variants"):
                return detector.all_detected_variants
        return []

    @property
    def supportedSites(self):
        """Compatibility property for legacy code that expects supportedSites"""
        return self.supported_sites


# For backward compatibility
if __name__ == "__main__":
    # Test the detection
    detector = DetectInstalledSites()
    detected_sites = detector.get_detected_sites()

    print("Detected poker sites:")
    for site in detected_sites:
        info = detector.get_site_info(site)
        print(f"  {site}: {info['heroname']} -> {info['hhpath']}")

    if not detected_sites:
        print("No poker sites detected.")
