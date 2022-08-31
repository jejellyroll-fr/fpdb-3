import requests
from bs4 import BeautifulSoup

#use pokerprotools for odds calculation
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

class OddsCalc:
    def __init__(self, game, dead, board, hero, vilain1, vilain2,vilain3,vilain4,vilain5) -> None:
  
        self.game = game
        self.board = board
        self.dead = dead
        self.hero= hero
        self.vilain1 = vilain1
        self.vilain2 = vilain2
        self.vilain3 = vilain3
        self.vilain4 = vilain4
        self.vilain5 = vilain5
       

    def calcBaseHoldem(self):
        url = 'http://www.propokertools.com/simulations/show?'
        params = {'g': self.game, 's': 'generic','d': self.dead, 'b': self.board ,'h1':  self.hero, 'h2': self.vilain1, 'h3': self.vilain2,'h4':  self.vilain3, 'h5': self.vilain4, 'h5': self.vilain5}
        response = requests.post(url, params=params)
        response.status_code
        html_doc= response.text
        print(html_doc)

        s = BeautifulSoup(html_doc, 'html.parser').table
        h, [_, *d] = [i.text for i in s.tr.find_all('th')], [[i.text for i in b.find_all('td')] for b in s.find_all('tr')]
        result = [dict(zip(h, i)) for i in d]
        
        print (type(result))
        return result

#odd1 = OddsCalc('oh','As8s4d9d','AK','89','','','','','')        
#odd1.calcBaseHoldem()