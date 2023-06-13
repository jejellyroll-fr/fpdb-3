#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Steffen Schaumburg
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.


import os
import sys

import Charset
#import Stove

DEBUG = False

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QComboBox, \
    QFrame, QTableWidget, QLineEdit
from PyQt5.QtGui import QIcon
import sys


class GuiStove(QWidget):
    def __init__(self, config, parent, debug=True):
        """Constructor for GuiStove"""
        super().__init__()

        #self.stove = Stove()
        self.ev = None
        self.boardtext = ""
        self.herorange = ""
        self.villainrange = ""
        self.conf = config
        self.parent = parent

        self.mainHBox = QHBoxLayout()

        # hierarchy: self.mainHBox / self.notebook

        self.notebook = QTabWidget()
        self.notebook.setTabPosition(QTabWidget.TabPosition.North)
        self.notebook.setTabsClosable(True)
        self.notebook.setMovable(True)

        self.createFlopTab()
        self.createStudTab()
        self.createDrawTab()

        self.mainHBox.addWidget(self.notebook)

        self.setLayout(self.mainHBox)

        self.setWindowTitle("GuiStove")
        self.setWindowIcon(QIcon("path/to/icon"))

        self.show()

        if not debug:
            warning_string = _("Stove is a GUI mockup of a EV calculation page, and completely non functional.") + "\n "
            warning_string += _("Unless you are interested in developing this feature, please ignore this page.") + "\n "
            warning_string += _("If you are interested in developing the code further see GuiStove.py and Stove.py.") + "\n "
            warning_string += _("Thank you")
            self.warning_box(warning_string)









