#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

from __future__ import print_function

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QTreeView, QHeaderView, QAbstractItemView, QStandardItemModel, QStandardItem, QMessageBox
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt


#import L10n
#_ = L10n.get_translation()

import os
import sys
import traceback
import queue
import re

import logging

import Exceptions
import Configuration
import Database
import SQL

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("maintdbs")

class GuiDatabase(object):

    # columns in liststore:
    MODEL_DBMS = 0
    MODEL_NAME = 1
    MODEL_DESC = 2
    MODEL_USER = 3
    MODEL_PASS = 4
    MODEL_HOST = 5
    MODEL_DFLT = 6
    MODEL_DFLTIC = 7
    MODEL_STATUS = 8
    MODEL_STATIC = 9

    # columns in listview:
    COL_DBMS = 0
    COL_NAME = 1
    COL_DESC = 2
    COL_USER = 3
    COL_PASS = 4
    COL_HOST = 5
    COL_DFLT = 6
    COL_ICON = 7





class Example(QWidget):
    """
    A class representing an example object
    """
    def __init__(self, config, mainwin, dia):
        """
        Initializes the Example object

        :param config: the configuration
        :param mainwin: the main window
        :param dia: the dia object
        """
        super().__init__()
        self.config = config
        self.main_window = mainwin
        self.dia = dia

        try:
            # Set up the dialog
            self.vbox = QVBoxLayout(self)
            self.action_area = QDialogButtonBox(Qt.Horizontal)
            self.vbox.addWidget(self.action_area)

            # Set up the horizontal box
            h = QHBoxLayout()
            self.vbox.addLayout(h)

            # Set up the vertical box for buttons
            vbtn = QVBoxLayout()
            h.addLayout(vbtn)

            # List of databases in self.config.supported_databases:
            self.liststore = QStandardItemModel(0, 10, self)
            # dbms, name, comment, user, passwd, host, "", default_icon, status, icon
            self.listview = QTreeView()
            self.listview.setModel(self.liststore)
            self.listview.setRootIsDecorated(False)
            self.listview.setSortingEnabled(True)
            self.listview.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.listview.setSelectionMode(QAbstractItemView.SingleSelection)
            self.listview.setDragEnabled(False)
            self.listview.setEditTriggers(QAbstractItemView.NoEditTriggers)
            h.addWidget(self.listview, 1)

            # Add buttons
            add_button = QPushButton("Add")
            add_button.clicked.connect(self.addDB)
            vbtn.addWidget(add_button)

            refresh_button = QPushButton("Refresh")
            refresh_button.clicked.connect(self.refresh)
            vbtn.addWidget(refresh_button)

            # Add columns
            self.addTextColumn("Type", 0, False)
            self.addTextColumn("Name", 1, False)
            self.addTextColumn("Description", 2, True)
            self.addTextColumn("Username", 3, True)
            self.addTextColumn("Password", 4, True)
            self.addTextColumn("Host", 5, True)
            self.addTextObjColumn("Open", 6, 6)
            self.addTextObjColumn("Status", 7, 8)

            # Show the dialog and load the databases
            self.show()
            self.loadDbs()

        except:
            # Handle any exceptions and print the error
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            print('guidbmaint: '+ err[2] + "(" + str(err[1]) + "): ")




    def dialog_response_cb(self, dialog, response_id):
        """
        Callback function for handling dialog responses.

        Args:
            dialog: QDialog object that triggered the response.
            response_id: Response ID of the button that was clicked.

        Returns:
            The response ID of the button that was clicked.
        """
        log.info(f'dialog_response_cb: response_id={response_id}')  # Log the response ID for debugging purposes.
        dialog.accept()  # Close the dialog.
        return response_id  # Return the response ID.


    def get_dialog(self):
        """
        Returns the dia parameter.
        """
        return self.dia


    def addTextColumn(self, title, n, editable=False):
        """
        Adds a QTreeView column with a QStandardItemModel to the widget.

        Parameters:
        title (str): The title of the column.
        n (int): The number of rows in the column.
        editable (bool, optional): Whether the column is editable. Defaults to False.

        Returns:
        QTreeView: The added column.
        """

        # Create a QTreeView column
        col = QTreeView()

        # Hide the header
        col.setHeaderHidden(True)

        # Disable editing
        col.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Set selection behavior to select entire rows
        col.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Enable word wrapping
        col.setWordWrap(True)

        # Create a QStandardItemModel and set it as the model for the column
        cRender = QStandardItemModel()
        col.setModel(cRender)

        # Set the model's editable property
        cRender.editable = editable

        # Connect the dataChanged signal to the edited_cb slot
        cRender.dataChanged.connect(self.edited_cb)

        # Set the section resize mode to resize to contents
        col.header().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Stretch the last section to fill the available space
        col.header().setStretchLastSection(True)

        # Disable highlighting of sections
        col.header().setHighlightSections(False)

        # Set the minimum section size to a large value to prevent resizing
        col.header().setMinimumSectionSize(1000)

        # Set the spacing between sections to 0
        col.header().setSpacing(0)

        # Allow clicking on the column and connect the clicked signal to the sortCols slot
        col.setClickable(True)
        col.clicked.connect(self.sortCols)

        # Append the column to the listview and listcols lists
        self.listview.append(col)
        self.listcols.append(col)

        # Return the added column
        return col



    def edited_cb(self, index, new_text):
        """
        Callback function that is called when a cell in the table is edited.

        Args:
            index: QModelIndex of the cell that was edited.
            new_text: The new text that is in the cell.

        Returns:
            None
        """
        # Get the row and column of the cell that was edited.
        row = index.row()
        col = index.column()

        # Get the name of the database from the liststore.
        name = self.liststore[row][self.COL_NAME]

        # Validate new value (only for dbms so far, but dbms now not updateable so no validation at all!)
        if col == self.COL_DBMS:
            if new_text not in Configuration.DATABASE_TYPES:
                valid = False

        valid = True

        # If the new value is valid, update the liststore and the database parameters.
        if valid:
            self.liststore[row][col] = new_text

            self.config.set_db_parameters(
                db_server=self.liststore[row][self.COL_DBMS],
                db_name=name,
                db_desc=self.liststore[row][self.COL_DESC],
                db_ip=self.liststore[row][self.COL_HOST],
                db_user=self.liststore[row][self.COL_USER],
                db_pass=self.liststore[row][self.COL_PASS]
            )

            # Set the changes flag to True.
            self.changes = True

        return



    def check_new_name(self, path, new_text):
        """
        Check if the new database name is unique. If it is not unique,
        display a pop-up error message.

        Args:
            path: The path of the database in the liststore.
            new_text: The new name that the user wants to give to the database.

        Returns:
            True if the new name is unique, False otherwise.
        """
        name_ok = True

        for i, db in enumerate(self.liststore):
            if i != path and new_text == db[self.COL_NAME]:
                name_ok = False

        # If the name is not unique, display a pop-up error message.
        if not name_ok:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Error")
            msg_box.setText("Database name must be unique.")
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()

        return name_ok




    def addTextObjColumn(self, title, viewcol, storecol, editable=False):
        # Create a new column.
        col = QTreeView()
        col.setHeaderHidden(True)
        col.setUniformRowHeights(True)
        col.setEditTriggers(QAbstractItemView.NoEditTriggers)
        col.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Add the column to the tree view.
        self.listview.addColumn(col)

        # Create a text cell renderer and add it to the column.
        cRenderT = QStandardItemModel()
        cRenderT.setColumnCount(1)
        cRenderT.setRowCount(len(self.liststore))
        for i, db in enumerate(self.liststore):
            item = QStandardItem(db[storecol])
            item.setEditable(False)
            cRenderT.setItem(i, 0, item)

        col.setModel(cRenderT)
        col.setItemDelegate(QStyledItemDelegate())

        # Create a pixmap cell renderer and add it to the column.
        cRenderP = QStandardItemModel()
        cRenderP.setColumnCount(1)
        cRenderP.setRowCount(len(self.liststore))
        for i, db in enumerate(self.liststore):
            if db[storecol+1] == 'green':
                pixmap = QPixmap('green.png')
            else:
                pixmap = QPixmap('red.png')
            item = QStandardItem()
            item.setData(pixmap, Qt.DecorationRole)
            item.setEditable(False)
            cRenderP.setItem(i, 0, item)

        col.setModel(cRenderP)
        col.setItemDelegate(QStyledItemDelegate())

        # Set the maximum width of the column.
        col.setMaximumWidth(1000)

        # Add the column to the list of columns.
        self.listcols.append(col)

        # Enable sorting for the column.
        col.setSortable(True)
        col.sortByColumn(viewcol, Qt.AscendingOrder)

        return col


    def selectTest(self, widget, event):
        if event.button == 1:  # and event.type == gtk.gdk._2BUTTON_PRESS:
            pthinfo = self.listview.get_path_at_pos( int(event.x), int(event.y) )
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                row = path[0]
                if col == self.listcols[self.COL_DFLT]:
                    if self.liststore[row][self.MODEL_STATUS] == 'ok' and self.liststore[row][self.MODEL_DFLTIC] is None:
                        self.setDefaultDB(row)

    def setDefaultDB(self, row):
        print("set new defaultdb:", row, self.liststore[row][self.MODEL_NAME])
        for r in range(len(self.liststore)):
            if r == row:
                self.liststore[r][self.MODEL_DFLTIC] = gtk.STOCK_APPLY
                default = "True"
            else:
                self.liststore[r][self.MODEL_DFLTIC] = None
                default = "False"

            self.config.set_db_parameters( db_server = self.liststore[r][self.COL_DBMS]
                                         , db_name = self.liststore[r][self.COL_NAME]
                                         , db_desc = self.liststore[r][self.COL_DESC]
                                         , db_ip   = self.liststore[r][self.COL_HOST]
                                         , db_user = self.liststore[r][self.COL_USER]
                                         , db_pass = self.liststore[r][self.COL_PASS]
                                         , default = default
                                         )
        self.changes = True
        return
        

    def loadDbs(self):

        self.liststore.clear()
        #self.listcols = []
        dia = InfoBox( parent=self.dia, str1=('Testing database connections ... ') )
        while gtk.events_pending():
            gtk.main_iteration() 

        try:
            # want to fill: dbms, name, comment, user, passwd, host, default, status, icon
            for name in self.config.supported_databases: #db_ip/db_user/db_pass/db_server
                dbms = self.config.supported_databases[name].db_server  # mysql/postgresql/sqlite
                dbms_num = self.config.get_backend(dbms)              #   2  /    3     /  4
                comment = self.config.supported_databases[name].db_desc
                if dbms == 'sqlite':
                    user = ""
                    passwd = ""
                else:
                    user = self.config.supported_databases[name].db_user
                    passwd = self.config.supported_databases[name].db_pass
                host = self.config.supported_databases[name].db_ip
                default = (name == self.config.db_selected)
                default_icon = None
                if default:  default_icon = gtk.STOCK_APPLY
                
                status, err_msg, icon = GuiDatabase.testDB(self.config, dbms, dbms_num, name, user, passwd, host)

                b = gtk.Button(name)
                b.show()
                iter = self.liststore.append( (dbms, name, comment, user, passwd, host, "", default_icon, status, icon) )

            dia.add_msg(("finished."), False, True )
            self.listview.show()
            self.scrolledwindow.show()
            self.vbox.show()
            self.dia.set_focus(self.listview)

            self.vbox.show_all()
            self.dia.show()
        except:
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            print(('loadDbs error: ')+str(dbms_num)+','+host+','+name+','+user+','+passwd+' failed: ' \
                      + err[2] + "(" + str(err[1]) + "): " + str(sys.exc_info()[1]))

    def sortCols(self, col, n):
        try:
            log.info('sortcols n='+str(n))
            if not col.get_sort_indicator() or col.get_sort_order() == gtk.SORT_ASCENDING:
                col.set_sort_order(gtk.SORT_DESCENDING)
            else:
                col.set_sort_order(gtk.SORT_ASCENDING)
            self.liststore.set_sort_column_id(n, col.get_sort_order())
            #self.liststore.set_sort_func(n, self.sortnums, (n,grid))
            log.info('sortcols len(listcols)='+str(len(self.listcols)))
            for i in range(len(self.listcols)):
                log.info('sortcols i='+str(i))
                self.listcols[i].set_sort_indicator(False)
            self.listcols[n].set_sort_indicator(True)
            # use this   listcols[col].set_sort_indicator(True)
            # to turn indicator off for other cols
        except:
            err = traceback.extract_tb(sys.exc_info()[2])
            print("***sortCols " + ("error") + ": " + str(sys.exc_info()[1]))
            print("\n".join( [e[0]+':'+str(e[1])+" "+e[2] for e in err] ))
            log.info('sortCols ' + ('error') + ': ' + str(sys.exc_info()) )

    def refresh(self, widget, data):
        self.loadDbs()

    def addDB(self, widget, data):
        adb = AddDB(self.config, self.dia)
        (status, err_msg, icon, dbms, dbms_num, name, comment, user, passwd, host) = adb.run()
        adb.destroy()

        # save in liststore
        if status == 'ok':
            iter = self.liststore.append( (dbms, name, comment, user, passwd, host, "", None, status, icon) )

            # keep config save code in line with edited_cb()? call common routine?

            valid = True
            # Validate new value (only for dbms so far, but dbms now not updateable so no validation at all!)
            #if col == self.COL_DBMS:
            #    if new_text not in Configuration.DATABASE_TYPES:
            #        valid = False

            if valid:
                self.config.add_db_parameters( db_server = dbms
                                             , db_name = name
                                             , db_desc = comment
                                             , db_ip   = host
                                             , db_user = user
                                             , db_pass = passwd )
                self.config.save()
                self.changes = False


    @staticmethod
    def testDB(config, dbms, dbms_num, name, user, passwd, host):
        status = ""
        icon = None
        err_msg = ""

        sql = SQL.Sql(db_server=dbms)
        db = Database.Database(config, sql = sql, autoconnect = False)
        # try to connect to db, set status and err_msg if it fails
        try:
            # is creating empty db for sqlite ... mod db.py further?
            # add noDbTables flag to db.py?
            log.debug("testDB: " + ("trying to connect to:") + " %s/%s, %s, %s/%s" % (str(dbms_num),dbms,name,user,passwd))
            db.connect(backend=dbms_num, host=host, database=name, user=user, password=passwd, create=False)
            if db.connected:
                log.debug(("connected ok"))
                status = 'ok'
                icon = gtk.STOCK_APPLY
                if db.wrongDbVersion:
                    status = 'old'
                    icon = gtk.STOCK_INFO
            else:
                log.debug(("not connected but no exception"))
        except Exceptions.FpdbMySQLAccessDenied:
            err_msg = ("MySQL Server reports: Access denied. Are your permissions set correctly?")
            status = "failed"
            icon = gtk.STOCK_CANCEL
        except Exceptions.FpdbMySQLNoDatabase:
            err_msg = ("MySQL client reports: 2002 or 2003 error. Unable to connect - ") \
                      + ("Please check that the MySQL service has been started")
            status = "failed"
            icon = gtk.STOCK_CANCEL
        except Exceptions.FpdbPostgresqlAccessDenied:
            err_msg = ("PostgreSQL Server reports: Access denied. Are your permissions set correctly?")
            status = "failed"
        except Exceptions.FpdbPostgresqlNoDatabase:
            err_msg = ("PostgreSQL client reports: Unable to connect - ") \
                      + ("Please check that the PostgreSQL service has been started")
            status = "failed"
            icon = gtk.STOCK_CANCEL
        except:
            # add more specific exceptions here if found (e.g. for sqlite?)
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            err_msg = err[2] + "(" + str(err[1]) + "): " + str(sys.exc_info()[1])
            status = "failed"
            icon = gtk.STOCK_CANCEL
        if err_msg:
            log.info(('db connection to %s, %s, %s, %s, %s failed: %s') % (str(dbms_num), host, name, user, passwd, err_msg))

        return( status, err_msg, icon )


