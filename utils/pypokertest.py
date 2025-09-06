#
# Copyright (C) 2007, 2008 Loic Dachary <loic@dachary.org>
# Copyright (C) 2004, 2005, 2006 Mekensleep
#
# Mekensleep
# 24 rue vieille du temple
# 75004 Paris
#       licensing@mekensleep.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301, USA.
#
# Authors:
#  Loic Dachary <loic@dachary.org>
#
#
import sys

sys.path.insert(0, ".")
sys.path.insert(0, ".libs")

from pokereval import PokerEval

iterations_low = 100000
iterations_high = 200000

pokereval = PokerEval()

if pokereval.best_hand_value("hi", ["Ah", "Ad", "As", "Kh", "Ks"]) != 101494784:
    sys.exit(1)

if pokereval.string2card("2h") != 0:
    sys.exit(1)

pockets = [
    ["As", "Ad", "Ac", "Tc", "Ts", "2d", "5c"],
    ["Js", "Jc", "7s", "8c", "8d", "3c", "3h"],
    [255, 255],
]

pockets = [[22, 18, 21, 3, 41, 1, 30], [39, 255, 255, 15, 13, 17, 255]]


hand = ["Ac", "As", "Td", "7s", "7h", "3s", "2c"]
best_hand = pokereval.best_hand("hi", hand)

hand = ["Ah", "Ts", "Kh", "Qs", "Js"]
best_hand = pokereval.best_hand("hi", hand)

hand = ["2h", "Kh", "Qh", "Jh", "Th"]
best_hand = pokereval.best_hand("hi", hand)

hand = ["2s", "3s", "Jd", "Ks", "As", "4d", "5h", "7d", "9c"]
best_hand = pokereval.best_hand("hi", hand)

hand = ["As", "2s", "4d", "4s", "5c", "5d", "7s"]
best_hand = pokereval.best_hand("low", hand)

hand = ["As", "2s", "4d", "4s", "5c", "5d", "8s"]
best_hand = pokereval.best_hand("low", hand)

hand = ["7d", "6c", "5h", "4d", "As"]
best_hand = pokereval.best_hand("low", hand)

board = ["As", "4d", "5h", "7d", "9c"]
hand = ["2s", "Ts", "Jd", "Ks"]
best_hand = pokereval.best_hand("low", hand, board)

board = ["As", "4d", "6h", "7d", "3c"]
hand = ["2s", "5s", "Jd", "Ks"]
best_hand = pokereval.best_hand("low", hand, board)

board = ["Jc", "4c", "3c", "5c", "9c"]
hand = ["2c", "Ac", "5h", "9d"]
best_hand = pokereval.best_hand("hi", hand, board)

board = ["Jd", "9c", "Jc", "Tc", "2h"]
hand = ["2c", "4c", "Th", "6s"]
best_hand = pokereval.best_hand("low", hand, board)

board = ["Ks", "Jd", "7s", "4d", "Js"]
hand = ["2d", "6c", "Ac", "5c"]
best_hand = pokereval.best_hand("low", hand, board)

if len(sys.argv) > 2:
    pass

hand = ["As", "Ad"]

hand = ["Qc", "7d"]

pokereval = None
