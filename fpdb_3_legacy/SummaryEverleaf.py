#!/usr/bin/env python
from __future__ import annotations

# Copyright (c) 2009-2011 Eric Blade, and the FPDB team.

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

# Ported from Python 2 to Python 3: the original relied on htmllib/formatter
# (both removed from the stdlib). This module now builds on html.parser, with a
# small compatibility shim that keeps the original start_<tag>/end_<tag>
# dispatch and save_bgn()/save_end() text-capture API, so the parsing logic
# below is unchanged.

import urllib.request
from html.parser import HTMLParser


class _CompatHTMLParser(HTMLParser):
    """Shim reproducing the bits of the old htmllib.HTMLParser API in use.

    - start tags dispatch to ``start_<tag>(attrs)`` if defined,
    - end tags dispatch to ``end_<tag>()`` if defined,
    - ``save_bgn()`` / ``save_end()`` capture and return the text between them.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._saving = False
        self._savebuf: list[str] = []

    def save_bgn(self) -> None:
        self._saving = True
        self._savebuf = []

    def save_end(self) -> str:
        self._saving = False
        return "".join(self._savebuf).strip()

    def handle_data(self, data: str) -> None:
        if self._saving:
            self._savebuf.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        handler = getattr(self, "start_" + tag, None)
        if handler is not None:
            handler(attrs)

    def handle_endtag(self, tag: str) -> None:
        handler = getattr(self, "end_" + tag, None)
        if handler is not None:
            handler()


class SummaryParser(_CompatHTMLParser):  # derive new HTML parser
    def get_attr(self, attrs, key):
        for a in attrs:
            if a[0] == key:
                return a[1]
        return None

    def __init__(self):  # class constructor
        super().__init__()
        self.nofill = True
        self.SiteName = None
        self.TourneyId = None
        self.TourneyName = None
        self.nextStartTime = False
        self.TourneyStartTime = None
        self.nextEndTime = False
        self.TourneyEndTime = None
        self.TourneyGameType = None
        self.nextGameType = False
        self.nextStructure = False
        self.TourneyStructure = None
        self.nextBuyIn = False
        self.TourneyBuyIn = None
        self.nextPool = False
        self.TourneyPool = None
        self.nextPlayers = False
        self.TourneysPlayers = None
        self.nextAllowRebuys = False
        self.TourneyRebuys = None
        self.parseResultsA = False
        self.parseResultsB = False
        self.TempResultStore = [0, 0, 0, 0]
        self.TempResultPos = 0
        self.Results = {}

    def start_meta(self, attrs):
        x = self.get_attr(attrs, "name")
        if x == "author":
            self.SiteName = self.get_attr(attrs, "content")

    def start_input(self, attrs):
        x = self.get_attr(attrs, "name")
        if x == "tid":
            self.TourneyId = self.get_attr(attrs, "value")

    def start_h1(self, attrs):
        if self.TourneyName is None:
            self.save_bgn()

    def end_h1(self):
        if self.TourneyName is None:
            self.TourneyName = self.save_end()

    def start_div(self, attrs):
        x = self.get_attr(attrs, "id")
        if x == "result":
            self.parseResultsA = True

    def end_div(self):  # TODO: Can we get attrs in the END tag too? Would be useful to make SURE we're closing the right div ..
        if self.parseResultsA:
            self.parseResultsA = False  # TODO: Should probably just make sure everything is false at this point

    def start_td(self, attrs):
        self.save_bgn()

    def end_td(self):
        x = self.save_end()

        if not self.parseResultsA:
            if not self.nextStartTime and x == "Start:":
                self.nextStartTime = True
            elif self.nextStartTime:
                self.TourneyStartTime = x
                self.nextStartTime = False

            if not self.nextEndTime and x == "Finished:":
                self.nextEndTime = True
            elif self.nextEndTime:
                self.TourneyEndTime = x
                self.nextEndTime = False

            if not self.nextGameType and x == "Game Type:":
                self.nextGameType = True
            elif self.nextGameType:
                self.TourneyGameType = x
                self.nextGameType = False

            if not self.nextStructure and x == "Limit:":
                self.nextStructure = True
            elif self.nextStructure:
                self.TourneyStructure = x
                self.nextStructure = False

            if not self.nextBuyIn and x == "Buy In / Fee:":
                self.nextBuyIn = True
            elif self.nextBuyIn:
                self.TourneyBuyIn = x  # TODO: Further parse the fee from this
                self.nextBuyIn = False

            if not self.nextPool and x == "Prize Money:":
                self.nextPool = True
            elif self.nextPool:
                self.TourneyPool = x
                self.nextPool = False

            if not self.nextPlayers and x == "Player Count:":
                self.nextPlayers = True
            elif self.nextPlayers:
                self.TourneysPlayers = x
                self.nextPlayers = False

            if not self.nextAllowRebuys and x == "Rebuys possible?:":
                self.nextAllowRebuys = True
            elif self.nextAllowRebuys:
                self.TourneyRebuys = x
                self.nextAllowRebuys = False

        else:  # parse results
            if x == "Won Prize":
                self.parseResultsB = True  # ok, NOW we can start parsing the results
            elif self.parseResultsB:
                if x and x[0] == "$":  # first char of the last of each row is the dollar sign, so now we can put it into a sane order
                    self.TempResultPos = 0
                    name = self.TempResultStore[1]
                    place = self.TempResultStore[0]
                    time = self.TempResultStore[2]

                    self.Results[name] = {}
                    self.Results[name]["place"] = place
                    self.Results[name]["winamount"] = x
                    self.Results[name]["outtime"] = time
                else:
                    self.TempResultStore[self.TempResultPos] = x
                    self.TempResultPos += 1


class EverleafSummary:
    def __init__(self):
        if __name__ != "__main__":
            self.main()

    def main(self, id="785646"):
        url = "http://www.poker4ever.com/en.tournaments.tournament-statistics?tid=" + id
        request = urllib.request.Request(url, headers={"User-Agent": "Free Poker Database/0.12+"})
        with urllib.request.urlopen(request) as file:
            data = file.read()
        self.parser = SummaryParser()
        self.parser.feed(data.decode("utf-8", errors="replace"))
        print("site=", self.parser.SiteName, "tourneyname=", self.parser.TourneyName, "tourneyid=", self.parser.TourneyId)
        print("start time=", self.parser.TourneyStartTime, "end time=", self.parser.TourneyEndTime)
        print("structure=", self.parser.TourneyStructure, "game type=", self.parser.TourneyGameType)
        print(
            "buy-in=", self.parser.TourneyBuyIn,
            "rebuys=", self.parser.TourneyRebuys,
            "total players=", self.parser.TourneysPlayers,
            "pool=", self.parser.TourneyPool,
        )
        print("results=", self.parser.Results)


if __name__ == "__main__":
    me = EverleafSummary()
    me.main()
