# IMPORT QT CORE
# ///////////////////////////////////////////////////////////////
from qt_core import *

# IMPORT STYLE
# ///////////////////////////////////////////////////////////////
from . style import *

# CUSTOM MESSAGE BOX
# ///////////////////////////////////////////////////////////////
class PyMessageBox(QMessageBox):
    def __init__(
        self,
        icon,
        title,
        text,
        buttons=QMessageBox.Ok,
        parent=None,
        radius=10,
        text_color="#FFF",
        bg_color="#333",
        button_text_color="#FFF",
        button_bg_color="#555",
        button_hover_bg_color="#666",
        button_pressed_bg_color="#777",
        button_radius=5
    ):
        super().__init__(parent)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self.setIcon(icon)
        self.setWindowTitle(title)
        self.setText(text)
        self.setStandardButtons(buttons)

        # Apply custom style
        self.setCustomStyle(
            radius,
            text_color,
            bg_color,
            button_text_color,
            button_bg_color,
            button_hover_bg_color,
            button_pressed_bg_color,
            button_radius
        )

    def setCustomStyle(
        self,
        radius,
        text_color,
        bg_color,
        button_text_color,
        button_bg_color,
        button_hover_bg_color,
        button_pressed_bg_color,
        button_radius
    ):
        # Define the style string within the method or import it

        custom_style = style.format(
            _text_color=text_color,
            _bg_color=bg_color,
            _radius=radius,
            _button_text_color=button_text_color,
            _button_bg_color=button_bg_color,
            _button_hover_bg_color=button_hover_bg_color,
            _button_pressed_bg_color=button_pressed_bg_color,
            _button_radius=button_radius
        )
        self.setStyleSheet(custom_style)
