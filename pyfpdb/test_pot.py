from decimal_wrapper import Decimal
from Hand import Pot
import pytest


"""
Main functionalities:
The Pot class represents a pot in a poker game. It keeps track of the players who are still in the pot, the amount of money each player has committed to the pot, the common money in the pot, the antes, the total amount of money in the pot, and the side pots. It also provides methods for adding and removing players, adding money to the pot, and calculating the total amount of money in the pot.

"""

class TestPot:
    # Tests that calling end() updates the total, returned, and pots attributes with the correct values.
    def test_end(self):
        pot = Pot()
        pot.committed = {'player1': Decimal(10), 'player2': Decimal(20)}
        pot.common = {'player1': Decimal(5), 'player2': Decimal(0)}
        pot.stp = Decimal(0)
        pot.contenders = {'player1', 'player2'}
        pot.handid = 12345

        pot.end()

        assert pot.total == Decimal(25)
        assert pot.returned == {'player2': Decimal(10)}
        assert pot.pots == [(Decimal(20), {'player1', 'player2'})]

    # Tests that adding money to the pot updates the committed dictionary and adds the player to the contenders set.
    def test_addMoney(self):
        pot = Pot()
        pot.addPlayer('player1')
        pot.addPlayer('player2')

        pot.addMoney('player1', Decimal(10))
        pot.addMoney('player2', Decimal(20))

        assert pot.committed == {'player1': Decimal(10), 'player2': Decimal(20)}
        assert pot.contenders == {'player1', 'player2'}

    # Tests that removing a player from the pot deletes their entries from the committed, common, and antes dictionaries.
    def test_removePlayer(self):
        pot = Pot()
        pot.addPlayer('player1')
        pot.addPlayer('player2')

        pot.removePlayer('player1')

        assert 'player1' not in pot.committed
        assert 'player1' not in pot.common
        assert 'player1' not in pot.antes

    # Tests that marking the total at a street updates the streettotals dictionary with the correct value.
    def test_markTotal(self):
        pot = Pot()
        pot.addPlayer('player1')
        pot.addPlayer('player2')
        pot.committed = {'player1': Decimal(10), 'player2': Decimal(20)}
        pot.common = {'player1': Decimal(5), 'player2': Decimal(0)}
        pot.stp = Decimal(0)

        pot.markTotal('flop')

        assert pot.streettotals == {'flop': Decimal(35)}

    # Tests that getting the total at a street returns the correct value from the streettotals dictionary.
    def test_getTotalAtStreet(self):
        pot = Pot()
        pot.streettotals = {'flop': Decimal(35), 'turn': Decimal(50)}

        assert pot.getTotalAtStreet('flop') == Decimal(35)
        assert pot.getTotalAtStreet('turn') == Decimal(50)
        assert pot.getTotalAtStreet('river') == 0

    # Tests that adding a fold for a player removes them from the contenders set.
    def test_addFold(self):
        pot = Pot()
        pot.contenders = {'player1', 'player2', 'player3'}

        pot.addFold('player2')

        assert pot.contenders == {'player1', 'player3'}