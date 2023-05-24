#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2013 Chaz Littlejohn
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

#import L10n
#_ = L10n.get_translation()

from decimal_wrapper import Decimal
import datetime

from Exceptions import FpdbParseError
from HandHistoryConverter import *
from TourneySummary import *
import BovadaToFpdb

class BovadaSummary(TourneySummary):
    """
    A subclass of TourneySummary that parses Bovada tournament summaries.

    Attributes:
        substitutions (dict): A dictionary of strings to be substituted in regular expressions.
        codepage (tuple): A tuple of valid codepages for the summary.
        re_Identify (re.Pattern): A regular expression pattern to identify Bovada hands.
        re_AddOn (re.Pattern): A regular expression pattern to parse the Addon section.
        re_Rebuyin (re.Pattern): A regular expression pattern to parse the Rebuyin section.
        re_Ranking (re.Pattern): A regular expression pattern to parse the Ranking section.
        re_Stand (re.Pattern): A regular expression pattern to parse the Stand section.
    """    
    substitutions = {
                         'LEGAL_ISO' : "USD",      # legal ISO currency codes
                                'LS' : u"\$|", # legal currency symbols - Euro(cp1252, utf-8)
                               'PLYR': r'(?P<PNAME>.+?)',
                               'PLYR1': r'(?P<PNAME1>.+?)',
                                'CUR': u"(\$|)",
                                'NUM' :u".,\d",
                        }
    codepage = ("utf8", "cp1252")
    
    re_Identify = re.compile(u'(Ignition|Bovada|Bodog(\.eu|\sUK|\sCanada|88)?)\sHand')
    re_AddOn = re.compile(r"^%(PLYR)s  ?\[ME\] : Addon (?P<ADDON>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_Rebuyin = re.compile(r"%(PLYR)s  ?\[ME\] : Rebuyin (?P<REBUY>[%(NUM)s]+)" % substitutions, re.MULTILINE)
    re_Ranking = re.compile(r"%(PLYR)s  ?\[ME\] : Ranking (?P<RANK>[%(NUM)s]+)(\s+?%(PLYR1)s  ?\[ME\] : Prize Cash \[(?P<WINNINGS>%(CUR)s[%(NUM)s]+)\])?" % substitutions, re.MULTILINE)
    re_Stand = re.compile(r"%(PLYR)s  ?\[ME\] : Stand" % substitutions, re.MULTILINE)
    
    @staticmethod
    def getSplitRe(self, head):
        """
        Returns a regular expression object that can be used to split tournament
        information from a Bovada tournament header.

        Args:
            head (str): The tournament header string.

        Returns:
            re.Pattern: A compiled regular expression pattern that can be used to
            split tournament information from the header string.
        """
        # Regular expression pattern to split tournament information from header
        return re.compile("Bovada Tournament ") #not used
    
    def parseSummary(self):
        """
        Parses summary text and extracts relevant information for hand history.

        Returns:
            None

        Raises:
            FpdbParseError: If tournament text not found or failed to detect currency.

        """

        # Instantiate the BovadaToFpdb object
        obj = getattr(BovadaToFpdb, "Bovada", None)
        hhc = obj(self.config, in_path=self.in_path, sitename=None, autostart=False)

        # Search for the game info in the summary text
        m = hhc.re_GameInfo.search(self.summaryText)
        if m is None:
            tmp = self.summaryText[0:200]
            log.error(("BovadaSummary.parseSummary: '%s'") % tmp)
            raise FpdbParseError

        # Extract relevant information from the game info
        info = {}
        info.update(m.groupdict())

        # Search for the buy-in in the input path
        m = hhc.re_Buyin.search(self.in_path)
        if m:
            info.update(m.groupdict())

        # Check if the summary text corresponds to a tournament
        if info['TOURNO'] is None:
            tmp = self.summaryText[0:200]
            log.error(("BovadaSummary.parseSummary: Text does not appear to be a tournament '%s'") % tmp)
            raise FpdbParseError
        else:
            self.tourNo = info['TOURNO']

            # Extract the limit type and game category from the info
            if 'LIMIT' in info:
                if not info['LIMIT']:
                    self.gametype['limitType'] = 'nl'
                else:
                    self.gametype['limitType'] = hhc.limits[info['LIMIT']]
            if 'GAME' in info:
                self.gametype['category'] = hhc.games[info['GAME']][1]

            if 'CURRENCY' in info and info['CURRENCY']:
                self.buyinCurrency = hhc.currencies[info['CURRENCY']]
            self.currency = self.buyinCurrency

            # Extract the start time of the tournament
            if 'DATETIME' in info and info['CURRENCY'] is not None:
                m1 = hhc.re_DateTime.finditer(info['DATETIME'])
                datetimestr = "2000/01/01 00:00:00"  # default used if time not found
                for a in m1:
                    datetimestr = "%s/%s/%s %s:%s:%s" % (a.group('Y'), a.group('M'), a.group('D'), a.group('H'), a.group('MIN'), a.group('S'))
                    # tz = a.group('TZ')  # just assume ET??
                    # print "   tz = ", tz, " datetime =", datetimestr
                self.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S")  # also timezone at end, e.g. " ET"
                self.startTime = HandHistoryConverter.changeTimezone(self.startTime, "ET", "UTC")

            # Initialize buy-in, fee, prize pool, and entries
            self.buyin = 0
            self.fee = 0
            self.prizepool = None
            self.entries = None

            if self.currency is None:
                self.buyinCurrency = "FREE"

            # Process the buy-in information
            if 'BUYIN' in info and info['BUYIN'] is not None:
                if info['BIAMT'] is not None and info['BIRAKE'] is not None:
                    if info['BUYIN'].find("$") != -1:
                        self.buyinCurrency = "USD"
                    elif re.match("^[0-9+]*$", info['BUYIN']):
                        self.buyinCurrency = "play"
                    else:
                        log.error(("BovadaSummary.parseSummary: Failed to detect currency"))
                        raise FpdbParseError
                    self.currency = self.buyinCurrency

                    info['BIAMT'] = hhc.clearMoneyString(info['BIAMT'].strip(u'$'))

                    if info['BIRAKE']:
                        info['BIRAKE'] = hhc.clearMoneyString(info['BIRAKE'].strip(u'$'))
                    else:
                        info['BIRAKE'] = '0'

                    if info['TICKET'] is None:
                        self.buyin = int(100 * Decimal(info['BIAMT']))
                        self.fee = int(100 * Decimal(info['BIRAKE']))
                    else:
                        self.buyin = 0
                        self.fee = 0

                    if info['TOURNAME'] is not None:
                        tourneyNameFull = info['TOURNAME'] + ' - ' + info['BIAMT'] + '+' + info['BIRAKE']
                        self.tourneyName = tourneyNameFull

                        if 'TOURNAME' in info and 'Rebuy' in info['TOURNAME']:
                            self.isAddOn, self.isRebuy = True, True
                            self.rebuyCost = self.buyin
                            self.addOnCost = self.buyin

            rebuys, addons, winnings = None, None, []
            i = 0

            # Extract rankings and winnings from the summary text
            m = self.re_Ranking.finditer(self.summaryText)
            for a in m:
                mg = a.groupdict()
                winnings.append([int(mg['RANK']), 0])
                if mg['WINNINGS'] is not None:
                    if mg['WINNINGS'].find("$") != -1:
                        self.currency = "USD"
                    elif re.match("^[0-9+]*$", mg['WINNINGS']):
                        self.currency = "play"
                    winnings[i][1] = int(100 * Decimal(self.clearMoneyString(mg['WINNINGS'])))
                i += 1

            # Count rebuys and addons
            m = self.re_Rebuyin.finditer(self.summaryText)
            for a in m:
                if rebuys is None:
                    rebuys = 0
                rebuys += 1

            m = self.re_AddOn.finditer(self.summaryText)
            for a in m:
                if addons is None:
                    addons = 0
                addons += 1

            i = 0

            # Add players to the tournament
            for win in winnings:
                if len(win) > 1:
                    rankId = (i + 1)
                else:
                    rankId = None
                if i == 0:
                    self.addPlayer(win[0], 'Hero', win[1], self.currency, rebuys, addons, rankId)
                else:
                    self.addPlayer(win[0], 'Hero', win[1], self.currency, 0, 0, rankId)
                i += 1
