# Copyright 2008-2012 Steffen Schaumburg, Carl Gherardi
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

"""pokerstars-specific summary parsing code."""

import datetime
import quopri
import re
from typing import ClassVar, NoReturn

import PokerStarsStructures
from HandHistoryConverter import FpdbHandPartial, FpdbParseError, HandHistoryConverter
from loggingFpdb import get_logger
from TourneySummary import TourneySummary

try:
    import xlrd
except ImportError:
    xlrd = None

# PPokerstatars HH Format
log = get_logger("parser")


class PokerStarsSummary(TourneySummary):
    """PokerStars tournament summary parser.

    Parses PokerStars tournament summary files including:
    - Standard tournament summaries
    - Email formats with quoted-printable encoding
    - HTML archive formats
    - Excel/XLS formats
    - Special formats (Super Satellite, Run It Once)
    """
    hhtype = "summary"
    limits: ClassVar[dict[str, str]] = {
        "No Limit": "nl",
        "NO LIMIT": "nl",
        "NL": "nl",
        "Pot Limit": "pl",
        "POT LIMIT": "pl",
        "PL": "pl",
        "Limit": "fl",
        "LIMIT": "fl",
        "Pot Limit Pre-Flop, No Limit Post-Flop": "pn",
        "PNL": "pn",
    }
    games: ClassVar[dict[str, tuple[str, str]]] = {  # base, category
        "Hold'em": ("hold", "holdem"),
        "Hold 'Em": ("hold", "holdem"),
        "6+ Hold'em": ("hold", "6_holdem"),
        "Omaha": ("hold", "omahahi"),
        "Omaha Hi/Lo": ("hold", "omahahilo"),
        "Omaha H/L": ("hold", "omahahilo"),
        "5 Card Omaha": ("hold", "5_omahahi"),
        "5 Card Omaha Hi/Lo": ("hold", "5_omaha8"),
        "5 Card Omaha H/L": ("hold", "5_omaha8"),
        "6 Card Omaha": ("hold", "6_omahahi"),
        "6 Card Omaha Hi/Lo": ("hold", "6_omaha8"),
        "Courchevel": ("hold", "cour_hi"),
        "Courchevel Hi/Lo": ("hold", "cour_hilo"),
        "Courchevel H/L": ("hold", "cour_hilo"),
        "Razz": ("stud", "razz"),
        "RAZZ": ("stud", "razz"),
        "7 Card Stud": ("stud", "studhi"),
        "7 Card Stud Hi/Lo": ("stud", "studhilo"),
        "7 Card Stud H/L": ("stud", "studhilo"),
        "Badugi": ("draw", "badugi"),
        "Triple Draw 2-7 Lowball": ("draw", "27_3draw"),
        "Single Draw 2-7 Lowball": ("draw", "27_1draw"),
        "Triple Draw 2-7": ("draw", "27_3draw"),
        "Single Draw 2-7": ("draw", "27_1draw"),
        "5 Card Draw": ("draw", "fivedraw"),
        "HORSE": ("mixed", "horse"),
        "HOSE": ("mixed", "hose"),
        "Horse": ("mixed", "horse"),
        "Hose": ("mixed", "hose"),
        "Triple Stud": ("mixed", "3stud"),
        "8-Game": ("mixed", "8game"),
        "Mixed PLH/PLO": ("mixed", "plh_plo"),
        "Mixed NLH/PLO": ("mixed", "nlh_plo"),
        "Mixed NLH/NLO": ("mixed", "nlh_nlo"),
        "Mixed Omaha H/L": ("mixed", "plo_lo"),
        "Mixed Hold'em": ("mixed", "mholdem"),
        "PLH/PLO Mixed": ("mixed", "plh_plo"),
        "NLH/PLO Mixed": ("mixed", "nlh_plo"),
        "NLH/NLO Mixed": ("mixed", "nlh_nlo"),
        "Omaha H/L Mixed": ("mixed", "plo_lo"),
        "Hold'em Mixed": ("mixed", "mholdem"),
        "Mixed Omaha": ("mixed", "momaha"),
    }

    substitutions: ClassVar[dict[str, str]] = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",  # legal ISO currency codes
        "LS": "\\$|€|£|₹|¥|Rs\\.|Â£|â\u201a¬|â\u201a¹|Â€",  # legal currency symbols including corrupted variants
    }

    re_identify = re.compile(
        r"((?P<SITE>PokerStars|Full\sTilt|Run\sIt\sOnce\sPoker)\sTournament\s\#\d+|<title>TOURNEYS:)",
    )

    re_tour_no = re.compile(r"\#(?P<TOURNO>[0-9]+),")
    re_header = re.compile(r"History\sRequest\s\-\s")
    re_email_header = re.compile(r"Delivered\-To\:\s")

    re_tourney_info = re.compile(
        """
                        \\#(?P<TOURNO>[0-9]+),\\s
                        (?P<DESC1>.+?\\sSNG\\s)?
                        ((?P<LIMIT>No\\sLimit|NO\\sLIMIT|Limit|LIMIT|Pot\\sLimit|POT\\sLIMIT|Pot\\sLimit\\sPre\\-Flop,\\sNo\\sLimit\\sPost\\-Flop)\\s)?
                        (?P<SPLIT>Split)?\\s?
                        (?P<GAME>Hold\'em|6\\+\\sHold\'em|Hold\\s\'Em|Razz|RAZZ|7\\sCard\\sStud|7\\sCard\\sStud\\sHi/Lo|Omaha|Omaha\\sHi/Lo|Badugi|Triple\\sDraw\\s2\\-7\\sLowball|Single\\sDraw\\s2\\-7\\sLowball|5\\sCard\\sDraw|(5|6)\\sCard\\sOmaha(\\sHi/Lo)?|Courchevel(\\sHi/Lo)?|HORSE|8\\-Game|HOSE|Mixed\\sOmaha\\sH/L|Mixed\\sHold\'em|Mixed\\sPLH/PLO|Mixed\\sNLH/PLO||Mixed\\sOmaha|Triple\\sStud).*?
                        (Buy-In:\\s(?P<CURRENCY>[{LS}]*)(?P<BUYIN>[,.0-9]+)(\\s(?P<CURRENCY1>(FPP|SC)))?(\\/[{LS}]*(?P<FEE>[,.0-9]+))?(\\/[{LS}]*(?P<BOUNTY>[,.0-9]+))?(?P<CUR>\\s({LEGAL_ISO}))?\\s+)?
                        (?P<ENTRIES>[0-9]+)\\splayers\\s+
                        ([{LS}]?(?P<ADDED>[,.\\d]+)(\\s({LEGAL_ISO}))?\\sadded\\sto\\sthe\\sprize\\spool\\sby\\s(PokerStars|Full\\sTilt)(\\.com)?\\s+)?
                        (Total\\sPrize\\sPool:\\s[{LS}]?(?P<PRIZEPOOL>[,.0-9]+|Sunday\\sMillion\\s(ticket|biļete))(\\s({LEGAL_ISO}))?\\s+)?
                        (?P<SATELLITE>Target\\sTournament\\s\\#(?P<TARGTOURNO>[0-9]+)\\s+
                         (Buy-In:\\s(?P<TARGCURRENCY>[{LS}]?)(?P<TARGBUYIN>[,.0-9]+)(\\/[{LS}]?(?P<TARGFEE>[,.0-9]+))?(\\/[{LS}]?(?P<TARGBOUNTY>[,.0-9]+))?(?P<TARGCUR>\\s({LEGAL_ISO}))?\\s+)?)?
                        ([0-9]+\\stickets?\\sto\\sthe\\starget\\stournament\\s+)?
                        Tournament\\sstarted\\s+(-\\s)?
                        (?P<DATETIME>.*$)
                        """.format(**substitutions),
        re.VERBOSE | re.MULTILINE | re.DOTALL,
    )
    # You made 5 rebuys and 1 addons for a total of USD 3,180.00.
    re_rebuy_add_on = re.compile(
        r"""
                        You\smade\s(?P<REBUYCOUNT>\d+)\srebuys\sand\s(?P<ADDONCOUNT>\d+)\saddons\sfor\sa\stotal\sof\s({LEGAL_ISO})\s(?P<REBUYADDON>[,.0-9]+)
                               """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )
    # You collected 5 bounties for a total of USD 875.00.
    re_ko_bounties = re.compile(
        r"""
                        You\scollected\s(?P<KOCOUNT>\d+)\sbounties\sfor\sa\stotal\sof\s({LEGAL_ISO})\s(?P<KOBOUNTY>[,.0-9]+)
                               """.format(**substitutions),
        re.VERBOSE | re.MULTILINE,
    )

    re_html_tourney_info = re.compile(
        r'<td align="right">(?P<DATETIME>.*)</td>'
        r'<td align="center">(?P<TOURNO>[0-9]+)</td>'
        r"(<td>(?P<TOURNAME>.*)</td>)?"
        r'<td align="right">'
        r"(?P<LIMIT>[ a-zA-Z\-]+)\s"
        r"(?P<SPLIT>Split)?\s?"
        r"(?P<GAME>Hold\'em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sH/L|Omaha|Omaha\sH/L|Badugi|Triple\sDraw\s2\-7(\sLowball)?|Single\sDraw\s2\-7(\sLowball)?|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sH/L)?|Courchevel(\sH/L)?|HORSE|Horse|8\-Game|HOSE|Hose|Omaha\sH/L\sMixed|Hold\'em\sMixed|PLH/PLO\sMixed|NLH/PLO\sMixed|Triple\sStud|NLH/NLO\sMixed|Mixed\sNLH/NLO|Mixed\sOmaha\sH/L|Mixed\sHold\'em|Mixed\sPLH/PLO|Mixed\sNLH/PLO)</td>"
        r"<td.*?>(?P<CURRENCY>({LEGAL_ISO})?)(&nbsp;)?</td>"
        r"<td.*?>(?P<BUYIN>([,.0-9 ]+|Freeroll))(?P<FPPBUYIN>(\s|&nbsp;)(FPP|SC|StarsCoin))?</td>"
        r"<td.*?>(?P<REBUYADDON>[,.0-9 ]+)</td>"
        r"<td.*?>(?P<FEE>[,.0-9 ]+)</td>"
        r'<td align="?right"?>(?P<RANK>[,.0-9]+)</td>'
        r'<td align="right">(?P<ENTRIES>[,.0-9]+)</td>'
        r"(<td.*?>[,.0-9]+</td>)?"
        r"<td.*?>(?P<WINNINGS>[,.0-9]+)(?P<FPPWINNINGS>\s\+\s[,.0-9]+(\s|&nbsp;)(FPP|SC|StarsCoin))?</td>"
        r"<td.*?>(?P<KOS>[,.0-9]+)</td>"
        r"<td.*?>((?P<TARGET>[,.0-9]+)|(&nbsp;))</td>"
        r"<td.*?>((?P<WONTICKET>\*\\\/\*)|(&nbsp;))</td>".format(**substitutions),
        re.IGNORECASE,
    )

    re_xls_tourney_info: ClassVar[dict[str, re.Pattern[str]]] = {}
    re_xls_tourney_info["Date/Time"] = re.compile(r"(?P<DATETIME>.*)")
    re_xls_tourney_info["Tourney"] = re.compile(r"(?P<TOURNO>[0-9]+)")
    re_xls_tourney_info["Name"] = re.compile(r"(?P<TOURNAME>.*)")
    re_xls_tourney_info["Game"] = re.compile(
        r"(?P<LIMIT>[ a-zA-Z\-]+)\s"
        r"(?P<SPLIT>Split)?\s?"
        r"(?P<GAME>Hold\'em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sH/L|Omaha|Omaha\sH/L|Badugi|Triple\sDraw\s2\-7(\sLowball)?|Single\sDraw\s2\-7(\sLowball)?|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sH/L)?|Courchevel(\sH/L)?|HORSE|Horse|8\-Game|HOSE|Hose|Omaha\sH/L\sMixed|Hold\'em\sMixed|PLH/PLO\sMixed|NLH/PLO\sMixed|Triple\sStud|NLH/NLO\sMixed|Mixed\sNLH/NLO|Mixed\sOmaha\sH/L|Mixed\sHold\'em|Mixed\sPLH/PLO|Mixed\sNLH/PLO)",
    )
    re_xls_tourney_info["Currency"] = re.compile(
        r"(?P<CURRENCY>({LEGAL_ISO})?)".format(**substitutions),
    )
    re_xls_tourney_info["Buy-In"] = re.compile(
        r"(?P<BUYIN>([,.0-9]+|Freeroll))(?P<FPPBUYIN>\s(FPP|SC|StarsCoin))?",
    )
    re_xls_tourney_info["ReBuys"] = re.compile(r"(?P<REBUYADDON>[,.0-9]+)")
    re_xls_tourney_info["Rake"] = re.compile(r"(?P<FEE>[,.0-9]+)")
    re_xls_tourney_info["Place"] = re.compile(r"(?P<RANK>[,.0-9]+)")
    re_xls_tourney_info["Entries"] = re.compile(r"(?P<ENTRIES>[,.0-9]+)")
    re_xls_tourney_info["Prize"] = re.compile(
        r"(?P<WINNINGS>[,.0-9]+)(?P<FPPWINNINGS>\s\+\s[,.0-9]+\s(FPP|SC|StarsCoin))?",
    )
    re_xls_tourney_info["Bounty Awarded"] = re.compile(r"(?P<KOS>[,.0-9]+)")
    re_xls_tourney_info["Target ID"] = re.compile(r"(?P<TARGET>[0-9]+)?")
    re_xls_tourney_info["Qualified"] = re.compile(r"(?P<WONTICKET>\*\\\/\*)?")

    re_player_stars = re.compile(
        r"""(?P<RANK>[,.0-9]+):\s(?P<NAME>.+?)(\s\[(?P<ENTRYID>\d+)\])?\s\(.+?\),(\s)?((?P<CUR>\[{LS}]?)(?P<WINNINGS>[,.0-9]+)(\s(?P<CUR1>(FPP|SC)))?)?(?P<STILLPLAYING>still\splaying)?((?P<TICKET>Tournament\sTicket)\s\(WSOP\sStep\s(?P<LEVEL>\d)\))?(?P<QUALIFIED>\s\(qualified\sfor\sthe\starget\stournament\)|Sunday\sMillion\s(ticket|biļete))?(\s+)?""".format(
            **substitutions,
        ),
    )
    re_player_rio = re.compile(
        r"""(?P<RANK>[,.0-9]+):\s(?P<NAME>[^,]+?)(,\s(?P<CUR>\[{LS}])(?P<WINNINGS>[,.0-9]+))?(\s+)?$""".format(
            **substitutions,
        ),
        re.MULTILINE,
    )
    re_html_player1 = re.compile(
        r"<h2>All\s+(?P<SNG>(Regular|Sit & Go))\s?Tournaments\splayed\sby\s'(<b>)?(?P<NAME>.+?)':?</h2>",
        re.IGNORECASE,
    )
    re_html_player2 = re.compile(
        r"<title>TOURNEYS:\s&lt;(?P<NAME>.+?)&gt;</title>",
        re.IGNORECASE,
    )
    re_xls_player = re.compile(
        r"All\s(?P<SNG>(Regular|(Heads\sup\s)?Sit\s&\sGo))\sTournaments\splayed\sby\s\'(?P<NAME>.+?)\'",
    )

    re_date_time = re.compile(
        r"""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_html_date_time = re.compile(
        r"""(?P<M>[0-9]+)\/(?P<D>[0-9]+)\/(?P<Y>[0-9]{4})[\- ]+
        (?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) (?P<AMPM>(AM|PM))""",
        re.MULTILINE,
    )
    re_html_tourney_extra_info = re.compile(
        r"\[(Deep\s)?((?P<MAX>\d+)-Max,\s?)?((\dx\-)?(?P<SPEED>Turbo|Hyper\-Turbo))?(, )?(?P<REBUYADDON1>\dR\dA)?",
    )
    re_xls_date_time = re.compile("^[.0-9]+$")
    re_rank = re.compile(
        r"^You\sfinished\sin\s(?P<RANK>[0-9]+)(st|nd|rd|th)\splace\.",
        re.MULTILINE,
    )

    codepage: ClassVar[list[str]] = ["cp1252", "utf8", "latin1", "iso-8859-1"]

    # Constants for tournament structure lookup
    MAX_9_PLAYER_ENTRIES = 45
    MAX_6_PLAYER_ENTRIES = 30
    MIN_LARGE_TOURNAMENT = 6
    MAX_SMALL_TOURNAMENT = 9
    DOUBLE_OR_NOTHING_ENTRIES = 10

    def getSplitRe(self, head: str) -> re.Pattern[str]:
        """Get regex pattern for splitting multiple tournament summaries."""
        re_split_tourneys = re.compile(
            r"(?:PokerStars|Full\sTilt|Run\sIt\sOnce\sPoker) Tournament ",
        )
        re_html_split_tourneys = re.compile(r'tr id="row_\d+')
        m = re.search("<title>TOURNEYS:", head)
        if m is not None:
            self.hhtype = "html"
            return re_html_split_tourneys
        self.hhtype = "summary"
        return re_split_tourneys

    def _cleanEmailFormat(self, text: str) -> str:
        """Clean email format and quoted-printable encoding from summary text."""
        if not text:
            return text

        # Check if this looks like an email format
        if "Content-Transfer-Encoding: quoted-printable" in text or "Delivered-To:" in text:
            log.info("Found email format, extracting tournament summaries...")

            # Decode quoted-printable if present (do this first)
            if "=20" in text or "=" in text:
                try:
                    # Decode quoted-printable encoding
                    decoded_bytes = quopri.decodestring(text.encode("ascii"))
                    text = decoded_bytes.decode("windows-1252", errors="replace")
                    log.info("Successfully decoded quoted-printable content")
                except (UnicodeDecodeError, ValueError) as e:
                    log.warning("Failed to decode quoted-printable: %s", e)
                    # Continue with original content if decoding fails

            # Find the start of actual tournament content after email headers
            lines = text.split("\n")
            content_start = 0

            # Skip email headers until we find tournament content
            for i, line in enumerate(lines):
                if "PokerStars Tournament #" in line:
                    content_start = i
                    break

            if content_start > 0:
                # Extract just the tournament content
                tournament_content = "\n".join(lines[content_start:])

                # Check if we have multiple tournaments in the email
                tournament_matches = list(re.finditer(r"PokerStars Tournament #\d+", tournament_content))
                if len(tournament_matches) > 1:
                    log.info("Found %d tournaments in email", len(tournament_matches))
                    # For now, just return the first tournament
                    # This allows the splitting logic to work properly
                    first_tournament_start = tournament_matches[0].start()
                    if len(tournament_matches) > 1:
                        second_tournament_start = tournament_matches[1].start()
                        first_tournament = tournament_content[first_tournament_start:second_tournament_start]
                    else:
                        first_tournament = tournament_content[first_tournament_start:]

                    # Clean up any remaining encoded characters
                    return first_tournament.replace("=\n", "").strip()

                # Clean up any remaining encoded characters
                return tournament_content.replace("=\n", "").strip()

        return text

    def parseSummary(self) -> None:
        """Parse tournament summary based on detected format type."""
        # Clean email format if present
        self.summaryText = self._cleanEmailFormat(self.summaryText)
        if self.hhtype == "summary":
            self.parseSummaryFile()
        elif self.hhtype == "html":
            self.parseSummaryHtml()
        elif self.hhtype == "xls":
            self.parseSummaryXLS()
        elif self.hhtype == "hh":
            self.parseSummaryFromHH()
        else:
            msg = "parseSummary FAIL"
            raise FpdbParseError(msg)

    def parseSummaryFromHH(self) -> NoReturn:
        """Parse summary from hand history (not supported)."""
        msg = "PokerStarsSummary.parseSummaryHtml: This file format is not yet supported"
        raise FpdbParseError(
            (msg),
        )
        # self.entries   = Unavailable from HH
        # self.prizepool = Unavailable from HH
        # self.startTime = Unreliable from HH (late reg)

    def parseSummaryXLS(self) -> None:
        """Parse tournament summary from Excel/XLS format."""
        info = self.summaryText[0]
        m = self.re_xls_player.search(info["header"])
        if m is None:
            tmp1 = info["header"]
            tmp2 = str(info)[0:200]
            log.error("Summary XLS not found: '%s' '%s'", tmp1, tmp2)
            raise FpdbParseError
        info.update(m.groupdict())
        mg = {}
        for k, j in info.iteritems():
            if self.re_xls_tourney_info.get(k) is not None:
                m1 = self.re_xls_tourney_info[k].search(j)
                if m1:
                    mg.update(m1.groupdict())
                elif k == "Game":
                    log.error("Summary XLS Game '%s' not found", j)
                    raise FpdbParseError
        info.update(mg)
        self.parseSummaryArchive(info)

    def parseSummaryHtml(self) -> None:
        """Parse tournament summary from HTML archive format."""
        info = {}
        m1 = self.re_html_player1.search(self.header)
        if m1 is None:
            m1 = self.re_html_player2.search(self.header)
        m2 = self.re_html_tourney_info.search(self.summaryText)
        if m1 is None or m2 is None:
            if self.re_html_player1.search(
                self.summaryText,
            ) or self.re_html_player2.search(self.summaryText):
                raise FpdbHandPartial
            tmp1 = self.header[0:200] if m1 is None else "NA"
            tmp2 = self.summaryText if m2 is None else "NA"
            log.error("Summary HTML not found: '%s' '%s'", tmp1, tmp2)
            raise FpdbParseError
        info.update(m1.groupdict())
        info.update(m2.groupdict())
        self.parseSummaryArchive(info)

    def parseSummaryArchive(self, info: dict) -> None:  # noqa: C901, PLR0912, PLR0915
        """Parse tournament information from archive data."""
        if "SNG" in info and "Sit & Go" in info["SNG"]:
            self.isSng = True

        if "TOURNAME" in info and info["TOURNAME"] is not None:
            self.tourneyName = re.sub("</?(b|font).*?>", "", info["TOURNAME"])
            m3 = self.re_html_tourney_extra_info.search(self.tourneyName)
            if m3 is not None:
                info.update(m3.groupdict())

        if "TOURNO" in info:
            self.tourNo = info["TOURNO"]
        if "LIMIT" in info and info["LIMIT"] is not None:
            self.gametype["limitType"] = self.limits[info["LIMIT"]]
        if "GAME" in info:
            self.gametype["category"] = self.games[info["GAME"]][1]
        if "SPLIT" in info and info["SPLIT"] == "Split":
            self.isSplit = True
        if info["BUYIN"] is not None:
            if info["BUYIN"] == "Freeroll":
                self.buyin = 0
            else:
                self.buyin = int(
                    100 * float(self.clearMoneyString(info["BUYIN"].replace(" ", ""))),
                )
        if info["FEE"] is not None:
            self.fee = int(
                100 * float(self.clearMoneyString(info["FEE"].replace(" ", ""))),
            )
        if "REBUYADDON" in info and float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))) > 0:
            self.isRebuy = True
            self.isAddOn = True
            rebuy_add_on_amt = int(
                100 * float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))),
            )
            if self.buyin != 0:
                rebuys = int(rebuy_add_on_amt / self.buyin)
                if rebuys != 0:
                    self.fee = self.fee / (rebuys + 1)
            self.rebuyCost = self.buyin + self.fee
            self.addOnCost = self.buyin + self.fee
        if "REBUYADDON1" in info and info["REBUYADDON1"] is not None:
            self.isRebuy = True
            self.isAddOn = True
            self.rebuyCost = self.buyin + self.fee
            self.addOnCost = self.buyin + self.fee
        if "ENTRIES" in info:
            self.entries = int(self.clearMoneyString(info["ENTRIES"]))
        if "MAX" in info and info["MAX"] is not None:
            self.maxseats = int(info["MAX"])
        if not self.isSng and "SPEED" in info and info["SPEED"] is not None:
            if info["SPEED"] == "Turbo":
                self.speed = "Turbo"
            elif info["SPEED"] == "Hyper-Turbo":
                self.speed = "Hyper"
        if "TARGET" in info and info["TARGET"] is not None:
            self.isSatellite = True
            if "WONTICKET" in info and info["WONTICKET"] is not None:
                self.comment = info["TARGET"]

        if "DATETIME" in info:
            m4 = self.re_html_date_time.finditer(info["DATETIME"])
        datetime_str = None  # default used if time not found
        for a in m4:
            datetime_str = "{}/{}/{} {}:{}:{} {}".format(
                a.group("Y"),
                a.group("M"),
                a.group("D"),
                a.group("H"),
                a.group("MIN"),
                a.group("S"),
                a.group("AMPM"),
            )
            self.endTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetime_str,
                "%Y/%m/%d %I:%M:%S %p",
            )  # also timezone at end, e.g. " ET"
            self.endTime = HandHistoryConverter.changeTimezone(
                self.endTime,
                "ET",
                "UTC",
            )
        if datetime_str is None:
            if xlrd and self.re_xls_date_time.match(info["DATETIME"]):
                date_tup = xlrd.xldate_as_tuple(float(info["DATETIME"]), 0)
                datetime_str = "%d/%d/%d %d:%d:%d" % (
                    date_tup[0],
                    date_tup[1],
                    date_tup[2],
                    date_tup[3],
                    date_tup[4],
                    date_tup[5],
                )
            else:
                datetime_str = "2000/01/01 12:00:00"
            self.endTime = datetime.datetime.strptime(  # noqa: DTZ007
                datetime_str,
                "%Y/%m/%d %H:%M:%S",
            )  # also timezone at end, e.g. " ET"
            self.endTime = HandHistoryConverter.changeTimezone(
                self.endTime,
                "ET",
                "UTC",
            )

        if "CURRENCY" in info and info["CURRENCY"] is not None:
            self.currency = info["CURRENCY"]
        if info["BUYIN"] == "Freeroll":
            self.buyinCurrency = "FREE"
            self.currency = "USD"
        elif info["FPPBUYIN"] is not None:
            self.buyinCurrency = "PSFP"
        elif self.currency is not None:
            self.buyinCurrency = self.currency
        else:
            self.buyinCurrency = "play"
            self.currency = "play"

        if self.buyinCurrency not in ("FREE", "PSFP"):
            self.prizepool = int(float(self.entries)) * self.buyin

        if self.isSng:
            self.lookupStructures(self.endTime)

        if info.get("NAME") is not None and info.get("RANK") is not None:
            name = info["NAME"]
            rank = int(self.clearMoneyString(info["RANK"]))
            winnings = 0
            rebuy_count = None
            add_on_count = None
            ko_count = None
            entry_id = 1

            if "WINNINGS" in info and info["WINNINGS"] is not None:
                winnings = int(100 * float(self.clearMoneyString(info["WINNINGS"])))

            if "REBUYADDON" in info and float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))) > 0:
                rebuy_add_on_amt = int(
                    100 * float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))),
                )
                rebuy_count = rebuy_add_on_amt / self.buyin

            # KOs should be exclusively handled in the PokerStars hand history files
            if "KOS" in info and info["KOS"] is not None and info["KOS"] != "0.00":
                self.isKO = True

            re_html_entries = re.compile(
                rf'<td align="center">{self.tourNo}</td>.+?<td align="?right"?>(?P<RANK>[,.0-9]+)</td>',
                re.IGNORECASE,
            )
            m = re_html_entries.finditer(self.header)
            entries = [int(self.clearMoneyString(a.group("RANK"))) for a in m]
            entries.sort(reverse=True)

            if len(entries) > 1:
                entry_id = entries.index(rank) + 1
                self.isReEntry = True

            self.addPlayer(
                rank,
                name,
                winnings,
                self.currency,
                rebuy_count,
                add_on_count,
                ko_count,
                entry_id,
            )

    def _tryFallbackRegex(self) -> re.Match[str] | None:
        """Try alternative regex patterns for special tournament formats."""
        # Pattern 1: Super Satellite format (GBP example)
        # #661361197, No Limit Hold'em
        # Super Satellite
        # Buy-In: Â£75.00/Â£7.00 GBP
        satellite_pattern = re.compile(
            r"""
            \#(?P<TOURNO>[0-9]+),\s
            (?P<DESC1>)  # Empty group for compatibility
            (?P<LIMIT>No\sLimit|Limit|Pot\sLimit)\s
            (?P<GAME>Hold'em|Omaha|Razz|7\sCard\sStud|Badugi).*?
            Super\sSatellite.*?
            Buy-In:\s(?P<CURRENCY>[^0-9]*)(?P<BUYIN>[,.0-9]+)/?([^0-9]*(?P<FEE>[,.0-9]+))?\s(?P<CUR>GBP|USD|EUR|CAD|INR).*?
            (?P<ENTRIES>[0-9]+)\splayers.*?
            Total\sPrize\sPool:.*?
            (?P<SATELLITE>Target\sTournament\s\#(?P<TARGTOURNO>[0-9]+).*?)?
            Tournament\sstarted\s.*?(?P<DATETIME>.*?)$
            """,
            re.VERBOSE | re.MULTILINE | re.DOTALL,
        )

        # Pattern 2: Run It Once format
        # Run It Once Poker Tournament #158168, Cubed SNG No Limit Hold 'Em
        rio_pattern = re.compile(
            r"""
            Run\sIt\sOnce\sPoker\sTournament\s\#(?P<TOURNO>[0-9]+),\s
            (?P<DESC1>.*?)\s
            (?P<LIMIT>No\sLimit|Limit|Pot\sLimit)\s
            (?P<GAME>Hold\s'Em|Hold'em|Omaha|Razz).*?
            Buy-In:\s(?P<CURRENCY>[^0-9]*)(?P<BUYIN>[,.0-9]+).*?
            (?P<ENTRIES>[0-9]+)\splayers.*?
            Tournament\sstarted\s.*?(?P<DATETIME>.*?)$
            """,
            re.VERBOSE | re.MULTILINE | re.DOTALL,
        )

        # Pattern 3: Simple format with corrupted currency
        # #354025449, No Limit Hold'em
        # Buy-In: €9.04/€0.96 EUR
        simple_pattern = re.compile(
            r"""
            \#(?P<TOURNO>[0-9]+),\s
            (?P<DESC1>)  # Empty group for compatibility
            (?P<LIMIT>No\sLimit|Limit|Pot\sLimit)\s
            (?P<GAME>Hold'em|Omaha|Razz|7\sCard\sStud|Badugi).*?
            Buy-In:\s(?P<CURRENCY>.{0,5})(?P<BUYIN>[,.0-9]+)/?(.{0,5}(?P<FEE>[,.0-9]+))?\s(?P<CUR>GBP|USD|EUR|CAD|INR).*?
            (?P<ENTRIES>[0-9]+)\splayers.*?
            Tournament\sstarted\s.*?(?P<DATETIME>.*?)$
            """,
            re.VERBOSE | re.MULTILINE | re.DOTALL,
        )

        # Pattern 4: Email format without currency symbols
        # #2892717422, No Limit Hold'em
        # Buy-In: 17000/3000
        email_pattern = re.compile(
            r"""
            \#(?P<TOURNO>[0-9]+),\s
            (?P<DESC1>)  # Empty group for compatibility
            (?P<LIMIT>No\sLimit|Limit|Pot\sLimit)\s
            (?P<GAME>Hold'em|Omaha|Razz|7\sCard\sStud|Badugi).*?
            Buy-In:\s(?P<CURRENCY>)(?P<BUYIN>[,.0-9]+)/?(?P<FEE>[,.0-9]+)?.*?
            (?P<ENTRIES>[0-9]+)\splayers.*?
            Tournament\sstarted\s.*?(?P<DATETIME>.*?)$
            """,
            re.VERBOSE | re.MULTILINE | re.DOTALL,
        )

        # Try each pattern
        for pattern_name, pattern in [
            ("satellite", satellite_pattern),
            ("rio", rio_pattern),
            ("simple", simple_pattern),
            ("email", email_pattern),
        ]:
            m = pattern.search(self.summaryText)
            if m:
                log.info("Matched using %s fallback pattern", pattern_name)
                return m

        return None

    def parseSummaryFile(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Parse tournament summary from standard text format."""
        m = self.re_tourney_info.search(self.summaryText)
        if m is None:
            if self.re_header.match(self.summaryText):
                error_msg = "Tournament history request header found"
                raise FpdbHandPartial(error_msg)
            if self.re_email_header.match(self.summaryText):
                error_msg = "Email header found"
                raise FpdbHandPartial(error_msg)

            # Check if this contains multiple summaries (email format)
            tournament_count = len(re.findall(r"PokerStars Tournament #\d+", self.summaryText))
            if tournament_count > 1:
                log.warning("Found %d tournaments in text, this should be split", tournament_count)
                error_msg = f"Multiple tournaments found ({tournament_count})"
                raise FpdbHandPartial(error_msg)

            # Try fallback regex patterns for special formats
            m = self._tryFallbackRegex()
            if m is not None:
                log.info("Matched using fallback regex")
            else:
                # Provide better error message
                preview = self.summaryText[:200] if self.summaryText else "Empty text"
                log.error("Summary File failed to match TourneyInfo regex. Preview: '%s'", preview)
                error_msg = f"Could not parse tournament info from summary text. Preview: {preview}"
                raise FpdbParseError(error_msg)
        mg = m.groupdict()
        if "DATETIME" in mg:
            m1 = self.re_date_time.finditer(mg["DATETIME"])
        datetime_str = "2000/01/01 00:00:00"  # default used if time not found
        for a in m1:
            datetime_str = "{}/{}/{} {}:{}:{}".format(
                a.group("Y"),
                a.group("M"),
                a.group("D"),
                a.group("H"),
                a.group("MIN"),
                a.group("S"),
            )

        self.startTime = datetime.datetime.strptime(  # noqa: DTZ007
            datetime_str,
            "%Y/%m/%d %H:%M:%S",
        )  # also timezone at end, e.g. " ET"
        self.startTime = HandHistoryConverter.changeTimezone(
            self.startTime,
            "ET",
            "UTC",
        )

        if "DESC1" in mg and mg["DESC1"] is not None and mg["DESC1"] != "":
            self.siteName = "Run It Once Poker"
            self.siteId = 26
            re_player = self.re_player_rio
        else:
            re_player = self.re_player_stars

        if "TOURNO" in mg:
            self.tourNo = mg["TOURNO"]
        if "LIMIT" in mg and mg["LIMIT"] is not None:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
        else:
            self.gametype["limitType"] = "fl"
        if "GAME" in mg and mg["GAME"] and mg["GAME"] in self.games:
            self.gametype["category"] = self.games[mg["GAME"]][1]
        if "SPLIT" in mg and mg["SPLIT"] == "Split":
            self.isSplit = True
        if "BOUNTY" in mg and mg["BOUNTY"] is not None and "FEE" in mg and mg["FEE"] is not None:
            self.koBounty = int(100 * float(self.clearMoneyString(mg["FEE"])))
            self.isKO = True
            mg["FEE"] = mg["BOUNTY"]
        if "BUYIN" in mg and mg["BUYIN"] is not None:
            self.buyin = int(100 * float(self.clearMoneyString(mg["BUYIN"]))) + self.koBounty
        if "FEE" in mg and mg["FEE"] is not None:
            self.fee = int(100 * float(self.clearMoneyString(mg["FEE"])))

        m2 = self.re_rebuy_add_on.search(self.summaryText)
        if m2 and m2.group("REBUYCOUNT") is not None:
            self.isRebuy = True
            self.isAddOn = True
            # You made 5 rebuys and 1 addons for a total of USD 3,180.00.
            rebuy_count_hero = int(m2.group("REBUYCOUNT")) + int(
                m2.group("ADDONCOUNT"),
            )  # combine b/c html summary does not split out
            self.rebuyCost = self.buyin + self.fee
            self.addOnCost = self.buyin + self.fee
        else:
            rebuy_count_hero = None

        if "PRIZEPOOL" in mg and mg["PRIZEPOOL"] is not None:
            if "Sunday Million" in mg["PRIZEPOOL"]:
                self.isSatellite = True
                new_buyin_date = HandHistoryConverter.changeTimezone(
                    datetime.datetime.strptime(  # noqa: DTZ007
                        "2019/01/27 00:00:00",
                        "%Y/%m/%d %H:%M:%S",
                    ),
                    "ET",
                    "UTC",
                )
                if self.startTime > new_buyin_date:
                    target_buyin, target_currency = 10900, "USD"
                else:
                    target_buyin, target_currency = 21500, "USD"
            else:
                self.prizepool = int(float(self.clearMoneyString(mg["PRIZEPOOL"])))
        if "ENTRIES" in mg:
            self.entries = int(mg["ENTRIES"])
        if "SATELLITE" in mg and mg["SATELLITE"] is not None:
            self.isSatellite = True
            target_buyin, target_currency = 0, "USD"
            if "TARGBUYIN" in mg and mg["TARGBUYIN"] is not None:
                target_buyin += int(100 * float(self.clearMoneyString(mg["TARGBUYIN"])))
            if "TARGFEE" in mg and mg["TARGFEE"] is not None:
                target_buyin += int(100 * float(self.clearMoneyString(mg["TARGFEE"])))
            if "TARGBOUNTY" in mg and mg["TARGBOUNTY"] is not None:
                target_buyin += int(100 * float(self.clearMoneyString(mg["TARGBOUNTY"])))
            if "TARGCUR" in mg and mg["TARGCUR"] is not None:
                if mg["CUR"] == "$":
                    target_currency = "USD"
                elif mg["CUR"] == "€":
                    target_currency = "EUR"
                elif mg["CUR"] == "£":
                    target_currency = "GBP"
                elif mg["CUR"] == "₹" or mg["CUR"] == "Rs. ":
                    target_currency = "INR"
                elif mg["CUR"] == "¥":
                    target_currency = "CNY"
                elif mg["CUR"] == "FPP" or mg["CUR"] == "SC":
                    target_currency = "PSFP"

        if mg.get("CURRENCY"):
            if mg["CURRENCY"] == "$":
                self.buyinCurrency = "USD"
            elif mg["CURRENCY"] == "€":
                self.buyinCurrency = "EUR"
            elif mg["CURRENCY"] == "£":
                self.buyinCurrency = "GBP"
            elif mg["CURRENCY"] == "₹" or mg["CURRENCY"] == "Rs. ":
                self.buyinCurrency = "INR"
            elif mg["CURRENCY"] == "¥":
                self.buyinCurrency = "CNY"
            else:
                self.buyinCurrency = "USD"
        elif "CURRENCY1" in mg and (mg["CURRENCY1"] == "FPP" or mg["CURRENCY1"] == "SC"):
            self.buyinCurrency = "PSFP"
        else:
            self.buyinCurrency = "play"
        if self.buyin == 0:
            self.buyinCurrency = "FREE"
        self.currency = self.buyinCurrency

        if "Zoom" in self.in_path or "Rush" in self.in_path:
            self.isFast = True

        self.lookupStructures(self.startTime)

        m3 = self.re_rank.search(self.summaryText)
        hero_rank = int(m3.group("RANK")) if m3 else 0

        m = re_player.finditer(self.summaryText)
        for a in m:
            mg = a.groupdict()
            # print "DEBUG: a.groupdict(): %s" % mg
            name = mg["NAME"]
            rank = int(mg["RANK"])
            winnings = 0
            rebuy_count = None
            add_on_count = None
            ko_count = None
            entry_id = 1

            if "WINNINGS" in mg and mg["WINNINGS"] is not None:
                winnings = int(100 * float(self.clearMoneyString(mg["WINNINGS"])))

            if "CUR" in mg and mg["CUR"] is not None:
                if mg["CUR"] == "$":
                    self.currency = "USD"
                elif mg["CUR"] == "€":
                    self.currency = "EUR"
                elif mg["CUR"] == "£":
                    self.currency = "GBP"
                elif mg["CUR"] == "₹" or mg["CUR"] == "Rs. ":
                    self.currency = "INR"
                elif mg["CUR"] == "¥":
                    self.currency = "CNY"
                elif "CUR1" in mg and (mg["CUR1"] == "FPP" or mg["CUR1"] == "SC"):
                    self.currency = "PSFP"

            if "STILLPLAYING" in mg and mg["STILLPLAYING"] is not None:
                # print "stillplaying"
                rank = None
                winnings = None

            if "TICKET" in mg and mg["TICKET"] is not None:
                # print "Tournament Ticket Level %s" % mg['LEVEL']
                step_values = {
                    "1": "750",  # Step 1 -    $7.50 USD
                    "2": "2750",  # Step 2 -   $27.00 USD
                    "3": "8200",  # Step 3 -   $82.00 USD
                    "4": "21500",  # Step 4 -  $215.00 USD
                    "5": "70000",  # Step 5 -  $700.00 USD
                    "6": "210000",  # Step 6 - $2100.00 USD
                }
                winnings = int(step_values[mg["LEVEL"]])

            if "QUALIFIED" in mg and mg["QUALIFIED"] is not None and self.isSatellite:
                winnings = target_buyin
                self.currency = target_currency

            if "ENTRYID" in mg and mg["ENTRYID"] is not None:
                entry_id = int(mg["ENTRYID"])
                self.isReEntry = True

            if hero_rank == rank and entry_id == 1:
                rebuy_count = rebuy_count_hero
                add_on_count = None
                ko_count = None

            # print "DEBUG: addPlayer(%s, %s, %s, %s, None, None, None)" %(rank, name, winnings, self.currency)
            # print "DEBUG: self.buyin: %s self.fee %s" %(self.buyin, self.fee)
            self.addPlayer(
                rank,
                name,
                winnings,
                self.currency,
                rebuy_count,
                add_on_count,
                ko_count,
                entry_id,
            )

        # print self

    def lookupStructures(self, date: datetime.datetime) -> None:
        """Look up tournament structure based on entries and date."""
        structures = PokerStarsStructures.PokerStarsStructures()
        if self.entries % 9 == 0 and self.entries < self.MAX_9_PLAYER_ENTRIES:
            entries = 9
        elif self.entries % 6 == 0 and self.entries < self.MAX_6_PLAYER_ENTRIES:
            entries = 6
        elif self.entries > self.MIN_LARGE_TOURNAMENT and self.entries < self.MAX_SMALL_TOURNAMENT:
            entries = 9
        else:
            entries = self.entries

        speed = structures.lookupSnG((self.buyin, self.fee, entries), date)
        if speed is not None:
            self.speed = speed
            if entries == self.DOUBLE_OR_NOTHING_ENTRIES:
                self.isDoubleOrNothing = True


# end class PokerStarsSummary
