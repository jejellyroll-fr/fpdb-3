#!/usr/bin/env python

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


import codecs
import os
import sys

import chardet

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Configuration
from IdentifySite import IdentifySite
from L10n import set_locale_translation

# Optional imports - only load when needed
SITE_MODULES = {}


def get_site_regex(filter_name):
    """Get regex pattern for a specific poker site."""
    site_mappings = {
        "WinamaxToFpdb": ("WinamaxToFpdb", "Winamax", "re_player_info"),
        "BovadaToFpdb": ("BovadaToFpdb", "Bovada", "re_player_info"),
        "CakeToFpdb": ("CakeToFpdb", "Cake", "re_player_info"),
        "GGPokerToFpdb": ("GGPokerToFpdb", "GGPoker", "re_player_info"),
        "iPokerToFpdb": ("iPokerToFpdb", "iPoker", "re_player_info"),
        "KingsClubToFpdb": ("KingsClubToFpdb", "KingsClub", "re_PlayerInfo"),
        "MergeToFpdb": ("MergeToFpdb", "Merge", "re_PlayerInfo"),
        "PacificPokerToFpdb": ("PacificPokerToFpdb", "PacificPoker", "re_PlayerInfo"),
        "PartyPokerToFpdb": ("PartyPokerToFpdb", "PartyPoker", "re_PlayerInfo"),
        "PokerStarsToFpdb": ("PokerStarsToFpdb", "PokerStars", "re_player_info"),
        "WinningToFpdb": ("WinningToFpdb", "Winning", "re_PlayerInfo1"),
    }

    if filter_name not in site_mappings:
        return None

    module_name, class_name, regex_name = site_mappings[filter_name]

    try:
        # Dynamically import the module
        module = __import__(module_name)
        site_class = getattr(module, class_name)
        regex = getattr(site_class, regex_name)
        return regex
    except (ImportError, AttributeError) as e:
        print(f"Could not load regex for {filter_name}: {e}")
        return None


def sanitize_filter_name(input_str):
    """Sanitizes a filter name by removing any leading "hh" characters and trimming any leading or trailing whitespace.

    Args:
        input_str (str): The input filter name to sanitize.

    Returns:
        str: The sanitized filter name.

    """
    # If the input string starts with "hh", remove those characters
    input_str = input_str.removeprefix("hh")
    # Trim any leading or trailing whitespace from the input string
    return input_str.strip()


def anonymize_hand_history(file_path, hero_name, output_file=None, force_site=None) -> None:
    """This function anonymizes the player names in a hand history file.

    Args:
        file_path (str): The path to the hand history file.
        hero_name (str): The name of the hero player to replace with 'Hero'.

    Returns:
        None

    """
    if force_site:
        # Use manually specified site
        filter_name = f"{force_site}ToFpdb"
        print(f"Using manually specified site: {force_site}")
    else:
        # Auto-detect site
        config_file = f"{Configuration.CONFIG_PATH}/HUD_config.xml"
        config = Configuration.Config(config_file)

        # Create an IdentifySite object and process the hand history file
        id_site = IdentifySite(config)
        id_site.processFile(file_path)
        set_locale_translation()
        for _f, ffile in list(id_site.filelist.items()):
            tmp = ""
            tmp += f"{ffile.ftype} "
            if ffile.ftype == "hh":
                tmp += f" {ffile.site.hhc_fname}"
            elif ffile.ftype == "summary":
                tmp += f" {ffile.site.summary}"
        # print(f'{count} files identified')

        # Sanitize the filter name and print it
        filter_name = sanitize_filter_name(tmp)
        print(f"Auto-detected site: {filter_name}")
    # print(filter_name)

    # Choose the appropriate regular expression pattern based on the filter name
    regex = get_site_regex(filter_name)
    if regex is None:
        print(f"Unsupported site: {filter_name}")
        print("Using simple fallback anonymization...")
        # Simple fallback - just replace the hero name
        if os.path.exists(file_path):
            with open(file_path, "rb") as in_file:
                raw_data = in_file.read()
                result = chardet.detect(raw_data)
                encoding = result["encoding"]

                with codecs.open(file_path, "r", encoding) as in_fh:
                    filecontents = in_fh.read()

            # Simple replacement of hero name
            filecontents = filecontents.replace(hero_name, "Hero")

            outfile = output_file or f"{file_path}.anon"
            with open(outfile, "w", encoding=encoding) as fsock:
                fsock.write(filecontents)

            print(f"Simple anonymization completed: {outfile}")
        return

    # Open the hand history file, detect the encoding, and read the file contents
    if os.path.exists(file_path):
        with open(file_path, "rb") as in_file:
            raw_data = in_file.read()
            result = chardet.detect(raw_data)
            encoding = result["encoding"]

            with codecs.open(file_path, "r", encoding) as in_fh:
                filecontents = in_fh.read()
    else:
        sys.exit(1)

    # Find all occurrences of player names using the regular expression pattern
    m = regex.finditer(filecontents)

    outfile = f"{file_path}.anon"

    # Extract player names
    players = []
    for a in m:
        players = [*players, a.group("PNAME")]

    uniq = set(players)

    # Replace player names
    for i, name in enumerate(uniq):
        filecontents = filecontents.replace(
            name,
            "Hero" if name == hero_name else f"Player{i}",
        )

    # Write anonymized content to output file
    outfile = output_file or f"{file_path}.anon"
    with open(outfile, "w", encoding=encoding) as fsock:
        fsock.write(filecontents)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB Hand History Anonymizer")
    parser.add_argument("file_path", nargs="?", help="Path to the hand history file to anonymize")
    parser.add_argument("hero_name", nargs="?", help='Name of the hero player (will be replaced with "Hero")')
    parser.add_argument(
        "--site",
        type=str,
        choices=[
            "Winamax",
            "PokerStars",
            "Betfair",
            "Bovada",
            "Cake",
            "GGPoker",
            "iPoker",
            "KingsClub",
            "Merge",
            "PacificPoker",
            "PartyPoker",
            "Winning",
        ],
        help="Specify poker site manually (overrides auto-detection)",
    )
    parser.add_argument("--output", "-o", type=str, help="Output file path (default: input_file.anon)")
    parser.add_argument("--list-sites", action="store_true", help="List supported poker sites for anonymization")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be anonymized without creating output file"
    )

    args = parser.parse_args(argv)

    # Handle options that don't require file arguments first
    if args.list_sites:
        print("=== Supported Poker Sites ===")
        sites = [
            "Winamax",
            "Betfair",
            "Bovada",
            "Cake",
            "GGPoker",
            "iPoker",
            "KingsClub",
            "Merge",
            "PacificPoker",
            "PartyPoker",
            "PokerStars",
            "Winning",
        ]
        for site in sites:
            print(f"- {site}")
        return 0

    # Check for required arguments
    if not args.file_path or not args.hero_name:
        parser.print_help()
        return 1

    if args.dry_run:
        print(f"Would anonymize: {args.file_path}")
        print(f"Hero player: {args.hero_name} -> Hero")
        print("Other players would be renamed to: Player0, Player1, Player2, etc.")
        return 0

    # Check if file exists
    if not os.path.exists(args.file_path):
        print(f"Error: File '{args.file_path}' not found")
        return 1

    try:
        print(f"Anonymizing: {args.file_path}")
        print(f"Hero: {args.hero_name}")

        output_file = args.output or f"{args.file_path}.anon"
        anonymize_hand_history(args.file_path, args.hero_name, output_file, args.site)

        print(f"Anonymized file created: {output_file}")
        return 0

    except Exception as e:
        print(f"Error during anonymization: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
