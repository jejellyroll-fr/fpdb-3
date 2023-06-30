#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright 2008-2011, Carl Gherardi
#    
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

#import L10n
#_ = L10n.get_translation()

# TODO: straighten out discards for draw games

import sys
from HandHistoryConverter import *
from decimal_wrapper import Decimal

# Unibet HH Format

class Unibet(HandHistoryConverter):

    # Class Variables

    sitename = "Unibet"
    filetype = "text"
    codepage = ("utf8", "cp1252", "ISO-8859-1")
    siteId   = 30 # Needs to match id entry in Sites database
    sym = {'USD': "\$", 'CAD': "\$", 'T$': "", "EUR": "\xe2\x82\xac", "GBP": "\£", "play": "", "INR": "\₹", "CNY": "\¥"}         # ADD Euro, Sterling, etc HERE
    substitutions = {
                     'LEGAL_ISO' : "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",      # legal ISO currency codes
                            'LS' : u"\$|\xe2\x82\xac|\u20ac|\£|\u20b9|\¥|", # legal currency symbols - Euro(cp1252, utf-8)
                           'PLYR': r'\s?(?P<PNAME>.+?)',
                            'CUR': u"(\$|\xe2\x82\xac|\u20ac||\£|\u20b9|\¥|)",
                          'BRKTS': r'(\(button\) |\(small blind\) |\(big blind\) |\(button blind\) |\(button\) \(small blind\) |\(small blind/button\) |\(button\) \(big blind\) )?',
                    }
                    
    # translations from captured groups to fpdb info strings
    Lim_Blinds = {      '0.04': ('0.01', '0.02'),         '0.08': ('0.02', '0.04'),
                        '0.10': ('0.02', '0.05'),         '0.20': ('0.05', '0.10'),
                        '0.40': ('0.10', '0.20'),         '0.50': ('0.10', '0.25'),
                        '1.00': ('0.25', '0.50'),         '1': ('0.25', '0.50'),
                        '2.00': ('0.50', '1.00'),         '2': ('0.50', '1.00'),
                        '4.00': ('1.00', '2.00'),         '4': ('1.00', '2.00'),
                        '6.00': ('1.00', '3.00'),         '6': ('1.00', '3.00'),
                        '8.00': ('2.00', '4.00'),         '8': ('2.00', '4.00'),
                       '10.00': ('2.00', '5.00'),        '10': ('2.00', '5.00'),
                       '16.00': ('4.00', '8.00'),        '16': ('4.00', '8.00'),
                       '20.00': ('5.00', '10.00'),       '20': ('5.00', '10.00'),
                       '30.00': ('10.00', '15.00'),      '30': ('10.00', '15.00'),
                       '40.00': ('10.00', '20.00'),      '40': ('10.00', '20.00'),
                       '50.00': ('10.00', '25.00'),      '50': ('10.00', '25.00'),
                       '60.00': ('15.00', '30.00'),      '60': ('15.00', '30.00'),
                       '80.00': ('20.00', '40.00'),      '80': ('20.00', '40.00'),
                      '100.00': ('25.00', '50.00'),     '100': ('25.00', '50.00'),
                      '150.00': ('50.00', '75.00'),     '150': ('50.00', '75.00'),
                      '200.00': ('50.00', '100.00'),    '200': ('50.00', '100.00'),
                      '400.00': ('100.00', '200.00'),   '400': ('100.00', '200.00'),
                      '500.00': ('100.00', '250.00'),   '500': ('100.00', '250.00'),
                      '600.00': ('150.00', '300.00'),   '600': ('150.00', '300.00'),
                      '800.00': ('200.00', '400.00'),   '800': ('200.00', '400.00'),
                     '1000.00': ('250.00', '500.00'),  '1000': ('250.00', '500.00'),
                     '2000.00': ('500.00', '1000.00'), '2000': ('500.00', '1000.00'),
                     '4000.00': ('1000.00', '2000.00'), '4000': ('1000.00', '2000.00'),
                    '10000.00': ('2500.00', '5000.00'), '10000': ('2500.00', '5000.00'),
                    '20000.00': ('5000.00', '10000.00'),'20000': ('5000.00', '10000.00'),
                    '40000.00': ('10000.00', '20000.00'),'40000': ('10000.00', '20000.00'),
                  }

    limits = { 
              'No Limit':'nl', 
              'Pot Limit':'pl', 
              'Fixed Limit':'fl', 
              'Limit':'fl'
              }
    games = {                          # base, category
                              "Hold'em" : ('hold','holdem'),
                                'Omaha' : ('hold','omahahi'),
                          'Omaha Hi/Lo' : ('hold','omahahilo')
               }
    currencies = { u'€':'EUR', '$':'USD', '':'T$', u'£':'GBP', u'¥':'CNY', u'₹':'INR'}

    # Static regexes
    re_GameInfo     = re.compile(u"""
          Game\s\#(?P<HID>[0-9]+):\s+Table\s(?P<CURRENCY>€|$|£)[0-9]+\s(?P<LIMIT>PL|NL|FL)\s-\s(?P<SB>[.0-9]+)/(?P<BB>[.0-9]+)\s-\s(?P<GAME>Pot\sLimit\sOmaha|No\sLimit\sHold\'Em\sBanzai)\s-\s(?P<DATETIME>.*$)
        """ % substitutions, re.MULTILINE|re.VERBOSE)

    re_PlayerInfo   = re.compile(u"""
          Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>\w+)\s\((€|$|£)(?P<CASH>[,.0-9]+)\)""" % substitutions, 
          re.MULTILINE|re.VERBOSE)

    re_PlayerInfo2   = re.compile(u"""
          (?P<SITOUT>\w+)\s\((€|$|£)[,.0-9]+\)\s\(sitting\sout\)""" % substitutions, 
          re.MULTILINE|re.VERBOSE)

    re_HandInfo     = re.compile("""
          (?P<TABLE>\sTable\s(€|$|£)[0-9]+\s(PL|NL|FL))""", 
          re.MULTILINE|re.VERBOSE)

    re_Identify     = re.compile(u'Game\s\#\d+:\sTable\s(€|$|£)[0-9]+\s(PL|NL|FL)')
    re_SplitHands   = re.compile('(?:\s?\n){2,}')
    re_TailSplitHands   = re.compile('(\n\n\n+)')
    re_Button       = re.compile('(?P<BUTTON>\w+)\shas\sthe\sbutton', re.MULTILINE)
    re_Board        = re.compile(r"\[(?P<CARDS>.+)\]")
    re_Board2       = re.compile(r"\[(?P<C1>\S\S)\] \[(\S\S)?(?P<C2>\S\S) (?P<C3>\S\S)\]")
    re_DateTime1     = re.compile("""(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+)\s(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})""", re.MULTILINE)
    re_DateTime2     = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+)""", re.MULTILINE)
    # revised re including timezone (not currently used):
    #re_DateTime     = re.compile("""(?P<Y>[0-9]{4})\/(?P<M>[0-9]{2})\/(?P<D>[0-9]{2})[\- ]+(?P<H>[0-9]+):(?P<MIN>[0-9]+):(?P<S>[0-9]+) \(?(?P<TZ>[A-Z0-9]+)""", re.MULTILINE)

    # These used to be compiled per player, but regression tests say
    # we don't have to, and it makes life faster.
    re_PostSB           = re.compile(r"%(PLYR)s:\sposts\ssmall\sblind\s%(CUR)s(?P<SB>[,.0-9]+)" %  substitutions, re.MULTILINE)
    re_PostBB           = re.compile(r"%(PLYR)s:\sposts\sbig\sblind\s%(CUR)s(?P<BB>[,.0-9]+)" %  substitutions, re.MULTILINE)
    re_PostBUB          = re.compile(r"%(PLYR)s:\sposts\sbutton\sblind\s%(CUR)s(?P<BUB>[,.0-9]+)" %  substitutions, re.MULTILINE)
    re_Antes            = re.compile(r"%(PLYR)s:\sposts\sthe\sant\s%(CUR)s(?P<ANTE>[,.0-9]+)" % substitutions, re.MULTILINE)
    re_BringIn          = re.compile(r"%(PLYR)s:\sbrings[- ]in(\slow|)\sfo/%(CUR)s(?P<BRINGIN>[,.0-9]+)" % substitutions, re.MULTILINE)
    re_PostBoth         = re.compile(r"%(PLYR)s:\sposts\ssmall\s\&\sbig\sblinds\s%(CUR)s(?P<SBBB>[,.0-9]+)" %  substitutions, re.MULTILINE)
    re_PostStraddle     = re.compile(r"%(PLYR)s:\sposts\sstraddle\s%(CUR)s(?P<STRADDLE>[,.0-9]+)" %  substitutions, re.MULTILINE)
    re_Action           = re.compile(r"""
                        %(PLYR)s:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands\spat)
                        (\s%(CUR)s(?P<BET>[,.\d]+))?(\sto\s%(CUR)s(?P<BETTO>[,.\d]+))? 
                        \s*(and\sis\sall.in)?
                        (and\shas\sreached\sthe\s[%(CUR)s\d\.,]+\scap)?
                        (\son|\scards?)?
                        (\s\(disconnect\))?
                        (\s\[(?P<CARDS>.+?)\])?\s*$"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    re_ShowdownAction   = re.compile(r"%s: shows \[(?P<CARDS>.*)\]" % substitutions['PLYR'], re.MULTILINE)
    re_sitsOut          = re.compile("^%s sits out" %  substitutions['PLYR'], re.MULTILINE)
    re_HeroCards = re.compile(r"Dealt\sto\s%(PLYR)s\s(?:\[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % substitutions, re.MULTILINE)
    #re_ShownCards       = re.compile("^Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \(%(CUR)s(?P<POT>[.\d]+)\)) with (?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$" % substitutions, re.MULTILINE)
    #re_CollectPot       = re.compile(r"Seat (?P<SEAT>[0-9]+): %(PLYR)s %(BRKTS)s(collected|showed \[.*\] and (won|collected)) \(?%(CUR)s(?P<POT>[,.\d]+)\)?(, mucked| with.*|)" %  substitutions, re.MULTILINE)
    re_CollectPot       = re.compile(r"Seat (?P<SEAT>[0-9]+):\s%(PLYR)s:\sbet\s(€|$|£)(?P<BET>[,.\d]+)\sand\swon\s(€|$|£)[\.0-9]+\W\snet\sresult:\s(€|$|£)(?P<POT>[,.\d]+)" %  substitutions, re.MULTILINE)
    #Vinsand88 cashed out the hand for $2.19 | Cash Out Fee $0.02
    re_CollectPot2      = re.compile(u"%(PLYR)s (collected|cashed out the hand for) %(CUR)s(?P<POT>[,.\d]+)" %  substitutions, re.MULTILINE)
    re_CashedOut        = re.compile(r"cashed\sout\sthe\shand")
    re_WinningRankOne   = re.compile(u"%(PLYR)s wins the tournament and receives %(CUR)s(?P<AMT>[,\.0-9]+) - congratulations!$" %  substitutions, re.MULTILINE)
    re_WinningRankOther = re.compile(u"%(PLYR)s finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place and received %(CUR)s(?P<AMT>[,.0-9]+)\.$" %  substitutions, re.MULTILINE)
    re_RankOther        = re.compile(u"%(PLYR)s finished the tournament in (?P<RANK>[0-9]+)(st|nd|rd|th) place$" %  substitutions, re.MULTILINE)
    re_Cancelled        = re.compile('Hand\scancelled', re.MULTILINE)
    re_Uncalled         = re.compile('Uncalled\sbet\s\(%(CUR)s(?P<BET>[,.\d]+)\)\sreturned\sto' %  substitutions, re.MULTILINE)
    #APTEM-89 wins the $0.27 bounty for eliminating Hero
    #ChazDazzle wins the 22000 bounty for eliminating berkovich609
    #JKuzja, vecenta split the $50 bounty for eliminating ODYSSES
    re_Bounty           = re.compile(u"%(PLYR)s (?P<SPLIT>split|wins) the %(CUR)s(?P<AMT>[,\.0-9]+) bounty for eliminating (?P<ELIMINATED>.+?)$" %  substitutions, re.MULTILINE)
    #Amsterdam71 wins $19.90 for eliminating MuKoJla and their own bounty increases by $19.89 to $155.32
    #Amsterdam71 wins $4.60 for splitting the elimination of Frimble11 and their own bounty increases by $4.59 to $41.32    
    #Amsterdam71 wins the tournament and receives $230.36 - congratulations!
    re_Progressive      = re.compile(u"""
                        %(PLYR)s\swins\s%(CUR)s(?P<AMT>[,\.0-9]+)\s
                        for\s(splitting\sthe\selimination\sof|eliminating)\s(?P<ELIMINATED>.+?)\s
                        and\stheir\sown\sbounty\sincreases\sby\s%(CUR)s(?P<INCREASE>[\.0-9]+)\sto\s%(CUR)s(?P<ENDAMT>[\.0-9]+)$"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    re_Rake             = re.compile(u"""
                        Total\spot\s%(CUR)s(?P<POT>[,\.0-9]+)(.+?)?\s\|\sRake\s%(CUR)s(?P<RAKE>[,\.0-9]+)"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)
    
    re_STP             = re.compile(u"""
                        STP\sadded:\s%(CUR)s(?P<AMOUNT>[,\.0-9]+)"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)

    def compilePlayerRegexs(self,  hand):
        players = set([player[1] for player in hand.players])
        if not players <= self.compiledPlayers: # x <= y means 'x is subset of y'
            self.compiledPlayers = players
            player_re = "(?P<PNAME>" + "|".join(map(re.escape, players)) + ")"
            subst = {
                'PLYR': player_re,
                'BRKTS': r'(\(button\) |\(small\sblind\) |\(big\blind\) |\(button\) \(small\sblind\) |\(button\) \(big\sblind\) )?',
                'CUR': u"(\$|\xe2\x82\xac|\u20ac||\£|)"
            }

            self.re_HeroCards = re.compile(r"Dealt\sto\s%(PLYR)s(?: \[(?P<OLDCARDS>.+?)\])?( \[(?P<NEWCARDS>.+?)\])" % subst, re.MULTILINE)
            self.re_ShownCards = re.compile("Seat\s(?P<SEAT>[0-9]+):\s%(PLYR)s\s%(BRKTS)s(?P<SHOWED>showed|mucked)\s\[(?P<CARDS>.*)\](\sand\s(lost|(won|collected)\s \(%(CUR)s(?P<POT>[,\.\d]+)\))\swith\s(?P<STRING>.+?)(,\sand\s(won\s\(%(CUR)s[\.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$" % subst, re.MULTILINE)   

    def readSupportedGames(self):
        return [["ring", "hold", "nl"],
                ["ring", "hold", "pl"],
                ["ring", "hold", "fl"],
                ["ring", "hold", "pn"],

                ["ring", "stud", "fl"],

                ["ring", "draw", "fl"],
                ["ring", "draw", "pl"],
                ["ring", "draw", "nl"],

                ["tour", "hold", "nl"],
                ["tour", "hold", "pl"],
                ["tour", "hold", "fl"],
                ["tour", "hold", "pn"],

                ["tour", "stud", "fl"],
                
                ["tour", "draw", "fl"],
                ["tour", "draw", "pl"],
                ["tour", "draw", "nl"],
                ]

    def determineGameType(self, handText):
        info = {}
        m = self.re_GameInfo.search(handText)
        if not m:
            tmp = handText[0:200]
            log.error(("UnibetToFpdb.determineGameType: '%s'") % tmp)
            raise FpdbParseError

        mg = m.groupdict()
        if 'LIMIT' in mg:
            #print(mg['LIMIT'])
            if mg['LIMIT'] == 'NL':
                info['limitType'] = self.limits['No Limit']
            elif mg['LIMIT'] == 'PL':
                info['limitType'] = self.limits['Pot Limit']

            #info['limitType'] = self.limits[mg['LIMIT']]
        if 'GAME' in mg:
            print(mg['GAME'])
            if mg['GAME'] == 'No Limit Hold\'Em Banzai':          
                info['base']  = 'hold'
                info['category']  = 'holdem'
                info['type']  = 'ring'  
                info['split'] = False
            elif mg['GAME'] == 'Pot Limit Omaha':
                info['base']  = 'hold'
                info['category']  = 'omahahi'
                info['type']  = 'ring' 
                info['split'] = False
            #(info['base'], info['category']) = self.games[mg['GAME']]
        if 'SB' in mg and mg['SB'] is not None:
            info['sb'] = mg['SB']
        if 'BB' in mg and mg['BB'] is not None:
            info['bb'] = mg['BB']
        if 'BUB' in mg and mg['BUB'] is not None:
            info['sb'] = '0'
            info['bb'] = mg['BUB']
        if 'CURRENCY1' in mg and mg['CURRENCY1'] is not None:
            info['currency'] = self.currencies[mg['CURRENCY1']]
        elif 'CURRENCY' in mg:
            info['currency'] = self.currencies[mg['CURRENCY']]
        
        # if 'Zoom' in mg['TITLE'] or 'Rush' in mg['TITLE']:
        #     info['fast'] = True
        # else:
        #     info['fast'] = False
        # if 'Home' in mg['TITLE']:
        #     info['homeGame'] = True
        # else:
        #     info['homeGame'] = False
        # if 'CAP' in mg and mg['CAP'] is not None:
        #     info['buyinType'] = 'cap'
        # else:
        #     info['buyinType'] = 'regular'
        # if 'SPLIT' in mg and mg['SPLIT'] == 'Split':
        #     info['split'] = True
        # else:
        #     info['split'] = False
        # if 'SITE' in mg:
        #     if mg['SITE'] == 'PokerMaster':
        #         self.sitename = "PokerMaster"
        #         self.siteId   = 25 
        #         m1  = self.re_HandInfo.search(handText,re.DOTALL)
        #         if m1 and '_5Cards_' in m1.group('TABLE'):
        #             info['category'] = '5_omahahi'
        #     elif mg['SITE'] == 'Run It Once Poker':
        #         self.sitename = "Run It Once Poker"
        #         self.siteId   = 26
        #     elif mg['SITE'] == 'BetOnline':
        #         self.sitename = 'BetOnline'
        #         self.siteId = 19
        #     elif mg['SITE'] == 'PokerBros':
        #         self.sitename = 'PokerBros'
        #         self.siteId = 29
                
        # if 'TOURNO' in mg and mg['TOURNO'] is None:
        #     info['type'] = 'ring'
        # else:
        #     info['type'] = 'tour'
        #     if 'ZOOM' in mg['TOUR']:
        #         info['fast'] = True
        
        if info.get('currency') in ('T$', None) and info['type']=='ring':
            info['currency'] = 'play'

        if info['limitType'] == 'fl' and info['bb'] is not None:
            if info['type'] == 'ring':
                try:
                    info['sb'] = self.Lim_Blinds[mg['BB']][0]
                    info['bb'] = self.Lim_Blinds[mg['BB']][1]
                except KeyError:
                    tmp = handText[0:200]
                    log.error(("UnibetToFpdb.determineGameType: Lim_Blinds has no lookup for '%s' - '%s'") % (mg['BB'], tmp))
                    raise FpdbParseError
            else:
                info['sb'] = str((Decimal(mg['SB'])/2).quantize(Decimal("0.01")))
                info['bb'] = str(Decimal(mg['SB']).quantize(Decimal("0.01")))    
        log.info(("UnibetToFpdb.determineGameType: '%s'") % info)
        return info

    def readHandInfo(self, hand):
        #First check if partial
        if hand.handText.count('*** Summary ***')!=1:
            raise FpdbHandPartial(("Hand is not cleanly split into pre and post Summary"))
        
        info = {}
        m  = self.re_HandInfo.search(hand.handText,re.DOTALL)
        m2 = self.re_GameInfo.search(hand.handText)
        if m is None or m2 is None:
            tmp = hand.handText[0:200]
            log.error(("UnibetToFpdb.readHandInfo: '%s'") % tmp)
            raise FpdbParseError

        info.update(m.groupdict())
        info.update(m2.groupdict())

        log.debug("readHandInfo: %s" % info)
        for key in info:
            if key == 'DATETIME':
                #2008/11/12 10:00:48 CET [2008/11/12 4:00:48 ET] # (both dates are parsed so ET date overrides the other)
                #2008/08/17 - 01:14:43 (ET)
                #2008/09/07 06:23:14 ET                
                datetimestr = "00:00:00 2000/01/01"  # default used if time not found
                if self.siteId == 26:
                    m2 = self.re_DateTime2.finditer(info[key])
                    
                else:
                    m1 = self.re_DateTime1.finditer(info[key])
                    for a in m1:
                        datetimestr1 = str(a.group('H'))+":"+str(a.group('MIN'))+":"+str(a.group('S'))
                        datetimestr2 = str(a.group('Y'))+"/"+str(a.group('M'))+"/"+str(a.group('D'))
                        datetimestr = datetimestr2+" "+datetimestr1
                        print('datetimestr',datetimestr)
                        #tz = a.group('TZ')  # just assume ET??
                        #print ("   tz = ", tz, " datetime =", datetimestr)
                    hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S") # also timezone at end, e.g. " ET"
                    #hand.startTime = HandHistoryConverter.changeTimezone(hand.startTime, "ET", "UTC")
                    
            if key == 'HID':
                hand.handid = info[key]
            if key == 'TOURNO':
                hand.tourNo = info[key]
            if key == 'BUYIN':
                if hand.tourNo!=None:
                    print ("DEBUG: info['BUYIN']: %s" % info['BUYIN'])
                    print ("DEBUG: info['BIAMT']: %s" % info['BIAMT'])
                    print ("DEBUG: info['BIRAKE']: %s" % info['BIRAKE'])
                    print ("DEBUG: info['BOUNTY']: %s" % info['BOUNTY'])
                    if info[key].strip() == 'Freeroll':
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "FREE"
                    elif info[key].strip() == '':
                        hand.buyin = 0
                        hand.fee = 0
                        hand.buyinCurrency = "NA"
                    else:
                        if info[key].find("$")!=-1:
                            hand.buyinCurrency="USD"
                        elif info[key].find(u"£")!=-1:
                            hand.buyinCurrency="GBP"
                        elif info[key].find(u"€")!=-1:
                            hand.buyinCurrency="EUR"
                        elif info[key].find(u"₹")!=-1:
                            hand.buyinCurrency="INR"
                        elif info[key].find(u"¥")!=-1:
                            hand.buyinCurrency="CNY"
                        elif info[key].find("FPP")!=-1:
                            hand.buyinCurrency="PSFP"
                        elif info[key].find("SC")!=-1:
                            hand.buyinCurrency="PSFP"
                        elif re.match("^[0-9+]*$", info[key].strip()):
                            hand.buyinCurrency="play"
                        else:
                            #FIXME: handle other currencies, play money
                            log.error(("UnibetToFpdb.readHandInfo: Failed to detect currency.") + " Hand ID: %s: '%s'" % (hand.handid, info[key]))
                            raise FpdbParseError

                        info['BIAMT'] = info['BIAMT'].strip(u'$€£FPPSC₹')
                        
                        if hand.buyinCurrency!="PSFP":
                            if info['BOUNTY'] != None:
                                # There is a bounty, Which means we need to switch BOUNTY and BIRAKE values
                                tmp = info['BOUNTY']
                                info['BOUNTY'] = info['BIRAKE']
                                info['BIRAKE'] = tmp
                                info['BOUNTY'] = info['BOUNTY'].strip(u'$€£₹') # Strip here where it isn't 'None'
                                hand.koBounty = int(100*Decimal(info['BOUNTY']))
                                hand.isKO = True
                            else:
                                hand.isKO = False

                            info['BIRAKE'] = info['BIRAKE'].strip(u'$€£₹')

                            hand.buyin = int(100*Decimal(info['BIAMT'])) + hand.koBounty
                            hand.fee = int(100*Decimal(info['BIRAKE']))
                        else:
                            hand.buyin = int(100*Decimal(info['BIAMT']))
                            hand.fee = 0
                    if 'Zoom' in info['TITLE'] or 'Rush' in info['TITLE']:
                        hand.isFast = True
                    else:
                        hand.isFast = False
                    if 'Home' in info['TITLE']:
                        hand.isHomeGame = True
                    else:
                        hand.isHomeGame = False
            if key == 'LEVEL':
                hand.level = info[key]       
            if key == 'SHOOTOUT' and info[key] != None:
                hand.isShootout = True
            if key == 'TABLE':
                hand.tablename = info[key]
                # if info['TOURNO'] is not None and info['HIVETABLE'] is not None:
                #     hand.tablename = info['HIVETABLE']
                # elif hand.tourNo != None and len(tablesplit)>1:
                #     hand.tablename = tablesplit[1]
                # else:
                #     hand.tablename = info[key]
            if key == 'BUTTON':
                hand.buttonpos = info[key]
            if key == 'MAX' and info[key] != None:
                hand.maxseats = int(info[key])
        log.info("readHandInfo.hand: %s" % hand)        
        if self.re_Cancelled.search(hand.handText):
            raise FpdbHandPartial(("Hand '%s' was cancelled.") % hand.handid)
    
    def readButton(self, hand):
        pre, post = hand.handText.split('*** Summary ***')
        m = self.re_Button.search(hand.handText)
        m2 = self.re_PlayerInfo.finditer(pre)
        if m:
            for b in m2:
                if b.group('PNAME') == m.group('BUTTON'):
                   hand.buttonpos = int(b.group('SEAT'))
                   log.info("readHandInfo.readbutton: %s" % int(b.group('SEAT')))
        else:
            log.info('readButton: ' + ('not found'))

    def readPlayerStacks(self, hand):
        pre, post = hand.handText.split('*** Summary ***')
        m = self.re_PlayerInfo.finditer(pre)
        m2 = self.re_PlayerInfo2.finditer(pre)
        for b in m2:
            
            for a in m:
               
                if a.group('PNAME') == b.group('SITOUT'):
                        hand.addPlayer(
                            int(a.group('SEAT')), 
                            a.group('PNAME'), 
                            self.clearMoneyString(a.group('CASH')), 
                            None, 
                            int(a.group('SEAT'))
                    #self.clearMoneyString(a.group('BOUNTY'))
                    )   
                        log.info("readPlayerStacks: '%s' '%s' '%s' '%s' '%s'" % int(a.group('SEAT')), a.group('PNAME'), self.clearMoneyString(a.group('CASH')), None, int(a.group('SEAT')))
                        break
                elif a.group('PNAME') != b.group('SITOUT'):
                    hand.addPlayer(
                            int(a.group('SEAT')), 
                            a.group('PNAME'), 
                            self.clearMoneyString(a.group('CASH')), 
                            None,
                    
                       )
                    log.info("readPlayerStacks: '%s' '%s' '%s' '%s' '%s'" % int(a.group('SEAT')), a.group('PNAME'), self.clearMoneyString(a.group('CASH')), None)
        


    def markStreets(self, hand):

        # There is no marker between deal and draw in Stars single draw games
        #  this upsets the accounting, incorrectly sets handsPlayers.cardxx and 
        #  in consequence the mucked-display is incorrect.
        # Attempt to fix by inserting a DRAW marker into the hand text attribute
        # PREFLOP = ** Dealing down cards **
        # This re fails if,  say, river is missing; then we don't get the ** that starts the river.
        m =  re.search(r"\*\*\*\sHole\scards\s\*\*\*(?P<PREFLOP>(.+(?P<FLOPET>\[\S\S\]))?.+(?=\*\*\*\sFlop\s\*\*\*)|.+)"
                   r"(\*\*\*\sFlop\s\*\*\*(?P<FLOP>(\[\S\S\s])?\[(\S\S?)?\S\S\S\S\].+(?=\*\*\*\sTurn\s\*\*\*)|.+))?"
                   r"(\*\*\*\sTurn\s\*\*\*\s\[\S\S \S\S \S\S\](?P<TURN>\[\S\S\].+(?=\*\*\*\sRiver\s\*\*\*)|.+))?"
                   r"(\*\*\*\sRiver\s\*\*\*\s\[\S\S \S\S \S\S\]?\s\[?\S\S\]\s(?P<RIVER>\[\S\S\].+))?", hand.handText,re.DOTALL)
        hand.addStreets(m)
        log.info("markStreets.handaddstreets: %s" % hand)

    def readCommunityCards(self, hand, street): # street has been matched by markStreets, so exists in this hand
        m = self.re_Board.search(hand.streets[street])
        if m:
            hand.setCommunityCards(street, m.group('CARDS').split(' '))
            log.info("readCommunityCards.setCommunityCards:' %s' " % street)
        else:   
            log.error("readCommunityCards.setCommunityCards: none")
               

        
    def readAntes(self, hand):
        log.debug(("reading antes"))
        m = self.re_Antes.finditer(hand.handText)
        for player in m:
            logging.info("hand.addAnte(%s,%s)" %(player.group('PNAME'), player.group('ANTE')))
            hand.addAnte(player.group('PNAME'), self.clearMoneyString(player.group('ANTE')))
    
    def readBringIn(self, hand):
        m = self.re_BringIn.search(hand.handText,re.DOTALL)
        if m:
            logging.info("readBringIn: %s for %s" %(m.group('PNAME'),  m.group('BRINGIN')))
            hand.addBringIn(m.group('PNAME'),  self.clearMoneyString(m.group('BRINGIN')))
        
    def readBlinds(self, hand):
        liveBlind = True
        for a in self.re_PostSB.finditer(hand.handText):
            if liveBlind:
                hand.addBlind(a.group('PNAME'), 'small blind', self.clearMoneyString(a.group('SB')))
                logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('SB'))))
                liveBlind = False
            else:
                names = [p[1] for p in hand.players]
                if "Big Blind" in names or "Small Blind" in names or "Dealer" in names:
                    hand.addBlind(a.group('PNAME'), 'small blind', self.clearMoneyString(a.group('SB')))
                    logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('SB'))))
                else:
                    # Post dead blinds as ante
                    hand.addBlind(a.group('PNAME'), 'secondsb', self.clearMoneyString(a.group('SB')))
                    logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('SB'))))
        for a in self.re_PostBB.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'big blind', self.clearMoneyString(a.group('BB')))
            logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('BB'))))
        for a in self.re_PostBoth.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'both', self.clearMoneyString(a.group('SBBB')))
            logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('SBBB'))))

        for a in self.re_PostStraddle.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'straddle', self.clearMoneyString(a.group('STRADDLE')))
            logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('STRADDLE'))))
        for a in self.re_PostBUB.finditer(hand.handText):
            hand.addBlind(a.group('PNAME'), 'button blind', self.clearMoneyString(a.group('BUB')))
            logging.info("readBlinds: '%s' for '%s'" %(a.group('PNAME'),  self.clearMoneyString(a.group('BUB'))))

    def readHoleCards(self, hand):
#    streets PREFLOP, PREDRAW, and THIRD are special cases beacause
#    we need to grab hero's cards
        for street in ('PREFLOP', 'DEAL'):
            if street in hand.streets.keys():
                print(street)
                m = self.re_HeroCards.finditer(hand.streets[street])
                print(m)
                for found in m:
#                    if m == None:
#                        hand.involved = False
#                    else:
                    hand.hero = found.group('PNAME')
                    logging.info("readHoleCards: '%s'" %(found.group('PNAME')))
                    if 'cards' not in found.group('NEWCARDS'):
                        newcards = found.group('NEWCARDS').split(' ')
                        hand.addHoleCards(street, hand.hero, closed=newcards, shown=False, mucked=False, dealt=True)





    def readAction(self, hand, street):
        if hand.gametype['split'] and street in hand.communityStreets:
            s = street + '2'
        else:
            s = street
        if not hand.streets[s]:
            return
        m = self.re_Action.finditer(hand.streets[s])
        for action in m:
            acts = action.groupdict()
            log.error("DEBUG: %s acts: %s" % (street, acts))
            if action.group('ATYPE') == ' folds':
                hand.addFold( street, action.group('PNAME'))
            elif action.group('ATYPE') == ' checks':
                hand.addCheck( street, action.group('PNAME'))
            elif action.group('ATYPE') == ' calls':
                hand.addCall( street, action.group('PNAME'), self.clearMoneyString(action.group('BET')) )
            elif action.group('ATYPE') == ' raises':
                if action.group('BETTO') is not None:
                    hand.addRaiseTo( street, action.group('PNAME'), self.clearMoneyString(action.group('BETTO')) )
                elif action.group('BET') is not None:
                   hand.addCallandRaise( street, action.group('PNAME'), self.clearMoneyString(action.group('BET')) ) 
            elif action.group('ATYPE') == ' bets':
                hand.addBet( street, action.group('PNAME'), self.clearMoneyString(action.group('BET')) )
            elif action.group('ATYPE') == ' discards':
                hand.addDiscard(street, action.group('PNAME'), action.group('BET'), action.group('CARDS'))
            elif action.group('ATYPE') == ' stands pat':
                hand.addStandsPat( street, action.group('PNAME'), action.group('CARDS'))
            else:
                log.info(("DEBUG:") + " " + ("Unimplemented %s: '%s' '%s'") % ("readAction", action.group('PNAME'), action.group('ATYPE')))


    def readShowdownActions(self, hand):
      for shows in self.re_ShowdownAction.finditer(hand.handText):            
            cards = shows.group('CARDS').split(' ')
            logging.debug("hand.readShowdownActions('%s','%s')" % cards, shows.group('PNAME'))
            hand.addShownCards(cards, shows.group('PNAME')) 
            logging.info("hand.readShowdownActions('%s','%s')" % cards, shows.group('PNAME'))
     
    def readTourneyResults(self, hand):
        """Reads knockout bounties and add them to the koCounts dict"""
        pass      

    def readCollectPot(self,hand):
        hand.setUncalledBets(True)
        for m in self.re_CollectPot.finditer(hand.handText):
            
            hand.addCollectPot(player=m.group('PNAME'), pot=str(Decimal((m.group('POT')))))
            logging.info("readCollectPot: '%s' for '%s'" %(m.group('PNAME'),  str(Decimal((m.group('POT'))))))
            

    def readShownCards(self,hand):
        pass
            

    @staticmethod
    def getTableTitleRe(type, table_name=None, tournament = None, table_number=None):
        pass

