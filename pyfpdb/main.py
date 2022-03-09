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
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import (QCoreApplication, QPropertyAnimation, QDate, QDateTime, QMetaObject, QObject, QPoint, QRect, QSize, QTime, QUrl, Qt, QEvent)
from PyQt5.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont, QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPalette, QPainter, QPixmap, QRadialGradient)
from PyQt5.QtWidgets import *
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
# GUI FILE
from app_modules import *

class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        ########################################################################
        ## START - fpdb ATTRIBUTES
        ########################################################################
        self.lock = interlocks.InterProcessLock(name="fpdb_global_lock")
        self.db = None
        self.status_bar = None
        self.quitting = False
        self.visible = False
        self.threads = []     # objects used by tabs - no need for threads, gtk handles it
        self.closeq = queue.Queue(20)  # used to signal ending of a thread (only logviewer for now)

        if options.initialRun:
            self.display_config_created_dialogue = True
            self.display_site_preferences = True
        else:
            self.display_config_created_dialogue = False
            self.display_site_preferences = False

           
        self.load_profile(create_db=True)   
        if self.config.install_method == 'app':
            for site in list(self.config.supported_sites.values()):
                if site.screen_name != "YOUR SCREEN NAME HERE":
                    break
            else: # No site has a screen name set
                options.initialRun = True
                self.display_config_created_dialogue = True
                self.display_site_preferences = True

        if options.initialRun and self.display_site_preferences:
            self.dia_site_preferences(None,None)
            self.display_site_preferences=False
        if not options.errorsToConsole:
            fileName = os.path.join(self.config.dir_log, 'fpdb-errors.txt')
            print(((("Note: error output is being diverted to %s.") % self.config.dir_log) + " " +
                  ("Any major error will be reported there _only_.")))
            errorFile = codecs.open(fileName, 'w', 'utf-8')
            sys.stderr = errorFile
        sys.stderr.write(("fpdb starting ..."))                




        ## PRINT ==> SYSTEM
        print('System: ' + platform.system())
        print('Version: ' +platform.release())

        ########################################################################
        ## START - WINDOW ATTRIBUTES
        ########################################################################

        ## REMOVE ==> STANDARD TITLE BAR
        UIFunctions.removeTitleBar(True)
        ## ==> END ##

        ## SET ==> WINDOW TITLE
        self.setWindowTitle('Free Poker DB 3')
        UIFunctions.labelTitle(self, 'Free Poker DB 3')
        UIFunctions.labelDescription(self, 'Set text')
        ## ==> END ##

        ## WINDOW SIZE ==> DEFAULT SIZE
        startSize = QSize(1000, 720)
        self.resize(startSize)
        self.setMinimumSize(startSize)
        # UIFunctions.enableMaximumSize(self, 500, 720)
        ## ==> END ##

        ## ==> CREATE MENUS
        ########################################################################

        ## ==> TOGGLE MENU SIZE
        self.ui.btn_toggle_menu.clicked.connect(lambda: UIFunctions.toggleMenu(self, 220, True))
        ## ==> END ##

        ## ==> ADD CUSTOM MENUS
        self.ui.stackedWidget.setMinimumWidth(20)
        UIFunctions.addNewMenu(self, "HOME", "btn_home", "url(:/16x16/icons/16x16/cil-home.png)", True)
        UIFunctions.addNewMenu(self, "Import", "btn_import", "url(:/16x16/icons/16x16/cil-wrap-text.png)", True)
        UIFunctions.addNewMenu(self, "Add User", "btn_new_user", "url(:/16x16/icons/16x16/cil-user-follow.png)", True)
        UIFunctions.addNewMenu(self, "Custom Widgets", "btn_widgets", "url(:/16x16/icons/16x16/cil-equalizer.png)", False)
        UIFunctions.addNewMenu(self, "Sites settings", "btn_sites_settings", "url(:/16x16/icons/16x16/cil-home.png)", True)
        ## ==> END ##

        # START MENU => SELECTION
        UIFunctions.selectStandardMenu(self, "btn_home")
        ## ==> END ##

        ## ==> START PAGE
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_home)
        ## ==> END ##

        ## USER ICON ==> SHOW HIDE
        UIFunctions.userIcon(self, "WM", "", True)
        ## ==> END ##


        ## ==> MOVE WINDOW / MAXIMIZE / RESTORE
        ########################################################################
        def moveWindow(event):
            # IF MAXIMIZED CHANGE TO NORMAL
            if UIFunctions.returStatus() == 1:
                UIFunctions.maximize_restore(self)

            # MOVE WINDOW
            if event.buttons() == Qt.LeftButton:
                self.move(self.pos() + event.globalPos() - self.dragPos)
                self.dragPos = event.globalPos()
                event.accept()

        # WIDGET TO MOVE
        self.ui.frame_label_top_btns.mouseMoveEvent = moveWindow
        ## ==> END ##

        ## ==> LOAD DEFINITIONS
        ########################################################################
        UIFunctions.uiDefinitions(self)
        ## ==> END ##

        ########################################################################
        ## END - WINDOW ATTRIBUTES
        ############################## ---/--/--- ##############################




        ########################################################################
        #                                                                      #
        ## START -------------- WIDGETS FUNCTIONS/PARAMETERS ---------------- ##
        #                                                                      #
        ## ==> USER CODES BELLOW                                              ##
        ########################################################################



        ## ==> QTableWidget RARAMETERS
        ########################################################################
        self.ui.tableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        ## ==> END ##



        ########################################################################
        #                                                                      #
        ## END --------------- WIDGETS FUNCTIONS/PARAMETERS ----------------- ##
        #                                                                      #
        ############################## ---/--/--- ##############################


        ## SHOW ==> MAIN WINDOW
        ########################################################################
        self.show()
        ## ==> END ##

    ########################################################################
    ## MENUS ==> DYNAMIC MENUS FUNCTIONS
    ########################################################################
    def Button(self):
        # GET BT CLICKED
        btnWidget = self.sender()

        # PAGE HOME
        if btnWidget.objectName() == "btn_home":
            self.ui.stackedWidget.setCurrentWidget(self.ui.page_home)
            UIFunctions.resetStyle(self, "btn_home")
            UIFunctions.labelPage(self, "Home")
            btnWidget.setStyleSheet(UIFunctions.selectMenu(btnWidget.styleSheet()))

       # PAGE sites_settings
        if btnWidget.objectName() == "btn_sites_settings":
            self.ui.stackedWidget.setCurrentWidget(self.ui.page_sites_settings)
            UIFunctions.resetStyle(self, "btn_sites_settings")
            UIFunctions.labelPage(self, "Sites settings")
            btnWidget.setStyleSheet(UIFunctions.selectMenu(btnWidget.styleSheet()))
            
        # PAGE import
        if btnWidget.objectName() == "btn_import":
            self.ui.stackedWidget.setCurrentWidget(self.ui.page_home)
            UIFunctions.resetStyle(self, "btn_import")
            UIFunctions.labelPage(self, "Import")
            btnWidget.setStyleSheet(UIFunctions.selectMenu(btnWidget.styleSheet()))

        # PAGE NEW USER
        if btnWidget.objectName() == "btn_new_user":
            self.ui.stackedWidget.setCurrentWidget(self.ui.page_home)
            UIFunctions.resetStyle(self, "btn_new_user")
            UIFunctions.labelPage(self, "New User")
            btnWidget.setStyleSheet(UIFunctions.selectMenu(btnWidget.styleSheet()))

        # PAGE WIDGETS
        if btnWidget.objectName() == "btn_widgets":
            self.ui.stackedWidget.setCurrentWidget(self.ui.page_widgets)
            UIFunctions.resetStyle(self, "btn_widgets")
            UIFunctions.labelPage(self, "Custom Widgets")
            btnWidget.setStyleSheet(UIFunctions.selectMenu(btnWidget.styleSheet()))



    ## ==> END ##

    ########################################################################
    ## START ==> APP EVENTS
    ########################################################################

    ## EVENT ==> MOUSE DOUBLE CLICK
    ########################################################################
    def eventFilter(self, watched, event):
        if watched == self.le and event.type() == QtCore.QEvent.MouseButtonDblClick:
            print("pos: ", event.pos())
    ## ==> END ##

    ## EVENT ==> MOUSE CLICK
    ########################################################################
    def mousePressEvent(self, event):
        self.dragPos = event.globalPos()
        if event.buttons() == Qt.LeftButton:
            #sitepref = self.dia_site_preferences()
            print('Mouse click: LEFT CLICK')
        if event.buttons() == Qt.RightButton:
            print('Mouse click: RIGHT CLICK')
        if event.buttons() == Qt.MidButton:
            print('Mouse click: MIDDLE BUTTON')
    ## ==> END ##

    ## EVENT ==> KEY PRESSED
    ########################################################################
    def keyPressEvent(self, event):
        print('Key: ' + str(event.key()) + ' | Text Press: ' + str(event.text()))
    ## ==> END ##

    ## EVENT ==> RESIZE EVENT
    ########################################################################
    def resizeEvent(self, event):
        self.resizeFunction()
        return super(MainWindow, self).resizeEvent(event)

    def resizeFunction(self):
        print('Height: ' + str(self.height()) + ' | Width: ' + str(self.width()))
    ## ==> END ##

    ########################################################################
    ## END ==> APP EVENTS
    ############################## ---/--/--- ##############################


    ########################################################################
    ## call ==> site pref
    ############################## ---/--/--- ##############################
    def dia_site_preferences(self, data=None):
        dia = QDialog(self)
        dia.setStyleSheet(u"background-color: rgb(39, 44, 54);\n"
"border-radius: 5px;")
        
        dia.setWindowTitle(("Site Preferences"))
        dia.resize(950,550)
        font1 = QFont()
        font1.setFamily(u"Segoe UI")
        font1.setPointSize(10)
        font1.setBold(True)
        font1.setWeight(75)
        
        self.label = QLabel(("Please select which sites you play on and enter your usernames."))
        self.label.setFont(font1)
        self.label.setStyleSheet(u"background: transparent;\n"
"")

        dia.setLayout(QVBoxLayout())
        dia.layout().addWidget(self.label)
        
        self.load_profile()
        site_names = self.config.site_ids
        available_site_names=[]
        for site_name in site_names:
            try:
                tmp = self.config.supported_sites[site_name].enabled
                available_site_names.append(site_name)
            except KeyError:
                pass
        
        column_headers=[("Site"), ("Detect"), ("Screen Name"), ("Hand History Path"), "", ("Tournament Summary Path"), ""]  # todo ("HUD")
        #HUD column will contain a button that shows favseat and HUD locations. Make it possible to load screenshot to arrange HUD windowlets.

        table = QGridLayout()
        table.setSpacing(0)

        scrolling_frame = QScrollArea(dia)
        dia.layout().addWidget(scrolling_frame)
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
        for site_number in range(0, len(available_site_names)):
            check_button = QCheckBox(available_site_names[site_number])
            check_button.setChecked(self.config.supported_sites[available_site_names[site_number]].enabled)
            table.addWidget(check_button, y_pos, 0)
            check_buttons.append(check_button)
            
            hero = QLineEdit()
            hero.setText(self.config.supported_sites[available_site_names[site_number]].screen_name)
            table.addWidget(hero, y_pos, 2)
            screen_names.append(hero)
            hero.textChanged.connect(partial(self.autoenableSite, checkbox=check_buttons[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[available_site_names[site_number]].HH_path)
            table.addWidget(entry, y_pos, 3)
            history_paths.append(entry)
            
            choose1 = QPushButton("Browse")
            table.addWidget(choose1, y_pos, 4)
            choose1.clicked.connect(partial(self.browseClicked, parent=dia, path=history_paths[site_number]))
            
            entry = QLineEdit()
            entry.setText(self.config.supported_sites[available_site_names[site_number]].TS_path)
            table.addWidget(entry, y_pos, 5)
            summary_paths.append(entry)

            choose2 = QPushButton("Browse")
            table.addWidget(choose2, y_pos, 6)
            choose2.clicked.connect(partial(self.browseClicked, parent=dia, path=summary_paths[site_number]))
            
            if available_site_names[site_number] in detector.supportedSites:
                button = QPushButton(("Detect"))
                table.addWidget(button, y_pos, 1)
                button.clicked.connect(partial(self.detect_clicked, data=(detector, available_site_names[site_number], screen_names[site_number], history_paths[site_number], summary_paths[site_number])))
            y_pos+=1

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dia)
        btns.accepted.connect(dia.accept)
        btns.rejected.connect(dia.reject)
        dia.layout().addWidget(btns)

        response = dia.exec_()
        if response:
            for site_number in range(0, len(available_site_names)):
                #print "site %s enabled=%s name=%s" % (available_site_names[site_number], check_buttons[site_number].get_active(), screen_names[site_number].get_text(), history_paths[site_number].get_text())
                self.config.edit_site(available_site_names[site_number], str(check_buttons[site_number].isChecked()), screen_names[site_number].text(), history_paths[site_number].text(), summary_paths[site_number].text())
            
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

    def autoenableSite(self, text, checkbox):
        #autoactivate site if something gets typed in the screename field
        checkbox.setChecked(True)
                
    def browseClicked(self, widget, parent, path):
        """runs when user clicks one of the browse buttons for the TS folder"""

        newpath = QFileDialog.getExistingDirectory(parent, ("Please choose the path that you want to Auto Import"), path.text())
        if newpath:
            path.setText(newpath)




if __name__ == "__main__":
    app = QApplication(sys.argv)
    QtGui.QFontDatabase.addApplicationFont('fonts/segoeui.ttf')
    QtGui.QFontDatabase.addApplicationFont('fonts/segoeuib.ttf')
    window = MainWindow()
    sys.exit(app.exec_())