class AddDB(gtk.Dialog):

    def __init__(self, config, parent):
        log.debug(("AddDB starting"))
        self.dbnames = { 'Sqlite'     : Configuration.DATABASE_TYPE_SQLITE
                       , 'MySQL'      : Configuration.DATABASE_TYPE_MYSQL
                       , 'PostgreSQL' : Configuration.DATABASE_TYPE_POSTGRESQL
                       }
        self.config = config
        # create dialog and add icon and label
        super(AddDB,self).__init__( parent=parent
                                  , flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
                                  , title=("Add New Database")
                                  , buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT
                                              ,gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
                                  ) # , buttons=btns
        self.set_default_size(450, 280)
        #self.connect('response', self.response_cb)

        t = gtk.Table(5, 3, True)
        self.vbox.pack_start(t, expand=False, fill=False, padding=3)

        l = gtk.Label( ("DB Type") )
        l.set_alignment(1.0, 0.5)
        t.attach(l, 0, 1, 0, 1, xpadding=3)
        self.cb_dbms = gtk.combo_box_new_text()
        for s in ('Sqlite',):  # keys(self.dbnames):
            self.cb_dbms.append_text(s)
        self.cb_dbms.set_active(0)
        t.attach(self.cb_dbms, 1, 3, 0, 1, xpadding=3)
        self.cb_dbms.connect("changed", self.db_type_changed, None)

        l = gtk.Label( ("DB Name") )
        l.set_alignment(1.0, 0.5)
        t.attach(l, 0, 1, 1, 2, xpadding=3)
        self.e_db_name = gtk.Entry()
        self.e_db_name.set_width_chars(15)
        t.attach(self.e_db_name, 1, 3, 1, 2, xpadding=3)
        self.e_db_name.connect("focus-out-event", self.db_name_changed, None)

        l = gtk.Label( ("DB Description") )
        l.set_alignment(1.0, 0.5)
        t.attach(l, 0, 1, 2, 3, xpadding=3)
        self.e_db_desc = gtk.Entry()
        self.e_db_desc.set_width_chars(15)
        t.attach(self.e_db_desc, 1, 3, 2, 3, xpadding=3)

        self.l_username = gtk.Label( ("Username") )
        self.l_username.set_alignment(1.0, 0.5)
        t.attach(self.l_username, 0, 1, 3, 4, xpadding=3)
        self.e_username = gtk.Entry()
        self.e_username.set_width_chars(15)
        t.attach(self.e_username, 1, 3, 3, 4, xpadding=3)

        self.l_password = gtk.Label(("Password") )
        self.l_password.set_alignment(1.0, 0.5)
        t.attach(self.l_password, 0, 1, 4, 5, xpadding=3)
        self.e_password = gtk.Entry()
        self.e_password.set_width_chars(15)
        t.attach(self.e_password, 1, 3, 4, 5, xpadding=3)

        self.l_host = gtk.Label(("Host Computer") )
        self.l_host.set_alignment(1.0, 0.5)
        t.attach(self.l_host, 0, 1, 5, 6, xpadding=3)
        self.e_host = gtk.Entry()
        self.e_host.set_width_chars(15)
        self.e_host.set_text("localhost")
        t.attach(self.e_host, 1, 3, 5, 6, xpadding=3)

        parent.show_all()
        self.show_all()

        # hide username/password fields as not used by sqlite
        self.l_username.hide()
        self.e_username.hide()
        self.l_password.hide()
        self.e_password.hide()

    def run(self):
        response = super(AddDB,self).run()
        log.debug(("addDB.run: response is %s, accept is %s") % (str(response), str(int(gtk.RESPONSE_ACCEPT))))

        ok,retry = False,True
        while response == gtk.RESPONSE_ACCEPT:
            ok,retry = self.check_fields()
            if retry:
                response = super(AddDB,self).run()
            else:
                response = gtk.RESPONSE_REJECT

        (status, err_msg, icon, dbms, dbms_num
        ,name, db_desc, user, passwd, host) = ("error", "error", None, None, None
                                              ,None, None, None, None, None)
        if ok:
            log.debug(("start creating new db"))
            # add a new db
            master_password = None
            dbms     = self.dbnames[ self.cb_dbms.get_active_text() ]
            dbms_num = self.config.get_backend(dbms)
            name     = self.e_db_name.get_text()
            db_desc  = self.e_db_desc.get_text()
            user     = self.e_username.get_text()
            passwd   = self.e_password.get_text()
            host     = self.e_host.get_text()
            
            # TODO:
            # if self.cb_dbms.get_active_text() == 'Postgres':
            #     <ask for postgres master password>
            
            # create_db()  in Database.py or here? ... TODO

            # test db after creating?
            status, err_msg, icon = GuiDatabase.testDB(self.config, dbms, dbms_num, name, user, passwd, host)
            log.debug(('tested new db, result=%s') % str((status,err_msg)))
            if status == 'ok':
                #dia = InfoBox( parent=self, str1=('Database created') )
                str1 = ('Database created')
            else:
                #dia = InfoBox( parent=self, str1=('Database creation failed') )
                str1 = ('Database creation failed')
            #dia.add_msg("", True, True)
            btns = (gtk.BUTTONS_OK)
            dia = gtk.MessageDialog( parent=self, flags=gtk.DIALOG_DESTROY_WITH_PARENT
                                   , type=gtk.MESSAGE_INFO, buttons=(btns), message_format=str1 )
            dia.run()

        return( (status, err_msg, icon, dbms, dbms_num, name, db_desc, user, passwd, host) )

    def check_fields(self):
        """check fields and return true/false according to whether user wants to try again
           return False if fields are ok
        """
        log.debug(("check_fields: starting"))
        try_again = False
        ok = True

        # checks for all db's
        if self.e_db_name.get_text() == "":
            msg = ("No Database Name given")
            ok = False
        elif self.e_db_desc.get_text() is None or self.e_db_desc.get_text() == "":
            msg = ("No Database Description given")
            ok = False
        elif self.cb_dbms.get_active_text() != 'Sqlite' and self.e_username.get_text() == "":
            msg = ("No Username given")
            ok = False
        elif self.cb_dbms.get_active_text() != 'Sqlite' and self.e_password.get_text() == "":
            msg = ("No Password given")
            ok = False
        elif self.e_host.get_text() == "":
            msg = ("No Host given")
            ok = False

        if ok:
            if self.cb_dbms.get_active_text() == 'Sqlite':
                # checks for sqlite
                pass
            elif self.cb_dbms.get_active_text() == 'MySQL':
                # checks for mysql
                pass
            elif self.cb_dbms.get_active_text() == 'Postgres':
                # checks for postgres
                pass
            else:
                msg = ("Unknown Database Type selected")
                ok = False

        if not ok:
            log.debug(("check_fields: open dialog"))
            dia = gtk.MessageDialog( parent=self
                                   , flags=gtk.DIALOG_DESTROY_WITH_PARENT
                                   , type=gtk.MESSAGE_ERROR
                                   , message_format=msg
                                   , buttons = gtk.BUTTONS_YES_NO
                                   )
            #l = gtk.Label(msg)
            #dia.vbox.add(l)
            l = gtk.Label(("Do you want to try again?") )
            dia.vbox.add(l)
            dia.show_all()
            ret = dia.run()
            #log.debug(("check_fields: ret is %s cancel is %s") % (str(ret), str(int(gtk.RESPONSE_CANCEL))))
            if ret == gtk.RESPONSE_YES:
                try_again = True
            #log.debug(("check_fields: destroy dialog"))
            dia.hide()
            dia.destroy()

        #log.debug(("check_fields: returning ok as %s, try_again as %s") % (str(ok), str(try_again)))
        return(ok,try_again)

    def db_type_changed(self, widget, data):
        if self.cb_dbms.get_active_text() == 'Sqlite':
            self.l_username.hide()
            self.e_username.hide()
            self.e_username.set_text("")
            self.l_password.hide()
            self.e_password.hide()
            self.e_password.set_text("")
        else:
            self.l_username.show()
            self.e_username.show()
            self.l_password.show()
            self.e_password.show()
        return(response)

    def db_name_changed(self, widget, event, data):
        log.debug('db_name_changed: text='+widget.get_text())
        if not re.match('\....$', widget.get_text()):
            widget.set_text(widget.get_text()+'.db3')
            widget.show()

    #def response_cb(self, dialog, data):
    #    dialog.destroy()
    #    return(data)


