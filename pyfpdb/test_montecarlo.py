import pytest

from montecarlo import check_threeofakind, check_twopair, check_onepair



def test_check_threeofakind():


    # Tests that the function correctly identifies the rank of the three of a kind card
    def test_three_of_a_kind_rank(self):
        hand = [('A', 'H'), ('A', 'D'), ('A', 'S'), ('K', 'C'), ('Q', 'H')]
        assert check_threeofakind(hand)[1] == 13

    # Tests that the function returns False when there is no three of a kind
    def test_no_three_of_a_kind(self):
        hand = [('A', 'H'), ('K', 'D'), ('Q', 'S'), ('J', 'C'), ('10', 'H')]
        assert check_threeofakind(hand)[0] == False

    # Tests that the function returns garbage values when there are four of a kind
    def test_four_of_a_kind(self):
        hand = [('A', 'H'), ('A', 'D'), ('A', 'S'), ('A', 'C'), ('Q', 'H')]
        assert check_threeofakind(hand)[1] != 0 and check_threeofakind(hand)[2] != 0

    # Tests that the function returns garbage values when there are five of a kind
    def test_five_of_a_kind(self):
        hand = [('A', 'H'), ('A', 'D'), ('A', 'S'), ('A', 'C'), ('A', 'H')]
        assert check_threeofakind(hand)[1] != 0 and check_threeofakind(hand)[2] != 0

    # Tests that the function correctly handles ties when two hands have three of a kind
    def test_tie(self):
        hand1 = [('A', 'H'), ('A', 'D'), ('A', 'C'), ('K', 'S'), ('Q', 'H')]
        hand2 = [('A', 'S'), ('A', 'C'), ('A', 'D'), ('K', 'H'), ('Q', 'S')]
        assert check_threeofakind(hand1)[1] == check_threeofakind(hand2)[1]

def test_check_twopairs():
    # Tests that function returns False and garbage values for a hand with no pairs
    def test_no_pairs(self):
        hand = [('2', 'H'), ('3', 'D'), ('5', 'C'), ('7', 'S'), ('K', 'H')]
        expected_result = (False, [13, 13], 13)
        assert check_twopair(hand) == expected_result

    # Tests that function returns False and garbage values for a hand with one pair
    def test_one_pair(self):
        hand = [('2', 'H'), ('2', 'D'), ('5', 'C'), ('7', 'S'), ('K', 'H')]
        expected_result = (False, [13, 13], 13)
        assert check_twopair(hand) == expected_result

    # Tests that function returns False and garbage values for a hand with four of a kind
    def test_four_of_a_kind(self):
        hand = [('2', 'H'), ('2', 'D'), ('2', 'C'), ('2', 'S'), ('K', 'H')]
        expected_result = (False, [13, 13], 13)
        assert check_twopair(hand) == expected_result

    # Tests that function returns True  for a hand with two pairs
