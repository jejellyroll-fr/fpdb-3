from unittest import result
from ploev.calc import *
from ploev.ppt import *

# use https://github.com/vyvojer/ploev python lib for Pokerprotools odds oracle
# until the end of 2022 the pokerprotools servers will be down, a public key is provided by the author Dan (aka nerdytenor/bachfan) to use the desktop version
# use pokerprotools for odds calculation
# g = oh5 - 5 card omaha
# g = o85 - 5 card omaha Hi/Lo
# g = he - holdem
# g = oh - omaha
# g = o8 - omaha Hi/Lo
# g = rz - razz
# g = st - stud
# g = s8 - stud Hi/Lo

#'s': 'generic'

#'d': 'dead card'

#'b': 'board' flop turn river

#'h1' to h6 : 'hand' or range

# use pql


odds_oracle = OddsOracle()
pql = """
            select count(inRange(PLAYER_1,'AA')),
              count(inRange(PLAYER_1,'AK,KK'))
            from game='omahahi', syntax='Generic',
                 board='Ad Ks 3s',
                 PLAYER_1='10%',
                 PLAYER_2='Qs Ts Jd 2d'
"""
test = odds_oracle.pql(pql)

print(test.results_list)
print(type(test))

#odd1 = OddsCalc('oh','As8s4d9d','AK','89','','','','','')        
#odd1.calcBaseHoldem()