from bs4 import Stylesheet
from qt_core import *

import xml.dom.minidom
from xml.dom.minidom import Node
import Configuration
import Options
import sys
cl_options = '.'.join(sys.argv[1:])
(options, argv) = Options.fpdb_options()
from gui.widgets.py_tree_widget.py_tree_widget import PyTreeWidget
from gui.widgets.py_push_button.py_push_button import PyPushButton
from gui.widgets.py_message_box.py_message_box import PyMessageBox
from gui.core.json_themes import Themes
from gui.core.json_settings import Settings

class GuiPrefs(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

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
            bg_color = self.themes["app_color"]["dark_four"],
            header_horizontal_color = self.themes["app_color"]["dark_two"],
            header_vertical_color = self.themes["app_color"]["dark_four"],
            bottom_line_color = self.themes["app_color"]["dark_four"],
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

        # Create custom buttons with specific size
        save_btn = PyPushButton(
            text="Save",
            radius=5,
            color=self.themes["app_color"]["text_foreground"],
            bg_color=self.themes["app_color"]["dark_two"],
            bg_color_hover=self.themes["app_color"]["bg_one"],
            bg_color_pressed=self.themes["app_color"]["dark_four"],
            parent=self
        )
        save_btn.setFixedSize(80, 30)  # Set fixed size for button

        cancel_btn = PyPushButton(
            text="Cancel",
            radius=5,
            color=self.themes["app_color"]["text_foreground"],
            bg_color=self.themes["app_color"]["dark_two"],
            bg_color_hover=self.themes["app_color"]["bg_one"],
            bg_color_pressed=self.themes["app_color"]["dark_four"],
            parent=self
        )
        cancel_btn.setFixedSize(80, 30)  # Set fixed size for button

        # Connect button signals
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        # Add buttons to the layout aligned to the right
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # This will push the buttons to the right
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)



    def accept(self):
        theme = self.themes['app_color']  # Utilisez self.themes déjà initialisé
        msg_box = PyMessageBox(
            icon=QMessageBox.Information,
            title="Confirmation",
            text="Settings saved successfully!",
            parent=self,
            radius=5,
            text_color=theme["text_foreground"],
            bg_color=theme["dark_three"],
            button_text_color=theme["text_foreground"],
            button_bg_color=theme["dark_two"],
            button_hover_bg_color=theme["context_hover"],
            button_pressed_bg_color=theme["context_pressed"],
            button_radius=5
        )
        msg_box.exec_()
        self.close()

    def reject(self):
        theme = self.themes['app_color']  # Utilisez self.themes déjà initialisé
        msg_box = PyMessageBox(
            icon=QMessageBox.Warning,
            title="Cancellation",
            text="No changes were saved.",
            parent=self,
            radius=5,
            text_color=theme["text_foreground"],
            bg_color=theme["dark_three"],
            button_text_color=theme["text_foreground"],
            button_bg_color=theme["dark_two"],
            button_hover_bg_color=theme["context_hover"],
            button_pressed_bg_color=theme["context_pressed"],
            button_radius=5
        )
        msg_box.exec_()
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

