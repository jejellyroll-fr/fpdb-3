# pokersim.py - Runs a Monte Carlo simulation of two Texas Hold'em hands
#               with user-specified (or random) community cards
#
# Work to be done:
# Add exhaustive search?
# Add input checking for user input
#   No duplicate cards or invalid input
# Add support for random rank, defined suit (and vice versa)
# Add support for random 'hand2' cards
# Add test cases
#
import argparse
import itertools
import random
import time

from numba import njit
import numpy as np


def readable_hand(cards):
    #
    # Returns a readable version of a set of cards
    #
    card_rank = {0: "2", 1: "3", 2: "4", 3: "5", 4: "6", 5: "7", 6: "8",
                 7: "9", 8: "T", 9: "J", 10: "Q", 11: "K", 12: "A", -1: "X"}
    card_suit = {0: "c", 1: "d", 2: "h", 3: "s", -1: "x"}
    return "".join(card_rank[i[0]] + card_suit[i[1]] for i in cards)


def hand_copy(cards):
    return list(cards)


def legal_hand(cards):
    return not any(cards.count(i) > 1 or cards == [-1, -1] for i in cards)


def valid_card(card):
    #
    # Returns True if card is a valid card in text format (rank in (A-2),
    #  suit in (c, d, h, s) or wildcard (Xx)
    # Returns False if card is invalid
    #
    return card[0] in (
        "X",
        "x",
        "A",
        "a",
        "K",
        "k",
        "Q",
        "q",
        "J",
        "j",
        "T",
        "t",
        "9",
        "8",
        "7",
        "6",
        "5",
        "4",
        "3",
        "2",
    ) and card[1] in ("x", "X", "c", "C", "d", "D", "h", "H", "s", "S")


