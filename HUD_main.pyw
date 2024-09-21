#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hud_main.py

Main for FreePokerTools HUD.
"""

import codecs
import contextlib
import sys
import os
import time
import logging
import zmq
from PyQt5.QtCore import (QCoreApplication, QObject, QThread, pyqtSignal, QMutex, Qt, QTimer, QThreadPool, QRunnable)
from PyQt5.QtWidgets import (QApplication, QLabel, QVBoxLayout, QWidget)
from PyQt5.QtGui import QIcon
from qt_material import apply_stylesheet

import Configuration
import Database
import Hud
import Options
import Deck

# Add a cache for frequently accessed data
from cachetools import TTLCache

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("hud")

(options, argv) = Options.fpdb_options()

# Configuration
Configuration.set_logfile(u"HUD-log.txt")
c = Configuration.Config(file=options.config, dbname=options.dbname)

# Selecting the right module for the OS
if c.os_family == 'Linux':
    import XTables as Tables
elif c.os_family == 'Mac':
    import OSXTables as Tables
elif c.os_family in ('XP', 'Win7'):
    import WinTables as Tables

class ZMQWorker(QThread):
    error_occurred = pyqtSignal(str)

    def __init__(self, zmq_receiver):
        super().__init__()
        self.zmq_receiver = zmq_receiver
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                self.zmq_receiver.process_message()
            except Exception as e:
                log.error(f"Error in ZMQWorker: {e}")
                self.error_occurred.emit(str(e))
            time.sleep(0.01)  # Short delay to avoid excessive CPU usage

    def stop(self):
        self.is_running = False
        self.wait()  # Attend que le thread se termine

class ZMQReceiver(QObject):
    message_received = pyqtSignal(str)

    def __init__(self, port="5555", parent=None):
        super().__init__(parent)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.connect(f"tcp://127.0.0.1:{port}")
        log.info(f"ZMQ receiver connected on port {port}")

        # Heartbeat configuration
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def process_message(self):
        try:
            socks = dict(self.poller.poll(1000))  # Timeout 1 seconde
            if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                hand_id = self.socket.recv_string(zmq.NOBLOCK)
                log.debug(f"Received hand ID: {hand_id}")
                self.message_received.emit(hand_id)
            else:
                # Heartbeat
                log.debug("Heartbeat: No message received")
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                pass  # No message available
            else:
                log.error(f"ZMQ error: {e}")

    def close(self):
        self.socket.close()
        self.context.term()
        log.info("ZMQ receiver closed")

class HUD_main(QObject):
    """A main() object to own both the socket thread and the gui."""
    def __init__(self, db_name='fpdb'):
        QObject.__init__(self)
        self.db_name = db_name
        self.config = c
        log.info(f"HUD_main starting: Using db name = {db_name}")

        # Configuration du logging
        if not options.errorsToConsole:
            fileName = os.path.join(self.config.dir_log, u'HUD-errors.txt')
            log.info(f"Note: error output is being diverted to {fileName}.")
            log.info("Any major error will be reported there *only*.")
            errorFile = codecs.open(fileName, 'w', 'utf-8')
            sys.stderr = errorFile
            log.info("HUD_main starting")

        try:
            # Connecting to the database
            self.db_connection = Database.Database(self.config)

            # HUD dictionary and parameters
            self.hud_dict = {}
            self.blacklist = []
            self.hud_params = self.config.get_hud_ui_parameters()
            self.deck = Deck.Deck(self.config, deck_type=self.hud_params["deck_type"], card_back=self.hud_params["card_back"],
                                  width=self.hud_params['card_wd'], height=self.hud_params['card_ht'])

            # Cache initialization
            self.cache = TTLCache(maxsize=1000, ttl=300)  # Cache of 1000 elements with a TTL of 5 minutes

            # Initialisation ZMQ avec QThread
            self.zmq_receiver = ZMQReceiver(parent=self)
            self.zmq_receiver.message_received.connect(self.handle_message)
            self.zmq_worker = ZMQWorker(self.zmq_receiver)
            self.zmq_worker.error_occurred.connect(self.handle_worker_error)
            self.zmq_worker.start()

            # Main window
            self.init_main_window()

            log.debug("Main window initialized and shown.")
        except Exception as e:
            log.error(f"Error during HUD_main initialization: {e}")
            raise

    def handle_worker_error(self, error_message):
        log.error(f"ZMQWorker encountered an error: {error_message}")

    def init_main_window(self):
        self.main_window = QWidget(None, Qt.Dialog | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        if options.xloc is not None or options.yloc is not None:
            if options.xloc is None:
                options.xloc = 0
            if options.yloc is None:
                options.yloc = 0
            self.main_window.move(options.xloc, options.yloc)
        self.main_window.destroyed.connect(self.destroy)
        self.vb = QVBoxLayout()
        self.vb.setContentsMargins(2, 0, 2, 0)
        self.main_window.setLayout(self.vb)
        self.label = QLabel('Closing this window will exit from the HUD.')
        self.main_window.closeEvent = lambda event: sys.exit()
        self.vb.addWidget(self.label)
        self.main_window.setWindowTitle("HUD Main Window")
        cards = os.path.join(self.config.graphics_path, 'tribal.jpg')
        if cards:
            self.main_window.setWindowIcon(QIcon(cards))

        # Timer for periodically checking tables
        self.check_tables_timer = QTimer(self)
        self.check_tables_timer.timeout.connect(self.check_tables)
        self.check_tables_timer.start(800)
        self.main_window.show()

    def handle_message(self, hand_id):
        # This method will be called in the main thread
        self.read_stdin(hand_id)

    def destroy(self, *args):
        if hasattr(self, 'zmq_receiver'):
            self.zmq_receiver.close()
        if hasattr(self, 'zmq_worker'):
            self.zmq_worker.stop()
        log.info("Quitting normally")
        QCoreApplication.quit()

    def check_tables(self):
        for tablename, hud in list(self.hud_dict.items()):
            status = hud.table.check_table()
            if status == "client_destroyed":
                self.client_destroyed(None, hud)
            elif status == "client_moved":
                self.client_moved(None, hud)
            elif status == "client_resized":
                self.client_resized(None, hud)

        if self.config.os_family == "Mac":
            for hud in self.hud_dict.values():
                for aw in hud.aux_windows:
                    if not hasattr(aw, 'm_windows'):
                        continue
                    for w in aw.m_windows.values():
                        if w.isVisible():
                            hud.table.topify(w)

    def client_moved(self, widget, hud):
        log.debug("Client moved event")
        self.idle_move(hud)

    def client_resized(self, widget, hud):
        log.debug("Client resized event")
        self.idle_resize(hud)

    def client_destroyed(self, widget, hud):
        log.debug("Client destroyed event")
        self.kill_hud(None, hud.table.key)

    def table_title_changed(self, widget, hud):
        log.debug("Table title changed, killing current HUD")
        self.kill_hud(None, hud.table.key)

    def table_is_stale(self, hud):
        log.debug("Moved to a new table, killing current HUD")
        self.kill_hud(None, hud.table.key)

    def destroy(self, *args):
        if hasattr(self, 'zmq_receiver'):
            self.zmq_receiver.close()
        if hasattr(self, 'worker'):
            self.worker.stop()
        log.info("Quitting normally")
        QCoreApplication.quit()

    def kill_hud(self, event, table):
        log.debug("kill_hud event")
        self.idle_kill(table)

    def blacklist_hud(self, event, table):
        log.debug("blacklist_hud event")
        self.blacklist.append(self.hud_dict[table].tablenumber)
        self.idle_kill(table)

    def create_HUD(self, new_hand_id, table, temp_key, max, poker_game, type, stat_dict, cards):
        log.debug(f"Creating HUD for table {temp_key} and hand {new_hand_id}")
        self.hud_dict[temp_key] = Hud.Hud(self, table, max, poker_game, type, self.config)
        self.hud_dict[temp_key].table_name = temp_key
        self.hud_dict[temp_key].stat_dict = stat_dict
        self.hud_dict[temp_key].cards = cards
        self.hud_dict[temp_key].max = max

        table.hud = self.hud_dict[temp_key]

        self.hud_dict[temp_key].hud_params['new_max_seats'] = None  # trigger for seat layout change

        for aw in self.hud_dict[temp_key].aux_windows:
            aw.update_data(new_hand_id, self.db_connection)

        self.idle_create(new_hand_id, table, temp_key, max, poker_game, type, stat_dict, cards)
        log.debug(f"HUD for table {temp_key} created successfully.")

    def update_HUD(self, new_hand_id, table_name, config):
        log.debug(f"Updating HUD for table {table_name} and hand {new_hand_id}")
        self.idle_update(new_hand_id, table_name, config)

    def read_stdin(self, new_hand_id):
        log.debug(f"Processing new hand id: {new_hand_id}")
        
        # Using the cache for frequently accessed data
        if new_hand_id in self.cache:
            log.debug(f"Using cached data for hand {new_hand_id}")
            table_info = self.cache[new_hand_id]
        else:
            # get hero's screen names and player ids
            self.hero, self.hero_ids = {}, {}
            found = False

            enabled_sites = self.config.get_supported_sites()
            if not enabled_sites:
                log.error("No enabled sites found")
                self.db_connection.connection.rollback()
                self.destroy()
                return

            aux_disabled_sites = []
            for i in enabled_sites:
                if not c.get_site_parameters(i)['aux_enabled']:
                    log.info(f"Aux disabled for site {i}")
                    aux_disabled_sites.append(i)

            self.db_connection.connection.rollback()  # release lock from previous iteration

            if not found:
                for site in enabled_sites:
                    if result := self.db_connection.get_site_id(site):
                        site_id = result[0][0]
                        self.hero[site_id] = self.config.supported_sites[site].screen_name
                        self.hero_ids[site_id] = self.db_connection.get_player_id(self.config, site, self.hero[site_id])
                        if self.hero_ids[site_id] is not None:
                            found = True
                        else:
                            self.hero_ids[site_id] = -1

            if new_hand_id != "":
                log.debug("HUD_main.read_stdin: Hand processing starting.")
                try:
                    table_info = self.db_connection.get_table_info(new_hand_id)
                    self.cache[new_hand_id] = table_info  # Information caching
                except Exception as e:
                    log.error(f"Database error while processing hand {new_hand_id}: {e}", exc_info=True)
                    return

        (table_name, max, poker_game, type, fast, site_id, site_name, num_seats, tour_number, tab_number) = table_info

        if fast:
            return

        if site_name in aux_disabled_sites:
            return
        if site_name not in enabled_sites:
            return

        # Generating the temporary key
        if type == "tour":
            try:
                log.debug(f"creating temp_key for tour")
                if len(table_name) >= 2 and table_name[-2].endswith(','):
                    parts = table_name.split(',', 1)
                else:
                    parts = table_name.split(' ', 1)

                tab_number = tab_number.rsplit(' ', 1)[-1]
                temp_key = f"{tour_number} Table {tab_number}"
                log.debug(f"temp_key {temp_key}")
            except ValueError:
                log.error("Both tab_number and table_name not working")
        else:
            temp_key = table_name

        # Managing table changes for tournaments
        if type == "tour":
            if temp_key in self.hud_dict:
                if self.hud_dict[temp_key].table.has_table_title_changed(self.hud_dict[temp_key]):
                    log.debug(f"table has been renamed")
                    self.table_is_stale(self.hud_dict[temp_key])
                    return
            else:
                for k in self.hud_dict:
                    log.debug(f"check if the tournament number is in the hud_dict under a different table")
                    if k.startswith(tour_number):
                        self.table_is_stale(self.hud_dict[k])
                        continue

        # Detection of max_seats and poker_game changes
        if temp_key in self.hud_dict:
            with contextlib.suppress(Exception):
                newmax = self.hud_dict[temp_key].hud_params['new_max_seats']
                log.debug(f"newmax {newmax}")
                if newmax and self.hud_dict[temp_key].max != newmax:
                    log.debug(f"going to kill_hud due to max seats change")
                    self.kill_hud("activate", temp_key)
                    while temp_key in self.hud_dict: time.sleep(0.5)
                    max = newmax
                self.hud_dict[temp_key].hud_params['new_max_seats'] = None

            if self.hud_dict[temp_key].poker_game != poker_game:
                with contextlib.suppress(Exception):
                    log.debug(f"going to kill_hud due to poker game change")
                    self.kill_hud("activate", temp_key)
                    while temp_key in self.hud_dict: time.sleep(0.5)

        # Updating or creating the HUD
        if temp_key in self.hud_dict:
            log.debug(f"update hud for hand {new_hand_id}")
            self.db_connection.init_hud_stat_vars(self.hud_dict[temp_key].hud_params['hud_days'],
                                                  self.hud_dict[temp_key].hud_params['h_hud_days'])
            stat_dict = self.db_connection.get_stats_from_hand(new_hand_id, type, self.hud_dict[temp_key].hud_params,
                                                               self.hero_ids[site_id], num_seats)
            log.debug(f"got stats for hand {new_hand_id}")

            try:
                self.hud_dict[temp_key].stat_dict = stat_dict
            except KeyError:
                log.error(f'hud_dict[{temp_key}] was not found')
                log.error('will not send hand')
                return

            self.hud_dict[temp_key].cards = self.get_cards(new_hand_id, poker_game)
            for aw in self.hud_dict[temp_key].aux_windows:
                aw.update_data(new_hand_id, self.db_connection)
            self.update_HUD(new_hand_id, temp_key, self.config)
            log.debug(f"hud updated for table {temp_key} and hand {new_hand_id}")
        else:
            log.debug(f"create new hud for hand {new_hand_id}")
            self.db_connection.init_hud_stat_vars(self.hud_params['hud_days'], self.hud_params['h_hud_days'])
            stat_dict = self.db_connection.get_stats_from_hand(new_hand_id, type, self.hud_params,
                                                               self.hero_ids[site_id], num_seats)
            log.debug(f"got stats for hand {new_hand_id}")

            hero_found = any(
                stat_dict[key]['screen_name'] == self.hero[site_id]
                for key in stat_dict
            )
            if not hero_found:
                log.info("HUD not created yet, because hero is not seated for this hand")
                return

            cards = self.get_cards(new_hand_id, poker_game)
            table_kwargs = dict(table_name=table_name, tournament=tour_number, table_number=tab_number)
            tablewindow = Tables.Table(self.config, site_name, **table_kwargs)
            if tablewindow.number is None:
                log.debug(f"tablewindow.number is none")
                if type == "tour":
                    table_name = f"{tour_number} {tab_number}"
                log.error(f"HUD create: table name {table_name} not found, skipping.")
                return
            elif tablewindow.number in self.blacklist:
                return
            else:
                log.debug(f"tablewindow.number is not none")
                tablewindow.key = temp_key
                tablewindow.max = max
                tablewindow.site = site_name
                if hasattr(tablewindow, 'number'):
                    log.debug(f"table window still exists")
                    self.create_HUD(new_hand_id, tablewindow, temp_key, max, poker_game, type, stat_dict, cards)
                else:
                    log.error(f'Table "{table_name}" no longer exists')
                    return

    def get_cards(self, new_hand_id, poker_game):
        cards = self.db_connection.get_cards(new_hand_id)
        if poker_game in ['holdem', 'omahahi', 'omahahilo']:
            comm_cards = self.db_connection.get_common_cards(new_hand_id)
            cards['common'] = comm_cards['common']
        return cards

    def idle_move(self, hud):
        try:
            hud.move_table_position()
            for aw in hud.aux_windows:
                aw.move_windows()
        except Exception:
            log.exception(f"Error moving HUD for table: {hud.table.title}.")

    def idle_resize(self, hud):
        try:
            hud.resize_windows()
            for aw in hud.aux_windows:
                aw.resize_windows()
        except Exception:
            log.exception(f"Error resizing HUD for table: {hud.table.title}.")

    def idle_kill(self, table):
        try:
            if table in self.hud_dict:
                self.vb.removeWidget(self.hud_dict[table].tablehudlabel)
                self.hud_dict[table].tablehudlabel.setParent(None)
                self.hud_dict[table].kill()
                del self.hud_dict[table]
            self.main_window.resize(1, 1)
        except Exception:
            log.exception(f"Error killing HUD for table: {table}.")

    def idle_create(self, new_hand_id, table, temp_key, max, poker_game, type, stat_dict, cards):
        try:
            newlabel = QLabel(f"{table.site} - {temp_key}")
            log.debug(f"adding label {newlabel.text()}")
            self.vb.addWidget(newlabel)

            self.hud_dict[temp_key].tablehudlabel = newlabel
            self.hud_dict[temp_key].tablenumber = table.number
            self.hud_dict[temp_key].create(new_hand_id, self.config, stat_dict)
            for m in self.hud_dict[temp_key].aux_windows:
                m.create()
                log.debug(f"idle_create new_hand_id {new_hand_id}")
                m.update_gui(new_hand_id)

        except Exception:
            log.exception(f"Error creating HUD for hand {new_hand_id}.")

    def idle_update(self, new_hand_id, table_name, config):
        try:
            log.debug(f"idle_update entered for {table_name} {new_hand_id}")
            self.hud_dict[table_name].update(new_hand_id, config)
            log.debug(f"idle_update update_gui {new_hand_id}")
            for aw in self.hud_dict[table_name].aux_windows:
                aw.update_gui(new_hand_id)
        except Exception:
            log.exception(f"Error updating HUD for hand {new_hand_id}.")

if __name__ == "__main__":
    app = QApplication([])
    apply_stylesheet(app, theme='dark_purple.xml')

    # start the HUD_main object
    hm = HUD_main(db_name=options.dbname)

    # start the event loop
    app.exec_()