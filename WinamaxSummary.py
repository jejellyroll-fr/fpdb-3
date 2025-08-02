"""Winamax tournament summary parser.

Copyright 2008-2011 Carl Gherardi
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

import datetime
import re
from decimal import Decimal
from typing import ClassVar

from bs4 import BeautifulSoup

from HandHistoryConverter import FpdbParseError
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

# Winamax HH Format
log = get_logger("winamax_summary_parser")


class WinamaxSummary(TourneySummary):
    """Winamax tournament summary parser."""

    limits: ClassVar = {"No Limit": "nl", "Pot Limit": "pl", "Limit": "fl", "LIMIT": "fl"}
    games: ClassVar = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Omaha": ("hold", "omahahi"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "Omaha 5": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omahahi"),  # incorrect in file
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "7-Card Stud": ("stud", "studhi"),
        "7-Card Stud Hi/Lo": ("stud", "studhilo"),
        "Razz": ("stud", "razz"),
        "2-7 Triple Draw": ("draw", "27_3draw"),
    }

    substitutions: ClassVar = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
        "LS": r"\$|€|",  # legal currency symbols
    }

    re_identify = re.compile(r"Winamax\sPoker\s\-\sTournament\ssummary")

    re_summary_tourney_info = re.compile(
        r"""\s:\s
                                           ((?P<LIMIT>No\sLimit|Limit|LIMIT|Pot\sLimit)\s)?
                                           (?P<GAME>.+)?
                                           \((?P<TOURNO>[0-9]+)\)(\s-\sLate\s(r|R)egistration)?\s+
                                           (Player\s:\s(?P<PNAME>.*)\s+)?
                                           Buy-In\s:\s(?P<BUYIN>(?P<BIAMT>.+?)\s\+\s(?P<BIRAKE>.+?)(\s\+\s(?P<BIBOUNTY>.+))?|Freeroll|Gratuit|Ticket\suniquement|Free|Ticket)\s+
                                           (Rebuy\scost\s:\s(?P<REBUY>(?P<REBUYAMT>.+)\s\+\s(?P<REBUYRAKE>.+))\s+)?
                                           (Addon\scost\s:\s(?P<ADDON>(?P<ADDONAMT>.+)\s\+\s(?P<ADDONRAKE>.+))\s+)?
                                           (Your\srebuys\s:\s(?P<PREBUYS>\d+)\s+)?
                                           (Your\saddons\s:\s(?P<PADDONS>\d+)\s+)?
                                           Registered\splayers\s:\s(?P<ENTRIES>[0-9]+)\s+
                                           (Total\srebuys\s:\s\d+\s+)?
                                           (Total\saddons\s:\s\d+\s+)?
                                           (Prizepool\s:\s(?P<PRIZEPOOL1>[.0-9{LS}]+)\s+)?
                                           (Mode\s:\s(?P<MODE>.+)?\s+)?
                                           (Type\s:\s(?P<TYPE>.+)?\s+)?
                                           (Speed\s:\s(?P<SPEED>.+)?\s+)?
                                           (Flight\sID\s:\s.+\s+)?
                                           (Levels\s:\s.+\s+)?
                                           (Total\srebuys\s:\s(?P<TREBUYS>\d+)\s+)?
                                           (Total\saddons\s:\s(?P<TADDONS>\d+)\s+)?
                                           (Prizepool\s:\s(?P<PRIZEPOOL2>[.0-9{LS}]+)\s+)?
                                           Tournament\sstarted\s(?P<DATETIME>[0-9]{{4}}\/[0-9]{{2}}\/[0-9]{{2}}\s[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}\sUTC)\s+
                                           (?P<BLAH>You\splayed\s.+)\s+
                                           You\sfinished\sin\s(?P<RANK>[.0-9]+)(st|nd|rd|th)?\splace\s+
                                           (You\swon\s((?P<WINNINGS>[.0-9{LS}]+))?(\s\+\s)?(Ticket\s(?P<TICKET>[.0-9{LS}]+))?(\s\+\s)?(Bounty\s(?P<BOUNTY>[.0-9{LS}]+))?)?
                                        """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_game_type = re.compile(
        """<h1>((?P<LIMIT>No Limit|Pot Limit) (?P<GAME>Hold\'em|Omaha))</h1>""",
    )

    re_tour_no = re.compile(r"ID\=(?P<TOURNO>[0-9]+)")

    re_player = re.compile(
        r"""(?P<RANK>\d+)<\/td><td width="30%">(?P<PNAME>.+?)<\/td><td width="60%">(?P<WINNINGS>.+?)</td>""",
    )

    re_details = re.compile("""<p class="text">(?P<LABEL>.+?) : (?P<VALUE>.+?)</p>""")
    re_prizepool = re.compile("""<div class="title2">.+: (?P<PRIZEPOOL>[0-9,]+)""")

    re_date_time = re.compile(
        r"\[(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)",
    )
    re_ticket = re.compile(
        """ / (?P<TTYPE>Ticket (?P<VALUE>[0-9.]+)&euro;|Tremplin Winamax Poker Tour|Starting Block Winamax Poker Tour|Finale Freeroll Mobile 2012|SNG Freeroll Mobile 2012)""",  # noqa: E501
    )

    codepage: ClassVar = ("utf8", "cp1252")
    hhtype: ClassVar = "summary"

    def __init__(self, *args, **kwargs):
        """Initialize WinamaxSummary with lottery support."""
        super().__init__(*args, **kwargs)
        # Initialize lottery fields with default values
        self.isLottery = False
        self.tourneyMultiplier = 1

    def getSplitRe(self, head: str) -> re.Pattern[str]:
        """Get regex pattern for splitting tournament summaries."""
        re_split_tourneys = re.compile(r"Winamax\sPoker\s-\sTournament\ssummary")
        m = re.search("<!DOCTYPE html PUBLIC", head)
        if m is not None:
            pass
        else:
            pass
        return re_split_tourneys

    def parseSummary(self) -> None:
        """Parse tournament summary text."""
        if self.hhtype == "summary":
            self.parseSummaryFile()
        elif self.hhtype == "html":
            self.parseSummaryHtml()

    def parseSummaryHtml(self) -> None:  # noqa: PLR0912, C901
        """Parse HTML tournament summary."""
        self.currency = "EUR"
        soup = BeautifulSoup(self.summaryText)
        tl = soup.findAll("div", {"class": "left_content"})

        ps = soup.findAll("p", {"class": "text"})
        for p in ps:
            for m in self.re_details.finditer(str(p)):
                mg = m.groupdict()
                # print mg
                if mg["LABEL"] == "Buy-in":
                    mg["VALUE"] = mg["VALUE"].replace("&euro;", "")
                    mg["VALUE"] = mg["VALUE"].replace("+", "")
                    mg["VALUE"] = mg["VALUE"].strip(" $")
                    bi, fee = mg["VALUE"].split(" ")
                    self.buyin = int(100 * Decimal(bi))
                    self.fee = int(100 * Decimal(fee))
                    # print "DEBUG: bi: '%s' fee: '%s" % (self.buyin, self.fee)
                if mg["LABEL"] == "Nombre de joueurs inscrits":
                    self.entries = mg["VALUE"]
                if mg["LABEL"] == "D\xc3\xa9but du tournoi":
                    self.startTime = datetime.datetime.strptime(
                        mg["VALUE"], "%d-%m-%Y %H:%M",
                    ).replace(tzinfo=datetime.timezone.utc)
                if mg["LABEL"] == "Nombre de joueurs max":
                    # Max seats i think
                    pass

        div = soup.findAll("div", {"class": "title2"})
        for m in self.re_prizepool.finditer(str(div)):
            mg = m.groupdict()
            # print mg
            self.prizepool = mg["PRIZEPOOL"].replace(",", ".")

        for m in self.re_game_type.finditer(str(tl[0])):
            mg = m.groupdict()
            # print mg
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
            self.gametype["category"] = self.games[mg["GAME"]][1]
        # TODO(@dev): No gametype
        #       Quitte or Double, Starting Block Winamax Poker Tour
        #       Do not contain enough the gametype.
        # Lookup the tid from the db, if it exists get the gametype info from there, otherwise ParseError
        log.warning("Gametype unknown defaulting to NLHE")
        self.gametype["limitType"] = "nl"
        self.gametype["category"] = "holdem"

        for m in self.re_player.finditer(str(tl[0])):
            winnings = 0
            mg = m.groupdict()
            rank = mg["RANK"]
            name = mg["PNAME"]
            if rank != "...":
                rank = int(mg["RANK"])
                # print "DEUBG: mg: '%s'" % mg
                is_satellite = self.re_ticket.search(mg["WINNINGS"])
                if is_satellite:
                    # Ticket
                    if is_satellite.group("VALUE"):
                        winnings = self.convert_to_decimal(is_satellite.group("VALUE"))
                    else:  # Value not specified
                        rank = 1
                        # TODO(@dev): Do lookup here
                        # Tremplin Winamax Poker Tour
                        # Starting Block Winamax Poker Tour
                    # For stallites, any ticket means 1st
                    if winnings > 0:
                        rank = 1
                else:
                    winnings = self.convert_to_decimal(mg["WINNINGS"])

                winnings = int(100 * Decimal(winnings))
                # print "DEBUG: %s) %s: %s"  %(rank, name, winnings)
                self.addPlayer(rank, name, winnings, self.currency, None, None, None)

        for m in self.re_tour_no.finditer(self.summaryText):
            mg = m.groupdict()
            # print mg
            self.tourNo = mg["TOURNO"]

    def parseSummaryFile(self) -> None:  # noqa: PLR0912, PLR0915, C901
        """Parse file-based tournament summary."""
        m = self.re_summary_tourney_info.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error("parse Summary From File failed: '%s'", tmp)
            raise FpdbParseError

        mg = m.groupdict()
        # print "DEBUG: m.groupdict(): %s" % m.groupdict()

        if "LIMIT" in mg and mg["LIMIT"] is not None:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
            self.gametype["category"] = self.games[mg["GAME"]][1]
        else:
            # TODO(@dev): No gametype
            #       Quitte or Double, Starting Block Winamax Poker Tour
            #       Do not contain enough the gametype.
            # Lookup the tid from the db, if it exists get the gametype info from there, otherwise ParseError
            log.warning("Gametype unknown defaulting to NLHE")
            self.gametype["limitType"] = "nl"
            self.gametype["category"] = "holdem"
            self.tourneyName = mg["GAME"]
        if "ENTRIES" in mg:
            self.entries = mg["ENTRIES"]
        if "PRIZEPOOL1" in mg and mg["PRIZEPOOL1"] is not None:
            self.prizepool = int(100 * self.convert_to_decimal(mg["PRIZEPOOL1"]))
        if "PRIZEPOOL2" in mg and mg["PRIZEPOOL2"] is not None:
            self.prizepool = int(100 * self.convert_to_decimal(mg["PRIZEPOOL2"]))
        if "DATETIME" in mg:
            self.startTime = datetime.datetime.strptime(
                mg["DATETIME"], "%Y/%m/%d %H:%M:%S UTC",
            ).replace(tzinfo=datetime.timezone.utc)

        # TODO(@dev): buyinCurrency and currency not detected
        self.buyinCurrency = "EUR"
        self.currency = "EUR"

        if "BUYIN" in mg:
            # print "DEBUG: BUYIN '%s'" % mg['BUYIN']
            if mg["BUYIN"] in ("Gratuit", "Freeroll", "Ticket uniquement", "Ticket"):
                self.buyin = 0
                self.fee = 0
                self.buyinCurrency = "FREE"
            else:
                if mg["BUYIN"].find("€") != -1:
                    self.buyinCurrency = "EUR"
                elif mg["BUYIN"].find("FPP") != -1 or mg["BUYIN"].find("Free") != -1:
                    self.buyinCurrency = "WIFP"
                else:
                    self.buyinCurrency = "play"

                if mg["BIBOUNTY"] is not None and mg["BIRAKE"] is not None:
                    self.koBounty = int(
                        100 * Decimal(self.convert_to_decimal(mg["BIRAKE"].strip("\r"))),
                    )
                    self.isKO = True
                    mg["BIRAKE"] = mg["BIBOUNTY"].strip("\r")

                rake = mg["BIRAKE"].strip("\r")
                self.buyin = int(100 * self.convert_to_decimal(mg["BIAMT"]))
                self.fee = int(100 * self.convert_to_decimal(rake))

                if self.buyin == 0 and self.fee == 0:
                    self.buyinCurrency = "FREE"

        if "REBUY" in mg and mg["REBUY"] is not None:
            self.isRebuy = True
            rebuyrake = mg["REBUYRAKE"].strip("\r")
            rebuyamt = int(100 * self.convert_to_decimal(mg["REBUYAMT"]))
            rebuyfee = int(100 * self.convert_to_decimal(rebuyrake))
            self.rebuyCost = rebuyamt + rebuyfee
        if "ADDON" in mg and mg["ADDON"] is not None:
            self.isAddOn = True
            addonrake = mg["ADDONRAKE"].strip("\r")
            addonamt = int(100 * self.convert_to_decimal(mg["ADDONAMT"]))
            addonfee = int(100 * self.convert_to_decimal(addonrake))
            self.addOnCost = addonamt + addonfee

        if "TOURNO" in mg:
            self.tourNo = mg["TOURNO"]
        # self.maxseats  =
        sng_threshold = 10
        if int(self.entries) <= sng_threshold:  # TODO(@dev): obv not a great metric
            self.isSng = True
        if "MODE" in mg and mg["MODE"] is not None and "sng" in mg["MODE"]:
            self.isSng = True
        if "SPEED" in mg and mg["SPEED"] is not None:
            if mg["SPEED"] == "turbo":
                self.speed = "Hyper"
            elif mg["SPEED"] == "semiturbo":
                self.speed = "Turbo"

        if "PNAME" in mg and mg["PNAME"] is not None:
            name = mg["PNAME"].strip("\r")
            rank = mg["RANK"]
            if rank != "...":
                rank = int(mg["RANK"])
                winnings = 0
                rebuy_count = None
                add_on_count = None
                ko_count = None

                if "WINNINGS" in mg and mg["WINNINGS"] is not None:
                    if mg["WINNINGS"].find("€") != -1:
                        self.currency = "EUR"
                    elif mg["WINNINGS"].find("FPP") != -1 or mg["WINNINGS"].find("Free") != -1:
                        self.currency = "WIFP"
                    else:
                        self.currency = "play"
                    winnings = int(100 * self.convert_to_decimal(mg["WINNINGS"]))
                if "PREBUYS" in mg and mg["PREBUYS"] is not None:
                    rebuy_count = int(mg["PREBUYS"])
                if "PADDONS" in mg and mg["PADDONS"] is not None:
                    add_on_count = int(mg["PADDONS"])

                if "TICKET" in mg and mg["TICKET"] is not None:
                    winnings += int(100 * self.convert_to_decimal(mg["TICKET"]))

                if "BOUNTY" in mg and mg["BOUNTY"] is not None:
                    ko_count = (
                        100
                        * self.convert_to_decimal(mg["BOUNTY"])
                        / Decimal(self.koBounty)
                    )
                    if winnings == 0:
                        if mg["BOUNTY"].find("€") != -1:
                            self.currency = "EUR"
                        elif mg["BOUNTY"].find("FPP") != -1 or mg["BOUNTY"].find("Free") != -1:
                            self.currency = "WIFP"
                        else:
                            self.currency = "play"

                # Debug output removed for clarity
                self.addPlayer(
                    rank, name, winnings, self.currency, rebuy_count, add_on_count, ko_count,
                )

        # Detect lottery tournaments after parsing
        self._detect_expresso_lottery()

    def convert_to_decimal(self, string: str) -> Decimal:
        """Convert money string to decimal."""
        dec = self.clearMoneyString(string)
        return Decimal(dec)

    def _detect_expresso_lottery(self) -> None:
        """Detect Expresso lottery tournaments and set lottery attributes."""
        log.debug("Detecting Expresso lottery tournament")
        
        # Check if tournament name contains "Expresso"
        tournament_name = getattr(self, 'tourneyName', '')
        if tournament_name and "Expresso" in tournament_name:
            self.isLottery = True
            log.info("Expresso lottery tournament detected: %s", tournament_name)
            
            # Calculate multiplier from prizepool vs buy-in total
            if hasattr(self, 'prizepool') and hasattr(self, 'buyin') and hasattr(self, 'fee'):
                total_buyin = (self.buyin + self.fee) if self.buyin and self.fee else 0
                if total_buyin > 0 and self.prizepool > 0:
                    # Convert to same units (both should be in centimes)
                    multiplier = self.prizepool / total_buyin
                    self.tourneyMultiplier = int(round(multiplier))
                    log.info("Calculated multiplier: prizepool=%s, total_buyin=%s, multiplier=%sx", 
                            self.prizepool, total_buyin, self.tourneyMultiplier)
                else:
                    self.tourneyMultiplier = 1
                    log.debug("Cannot calculate multiplier: prizepool=%s, buyin=%s, fee=%s",
                            getattr(self, 'prizepool', None), 
                            getattr(self, 'buyin', None), 
                            getattr(self, 'fee', None))
            else:
                self.tourneyMultiplier = 1
            
            log.info("Lottery tournament: lottery=%s, multiplier=%s", 
                    self.isLottery, self.tourneyMultiplier)
        else:
            log.debug("Not an Expresso tournament: %s", tournament_name)
