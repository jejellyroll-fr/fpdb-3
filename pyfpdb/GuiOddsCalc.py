from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QComboBox

import OddsCalc

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
        
        
        self.hbox = QHBoxLayout()
        self.hbox.addWidget(self.QLgame)
        self.hbox.addWidget(self.QLEgame)
        self.hbox.addWidget(self.QLdeadcard)
        self.hbox.addWidget(self.QLEdeadcard)
        
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


        self.load_button = QPushButton(('Odds Calculate'))
        self.load_button.clicked.connect(self.load_result)
        self.layout().addWidget(self.load_button)

        self.QTcalc = QTableWidget()
        hbox_result = QHBoxLayout()
        hbox_result.addWidget(self.QTcalc)
        self.layout().addLayout(hbox_result)


    def load_result(self):
        game = self.QLEgame.currentText()
        if game == "hold'em":
            game = 'he'
            
            self.Lreq = QLabel("Required")
            self.Lreq.setStyleSheet("QLabel { background-color : red; color : blue; }")
            self.hbox.addWidget(self.Lreq)
        elif game == "Omaha":
            game = 'oh'
            self.Lreq = QLabel("Required")
            self.Lreq.setStyleSheet("QLabel { background-color : blue; color : red; }")
            self.hbox.addWidget(self.Lreq)
        elif game == "5 card Omaha":
            game = 'oh5'
        elif game == "5 card Omaha Hi/Lo":
            game = 'o85'
        elif game == "Omaha Hi/Lo":
            game = 'o8'
        print(game)
        board = self.QLEboard.text()
        hero = self.QLEhero.text()
        vilain1 = self.QLEvilain1.text()
        vilain2 = self.QLEvilain2.text()
        vilain3 = self.QLEvilain3.text()
        vilain4 = self.QLEvilain4.text()
        vilain5 = self.QLEvilain5.text()     
        odd1 = OddsCalc.OddsCalc(str(game),'',str(board),str(hero),str(vilain1),str(vilain2),str(vilain3),str(vilain4),str(vilain5)) 
        
        result_brut = odd1.calcBaseHoldem()
        print(result_brut)
        row_count = (len(result_brut))
        column_count = (len(result_brut[0]))
        self.QTcalc.setColumnCount(column_count) 
        self.QTcalc.setRowCount(row_count)

        self.QTcalc.setHorizontalHeaderLabels((list(result_brut[0].keys())))

        for row in range(row_count):  # add items from array to QTableWidget
            for column in range(column_count):
                item = (list(result_brut[row].values())[column])
                print (type(row))
                print (type(column))
                print (type(item))
                self.QTcalc.setItem(row, column, QTableWidgetItem(item))
    
        