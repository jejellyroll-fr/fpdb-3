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
from PyQt5.QtGui import *


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

class GuiDatabase(QWidget):

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
        """
        Adds a new column to the tree view with a text cell renderer and a pixmap cell renderer.

        Args:
            title: The title of the new column.
            viewcol: The index of the column in the view.
            storecol: The index of the column in the store.
            editable: A boolean indicating whether the column should be editable.

        Returns:
            The newly created column.
        """

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
        """
        Select a test based on a mouse event.

        Args:
            widget: The widget the event occurred on.
            event: The mouse event that occurred.
        """
        if event.button() == Qt.LeftButton:  # Check if the left mouse button was clicked
            pthinfo = self.listview.indexAt(QPoint(event.x(), event.y()))  # Get the item clicked on in the list view
            if pthinfo.isValid():  # Check if the item is valid
                row = pthinfo.row()  # Get the row of the item
                col = pthinfo.column()  # Get the column of the item
                if col == self.listcols[self.COL_DFLT]:  # Check if the column is the default column
                    if self.liststore[row][self.MODEL_STATUS] == 'ok' and self.liststore[row][self.MODEL_DFLTIC] is None:  # Check if the status is okay and the default icon is None
                        self.setDefaultDB(row)  # Set the default database for the selected item



    def setDefaultDB(self, row):
        """
        Sets the default database to the specified row index and updates the configuration.

        Args:
            row (int): The index of the row to set as default.

        Returns:
            None
        """
        # Print a message indicating the new defaultdb
        print("set new defaultdb:", row, self.liststore[row][self.MODEL_NAME])

        # Loop through all rows in the liststore
        for r in range(len(self.liststore)):
            # Check if the current row is the one we're setting as default
            if r == row:
                # If so, set the MODEL_DFLTIC to a checkmark icon
                self.liststore[r][self.MODEL_DFLTIC] = Qt.STOCK_APPLY
                default = "True"
            else:
                # Otherwise, set the MODEL_DFLTIC to None
                self.liststore[r][self.MODEL_DFLTIC] = None
                default = "False"

            # Update the configuration with the parameters from the current row
            self.config.set_db_parameters(db_server=self.liststore[r][self.COL_DBMS],
                                        db_name=self.liststore[r][self.COL_NAME],
                                        db_desc=self.liststore[r][self.COL_DESC],
                                        db_ip=self.liststore[r][self.COL_HOST],
                                        db_user=self.liststore[r][self.COL_USER],
                                        db_pass=self.liststore[r][self.COL_PASS],
                                        default=default
                                        )

        # Mark that changes have been made
        self.changes = True
        return



    def loadDbs(self):
        """
        Load supported databases and test their connection status

        :return: None
        """
        # Clear the liststore
        self.liststore.clear()

        # Create an info box to display progress
        dia = InfoBox(parent=self.dia, str1=('Testing database connections ... '))

        # Wait for events to be processed
        while QApplication.instance().processEvents():
            pass

        try:
            # Loop through all supported databases
            for name in self.config.supported_databases:
                # Get the database server and backend number
                dbms = self.config.supported_databases[name].db_server  # mysql/postgresql/sqlite
                dbms_num = self.config.get_backend(dbms)              #   2  /    3     /  4

                # Get the database comment, user, password, and host
                comment = self.config.supported_databases[name].db_desc
                if dbms == 'sqlite':
                    user = ""
                    passwd = ""
                else:
                    user = self.config.supported_databases[name].db_user
                    passwd = self.config.supported_databases[name].db_pass
                host = self.config.supported_databases[name].db_ip

                # Check if this database is the default
                default = (name == self.config.db_selected)
                default_icon = None
                if default:
                    default_icon = Qt.STOCK_APPLY

                # Test the database connection and get its status, error message, and icon
                status, err_msg, icon = GuiDatabase.testDB(self.config, dbms, dbms_num, name, user, passwd, host)

                # Create a button with the database name and add it to the liststore
                button = QPushButton(name)
                button.show()
                iter = self.liststore.append((dbms, name, comment, user, passwd, host, "", default_icon, status, icon))

            # Display finished message and show the listview and scrolledwindow
            dia.add_msg(("finished."), False, True)
            self.listview.show()
            self.scrolledwindow.show()
            self.vbox.show()
            self.dia.setFocus(self.listview)

            self.vbox.show()
            self.dia.show()
        except:
            # If there is an error, print it and show an error message
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            print(('loadDbs error: ') + str(dbms_num) + ',' + host + ',' + name + ',' + user + ',' + passwd + ' failed: ' \
                + err[2] + "(" + str(err[1]) + "): " + str(sys.exc_info()[1]))

    def sortCols(self, col, n):
        """Sort a column in a list.

        Args:
            col (QHeaderView): Header view of the column to sort.
            n (int): Index of the column to sort in the list.

        Returns:
            None
        """

        try:
            # log sorting action
            log.info('sortcols n='+str(n))

            # if no sort indicator or currently sorted in ascending order, sort in descending order
            if not col.sortIndicator() or col.sortOrder() == Qt.AscendingOrder:
                col.setSortOrder(Qt.DescendingOrder)
            # otherwise, sort in ascending order
            else:
                col.setSortOrder(Qt.AscendingOrder)

            # set the sort role for the column
            self.liststore.setSortRole(n, col.sortOrder())

            # turn off sort indicators for all columns except the one being sorted
            for i in range(len(self.listcols)):
                log.info('sortcols i='+str(i))
                self.listcols[i].setSortIndicator(False)
            col.setSortIndicator(True)

        except:
            # log any errors that occur during sorting
            err = traceback.extract_tb(sys.exc_info()[2])
            print("***sortCols " + ("error") + ": " + str(sys.exc_info()[1]))
            print("\n".join( [e[0]+':'+str(e[1])+" "+e[2] for e in err] ))
            log.info('sortCols ' + ('error') + ': ' + str(sys.exc_info()) )


    def refresh(self, widget, data):
        """
        This function refreshes the widget data by loading the databases.

        :param widget: The widget to be refreshed.
        :param data: The data to be refreshed.
        :return: None
        """
        # Load the databases
        self.loadDbs()


    def addDB(self, widget, data):
        """
        This function adds a new database to the liststore and saves the configuration.

        :param widget: The widget that triggered the addition of the new database.
        :param data: The data for the new database.
        :return: None
        """
        # Create a new AddDB dialog and run it
        adb = AddDB(self.config, self.dia)
        (status, err_msg, icon, dbms, dbms_num, name, comment, user, passwd, host) = adb.run()
        adb.destroy()

        # Save the new database in the liststore
        if status == 'ok':
            iter = self.liststore.append( (dbms, name, comment, user, passwd, host, "", None, status, icon) )

            # Keep the config save code in line with edited_cb()? Call a common routine?
            valid = True

            # Validate new value (only for dbms so far, but dbms now not updateable so no validation at all!)
            if col == self.COL_DBMS:
                if new_text not in Configuration.DATABASE_TYPES:
                    valid = False

            # Add the new database parameters to the configuration and save it
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
        """
        This function tests the connection to a database with the given parameters.

        :param config: The configuration object.
        :param dbms: The type of database management system.
        :param dbms_num: The number of the database management system.
        :param name: The name of the database.
        :param user: The username for the database.
        :param passwd: The password for the database.
        :param host: The hostname for the database.
        :return: A tuple containing the status, error message, and icon.
        """
        # Initialize variables
        status = ""
        icon = None
        err_msg = ""

        # Create SQL and Database objects
        sql = SQL.Sql(db_server=dbms)
        db = Database.Database(config, sql=sql, autoconnect=False)

        # Try to connect to the database
        try:
            log.debug("testDB: " + ("trying to connect to:") + " %s/%s, %s, %s/%s" % (str(dbms_num), dbms, name, user, passwd))
            db.connect(backend=dbms_num, host=host, database=name, user=user, password=passwd, create=False)

            # Check if connection was successful
            if db.connected:
                log.debug(("connected ok"))
                status = 'ok'
                icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-ok.png"))
                if db.wrongDbVersion:
                    status = 'old'
                    icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-information.png"))
            else:
                log.debug(("not connected but no exception"))

        # Handle specific exceptions for different database management systems
        except Exceptions.FpdbMySQLAccessDenied:
            err_msg = ("MySQL Server reports: Access denied. Are your permissions set correctly?")
            status = "failed"
            icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-cancel.png"))
        except Exceptions.FpdbMySQLNoDatabase:
            err_msg = ("MySQL client reports: 2002 or 2003 error. Unable to connect - ") \
                    + ("Please check that the MySQL service has been started")
            status = "failed"
            icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-cancel.png"))
        except Exceptions.FpdbPostgresqlAccessDenied:
            err_msg = ("PostgreSQL Server reports: Access denied. Are your permissions set correctly?")
            status = "failed"
        except Exceptions.FpdbPostgresqlNoDatabase:
            err_msg = ("PostgreSQL client reports: Unable to connect - ") \
                    + ("Please check that the PostgreSQL service has been started")
            status = "failed"
            icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-cancel.png"))
        except:
            # Handle all other exceptions
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            err_msg = err[2] + "(" + str(err[1]) + "): " + str(sys.exc_info()[1])
            status = "failed"
            icon = QtGui.QIcon(QtGui.QPixmap(":/icons/16x16/actions/dialog-cancel.png"))

        # Log error message if there is one
        if err_msg:
            log.info(('db connection to %s, %s, %s, %s, %s failed: %s') % (str(dbms_num), host, name, user, passwd, err_msg))

        # Return tuple containing status, error message, and icon
        return (status, err_msg, icon)


