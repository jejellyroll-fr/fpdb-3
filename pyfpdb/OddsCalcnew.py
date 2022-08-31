from ploev.calc import *

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


odds_oracle = OddsOracle()
calc = Calc(odds_oracle)
test = calc.equity(players=['AcAd7h2c', 'JdTs9s8d'])
print(test)
#odd1 = OddsCalc('oh','As8s4d9d','AK','89','','','','','')        
#odd1.calcBaseHoldem()