def warning_box(self, text, title="FPDB WARNING"):
    """
    Display a warning message box with a given text and title.

    Args:
        text (str): The message to display in the warning box.
        title (str): The title of the warning box. Defaults to "FPDB WARNING".

    Returns:
        int: The result of the user's interaction with the warning box (e.g. clicking OK).
    """
    # Create a warning message box using the given text and title, with the parent set to self.parent
    dialog = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning, title, text, parent=self.parent)
    # Set the standard and default buttons to OK
    dialog.setStandardButtons(QtWidgets.QMessageBox.Ok)
    dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)
    # Execute the warning box and return the result
    return dialog.exec_()



    def get_active_text(self, combobox):
        model = combobox.model()
        active = combobox.currentIndex()
        return None if active < 0 else model.item(active, 0).text()


    def create_combo_box(self, strings):
        combobox = QComboBox()
        for label in strings:
            combobox.addItem(label)
        combobox.setCurrentIndex(0)
        return combobox

    def createStudTab(self):
        tab_title = "Stud"
        label = QLabel(tab_title)

        widget = QWidget()
        stud_layout = QVBoxLayout(widget)
        self.notebook.addTab(widget, tab_title)

        # Add your desired widgets and layout for the Stud tab
        # Example: Add a label and a button
        stud_label = QLabel("This is the Stud tab")
        stud_button = QPushButton("Click me")

        stud_layout.addWidget(stud_label)
        stud_layout.addWidget(stud_button)



    def createDrawTab(self):
        tab_title = ("Draw")
        label = QLabel(tab_title)

        ddbox = QVBoxLayout()
        self.notebook.addTab(ddbox, label)

    def createDrawTab(self):
        tab_title = "Draw"

        widget = QWidget()
        ddbox = QVBoxLayout(widget)
        self.notebook.addTab(widget, tab_title)

    def createFlopTab(self):

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Top row: Combo boxes
        ddhbox = QHBoxLayout()
        self.layout.addLayout(ddhbox)

        games = ["Holdem", "Omaha", "Omaha 8"]
        players = ["2", "3", "4", "5", "6", "7", "8", "9", "10"]

        flop_games_cb = QComboBox()
        flop_games_cb.addItems(games)
        players_cb = QComboBox()
        players_cb.addItems(players)

        label = QLabel("Gametype:")
        ddhbox.addWidget(label)
        ddhbox.addWidget(flop_games_cb)
        label = QLabel("Players:")
        ddhbox.addWidget(label)
        ddhbox.addWidget(players_cb)

        # Frames for Stove input and output
        gamehbox = QHBoxLayout()
        self.layout.addLayout(gamehbox)

        in_frame = QFrame()
        in_frame.setFrameShape(QFrame.Box)
        in_frame.setFrameShadow(QFrame.Raised)
        out_frame = QFrame()
        out_frame.setFrameShape(QFrame.Box)
        out_frame.setFrameShadow(QFrame.Raised)

        gamehbox.addWidget(in_frame)
        gamehbox.addWidget(out_frame)

        self.outstring = """
No board given. Using Monte-Carlo simulation...
"""
        self.outputlabel = QLabel(self.outstring)
        out_frame.layout = QVBoxLayout(out_frame)
        out_frame.layout.addWidget(self.outputlabel)
        out_frame.setLayout(out_frame.layout)

        # Input Frame
        table = QTableWidget(4, 5)
        table.setHorizontalHeaderLabels(["Board:", "", "", "", ""])
        self.board = QLineEdit()

        btn1 = QPushButton()
        btn1.setIcon(QIcon.fromTheme("index"))

        table.setCellWidget(0, 1, self.board)
        table.setCellWidget(0, 2, btn1)

        self.p1_board = QLineEdit()
        btn2 = QPushButton()
        btn2.setIcon(QIcon.fromTheme("index"))
        btn3 = QPushButton()
        btn3.setIcon(QIcon.fromTheme("index"))

        table.setCellWidget(1, 0, QLabel("Player1:"))
        table.setCellWidget(1, 1, self.p1_board)
        table.setCellWidget(1, 2, btn2)
        table.setCellWidget(1, 3, btn3)

        self.p2_board = QLineEdit()
        btn4 = QPushButton()
        btn4.setIcon(QIcon.fromTheme("index"))
        btn5 = QPushButton()
        btn5.setIcon(QIcon.fromTheme("index"))

        table.setCellWidget(2, 0, QLabel("Player2:"))
        table.setCellWidget(2, 1, self.p2_board)
        table.setCellWidget(2, 2, btn4)
        table.setCellWidget(2, 3, btn5)

        btn6 = QPushButton("Results")
        btn6.clicked.connect(self.update_flop_output_pane)

        table.setCellWidget(3, 0, btn6)

        in_frame.layout = QVBoxLayout(in_frame)
        in_frame.layout.addWidget(table)
        in_frame.setLayout(in_frame.layout)




    def set_output_label(self, string):
        self.outputlabel.setText(string)


    def set_board_flop(self, caller, widget):
        debug_msg = f"DEBUG: called set_board_flop: '{caller}' '{widget}'"
        print(debug_msg)
        self.boardtext = widget.get_text()

    def tab_changed(self, index):
        # Get the current tab index and perform any necessary actions
        print("Tab changed to index:", index)

    def set_hero_cards_flop(self, caller, widget):
        print(("DEBUG:") + " " + ("called") + " set_hero_cards_flop")
        self.herorange = widget.get_text()


    def set_villain_cards_flop(self, widget):
        print(("DEBUG:") + " " + ("called") + " set_villain_cards_flop")
        self.villainrange = widget.text()

    def update_flop_output_pane(self, caller, widget):
        print (("DEBUG:") + " " + ("called") + " update_flop_output_pane")
#         self.stove.set_board_string(self.boardtext)
#         self.stove.set_hero_cards_string(self.herorange)
#         self.stove.set_villain_range_string(self.villainrange)
        self.stove.set_board_string(self.board.get_text())
        self.stove.set_hero_cards_string(self.p1_board.get_text())
        self.stove.set_villain_range_string(self.p2_board.get_text())
        print (("DEBUG:") + ("odds_for_range"))
        self.ev = Stove.odds_for_range(self.stove)
        print (("DEBUG:") + " " + ("set_output_label"))
        self.set_output_label(self.ev.output)



    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.mainHBox
    #end def get_vbox
if __name__ == "__main__":
    app = QApplication(sys.argv)
    config = {}  # Provide your configuration here
    parent = None  # Provide the parent widget if applicable, otherwise use None
    gui_stove = GuiStove(config, parent)
    sys.exit(app.exec_())