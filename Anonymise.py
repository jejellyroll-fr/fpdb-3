#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2009-2011 Carl Gherardi
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


import os
import re
import codecs
import Options
import HandHistoryConverter
from IdentifySite import IdentifySite
import Configuration
import sys
import time
import WinamaxToFpdb, BetfairToFpdb, BovadaToFpdb, CakeToFpdb, GGPokerToFpdb, iPokerToFpdb,KingsClubToFpdb, MergeToFpdb, PacificPokerToFpdb, PartyPokerToFpdb, WinningToFpdb, PokerStarsToFpdb
import chardet
from L10n import set_locale_translation


def sanitize_filter_name(input_str):
    """
    Sanitizes a filter name by removing any leading "hh" characters and trimming any leading or trailing whitespace.

    Args:
        input_str (str): The input filter name to sanitize.

    Returns:
        str: The sanitized filter name.
    """
    # If the input string starts with "hh", remove those characters
    if input_str.startswith("hh"):
        input_str = input_str[2:]
    # Trim any leading or trailing whitespace from the input string
    return input_str.strip()


def anonymize_hand_history(file_path, hero_name):
    """
    This function anonymizes the player names in a hand history file.
    Args:
        file_path (str): The path to the hand history file.
        hero_name (str): The name of the hero player to replace with 'Hero'.

    Returns:
        None
    """
    # Load the configuration file
    config_file = f"{Configuration.CONFIG_PATH}/HUD_config.xml"
    config = Configuration.Config(config_file)

    # Create an IdentifySite object and process the hand history file
    id_site = IdentifySite(config)
    id_site.processFile(file_path)
    set_locale_translation()
    for f, ffile in list(id_site.filelist.items()):
        tmp = ""
        tmp += f"{ffile.ftype} "
        if ffile.ftype == "hh":
            tmp += f" {ffile.site.hhc_fname}"
        elif ffile.ftype == "summary":
            tmp += f" {ffile.site.summary}"
    # print(f'{count} files identified')

    # Sanitize the filter name and print it
    filter_name = sanitize_filter_name(tmp)
    # print(filter_name)

    # Choose the appropriate regular expression pattern based on the filter name
    patterns = {
        "WinamaxToFpdb": WinamaxToFpdb.Winamax.re_PlayerInfo,
        "BetfairToFpdb": BetfairToFpdb.Betfair.re_PlayerInfo,
        "BovadaToFpdb": BovadaToFpdb.Bovada.re_PlayerInfo,
        "CakeToFpdb": CakeToFpdb.Cake.re_PlayerInfo,
        "GGPokerToFpdb": GGPokerToFpdb.GGPoker.re_PlayerInfo,
        "iPokerToFpdb": iPokerToFpdb.iPoker.re_PlayerInfo,
        "KingsClubToFpdb": KingsClubToFpdb.KingsClub.re_PlayerInfo,
        "MergeToFpdb": MergeToFpdb.Merge.re_PlayerInfo,
        "PacificPokerToFpdb": PacificPokerToFpdb.PacificPoker.re_PlayerInfo,
        "PartyPokerToFpdb": PartyPokerToFpdb.PartyPoker.re_PlayerInfo,
        "PokerStarsToFpdb": PokerStarsToFpdb.PokerStars.re_PlayerInfo,
        "WinningToFpdb": WinningToFpdb.Winning.re_PlayerInfo1
    }

    regex = patterns.get(filter_name)
    if regex is None:
        return

    # Open the hand history file, detect the encoding, and read the file contents
    if os.path.exists(file_path):
        with open(file_path, 'rb') as in_file:
            raw_data = in_file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']

            with codecs.open(file_path, 'r', encoding) as in_fh:
                filecontents = in_fh.read()
    else:
        print(f"Could not find file {file_path}")
        exit(1)

    # Find all occurrences of player names using the regular expression pattern
    m = regex.finditer(filecontents)

    outfile = f"{file_path}.anon"
    print(f"Output being written to {outfile}")

    savestdout = sys.stdout
    with open(outfile, "w") as fsock:
        sys.stdout = fsock

        players = []
        for a in m:
            players = players + [a.group('PNAME')]

        uniq = set(players)

        for i, name in enumerate(uniq):
                filecontents = filecontents.replace(name, "Hero" if name == hero_name else f'Player{i}')

        # print(filecontents.encode('utf-8').decode())

        sys.stdout = savestdout


# Usage example:
# anonymize_hand_history("C:/MyHandsArchive_H2N/2023/2/21/Ferrare 03.txt", "jejellyroll")


