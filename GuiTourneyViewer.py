#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2010-2011 Steffen Schaumburg
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





#import L10n
#_ = L10n.get_translation()


from PyQt5.QtCore import QCoreApplication, QSortFilterProxyModel, Qt
from PyQt5.QtGui import (QPainter, QPixmap, QStandardItem, QStandardItemModel)
from PyQt5.QtWidgets import (QApplication, QFrame, QMenu,
                             QProgressDialog, QScrollArea, QSplitter,
                             QTableView, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,QGridLayout ,QWidget ,QTableWidget ,QTableWidgetItem,QComboBox, QMessageBox)

class GuiTourneyViewer(QWidget):
    def __init__(self, config, db, sql, mainwin):
        QWidget.__init__(self, mainwin)
        self.db = db
        self.mainwin = mainwin
        #self.mainVBox = gtk.VBox()
        #self.mainVBox = QVBoxLayout()
        #self.interfaceHBox = gtk.HBox()
        self.interfaceHBox = QVBoxLayout()
        #self.mainVBox.pack_start(self.interfaceHBox, expand=False)
        #self.mainVBox.addWidget(self.interfaceHBox)
        self.setLayout(self.interfaceHBox)
        
        #self.siteBox = gtk.combo_box_new_text()
        self.siteBox = QComboBox()
        for count, site in enumerate(config.supported_sites, start=1):
            print(site)
            #self.siteBox.append_text(site)
            self.siteBox.insertItem(count,site)
        #self.siteBox.set_active(0)
        self.interfaceHBox.addWidget(self.siteBox)
        
        #label=gtk.Label(("Enter the tourney number you want to display:"))
        self.label_tour = QLabel()
        self.label_tour.setText("Enter the tourney number you want to display:")
        self.interfaceHBox.addWidget(self.label_tour)
        
        #self.entryTourney = gtk.Entry()
        self.entryTourney = QLineEdit()
        self.interfaceHBox.addWidget(self.entryTourney)
        
        #self.displayButton = gtk.Button(("Display"))
        

        
        self.label_Player = QLabel()
        self.label_Player.setText("Enter the player you want to display:")
        self.interfaceHBox.addWidget(self.label_Player)
        #self.entryPlayer = gtk.Entry()
        self.entryPlayer = QLineEdit()
        self.interfaceHBox.addWidget(self.entryPlayer)
        
        #self.playerButton = gtk.Button(("Display Player"))
        # self.playerButton = QPushButton()
        # self.playerButton.setText("Display Player")
        # self.playerButton.clicked.connect(self.displayPlayerClicked)
        # self.interfaceHBox.addWidget(self.playerButton)
        self.displayButton = QPushButton()
        self.displayButton.setText("Display")
        self.interfaceHBox.addWidget(self.displayButton)
        self.displayButton.clicked.connect(self.displayClicked)
        # self.table = gtk.Table(columns=10, rows=9)
        
        self.table = QTableWidget()
        self.interfaceHBox.addWidget(self.table)



        
        # self.mainVBox.show_all()
    #end def __init__
    def warning_box(self, string, diatitle=("FPDB WARNING")):
        return QMessageBox(QMessageBox.Warning, diatitle, string).exec_()   

    def displayClicked(self, widget, data=None):
        if self.siteBox.currentText() == "" or self.entryPlayer.text() == "" or self.entryTourney.text() == "":
            self.warning_box("you must enter Site Name, player Name and Tourney Number")
        else:
            self.siteName = self.siteBox.currentText()
            self.playerName = self.entryPlayer.text()   
            self.tourneyNo = int(self.entryTourney.text())                 
            result = self.db.getTourneyInfo(self.siteName, self.tourneyNo)
            rows = len(result)
            columns  = len(result[0])
            self.table.setColumnCount(columns) 
            self.table.setRowCount(rows)
        
            if result[1] == None:
                
                self.errorLabel = QLabel.setText(("Tournament not found.") + " " + ("Please ensure you imported it and selected the correct site."))
                self.interfaceHBox.addWidget(self.errorLabel)
            else:
                for row in range(rows):  # add items from array to QTableWidget
                    for column in range(columns):
                        if column == 0:
                            item = QTableWidgetItem(str(result[row][column]))
                        else:
                            item = QTableWidgetItem(str(result[row][column]))   
                            print(type(row))
                            print(type(column))
                            print(type(item))
                            self.table.setItem(row, column, QTableWidgetItem(item))
            
                    
        #self.mainVBox.show_all()
    #def displayClicked
    
    # def displayPlayerClicked(self, widget, data=None):
    #     self.siteName = self.siteBox.currentText()
    #     self.playerName = self.entryPlayer.text()   
    #     self.tourneyNo = int(self.entryTourney.text())        
    #     result=self.db.getTourneyPlayerInfo(self.siteName, self.tourneyNo, self.playerName)
    #     rows = len(result)
    #     columns  = len(result[0])
    #     self.table.setColumnCount(columns) 
    #     self.table.setRowCount(rows)
        
    #     if result[1] == None:
                
    #         self.errorLabel = QLabel.setText(("Tournament not found.") + " " + ("Please ensure you imported it and selected the correct site."))
    #         self.interfaceHBox.addWidget(self.errorLabel)
    #     else:
    #         for row in range(rows):  # add items from array to QTableWidget
    #             for column in range(columns):
    #                 if column == 0:
    #                     item = QTableWidgetItem(str(result[row][column]))
    #                 else:
    #                     item = QTableWidgetItem(str(result[row][column]))   
    #                     print(type(row))
    #                     print(type(column))
    #                     print(type(item))
    #                     self.table.setItem(row, column, QTableWidgetItem(item))
                
                    
        #self.mainVBox.show_all()
    #def displayPlayerClicked
    
    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.mainVBox
    #end def get_vbox
    
    def prepare(self, columns, rows):
        try: self.errorLabel.destroy()
        except: pass
        
        try:
            self.tourneyNo=int(self.entryTourney.text())
        except ValueError:
            self.errorLabel=QLabel()
            self.errorLabel.setText("invalid entry in tourney number - must enter numbers only")
            self.interfaceHBox.addWidget(self.errorLabel)
            return False
        self.siteName=self.siteBox.currentText()
        self.playerName=self.entryPlayer.text()
        
        #self.table.destroyed()
        self.table=QGridLayout()
        
        return True
    #end def readInfo
#end class GuiTourneyViewer
