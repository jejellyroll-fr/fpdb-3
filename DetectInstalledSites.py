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

    def __init__(self, config):
        super().__init__(config)
        self.all_detected_skins = []  # Store all detected skins

    def detect(self) -> Dict[str, any]:
        ipoker_skins = [
            # French Skins
            "PMU Poker",
            "FDJ Poker",
            "En ligne",  # Parions Sport en ligne (FDJ)
            "Parions Sport en ligne",
            "Betclic Poker",
            "Betclic PokerX",
            "BetclicPoker",
            "Poker770",
            "NetBet Poker",
            "Barrière Poker",
            "Winamax Poker",  # old iPoker skin
            # UK Skins
            "Red Star Poker",
            "RedStar Poker",
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
            # Italian Skins
            "Sisal Poker",
            "Lottomatica Poker",
            "Eurobet Poker",
            "Snai Poker",
            "Goldbet Poker",
            "Gioco Digitale",
            "Gioco Digitale Poker",
            # Spanish Skins
            "Casino Barcelona Poker",
            "Sportium Poker",
            "Marca Apuestas Poker",
            "Marca Poker",
            # German/Austrian Skins
            "Everest Poker",
            "Bet-at-home Poker",
            "Mybet Poker",
            "bwin Poker",  # Sometimes uses iPoker
            # Nordic Skins
            "Betsson Poker",
            "Betsson",
            "betsson",
            "Betsafe Poker",
            "NordicBet Poker",
            "Nordicbet Poker",
            # Other European Skins
            "Unibet Poker",
            "Maria Casino Poker",
            "LeoVegas Poker",
            "Mr Green Poker",
            "Redbet Poker",
            "Expekt Poker",
            "Coolbet Poker",
            # Network/Generic
            "iPoker",
            "Playtech Poker",
            "iPoker Network",
            # Additional skins that might exist
            "Chilipoker",
            "Poker Heaven",
            "Blue Square Poker",
            "Dafa Poker",
            "Dafabet Poker",
            "Fun88 Poker",
            "Bet-at-home",
            "NetBet",
            "NetBet.fr",
            "NetBet.it",
            "Betclic.fr",
            "Betclic.it",
            "PMU.fr",
            "FDJ.fr",
            # Alternative names
            "PMUPoker",
            "FDJPoker",
            "BetclicPoker",
            "RedStarPoker",
            "TitanPoker",
            "WilliamHill",
            "PaddyPower",
            "BetfairPoker",
            "CoralPoker",
            "GentingPoker",
            "MansionPoker",
            "WinnerPoker",
            "LadbrokesPoker",
            "SkyPoker",
        ]

        # Detect all iPoker skins
        self.all_detected_skins = []
        
        # First try individual skin folders
        for skin in ipoker_skins:
            result = self._detect_skin(skin)
            if result["detected"]:
                self.all_detected_skins.append(result)

        # Then try PokerClient folder structure
        result = self._detect_pokerclient()
        if result["detected"]:
            self.all_detected_skins.append(result)

        # Return the first detected skin for backward compatibility
        if self.all_detected_skins:
            return self.all_detected_skins[0]
            
        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def get_all_detected_skins(self) -> List[Dict[str, any]]:
        """Get all detected iPoker skins"""
        return self.all_detected_skins

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
            # Wine paths for Windows clients
            wine_paths = []
            wine_local = os.path.join(
                paths["wine_users"], "*", "AppData", "Local", skin, "data"
            )
            wine_paths.extend(glob.glob(wine_local))
            
            # Also check Program Files in Wine
            wine_pf = os.path.join(paths["wine_program_files"], skin, "data")
            wine_pf_x86 = os.path.join(paths["wine_program_files_x86"], skin, "data")
            
            if wine_paths:
                base_path = wine_paths[0]
            else:
                base_path = self._check_path_exists(wine_pf, wine_pf_x86)

        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            # Check for sandboxed apps in Containers
            home = os.path.expanduser("~")
            containers_path = os.path.join(home, "Library", "Containers")
            
            # Special handling for known macOS iPoker apps
            if skin == "PMU Poker":
                # PMU Poker on macOS uses a sandboxed container
                pmu_container = os.path.join(containers_path, "fr.pmu.poker.macos", "Data", "Library", "Application Support", "PMU Online Poker")
                if os.path.exists(pmu_container):
                    base_path = pmu_container
            elif skin in ["FDJ Poker", "En ligne", "Parions Sport en ligne"]:
                # FDJ/En ligne on macOS uses a sandboxed container
                fdj_container = os.path.join(containers_path, "fr.fdj.poker.macos", "Data", "Library", "Application Support", "En Ligne")
                if os.path.exists(fdj_container):
                    base_path = fdj_container
            else:
                # For other skins, check standard locations
                base_path = self._check_path_exists(
                    os.path.join(paths["app_support"], skin, "data"),
                    os.path.join(paths["documents"], skin, "data"),
                    # Some iPoker clients on macOS might use different structures
                    os.path.join(paths["app_support"], skin),
                    os.path.join(paths["documents"], skin)
                )

        if base_path and os.path.exists(base_path):
            try:
                # Look for player folders (can be numeric or alphanumeric)
                for item in os.listdir(base_path):
                    item_path = os.path.join(base_path, item)
                    # Skip common non-player folders
                    if item in ["cache", "logs", "plugins", "qml", "missions"]:
                        continue
                        
                    if os.path.isdir(item_path):
                        # Check for History/Data structure
                        hhpath = os.path.join(item_path, "History", "Data", "Tables")
                        tspath = os.path.join(
                            item_path, "History", "Data", "Tournaments"
                        )

                        if os.path.exists(hhpath) or os.path.exists(os.path.dirname(hhpath)):
                            # Détecté même si le dossier Tables n'existe pas encore
                            # mais que la structure History/Data existe
                            return {
                                "detected": True,
                                "hhpath": hhpath,
                                "heroname": item,
                                "tspath": tspath if os.path.exists(tspath) else "",
                                "skin": skin,
                                "has_hands": os.path.exists(hhpath) and len(os.listdir(hhpath)) > 0 if os.path.exists(hhpath) else False,
                            }
            except (OSError, PermissionError) as e:
                log.error(f"Error detecting iPoker ({skin}): {e}")

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_pokerclient(self) -> Dict[str, any]:
        """Detect iPoker skins in PokerClient folder structure"""
        pokerclient_path = None
        
        if self.platform == "Windows":
            paths = get_windows_paths()
            pokerclient_path = os.path.join(paths["local_appdata"], "PokerClient")
        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Check Wine paths
            wine_pokerclient = os.path.join(
                paths["wine_users"], "*", "AppData", "Local", "PokerClient"
            )
            wine_paths = glob.glob(wine_pokerclient)
            if wine_paths:
                pokerclient_path = wine_paths[0]
        elif self.platform == "Darwin":  # macOS
            paths = get_mac_paths()
            pokerclient_path = self._check_path_exists(
                os.path.join(paths["app_support"], "PokerClient"),
                os.path.join(paths["documents"], "PokerClient")
            )
        
        if not pokerclient_path or not os.path.exists(pokerclient_path):
            return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}
            
        try:
            # Map of PokerClient subfolder names to skin names
            skin_mapping = {
                "pmupoker": "PMU Poker",
                "pmu": "PMU Poker",
                "fdjpoker": "FDJ Poker",
                "fdj": "FDJ Poker",
                "betclicpokerfr": "Betclic Poker",
                "betclicpoker": "Betclic Poker",
                "betclic": "Betclic Poker",
                "betfairpoker": "Betfair Poker",
                "betfair": "Betfair Poker",
                "nordicbet.com": "NordicBet Poker",
                "nordicbet": "NordicBet Poker",
                "betsson.com": "Betsson Poker",
                "betsson": "Betsson Poker",
                "redstar": "Red Star Poker",
                "redstarpoker": "Red Star Poker",
                "williamhill": "William Hill Poker",
                "williamhillpoker": "William Hill Poker",
                "paddypower": "Paddy Power Poker",
                "paddypowerpoker": "Paddy Power Poker",
                "coral": "Coral Poker",
                "coralpoker": "Coral Poker",
                "ladbrokes": "Ladbrokes Poker",
                "ladbrokespoker": "Ladbrokes Poker",
                "skypoker": "Sky Poker",
                "sky": "Sky Poker",
                "titan": "Titan Poker",
                "titanpoker": "Titan Poker",
                "winner": "Winner Poker",
                "winnerpoker": "Winner Poker",
                "mansion": "Mansion Poker",
                "mansionpoker": "Mansion Poker",
                "genting": "Genting Poker",
                "gentingpoker": "Genting Poker",
                "bet365": "Bet365 Poker",
                "bet365poker": "Bet365 Poker",
                "unibet": "Unibet Poker",
                "unibetpoker": "Unibet Poker",
                "betsafe": "Betsafe Poker",
                "betsafepoker": "Betsafe Poker",
                "netbet": "NetBet Poker",
                "netbetpoker": "NetBet Poker",
                "poker770": "Poker770",
            }
            
            # Check each skin folder
            for folder_name, skin_name in skin_mapping.items():
                skin_path = os.path.join(pokerclient_path, folder_name, "data")
                if os.path.exists(skin_path):
                    # Look for player folders
                    for item in os.listdir(skin_path):
                        item_path = os.path.join(skin_path, item)
                        # Skip common non-player folders
                        if item in ["cache", "logs", "plugins", "qml", "missions"]:
                            continue
                            
                        if os.path.isdir(item_path):
                            # Check for History/Data structure
                            hhpath = os.path.join(item_path, "History", "Data", "Tables")
                            tspath = os.path.join(item_path, "History", "Data", "Tournaments")
                            
                            if os.path.exists(hhpath):
                                return {
                                    "detected": True,
                                    "hhpath": hhpath,
                                    "heroname": item,
                                    "tspath": tspath if os.path.exists(tspath) else "",
                                    "skin": skin_name,
                                }
        except (OSError, PermissionError) as e:
            log.error(f"Error detecting iPoker in PokerClient folder: {e}")
            
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
                f"C:\\{skin}\\handHistory",
                "C:\\ACR Poker\\handHistory",
                f"C:\\Program Files\\{skin}\\handHistory",
                f"C:\\Program Files (x86)\\{skin}\\handHistory",
            )
            tspath = self._check_path_exists(
                f"C:\\{skin}\\TournamentSummary",
                "C:\\ACR Poker\\TournamentSummary",
                f"C:\\Program Files\\{skin}\\TournamentSummary",
                f"C:\\Program Files (x86)\\{skin}\\TournamentSummary",
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

    def __init__(self, config):
        super().__init__(config)
        self.all_detected_skins = []  # Store all detected skins

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

        # Detect all PartyPoker skins
        self.all_detected_skins = []
        
        # First check C:\Programs for specific installations
        programs_result = self._detect_programs_installations()
        if programs_result:
            self.all_detected_skins.extend(programs_result)
        
        # Then check standard paths for other skins
        for skin in partygaming_skins:
            # Skip if already detected in C:\Programs
            if any(s['skin'] == skin for s in self.all_detected_skins):
                continue
                
            result = self._detect_skin(skin)
            if result["detected"]:
                self.all_detected_skins.append(result)

        # Return the first detected skin for backward compatibility
        if self.all_detected_skins:
            return self.all_detected_skins[0]
            
        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def get_all_detected_skins(self) -> List[Dict[str, any]]:
        """Get all detected PartyPoker skins"""
        return self.all_detected_skins

    def _detect_skin(self, skin: str) -> Dict[str, any]:
        """Detect a specific PartyGaming skin"""
        hhpath = None
        tspath = None
        actual_skin_name = skin  # Keep track of the actual skin name

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
                f"C:\\{skin}\\HandHistory",
                "C:\\PartyGaming\\PartyPoker\\HandHistory",
                "C:\\Program Files\\PartyGaming\\PartyPoker\\HandHistory",
                "C:\\Program Files (x86)\\PartyGaming\\PartyPoker\\HandHistory",
                # C:\Programs paths (custom installation) - removed to avoid false positives
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
                f"C:\\{skin}\\TournSummary",
                "C:\\PartyGaming\\PartyPoker\\TournSummary",
                "C:\\Program Files\\PartyGaming\\PartyPoker\\TournSummary",
                "C:\\Program Files (x86)\\PartyGaming\\PartyPoker\\TournSummary",
                # C:\Programs paths - removed to avoid false positives
            )

        elif self.platform == "Linux":
            paths = get_linux_paths()
            # Wine installation paths
            wine_docs = os.path.join(paths["wine_users"], "*", "Documents", skin, "HandHistory")
            wine_docs_paths = glob.glob(wine_docs)
            
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
                wine_docs_paths[0] if wine_docs_paths else None,
            )
            
            wine_docs_ts = os.path.join(paths["wine_users"], "*", "Documents", skin, "TournSummary")
            wine_docs_ts_paths = glob.glob(wine_docs_ts)
            
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
                wine_docs_ts_paths[0] if wine_docs_ts_paths else None,
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
            # Check if hhpath contains hero folders or hand history files directly
            if os.path.exists(hhpath):
                try:
                    items = os.listdir(hhpath)
                    # Check if there are .txt files (hand histories) directly in the folder
                    txt_files = [f for f in items if f.endswith(('.txt', '.xml'))]
                    if txt_files:
                        # Hand histories are directly in this folder
                        return {
                            "detected": True,
                            "hhpath": hhpath,
                            "heroname": "Hero",  # Generic hero name
                            "tspath": tspath if tspath and os.path.exists(tspath) else "",
                            "skin": skin,
                        }
                    else:
                        # Look for hero folders
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
                except (OSError, PermissionError) as e:
                    log.error(f"Error accessing PartyPoker path {hhpath}: {e}")

        return {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}

    def _detect_programs_installations(self) -> List[Dict[str, any]]:
        """Detect PartyPoker installations in C:\Programs"""
        if self.platform != "Windows":
            return []
            
        detected = []
        programs_path = "C:\\Programs"
        
        if not os.path.exists(programs_path):
            return []
            
        # Mapping of folder names to actual skin names
        folder_mapping = {
            "bwincom": {"subfolder": "bwincomPoker", "skin": "bwin Poker"},
            "PartyGaming": {"subfolder": "PartyPoker", "skin": "PartyPoker"},
            "PMU": {"subfolder": "PMUPoker", "skin": "PMU Poker (PartyPoker)"},
        }
        
        for folder, info in folder_mapping.items():
            base_path = os.path.join(programs_path, folder, info["subfolder"])
            if os.path.exists(base_path):
                hhpath = os.path.join(base_path, "HandHistory")
                tspath = os.path.join(base_path, "TournSummary")
                
                if os.path.exists(hhpath):
                    # Check if hhpath contains hero folders or hand history files directly
                    try:
                        items = os.listdir(hhpath)
                        # Filter out XMLHandHistory
                        items = [item for item in items if item != "XMLHandHistory"]
                        
                        # Check if there are .txt files directly
                        txt_files = [f for f in items if f.endswith(('.txt', '.xml')) and os.path.isfile(os.path.join(hhpath, f))]
                        if txt_files:
                            # Hand histories are directly in this folder
                            detected.append({
                                "detected": True,
                                "hhpath": hhpath,
                                "heroname": "Hero",
                                "tspath": tspath if os.path.exists(tspath) else "",
                                "skin": info["skin"],
                            })
                        else:
                            # Look for hero folders
                            heroes = [item for item in items if os.path.isdir(os.path.join(hhpath, item))]
                            if heroes:
                                hero = heroes[0]  # Take first hero
                                final_hhpath = os.path.join(hhpath, hero)
                                final_tspath = os.path.join(tspath, hero) if os.path.exists(tspath) else ""
                                
                                detected.append({
                                    "detected": True,
                                    "hhpath": final_hhpath,
                                    "heroname": hero,
                                    "tspath": final_tspath,
                                    "skin": info["skin"],
                                })
                    except (OSError, PermissionError) as e:
                        log.error(f"Error accessing {hhpath}: {e}")
                        
        return detected


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
                f"C:\\{skin}\\HandHistory",
                "C:\\Cake Poker\\HandHistory",
                "C:\\Everygame Poker\\HandHistory",
                "C:\\Program Files\\Cake Poker\\HandHistory",
                "C:\\Program Files (x86)\\Cake Poker\\HandHistory",
                "C:\\Program Files\\Everygame Poker\\HandHistory",
                "C:\\Program Files (x86)\\Everygame Poker\\HandHistory",
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
                f"C:\\{skin}\\TournSummary",
                "C:\\Cake Poker\\TournSummary",
                "C:\\Everygame Poker\\TournSummary",
                "C:\\Program Files\\Cake Poker\\TournSummary",
                "C:\\Program Files (x86)\\Cake Poker\\TournSummary",
                "C:\\Program Files\\Everygame Poker\\TournSummary",
                "C:\\Program Files (x86)\\Everygame Poker\\TournSummary",
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

    def get_all_ipoker_skins(self) -> List[Dict[str, any]]:
        """Get all detected iPoker skins"""
        if "iPoker" in self.detectors:
            detector = self.detectors["iPoker"]
            if hasattr(detector, "all_detected_skins"):
                return detector.all_detected_skins
        return []

    def get_all_partypoker_skins(self) -> List[Dict[str, any]]:
        """Get all detected PartyPoker skins"""
        if "PartyPoker" in self.detectors:
            detector = self.detectors["PartyPoker"]
            if hasattr(detector, "all_detected_skins"):
                return detector.all_detected_skins
        elif "PartyGaming" in self.detectors:
            detector = self.detectors["PartyGaming"]
            if hasattr(detector, "all_detected_skins"):
                return detector.all_detected_skins
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

