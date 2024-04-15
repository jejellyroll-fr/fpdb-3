# ///////////////////////////////////////////////////////////////
#
# BY: WANDERSON M.PIMENTA
# PROJECT MADE WITH: Qt Designer and PySide6
# V: 1.0.0
#
# This project can be used freely for all uses, as long as they maintain the
# respective credits only in the Python scripts, any information in the visual
# interface (GUI) can be modified without any implication.
#
# There are limitations on Qt licenses if you want to use your products
# commercially, I recommend reading them on the official website:
# https://doc.qt.io/qtforpython/licenses.html
#
# ///////////////////////////////////////////////////////////////

# IMPORT QT CORE
# ///////////////////////////////////////////////////////////////
from qt_core import *

import xml.dom.minidom
from xml.dom.minidom import Node
import Configuration
import Options
import sys
cl_options = '.'.join(sys.argv[1:])
(options, argv) = Options.fpdb_options()
from gui.widgets.py_tree_widget.py_tree_widget import PyTreeWidget
from gui.core.json_themes import Themes
from gui.core.json_settings import Settings

class Ui_MainPages(object):
    def setupUi(self, MainPages):
        if not MainPages.objectName():
            MainPages.setObjectName(u"MainPages")
        MainPages.resize(860, 600)
        self.main_pages_layout = QVBoxLayout(MainPages)
        self.main_pages_layout.setSpacing(0)
        self.main_pages_layout.setObjectName(u"main_pages_layout")
        self.main_pages_layout.setContentsMargins(5, 5, 5, 5)
        self.pages = QStackedWidget(MainPages)
        self.pages.setObjectName(u"pages")

        ### PAGE 1
        self.page_1 = QWidget()
        self.page_1.setObjectName(u"page_1")
        self.page_1.setStyleSheet(u"font-size: 14pt")
        self.page_1_layout = QVBoxLayout(self.page_1)
        self.page_1_layout.setSpacing(5)
        self.page_1_layout.setObjectName(u"page_1_layout")
        self.page_1_layout.setContentsMargins(5, 5, 5, 5)
        self.welcome_base = QFrame(self.page_1)
        self.welcome_base.setObjectName(u"welcome_base")
        self.welcome_base.setMinimumSize(QSize(300, 150))
        self.welcome_base.setMaximumSize(QSize(300, 150))
        self.welcome_base.setFrameShape(QFrame.NoFrame)
        self.welcome_base.setFrameShadow(QFrame.Raised)
        self.center_page_layout = QVBoxLayout(self.welcome_base)
        self.center_page_layout.setSpacing(10)
        self.center_page_layout.setObjectName(u"center_page_layout")
        self.center_page_layout.setContentsMargins(0, 0, 0, 0)
        self.logo = QFrame(self.welcome_base)
        self.logo.setObjectName(u"logo")
        self.logo.setMinimumSize(QSize(300, 120))
        self.logo.setMaximumSize(QSize(300, 120))
        self.logo.setFrameShape(QFrame.NoFrame)
        self.logo.setFrameShadow(QFrame.Raised)
        self.logo_layout = QVBoxLayout(self.logo)
        self.logo_layout.setSpacing(0)
        self.logo_layout.setObjectName(u"logo_layout")
        self.logo_layout.setContentsMargins(0, 0, 0, 0)

        self.center_page_layout.addWidget(self.logo)

        self.label = QLabel(self.welcome_base)
        self.label.setObjectName(u"label")
        self.label.setAlignment(Qt.AlignCenter)

        self.center_page_layout.addWidget(self.label)


        self.page_1_layout.addWidget(self.welcome_base, 0, Qt.AlignHCenter)

        self.pages.addWidget(self.page_1)



        ### PAGE 2
        self.page_2 = QWidget()
        self.page_2.setObjectName(u"page_2")
        self.page_2_layout = QVBoxLayout(self.page_2)
        self.page_2_layout.setSpacing(5)
        self.page_2_layout.setObjectName(u"page_2_layout")
        self.page_2_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_area = QScrollArea(self.page_2)
        self.scroll_area.setObjectName(u"scroll_area")
        self.scroll_area.setStyleSheet(u"background: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.contents = QWidget()
        self.contents.setObjectName(u"contents")
        self.contents.setGeometry(QRect(0, 0, 840, 580))
        self.contents.setStyleSheet(u"background: transparent;")
        self.verticalLayout = QVBoxLayout(self.contents)
        self.verticalLayout.setSpacing(15)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(5, 5, 5, 5)
        self.title_label = QLabel(self.contents)
        self.title_label.setObjectName(u"title_label")
        self.title_label.setMaximumSize(QSize(16777215, 40))
        font = QFont()
        font.setPointSize(16)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet(u"font-size: 16pt")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.title_label)

        self.description_label = QLabel(self.contents)
        self.description_label.setObjectName(u"description_label")
        self.description_label.setAlignment(Qt.AlignHCenter|Qt.AlignTop)
        self.description_label.setWordWrap(True)

        self.verticalLayout.addWidget(self.description_label)

        self.row_1_layout = QHBoxLayout()
        self.row_1_layout.setObjectName(u"row_1_layout")

        self.verticalLayout.addLayout(self.row_1_layout)

        self.row_2_layout = QHBoxLayout()
        self.row_2_layout.setObjectName(u"row_2_layout")

        self.verticalLayout.addLayout(self.row_2_layout)

        self.row_3_layout = QHBoxLayout()
        self.row_3_layout.setObjectName(u"row_3_layout")

        self.verticalLayout.addLayout(self.row_3_layout)

        self.row_4_layout = QVBoxLayout()
        self.row_4_layout.setObjectName(u"row_4_layout")

        self.verticalLayout.addLayout(self.row_4_layout)

        self.row_5_layout = QVBoxLayout()
        self.row_5_layout.setObjectName(u"row_5_layout")

        self.verticalLayout.addLayout(self.row_5_layout)

        self.scroll_area.setWidget(self.contents)

        self.page_2_layout.addWidget(self.scroll_area)

        self.pages.addWidget(self.page_2)



        ### PAGE 3
        self.page_3 = QWidget()
        self.page_3.setObjectName(u"page_3")
        self.page_3.setStyleSheet(u"QFrame {\n"
"	font-size: 16pt;\n"
"}")
        self.page_3_layout = QVBoxLayout(self.page_3)
        self.page_3_layout.setObjectName(u"page_3_layout")
        self.empty_page_label = QLabel(self.page_3)
        self.empty_page_label.setObjectName(u"empty_page_label")
        self.empty_page_label.setFont(font)
        self.empty_page_label.setAlignment(Qt.AlignCenter)

        self.page_3_layout.addWidget(self.empty_page_label)

        self.pages.addWidget(self.page_3)


        #### PAGE 4
        self.page_gui_prefs = GuiPrefs()
        self.pages.addWidget(self.page_gui_prefs)        






        self.main_pages_layout.addWidget(self.pages)


        self.retranslateUi(MainPages)

        self.pages.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainPages)
    # setupUi

    def retranslateUi(self, MainPages):
        MainPages.setWindowTitle(QCoreApplication.translate("MainPages", u"Form", None))
        self.label.setText(QCoreApplication.translate("MainPages", u"Welcome To PyOneDark GUI", None))
        self.title_label.setText(QCoreApplication.translate("MainPages", u"Custom Widgets Page", None))
        self.description_label.setText(QCoreApplication.translate("MainPages", u"Here will be all the custom widgets, they will be added over time on this page.\n"
"I will try to always record a new tutorial when adding a new Widget and updating the project on Patreon before launching on GitHub and GitHub after the public release.", None))
        self.empty_page_label.setText(QCoreApplication.translate("MainPages", u"Empty Page", None))
    # retranslateUi





