from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem

import OddsCalc

class GuiOddsCalc(QWidget):
    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.layout()    

    def __init__(self, parent = None):
        QWidget.__init__(self, parent)
        self.setLayout(QVBoxLayout())

        self.QLgame = QLabel("Game")
        self.QLEgame = QLineEdit()
        self.QLboard = QLabel("Board")
        self.QLEboard = QLineEdit()
        self.QLhero = QLabel("Hero")
        self.QLEhero = QLineEdit()
        self.QLvilain1 = QLabel("Vilain1")
        self.QLEvilain1 = QLineEdit()
        self.QLvilain2 = QLabel("Vilain2")
        self.QLEvilain2 = QLineEdit()
        hbox = QHBoxLayout()
        hbox.addWidget(self.QLgame)
        hbox.addWidget(self.QLEgame)
        hbox.addWidget(self.QLboard)
        hbox.addWidget(self.QLEboard)
        hbox.addWidget(self.QLhero)
        hbox.addWidget(self.QLEhero)
        hbox.addWidget(self.QLvilain1)
        hbox.addWidget(self.QLEvilain1)
        hbox.addWidget(self.QLvilain2)
        hbox.addWidget(self.QLEvilain2)
        self.layout().addLayout(hbox)

        self.load_button = QPushButton(('Odds Calculate'))
        self.load_button.clicked.connect(self.load_result)
        self.layout().addWidget(self.load_button)

        self.QTcalc = QTableWidget()
        hbox_result = QHBoxLayout()
        hbox_result.addWidget(self.QTcalc)
        self.layout().addLayout(hbox_result)


    def load_result(self):
        game = self.QLEgame.text()
        print(game)
        odd1 = OddsCalc.OddsCalc(str(game),'As8s4d9d','AK','89','') 
        
        result_brut = odd1.calcBaseHoldem()
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
    
        