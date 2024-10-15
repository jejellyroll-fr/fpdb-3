#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

"""pokerstars-specific summary parsing code"""

# import L10n
# _ = L10n.get_translation()

import datetime
import re
from HandHistoryConverter import HandHistoryConverter, FpdbParseError, FpdbHandPartial
import PokerStarsStructures
from TourneySummary import TourneySummary

import logging

try:
    import xlrd
except ImportError:
    xlrd = None

# PPokerstatars HH Format
log = logging.getLogger("parser")


class PokerStarsSummary(TourneySummary):
    hhtype = "summary"
    limits = {
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
    games = {  # base, category
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

    substitutions = {
        "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",  # legal ISO currency codes
        "LS": "\$|\xe2\x82\xac|\u20ac||\£|\u20b9|\¥|Rs\.\s|",  # legal currency symbols - Euro(cp1252, utf-8)
    }

    re_Identify = re.compile(
        "((?P<SITE>PokerStars|Full\sTilt|Run\sIt\sOnce\sPoker)\sTournament\s\#\d+|<title>TOURNEYS:)"
    )

    re_TourNo = re.compile("\#(?P<TOURNO>[0-9]+),")
    re_Header = re.compile("History\sRequest\s\-\s")
    re_emailHeader = re.compile("Delivered\-To\:\s")

    re_TourneyInfo = re.compile(
        """
                        \#(?P<TOURNO>[0-9]+),\s
                        (?P<DESC1>.+?\sSNG\s)?
                        ((?P<LIMIT>No\sLimit|NO\sLIMIT|Limit|LIMIT|Pot\sLimit|POT\sLIMIT|Pot\sLimit\sPre\-Flop,\sNo\sLimit\sPost\-Flop)\s)?
                        (?P<SPLIT>Split)?\s?
                        (?P<GAME>Hold\'em|6\+\sHold\'em|Hold\s\'Em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sHi/Lo|Omaha|Omaha\sHi/Lo|Badugi|Triple\sDraw\s2\-7\sLowball|Single\sDraw\s2\-7\sLowball|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sHi/Lo)?|Courchevel(\sHi/Lo)?|HORSE|8\-Game|HOSE|Mixed\sOmaha\sH/L|Mixed\sHold\'em|Mixed\sPLH/PLO|Mixed\sNLH/PLO||Mixed\sOmaha|Triple\sStud)\s+
                        (?P<DESC>[ a-zA-Z]+\s+)?
                        (Buy-In:\s(?P<CURRENCY>[%(LS)s]?)(?P<BUYIN>[,.0-9]+)(\s(?P<CURRENCY1>(FPP|SC)))?(\/[%(LS)s]?(?P<FEE>[,.0-9]+))?(\/[%(LS)s]?(?P<BOUNTY>[,.0-9]+))?(?P<CUR>\s(%(LEGAL_ISO)s))?\s+)?
                        (?P<ENTRIES>[0-9]+)\splayers\s+
                        ([%(LS)s]?(?P<ADDED>[,.\d]+)(\s(%(LEGAL_ISO)s))?\sadded\sto\sthe\sprize\spool\sby\s(PokerStars|Full\sTilt)(\.com)?\s+)?
                        (Total\sPrize\sPool:\s[%(LS)s]?(?P<PRIZEPOOL>[,.0-9]+|Sunday\sMillion\s(ticket|biļete))(\s(%(LEGAL_ISO)s))?\s+)?
                        (?P<SATELLITE>Target\sTournament\s\#(?P<TARGTOURNO>[0-9]+)\s+
                         (Buy-In:\s(?P<TARGCURRENCY>[%(LS)s]?)(?P<TARGBUYIN>[,.0-9]+)(\/[%(LS)s]?(?P<TARGFEE>[,.0-9]+))?(\/[%(LS)s]?(?P<TARGBOUNTY>[,.0-9]+))?(?P<TARGCUR>\s(%(LEGAL_ISO)s))?\s+)?)?
                        ([0-9]+\stickets?\sto\sthe\starget\stournament\s+)?
                        Tournament\sstarted\s+(-\s)?
                        (?P<DATETIME>.*$)
                        """
        % substitutions,
        re.VERBOSE | re.MULTILINE,
    )
    # re_TourneyInfo = re.compile(u"""(?P<TOURNO>[0-9]+),\s(?P<DESC1>.+?\sSNG\s)?((?P<LIMIT>No\sLimit|NO\sLIMIT|Limit|LIMIT|Pot\sLimit|POT\sLIMIT|Pot\sLimit\sPre\-Flop,\sNo\sLimit\sPost\-Flop)\s)?(?P<SPLIT>Split)?\s?(?P<GAME>Hold\'em|6\+\sHold\'em|Hold\s\'Em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sHi\/Lo|Omaha|Omaha\sHi\/Lo|Badugi|Triple\sDraw\s2\-7\sLowball|Single\sDraw\s2\-7\sLowball|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sHi\/Lo)?|Courchevel(\sHi\/Lo)?|HORSE|8\-Game|HOSE|Mixed\sOmaha\sH\/L|Mixed\sHold\'em|Mixed\sPLH\/PLO|Mixed\sNLH\/PLO||Mixed\sOmaha|Triple\sStud)\s+Buy-In:\s(?P<CURRENCY>\[%(LS)s\]?)((?P<BUYIN>[,.0-9]+)/\[%(LS)s\]?(?P<FEE>[,.0-9]+)|(?P<BUYIN2>[,.0-9]+))\s+""" % substitutions ,re.VERBOSE|re.MULTILINE)
    # re_TourneyInfo2 = re.compile(u"""(?P<ENTRIES>[0-9]+)\splayers\s+""" % substitutions ,re.VERBOSE|re.MULTILINE)
    # re_TourneyInfo3 = re.compile(u"""Total\sPrize\sPool:\s\[%(LS)s\]?(?P<PRIZEPOOL>[,.0-9]+)\s+""" % substitutions ,re.VERBOSE|re.MULTILINE)
    # re_TourneyInfo4 = re.compile(u"""Tournament\sstarted\s+(-\s)?(?P<DATETIME>.*$)""" % substitutions ,re.VERBOSE|re.MULTILINE)
    # You made 5 rebuys and 1 addons for a total of USD 3,180.00.
    re_rebuyAddOn = re.compile(
        """
                        You\smade\s(?P<REBUYCOUNT>\d+)\srebuys\sand\s(?P<ADDONCOUNT>\d+)\saddons\sfor\sa\stotal\sof\s(%(LEGAL_ISO)s)\s(?P<REBUYADDON>[,.0-9]+)
                               """
        % substitutions,
        re.VERBOSE | re.MULTILINE,
    )
    # You collected 5 bounties for a total of USD 875.00.
    re_KOBounties = re.compile(
        """
                        You\scollected\s(?P<KOCOUNT>\d+)\sbounties\sfor\sa\stotal\sof\s(%(LEGAL_ISO)s)\s(?P<KOBOUNTY>[,.0-9]+)
                               """
        % substitutions,
        re.VERBOSE | re.MULTILINE,
    )

    re_HTMLTourneyInfo = re.compile(
        r'<td align="right">(?P<DATETIME>.*)</td>'
        r'<td align="center">(?P<TOURNO>[0-9]+)</td>'
        r"(<td>(?P<TOURNAME>.*)</td>)?"
        r'<td align="right">'
        r"(?P<LIMIT>[ a-zA-Z\-]+)\s"
        r"(?P<SPLIT>Split)?\s?"
        r"(?P<GAME>Hold\'em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sH/L|Omaha|Omaha\sH/L|Badugi|Triple\sDraw\s2\-7(\sLowball)?|Single\sDraw\s2\-7(\sLowball)?|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sH/L)?|Courchevel(\sH/L)?|HORSE|Horse|8\-Game|HOSE|Hose|Omaha\sH/L\sMixed|Hold\'em\sMixed|PLH/PLO\sMixed|NLH/PLO\sMixed|Triple\sStud|NLH/NLO\sMixed|Mixed\sNLH/NLO|Mixed\sOmaha\sH/L|Mixed\sHold\'em|Mixed\sPLH/PLO|Mixed\sNLH/PLO)</td>"
        r"<td.*?>(?P<CURRENCY>(%(LEGAL_ISO)s)?)(&nbsp;)?</td>"
        r"<td.*?>(?P<BUYIN>([,.0-9 ]+|Freeroll))(?P<FPPBUYIN>(\s|&nbsp;)(FPP|SC|StarsCoin))?</td>"
        r"<td.*?>(?P<REBUYADDON>[,.0-9 ]+)</td>"
        r"<td.*?>(?P<FEE>[,.0-9 ]+)</td>"
        r'<td align="?right"?>(?P<RANK>[,.0-9]+)</td>'
        r'<td align="right">(?P<ENTRIES>[,.0-9]+)</td>'
        r"(<td.*?>[,.0-9]+</td>)?"
        r"<td.*?>(?P<WINNINGS>[,.0-9]+)(?P<FPPWINNINGS>\s\+\s[,.0-9]+(\s|&nbsp;)(FPP|SC|StarsCoin))?</td>"
        r"<td.*?>(?P<KOS>[,.0-9]+)</td>"
        r"<td.*?>((?P<TARGET>[,.0-9]+)|(&nbsp;))</td>"
        r"<td.*?>((?P<WONTICKET>\*\\\/\*)|(&nbsp;))</td>" % substitutions,
        re.IGNORECASE,
    )

    re_XLSTourneyInfo = {}
    re_XLSTourneyInfo["Date/Time"] = re.compile(r"(?P<DATETIME>.*)")
    re_XLSTourneyInfo["Tourney"] = re.compile(r"(?P<TOURNO>[0-9]+)")
    re_XLSTourneyInfo["Name"] = re.compile(r"(?P<TOURNAME>.*)")
    re_XLSTourneyInfo["Game"] = re.compile(
        r"(?P<LIMIT>[ a-zA-Z\-]+)\s"
        r"(?P<SPLIT>Split)?\s?"
        r"(?P<GAME>Hold\'em|Razz|RAZZ|7\sCard\sStud|7\sCard\sStud\sH/L|Omaha|Omaha\sH/L|Badugi|Triple\sDraw\s2\-7(\sLowball)?|Single\sDraw\s2\-7(\sLowball)?|5\sCard\sDraw|(5|6)\sCard\sOmaha(\sH/L)?|Courchevel(\sH/L)?|HORSE|Horse|8\-Game|HOSE|Hose|Omaha\sH/L\sMixed|Hold\'em\sMixed|PLH/PLO\sMixed|NLH/PLO\sMixed|Triple\sStud|NLH/NLO\sMixed|Mixed\sNLH/NLO|Mixed\sOmaha\sH/L|Mixed\sHold\'em|Mixed\sPLH/PLO|Mixed\sNLH/PLO)"
    )
    re_XLSTourneyInfo["Currency"] = re.compile(r"(?P<CURRENCY>(%(LEGAL_ISO)s)?)" % substitutions)
    re_XLSTourneyInfo["Buy-In"] = re.compile(r"(?P<BUYIN>([,.0-9]+|Freeroll))(?P<FPPBUYIN>\s(FPP|SC|StarsCoin))?")
    re_XLSTourneyInfo["ReBuys"] = re.compile(r"(?P<REBUYADDON>[,.0-9]+)")
    re_XLSTourneyInfo["Rake"] = re.compile(r"(?P<FEE>[,.0-9]+)")
    re_XLSTourneyInfo["Place"] = re.compile(r"(?P<RANK>[,.0-9]+)")
    re_XLSTourneyInfo["Entries"] = re.compile(r"(?P<ENTRIES>[,.0-9]+)")
    re_XLSTourneyInfo["Prize"] = re.compile(
        r"(?P<WINNINGS>[,.0-9]+)(?P<FPPWINNINGS>\s\+\s[,.0-9]+\s(FPP|SC|StarsCoin))?"
    )
    re_XLSTourneyInfo["Bounty Awarded"] = re.compile(r"(?P<KOS>[,.0-9]+)")
    re_XLSTourneyInfo["Target ID"] = re.compile(r"(?P<TARGET>[0-9]+)?")
    re_XLSTourneyInfo["Qualified"] = re.compile(r"(?P<WONTICKET>\*\\\/\*)?")

    re_PlayerStars = re.compile(
        """(?P<RANK>[,.0-9]+):\s(?P<NAME>.+?)(\s\[(?P<ENTRYID>\d+)\])?\s\(.+?\),(\s)?((?P<CUR>\[%(LS)s]?)(?P<WINNINGS>[,.0-9]+)(\s(?P<CUR1>(FPP|SC)))?)?(?P<STILLPLAYING>still\splaying)?((?P<TICKET>Tournament\sTicket)\s\(WSOP\sStep\s(?P<LEVEL>\d)\))?(?P<QUALIFIED>\s\(qualified\sfor\sthe\starget\stournament\)|Sunday\sMillion\s(ticket|biļete))?(\s+)?"""
        % substitutions
    )
    re_PlayerRIO = re.compile(
        """(?P<RANK>[,.0-9]+):\s(?P<NAME>[^,]+?)(,\s(?P<CUR>\[%(LS)s])(?P<WINNINGS>[,.0-9]+))?(\s+)?$"""
        % substitutions,
        re.MULTILINE,
    )
    re_HTMLPlayer1 = re.compile(
        r"<h2>All\s+(?P<SNG>(Regular|Sit & Go))\s?Tournaments\splayed\sby\s'(<b>)?(?P<NAME>.+?)':?</h2>", re.IGNORECASE
    )
    re_HTMLPlayer2 = re.compile(r"<title>TOURNEYS:\s&lt;(?P<NAME>.+?)&gt;</title>", re.IGNORECASE)
    re_XLSPlayer = re.compile(
        r"All\s(?P<SNG>(Regular|(Heads\sup\s)?Sit\s&\sGo))\sTournaments\splayed\sby\s\'(?P<NAME>.+?)\'"
    )

    re_DateTime = re.compile(
        """(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)""",
        re.MULTILINE,
    )
    re_HTMLDateTime = re.compile(
        """(?P<M>[0-9]+)\/(?P<D>[0-9]+)\/(?P<Y>[0-9]{4})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) (?P<AMPM>(AM|PM))""",
        re.MULTILINE,
    )
    re_HTMLTourneyExtraInfo = re.compile(
        "\[(Deep\s)?((?P<MAX>\d+)-Max,\s?)?((\dx\-)?(?P<SPEED>Turbo|Hyper\-Turbo))?(, )?(?P<REBUYADDON1>\dR\dA)?"
    )
    re_XLSDateTime = re.compile("^[.0-9]+$")
    re_Rank = re.compile("^You\sfinished\sin\s(?P<RANK>[0-9]+)(st|nd|rd|th)\splace\.", re.MULTILINE)
    # re_WinningRankOne   = re.compile(u"^%(PLYR)s wins the tournament and receives %(CUR)s(?P<AMT>[\.0-9]+) - congratulations!$" %  substitutions, re.MULTILINE)
    # re_WinningRankOther = re.compile(u"^%(PLYR)s finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place and received %(CUR)s(?P<AMT>[.0-9]+)\.$" %  substitutions, re.MULTILINE)
    # re_RankOther        = re.compile(u"^%(PLYR)s finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place$" %  substitutions, re.MULTILINE)

    codepage = ["utf8", "cp1252"]

    @staticmethod
    def getSplitRe(self, head):
        re_SplitTourneys = re.compile("(?:PokerStars|Full\sTilt|Run\sIt\sOnce\sPoker) Tournament ")
        re_HTMLSplitTourneys = re.compile('tr id="row_\d+')
        m = re.search("<title>TOURNEYS:", head)
        if m is not None:
            self.hhtype = "html"
            return re_HTMLSplitTourneys
        self.hhtype = "summary"
        return re_SplitTourneys

    def parseSummary(self):
        if self.hhtype == "summary":
            self.parseSummaryFile()
        elif self.hhtype == "html":
            self.parseSummaryHtml()
        elif self.hhtype == "xls":
            self.parseSummaryXLS()
        elif self.hhtype == "hh":
            self.parseSummaryFromHH()
        else:
            raise FpdbParseError(("parseSummary FAIL"))

    def parseSummaryFromHH(self):
        raise FpdbParseError(("PokerStarsSummary.parseSummaryHtml: This file format is not yet supported"))
        # self.entries   = Unavailable from HH
        # self.prizepool = Unavailable from HH
        # self.startTime = Unreliable from HH (late reg)
        # obj = getattr(PokerStarsToFpdb, "PokerStars", None)
        # hhc = obj(self.config, in_path = self.in_path, sitename = None, autostart = False)

        # self.buyin     = int(100*hhc.SnG_Structures[tourneyNameFull]['buyIn'])
        # self.fee       = int(100*hhc.SnG_Structures[tourneyNameFull]['fee'])

        # self.tourNo =
        # self.buyin     =
        # self.fee       =
        # self.buyinCurrency =
        # self.currency  =
        # self.maxseats  =
        # self.isSng     =
        # self.addPlayer(rank, name, winnings, self.currency, rebuyCount, addOnCount, koCount)

    def parseSummaryXLS(self):
        info = self.summaryText[0]
        m = self.re_XLSPlayer.search(info["header"])
        if m is None:
            tmp1 = info["header"]
            tmp2 = str(info)[0:200]
            log.error(("PokerStarsSummary.parseSummaryXLS: '%s' '%s") % (tmp1, tmp2))
            raise FpdbParseError
        info.update(m.groupdict())
        mg = {}
        for k, j in info.iteritems():
            if self.re_XLSTourneyInfo.get(k) is not None:
                m1 = self.re_XLSTourneyInfo[k].search(j)
                if m1:
                    mg.update(m1.groupdict())
                elif k == "Game":
                    log.error(("PokerStarsSummary.parseSummaryXLS Game '%s' not found") % j)
                    raise FpdbParseError
        info.update(mg)
        self.parseSummaryArchive(info)

    def parseSummaryHtml(self):
        info = {}
        m1 = self.re_HTMLPlayer1.search(self.header)
        if m1 is None:
            m1 = self.re_HTMLPlayer2.search(self.header)
        m2 = self.re_HTMLTourneyInfo.search(self.summaryText)
        if m1 is None or m2 is None:
            if self.re_HTMLPlayer1.search(self.summaryText) or self.re_HTMLPlayer2.search(self.summaryText):
                raise FpdbHandPartial
            tmp1 = self.header[0:200] if m1 is None else "NA"
            tmp2 = self.summaryText if m2 is None else "NA"
            log.error(("PokerStarsSummary.parseSummaryHtml: '%s' '%s") % (tmp1, tmp2))
            raise FpdbParseError
        info.update(m1.groupdict())
        info.update(m2.groupdict())
        self.parseSummaryArchive(info)

    def parseSummaryArchive(self, info):
        if "SNG" in info and "Sit & Go" in info["SNG"]:
            self.isSng = True

        if "TOURNAME" in info and info["TOURNAME"] is not None:
            self.tourneyName = re.sub("</?(b|font).*?>", "", info["TOURNAME"])
            m3 = self.re_HTMLTourneyExtraInfo.search(self.tourneyName)
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
                self.buyin = int(100 * float(self.clearMoneyString(info["BUYIN"].replace(" ", ""))))
        if info["FEE"] is not None:
            self.fee = int(100 * float(self.clearMoneyString(info["FEE"].replace(" ", ""))))
        if "REBUYADDON" in info and float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))) > 0:
            self.isRebuy = True
            self.isAddOn = True
            rebuyAddOnAmt = int(100 * float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))))
            if self.buyin != 0:
                rebuys = int(rebuyAddOnAmt / self.buyin)
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
            m4 = self.re_HTMLDateTime.finditer(info["DATETIME"])
        datetimestr = None  # default used if time not found
        for a in m4:
            datetimestr = "%s/%s/%s %s:%s:%s %s" % (
                a.group("Y"),
                a.group("M"),
                a.group("D"),
                a.group("H"),
                a.group("MIN"),
                a.group("S"),
                a.group("AMPM"),
            )
            self.endTime = datetime.datetime.strptime(
                datetimestr, "%Y/%m/%d %I:%M:%S %p"
            )  # also timezone at end, e.g. " ET"
            self.endTime = HandHistoryConverter.changeTimezone(self.endTime, "ET", "UTC")
        if datetimestr is None:
            if xlrd and self.re_XLSDateTime.match(info["DATETIME"]):
                datetup = xlrd.xldate_as_tuple(float(info["DATETIME"]), 0)
                datetimestr = "%d/%d/%d %d:%d:%d" % (
                    datetup[0],
                    datetup[1],
                    datetup[2],
                    datetup[3],
                    datetup[4],
                    datetup[5],
                )
            else:
                datetimestr = "2000/01/01 12:00:00"
            self.endTime = datetime.datetime.strptime(
                datetimestr, "%Y/%m/%d %H:%M:%S"
            )  # also timezone at end, e.g. " ET"
            self.endTime = HandHistoryConverter.changeTimezone(self.endTime, "ET", "UTC")

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
            rebuyCount = None
            addOnCount = None
            koCount = None
            entryId = 1

            if "WINNINGS" in info and info["WINNINGS"] is not None:
                winnings = int(100 * float(self.clearMoneyString(info["WINNINGS"])))

            if "REBUYADDON" in info and float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))) > 0:
                rebuyAddOnAmt = int(100 * float(self.clearMoneyString(info["REBUYADDON"].replace(" ", ""))))
                rebuyCount = rebuyAddOnAmt / self.buyin

            # KOs should be exclusively handled in the PokerStars hand history files
            if "KOS" in info and info["KOS"] is not None and info["KOS"] != "0.00":
                self.isKO = True

            re_HTMLEntries = re.compile(
                r'<td align="center">%s</td>.+?<td align="?right"?>(?P<RANK>[,.0-9]+)</td>' % self.tourNo, re.IGNORECASE
            )
            m = re_HTMLEntries.finditer(self.header)
            entries = []
            for a in m:
                entries.append(int(self.clearMoneyString(a.group("RANK"))))
            entries.sort(reverse=True)

            if len(entries) > 1:
                entryId = entries.index(rank) + 1
                self.isReEntry = True

            self.addPlayer(rank, name, winnings, self.currency, rebuyCount, addOnCount, koCount, entryId)

    def parseSummaryFile(self):
        m = self.re_TourneyInfo.search(self.summaryText)
        if m is None:
            if self.re_Header.match(self.summaryText):
                raise FpdbHandPartial
            if self.re_emailHeader.match(self.summaryText):
                raise FpdbHandPartial
            # tmp = self.summaryText[0:200]
            log.error(("PokerStarsSummary.parseSummaryFile: '%s'") % self.summaryText)
            raise FpdbParseError
        # m4 = self.re_TourneyInfo4.search(self.summaryText)
        # print "DEBUG: m.groupdict(): %s" % m.groupdict()
        mg = m.groupdict()
        # mg4 = m4.groupdict()
        if "DATETIME" in mg:
            m1 = self.re_DateTime.finditer(mg["DATETIME"])
        datetimestr = "2000/01/01 00:00:00"  # default used if time not found
        for a in m1:
            datetimestr = "%s/%s/%s %s:%s:%s" % (
                a.group("Y"),
                a.group("M"),
                a.group("D"),
                a.group("H"),
                a.group("MIN"),
                a.group("S"),
            )

        self.startTime = datetime.datetime.strptime(
            datetimestr, "%Y/%m/%d %H:%M:%S"
        )  # also timezone at end, e.g. " ET"
        self.startTime = HandHistoryConverter.changeTimezone(self.startTime, "ET", "UTC")

        if mg["DESC1"] is not None:
            self.siteName = "Run It Once Poker"
            self.siteId = 26
            re_Player = self.re_PlayerRIO
        else:
            re_Player = self.re_PlayerStars

        if "TOURNO" in mg:
            self.tourNo = mg["TOURNO"]
        if "LIMIT" in mg and mg["LIMIT"] is not None:
            self.gametype["limitType"] = self.limits[mg["LIMIT"]]
        else:
            self.gametype["limitType"] = "fl"
        if "GAME" in mg:
            self.gametype["category"] = self.games[mg["GAME"]][1]
        if "SPLIT" in mg and mg["SPLIT"] == "Split":
            self.isSplit = True
        if mg["BOUNTY"] is not None and mg["FEE"] is not None:
            self.koBounty = int(100 * float(self.clearMoneyString(mg["FEE"])))
            self.isKO = True
            mg["FEE"] = mg["BOUNTY"]
        if mg["BUYIN"] is not None:
            self.buyin = int(100 * float(self.clearMoneyString(mg["BUYIN"]))) + self.koBounty
        if mg["FEE"] is not None:
            self.fee = int(100 * float(self.clearMoneyString(mg["FEE"])))

        m2 = self.re_rebuyAddOn.search(self.summaryText)
        if m2 and m2.group("REBUYCOUNT") is not None:
            self.isRebuy = True
            self.isAddOn = True
            # You made 5 rebuys and 1 addons for a total of USD 3,180.00.
            rebuyCountHero = int(m2.group("REBUYCOUNT")) + int(
                m2.group("ADDONCOUNT")
            )  # combine b/c html summary does not split out
            self.rebuyCost = self.buyin + self.fee
            self.addOnCost = self.buyin + self.fee
        else:
            rebuyCountHero = None

        if "PRIZEPOOL" in mg and mg["PRIZEPOOL"] is not None:
            if "Sunday Million" in mg["PRIZEPOOL"]:
                self.isSatellite = True
                newBuyinDate = HandHistoryConverter.changeTimezone(
                    datetime.datetime.strptime("2019/01/27 00:00:00", "%Y/%m/%d %H:%M:%S"), "ET", "UTC"
                )
                if self.startTime > newBuyinDate:
                    targetBuyin, targetCurrency = 10900, "USD"
                else:
                    targetBuyin, targetCurrency = 21500, "USD"
            else:
                self.prizepool = int(float(self.clearMoneyString(mg["PRIZEPOOL"])))
        if "ENTRIES" in mg:
            self.entries = int(mg["ENTRIES"])
        if "SATELLITE" in mg and mg["SATELLITE"] is not None:
            self.isSatellite = True
            targetBuyin, targetCurrency = 0, "USD"
            if mg["TARGBUYIN"] is not None:
                targetBuyin += int(100 * float(self.clearMoneyString(mg["TARGBUYIN"])))
            if mg["TARGFEE"] is not None:
                targetBuyin += int(100 * float(self.clearMoneyString(mg["TARGFEE"])))
            if mg["TARGBOUNTY"] is not None:
                targetBuyin += int(100 * float(self.clearMoneyString(mg["TARGBOUNTY"])))
            if mg["TARGCUR"] is not None:
                if mg["CUR"] == "$":
                    targetCurrency = "USD"
                elif mg["CUR"] == "€":
                    targetCurrency = "EUR"
                elif mg["CUR"] == "£":
                    targetCurrency = "GBP"
                elif mg["CUR"] == "₹":
                    targetCurrency = "INR"
                elif mg["CUR"] == "Rs. ":
                    targetCurrency = "INR"
                elif mg["CUR"] == "¥":
                    targetCurrency = "CNY"
                elif mg["CUR"] == "FPP":
                    targetCurrency = "PSFP"
                elif mg["CUR"] == "SC":
                    targetCurrency = "PSFP"

        if mg["CURRENCY"] == "$":
            self.buyinCurrency = "USD"
        elif mg["CURRENCY"] == "€":
            self.buyinCurrency = "EUR"
        elif mg["CURRENCY"] == "£":
            self.buyinCurrency = "GBP"
        elif mg["CURRENCY"] == "₹":
            self.buyinCurrency = "INR"
        elif mg["CURRENCY"] == "Rs. ":
            self.buyinCurrency = "INR"
        elif mg["CURRENCY"] == "¥":
            self.buyinCurrency = "CNY"
        elif mg["CURRENCY1"] == "FPP":
            self.buyinCurrency = "PSFP"
        elif mg["CURRENCY1"] == "SC":
            self.buyinCurrency = "PSFP"
        elif not mg["CURRENCY"]:
            self.buyinCurrency = "play"
        if self.buyin == 0:
            self.buyinCurrency = "FREE"
        self.currency = self.buyinCurrency

        if "Zoom" in self.in_path or "Rush" in self.in_path:
            self.isFast = True

        self.lookupStructures(self.startTime)

        m3 = self.re_Rank.search(self.summaryText)
        if m3:
            heroRank = int(m3.group("RANK"))
        else:
            heroRank = 0

        m = re_Player.finditer(self.summaryText)
        for a in m:
            mg = a.groupdict()
            # print "DEBUG: a.groupdict(): %s" % mg
            name = mg["NAME"]
            rank = int(mg["RANK"])
            winnings = 0
            rebuyCount = None
            addOnCount = None
            koCount = None
            entryId = 1

            if "WINNINGS" in mg and mg["WINNINGS"] is not None:
                winnings = int(100 * float(self.clearMoneyString(mg["WINNINGS"])))

            if "CUR" in mg and mg["CUR"] is not None:
                if mg["CUR"] == "$":
                    self.currency = "USD"
                elif mg["CUR"] == "€":
                    self.currency = "EUR"
                elif mg["CUR"] == "£":
                    self.currency = "GBP"
                elif mg["CUR"] == "₹":
                    self.currency = "INR"
                elif mg["CUR"] == "Rs. ":
                    self.currency = "INR"
                elif mg["CUR"] == "¥":
                    self.currency = "CNY"
                elif mg["CUR1"] == "FPP":
                    self.currency = "PSFP"
                elif mg["CUR1"] == "SC":
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
                winnings = targetBuyin
                self.currency = targetCurrency

            if "ENTRYID" in mg and mg["ENTRYID"] is not None:
                entryId = int(mg["ENTRYID"])
                self.isReEntry = True

            if heroRank == rank and entryId == 1:
                rebuyCount = rebuyCountHero
                addOnCount = None
                koCount = None

            # print "DEBUG: addPlayer(%s, %s, %s, %s, None, None, None)" %(rank, name, winnings, self.currency)
            # print "DEBUG: self.buyin: %s self.fee %s" %(self.buyin, self.fee)
            self.addPlayer(rank, name, winnings, self.currency, rebuyCount, addOnCount, koCount, entryId)

        # print self

    def lookupStructures(self, date):
        Structures = PokerStarsStructures.PokerStarsStructures()
        if self.entries % 9 == 0 and self.entries < 45:
            entries = 9
        elif self.entries % 6 == 0 and self.entries < 30:
            entries = 6
        elif self.entries > 6 and self.entries < 9:
            entries = 9
        else:
            entries = self.entries

        speed = Structures.lookupSnG((self.buyin, self.fee, entries), date)
        if speed is not None:
            self.speed = speed
            if entries == 10:
                self.isDoubleOrNothing = True


# end class PokerStarsSummary
