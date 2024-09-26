# -*- coding: utf-8 -*-
from __future__ import print_function

import urllib.request, urllib.error, urllib.parse, re
import pprint
from bs4 import BeautifulSoup


playername = ''

if playername == '':
    print(("You need to manually enter the playername"))
    exit(0)

page = urllib.request.urlopen("http://www.pocketfives.com/poker-scores/%s/" %playername)
soup = BeautifulSoup(page)

results = []

for table in soup.findAll('table'):
#    print "Found %s" % table
    for row in table.findAll('tr'):
        tmp = []
        for col in row.findAll('td'):
            tmp = tmp + [col.string]
            #print col.string
        if len(tmp) > 3 and tmp[2] != None:
            results = results + [tmp]

cols =  ['TOURNAMENT', 'SITE', 'DATE', 'PRIZEPOOL', 'BUY-IN', 'PLACE', 'WON']

pp = pprint.PrettyPrinter(indent=4)

for result in results:
    print("Site: %s Date: %s\tPrizepool: %s\tBuyin: %s\tPosition: %s\tWon: %s" %(result[2], result[3], result[4], result[5], result[6], result[7]))

