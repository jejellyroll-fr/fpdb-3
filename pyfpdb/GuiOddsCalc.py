from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,QLabel, QPushButton, QFileDialog

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

        self.QLEcalc = QLineEdit()
        hbox_result = QHBoxLayout()
        hbox_result.addWidget(self.QLEcalc)
        self.layout().addLayout(hbox_result)


    def load_result(self):
        game = self.QLEgame.text()
        print(game)
        odd1 = OddsCalc.OddsCalc(str(game),'As8s4d9d','AK','89','') 
        #odd1.calcBaseHoldem()
        print(odd1.calcBaseHoldem())
        self.QLEcalc.setText(str(odd1.calcBaseHoldem()))
