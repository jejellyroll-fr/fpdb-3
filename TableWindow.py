"""Base class for interacting with poker client windows.

There are currently subclasses for X, OSX, and Windows.

The class queries the poker client window for data of interest, such as
size and location. It also controls the signals to alert the HUD when the
client has been resized, destroyed, etc.
"""
#    Copyright 2008 - 2011, Ray E. Barker

#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################


# import L10n
# _ = L10n.get_translation()

#    Standard Library modules
import re
from time import sleep

#    FreePokerTools modules
import Configuration
from HandHistoryConverter import getTableNoRe, getTableTitleRe
from loggingFpdb import get_logger

c = Configuration.Config()
log = get_logger("table_window")

#    Global used for figuring out the current game being played from the title.
#    The dict key is a tuple of (limit type, category) for the game.
#    The list is the names for those games used by the supported poker sites
#    This is currently only used for mixed games, so it only needs to support those
#    games on PokerStars and Full Tilt.
nlpl_game_names = {  # fpdb name      Stars Name   FTP Name (if different)
    ("nl", "holdem"): ("No Limit Hold'em",),
    ("pl", "holdem"): ("Pot Limit Hold'em",),
    ("pl", "omahahi"): ("Pot Limit Omaha", "Pot Limit Omaha Hi"),
}
limit_game_names = {  # fpdb name      Stars Name   FTP Name
    ("fl", "holdem"): ("Limit Hold'em",),
    ("fl", "omahahilo"): ("Limit Omaha H/L",),
    ("fl", "studhilo"): ("Limit Stud H/L",),
    ("fl", "razz"): ("Limit Razz",),
    ("fl", "studhi"): ("Limit Stud", "Stud Hi"),
    ("fl", "27_3draw"): ("Limit Triple Draw 2-7 Lowball",),
}

#    A window title might have our table name + one of these words/
#    phrases. If it has this word in the title, it is not a table.
bad_words = ("History for table:", "HUD:", "Chat:", "FPDBHUD", "Lobby")

#    Each TableWindow object must have the following attributes correctly populated:
#    tw.name = the table name from the title bar, which must to match the table name
#              from the corresponding hand record in the db.
#    tw.number = This is the system id number for the client table window in the
#                format that the system presents it.  This is Xid in Xwindows and
#                hwnd in Microsoft Windows.
#    tw.title = The full title from the window title bar.
#    tw.width, tw.height = The width and height of the window in pixels.  This is
#            the internal width and height, not including the title bar and
#            window borders.
#    tw.x, tw.y = The x, y (horizontal, vertical) location of the window relative
#            to the top left of the display screen.  This also does not include the
#            title bar and window borders.  To put it another way, this is the
#            screen location of (0, 0) in the working window.
#    tournament = Tournament number for a tournament or None for a cash game.
#    table = Table number for a tournament.
#    gdkhandle =
#    window =
#    parent =
#    game =
#    search_string =