class InfoBox(gtk.Dialog):

    def __init__(self, parent, str1):
        # create dialog and add icon and label
        btns = (gtk.BUTTONS_OK)
        btns = None
        # messagedialog puts text in inverse colors if no buttons are displayed??
        #dia = gtk.MessageDialog( parent=self.main_window, flags=gtk.DIALOG_DESTROY_WITH_PARENT
        #                       , type=gtk.MESSAGE_INFO, buttons=(btns), message_format=str1 )
        # so just use Dialog instead
        super(InfoBox,self).__init__( parent=parent
                                    , flags=gtk.DIALOG_DESTROY_WITH_PARENT
                                    , title="" ) # , buttons=btns
        
        h = gtk.HBox(False, 2)
        i = gtk.Image()
        i.set_from_stock(gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_DIALOG)
        l = gtk.Label(str1)
        h.pack_start(i, padding=5)
        h.pack_start(l, padding=5)
        self.vbox.pack_start(h)
        parent.show_all()
        self.show_all()

    def add_msg(self, str1, run, destroy):
        # add extra label
        self.vbox.pack_start( gtk.Label(str1) )
        self.show_all()
        response = None
        if run:      response = self.run()
        if destroy:  self.destroy()
        return (response)


class SideButton(gtk.Button):
    """Create a button with the label below the icon"""

    # to change label on buttons:
    # ( see http://faq.pygtk.org/index.py?req=show&file=faq09.005.htp )
    # gtk.stock_add([(gtk.STOCK_ADD, _("Add"), 0, 0, "")])

    # alternatively:
    # button = gtk.Button(stock=gtk.STOCK_CANCEL)
    # button.show()
    # alignment = button.get_children()[0]
    # hbox = alignment.get_children()[0]
    # image, label = hbox.get_children()
    # label.set_text('Hide')

    def __init__(self, label=None, stock=None, use_underline=True):
        gtk.stock_add([(stock, label, 0, 0, "")])

        super(SideButton, self).__init__(label=label, stock=stock, use_underline=True)
        alignment = self.get_children()[0]
        hbox = alignment.get_children()[0]
        image, label = hbox.get_children()
        #label.set_text('Hide')
        hbox.remove(image)
        hbox.remove(label)
        v = gtk.VBox(False, spacing=3)
        v.pack_start(image, 3)
        v.pack_start(label, 3)
        alignment.remove(hbox)
        alignment.add(v)
        self.show_all()




if __name__ == '__main__':
    config = Configuration.Config()

    app = QApplication(sys.argv)

    dia = QDialog()
    dia.setWindowTitle('Maintain Databases')
    dia.setFixedSize(500, 500)

    layout = QVBoxLayout()

    button = QPushButton('Close')
    button.clicked.connect(dia.accept)

    layout.addWidget(button)
    dia.setLayout(layout)

    log = GuiDatabase(config, None, dia)
    dia.show()

    sys.exit(app.exec_())





