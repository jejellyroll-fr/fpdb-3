from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QComboBox, QMessageBox
from sqlalchemy import null


import OddsCalc
import OddsCalcPQL


    

class GuiOddsCalc(QWidget):
    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.layout()    

    def __init__(self, parent = None):
        QWidget.__init__(self, parent)
        self.setLayout(QVBoxLayout())

        self.QLgame = QLabel("Game")
        self.QLEgame = QComboBox()
        he = "hold'em"
        self.QLEgame.insertItem(1, he)
        oh = "Omaha"
        self.QLEgame.insertItem(2, oh)
        oh5 = "5 card Omaha"
        self.QLEgame.insertItem(3, oh5)
        o85 = "5 card Omaha Hi/Lo"
        self.QLEgame.insertItem(4, o85)
        o8 = "Omaha Hi/Lo"
        self.QLEgame.insertItem(5, o8)
        rz = "Razz"
        self.QLEgame.insertItem(6, rz)
        st = "Stud"
        self.QLEgame.insertItem(7, st)
        s8 = "Stud Hi/Lo"
        self.QLEgame.insertItem(8, s8)
        o6 = "6 card Omaha"
        self.QLEgame.insertItem(9, o6)                
        self.QLEgame.setMinimumWidth(300)
        self.QLdeadcard = QLabel("Dead Card")
        self.QLEdeadcard = QLineEdit()        
        self.QLboard = QLabel("Board")
        self.QLEboard = QLineEdit()
        self.QLhero = QLabel("Hero")
        self.QLEhero = QLineEdit()
        self.QLvilain1 = QLabel("Vilain1")
        self.QLEvilain1 = QLineEdit()
        self.QLvilain2 = QLabel("Vilain2")
        self.QLEvilain2 = QLineEdit()
        self.QLvilain3 = QLabel("Vilain3")
        self.QLEvilain3 = QLineEdit()
        self.QLvilain4 = QLabel("Vilain4")
        self.QLEvilain4 = QLineEdit()
        self.QLvilain5 = QLabel("Vilain5")
        self.QLEvilain5 = QLineEdit()
        self.Lreq = QLabel()

        
        
        self.hbox = QHBoxLayout()
        self.hbox.addWidget(self.QLgame)
        self.hbox.addWidget(self.QLEgame)
        self.hbox.addWidget(self.QLdeadcard)
        self.hbox.addWidget(self.Lreq)
        self.hbox.addWidget(self.QLEdeadcard)
        
        self.Lreq.setText("Not Required")
        self.Lreq.setStyleSheet("QLabel { color : green; }")        
        self.layout().addLayout(self.hbox)

        self.hbox2 = QHBoxLayout()
        
        self.hbox2.addWidget(self.QLboard)
        self.hbox2.addWidget(self.QLEboard)
        self.layout().addLayout(self.hbox2)
        
        self.hbox3 = QHBoxLayout()
        self.hbox3.addWidget(self.QLhero)
        self.hbox3.addWidget(self.QLEhero)
        self.hbox3.addWidget(self.QLvilain1)
        self.hbox3.addWidget(self.QLEvilain1)
        self.hbox3.addWidget(self.QLvilain2)
        self.hbox3.addWidget(self.QLEvilain2)
        self.hbox3.addWidget(self.QLvilain3)
        self.hbox3.addWidget(self.QLEvilain3)
        self.hbox3.addWidget(self.QLvilain4)
        self.hbox3.addWidget(self.QLEvilain4)
        self.hbox3.addWidget(self.QLvilain5)
        self.hbox3.addWidget(self.QLEvilain5)
        self.layout().addLayout(self.hbox3)
        self.QLEgame.activated[str].connect(self.index_changed)

        self.load_button = QPushButton(('Odds Calculate'))

            
        
        self.load_button.clicked.connect(self.load_result)
        self.layout().addWidget(self.load_button)

        self.QTcalc = QTableWidget()
        hbox_result = QHBoxLayout()
        hbox_result.addWidget(self.QTcalc)
        self.layout().addLayout(hbox_result)
        
    def warning_box(self, string, diatitle=("FPDB WARNING")):
        return QMessageBox(QMessageBox.Warning, diatitle, string).exec_()

    def index_changed(self):
        if self.QLEgame.currentText() == "hold'em":
            self.Lreq.setText("Not Required")
            self.Lreq.setStyleSheet("QLabel { color : green; }")
        elif self.QLEgame.currentText() == "Omaha":
            self.Lreq.setText("Not Required")
        elif self.QLEgame.currentText() == "6 card Omaha":
            self.Lreq.setText("Not Required")
            self.Lreq.setStyleSheet("QLabel { color : green; }")    
        elif self.QLEgame.currentText() == "5 card Omaha":
            self.Lreq.setText("Not Required")
            self.Lreq.setStyleSheet("QLabel { color : green; }") 
        elif self.QLEgame.currentText() == "5 card Omaha Hi/Lo":
            self.Lreq.setText("Not Required")
            self.Lreq.setStyleSheet("QLabel { color : green; }")    
        elif self.QLEgame.currentText() == "Omaha Hi/Lo":
            self.Lreq.setText("Not Required")
            self.Lreq.setStyleSheet("QLabel { color : green; }")   
        elif self.QLEgame.currentText() == "Razz":
            self.Lreq.setText("Required")
            self.Lreq.setStyleSheet("QLabel { color : red; }")     
        elif self.QLEgame.currentText() == "Stud":
            self.Lreq.setText("Required")
            self.Lreq.setStyleSheet("QLabel { color : red; }") 
        elif self.QLEgame.currentText() == "Stud Hi/Lo":
            self.Lreq.setText("Required")
            self.Lreq.setStyleSheet("QLabel { color : red; }")                                          
   

    def load_result(self):
        if self.QLEhero.text() == "" and self.QLEvilain1.text() == "":
            self.warning_box("you must enter hero and vilain1 hands")
        else:
            game = self.QLEgame.currentText()
            if game == "hold'em":
                game = 'holdem'
            elif game == "Omaha":
                game = 'omahahi'
            elif game == "5 card Omaha":
                game = 'omahahi5'
            elif game == "5 card Omaha Hi/Lo":
                game = 'omaha85'
            elif game == "Omaha Hi/Lo":
                game = 'omaha8'
            elif game == "Razz":
                game = 'razz'
            elif game == "Stud":
                game = 'studhi'
            elif game == "Stud Hi/Lo":
                game = 'stud8'
            elif game == "6 card Omaha":
                game = 'omahahi6'
            print(game)
            board = self.QLEboard.text()
            dead = self.QLEdeadcard.text()
            hero = self.QLEhero.text()
            vilain1 = self.QLEvilain1.text()
            vilain2 = self.QLEvilain2.text()
            vilain3 = self.QLEvilain3.text()
            vilain4 = self.QLEvilain4.text()
            vilain5 = self.QLEvilain5.text()
            if game == 'stud8' or game == 'studhi' or game == 'razz':      
                odd1 = OddsCalcPQL.OddsCalcPQL(game,board)
                #odd1 = OddsCalc.OddsCalc(str(game),str(dead),str(board),str(hero),str(vilain1),str(vilain2),str(vilain3),str(vilain4),str(vilain5))
            else:
                odd1 = OddsCalcPQL.OddsCalcPQL(game,board)
                #odd1 = OddsCalc.OddsCalc(str(game),str(dead),str(board),str(hero),str(vilain1),str(vilain2),str(vilain3),str(vilain4),str(vilain5))
        
            result_brut = odd1.calcBasePQL()

            print(result_brut)
            row_count = len(result_brut)
            print(row_count)
            column_count = 2 #nb player
            print(column_count)
            self.QTcalc.setColumnCount(int(row_count/2)) 
            self.QTcalc.setRowCount(column_count)
            name_col = ['Hands', 'Equity', 'Win','Ties']
            self.QTcalc.setHorizontalHeaderLabels((list(name_col)))

            for row in range(column_count-1):
                for col in range(row_count-1):
                    item = list(result_brut.values())
                    print('item value:',item)
                    print('item value:',item[col])
                    self.QTcalc.setItem(row, col, QTableWidgetItem(item[col]))
