# -*- coding: utf-8 -*-
################################################################################
##
## BY: WANDERSON M.PIMENTA
## PROJECT MADE WITH: Qt Designer and PyQt5
## V: 1.0.0
##
## This project can be used freely for all uses, as long as they maintain the
## respective credits only in the Python scripts, any information in the visual
## interface (GUI) can be modified without any implication.
##
## There are limitations on Qt licenses if you want to use your products
## commercially, I recommend reading them on the official website:
## https://doc.qt.io/qtforpython/licenses.html
##
################################################################################

from PyQt5.QtCore import (QCoreApplication, QMetaObject, QObject, QPoint,
    QRect, QSize, QUrl, Qt)
from PyQt5.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QLinearGradient, QPalette, QPainter, QPixmap,
    QRadialGradient)
from PyQt5.QtWidgets import *

import files_rc as files_rc

class Ui_Sites_setting(object):
    def sitesUi(self):
        self.page_sites_settings = QWidget()
        self.page_sites_settings.setObjectName(u"page_sites_settings")
        self.verticalLayout_sites_settings= QVBoxLayout(self.page_sites_settings)
        self.verticalLayout_sites_settings.setObjectName(u"verticalLayout_sites_settings")
        self.label_sites_settings = QLabel(("Please select which sites you play on and enter your usernames."))
        self.verticalLayout_sites_settings.addWidget(self.label_sites_settings)
  