# -*- coding: utf-8 -*-
################################################################################
##
## BY: WANDERSON M.PIMENTA
## PROJECT MADE WITH: Qt Designer and PyQt5
## V: 1.0.0
##
## This project can be used freely for all uses, as long as they maintain the
## respective credits only in the Python scripts, any information in the visual
## interface (GUI) can be modified without any implication.
##
## There are limitations on Qt licenses if you want to use your products
## commercially, I recommend reading them on the official website:
## https://doc.qt.io/qtforpython/licenses.html
##
################################################################################
import os
import sys
import platform
import logging
import queue
import codecs
from functools import partial
from PyQt5.QtCore import (QCoreApplication, QMetaObject, QObject, QPoint,
    QRect, QSize, QUrl, Qt)
from PyQt5.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QLinearGradient, QPalette, QPainter, QPixmap,
    QRadialGradient)
from PyQt5.QtWidgets import *

import files_rc as files_rc
import numpy
numpy_version = numpy.__version__
import sqlite3
sqlite3_version = sqlite3.version
sqlite_version = sqlite3.sqlite_version

# fpdb module
import DetectInstalledSites
import Configuration
import Options
cl_options = '.'.join(sys.argv[1:])
(options, argv) = Options.fpdb_options()
import Exceptions
Configuration.set_logfile("fpdb-log.txt")
log = logging.getLogger("fpdb")
import SQL
import Database
import interlocks
import Card
import Stats
import main

