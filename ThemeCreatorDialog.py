#!/usr/bin/env python

"""ThemeCreatorDialog.py

Dialog for creating custom themes within fpdb.
Provides a user-friendly interface to create and install custom qt_material themes.
"""

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from loggingFpdb import get_logger

log = get_logger("theme_creator_dialog")


class ColorPickerWidget(QWidget):
    """Widget for picking colors with preview."""

    colorChanged = pyqtSignal(str)  # Emits hex color string

    def __init__(self, label: str, default_color: str = "#3F51B5", parent=None):
        super().__init__(parent)
        self.color = QColor(default_color)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Label
        self.label = QLabel(label)
        self.label.setMinimumWidth(120)
        layout.addWidget(self.label)

        # Color preview button
        self.color_button = QPushButton()
        self.color_button.setFixedSize(40, 25)
        self.color_button.clicked.connect(self.pick_color)
        self.update_button_color()
        layout.addWidget(self.color_button)

        # Hex input
        self.hex_input = QLineEdit(default_color)
        self.hex_input.setMaximumWidth(80)
        self.hex_input.textChanged.connect(self.on_hex_changed)
        layout.addWidget(self.hex_input)

        layout.addStretch()

    def update_button_color(self):
        """Update the color preview button."""
        self.color_button.setStyleSheet(f"background-color: {self.color.name()};")

    def pick_color(self):
        """Open color picker dialog."""
        color = QColorDialog.getColor(self.color, self, "Choose Color")
        if color.isValid():
            self.color = color
            self.hex_input.setText(color.name())
            self.update_button_color()
            self.colorChanged.emit(color.name())

    def on_hex_changed(self, text: str):
        """Handle hex input changes."""
        if text.startswith("#") and len(text) == 7:
            try:
                color = QColor(text)
                if color.isValid():
                    self.color = color
                    self.update_button_color()
                    self.colorChanged.emit(text)
            except:
                pass

    def get_color(self) -> str:
        """Get current color as hex string."""
        return self.color.name()

    def set_color(self, hex_color: str):
        """Set color from hex string."""
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.hex_input.setText(hex_color)
            self.update_button_color()