def hand_to_numeric(cards):
    #
    # Converts alphanumeric hand to numeric values for easier comparisons
    # Also sorts cards based on rank
    #
    card_rank = {"2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "8": 6,
                 "9": 7, "T": 8, "J": 9, "Q": 10, "K": 11, "A": 12, "X": -1,
                         "t": 8, "j": 9, "q": 10, "k": 11, "a": 12, "x": -1}
    card_suit = {"c": 0, "C": 0, "d": 1, "D": 1, "h": 2, "H": 2,
                 "s": 3, "S": 3, "x": -1, "X": -1}
    result = [
        [card_rank[cards[i * 2]], card_suit[cards[i * 2 + 1]]]
        for i in range(len(cards) // 2 + len(cards) % 2)
    ]
    result.sort()
    result.reverse()
    return result


def check_flush(hand):
    #
    # Returns True if hand is a Flush, otherwise returns False
    #
    hand_suit = [hand[0][1], hand[1][1], hand[2][1], hand[3][1], hand[4][1]]
    return any(hand_suit.count(i) == 5 for i in range(4))


def check_straight(hand):
    # Return True if hand is a Straight, otherwise returns False
    if hand[0][0] == (hand[1][0] + 1) == (hand[2][0] + 2) == (hand[3][0] + 3)\
            == (hand[4][0] + 4):
        return True
    elif (hand[0][0] == 12) and (hand[1][0] == 3) and (hand[2][0] == 2)\
            and (hand[3][0] == 1) and (hand[4][0] == 0):
        return True
    return False


def check_straightflush(hand):
    # Return True if hand is a Straight Flush, otherwise returns False
    return bool(check_flush(hand) and check_straight(hand))


def check_fourofakind(hand):
    # Return True if hand is Four-of-a-Kind, otherwise returns False
    # Also returns rank of four of a kind card and rank of fifth card
    # (garbage value if no four of a kind)
    hand_rank = [hand[0][0], hand[1][0], hand[2][0], hand[3][0], hand[4][0]]
    for quad_card in range(13):
        if hand_rank.count(quad_card) == 4:
            for kicker in range(13):
                if hand_rank.count(kicker) == 1:
                    return True, quad_card, kicker
    return False, 13, 13


def check_fullhouse(hand):
    # Return True if hand is a Full House, otherwise returns False
    # Also returns rank of three of a kind card and two of a kind card
    # (garbage values if no full house)
    hand_rank = [hand[0][0], hand[1][0], hand[2][0], hand[3][0], hand[4][0]]
    for trip_card in range(13):
        if hand_rank.count(trip_card) == 3:
            for pair_card in range(13):
                if hand_rank.count(pair_card) == 2:
                    return True, trip_card, pair_card
    return False, 13, 13


def check_threeofakind(hand):
    # Return True if hand is Three-of-a-Kind, otherwise returns False
    # Also returns rank of three of a kind card and remaining two cards
    # (garbage values if no three of a kind)
    hand_rank = [card[0] for card in hand]
    for trip_card in range(13):
        if hand_rank.count(trip_card) == 3:
            remaining_cards = sorted(set(hand_rank) - {trip_card})
            return True, trip_card, remaining_cards
    return False, 13, [13, 13]


def check_twopair(hand):
    # Return True if hand is Two Pair, otherwise returns False
    # Also returns ranks of paired cards and remaining card
    # (garbage values if no two pair)
    hand_rank = [hand[0][0], hand[1][0], hand[2][0], hand[3][0], hand[4][0]]
    pair_ranks = []
    kicker_rank = None
    for rank in set(hand_rank):
        if hand_rank.count(rank) == 2:
            pair_ranks.append(rank)
        elif hand_rank.count(rank) == 1:
            kicker_rank = rank
    if len(pair_ranks) == 2:
        return True, sorted(pair_ranks, reverse=True), kicker_rank
    else:
        return False, [13, 13], 13




def check_onepair(hand):
    # Return True if hand is One Pair, otherwise returns False
    # Also returns ranks of paired cards and remaining three cards
    # (garbage values if no pair)
    hand_rank = [hand[0][0], hand[1][0], hand[2][0], hand[3][0], hand[4][0]]
    for pair_card in range(13):
        if hand_rank.count(pair_card) == 2:
            for kicker1 in range(13):
                if hand_rank.count(kicker1) == 1:
                    for kicker2 in range(kicker1 + 1, 13):
                        if hand_rank.count(kicker2) == 1:
                            for kicker3 in range(kicker2 + 1, 13):
                                if hand_rank.count(kicker3) == 1:
                                    return True, pair_card, \
                                        [kicker3, kicker2, kicker1]
    return False, 13, [13, 13, 13]


def highest_card(hand1, hand2):
    # Return 0 if hand1 is higher
    # Return 1 if hand2 is higher
    # Return 2 if equal
    hand1_rank = \
        [hand1[0][0], hand1[1][0], hand1[2][0], hand1[3][0], hand1[4][0]]
    hand2_rank = \
        [hand2[0][0], hand2[1][0], hand2[2][0], hand2[3][0], hand2[4][0]]
    #
    # Compare
    #
    if hand1_rank > hand2_rank:
        return 0
    elif hand1_rank < hand2_rank:
        return 1
    return 2


def highest_card_straight(hand1, hand2):
    # Return 0 if hand1 is higher
    # Return 1 if hand2 is higher
    # Return 2 if equal
    #
    # Compare second card first (to account for Ace low straights)
    # if equal, we could have Ace low straight, so compare first card.
    # If first card is Ace, that is the lower straight
    #
    if hand1[1][0] > hand2[1][0]:
        return 0
    elif hand1[1][0] < hand2[1][0]:
        return 1
    elif hand1[0][0] > hand2[0][0]:
        return 1
    elif hand1[0][0] < hand2[0][0]:
        return 0
    return 2


def compare_hands(hand1, hand2):
    #
    # Compare two hands
    # Return 0 if hand1 is better
    # Return 1 if hand2 is better
    # Return 2 if equal
    #
    result1 = []
    result2 = []
    #
    # Check for straight flush
    #
    if check_straightflush(hand1):
        return (
            (highest_card_straight(hand1, hand2))
            if check_straightflush(hand2)
            else 0
        )
    elif check_straightflush(hand2):
            return 1
    #
    # Check for four of a kind
    #
    result1 = check_fourofakind(hand1)
    result2 = check_fourofakind(hand2)
    if result1[0] == 1:
        if result2[0] != 1:
            return 0
        if (
            result1[1] > result2[1]
            or result1[1] >= result2[1]
            and result1[2] > result2[2]
        ):
            return 0
        elif result1[1] < result2[1] or result1[2] < result2[2]:
            return 1
        else:
            return 2
    elif result2[0] == 1:
        return 1
    #
    # Check for full house
    #
    result1 = check_fullhouse(hand1)
    result2 = check_fullhouse(hand2)
    if result1[0] == 1:
        if result2[0] != 1:
            return 0
        if (
            result1[1] > result2[1]
            or result1[1] >= result2[1]
            and result1[2] > result2[2]
        ):
            return 0
        elif result1[1] < result2[1] or result1[2] < result2[2]:
            return 1
        else:
            return 2
    elif result2[0] == 1:
        return 1
    #
    # Check for flush
    #
    if check_flush(hand1):
        return (highest_card(hand1, hand2)) if check_flush(hand2) else 0
    elif check_flush(hand2):
        return 1
    #
    # Check for straight
    #
    if check_straight(hand1):
        return highest_card_straight(hand1, hand2) if check_straight(hand2) else 0
    elif check_straight(hand2):
        return 1
    #
    # Check for three of a kind
    #
    result1 = check_threeofakind(hand1)
    result2 = check_threeofakind(hand2)
    if result1[0] == 1:
        if result2[0] != 1:
            return 0
        if (
            result1[1] > result2[1]
            or result1[1] >= result2[1]
            and result1[2] > result2[2]
        ):
            return 0
        elif result1[1] < result2[1] or result1[2] < result2[2]:
            return 1
        else:
            return 2
    elif result2[0] == 1:
        return 1
    #
    # Check for two pair
    #
    result1 = check_twopair(hand1)
    result2 = check_twopair(hand2)
    if result1[0] == 1:
        if result2[0] != 1:
            return 0
        if (
            result1[1] > result2[1]
            or result1[1] >= result2[1]
            and result1[2] > result2[2]
        ):
            return 0
        elif result1[1] < result2[1] or result1[2] < result2[2]:
            return 1
        else:
            return 2
    elif result2[0] == 1:
        return 1
    #
    # Check for one pair
    #
    result1 = check_onepair(hand1)
    result2 = check_onepair(hand2)
    if result1[0] == 1:
        if result2[0] != 1:
            return 0
        if (
            result1[1] > result2[1]
            or result1[1] >= result2[1]
            and result1[2] > result2[2]
        ):
            return 0
        elif result1[1] < result2[1] or result1[2] < result2[2]:
            return 1
        else:
            return 2
    elif result2[0] == 1:
        return 1
    return (highest_card(hand1, hand2))


def best_five(hand, community):
    #
    # Takes hand and community cards in numeric form
    # Returns best five cards
    #
    currentbest = hand_copy(community)
    currentbest.sort()
    currentbest.reverse()
    #
    # Compare current best to five cards including only one player card
    #
    for m, n in itertools.product(range(2), range(5)):
        comparehand = hand_copy(community)
        comparehand[n] = hand[m]
        comparehand.sort()
        comparehand.reverse()
        if compare_hands(currentbest, comparehand) == 1:
            currentbest = hand_copy(comparehand)
    #
    # Compare current best to five cards including both player cards
    #
    for m in range(5):
        for n in range(m + 1, 5):
            comparehand = hand_copy(community)
            comparehand[m] = hand[0]
            comparehand[n] = hand[1]
            comparehand.sort()
            comparehand.reverse()
            if compare_hands(currentbest, comparehand) == 1:
                currentbest = hand_copy(comparehand)
    return currentbest





def MCSim(iterations, community, hand1, hand2  ):
    start = time.time()
    handnum1 = hand_to_numeric(hand1)
    handnum2 = hand_to_numeric(hand2)
    # Initialize counters
    totals = [0, 0, 0]
    # Monte Carlo Simulation
    for _ in range(iterations):
        community_original = hand_to_numeric(community)

        community_temp = community_original[:]
        for i in range(len(community_temp)):
            if community_temp[i][0] == -1:
                community_temp[i] = [random.randint(0, 12),
                                 random.randint(0, 3)]
        
        best_hand1 = best_five(handnum1, community_temp)
        best_hand2 = best_five(handnum2, community_temp)
        totals[compare_hands(best_hand1, best_hand2)] += 1
    end = time.time()
    elapsed = end - start
    print(elapsed)
    # Print results
    print ("Total Hands: %i" % (iterations))
    print ("Hand1: %i Hand2: %i Ties: %i" % (totals[0], totals[1], totals[2]))
    print ("Hand1: %.2f%% Hand2: %.2f%% Ties: %.2f%%" % \
        (100 * round((totals[0] / (iterations + 0.0)), 4),
         100 * round((totals[1] / (iterations + 0.0)), 4),
         100 * round((totals[2] / (iterations + 0.0)), 4)))

MCSim(10000, "XxXxXxXxXx", "AsAh", "KsKh")

