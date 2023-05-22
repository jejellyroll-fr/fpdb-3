# Deck.py
# -*- coding: utf-8
# PokerStats, an online poker statistics tracking software for Linux
# Copyright (C) 2007-2011 Mika Boström <bostik@iki.fi>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
"""Deck.py

Helper class for mucked card display. Loads specified deck from SVG
images and returns it as a dict of pixbufs.
"""


import os

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import (QPixmap, QPainter)
from PyQt5.QtSvg import QSvgRenderer

class Deck(object):
    def __init__(self, config, deck_type=u'simple', card_back=u'back04', width=30, height=42):
        """
        Constructor for the Deck class.

        Parameters:
        config (Config): The configuration object.
        deck_type (str): The type of deck to use.
        card_back (str): The name of the card back to use.
        width (int): The width of a card.
        height (int): The height of a card.
        """
        # Set width and height of cards
        self.__width = width
        self.__height = height

        # Set paths to card images and back image
        self.__cardspath = os.path.join(config.graphics_path, u"cards", deck_type).replace('\\', '/')
        self.__backfile = os.path.join(
            config.graphics_path, u"cards", u"backs", f"{card_back}.svg"
        ).replace('\\', '/')

        # Load card images for each suit
        self.__cards = dict({ 's': None, 'h': None, 'd': None, 'c': None })
        for sk in self.__cards:
            self.__load_suit(sk)

        # Load card back image
        self.__card_back = self.__load_svg(self.__backfile)

        # Create rank lookups
        self.__rank_vals = {}
        self.__create_rank_lookups()

    def __create_rank_lookups(self):
        """
        Creates a lookup dictionary for card ranks and assigns it to the object's __rank_vals attribute.

        The keys of the dictionary are the ranks of the cards as strings ('2' - '9', 'T', 'J', 'Q', 'K', 'A').
        The values of the dictionary are the corresponding integer values of the ranks.
        """
        # Create the dictionary with card rank keys and integer value values
        self.__rank_vals = {
            '2': 2, '3': 3, '4': 4, '5': 5,
            '6': 6, '7': 7, '8': 8, '9': 9,
            'T': 10, 'J': 11, 'Q': 12,
            'K': 13, 'A': 14 
        }
    
    
    def __load_svg(self, path):
        """
        Loads an SVG file from the given path and returns a QPixmap.

        Args:
            path (str): The path to the SVG file.

        Returns:
            QPixmap: The loaded SVG as a QPixmap.
        """
        # Create an SVG renderer from the given path
        renderer = QSvgRenderer(path)

        # Create a QPixmap with the specified width and height
        pm = QPixmap(self.__width, self.__height)

        # Create a QPainter for the QPixmap
        painter = QPainter(pm)

        # Render the SVG onto the QPixmap
        renderer.render(painter, QRectF(pm.rect()))

        # Return the loaded SVG as a QPixmap
        return pm

    def __load_suit(self, suit_key):
        """
        Load all the cards for a given suit into the self.__cards dictionary.

        :param suit_key: a string representing the suit to load
        :return: None
        """
        sd = {}
        _p = self.__cardspath
        # Load each card for the suit
        sd[2] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '2' + '.svg')).replace('\\', '/'))
        sd[3] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '3' + '.svg')).replace('\\', '/'))
        sd[4] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '4' + '.svg')).replace('\\', '/'))
        sd[5] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '5' + '.svg')).replace('\\', '/'))
        sd[6] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '6' + '.svg')).replace('\\', '/'))
        sd[7] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '7' + '.svg')).replace('\\', '/'))
        sd[8] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '8' + '.svg')).replace('\\', '/'))
        sd[9] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '9' + '.svg')).replace('\\', '/'))
        sd[10] = self.__load_svg(os.path.join(_p, (suit_key + '_' + '10' + '.svg')).replace('\\', '/'))
        sd[11] = self.__load_svg(os.path.join(_p, (suit_key + '_' + 'j' + '.svg')).replace('\\', '/'))
        sd[12] = self.__load_svg(os.path.join(_p, (suit_key + '_' + 'q' + '.svg')).replace('\\', '/'))
        sd[13] = self.__load_svg(os.path.join(_p, (suit_key + '_' + 'k' + '.svg')).replace('\\', '/'))
        sd[14] = self.__load_svg(os.path.join(_p, (suit_key + '_' + 'a' + '.svg')).replace('\\', '/'))
        self.__cards[suit_key] = sd
        

    def card(self, suit=None, rank=0):
        """
        Returns the card in the deck with the given suit and rank.

        Args:
            suit (str): The suit of the card to retrieve. Defaults to None.
            rank (int): The rank of the card to retrieve. Defaults to 0.

        Returns:
            The card with the given suit and rank.
        """
        return self.__cards[suit][rank]  # Access the cards dictionary with the given suit and rank to retrieve the card.

    def back(self):
        """
        Returns the card's back image.
        """
        return self.__card_back
        
    def rank(self, token=None):
        """
        Returns the rank value associated with the given token.

        Args:
            token (str): The token to retrieve the rank value for. If None, the function will return None.

        Returns:
            The rank value associated with the given token, or None if the token is None or not found.
        """
        # Convert the token to uppercase to ensure case-insensitivity
        key = token.upper()

        # Return the rank value associated with the token, or None if not found
        return self.__rank_vals.get(key)
    
    def get_all_card_images(self):
        """
        Returns a 4x13-element dictionary of every card image + index-0 = card back as a QPixmap.

        Returns:
        card_images (dict): A dictionary containing the card images, with each element being a QPixmap.
        """

        card_images = {}

        # Loop through each suit and rank to get the card image for each card
        for suit in ('s', 'h', 'd', 'c'):
            card_images[suit] = {}
            for rank in (14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2):
                card_images[suit][rank] = self.card(suit, rank)

        # Add the card back image to the dictionary
        card_images[0] = self.back()

        return card_images

