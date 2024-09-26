import pytest
from unittest.mock import MagicMock, patch
import types
import sys
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QApplication, QLineEdit, QComboBox
from PyQt5.QtCore import QCoreApplication, QDate, Qt, QPoint
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

# Détecter l'OS actuel
current_os = sys.platform
if current_os.startswith('win'):
    win_tables_module = types.ModuleType('WinTables')
    win_tables_module.Table = MagicMock()
    with patch.dict('sys.modules', {'WinTables': win_tables_module}):
        import fpdb
elif current_os.startswith('darwin'):
    osx_tables_module = types.ModuleType('OSXTables')
    osx_tables_module.Table = MagicMock()
    with patch.dict('sys.modules', {'OSXTables': osx_tables_module}):
        import fpdb
else:
    x_tables_module = types.ModuleType('XTables')
    x_tables_module.Table = MagicMock()
    with patch.dict('sys.modules', {'XTables': x_tables_module}):
        import fpdb

@pytest.fixture(scope="module")
def app(qapp):
    return qapp

def test_get_text(app):
    # Test avec un QLineEdit
    line_edit = QLineEdit()
    line_edit.setText("Test Text")
    assert fpdb.fpdb.get_text(line_edit) == "Test Text"

    # Test avec un QComboBox
    combo_box = QComboBox()
    combo_box.addItems(["Item 1", "Item 2", "Item 3"])
    combo_box.setCurrentIndex(1)
    assert fpdb.fpdb.get_text(combo_box) == "Item 2"

    # Test avec un widget non supporté
    unsupported_widget = QApplication.instance()
    with pytest.raises(AttributeError):
        fpdb.fpdb.get_text(unsupported_widget)