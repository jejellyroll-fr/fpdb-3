"""Dedicated automatic-note rules configuration dialog."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from fpdb_3_legacy.AutoNotes import (
    autonotes_enabled,
    configured_rule_summary,
    set_autonotes_enabled,
    set_rule_enabled,
    set_rule_note_template,
    set_rule_set_enabled,
)


class AutoNoteRulesDialog(QDialog):
    """Dialog for toggling automatic-note rule sets and individual rules."""

    def __init__(self, config: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.config = config
        self.rule_set_items: dict[QTreeWidgetItem, str] = {}
        self.rule_items: dict[QTreeWidgetItem, tuple[str, str]] = {}

        self.setWindowTitle("Automatic Notes")
        self.resize(760, 520)

        layout = QVBoxLayout(self)

        intro = QLabel("Enable or disable automatic player-note rules.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.enabled_checkbox = QCheckBox("Generate automatic notes")
        self.enabled_checkbox.setChecked(autonotes_enabled(config))
        layout.addWidget(self.enabled_checkbox)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Rule", "Status", "Version", "Template"])
        layout.addWidget(self.tree)

        self._populate_tree()
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_tree(self) -> None:
        for rule_set in configured_rule_summary(self.config):
            rule_set_item = QTreeWidgetItem(
                [
                    rule_set["ruleSet"],
                    "default on" if rule_set["enabledByDefault"] else "default off",
                    "",
                ],
            )
            rule_set_item.setFlags(rule_set_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            rule_set_item.setCheckState(
                0,
                Qt.CheckState.Checked if rule_set["enabled"] else Qt.CheckState.Unchecked,
            )
            self.tree.addTopLevelItem(rule_set_item)
            self.rule_set_items[rule_set_item] = rule_set["ruleSet"]

            for rule in rule_set["rules"]:
                rule_item = QTreeWidgetItem(
                    [
                        f"{rule['id']} - {rule['name']}",
                        "enabled" if rule["enabled"] else "disabled",
                        str(rule["version"]),
                        rule["configuredNoteTemplate"],
                    ],
                )
                rule_item.setFlags(
                    rule_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable,
                )
                rule_item.setCheckState(
                    0,
                    Qt.CheckState.Checked if rule["enabled"] else Qt.CheckState.Unchecked,
                )
                rule_set_item.addChild(rule_item)
                self.rule_items[rule_item] = (rule_set["ruleSet"], rule["id"])

    def apply_changes(self) -> None:
        """Apply widget state back to the XML config document."""
        set_autonotes_enabled(self.config, self.enabled_checkbox.isChecked())

        for item, rule_set_id in self.rule_set_items.items():
            set_rule_set_enabled(
                self.config,
                rule_set_id,
                item.checkState(0) == Qt.CheckState.Checked,
            )

        for item, (rule_set_id, rule_id) in self.rule_items.items():
            set_rule_enabled(
                self.config,
                rule_id,
                item.checkState(0) == Qt.CheckState.Checked,
                rule_set_name=rule_set_id,
            )
            set_rule_note_template(
                self.config,
                rule_id,
                item.text(3),
                rule_set_name=rule_set_id,
            )

    def accept(self) -> None:
        self.apply_changes()
        super().accept()


def exec_auto_note_rules_dialog(config: Any, parent: Any = None) -> bool:
    """Open the automatic-note rules dialog and save accepted changes."""
    dialog = AutoNoteRulesDialog(config, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    if accepted and hasattr(config, "save"):
        config.save()
    return accepted
