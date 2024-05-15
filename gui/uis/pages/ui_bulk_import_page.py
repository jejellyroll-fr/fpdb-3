from qt_core import *
import Configuration
import Options
import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QFileDialog
from gui.widgets.py_push_button.py_push_button import PyPushButton
from gui.widgets.py_message_box.py_message_box import PyMessageBox
from gui.core.json_themes import Themes

cl_options = '.'.join(sys.argv[1:])
(options, argv) = Options.fpdb_options()

class GuiBulkImport(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        self.resize(600, 350)
        layout = QVBoxLayout(self)
        themes = Themes()
        self.themes = themes.items

        self.importDir = QLineEdit(self.config.get_import_parameters().get('bulkImport-defaultPath', ''))
        hbox = QHBoxLayout()
        hbox.addWidget(self.importDir)
        self.chooseButton = PyPushButton(
            text="Browse...",
            radius=5,
            color=self.themes["app_color"]["text_foreground"],
            bg_color=self.themes["app_color"]["dark_two"],
            bg_color_hover=self.themes["app_color"]["bg_one"],
            bg_color_pressed=self.themes["app_color"]["dark_four"],
            parent=self
        )
        self.chooseButton.setFixedSize(80, 30)
        self.chooseButton.clicked.connect(self.browseClicked)
        hbox.addWidget(self.chooseButton)
        layout.addLayout(hbox)

        self.load_button = PyPushButton(
            text="Bulk Import",
            radius=5,
            color=self.themes["app_color"]["text_foreground"],
            bg_color=self.themes["app_color"]["dark_two"],
            bg_color_hover=self.themes["app_color"]["bg_one"],
            bg_color_pressed=self.themes["app_color"]["dark_four"],
            parent=self
        )
        self.load_button.setFixedSize(80, 30)
        self.load_button.clicked.connect(self.load_clicked)
        layout.addWidget(self.load_button)

    def browseClicked(self):
        if newdir := QFileDialog.getExistingDirectory(
            self,
            caption="Please choose the path that you want to Auto Import",
            directory=self.importDir.text(),
        ):
            self.importDir.setText(newdir)

    def load_clicked(self):
        theme = self.themes['app_color']
        msg_box = PyMessageBox(
            icon=QMessageBox.Information,
            title="Bulk Import",
            text="Bulk import started!",
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