class AddDB(QDialog):
    def __init__(self, config, parent):
        """
        Initializes the AddDB class.

        Args:
            config (Configuration): The configuration object.
            parent (QWidget): The parent widget.
        """
        # Set up logging
        log.debug("AddDB starting")

        # Set database type options
        self.dbnames = {
            'Sqlite': Configuration.DATABASE_TYPE_SQLITE,
            'MySQL': Configuration.DATABASE_TYPE_MYSQL,
            'PostgreSQL': Configuration.DATABASE_TYPE_POSTGRESQL
        }

        # Store configuration object
        self.config = config

        # Call parent constructor
        super().__init__(parent=parent)

        # Set dialog properties
        self.setModal(True)
        self.setWindowTitle("Add New Database")
        self.setFixedSize(450, 280)

        # Create widgets
        layout = QGridLayout(self)

        # DB Type label and combo box
        db_type_label = QLabel("DB Type")
        layout.addWidget(db_type_label, 0, 0)
        self.cb_dbms = QComboBox()
        self.cb_dbms.addItems(['Sqlite'])
        self.cb_dbms.currentIndexChanged.connect(self.db_type_changed)
        layout.addWidget(self.cb_dbms, 0, 1, 1, 2)

        # DB Name label and text box
        db_name_label = QLabel("DB Name")
        layout.addWidget(db_name_label, 1, 0)
        self.e_db_name = QLineEdit()
        self.e_db_name.setFixedWidth(150)
        self.e_db_name.editingFinished.connect(self.db_name_changed)
        layout.addWidget(self.e_db_name, 1, 1, 1, 2)

        # DB Description label and text box
        db_desc_label = QLabel("DB Description")
        layout.addWidget(db_desc_label, 2, 0)
        self.e_db_desc = QLineEdit()
        self.e_db_desc.setFixedWidth(150)
        layout.addWidget(self.e_db_desc, 2, 1, 1, 2)

        # Username and password labels and text boxes
        self.l_username = QLabel("Username")
        self.e_username = QLineEdit()
        self.e_username.setFixedWidth(150)
        self.l_password = QLabel("Password")
        self.e_password = QLineEdit()
        self.e_password.setFixedWidth(150)
        self.e_password.setEchoMode(QLineEdit.Password)

        # Host label and text box
        host_label = QLabel("Host Computer")
        layout.addWidget(host_label, 4, 0)
        self.e_host = QLineEdit("localhost")
        self.e_host.setFixedWidth(150)
        layout.addWidget(self.e_host, 4, 1, 1, 2)

        # Hide username/password fields as not used by SQLite
        self.l_username.hide()
        self.e_username.hide()
        self.l_password.hide()
        self.e_password.hide()

        # Add buttons
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.accept)
        layout.addWidget(self.btn_cancel, 5, 2)
        layout.addWidget(self.btn_save, 5, 1)

        # Show the dialog
        parent.show()
        self.show()

    # Define functions to handle widget events
    def db_type_changed(self):
        """
        This function is called when the user changes the selected database type.
        If the database type is Sqlite, it hides the username and password fields.
        Otherwise, it shows them.
        """
        if self.cb_dbms.currentText() == 'Sqlite':
            # Hide username and password fields
            self.l_username.hide()
            self.e_username.hide()
            self.l_password.hide()
            self.e_password.hide()
        else:
            # Show username and password fields
            self.l_username.show()
            self.e_username.show()
            self.l_password.show()
            self.e_password.show()

    def db_name_changed(self):
        """
        Update the database description with the current database name.

        This function is called when the user changes the text in the database name field.
        """
        # Set the text of the database description field to the current value of the database name field.
        self.e_db_desc.setText(self.e_db_name.text())

    def run(self):
        """
        Runs the AddDB dialog.

        Returns:
            A tuple containing status, err_msg, icon, dbms, dbms_num, name, db_desc, user, passwd, and host.
        """
        # Get the response from the super class' run method
        response = super(AddDB, self).run()

        # Debug logging of response and accept value
        log.debug(("addDB.run: response is %s, accept is %s") % (str(response), str(int(QMessageBox.Accept))))

        # Loop while the response is QMessageBox.Accept
        ok, retry = False, True
        while response == QMessageBox.Accept:
            # Check fields and set ok and retry values
            ok, retry = self.check_fields()
            if retry:
                # Retry and get new response if needed
                response = super(AddDB, self).run()
            else:
                # Set response to QMessageBox.Reject
                response = QMessageBox.Reject

        # Set default values for status, err_msg, icon, dbms, dbms_num, name, db_desc, user, passwd, and host
        (status, err_msg, icon, dbms, dbms_num, name, db_desc, user, passwd, host) = ("error", "error", None, None, None, None, None, None, None, None)
        if ok:
            # Debug logging
            log.debug(("start creating new db"))

            # Set master_password to None
            master_password = None

            # Set dbms and dbms_num values based on cb_dbms.currentText()
            dbms = self.dbnames[self.cb_dbms.currentText()]
            dbms_num = self.config.get_backend(dbms)

            # Get name, db_desc, user, passwd, and host values from the dialog fields
            name = self.e_db_name.text()
            db_desc = self.e_db_desc.text()
            user = self.e_username.text()
            passwd = self.e_password.text()
            host = self.e_host.text()

            # TODO: Ask for postgres master password if self.cb_dbms.currentText() == 'Postgres'.

            # Call create_db() in Database.py or here? ... TODO

            # Test the new database after creating
            status, err_msg, icon = GuiDatabase.testDB(self.config, dbms, dbms_num, name, user, passwd, host)
            log.debug(('tested new db, result=%s') % str((status, err_msg)))
            if status == 'ok':
                # Set str1 to 'Database created' if the test was successful
                str1 = ('Database created')
            else:
                # Set str1 to 'Database creation failed' if the test was not successful
                str1 = ('Database creation failed')

            # Set button values and create and execute a QMessageBox dialog
            btns = QMessageBox.Ok
            dia = QMessageBox()
            dia.setIcon(QMessageBox.Information)
            dia.setWindowTitle("Database Creation")
            dia.setText(str1)
            dia.setStandardButtons(btns)
            dia.exec_()

        return (status, err_msg, icon, dbms, dbms_num, name, db_desc, user, passwd, host)

    def check_fields(self):
        """
        Check fields and return True/False according to whether user wants to try again.

        Returns:
            A tuple containing True if fields are ok and False if fields are not ok, and True if user wants to try again and False otherwise.
        """
        # Log that the function has started
        log.debug(("check_fields: starting"))

        # Initialize variables
        try_again = False
        ok = True

        # Checks for all databases
        if self.e_db_name.text() == "":
            msg = ("No Database Name given")
            ok = False
        elif self.e_db_desc.text() is None or self.e_db_desc.text() == "":
            msg = ("No Database Description given")
            ok = False
        elif self.cb_dbms.currentText() != 'Sqlite' and self.e_username.text() == "":
            msg = ("No Username given")
            ok = False
        elif self.cb_dbms.currentText() != 'Sqlite' and self.e_password.text() == "":
            msg = ("No Password given")
            ok = False
        elif self.e_host.text() == "":
            msg = ("No Host given")
            ok = False

        if ok:
            if self.cb_dbms.currentText() == 'Sqlite':
                # Checks for SQLite
                pass
            elif self.cb_dbms.currentText() == 'MySQL':
                # Checks for MySQL
                pass
            elif self.cb_dbms.currentText() == 'Postgres':
                # Checks for Postgres
                pass
            else:
                msg = ("Unknown Database Type selected")
                ok = False

        if not ok:
            # If fields are not ok, open a dialog and ask user if they want to try again
            log.debug(("check_fields: open dialog"))
            dia = QMessageBox()
            dia.setIcon(QMessageBox.Critical)
            dia.setWindowTitle("Error")
            dia.setText(msg)
            dia.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            l = QLabel("Do you want to try again?")
            dia.layout().addWidget(l)
            ret = dia.exec_()
            if ret == QMessageBox.Yes:
                try_again = True

        # Return a tuple containing ok status and try_again status
        #log.debug(("check_fields: returning ok as %s, try_again as %s") % (str(ok), str(try_again)))
        return (ok, try_again)
            
    def response_cb(self, dialog, data):
        """
        Callback function to handle response data from a dialog.

        Args:
            dialog (QDialog): The dialog that the response is from.
            data (Any): The response data.

        Returns:
            Any: The response data.
        """
        dialog.accept()  # close the dialog with an "accept" response
        return data  # return the response data



