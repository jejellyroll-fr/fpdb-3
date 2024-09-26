import requests
from bs4 import BeautifulSoup

#use pokerprotools for odds calculation

url = 'http://www.propokertools.com/simulations/show?'

# g = oh5 - 5 card omaha
# g = o85 - 5 card omaha Hi/Lo
# g = he - holdem
# g = oh - omaha
# g = o8 - omaha Hi/Lo
# g = rz - razz
# g = st - stud
# g = s8 - stud Hi/Lo

#'s': 'generic'

#'b': 'board' flop turn river

#'h1' to h6 : 'hand' or range


params = {'g': 'he', 's': 'generic', 'b': 'As8s4d9d' ,'h1':  'AA', 'h2': '67'}

response = requests.post(url, params=params)
response.status_code
html_doc= response.text

s = BeautifulSoup(html_doc, 'html.parser').table
h, [_, *d] = [i.text for i in s.tr.find_all('th')], [[i.text for i in b.find_all('td')] for b in s.find_all('tr')]
result = [dict(zip(h, i)) for i in d]
print(result)