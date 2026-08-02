import json
import logging
import os
import sys
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QProcess, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import SQL, Database, GuiReplayer
from fpdb_3_legacy.http_capture_db_import import import_http_capture_directory, import_http_capture_hand
from fpdb_3_legacy.Translations import _

log = logging.getLogger(__name__)

# 4-color suit map
SUIT_SYMBOLS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
SUIT_COLORS = {
    "s": "#212121",  # Spades: Dark Grey/Black
    "h": "#d32f2f",  # Hearts: Red
    "d": "#1976d2",  # Diamonds: Blue
    "c": "#388e3c",  # Clubs: Green
}

GAME_NAME_MAPPING = {
    "poker (type 72)": "Hold'em",
    "poker (type 79)": "Omaha",
    "poker (type 88)": "5 Card Omaha",
    "poker (type 76)": "OFC/P 2-7",
    "poker (type 75)": "OFC/P Progressive",
    "poker (type 74)": "OFC/P",
    "poker (type 73)": "Turbo OFC",
    "poker (type 70)": "OFC",
}


def clean_game_name(game_type_str):
    if not game_type_str:
        return "Poker"
    key = game_type_str.lower().strip()
    return GAME_NAME_MAPPING.get(key, game_type_str)


class SwCPokerConsoleDialog(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(_("SwC Poker - Capture Console & Replayer"))
        self.resize(1100, 750)

        self.output_dir = os.path.expanduser("~/Documents/SwC Poker/Capture/")
        os.makedirs(self.output_dir, exist_ok=True)

        self.process = None
        self.captured_count = 0
        self.hands_data = {}
        self.hand_db_refs = {}
        self.current_hand_id = None
        self.current_step = 0
        self.gui_replayers = []

        self.setup_ui()
        self.populate_hand_list()

        # File watcher to auto-reload hands when new JSON files are saved
        self.watcher = QFileSystemWatcher([self.output_dir], self)
        self.watcher.directoryChanged.connect(self.populate_hand_list)

    def setup_ui(self):
        # Dark Theme Style Sheet
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #e0e0e0;
            }
            QSplitter::handle {
                background-color: #2b2b2b;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #e0e0e0;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #262626;
            }
            QListWidget::item:selected {
                background-color: #2e7d32;
                color: white;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #0b0b0b;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #a0e0a0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
            QPushButton {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b3b3b;
            }
            QPushButton:pressed {
                background-color: #1b1b1b;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- LEFT PANEL: CONTROLLER & CONSOLE ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Status & Controls
        ctrl_layout = QHBoxLayout()
        self.lbl_status = QLabel(_("Status: 🔴 Stopped"))
        self.lbl_status.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #ff5252;")

        self.lbl_count = QLabel(_("Hands Captured: 0"))
        self.lbl_count.setFont(QFont("Arial", 10))

        self.btn_start = QPushButton(_("Start Capture"))
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; border-color: #388e3c;")
        self.btn_start.clicked.connect(self.start_capture)

        self.btn_stop = QPushButton(_("Stop"))
        self.btn_stop.setStyleSheet("background-color: #c62828; color: white; border-color: #d32f2f;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_capture)

        ctrl_layout.addWidget(self.lbl_status)
        ctrl_layout.addWidget(self.lbl_count)
        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_stop)
        left_layout.addLayout(ctrl_layout)

        # Log view
        lbl_console = QLabel(_("Capture Console (Logs):"))
        left_layout.addWidget(lbl_console)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        left_layout.addWidget(self.txt_log)

        # Quick Actions
        actions_layout = QHBoxLayout()
        btn_open_folder = QPushButton(_("Open Hand Folder"))
        btn_open_folder.clicked.connect(self.open_hands_folder)

        btn_refresh = QPushButton(_("Refresh Hands"))
        btn_refresh.clicked.connect(self.populate_hand_list)

        self.btn_import_db = QPushButton(_("Import OFC to DB"))
        self.btn_import_db.clicked.connect(self.import_selected_hand_to_db)

        self.btn_import_all_db = QPushButton(_("Import All OFC"))
        self.btn_import_all_db.clicked.connect(self.import_all_hands_to_db)

        actions_layout.addWidget(btn_open_folder)
        actions_layout.addWidget(btn_refresh)
        actions_layout.addWidget(self.btn_import_db)
        actions_layout.addWidget(self.btn_import_all_db)
        left_layout.addLayout(actions_layout)

        splitter.addWidget(left_widget)

        # --- RIGHT PANEL: HAND HISTORY LIST & REPLAYER ---
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Top: Hand list
        hand_list_widget = QWidget()
        hand_list_layout = QVBoxLayout(hand_list_widget)
        hand_list_layout.setContentsMargins(0, 0, 0, 0)
        hand_list_layout.addWidget(QLabel(_("Captured Hand History:")))

        self.lst_hands = QListWidget()
        self.lst_hands.itemSelectionChanged.connect(self.on_hand_selected)
        hand_list_layout.addWidget(self.lst_hands)
        right_splitter.addWidget(hand_list_widget)

        # Bottom: Replayer
        replayer_widget = QWidget()
        replayer_widget.setStyleSheet("background-color: #181818; border-radius: 8px; border: 1px solid #2b2b2b;")
        self.rep_layout = QVBoxLayout(replayer_widget)

        # Replayer Header
        self.lbl_game_info = QLabel(_("Select a hand to start replay"))
        self.lbl_game_info.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.lbl_game_info.setStyleSheet("color: #ff9800; border: none;")
        self.lbl_game_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rep_layout.addWidget(self.lbl_game_info)

        # Replayer Content Area (Split cards on left, actions log on right)
        rep_content_splitter = QSplitter(Qt.Orientation.Horizontal)
        rep_content_splitter.setStyleSheet("QSplitter::handle { background-color: #2b2b2b; }")

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        rep_content_splitter.addWidget(self.scroll_area)

        self.txt_actions = QTextEdit()
        self.txt_actions.setReadOnly(True)
        self.txt_actions.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                border: 1px solid #2b2b2b;
                border-radius: 6px;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
        """)
        rep_content_splitter.addWidget(self.txt_actions)
        rep_content_splitter.setSizes([600, 300])

        self.rep_layout.addWidget(rep_content_splitter)

        # Replayer Controls
        rep_ctrl_layout = QHBoxLayout()
        self.btn_first = QPushButton(_("<<"))
        self.btn_prev = QPushButton(_("<"))
        self.lbl_step_num = QLabel(_("Step 0 / 0"))
        self.lbl_step_num.setStyleSheet("border: none; font-weight: bold;")
        self.btn_next = QPushButton(_(">"))
        self.btn_last = QPushButton(_(">>"))
        self.btn_open_db_replayer = QPushButton(_("Open DB Replayer"))
        self.btn_open_db_replayer.clicked.connect(self.open_selected_hand_db_replayer)

        self.btn_first.clicked.connect(self.go_first_step)
        self.btn_prev.clicked.connect(self.go_prev_step)
        self.btn_next.clicked.connect(self.go_next_step)
        self.btn_last.clicked.connect(self.go_last_step)

        rep_ctrl_layout.addWidget(self.btn_first)
        rep_ctrl_layout.addWidget(self.btn_prev)
        rep_ctrl_layout.addWidget(self.lbl_step_num, 0, Qt.AlignmentFlag.AlignCenter)
        rep_ctrl_layout.addWidget(self.btn_next)
        rep_ctrl_layout.addWidget(self.btn_last)
        rep_ctrl_layout.addWidget(self.btn_open_db_replayer)

        self.rep_layout.addLayout(rep_ctrl_layout)

        right_splitter.addWidget(replayer_widget)
        right_splitter.setSizes([200, 500])
        right_layout.addWidget(right_splitter)

        splitter.addWidget(right_widget)
        splitter.setSizes([500, 600])

        main_layout.addWidget(splitter)

    # --- CAPTURE PROCESS CONTROLS ---
    def start_capture(self):
        if self.process and self.process.state() == QProcess.Running:
            return

        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swc_http_capture.py")

        self.txt_log.clear()
        self.txt_log.append("Starting SwC Poker capture process...")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_process_output)
        self.process.finished.connect(self.on_process_finished)

        self.process.start(sys.executable, [script_path])

        self.lbl_status.setText(_("Statut : 🟢 En Cours"))
        self.lbl_status.setStyleSheet("color: #4caf50;")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_capture(self):
        if self.process and self.process.state() == QProcess.Running:
            self.txt_log.append("\nStopping capture process...")
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()

    def on_process_output(self):
        if self.process is None:
            return
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="ignore")
        self.txt_log.append(text.strip())

        # Check if a new hand was successfully saved
        if "[SUCCESS]" in text:
            self.populate_hand_list()
            self.import_all_hands_to_db(silent=True)

    def on_process_finished(self):
        self.lbl_status.setText(_("Statut : 🔴 Arrêté"))
        self.lbl_status.setStyleSheet("color: #ff5252;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.txt_log.append("\nCapture process stopped.")

    def open_hands_folder(self):
        import subprocess

        if sys.platform == "win32":
            os.startfile(self.output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.output_dir])
        else:
            subprocess.Popen(["xdg-open", self.output_dir])

    # --- HAND LIST POPULATION ---
    def populate_hand_list(self):
        # Keep selected item text
        selected_item = self.lst_hands.currentItem()
        selected_text = selected_item.text() if selected_item else None

        self.lst_hands.clear()
        self.hands_data.clear()
        self.hand_db_refs.clear()

        if not os.path.exists(self.output_dir):
            return

        json_files = []
        for filename in os.listdir(self.output_dir):
            if filename.startswith("hand_") and filename.endswith(".json"):
                json_files.append(filename)

        # Sort by hand ID/timestamp (most recent first or reverse)
        json_files.sort(reverse=True)
        self.captured_count = len(json_files)
        self.lbl_count.setText(f"Hands Captured: {self.captured_count}")

        for fn in json_files:
            filepath = os.path.join(self.output_dir, fn)
            try:
                with open(filepath) as stream:
                    hand = json.load(stream)
                hand_id = hand.get("hand_id")
                raw_game_type = hand.get("game_type", "OFC")
                game_type = clean_game_name(raw_game_type)
                ts = hand.get("timestamp", "")

                # Format: Hand #297093335 (OFC/P 2-7) - 2026-06-26 07:38:47
                time_str = ts.replace("T", " ").replace("Z", "")
                display_str = f"Hand #{hand_id} ({game_type}) - {time_str}"

                item = QListWidgetItem(display_str)
                item.setData(Qt.ItemDataRole.UserRole, hand_id)
                self.lst_hands.addItem(item)
                self.hands_data[hand_id] = hand

                # Restore selection if it existed
                if selected_text and display_str == selected_text:
                    self.lst_hands.setCurrentItem(item)
            except (AttributeError, json.JSONDecodeError, OSError, RuntimeError, TypeError):
                log.warning("Unable to read captured hand file %s", filepath, exc_info=True)

        # If nothing was selected previously, select the first hand
        if not self.lst_hands.currentItem() and self.lst_hands.count() > 0:
            self.lst_hands.setCurrentRow(0)

    def _db(self):
        if self.config is None:
            raise RuntimeError("FPDB configuration is required for database import/replay")
        sql = SQL.Sql(db_server=self.config.get_db_parameters()["db-server"])
        return Database.Database(self.config, sql=sql), sql

    def _import_hand_data_to_db(self, hand_data):
        db, _sql = self._db()
        try:
            result = import_http_capture_hand(db, hand_data)
            if result.replay_ref:
                self.hand_db_refs[str(result.site_hand_no)] = result.replay_ref
            return result
        finally:
            try:
                db.connection.close()
            except Exception:  # noqa: BLE001 - cleanup supports multiple DB drivers.
                log.debug("Unable to close SwC import database connection", exc_info=True)

    def import_selected_hand_to_db(self):
        hand_data = self.hands_data.get(self.current_hand_id)
        if not hand_data:
            QMessageBox.information(self, "Import OFC", "Select a hand first.")
            return
        try:
            result = self._import_hand_data_to_db(hand_data)
        except Exception as exc:  # noqa: BLE001 - GUI boundary surfaces import errors to the user.
            QMessageBox.critical(self, "Import OFC", f"Database import failed:\n{exc}")
            return
        if result.replay_ref:
            self.txt_log.append(f"[DB] Imported hand #{result.site_hand_no} as {result.replay_ref}")
            QMessageBox.information(self, "Import OFC", f"Imported hand #{result.site_hand_no} into DB.")
        else:
            QMessageBox.information(
                self, "Import OFC", result.message or f"Hand #{result.site_hand_no} was not imported."
            )

    def import_all_hands_to_db(self, silent=False):
        try:
            db, _sql = self._db()
            try:
                results = import_http_capture_directory(db, self.output_dir)
            finally:
                try:
                    db.connection.close()
                except Exception:  # noqa: BLE001 - cleanup supports multiple DB drivers.
                    log.debug("Unable to close SwC bulk-import database connection", exc_info=True)
        except Exception as exc:  # noqa: BLE001 - GUI boundary surfaces import errors to the user.
            if not silent:
                QMessageBox.critical(self, "Import OFC", f"Database import failed:\n{exc}")
            return

        imported = [result for result in results if result.replay_ref]
        for result in imported:
            self.hand_db_refs[str(result.site_hand_no)] = result.replay_ref
        if imported:
            self.txt_log.append(f"[DB] Imported {len(imported)} OFC hand(s).")
        if not silent:
            QMessageBox.information(self, "Import OFC", f"Imported {len(imported)} OFC hand(s) into DB.")

    def open_selected_hand_db_replayer(self):
        hand_data = self.hands_data.get(self.current_hand_id)
        if not hand_data:
            QMessageBox.information(self, "DB Replayer", "Select a hand first.")
            return
        hand_id = str(hand_data.get("hand_id"))
        replay_ref = self.hand_db_refs.get(hand_id)
        if replay_ref is None:
            try:
                result = self._import_hand_data_to_db(hand_data)
            except Exception as exc:  # noqa: BLE001 - GUI boundary surfaces import errors to the user.
                QMessageBox.critical(self, "DB Replayer", f"Database import failed:\n{exc}")
                return
            replay_ref = result.replay_ref
        if not replay_ref:
            QMessageBox.information(self, "DB Replayer", "This hand is not available in the DB replayer yet.")
            return
        try:
            db, sql = self._db()
            try:
                db.connection.close()
            except Exception:  # noqa: BLE001 - cleanup supports multiple DB drivers.
                log.debug("Unable to close SwC replayer database connection", exc_info=True)
            replayer = GuiReplayer.GuiReplayer(self.config, sql, self, [replay_ref])
            replayer.play_hand(0)
            self.gui_replayers.append(replayer)
            self.txt_log.append(f"[DB] Opened replayer for {replay_ref}")
        except Exception as exc:  # noqa: BLE001 - GUI boundary surfaces replay errors to the user.
            QMessageBox.critical(self, "DB Replayer", f"Unable to open DB replayer:\n{exc}")

    # --- REPLAYER LOGIC ---
    def on_hand_selected(self):
        item = self.lst_hands.currentItem()
        if not item:
            return

        hand_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_hand_id = hand_id
        hand_data = self.hands_data.get(hand_id)
        if not hand_data:
            return

        self.inferred_actions = self.infer_hand_actions(hand_data)
        self.current_step = len(hand_data.get("steps", []))  # Set to final step by default
        self.render_replayer_step()

    def go_first_step(self):
        self.current_step = 0
        self.render_replayer_step()

    def go_prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.render_replayer_step()

    def go_next_step(self):
        hand_data = self.hands_data.get(self.current_hand_id)
        if hand_data and self.current_step < len(hand_data.get("steps", [])):
            self.current_step += 1
            self.render_replayer_step()

    def go_last_step(self):
        hand_data = self.hands_data.get(self.current_hand_id)
        if hand_data:
            self.current_step = len(hand_data.get("steps", []))
            self.render_replayer_step()

    def create_card_widget(self, card_str, is_board=True):
        card_label = QLabel(self)
        card_label.setObjectName("cardLabel")
        card_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_label.setFixedSize(36, 52)

        if not card_str or card_str == "--" or card_str == "-1":
            if not is_board:
                # Red card back for hidden in-hand/hole cards
                card_label.setText(_("SwC"))
                card_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                card_label.setStyleSheet("""
                    background-color: #b71c1c;
                    color: #ffcdd2;
                    border: 1px solid #7f0000;
                    border-radius: 4px;
                """)
            else:
                # Dashed placeholder for empty board/grid slots
                card_label.setText("")
                card_label.setStyleSheet("""
                    background-color: #242424;
                    border: 2px dashed #444444;
                    border-radius: 4px;
                """)
        else:
            rank = card_str[:-1]
            suit = card_str[-1].lower()

            suit_sym = SUIT_SYMBOLS.get(suit, suit.upper())
            color = SUIT_COLORS.get(suit, "#ffffff")

            card_label.setText(f"{rank}\n{suit_sym}")
            card_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            card_label.setStyleSheet(f"""
                background-color: white;
                color: {color};
                border: 1px solid #888888;
                border-radius: 4px;
                padding-top: 2px;
            """)

        return card_label

    def infer_hand_actions(self, hand_data):
        steps = hand_data.get("steps", [])
        if not steps:
            return []

        game_name = clean_game_name(hand_data.get("game_type", "")).lower()
        is_ofc = "ofc" in game_name or "chinese" in game_name

        def card_count(cards):
            return sum(1 for c in cards if c and c != "--" and c != "-1")

        def get_newly_placed_cards(prev_player_cards, curr_player_cards):
            new_cards = []
            for row in ["top", "middle", "bottom"]:
                prev_row = prev_player_cards.get(row, [])
                curr_row = curr_player_cards.get(row, [])
                for c in curr_row:
                    if c and c != "--" and c != "-1" and c not in prev_row:
                        new_cards.append(f"{c} ({row.upper()})")
            return new_cards

        def get_discarded_cards(prev_player_cards, curr_player_cards):
            prev_active = prev_player_cards.get("active", [])
            if not prev_active:
                return []

            # Combine all cards in current rows
            curr_placed = []
            for row in ["top", "middle", "bottom"]:
                curr_placed.extend(curr_player_cards.get(row, []))

            discarded = []
            for c in prev_active:
                if c and c != "--" and c != "-1" and c not in curr_placed:
                    discarded.append(c)
            return discarded

        actions_by_step = []

        # Track states to infer actions
        prev_board: list[Any] = []
        prev_bets: dict[str, Any] = {}
        prev_stacks: dict[str, Any] = {}
        prev_pot = 0.0
        prev_placed_counts: dict[str, int] = {}
        current_round = 0

        for idx, step in enumerate(steps):
            step_actions = []
            board = step.get("board", [])
            pot = step.get("pot", 0.0)
            bets = step.get("bets", {})
            stacks = step.get("stacks", {})
            placed = step.get("placed", {})

            # 1. Round/Street headers
            if not is_ofc:
                if len(board) > len(prev_board):
                    new_cards = [c for c in board if c not in prev_board]
                    street_name = "FLOP" if len(board) == 3 else ("TURN" if len(board) == 4 else "RIVER")
                    step_actions.append(f"\n=== {street_name}: " + " ".join(new_cards) + " ===")
                elif idx == 0:
                    step_actions.append("=== PREFLOP ===")
            else:
                # Count placed cards for each player in this step
                curr_placed_counts = {}
                for player in hand_data.get("players", []):
                    name = player["name"]
                    p_cards = placed.get(name, {})
                    curr_placed_counts[name] = (
                        sum(1 for c in p_cards.get("top", []) if c and c != "--" and c != "-1")
                        + sum(1 for c in p_cards.get("middle", []) if c and c != "--" and c != "-1")
                        + sum(1 for c in p_cards.get("bottom", []) if c and c != "--" and c != "-1")
                    )

                max_placed = max(curr_placed_counts.values()) if curr_placed_counts else 0

                big_jump = False
                if idx > 0:
                    for player in hand_data.get("players", []):
                        name = player["name"]
                        prev_c = prev_placed_counts.get(name, 0)
                        curr_c = curr_placed_counts.get(name, 0)
                        if curr_c - prev_c > 5:
                            big_jump = True
                            break

                if idx == 0:
                    step_actions.append("=== DEAL ===")
                    current_round = 0
                elif idx == len(steps) - 1:
                    step_actions.append("\n=== PHASE COMPARISON ===")
                elif big_jump:
                    step_actions.append("\n=== [FANTASY LAND / MID-HAND] ===")
                    current_round = 5
                else:

                    def get_ofc_round(count):
                        if count == 0:
                            return 0
                        elif count <= 5:
                            return 1
                        elif count <= 7:
                            return 2
                        elif count <= 9:
                            return 3
                        elif count <= 11:
                            return 4
                        else:
                            return 5

                    round_num = get_ofc_round(max_placed)
                    if round_num > current_round:
                        step_actions.append(f"\n=== PLACEMENT ROUND {round_num} ===")
                        current_round = round_num

            # 2. Player actions
            for player in hand_data.get("players", []):
                name = player["name"]
                curr_bet = bets.get(name, 0.0)
                prev_bet = prev_bets.get(name, 0.0)
                curr_stack = stacks.get(name, 0.0)
                prev_stack = prev_stacks.get(name, 0.0)

                curr_player_cards = placed.get(name, {})

                if idx > 0:
                    bet_diff = curr_bet - prev_bet
                    stack_diff = curr_stack - prev_stack

                    if is_ofc:
                        prev_player_cards = steps[idx - 1].get("placed", {}).get(name, {})

                        # Check for active cards dealt
                        prev_active = prev_player_cards.get("active", [])
                        curr_active = curr_player_cards.get("active", [])
                        if len(prev_active) == 0 and len(curr_active) > 0:
                            visible_active = [c for c in curr_active if c and c != "--" and c != "-1"]
                            if visible_active:
                                step_actions.append(
                                    f"• {name} receives {len(curr_active)} private cards: {', '.join(visible_active)}"
                                )
                            else:
                                step_actions.append(f"• {name} receives {len(curr_active)} private cards")

                        newly_placed = get_newly_placed_cards(prev_player_cards, curr_player_cards)
                        discarded = get_discarded_cards(prev_player_cards, curr_player_cards)
                        if newly_placed:
                            discard_str = f" [discard: {', '.join(discarded)}]" if discarded else ""
                            step_actions.append(f"• {name} places: " + ", ".join(newly_placed) + discard_str)
                    else:
                        if bet_diff > 0:
                            # Max bet among all other players in the previous step
                            other_bets = [
                                prev_bets.get(p["name"], 0.0) for p in hand_data["players"] if p["name"] != name
                            ]
                            prev_max_bet = max(other_bets) if other_bets else 0.0

                            # Check if it's blinds posting or normal action
                            if idx <= 2 and prev_bet == 0 and len(board) == 0:
                                p_seat = player.get("seat_idx", hand_data["players"].index(player))
                                if p_seat == hand_data.get("sb_idx"):
                                    step_actions.append(f"• {name} posts Small Blind {curr_bet:.2f} mBTC")
                                elif p_seat == hand_data.get("bb_idx"):
                                    step_actions.append(f"• {name} posts Big Blind {curr_bet:.2f} mBTC")
                                else:
                                    step_actions.append(f"• {name} bets {curr_bet:.2f} mBTC")
                            else:
                                if curr_bet == prev_max_bet:
                                    step_actions.append(f"• {name} calls {curr_bet:.2f} mBTC")
                                elif curr_bet > prev_max_bet:
                                    if prev_max_bet == 0:
                                        step_actions.append(f"• {name} bets {curr_bet:.2f} mBTC")
                                    else:
                                        step_actions.append(f"• {name} raises to {curr_bet:.2f} mBTC (+{bet_diff:.2f})")
                                else:
                                    step_actions.append(f"• {name} calls All-In {curr_bet:.2f} mBTC")
                        elif stack_diff < 0 and bet_diff == 0:
                            ante_val = prev_stack - curr_stack
                            step_actions.append(f"• {name} blind/ante of {ante_val:.2f} mBTC")

                        # Fold detection
                        prev_cards = steps[idx - 1].get("placed", {}).get(name, {}).get("cards", [])
                        curr_cards = curr_player_cards.get("cards", [])
                        if len(prev_cards) > 0 and len(curr_cards) == 0 and idx < len(steps) - 1:
                            step_actions.append(f"• {name} folds")
                else:
                    if curr_bet > 0:
                        p_seat = player.get("seat_idx", hand_data["players"].index(player))
                        if p_seat == hand_data.get("sb_idx"):
                            step_actions.append(f"• {name} posts Small Blind {curr_bet:.2f} mBTC")
                        elif p_seat == hand_data.get("bb_idx"):
                            step_actions.append(f"• {name} posts Big Blind {curr_bet:.2f} mBTC")
                        else:
                            step_actions.append(f"• {name} posts Blind {curr_bet:.2f} mBTC")

            # Pot updates
            if pot > 0 and pot != prev_pot:
                step_actions.append(f"  [TOTAL POT: {pot:.2f} mBTC]")

            prev_board = board
            prev_bets = bets
            prev_stacks = stacks
            prev_pot = pot
            if is_ofc:
                prev_placed_counts = curr_placed_counts

            actions_by_step.append(step_actions)

        # 3. Showdown / End of hand summary
        showdown = hand_data.get("showdown")
        if showdown and showdown.get("points_settled"):
            sd_actions = ["\n=== HAND SUMMARY ==="]

            # Print row combinations if available
            if showdown.get("rows"):
                sd_actions.append("Combinations:")
                for p, rows in showdown["rows"].items():
                    if is_ofc:
                        sd_actions.append(
                            f"  • {p} : TOP: {rows.get('top', '--')} | MID: {rows.get('mid', '--')} | BOT: {rows.get('bot', '--')}"
                        )
                    else:
                        sd_actions.append(f"  • {p} : {rows.get('top', '--')}")

            sd_actions.append("\nScores:")
            for p, pts in showdown["points_settled"].items():
                breakdown = showdown.get("points_breakdown", {}).get(p)
                if breakdown:
                    detail_str = f" (Lines: {breakdown['lines']:+d} | Royalties: H:{breakdown['top_royalty']:+d} M:{breakdown['middle_royalty']:+d} B:{breakdown['bottom_royalty']:+d})"
                else:
                    detail_str = ""

                # Adapt values and units to game type
                val = pts / 100.0 if not is_ofc else pts
                unit = "mBTC" if not is_ofc else "pts"
                fmt_val = f"{val:+.2f}" if not is_ofc else f"{val:+g}"

                if pts > 0:
                    sd_actions.append(f"  • {p} wins the hand ({fmt_val} {unit}){detail_str}")
                elif pts < 0:
                    sd_actions.append(f"  • {p} loses the hand ({fmt_val} {unit}){detail_str}")
                else:
                    sd_actions.append(f"  • {p} splits ({fmt_val} {unit}){detail_str}")
            actions_by_step.append(sd_actions)
        else:
            actions_by_step.append([])

        return actions_by_step

    def render_replayer_step(self):
        hand_data = self.hands_data.get(self.current_hand_id)
        if not hand_data:
            return

        # Clean scroll layout
        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        steps = hand_data.get("steps", [])
        total_steps = len(steps)

        # Display title info (cleaned game name)
        game_name = clean_game_name(hand_data.get("game_type", "OFC"))
        self.lbl_game_info.setText(
            f"Replay: {game_name} | Table: {hand_data.get('table_id', '--')} | Hand #{hand_data['hand_id']}"
        )

        # Step counter
        is_showdown = self.current_step >= total_steps
        self.lbl_step_num.setText(
            _("Showdown" if (is_showdown and total_steps > 0) else f"Step {self.current_step} / {total_steps}")
        )

        # Render action history up to current step
        actions_text = ""
        for idx in range(min(self.current_step + 1, len(self.inferred_actions))):
            for action in self.inferred_actions[idx]:
                actions_text += action + "\n"
        self.txt_actions.setText(actions_text)

        # Get card layout at current step
        step_data = None
        if total_steps > 0:
            idx = min(self.current_step, total_steps - 1)
            step_data = steps[idx]

        placed_cards = step_data.get("placed", {}) if step_data else {}
        board_cards = step_data.get("board", []) if step_data else []
        pot_size = step_data.get("pot", 0.0) if step_data else 0.0
        step_bets = step_data.get("bets", {}) if step_data else {}
        step_stacks = step_data.get("stacks", {}) if step_data else {}

        # Determine layout based on game category
        game_name = hand_data.get("game_type", "").lower()
        is_ofc = "ofc" in game_name or "chinese" in game_name

        # --- RENDER BOARD IF TRADITIONAL POKER ---
        if not is_ofc:
            board_frame = QFrame()
            board_frame.setStyleSheet(
                "background-color: #242424; border: 1px solid #333333; border-radius: 8px; margin-bottom: 12px; border: none;"
            )
            board_layout = QVBoxLayout(board_frame)
            board_layout.setContentsMargins(10, 10, 10, 10)

            board_lbl = QLabel(f"<b>TABLE / POT: {pot_size:.2f} mBTC</b>")
            board_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            board_layout.addWidget(board_lbl)

            cards_row = QHBoxLayout()
            cards_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Show up to 5 community cards
            for idx in range(5):
                card_str = board_cards[idx] if idx < len(board_cards) else "--"
                cards_row.addWidget(self.create_card_widget(card_str, is_board=True))
            board_layout.addLayout(cards_row)
            self.scroll_layout.addWidget(board_frame)

        # --- RENDER PLAYERS ---
        for player in hand_data.get("players", []):
            p_name = player.get("name")
            p_stack = step_stacks.get(p_name, player.get("starting_stack", 0.0))
            p_bet = step_bets.get(p_name, 0.0)

            p_seat = player.get("seat_idx", hand_data.get("players").index(player))
            is_dealer = hand_data.get("dealer_idx") == p_seat

            player_frame = QFrame()
            player_frame.setStyleSheet("""
                QFrame {
                    background-color: #242424;
                    border: 1px solid #333333;
                    border-radius: 6px;
                    margin: 4px;
                }
                QLabel {
                    border: none;
                }
            """)
            p_box = QVBoxLayout(player_frame)
            p_box.setContentsMargins(10, 8, 10, 8)

            # Header with seat / name / stack / showdown point diff
            header_layout = QHBoxLayout()

            # Highlights dealer button
            dealer_text = " [D]" if is_dealer else ""

            # Show points won/lost at showdown
            points_text = ""
            if is_showdown and hand_data.get("showdown"):
                points_settled = hand_data["showdown"].get("points_settled", {})
                diff = points_settled.get(p_name, 0)

                # Adapt values and units to game type
                val = diff / 100.0 if not is_ofc else diff
                unit = "mBTC" if not is_ofc else "pts"

                if diff > 0:
                    points_text = (
                        f" <font color='#4caf50'>+{val:.2f} {unit}</font>"
                        if not is_ofc
                        else f" <font color='#4caf50'>+{val:g} {unit}</font>"
                    )
                elif diff < 0:
                    points_text = (
                        f" <font color='#f44336'>{val:.2f} {unit}</font>"
                        if not is_ofc
                        else f" <font color='#f44336'>{val:g} {unit}</font>"
                    )
                else:
                    points_text = (
                        f" <font color='#9e9e9e'>+0.00 {unit}</font>"
                        if not is_ofc
                        else f" <font color='#9e9e9e'>+0 {unit}</font>"
                    )

                # Check for breakdown
                breakdown = hand_data["showdown"].get("points_breakdown", {}).get(p_name)
                if breakdown:
                    detail_str = f" (Lines: {breakdown['lines']:+d} | Royalties: H:{breakdown['top_royalty']:+d} M:{breakdown['middle_royalty']:+d} B:{breakdown['bottom_royalty']:+d})"
                    points_text += f" <font color='#a0a0a0'>{detail_str}</font>"

            bet_text = f" | <font color='#81c784'>Bet: {p_bet:.2f} mBTC</font>" if p_bet > 0 else ""
            p_lbl = QLabel(f"👤 <b>{p_name}</b>{dealer_text} | Stack: {p_stack:.2f} mBTC{bet_text}{points_text}")
            p_lbl.setFont(QFont("Arial", 10))
            p_lbl.setStyleSheet("border: none;")
            header_layout.addWidget(p_lbl)
            p_box.addLayout(header_layout)

            if is_ofc:
                p_cards = placed_cards.get(p_name, {"top": [], "middle": [], "bottom": [], "active": []})
                # OFC uses 3-5-5 grid layout
                grid = QGridLayout()
                grid.setHorizontalSpacing(6)
                grid.setVerticalSpacing(6)
                grid.setContentsMargins(5, 5, 5, 5)

                # Showdown row descriptions if available
                sd_rows = {}
                if is_showdown and hand_data.get("showdown") and hand_data["showdown"].get("rows"):
                    sd_rows = hand_data["showdown"]["rows"].get(p_name, {})

                # Row 1: TOP (3 cards)
                lbl_top = QLabel(_("TOP :"))
                lbl_top.setStyleSheet("font-weight: bold; border: none; color: #ffb74d;")
                grid.addWidget(lbl_top, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                top_cards = p_cards.get("top", ["--"] * 3)
                for idx in range(3):
                    card_str = top_cards[idx] if idx < len(top_cards) else "--"
                    grid.addWidget(self.create_card_widget(card_str, is_board=True), 0, idx + 1)
                if sd_rows.get("top"):
                    grid.addWidget(
                        QLabel(f"<font color='#a0a0a0'><i>{sd_rows['top']}</i></font>"),
                        0,
                        4,
                        1,
                        3,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    )

                # Row 2: MIDDLE (5 cards)
                lbl_mid = QLabel(_("MIDDLE :"))
                lbl_mid.setStyleSheet("font-weight: bold; border: none; color: #ffb74d;")
                grid.addWidget(lbl_mid, 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                mid_cards = p_cards.get("middle", ["--"] * 5)
                for idx in range(5):
                    card_str = mid_cards[idx] if idx < len(mid_cards) else "--"
                    grid.addWidget(self.create_card_widget(card_str, is_board=True), 1, idx + 1)
                if sd_rows.get("mid"):
                    grid.addWidget(
                        QLabel(f"<font color='#a0a0a0'><i>{sd_rows['mid']}</i></font>"),
                        1,
                        6,
                        1,
                        3,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    )

                # Row 3: BOTTOM (5 cards)
                lbl_bot = QLabel(_("BOTTOM :"))
                lbl_bot.setStyleSheet("font-weight: bold; border: none; color: #ffb74d;")
                grid.addWidget(lbl_bot, 2, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                bot_cards = p_cards.get("bottom", ["--"] * 5)
                for idx in range(5):
                    card_str = bot_cards[idx] if idx < len(bot_cards) else "--"
                    grid.addWidget(self.create_card_widget(card_str, is_board=True), 2, idx + 1)
                if sd_rows.get("bot"):
                    grid.addWidget(
                        QLabel(f"<font color='#a0a0a0'><i>{sd_rows['bot']}</i></font>"),
                        2,
                        6,
                        1,
                        3,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    )

                p_box.addLayout(grid)

                # Show overall combination if present
                hcnu = p_cards.get("hcnu", "")
                lcnu = p_cards.get("lcnu", "")
                comb_text = []
                if hcnu:
                    comb_text.append(f"Comb: {hcnu}")
                if lcnu:
                    comb_text.append(f"Low: {lcnu}")
                if comb_text:
                    comb_lbl = QLabel(" | ".join(comb_text))
                    comb_lbl.setStyleSheet("font-style: italic; color: #a0a0a0; border: none;")
                    p_box.addWidget(comb_lbl)

                # Active/In hand cards if any
                active_cards = p_cards.get("active", [])
                if active_cards:
                    active_layout = QHBoxLayout()
                    active_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    active_layout.addWidget(QLabel(_("In Hand:")))
                    for card in active_cards:
                        active_layout.addWidget(self.create_card_widget(card, is_board=False))
                    p_box.addLayout(active_layout)
            else:
                p_cards = placed_cards.get(p_name, {"cards": []})
                # Traditional games: horizontal row of private cards
                hole_layout = QHBoxLayout()
                hole_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                hole_layout.addWidget(QLabel(_("Cards:")))

                # If there are flat cards inside cards of places list
                flat_cards = p_cards.get("cards", [])
                for idx, card_str in enumerate(flat_cards):
                    hole_layout.addWidget(self.create_card_widget(card_str, is_board=False))
                p_box.addLayout(hole_layout)

                # Show combination if present (e.g. at showdown)
                hcnu = p_cards.get("hcnu", "")
                if hcnu:
                    comb_lbl = QLabel(f"Hand: {hcnu}")
                    comb_lbl.setStyleSheet("font-style: italic; color: #a0a0a0; border: none;")
                    p_box.addWidget(comb_lbl)

            self.scroll_layout.addWidget(player_frame)

        self.scroll_layout.addStretch()

    def closeEvent(self, event):
        # Auto-stop capture when dialog is closed
        self.stop_capture()
        event.accept()