class GuiPrefs(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()
        self.applyTheme()

    def applyTheme(self):
        # Charger le thème actuel
        themes = Themes()
        theme_colors = themes.items['app_color']
        
        # Appliquer le thème aux éléments de l'interface utilisateur ici, si nécessaire
        # Exemple : self.setStyleSheet(f"background-color: {theme_colors['bg_one']};")

    def setupUi(self):
        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        self.resize(600, 350)
        layout = QVBoxLayout(self)
        themes = Themes()
        self.themes = themes.items
        self.doc = self.config.get_doc()

        # Créer PyTreeWidget avec des paramètres de thème
        theme_colors = Themes().items['app_color']
        self.configView = PyTreeWidget(           
            radius = 8,
            color = self.themes["app_color"]["text_foreground"],
            selection_color = self.themes["app_color"]["context_color"],
            bg_color = self.themes["app_color"]["bg_one"],
            header_horizontal_color = self.themes["app_color"]["dark_two"],
            header_vertical_color = self.themes["app_color"]["bg_three"],
            bottom_line_color = self.themes["app_color"]["bg_three"],
            grid_line_color = self.themes["app_color"]["bg_two"],
            scroll_bar_bg_color = self.themes["app_color"]["bg_one"],
            scroll_bar_btn_color = self.themes["app_color"]["dark_four"],
            context_color = self.themes["app_color"]["context_color"]
        )
        self.configView.setColumnCount(2)
        self.configView.setHeaderLabels(["Setting", "Value"])




        if self.doc.documentElement.tagName == 'FreePokerToolsConfig':
            self.root = QTreeWidgetItem(["fpdb", None])
            self.configView.addTopLevelItem(self.root)
            self.root.setExpanded(True)
            for elem in self.doc.documentElement.childNodes:
                self.addTreeRows(self.root, elem)

        layout.addWidget(self.configView)

        for column in range(self.configView.columnCount()):
            self.configView.resizeColumnToContents(column)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


    def accept(self):
        QMessageBox.information(self, "Confirmation", "Settings saved successfully!")
        self.close()

    def reject(self):
        QMessageBox.warning(self, "Cancellation", "No changes were saved.")
        self.close()

    def updateConf(self, item, column):
        if column != 1:
            return
        item.setData(1, Qt.UserRole, item.data(1, Qt.DisplayRole))

    def rewriteText(self, s):
        rewrite = {
            'general': 'General', 'supported_databases': 'Databases', 'import': 'Import',
            'hud_ui': 'HUD', 'supported_sites': 'Sites', 'supported_games': 'Games',
            'popup_windows': 'Popup Windows', 'pu': 'Window', 'pu_name': 'Popup Name',
            'pu_stat': 'Stat', 'pu_stat_name': 'Stat Name', 'aux_windows': 'Auxiliary Windows',
            'aw stud_mucked': 'Stud mucked', 'aw mucked': 'Mucked', 'hhcs': 'Hand History Converters',
            'gui_cash_stats': 'Ring Player Stats', 'field_type': 'Field Type', 'col_title': 'Column Heading',
            'xalignment': 'Left/Right Align', 'disp_all': 'Show in Summaries', 'disp_posn': 'Show in Position Stats',
            'col_name': 'Stat Name', 'field_format': 'Format', 'gui_tour_stats': 'Tour Player Stats'
        }
        return rewrite.get(s, s)  # Default to original if not found

    def addTreeRows(self, parent, node):
        if node.nodeType != node.ELEMENT_NODE:
            return
        setting = node.nodeName
        value = node.firstChild.nodeValue if node.firstChild else ""
        item = QTreeWidgetItem(parent, [self.rewriteText(setting), value])
        item.setFlags(item.flags() | Qt.ItemIsEditable)  # Set the item flags to be editable

        if node.hasAttributes():
            for i in range(node.attributes.length):
                attr = node.attributes.item(i)
                attrItem = QTreeWidgetItem([self.rewriteText(attr.localName), attr.value])
                attrItem.setFlags(attrItem.flags() | Qt.ItemIsEditable)  # Also make attributes editable
                item.addChild(attrItem)

        if node.hasChildNodes():
            for elem in node.childNodes:
                self.addTreeRows(item, elem)

