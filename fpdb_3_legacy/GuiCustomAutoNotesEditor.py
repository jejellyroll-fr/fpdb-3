"""Custom Auto Notes Creator and Visual Editor UI component for FPDB 3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.AutoNoteRules import PreflopContext
from fpdb_3_legacy.AutoNotes import configured_rule_summary
from fpdb_3_legacy.Configuration import GRAPHICS_PATH
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.user_autonotes_parser import (
    compile_custom_rule,
    load_user_autonotes_data,
    save_user_autonotes_data,
)

log = get_logger("gui_custom_autonotes_editor")

_CARD_PIXMAP_CACHE: dict[tuple[str, str, int, int], QPixmap] = {}

FIELD_OPTIONS = [
    ("Game Variant", "game.base"),
    ("Game Category", "game.category"),
    ("Game Limit", "game.limit"),
    ("Player Position", "player.position"),
    ("Opponent Position", "opponent.position"),
    ("Effective Stack (BB)", "player.eff_stack_bb"),
    ("Flop SPR", "spr.flop"),
    ("Preflop Action", "action.preflop"),
    ("Flop Action", "action.flop"),
    ("Turn Action", "action.turn"),
    ("River Action", "action.river"),
    ("Made Hand Rank", "hand.rank"),
    ("Flop Texture", "board.flop_texture"),
]

OPERATOR_OPTIONS = [
    ("IS (=)", "eq"),
    ("IS NOT (!=)", "neq"),
    ("Less than or equal (<=)", "lte"),
    ("Greater than or equal (>=)", "gte"),
    ("Less than (<)", "lt"),
    ("Greater than (>)", "gt"),
    ("IN (list)", "in"),
    ("NOT IN", "not_in"),
    ("BETWEEN [min, max]", "between"),
    ("CONTAINS", "contains"),
]


class _ConditionRowWidget(QWidget):
    """Single condition block row in the Visual Condition Builder."""

    removed = Signal(object)

    def __init__(self, condition_data: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui(condition_data or {})

    def _build_ui(self, data: dict[str, Any]) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        self.field_combo = QComboBox()
        for label, val in FIELD_OPTIONS:
            self.field_combo.addItem(label, val)

        initial_field = data.get("field", "game.base")
        idx = self.field_combo.findData(initial_field)
        if idx >= 0:
            self.field_combo.setCurrentIndex(idx)
        layout.addWidget(self.field_combo, 2)

        self.op_combo = QComboBox()
        for label, val in OPERATOR_OPTIONS:
            self.op_combo.addItem(label, val)

        initial_op = data.get("operator", "eq")
        idx = self.op_combo.findData(initial_op)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)
        layout.addWidget(self.op_combo, 2)

        val_str = data.get("value", "")
        if isinstance(val_str, (list, tuple)):
            val_str = ", ".join(str(x) for x in val_str)

        self.val_edit = QLineEdit(str(val_str))
        self.val_edit.setPlaceholderText("Value (e.g. holdem, BTN, 15.0, CO, BTN, SB)")
        layout.addWidget(self.val_edit, 3)

        self.remove_btn = QPushButton("❌")
        self.remove_btn.setToolTip(_("Remove Condition"))
        self.remove_btn.setFixedWidth(32)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self.remove_btn)

    def to_dict(self) -> dict[str, Any]:
        field = self.field_combo.currentData()
        op = self.op_combo.currentData()
        raw_val = self.val_edit.text().strip()

        if op in ("in", "not_in"):
            parsed_val: Any = [v.strip() for v in raw_val.split(",") if v.strip()]
        elif op == "between":
            parts = [v.strip() for v in raw_val.split(",") if v.strip()]
            try:
                parsed_val = [float(parts[0]), float(parts[1])] if len(parts) >= 2 else [0.0, 0.0]
            except ValueError:
                parsed_val = [0.0, 0.0]
        else:
            try:
                if "." in raw_val:
                    parsed_val = float(raw_val)
                else:
                    parsed_val = int(raw_val)
            except ValueError:
                parsed_val = raw_val

        return {"field": field, "operator": op, "value": parsed_val}


class GuiCustomAutoNotesEditor(QWidget):
    """Custom Auto Notes Creator and Visual Editor Panel."""

    rules_saved = Signal()

    def __init__(self, config: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.user_data: dict[str, Any] = {"version": 1, "custom_rule_sets": []}
        self.current_rule_dict: dict[str, Any] | None = None
        self.condition_rows: list[_ConditionRowWidget] = []

        self._build_ui()
        self.load_rules()

    def _build_ui(self) -> None:  # noqa: PLR0915
        main_layout = QVBoxLayout(self)

        # Header Action Toolbar
        toolbar = QHBoxLayout()
        self.btn_new = QPushButton(_("+ New Rule"))
        self.btn_new.clicked.connect(self.on_new_rule)
        toolbar.addWidget(self.btn_new)

        self.btn_duplicate = QPushButton(_("📋 Duplicate"))
        self.btn_duplicate.clicked.connect(self.on_duplicate_rule)
        toolbar.addWidget(self.btn_duplicate)

        self.btn_delete = QPushButton(_("🗑️ Delete"))
        self.btn_delete.clicked.connect(self.on_delete_rule)
        toolbar.addWidget(self.btn_delete)

        toolbar.addStretch(1)

        self.btn_save = QPushButton(_("💾 Save Rules"))
        self.btn_save.setStyleSheet("font-weight: bold; background-color: #059669; color: white;")
        self.btn_save.clicked.connect(self.on_save_rules)
        toolbar.addWidget(self.btn_save)

        self.btn_sandbox = QPushButton(_("🧪 Test Sandbox"))
        self.btn_sandbox.clicked.connect(self.on_toggle_sandbox)
        toolbar.addWidget(self.btn_sandbox)

        main_layout.addLayout(toolbar)

        # Splitter: Tree on Left, Editor on Right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel: Tree Widget
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(_("Rule Sets & Custom Rules")))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("Rule / Group"), _("ID")])
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        left_layout.addWidget(self.tree)
        splitter.addWidget(left_widget)

        # Right Panel: Rule Editor Form
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)

        right_widget = QWidget()
        self.editor_layout = QVBoxLayout(right_widget)

        # Basic Info Group
        info_group = QGroupBox(_("Rule Metadata"))
        info_layout = QVBoxLayout(info_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(_("Rule Name:")))
        self.edit_name = QLineEdit()
        self.edit_name.textChanged.connect(self._sync_current_rule)
        row1.addWidget(self.edit_name, 2)

        row1.addWidget(QLabel(_("Rule ID:")))
        self.edit_id = QLineEdit()
        self.edit_id.textChanged.connect(self._sync_current_rule)
        row1.addWidget(self.edit_id, 2)
        info_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(_("Rule Set:")))
        self.edit_ruleset = QLineEdit()
        self.edit_ruleset.setText("custom_user_rules")
        self.edit_ruleset.textChanged.connect(self._sync_current_rule)
        row2.addWidget(self.edit_ruleset, 2)

        self.chk_enabled = QCheckBox(_("Enabled"))
        self.chk_enabled.setChecked(True)
        self.chk_enabled.toggled.connect(self._sync_current_rule)
        row2.addWidget(self.chk_enabled)
        info_layout.addLayout(row2)

        row3 = QVBoxLayout()
        row3.addWidget(QLabel(_("Note Template (Tags: {player}, {hole}, {flop}, {eff_stack_bb}, {pot}, {spr}):")))
        self.edit_template = QLineEdit()
        self.edit_template.setPlaceholderText("{player} 3-Bet Shove Preflop {eff_stack_bb}BB with {hole}")
        self.edit_template.textChanged.connect(self._sync_current_rule)
        row3.addWidget(self.edit_template)
        info_layout.addLayout(row3)

        self.editor_layout.addWidget(info_group)

        # Visual Condition Builder Group
        cond_group = QGroupBox(_("Logical Conditions (No-Code GUI)"))
        cond_layout = QVBoxLayout(cond_group)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel(_("Root Operator:")))
        self.root_op_combo = QComboBox()
        self.root_op_combo.addItems(["AND", "OR", "NOT"])
        self.root_op_combo.currentIndexChanged.connect(self._sync_current_rule)
        op_row.addWidget(self.root_op_combo)

        btn_add_cond = QPushButton(_("➕ Add Condition"))
        btn_add_cond.clicked.connect(self.on_add_condition_row)
        op_row.addWidget(btn_add_cond)
        op_row.addStretch(1)
        cond_layout.addLayout(op_row)

        self.cond_rows_container = QVBoxLayout()
        cond_layout.addLayout(self.cond_rows_container)

        self.editor_layout.addWidget(cond_group)

        # Evidence Schema Group
        evidence_group = QGroupBox(_("Captured Evidence Schema"))
        ev_layout = QHBoxLayout(evidence_group)
        self.chk_ev_hole = QCheckBox(_("Hole Cards ({hole})"))
        self.chk_ev_hole.setChecked(True)
        self.chk_ev_hole.toggled.connect(self._sync_current_rule)
        ev_layout.addWidget(self.chk_ev_hole)

        self.chk_ev_board = QCheckBox(_("Board ({flop})"))
        self.chk_ev_board.setChecked(True)
        self.chk_ev_board.toggled.connect(self._sync_current_rule)
        ev_layout.addWidget(self.chk_ev_board)

        self.chk_ev_stack = QCheckBox(_("Stack & SPR"))
        self.chk_ev_stack.setChecked(True)
        self.chk_ev_stack.toggled.connect(self._sync_current_rule)
        ev_layout.addWidget(self.chk_ev_stack)

        self.chk_ev_actions = QCheckBox(_("Actions"))
        self.chk_ev_actions.setChecked(True)
        self.chk_ev_actions.toggled.connect(self._sync_current_rule)
        ev_layout.addWidget(self.chk_ev_actions)

        self.editor_layout.addWidget(evidence_group)

        # Live Testing Sandbox Panel
        self.sandbox_group = QGroupBox(_("Live Testing Sandbox"))
        sb_layout = QVBoxLayout(self.sandbox_group)
        sb_layout.setSpacing(8)

        sb_input_row = QHBoxLayout()
        sb_input_row.addWidget(QLabel(_("Test Source (Raw Hand History Text):")))
        sb_input_row.addStretch(1)
        self.btn_eval_sandbox = QPushButton(_("🧪 Evaluate Rule"))
        self.btn_eval_sandbox.setStyleSheet(
            "font-weight: bold; background-color: #2563eb; color: white; border-radius: 6px; padding: 6px 16px;"
        )
        self.btn_eval_sandbox.clicked.connect(self.on_evaluate_sandbox)
        sb_input_row.addWidget(self.btn_eval_sandbox)
        sb_layout.addLayout(sb_input_row)

        self.txt_sandbox_hh = QPlainTextEdit()
        self.txt_sandbox_hh.setPlaceholderText(_("Paste raw GGPoker or PokerStars hand history text here to test..."))
        self.txt_sandbox_hh.setMaximumHeight(100)
        self.txt_sandbox_hh.setStyleSheet(
            "background: #0f172a; color: #f8fafc; font-family: monospace; border: 1px solid #334155; border-radius: 6px; padding: 6px;"
        )
        sb_layout.addWidget(self.txt_sandbox_hh)

        sb_result_row = QHBoxLayout()
        self.lbl_sandbox_status = QLabel(_("Status: READY"))
        self.lbl_sandbox_status.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 6px 12px; border-radius: 6px; background: #334155; color: #f8fafc;"
        )
        sb_result_row.addWidget(self.lbl_sandbox_status)
        sb_result_row.addStretch(1)
        sb_layout.addLayout(sb_result_row)

        self.lbl_sandbox_note = QLabel(_("Generated Note: (None)"))
        self.lbl_sandbox_note.setWordWrap(True)
        self.lbl_sandbox_note.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #f8fafc; background-color: #0f172a; "
            "border: 1px solid #38bdf8; border-radius: 6px; padding: 10px 14px;"
        )
        sb_layout.addWidget(self.lbl_sandbox_note)

        self.cards_sandbox_container = QHBoxLayout()
        self.cards_sandbox_container.setSpacing(4)
        sb_layout.addLayout(self.cards_sandbox_container)

        self.editor_layout.addWidget(self.sandbox_group)
        self.sandbox_group.setVisible(True)

        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)

        splitter.setSizes([260, 600])
        main_layout.addWidget(splitter)

    def load_rules(self) -> None:
        self.user_data = load_user_autonotes_data()
        self._populate_tree()

    def _populate_tree(self) -> None:
        self.tree.clear()

        # Custom Rule Sets
        custom_sets = self.user_data.get("custom_rule_sets", [])
        if not custom_sets:
            # Ensure at least default custom rule set
            custom_sets = [
                {
                    "rule_set_id": "custom_user_rules",
                    "name": "User Custom Rules",
                    "enabled": True,
                    "rules": [],
                }
            ]
            self.user_data["custom_rule_sets"] = custom_sets

        for rset in custom_sets:
            set_item = QTreeWidgetItem([rset.get("name", "Custom Rules"), rset.get("rule_set_id", "")])
            set_item.setFlags(set_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            set_item.setCheckState(0, Qt.CheckState.Checked if rset.get("enabled", True) else Qt.CheckState.Unchecked)
            set_item.setData(0, Qt.ItemDataRole.UserRole, rset)

            for rule in rset.get("rules", []):
                rule_item = QTreeWidgetItem([f"  ☑️ {rule.get('name', 'Rule')}", rule.get("rule_id", "")])
                rule_item.setData(0, Qt.ItemDataRole.UserRole, rule)
                set_item.addChild(rule_item)

            self.tree.addTopLevelItem(set_item)

        self.tree.expandAll()

        # Built-in summary for reference
        builtin_sets = configured_rule_summary(self.config)
        for bset in builtin_sets:
            b_item = QTreeWidgetItem([f"🔒 {bset['ruleSet']}", "builtin"])
            b_item.setDisabled(True)
            for brule in bset.get("rules", []):
                br_item = QTreeWidgetItem([f"    {brule['name']}", brule["id"]])
                br_item.setDisabled(True)
                b_item.addChild(br_item)
            self.tree.addTopLevelItem(b_item)

    def on_tree_selection_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "rule_id" in data:
            self._load_rule_into_editor(data)

    def _load_rule_into_editor(self, rule_dict: dict[str, Any]) -> None:
        self.current_rule_dict = rule_dict

        self.edit_name.blockSignals(True)
        self.edit_id.blockSignals(True)
        self.edit_ruleset.blockSignals(True)
        self.edit_template.blockSignals(True)
        self.chk_enabled.blockSignals(True)
        self.root_op_combo.blockSignals(True)
        self.chk_ev_hole.blockSignals(True)
        self.chk_ev_board.blockSignals(True)
        self.chk_ev_stack.blockSignals(True)
        self.chk_ev_actions.blockSignals(True)

        self.edit_name.setText(rule_dict.get("name", ""))
        self.edit_id.setText(rule_dict.get("rule_id", ""))
        self.edit_ruleset.setText("custom_user_rules")
        self.edit_template.setText(rule_dict.get("note_template", ""))
        self.chk_enabled.setChecked(rule_dict.get("enabled", True))

        conds = rule_dict.get("conditions", {})
        root_op = conds.get("operator", "AND")
        idx = self.root_op_combo.findText(root_op)
        if idx >= 0:
            self.root_op_combo.setCurrentIndex(idx)

        # Clear condition rows
        self._clear_condition_rows()

        rules_list = conds.get("rules", [])
        if not rules_list and "field" in conds:
            rules_list = [conds]

        for cond_item in rules_list:
            if isinstance(cond_item, dict):
                self._add_condition_row_widget(cond_item)

        ev = rule_dict.get("evidence", {})
        self.chk_ev_hole.setChecked(ev.get("capture_hole", True))
        self.chk_ev_board.setChecked(ev.get("capture_board", True))
        self.chk_ev_stack.setChecked(ev.get("capture_eff_stack", True))
        self.chk_ev_actions.setChecked(ev.get("capture_action_sequence", True))

        self.edit_name.blockSignals(False)
        self.edit_id.blockSignals(False)
        self.edit_ruleset.blockSignals(False)
        self.edit_template.blockSignals(False)
        self.chk_enabled.blockSignals(False)
        self.root_op_combo.blockSignals(False)
        self.chk_ev_hole.blockSignals(False)
        self.chk_ev_board.blockSignals(False)
        self.chk_ev_stack.blockSignals(False)
        self.chk_ev_actions.blockSignals(False)

    def _clear_condition_rows(self) -> None:
        for row in self.condition_rows:
            self.cond_rows_container.removeWidget(row)
            row.deleteLater()
        self.condition_rows.clear()

    def _add_condition_row_widget(self, data: dict[str, Any] | None = None) -> None:
        row_widget = _ConditionRowWidget(data, self)
        row_widget.removed.connect(self.on_remove_condition_row)
        self.condition_rows.append(row_widget)
        self.cond_rows_container.addWidget(row_widget)

    def on_add_condition_row(self) -> None:
        self._add_condition_row_widget()
        self._sync_current_rule()

    def on_remove_condition_row(self, row_widget: _ConditionRowWidget) -> None:
        if row_widget in self.condition_rows:
            self.condition_rows.remove(row_widget)
            self.cond_rows_container.removeWidget(row_widget)
            row_widget.deleteLater()
            self._sync_current_rule()

    def _sync_current_rule(self) -> None:
        if not self.current_rule_dict:
            return

        self.current_rule_dict["name"] = self.edit_name.text().strip()
        self.current_rule_dict["rule_id"] = self.edit_id.text().strip()
        self.current_rule_dict["note_template"] = self.edit_template.text().strip()
        self.current_rule_dict["enabled"] = self.chk_enabled.isChecked()

        cond_rules = [row.to_dict() for row in self.condition_rows]
        self.current_rule_dict["conditions"] = {
            "operator": self.root_op_combo.currentText(),
            "rules": cond_rules,
        }

        self.current_rule_dict["evidence"] = {
            "capture_hole": self.chk_ev_hole.isChecked(),
            "capture_board": self.chk_ev_board.isChecked(),
            "capture_eff_stack": self.chk_ev_stack.isChecked(),
            "capture_action_sequence": self.chk_ev_actions.isChecked(),
        }

    def _existing_rule_ids(self) -> set[str]:
        return {
            str(rule.get("rule_id", ""))
            for cset in self.user_data.get("custom_rule_sets", [])
            for rule in cset.get("rules", [])
        }

    def _unique_rule_id(self, candidate: str) -> str:
        """Return `candidate`, suffixed if needed so no two rules share an id.

        Generated notes are keyed by rule id, so a collision makes a note
        impossible to attribute. Both entry points can produce one: duplicating
        the same rule twice yields `<id>_copy` twice, and numbering new rules by
        list length repeats an id as soon as an earlier rule was deleted.
        """
        existing = self._existing_rule_ids()
        if candidate not in existing:
            return candidate
        suffix = 2
        while f"{candidate}_{suffix}" in existing:
            suffix += 1
        return f"{candidate}_{suffix}"

    def on_new_rule(self) -> None:
        custom_sets = self.user_data.setdefault("custom_rule_sets", [])
        if not custom_sets:
            custom_sets.append({"rule_set_id": "custom_user_rules", "name": "User Custom Rules", "enabled": True, "rules": []})
        cset = custom_sets[0]

        count = len(cset.get("rules", [])) + 1
        new_rule = {
            "rule_id": self._unique_rule_id(f"custom_rule_{count}"),
            "version": 1,
            "name": f"Custom Rule #{count}",
            "note_template": "{player} action with {hole} (Stack: {eff_stack_bb}bb)",
            "enabled": True,
            "conditions": {
                "operator": "AND",
                "rules": [{"field": "game.base", "operator": "eq", "value": "holdem"}],
            },
            "evidence": {
                "capture_hole": True,
                "capture_board": True,
                "capture_eff_stack": True,
                "capture_action_sequence": True,
            },
        }

        cset.setdefault("rules", []).append(new_rule)
        self._populate_tree()
        self._load_rule_into_editor(new_rule)

    def on_duplicate_rule(self) -> None:
        if not self.current_rule_dict:
            return
        custom_sets = self.user_data.setdefault("custom_rule_sets", [])
        if not custom_sets:
            return
        cset = custom_sets[0]

        dupe = json.loads(json.dumps(self.current_rule_dict))
        dupe["rule_id"] = self._unique_rule_id(f"{dupe.get('rule_id', 'rule')}_copy")
        dupe["name"] = f"{dupe.get('name', 'Rule')} (Copy)"

        cset.setdefault("rules", []).append(dupe)
        self._populate_tree()
        self._load_rule_into_editor(dupe)

    def on_delete_rule(self) -> None:
        if not self.current_rule_dict:
            return

        res = QMessageBox.question(
            self,
            _("Delete Rule"),
            _("Are you sure you want to delete rule '%s'?") % self.current_rule_dict.get("name"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        # Match on identity, not equality: two rules can hold identical content,
        # and list.remove() would then drop the first match instead of the one
        # the user selected.
        for cset in self.user_data.get("custom_rule_sets", []):
            rules = cset.get("rules", [])
            for index, rule in enumerate(rules):
                if rule is self.current_rule_dict:
                    del rules[index]
                    break
            else:
                continue
            break

        self.current_rule_dict = None
        self._populate_tree()
        self._clear_condition_rows()

    def _duplicate_rule_ids(self) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for cset in self.user_data.get("custom_rule_sets", []):
            for rule in cset.get("rules", []):
                rule_id = str(rule.get("rule_id", ""))
                if rule_id in seen and rule_id not in duplicates:
                    duplicates.append(rule_id)
                seen.add(rule_id)
        return duplicates

    def on_save_rules(self) -> None:
        self._sync_current_rule()

        # The id field is free text, so the generated ids can still be edited into
        # a collision. Refuse rather than rename silently: notes are keyed by rule
        # id, and renaming someone's rule would orphan the notes it already wrote.
        duplicates = self._duplicate_rule_ids()
        if duplicates:
            QMessageBox.warning(
                self,
                _("Duplicate Rule IDs"),
                _("These rule IDs are used more than once: %s\n\nGive each rule a unique ID before saving.")
                % ", ".join(duplicates),
            )
            return

        save_user_autonotes_data(self.user_data)
        QMessageBox.information(self, _("Saved"), _("Custom Auto Notes rules saved successfully!"))
        self.rules_saved.emit()
        self._populate_tree()

    def on_toggle_sandbox(self) -> None:
        visible = self.sandbox_group.isVisible()
        self.sandbox_group.setVisible(not visible)

    def on_evaluate_sandbox(self) -> None:
        self._sync_current_rule()
        if not self.current_rule_dict:
            QMessageBox.warning(self, _("No Rule"), _("Please select or create a rule to evaluate."))
            return

        hh_text = self.txt_sandbox_hh.toPlainText().strip()
        if not hh_text:
            QMessageBox.warning(self, _("Empty HH"), _("Please paste a Hand History text to evaluate against."))
            return

        try:
            cfg = self.config
            if cfg is None:
                from fpdb_3_legacy.Configuration import Config
                cfg = Config()

            from fpdb_3_legacy.GGPokerToFpdb import GGPoker
            from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

            if "PokerStars" in hh_text:
                parser = PokerStars(config=cfg, in_path="-", out_path="-", autostart=False)
            else:
                parser = GGPoker(config=cfg, in_path="-", out_path="-", autostart=False)

            parser.whole_file = hh_text
            hand = parser.processHand(hh_text)
        except Exception as e:
            self.lbl_sandbox_status.setText(f"Status: PARSE ERROR ({e})")
            self.lbl_sandbox_status.setStyleSheet("font-weight: bold; background: #fecdd3; color: #9f1239;")
            return

        rule = compile_custom_rule(self.current_rule_dict)
        context = PreflopContext.from_hand(hand)

        players = [p[1] for p in getattr(hand, "players", []) if len(p) > 1]
        player_name = "Hero" if "Hero" in players else (players[0] if players else "Hero")

        # Fallback IDs for sandbox mode evaluation
        if not getattr(hand, "playerIds", None):
            hand.playerIds = {p: idx + 1 for idx, p in enumerate(players)}
        if getattr(hand, "dbid_hands", None) is None:
            setattr(hand, "dbid_hands", getattr(hand, "handid", 1))

        note = rule.evaluate(hand, player_name, context)

        if note:
            self.lbl_sandbox_status.setText("Status: ✅ MATCH")
            self.lbl_sandbox_status.setStyleSheet(
                "font-weight: bold; font-size: 13px; padding: 6px 12px; border-radius: 6px; background: #166534; color: #ffffff;"
            )
            self.lbl_sandbox_note.setText(f"Generated Note: {note.note_text}")
            self.lbl_sandbox_note.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #f8fafc; background-color: #0f172a; "
                "border: 1px solid #22c55e; border-radius: 6px; padding: 10px 14px;"
            )
            self._render_sandbox_cards(note.evidence.get("hole", []), note.evidence.get("flop", []))
        else:
            self.lbl_sandbox_status.setText("Status: ❌ NO MATCH")
            self.lbl_sandbox_status.setStyleSheet(
                "font-weight: bold; font-size: 13px; padding: 6px 12px; border-radius: 6px; background: #991b1b; color: #ffffff;"
            )
            self.lbl_sandbox_note.setText("Generated Note: (Condition predicate evaluated to False)")
            self.lbl_sandbox_note.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #fca5a5; background-color: #0f172a; "
                "border: 1px solid #ef4444; border-radius: 6px; padding: 10px 14px;"
            )
            self._clear_sandbox_cards()

    def _clear_sandbox_cards(self) -> None:
        while self.cards_sandbox_container.count():
            item = self.cards_sandbox_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_sandbox_cards(self, hole_cards: list[str], board_cards: list[str]) -> None:
        self._clear_sandbox_cards()

        all_cards = [(c, "hole") for c in hole_cards] + [(c, "board") for c in board_cards]
        if not all_cards:
            return

        if hole_cards:
            lbl_h = QLabel(_("Hole:"))
            lbl_h.setStyleSheet("font-weight: bold; color: #a78bfa; font-size: 12px;")
            self.cards_sandbox_container.addWidget(lbl_h)

        for idx, (card_str, card_type) in enumerate(all_cards):
            card_str = card_str.strip()
            if len(card_str) >= 2:
                rank, suit = card_str[:-1], card_str[-1]
                pixmap = self._get_card_pixmap(rank, suit, width=25, height=33)
                lbl = QLabel()
                if pixmap:
                    lbl.setPixmap(pixmap)
                    lbl.setToolTip(f"{card_type.capitalize()} card: {card_str}")
                else:
                    s_lower = suit.lower()
                    bg_color = "#dc2626" if s_lower in ("h", "d") else "#0f172a"
                    lbl.setText(card_str)
                    lbl.setStyleSheet(
                        f"font-weight: bold; font-size: 12px; padding: 4px 6px; "
                        f"background: {bg_color}; color: #ffffff; border-radius: 4px; border: 1px solid #64748b;"
                    )
                self.cards_sandbox_container.addWidget(lbl)

            if card_type == "hole" and idx == len(hole_cards) - 1 and board_cards:
                lbl_sep = QLabel("  |  " + _("Board:"))
                lbl_sep.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px;")
                self.cards_sandbox_container.addWidget(lbl_sep)

        self.cards_sandbox_container.addStretch(1)

    def _get_card_pixmap(self, rank: str, suit: str, width: int = 25, height: int = 33) -> QPixmap | None:
        rank_str = "10" if rank.upper() in ("10", "T") else rank.lower()
        suit_str = suit.lower()
        key = (rank_str, suit_str, width, height)
        if key in _CARD_PIXMAP_CACHE:
            return _CARD_PIXMAP_CACHE[key]

        cards_dir = Path(GRAPHICS_PATH) / "cards" / "simple_flat_4color"
        svg_path = cards_dir / f"{suit_str}_{rank_str}.svg"
        if not svg_path.exists():
            svg_path = cards_dir / f"{suit_str}_{rank_str.upper()}.svg"
            if not svg_path.exists():
                return None

        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            return None

        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        _CARD_PIXMAP_CACHE[key] = pixmap
        return pixmap
