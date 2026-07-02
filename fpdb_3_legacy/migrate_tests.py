from __future__ import annotations

import os
import re


def migrate_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    new_content = content

    # Replace imports
    new_content = new_content.replace("from PyQt5.QtCore", "from PySide6.QtCore")
    new_content = new_content.replace("from PyQt5.QtWidgets", "from PySide6.QtWidgets")
    new_content = new_content.replace("from PyQt5.QtGui", "from PySide6.QtGui")
    new_content = new_content.replace("import PyQt5.QtCore", "import PySide6.QtCore")
    new_content = new_content.replace("import PyQt5.QtWidgets", "import PySide6.QtWidgets")
    new_content = new_content.replace("import PyQt5.QtGui", "import PySide6.QtGui")

    # Replace exec_() with exec()
    new_content = new_content.replace(".exec_()", ".exec()")

    # Replace QAction triggers if any (PyQt5 uses triggered.connect, PySide6 too, but sometimes signal names differ slightly, usually compatible)

    if content != new_content:
        print(f"Migrating {filepath}")
        with open(filepath, "w") as f:
            f.write(new_content)
    else:
        print(f"No changes for {filepath}")


def main():
    test_dir = "./test"
    for root, dirs, files in os.walk(test_dir):
        for file in files:
            if file.endswith(".py"):
                migrate_file(os.path.join(root, file))


if __name__ == "__main__":
    main()