class Table_Window:
    def __init__(
        self,
        config,
        site,
        table_name=None,
        tournament=None,
        table_number=None,
    ) -> None:
        self.config = config
        self.site = site
        self.hud = None  # Will be filled in later
        self.gdkhandle = None
        self.number = None

        # Decode values if they are in bytes
        if isinstance(table_name, bytes):
            log.debug(f"Decoding table_name to UTF-8: {table_name}")
            table_name = table_name.decode("utf-8")
        if isinstance(tournament, bytes):
            log.debug(f"Decoding tournament to UTF-8: {tournament}")
            tournament = tournament.decode("utf-8")
        if isinstance(table_number, bytes):
            log.debug(f"Decoding table_number to UTF-8: {table_number}")
            table_number = table_number.decode("utf-8")

        # Handle tournament and table number
        if tournament is not None and table_number is not None:
            log.debug(f"Tournament: {tournament}")
            self.tournament = int(tournament)
            log.debug(f"Converted tournament: {self.tournament}")
            log.debug(f"Table number type: {type(table_number)}, value: {table_number}")

            # Temporary correction for errors in table_number conversion
            try:
                self.table = int(table_number)
            except ValueError:
                # Try to extract table number from string like "Twister 0.25€, 1091614818"
                import re

                match = re.search(r"(\d+)$", str(table_number))
                if match:
                    self.table = int(match.group(1))
                    log.debug(f"Extracted table number from string: {self.table}")
                else:
                    log.exception(f"Error converting table_number: {table_number}")
                    # Fallback to tournament number if table extraction fails
                    self.table = self.tournament
                    log.warning(f"Using tournament number as table fallback: {self.table}")

            log.debug(f"Converted table number: {self.table}")
            self.name = f"{self.tournament} - {self.table}"

            self.type = "tour"
            table_kwargs = {"tournament": self.tournament, "table_number": self.table}
            self.tableno_re = getTableNoRe(
                self.config,
                self.site,
                tournament=self.tournament,
            )

        # Handle cash game tables
        elif table_name is not None:
            log.debug(f"Cash table name type: {type(table_name)}, value: {table_name}")

            self.name = table_name
            self.type = "cash"
            self.tournament = None
            table_kwargs = {"table_name": table_name}

            log.debug(
                f"Cash table kwargs type: {type(table_kwargs)}, value: {table_kwargs}",
            )

        # Log a warning if neither tournament nor table_name is provided

        else:
            log.warning(
                "Neither tournament nor table_name provided; initialization failed.",
            )
            return

        self.search_string = getTableTitleRe(
            self.config,
            self.site,
            self.type,
            **table_kwargs,
        )
        log.debug(f"search string: {self.search_string}")
        # make a small delay otherwise Xtables.root.get_windows()
        #  returns empty for unknown reasons
        sleep(0.1)

        self.find_table_parameters()
        if not self.number:
            log.error(
                f'Can\'t find table "{table_name}" with search string "{self.search_string}"',
            )

        geo = self.get_geometry()
        if geo is None:
            return
        self.width = geo["width"]
        self.height = geo["height"]
        self.x = geo["x"]

        log.debug(f"X coordinate: {self.x}")
        self.y = geo["y"]
        log.debug(f"Y coordinate: {self.y}")
        self.oldx = self.x  # Attention: Remove these two lines and update Hud.py::update_table_position()
        log.debug(f"Old X coordinate: {self.oldx}")
        self.oldy = self.y
        log.debug(f"Old Y coordinate: {self.oldy}")

        self.game = self.get_game()

    def __str__(self) -> str:
        likely_attrs = (
            "number",
            "title",
            "site",
            "width",
            "height",
            "x",
            "y",
            "tournament",
            "table",
            "gdkhandle",
            "window",
            "parent",
            "key",
            "hud",
            "game",
            "search_string",
            "tableno_re",
        )
        temp = "TableWindow object\n"
        for a in likely_attrs:
            if getattr(self, a, 0):
                temp += f"    {a} = {getattr(self, a)}\n"
        return temp

    ####################################################################
    #    "get" methods. These query the table and return the info to get.
    #    They don't change the data in the table and are generally used
    #    by the "check" methods. Most of the get methods are in the
    #    subclass because they are specific to X, Windows, etc.
    def get_game(self):
        #        title = self.get_window_title()
        #        if title is None:
        #            return False
        title = self.title

        #    check for nl and pl games first, to avoid bad matches
        for game, names in list(nlpl_game_names.items()):
            for name in names:
                if name in title:
                    return game
        for game, names in list(limit_game_names.items()):
            for name in names:
                if name in title:
                    return game
        return False

    def get_table_no(self):
        new_title = self.get_window_title()
        log.debug(f"new table title: {new_title}")
        if new_title is None:
            return False

        try:
            log.debug(f"before searching: {new_title}")
            mo = re.search(self.tableno_re, new_title)
        except AttributeError:  #'Table' object has no attribute 'tableno_re'
            log.debug("'Table' object has no attribute 'tableno_re'")
            return False

        if mo is not None:
            return int(mo.group(1))
        return False

    ####################################################################
    #    check_table() is meant to be called by the hud periodically to
    #    determine if the client has been moved or resized. check_table()
    #    also checks and signals if the client has been closed.
    def check_table(self):
        return self.check_size() or self.check_loc()

    ####################################################################
    #    "check" methods. They use the corresponding get method, update the
    #    table object and return the name of the signal to be emitted or
    #    False if unchanged. These do not signal for destroyed
    #    clients to prevent a race condition.

    #    These might be called by a Window.timeout, so they must not
    #    return False, or the timeout will be cancelled.
    def check_size(self) -> str | bool:
        new_geo = self.get_geometry()
        if new_geo is None:  # window destroyed
            return "client_destroyed"

        if self.width != new_geo["width"] or self.height != new_geo["height"]:  # window resized
            self.oldwidth = self.width
            self.width = new_geo["width"]
            self.oldheight = self.height
            self.height = new_geo["height"]
            return "client_resized"
        return False  # no change

    def check_loc(self) -> str | bool:
        new_geo = self.get_geometry()
        if new_geo is None:  # window destroyed
            return "client_destroyed"

        if self.x != new_geo["x"] or self.y != new_geo["y"]:  # window moved
            self.x = new_geo["x"]
            self.y = new_geo["y"]
            return "client_moved"
        return False  # no change

    def has_table_title_changed(self, hud) -> bool:
        log.debug("before get_table_no()")
        result = self.get_table_no()
        log.debug(f"tb has change nb {result}")
        if result is not False and result != self.table:
            log.debug(f"compare result and self.table {result} {self.table}")
            self.table = result
            if hud is not None:
                log.debug("return True")
                return True
        log.debug("return False")
        return False

    def check_bad_words(self, title) -> bool:
        return any(word in title for word in bad_words)