class ThemeCreatorDialog(QDialog):
    """Dialog for creating custom themes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Custom Theme")
        self.setModal(True)
        self.resize(600, 700)

        # Theme data
        self.theme_colors = {}

        # Setup UI
        self.setup_ui()

        # Load default dark theme
        self.load_preset("Dark")

    def setup_ui(self):
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)

        # Create scroll area for the form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)

        # Theme Information Group
        info_group = QGroupBox("Theme Information")
        info_layout = QFormLayout(info_group)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., my_custom_theme")
        info_layout.addRow("Theme Name:", self.name_input)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Brief description of your theme")
        info_layout.addRow("Description:", self.description_input)

        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Your name")
        info_layout.addRow("Author:", self.author_input)

        form_layout.addWidget(info_group)

        # Theme Preset Group
        preset_group = QGroupBox("Theme Preset")
        preset_layout = QFormLayout(preset_group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Dark", "Light", "Custom"])
        self.preset_combo.currentTextChanged.connect(self.load_preset)
        preset_layout.addRow("Base Theme:", self.preset_combo)

        form_layout.addWidget(preset_group)

        # Colors Group
        colors_group = QGroupBox("Colors")
        colors_layout = QVBoxLayout(colors_group)

        # Color pickers
        self.color_pickers = {}
        color_definitions = [
            ("Primary", "#3F51B5", "Main accent color for buttons and highlights"),
            ("Secondary", "#FF4081", "Secondary accent color"),
            ("Background", "#2b2b2b", "Main background color"),
            ("Surface", "#404040", "Surface color for cards, dialogs, etc."),
            ("Text", "#ffffff", "Primary text color"),
            ("Text Secondary", "#cccccc", "Secondary text color"),
        ]

        for name, default, tooltip in color_definitions:
            picker = ColorPickerWidget(name, default)
            picker.setToolTip(tooltip)
            picker.colorChanged.connect(lambda color, n=name.lower().replace(" ", "_"): self.on_color_changed(n, color))
            self.color_pickers[name.lower().replace(" ", "_")] = picker
            colors_layout.addWidget(picker)

        form_layout.addWidget(colors_group)

        # Preview Group
        preview_group = QGroupBox("Theme Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_text = QTextEdit()
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)

        form_layout.addWidget(preview_group)

        scroll.setWidget(form_widget)
        main_layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()

        self.preview_button = QPushButton("Update Preview")
        self.preview_button.clicked.connect(self.update_preview)
        button_layout.addWidget(self.preview_button)

        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.create_button = QPushButton("Create Theme")
        self.create_button.clicked.connect(self.create_theme)
        self.create_button.setDefault(True)
        button_layout.addWidget(self.create_button)

        main_layout.addLayout(button_layout)

        # Update preview initially
        self.update_preview()

    def load_preset(self, preset_name: str):
        """Load a color preset."""
        if preset_name == "Dark":
            colors = {
                "primary": "#3F51B5",
                "secondary": "#FF4081",
                "background": "#2b2b2b",
                "surface": "#404040",
                "text": "#ffffff",
                "text_secondary": "#cccccc",
            }
        elif preset_name == "Light":
            colors = {
                "primary": "#3F51B5",
                "secondary": "#FF4081",
                "background": "#fafafa",
                "surface": "#ffffff",
                "text": "#212121",
                "text_secondary": "#757575",
            }
        else:  # Custom
            return

        # Update color pickers
        for key, color in colors.items():
            if key in self.color_pickers:
                self.color_pickers[key].set_color(color)

        self.update_preview()

    def on_color_changed(self, name: str, color: str):
        """Handle color changes."""
        self.theme_colors[name] = color
        self.update_preview()

    def update_preview(self):
        """Update the theme preview."""
        # Collect current colors
        colors = {}
        for key, picker in self.color_pickers.items():
            colors[key] = picker.get_color()

        # Generate preview text
        preview_lines = [
            "Theme Preview:",
            "=" * 30,
            f"Primary Color: {colors.get('primary', '#3F51B5')}",
            f"Secondary Color: {colors.get('secondary', '#FF4081')}",
            f"Background: {colors.get('background', '#2b2b2b')}",
            f"Surface: {colors.get('surface', '#404040')}",
            f"Text: {colors.get('text', '#ffffff')}",
            f"Secondary Text: {colors.get('text_secondary', '#cccccc')}",
            "",
            "This theme will be applied to:",
            "• Buttons and controls",
            "• Backgrounds and surfaces",
            "• Text and labels",
            "• Menus and dialogs",
        ]

        self.preview_text.setText("\n".join(preview_lines))

        # Apply preview colors to the preview text
        try:
            bg_color = colors.get("background", "#2b2b2b")
            text_color = colors.get("text", "#ffffff")
            surface_color = colors.get("surface", "#404040")

            self.preview_text.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {surface_color};
                    color: {text_color};
                    border: 1px solid {colors.get('primary', '#3F51B5')};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
        except Exception as e:
            log.warning(f"Error applying preview style: {e}")

    def create_theme(self):
        """Create and install the custom theme."""
        # Validate inputs
        theme_name = self.name_input.text().strip()
        if not theme_name:
            QMessageBox.warning(self, "Error", "Please enter a theme name.")
            return

        # Ensure .xml extension
        if not theme_name.endswith(".xml"):
            theme_name += ".xml"

        description = self.description_input.text().strip() or f"Custom theme: {theme_name}"
        author = self.author_input.text().strip() or "Anonymous"

        # Collect colors
        colors = {}
        for key, picker in self.color_pickers.items():
            colors[key] = picker.get_color()

        try:
            # Generate theme XML
            theme_xml = self.generate_theme_xml(theme_name, description, author, colors)

            # Install theme using ThemeManager
            from ThemeManager import ThemeManager

            theme_manager = ThemeManager()

            # Create temporary file and install
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
                f.write(theme_xml)
                f.flush()  # Ensure content is written to disk
                temp_path = f.name

            try:
                # Debug: log the generated XML content
                log.info(f"Generated theme XML for {theme_name}:")
                log.info(f"XML content preview: {theme_xml[:500]}...")

                success = theme_manager.install_custom_theme(temp_path, theme_name)
                if success:
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Theme '{theme_name}' has been created and installed!\n\n"
                        f"You can now select it from the Themes menu.",
                    )
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Failed to install the theme.")
            finally:
                # Clean up temporary file
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            log.exception(f"Error creating theme: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create theme:\n{str(e)}")

    def generate_theme_xml(self, name: str, description: str, author: str, colors: dict[str, str]) -> str:
        """Generate theme XML content in qt_material compatible format."""

        # Map our colors to qt_material format
        # For dark themes, use dark background colors
        is_dark_theme = self._is_dark_color(colors["background"])

        if is_dark_theme:
            secondary_color = colors["background"]
            secondary_light = self._lighten_color(colors["background"], 0.2)
            secondary_dark = self._darken_color(colors["background"], 0.2)
            primary_text = colors["text"]
            secondary_text = colors["text"]
        else:
            secondary_color = colors["background"]
            secondary_light = self._lighten_color(colors["background"], 0.1)
            secondary_dark = self._darken_color(colors["background"], 0.1)
            primary_text = colors["text"]
            secondary_text = colors["text"]

        return f"""<!--?xml version="1.0" encoding="UTF-8"?-->
<!--
Custom Theme: {description}
Author: {author}
Created with fpdb Theme Creator
-->
<resources>
  <color name="primaryColor">{colors['primary']}</color>
  <color name="primaryLightColor">{self._lighten_color(colors['primary'], 0.2)}</color>
  <color name="secondaryColor">{secondary_color}</color>
  <color name="secondaryLightColor">{secondary_light}</color>
  <color name="secondaryDarkColor">{secondary_dark}</color>
  <color name="primaryTextColor">{primary_text}</color>
  <color name="secondaryTextColor">{secondary_text}</color>
</resources>"""

    def _is_dark_color(self, hex_color: str) -> bool:
        """Check if a color is dark by calculating its luminance."""
        # Remove # and convert to RGB
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Calculate luminance
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5

    def _lighten_color(self, hex_color: str, factor: float) -> str:
        """Lighten a color by a given factor (0.0 to 1.0)."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Lighten by moving towards white
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))

        return f"#{r:02x}{g:02x}{b:02x}"

    def _darken_color(self, hex_color: str, factor: float) -> str:
        """Darken a color by a given factor (0.0 to 1.0)."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Darken by moving towards black
        r = max(0, int(r * (1 - factor)))
        g = max(0, int(g * (1 - factor)))
        b = max(0, int(b * (1 - factor)))

        return f"#{r:02x}{g:02x}{b:02x}"


def show_theme_creator(parent=None):
    """Show the theme creator dialog."""
    dialog = ThemeCreatorDialog(parent)
    return dialog.exec_()


if __name__ == "__main__":
    # Test the dialog
    import sys

    app = QApplication(sys.argv)

    result = show_theme_creator()
    print(f"Dialog result: {result}")

    sys.exit()
