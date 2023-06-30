from ast import Param
from bs4 import BeautifulSoup
import aiohttp 
import asyncio

###http://www.propokertools.com/pql/show?
# query=select%20avg(equity(aces%2C%20river))%20as%20aces_equity%0Afrom%20game%3D%22holdem%22%2C%20aces%3D%22AA%22%2C%20player2%3D%22**%22

class Simulation:
    def __init__(self, query) -> None:
        self.query = query
    
    async def make_request(self):
        self.url = 'http://www.propokertools.com/pql/show?'
        #query = 'select avg(equity(aces, river)) as aces_equity from game="holdem", aces="AA", player2="**"'
        self.params = {'query': self.query} 
        print(self.params) 
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, params=self.params) as resp:
                print(resp.status)
                print(await resp.text())    
       
                html_doc= await resp.text()
                print(html_doc)

                s = BeautifulSoup(html_doc, 'html.parser').table
                h, [_, *d] = [i.text for i in s.tr.find_all('th')], [[i.text for i in b.find_all('td')] for b in s.find_all('tr')]
                result = [dict(zip(h, i)) for i in d]
        
                print (type(result))
                print(result)
                return result

sim1 = Simulation()
asyncio.run(sim1.make_request())