class Ui_Sites_setting(object):
    def __init__(self,):
        self.load_profile()  
        self.site_names = self.config.site_ids
        self.available_site_names=[]
        
        
    def sitesUi(self):
        
        self.page_sites_settings = QWidget()
        self.page_sites_settings.setObjectName(u"page_sites_settings")
        self.verticalLayout_sites_settings= QVBoxLayout(self.page_sites_settings)
        self.verticalLayout_sites_settings.setObjectName(u"verticalLayout_sites_settings")
        self.label_sites_settings = QLabel(("Please select which sites you play on and enter your usernames."))
        self.verticalLayout_sites_settings.addWidget(self.label_sites_settings)
 
   ########################################################################
    ## call ==> site pref
    ############################## ---/--/--- ##############################

        
        

        for self.site_name in self.site_names:
            try:
                tmp = self.config.supported_sites[self.site_name].enabled
                self.available_site_names.append(self.site_name)
            except KeyError:
                pass
        
        column_headers=[("Site"), ("Detect"), ("Screen Name"), ("Hand History Path"), "", ("Tournament Summary Path"), ""]  # todo ("HUD")
        #HUD column will contain a button that shows favseat and HUD locations. Make it possible to load screenshot to arrange HUD windowlets.

        table = QGridLayout()
        table.setSpacing(0)

        scrolling_frame = QScrollArea(self.page_sites_settings)
        self.page_sites_settings.layout().addWidget(scrolling_frame)
        scrolling_frame.setLayout(table)
                
        for header_number in range (0, len(column_headers)):
            label = QLabel(column_headers[header_number])
            label.setAlignment(Qt.AlignCenter)
            table.addWidget(label, 0, header_number)
        
        check_buttons=[]
        screen_names=[]
        history_paths=[]
        summary_paths=[]
        detector = DetectInstalledSites.DetectInstalledSites()
              
        y_pos=1
        for site_number in range(0, len(self.available_site_names)):
            check_button = QCheckBox(self.available_site_names[site_number])
            check_button.setChecked(self.config.supported_sites[self.available_site_names[site_number]].enabled)
            table.addWidget(check_button, y_pos, 0)
            check_buttons.append(check_button)
            
            hero = QLineEdit()
            hero.setText(self.config.supported_sites[self.available_site_names[site_number]].screen_name)
            table.addWidget(hero, y_pos, 2)
            screen_names.append(hero)
            hero.textChanged.connect(partial(self.autoenableSite, checkbox=check_buttons[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[self.available_site_names[site_number]].HH_path)
            table.addWidget(entry, y_pos, 3)
            history_paths.append(entry)
            
            choose1 = QPushButton("Browse")
            table.addWidget(choose1, y_pos, 4)
            choose1.clicked.connect(partial(self.browseClicked, parent=self.page_sites_settings, path=history_paths[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[self.available_site_names[site_number]].TS_path)
            table.addWidget(entry, y_pos, 5)
            summary_paths.append(entry)

            choose2 = QPushButton("Browse")
            table.addWidget(choose2, y_pos, 6)
            choose2.clicked.connect(partial(self.browseClicked, parent=self.page_sites_settings, path=summary_paths[site_number]))
            
            if self.available_site_names[site_number] in detector.supportedSites:
                button = QPushButton(("Detect"))
                table.addWidget(button, y_pos, 1)
                button.clicked.connect(partial(self.detect_clicked, data=(detector, self.available_site_names[site_number], screen_names[site_number], history_paths[site_number], summary_paths[site_number])))
            y_pos+=1

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self.page_sites_settings)
        btns.accepted.connect(self.page_sites_settings.accept)
        btns.rejected.connect(self.page_sites_settings.reject)
        self.page_sites_settings.layout().addWidget(btns)

        response = self.page_sites_settings.exec_()
        if response:
            for site_number in range(0, len(self.available_site_names)):
                #print "site %s enabled=%s name=%s" % (available_site_names[site_number], check_buttons[site_number].get_active(), screen_names[site_number].get_text(), history_paths[site_number].get_text())
                self.config.edit_site(self.available_site_names[site_number], str(check_buttons[site_number].isChecked()), screen_names[site_number].text(), history_paths[site_number].text(), summary_paths[site_number].text())
            
            self.config.save()
            self.reload_config()

    ########################################################################
    ## call ==> load profiles
    ############################## ---/--/--- ##############################

    def load_profile(self, create_db=False):
        """Loads profile from the provided path name."""
        self.config = Configuration.Config(file=options.config, dbname=options.dbname)
        if self.config.file_error:
            self.warning_box(("There is an error in your config file %s") % self.config.file
                              + ":\n" + str(self.config.file_error),
                              diatitle=("CONFIG FILE ERROR"))
            sys.exit()

        log = logging.getLogger("fpdb")
        print ((("Logfile is %s") % os.path.join(self.config.dir_log, self.config.log_file)))
        print("load profiles", self.config.example_copy)
 
        if self.config.example_copy or self.display_config_created_dialogue:
            self.info_box(("Config file"),
                          ("Config file has been created at %s.") % self.config.file + " "
                           + ("Enter your screen_name and hand history path in the Site Preferences window (Main menu) before trying to import hands."))
            self.display_config_created_dialogue = False
        elif self.config.wrongConfigVersion:
            diaConfigVersionWarning = QDialog()
            diaConfigVersionWarning.setWindowTitle(("Strong Warning - Local configuration out of date"))
            diaConfigVersionWarning.setLayout(QVBoxLayout())

            label = QLabel("\n"+("Your local configuration file needs to be updated."))
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("This error is not necessarily fatal but it is strongly recommended that you update the configuration.")+"\n")
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("To create a new configuration, see fpdb.sourceforge.net/apps/mediawiki/fpdb/index.php?title=Reset_Configuration"))
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            diaConfigVersionWarning.layout().addWidget(label)
            label = QLabel(("A new configuration will destroy all personal settings (hud layout, site folders, screennames, favourite seats)")+"\n")
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("To keep existing personal settings, you must edit the local file."))
            diaConfigVersionWarning.layout().addWidget(label)

            label = QLabel(("See the release note for information about the edits needed"))
            diaConfigVersionWarning.layout().addWidget(label)

            btns = QDialogButtonBox(QDialogButtonBox.Ok)
            btns.accepted.connect(diaConfigVersionWarning.accept)
            diaConfigVersionWarning.layout().addWidget(btns)

            diaConfigVersionWarning.exec_()
            self.config.wrongConfigVersion = False
            
        self.settings = {}
        self.settings['global_lock'] = self.lock
        if (os.sep == "/"):
            self.settings['os'] = "linuxmac"
        else:
            self.settings['os'] = "windows"

        self.settings.update({'cl_options': cl_options})
        self.settings.update(self.config.get_db_parameters())
        self.settings.update(self.config.get_import_parameters())
        self.settings.update(self.config.get_default_paths())

        if self.db is not None and self.db.is_connected():
            self.db.disconnect()

        self.sql = SQL.Sql(db_server=self.settings['db-server'])
        err_msg = None
        try:
            self.db = Database.Database(self.config, sql=self.sql)
            if self.db.get_backend_name() == 'SQLite':
                # tell sqlite users where the db file is
                print ((("Connected to SQLite: %s") % self.db.db_path))
        except Exceptions.FpdbMySQLAccessDenied:
            err_msg = ("MySQL Server reports: Access denied. Are your permissions set correctly?")
        except Exceptions.FpdbMySQLNoDatabase:
            err_msg = ("MySQL client reports: 2002 or 2003 error. Unable to connect - ") \
                      + ("Please check that the MySQL service has been started")
        except Exceptions.FpdbPostgresqlAccessDenied:
            err_msg = ("PostgreSQL Server reports: Access denied. Are your permissions set correctly?")
        except Exceptions.FpdbPostgresqlNoDatabase:
            err_msg = ("PostgreSQL client reports: Unable to connect - ") \
                      + ("Please check that the PostgreSQL service has been started")
        if err_msg is not None:
            self.db = None
            self.warning_box(err_msg)
        if self.db is not None and not self.db.is_connected():
            self.db = None

        if self.db is not None and self.db.wrongDbVersion:
            diaDbVersionWarning = QMessageBox(QMessageBox.Warning, ("Strong Warning - Invalid database version"), ("An invalid DB version or missing tables have been detected."), QMessageBox.Ok, self)
            diaDbVersionWarning.setInformativeText(("This error is not necessarily fatal but it is strongly recommended that you recreate the tables by using the Database menu.")
                                                   + "\n" +  ("Not doing this will likely lead to misbehaviour including fpdb crashes, corrupt data etc."))
            diaDbVersionWarning.exec_()
        if self.db is not None and self.db.is_connected():
            self.statusBar().showMessage(("Status: Connected to %s database named %s on host %s")
                                     % (self.db.get_backend_name(), self.db.database, self.db.host))
            # rollback to make sure any locks are cleared:
            self.db.rollback()

        #If the db-version is out of date, don't validate the config 
        # otherwise the end user gets bombarded with false messages
        # about every site not existing
        if hasattr(self.db, 'wrongDbVersion'):
            if not self.db.wrongDbVersion:
                self.validate_config()

    ########################################################################
    ## call ==> load info box
    ############################## ---/--/--- ##############################
    def info_box(self, str1, str2):
        diapath = QMessageBox(self)
        diapath.setWindowTitle(str1)
        diapath.setText(str2)
        return diapath.exec_()
    ########################################################################
    ## call ==> validate config fpdb
    ############################## ---/--/--- ##############################

    def validate_config(self):
        # check if sites in config file are in DB
        for site in self.config.supported_sites:    # get site names from config file
            try:
                self.config.get_site_id(site)                     # and check against list from db
            except KeyError as exc:
                log.warning("site %s missing from db" % site)
    ########################################################################
    ## call ==> load detected clicked
    ############################## ---/--/--- ##############################      
    def detect_clicked(self, widget, data):
        detector = data[0]
        site_name = data[1]
        entry_screen_name = data[2]
        entry_history_path = data[3]
        entry_summary_path = data[4]
        if detector.sitestatusdict[site_name]['detected']:
            entry_screen_name.setText(detector.sitestatusdict[site_name]['heroname'])
            entry_history_path.setText(detector.sitestatusdict[site_name]['hhpath'])
            if detector.sitestatusdict[site_name]['tspath']:
                entry_summary_path.setText(detector.sitestatusdict[site_name]['tspath'])
    ########################################################################
    ## call ==> self reload
    ############################## ---/--/--- ############################## 
    def reload_config(self):

            self.load_profile()
            self.warning_box(("Configuration settings have been updated, Fpdb needs to be restarted now")+"\n\n"+("Click OK to close Fpdb"))
            sys.exit()
    ########################################################################
    ## call ==> warning box
    ############################## ---/--/--- ##############################      
    def warning_box(self, string, diatitle=("FPDB WARNING")):
        return QMessageBox(QMessageBox.Warning, diatitle, string).exec_()    