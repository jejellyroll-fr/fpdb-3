# Deck.py
# PokerStats, an online poker statistics tracking software for Linux
# Copyright (C) 2007-2011 Mika Boström <bostik@iki.fi>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
"""Deck.py.

Helper class for mucked card display. Loads specified deck from SVG
images and returns it as a dict of pixbufs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer


class Deck:
    """Card deck for mucked card display.

    Loads SVG card images and provides access to card pixmaps.
    """
    def __init__(
        self,
        config: Any,
        deck_type: str = "simple",
        card_back: str = "back04",
        width: int = 30,
        height: int = 42,
    ) -> None:
        """Initialize the deck with card images.

        Args:
            config: Configuration object with graphics path
            deck_type: Type of deck to load (default: "simple")
            card_back: Card back design name (default: "back04")
            width: Card width in pixels (default: 30)
            height: Card height in pixels (default: 42)
        """
        self.__width = width
        self.__height = height
        self.__cardspath = str(Path(config.graphics_path) / "cards" / deck_type)
        self.__backfile = str(Path(config.graphics_path) / "cards" / "backs" / f"{card_back}.svg")
        self.__cards = {"s": None, "h": None, "d": None, "c": None}
        self.__card_back = None
        self.__rank_vals = {}

        for sk in self.__cards:
            self.__load_suit(sk)

        self.__card_back = self.__load_svg(self.__backfile)

        self.__create_rank_lookups()

    def __create_rank_lookups(self) -> None:
        self.__rank_vals = {
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "T": 10,
            "J": 11,
            "Q": 12,
            "K": 13,
            "A": 14,
        }

    def __load_svg(self, path: str) -> QPixmap:
        """Load SVG file and return as QPixmap.

        Args:
            path: Path to SVG file

        Returns:
            QPixmap with the loaded SVG image
        """
        renderer = QSvgRenderer(path)
        pm = QPixmap(self.__width, self.__height)
        painter = QPainter(pm)
        renderer.render(painter, QRectF(pm.rect()))
        return pm

    def __load_suit(self, suit_key: str) -> None:
        """Load all cards for a specific suit.

        Args:
            suit_key: Single character suit key (s, h, d, c)
        """
        sd = {}
        _p = self.__cardspath
        for rank, rank_str in [
            (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6"),
            (7, "7"), (8, "8"), (9, "9"), (10, "10"),
            (11, "j"), (12, "q"), (13, "k"), (14, "a"),
        ]:
            sd[rank] = self.__load_svg(
                str(Path(_p) / f"{suit_key}_{rank_str}.svg"),
            )
        self.__cards[suit_key] = sd

    def card(self, suit: str | None = None, rank: int = 0) -> QPixmap:
        """Get card pixmap for specified suit and rank.

        Args:
            suit: Suit character (s, h, d, c)
            rank: Card rank (2-14)

        Returns:
            QPixmap of the requested card
        """
        return self.__cards[suit][rank]

    def back(self) -> QPixmap:
        """Get card back pixmap.

        Returns:
            QPixmap of the card back
        """
        return self.__card_back

    def rank(self, token: str | None = None) -> int:
        """Convert rank token to numeric value.

        Args:
            token: Rank string (2-9, T, J, Q, K, A)

        Returns:
            Numeric rank value (2-14)
        """
        key = token.upper()
        return self.__rank_vals[key]

    def get_all_card_images(self) -> dict[str | int, dict[int, QPixmap] | QPixmap]:
        """Get all card images as a dictionary.

        Returns:
            Dictionary with suit keys containing rank dictionaries of QPixmaps,
            plus key 0 for card back
        """
        # returns a 4x13-element dictionary of every card image +
        # index-0 = card back each element is a QPixmap
        card_images = {}

        for suit in ("s", "h", "d", "c"):
            card_images[suit] = {}
            for rank in (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2):
                card_images[suit][rank] = self.card(suit, rank)

        # This is a nice trick. We put the card back image behind key 0,
        # which allows the old code to work. A dict[0] looks like first
        # index of an array.
        card_images[0] = self.back()
        return card_images
