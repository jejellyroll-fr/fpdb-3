#!/usr/bin/env python
from __future__ import annotations

"""HandHistory.py.

Parses HandHistory xml files and returns requested objects.
"""

from xml.parsers.expat import ExpatError

import defusedxml.ElementTree

from fpdb_3_legacy.loggingFpdb import get_logger

#    Copyright 2008-2011, Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################
#    Standard Library modules


log = get_logger("hand_history")


def _descendants(node, tag: str):
    if hasattr(node, "getElementsByTagName"):
        return list(node.getElementsByTagName(tag))
    return [child for child in node.iter(tag) if child is not node]


def _attribute(node, name: str) -> str:
    if hasattr(node, "getAttribute"):
        return node.getAttribute(name)
    return node.get(name, "")


def _direct_text(node) -> str:
    if hasattr(node, "childNodes"):
        return "".join(child.data for child in node.childNodes if child.nodeType == child.TEXT_NODE)
    return node.text or ""


class HandHistory:
    def __init__(self, xml_string, elements=("ALL")) -> None:
        try:
            root = defusedxml.ElementTree.fromstring(xml_string)
        except defusedxml.ElementTree.ParseError as exc:
            raise ExpatError(str(exc)) from exc
        if elements == ("ALL"):
            elements = ("BETTING", "AWARDS", "POSTS", "PLAYERS", "GAME")

        if "BETTING" in elements:
            self.BETTING = Betting(next(iter(root.iter("BETTING"))))
        if "AWARDS" in elements:
            self.AWARDS = Awards(next(iter(root.iter("AWARDS"))))
        if "POSTS" in elements:
            self.POSTS = Posts(next(iter(root.iter("POSTS"))))
        if "GAME" in elements:
            self.GAME = Game(next(iter(root.iter("GAME"))))
        if "PLAYERS" in elements:
            self.PLAYERS = {}
            p_n = next(iter(root.iter("PLAYERS")))
            for p in _descendants(p_n, "PLAYER"):
                a_player = Player(p)
                self.PLAYERS[a_player.name] = a_player


class Player:
    def __init__(self, node) -> None:
        self.name = _attribute(node, "NAME")
        self.seat = _attribute(node, "SEAT")
        self.stack = _attribute(node, "STACK")
        self.showed_hand = _attribute(node, "SHOWED_HAND")
        self.cards = _attribute(node, "CARDS")
        self.allin = _attribute(node, "ALLIN")
        self.sitting_out = _attribute(node, "SITTING_OUT")
        self.hand = _attribute(node, "HAND")
        self.start_cards = _attribute(node, "START_CARDS")

        if self.allin in ("", "0") or self.allin.upper() == "FALSE":
            self.allin = False
        else:
            self.allin = True

        if self.sitting_out in ("", "0") or self.sitting_out.upper() == "FALSE":
            self.sitting_out = False
        else:
            self.sitting_out = True

    def __str__(self) -> str:
        temp = f"{self.name}\n    seat = {self.seat}\n    stack = {self.stack}\n    cards = {self.cards}\n"
        temp = temp + f"    showed_hand = {self.showed_hand}\n    allin = {self.allin}\n"
        return temp + f"    hand = {self.hand}\n    start_cards = {self.start_cards}\n"


class Awards:
    def __init__(self, node) -> None:
        self.awards = []  # just an array of award objects
        for a in _descendants(node, "AWARD"):
            self.awards.append(Award(a))

    def __str__(self) -> str:
        return "".join(f"{a}\n" for a in self.awards)


class Award:
    def __init__(self, node) -> None:
        self.player = _attribute(node, "PLAYER")
        self.amount = _attribute(node, "AMOUNT")
        self.pot = _attribute(node, "POT")

    def __str__(self) -> str:
        return self.player + " won " + self.amount + " from " + self.pot


class Game:
    def __init__(self, node) -> None:
        # print(node)
        self.tags = {}
        for tag in (
            ("GAME_NAME", "game_name"),
            ("MAX", "max"),
            ("HIGHLOW", "high_low"),
            ("STRUCTURE", "structure"),
            ("MIXED", "mixed"),
        ):
            L = _descendants(node, tag[0])
            if not L:
                continue
            # print(L)
            for node2 in L:
                title = ""
                title += _direct_text(node2)
                self.tags[tag[1]] = title

    def __str__(self) -> str:
        return "{} {} {}, ({} max), {}".format(
            self.tags["structure"],
            self.tags["game_name"],
            self.tags["game_name"],
            self.tags["max"],
            self.tags["game_name"],
        )


class Posts:
    def __init__(self, node) -> None:
        self.posts = []  # just an array of post objects
        for p in _descendants(node, "POST"):
            self.posts.append(Post(p))

    def __str__(self) -> str:
        return "".join(f"{p}\n" for p in self.posts)


class Post:
    def __init__(self, node) -> None:
        self.player = _attribute(node, "PLAYER")
        self.amount = _attribute(node, "AMOUNT")
        self.posted = _attribute(node, "POSTED")
        self.live = _attribute(node, "LIVE")

    def __str__(self) -> str:
        return f"{self.player} posted {self.amount} {self.posted} {self.live}"


class Betting:
    def __init__(self, node) -> None:
        self.rounds = []  # a Betting object is just an array of rounds
        for r in _descendants(node, "ROUND"):
            self.rounds.append(Round(r))

    def __str__(self) -> str:
        return "".join(f"{r}\n" for r in self.rounds)


class Round:
    def __init__(self, node) -> None:
        self.name = _attribute(node, "ROUND_NAME")
        self.action = []
        for a in _descendants(node, "ACTION"):
            self.action.append(Action(a))

    def __str__(self) -> str:
        return self.name + "\n" + "".join(f"    {a}\n" for a in self.action)


class Action:
    def __init__(self, node) -> None:
        self.player = _attribute(node, "PLAYER")
        self.action = _attribute(node, "ACT")
        self.amount = _attribute(node, "AMOUNT")
        self.allin = _attribute(node, "ALLIN")

    def __str__(self) -> str:
        return self.player + " " + self.action + " " + self.amount + " " + self.allin


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Simple test - just parse test.xml like the original
    try:
        with open("test.xml") as file:
            xml_string = file.read()

        print("Parsing test.xml...")
        h = HandHistory(xml_string, ("ALL"))

        print("✓ XML parsing completed successfully")

        for _p in list(h.PLAYERS.keys()):
            pass

        return 0

    except FileNotFoundError:
        print("✗ Error: test.xml not found")
        print("Note: No test.xml file exists in the codebase - this is expected behavior")
        return 1
    except (ExpatError, AttributeError, KeyError, TypeError, ValueError) as e:
        print(f"✗ Error parsing XML: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