from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QApplication
from PyQt5.QtCore import Qt


class InfoDialog(QDialog):
    """
    A custom dialog box that displays an information icon and a message.
    """

    def __init__(self, parent: QWidget, message: str):
        """
        Initializes the dialog box.

        :param parent: The parent widget.
        :param message: The message to display.
        """
        # Call the superclass constructor
        super().__init__(parent=parent)

        # Set window flags to customize the appearance of the dialog box
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        # Set the window title to an empty string
        self.setWindowTitle('')

        # Call the setup user interface method
        self._setup_ui(message)


    def _setup_ui(self, message: str):
        """
        Sets up the user interface of the dialog box.

        :param message: The message to display.
        """
        # Create layout for icon and label
        icon_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(QPixmap(':/dialog-info.png'))
        message_label = QLabel(message)
        icon_layout.addWidget(icon_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        icon_layout.addWidget(message_label, alignment=Qt.AlignLeft | Qt.AlignVCenter, spacing=5)

        # Create main layout and add icon layout to it
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(icon_layout)

        # Show parent and dialog
        self.parent().show()
        self.show()



    def add_msg(self, str1, run, destroy):
        """
        Adds an extra label to the dialog box.

        :param str1: The string to display in the label.
        :param run: If True, runs the dialog box and returns the response.
        :param destroy: If True, destroys the dialog box.
        :return: The response from running the dialog box, if run is True.
        """
        # Create a new label widget with the given string
        label = QLabel(str1)

        # Add the label to the dialog box's vertical layout
        self.vbox.addWidget(label)

        # Show all widgets in the dialog box
        self.show()

        response = None
        if run:
            # Run the dialog box and get the response
            response = self.exec_()

        if destroy:
            # Destroy the dialog box
            self.destroy()

        # Return the response, if any
        return response





class SideButton(QPushButton):
    """Create a button with the label below the icon"""

    def __init__(self, label=None, stock=None, use_underline=True):
        super().__init__()

        # Add the stock icon and label to the button
        self.setIcon(self.style().standardIcon(stock))
        self.setText(label)

        # Remove the icon and label from the button's layout
        layout = self.layout()
        icon = layout.itemAt(0).widget()
        label = layout.itemAt(1).widget()
        layout.removeWidget(icon)
        layout.removeWidget(label)

        # Create a new layout with the icon above the label
        new_layout = QVBoxLayout()
        new_layout.addWidget(icon)
        new_layout.addWidget(label)

        # Add the new layout to the button
        widget = QWidget()
        widget.setLayout(new_layout)
        layout.addWidget(widget)

        self.show()





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





