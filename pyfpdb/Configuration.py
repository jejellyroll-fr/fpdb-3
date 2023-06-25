#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Configuration####
#Handles fpdb/fpdb-hud configuration files.
#    Copyright 2008-2012,  Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

########################################################################

#TODO fix / rethink edit stats - it is broken badly just now

#    Standard Library modules
from __future__ import with_statement
from __future__ import print_function


#import L10n
#_ = L10n.get_translation()

import codecs
import os
import sys
import inspect
import string
import shutil
import locale
import re
import xml.dom.minidom
from xml.dom.minidom import Node

import platform


if platform.system() == 'Windows':
    #import winpaths
    #winpaths_appdata = winpaths.get_appdata()
    import os
    winpaths_appdata = os.getenv('APPDATA')
    #winpaths_appdata = os.getcwd()
    winpaths_appdata = winpaths_appdata.replace("\\", "/")
    print ('winpaths_appdata:') #debug
    print (winpaths_appdata) #debug
else:
    winpaths_appdata = False

import logging, logging.config


# config version is used to flag a warning at runtime if the users config is
#  out of date.
# The CONFIG_VERSION should be incremented __ONLY__ if the add_missing_elements()
#  method cannot update existing standard configurations
CONFIG_VERSION = 83

#
# Setup constants
# code is centralised here to ensure uniform handling of path names
# especially important when user directory includes non-ascii chars
#
# INSTALL_METHOD ("source" or "exe")
# FPDB_ROOT_PATH (path to the root fpdb installation dir root (normally ...../fpdb)
# APPDATA_PATH (root path for appdata eg /~ or appdata)
# CONFIG_PATH (path to the directory holding logs, sqlite db's and config)
# GRAPHICS_PATH (path to graphics assets (normally .gfx)
# PYFPDB_PATH (path to py's)
# OS_FAMILY (OS Family for installed system (Linux, Mac, XP, Win7)
# POSIX (True=Linux or Mac platform, False=Windows platform)
# PYTHON_VERSION (n.n)

if hasattr(sys, "frozen"):
    if platform.system() == 'Windows':
        INSTALL_METHOD = "exe"
    elif platform.system() == 'Darwin':
        INSTALL_METHOD = "app"
else:
    INSTALL_METHOD = "source"

if INSTALL_METHOD == "exe" :
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)

    FPDB_ROOT_PATH = FPDB_ROOT_PATH.replace("\\", "/")
     # should be exe path to \fpdbroot\pyfpdb
elif INSTALL_METHOD == "app":
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)
elif sys.path[0] == "": # we are probably running directly (>>>import Configuration)
    temp = os.getcwd() # should be ./pyfpdb
    print(temp)
    FPDB_ROOT_PATH = os.path.join(temp, os.pardir)   # go up one level (to fpdbroot)
else: # all other cases
    FPDB_ROOT_PATH = os.path.dirname(sys.path[0])  # should be source path to /fpdbroot
    #FPDB_ROOT_PATH = os.getcwd()

sysPlatform = platform.system()  #Linux, Windows, Darwin
if sysPlatform[:5] == 'Linux':
    OS_FAMILY = 'Linux'
elif sysPlatform == 'Darwin':
    OS_FAMILY = 'Mac'
elif sysPlatform == 'Windows':
    OS_FAMILY = 'Win7' if platform.release() != 'XP' else 'XP'
else:
    OS_FAMILY = False

#GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
#PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")

if OS_FAMILY in ['XP', 'Win7']:
    APPDATA_PATH = winpaths_appdata
    CONFIG_PATH = os.path.join(APPDATA_PATH, "fpdb")
    CONFIG_PATH = CONFIG_PATH.replace("\\", "/")
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)
    FPDB_ROOT_PATH = FPDB_ROOT_PATH.replace("\\", "/")
    if INSTALL_METHOD == "source":
        script = os.path.realpath(__file__)
        print("SCript path:", script)
        script = script.replace("\\", "/")
        script = script.rsplit('/',2)[0]
        GRAPHICS_PATH = script+'/gfx'
    else:
        GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
        GRAPHICS_PATH = GRAPHICS_PATH.replace("\\", "/")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
    PYFPDB_PATH = PYFPDB_PATH.replace("\\", "/")
elif OS_FAMILY == 'Mac':
    APPDATA_PATH = os.getenv("HOME")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
elif OS_FAMILY == 'Linux':
    APPDATA_PATH = os.path.expanduser(u"~")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
else:
    APPDATA_PATH = False
    CONFIG_PATH = False

if os.name == 'posix':
    POSIX = True
else:
    POSIX = False

PYTHON_VERSION = sys.version[:3]

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("config")

LOGLEVEL = {'DEBUG'   : logging.DEBUG,
            'INFO'    : logging.INFO,
            'WARNING' : logging.WARNING,
            'ERROR'   : logging.ERROR,
            'CRITICAL': logging.CRITICAL}

def get_config(file_name, fallback=True):
    """
    Looks in cwd and in CONFIG_PATH for a config file.
    :param file_name: str - the name of the config file to search for
    :param fallback: bool - whether or not to fall back to an example file if a config file is not found
    :return: tuple - (config_path, example_copy, example_path)
    """

    def get_config_path(file_name):
        """
        Returns the path to the config file.
        :param file_name: str - the name of the config file
        :return: str - the path to the config file
        """        
        if sysPlatform == 'Windows':
            if platform.release() != 'XP':
                OS_FAMILY = 'Win7' #Vista and win7
        else:
            OS_FAMILY = 'XP'

        if OS_FAMILY == 'XP' or 'Win7':
            return os.path.join(CONFIG_PATH, file_name).replace("\\", "/")
        else:
            return os.path.join(CONFIG_PATH, file_name)

    def config_file_exists(config_path):
        """
        Checks if the config file exists.
        :param config_path: str - the path to the config file
        :return: bool - True if the config file exists, False otherwise
        """
        return os.path.exists(config_path)

    def copy_example_file(example_path, config_path):
        """
        Copies the example file to create a new config file.
        :param example_path: str - the path to the example file
        :param config_path: str - the path to the new config file
        :return: bool - True if the example file was successfully copied, False otherwise
        """
        try:
            shutil.copyfile(example_path, config_path)
            example_copy = True
            msg = f"Config file has been created at {config_path}."
            log.info(msg)
            return True
        except IOError:
            return False

    config_path = get_config_path(file_name)
    example_found = False
    example_copy = False
    example_path = None

    if config_file_exists(config_path):    # there is a file in the cwd
        fallback = False
    else: # no file in the cwd, look where it should be in the first place
        config_path = get_config_path(file_name)

        if config_file_exists(config_path):
            fallback = False
        elif POSIX:
            # If we're on linux, try to copy example from the place
            # debian package puts it; get_default_config_path() creates
            # the config directory for us so there's no need to check it
            # again
            example_path = f'/usr/share/python-fpdb/{file_name}.example'
            if os.path.exists(example_path):
                example_found = True
            elif os.path.exists(f'{file_name}.example'):
                example_path = f'{file_name}.example'
                example_found = True
            else:
                example_path = os.path.join(PYFPDB_PATH, f'{file_name}.example')

            if example_found and fallback:
                example_copy = copy_example_file(example_path, config_path)

        elif fallback:
            sys.stderr.write(f"No {file_name} found, cannot fall back. Exiting.\n")
            sys.exit()

    return (config_path, example_copy, example_path)



def set_logfile(file_name):
    """
    Sets the log file for the application.

    Args:
        file_name (str): The name of the log file.

    Returns:
        None
    """
    # Get the configuration files
    (conf_file, copied, example_file) = get_config("logging.conf", fallback=False)

    # Create log directory if it does not exist
    log_dir = os.path.join(CONFIG_PATH, 'log').replace('\\', '/')
    check_dir(log_dir)

    # Set the log file path
    log_file = os.path.join(log_dir, file_name).replace('\\', '/')

    # Check if the configuration file already exists
    if os.path.isfile(conf_file):
        print('logging.conf file already exists')
    else:
        # Create a configuration file
        print('copying logging.conf file in appdata rooming folder')

    # Set up the log file
    if conf_file:
        try:
            log_file = log_file.replace('\\', '/')
            logging.config.fileConfig(conf_file, {"logFile": log_file})
        except Exception:
            sys.stderr.write(f"Could not setup log file {file_name}")

def check_dir(path, create = True):
    """
    Check if a directory exists, optionally creates it if not.

    Args:
        path (str): path to directory
        create (bool, optional): whether to create the directory if it doesn't exist. Defaults to True.

    Returns:
        Union[str, bool]: Returns the path if it exists and is a directory. Returns False if it doesn't exist or isn't a directory and the `create` argument is False.
    """
    # Check if the directory already exists
    if os.path.exists(path):
        # If it does, return the path if it's a directory, or False if it's not
        return path if os.path.isdir(path) else False

    # If the directory doesn't exist and we're allowed to create it
    if create:
        # Replace any backslashes in the path with forward slashes
        path = path.replace('\\', '/')
        # Log that we're creating the directory
        msg = f"Creating directory: '{path}'"
        print(msg)
        log.info(msg)
        # Create the directory
        os.makedirs(path)#, "utf-8"))
    else:
        # If the directory doesn't exist and we're not allowed to create it, return False
        return False


def normalizePath(path):
    """
    Normalize an existing path.

    Args:
        path (str): The path to normalize.

    Returns:
        str: The normalized path.
    """
    return os.path.abspath(path) if os.path.exists(path) else path
            
########################################################################
# application wide consts

APPLICATION_NAME_SHORT = 'fpdb'
APPLICATION_VERSION = 'xx.xx.xx'

DATABASE_TYPE_POSTGRESQL = 'postgresql'
DATABASE_TYPE_SQLITE = 'sqlite'
DATABASE_TYPE_MYSQL = 'mysql'
DATABASE_TYPES = (
        DATABASE_TYPE_POSTGRESQL,
        DATABASE_TYPE_SQLITE,
        DATABASE_TYPE_MYSQL,
        )

LOCALE_ENCODING = locale.getpreferredencoding()
if LOCALE_ENCODING in ("US-ASCII", "", None):
    LOCALE_ENCODING = "cp1252"
    if (os.uname()[0]!="Darwin"):
        print((("Default encoding set to US-ASCII, defaulting to CP1252 instead."), ("Please report this problem.")))
    
# needs LOCALE_ENCODING (above), imported for sqlite setup in Config class below

import Charset


        
########################################################################
def string_to_bool(string: str, default: bool = True) -> bool:
    """
    Converts a string representation of a boolean value to a boolean True or False.

    Args:
        string (str): The string to convert.
        default (bool, optional): Value to return if the string cannot be converted to a boolean value. Defaults to True.

    Returns:
        bool: The converted boolean value.
    """
    # Convert the string to lowercase for case-insensitive comparison
    string = string.lower()
    if string in {'1', 'true', 't'}:
        # Return True if the string is '1', 'true', or 't'
        return True
    elif string in {'0', 'false', 'f'}:
        # Return False if the string is '0', 'false', or 'f'
        return False
    # Return the default value if the string cannot be converted to a boolean value
    return default

class Layout:
    """
    A class representing the layout of a poker table.

    Attributes:
    - max (int): the maximum number of seats at the table
    - width (int): the width of the table
    - height (int): the height of the table
    - location (list): a list representing the locations of each seat at the table
    - hh_seats (list): a list mapping seat numbers to contiguous integers for display purposes
    - common (tuple): a tuple representing the location of the common cards on the table
    """

    def __init__(self, node):
        """
        Initializes a Layout object from an XML node representing the table layout.

        Args:
        - node (xml.dom.minidom.Element): an XML node representing the table layout
        """
        # Extract attributes from the XML node and store them as instance variables
        attributes = node.attributes
        self.max = int(attributes['max'].value)
        self.width = int(attributes['width'].value)
        self.height = int(attributes['height'].value)

        # Initialize lists to store location and seat data for each seat at the table
        self.location = [None] * (self.max + 1)
        self.hh_seats = [None] * (self.max + 1)

        # Iterate over all location nodes in the XML and extract seat and location data
        for location_node in node.getElementsByTagName('location'):
            if hud_seat := location_node.getAttribute('seat'):
                hist_seat = location_node.getAttribute('hist_seat')
                seat = int(hud_seat)
                hist_seat = int(hist_seat) if hist_seat else seat
                self.hh_seats[seat] = hist_seat
                self.location[seat] = (int(location_node.getAttribute('x')),
                                        int(location_node.getAttribute('y')))
            elif location_node.getAttribute('common'):
                self.common = (int(location_node.getAttribute('x')), int(location_node.getAttribute('y')))

    def __str__(self):
        """Returns a string representation of the object."""

        # Check if the object has a 'name' attribute
        if hasattr(self, 'name'):
            name = str(self.name)

        # Create a string with the object's max, width, and height attributes
        # If the object has a 'fav_seat' attribute, add it to the string
        temp = "    Layout = %d max, width= %d, height = %d" % (self.max, self.width, self.height)
        if hasattr(self, 'fav_seat'):
            temp = temp + ", fav_seat = %d\n" % self.fav_seat
        else:
            temp = temp + "\n"

        # If the object has a 'common' attribute, add it to the string
        if hasattr(self, "common"):
            temp = temp + "        Common = (%d, %d)\n" % (self.common[0], self.common[1])

        # Add the 'Locations' attribute to the string
        temp = f"{temp}        Locations = "

        # Loop through the location attribute and add each seat to the string
        for i in range(1, len(self.location)):
            temp = temp + "%s:(%d,%d) " % (self.hh_seats[i],self.location[i][0],self.location[i][1])

        # Return the final string
        return temp + "\n"


class Email(object):
    """
    A class representing a connection to a remote mail server.
    """

    def __init__(self, node):
        """
        Constructor for Email class.

        Args:
            node (xml.dom.minidom.Element): The XML element representing the connection.
        """
        self.node = node
        self.host= node.getAttribute("host")  # Get the host attribute from the XML element.
        self.username = node.getAttribute("username")  # Get the username attribute from the XML element.
        self.password = node.getAttribute("password")  # Get the password attribute from the XML element.
        self.useSsl = node.getAttribute("useSsl")  # Get the useSsl attribute from the XML element.
        self.folder = node.getAttribute("folder")  # Get the folder attribute from the XML element.
        self.fetchType = node.getAttribute("fetchType")  # Get the fetchType attribute from the XML element.

        
    def __str__(self):
        """
        Returns a string representation of the EmailClient object.
        """
        return "    email\n        fetchType = %s  host = %s\n        username = %s password = %s\n        useSsl = %s folder = %s" \
            % (self.fetchType, self.host, self.username, self.password, self.useSsl, self.folder)

class Site(object):
    def __init__(self, node):
        """
        Initialize a new instance of the Site class with the given XML node.

        :param node: An XML node representing the site preferences.
        """
        # Extract site name, screen name, and paths from the XML node attributes and normalize the paths
        self.site_name = node.getAttribute("site_name")
        self.screen_name = node.getAttribute("screen_name")
        self.site_path = normalizePath(node.getAttribute("site_path"))
        self.HH_path = normalizePath(node.getAttribute("HH_path"))
        self.TS_path = normalizePath(node.getAttribute("TS_path"))

        # Extract boolean flags from the XML node attributes
        self.enabled = string_to_bool(node.getAttribute("enabled"), default=True)
        self.aux_enabled = string_to_bool(node.getAttribute("aux_enabled"), default=True)

        # Extract and normalize HUD menu position offsets from the XML node attributes
        self.hud_menu_xshift = node.getAttribute("hud_menu_xshift")
        self.hud_menu_xshift = 1 if self.hud_menu_xshift == "" else int(self.hud_menu_xshift)
        self.hud_menu_yshift = node.getAttribute("hud_menu_yshift")
        self.hud_menu_yshift = 1 if self.hud_menu_yshift == "" else int(self.hud_menu_yshift)

        # Set TS_path to an empty string if it's not present in the XML node attributes
        if node.hasAttribute("TS_path"):
            self.TS_path = normalizePath(node.getAttribute("TS_path"))
        else:
            self.TS_path = ''

        # Extract favorite seat mappings from the XML node and store them in a dictionary
        self.fav_seat = {}
        for fav_node in node.getElementsByTagName('fav'):
            max = int(fav_node.getAttribute("max"))
            fav = int(fav_node.getAttribute("fav_seat"))
            self.fav_seat[max] = fav

        # Extract layout set mappings from the XML node and store them in a dictionary
        self.layout_set = {}
        for site_layout_node in node.getElementsByTagName('layout_set'):
            gt = site_layout_node.getAttribute("game_type")
            ls = site_layout_node.getAttribute("ls")
            self.layout_set[gt] = ls

        # Extract email settings from the XML node and store them in a dictionary
        self.emails = {}
        for email_node in node.getElementsByTagName('email'):
            email = Email(email_node)
            self.emails[email.fetchType] = email


    def __str__(self):
        """
        Return a string representation of the object.

        Returns:
            str: A string representation of the object.
        """
        # Initialize the temp variable with the site name
        temp = f"Site = {self.site_name}" + "\n"

        # Iterate over all the attributes of the object
        for key in dir(self):
            # Ignore special methods
            if key.startswith('__'): continue
            # Ignore certain attributes
            if key == 'layout_set':  continue
            if key == 'fav_seat':  continue
            if key == 'emails':  continue
            value = getattr(self, key)
            # Ignore callable attributes
            if callable(value): continue
            # Append the attribute to the temp variable
            temp = f'{temp}    {key} = {str(value)}' + "\n"

        # Append the email addresses to the temp variable
        for fetchtype in self.emails:
            temp = temp + str(self.emails[fetchtype]) + "\n"

        # Append the game types and layout sets to the temp variable
        for game_type in self.layout_set:
            temp = temp + "    game_type = %s, layout_set = %s\n" % (game_type, self.layout_set[game_type])

        # Append the favorite seats to the temp variable
        for max in self.fav_seat:
            temp = temp + "    max = %s, fav_seat = %s\n" % (max, self.fav_seat[max])

        # Return the final string representation of the object
        return temp



class Stat(object):  
    """A class representing a stat."""

    def __init__(self, node):
        """Initializes an instance of the Stat class with the given node object.

        Args:
            node (xml.dom.minidom.Element): The node object to initialize the Stat instance with.
        """
        rowcol         = node.getAttribute("_rowcol")                      # human string "(r,c)" values >0)
        self.rows  = node.getAttribute("rows")
        self.cols  = node.getAttribute("cols")
        self.rowcol    = tuple(int(s)-1 for s in rowcol[1:-1].split(',')) # tuple (r-1,c-1)
        self.stat_name = node.getAttribute("_stat_name")
        self.tip     = node.getAttribute("tip")
        self.click    = node.getAttribute("click")
        self.popup    = node.getAttribute("popup")
        self.hudprefix = node.getAttribute("hudprefix")
        self.hudsuffix = node.getAttribute("hudsuffix")
        self.hudcolor  = node.getAttribute("hudcolor")
        self.stat_loth = node.getAttribute("stat_loth")
        self.stat_hith = node.getAttribute("stat_hith")
        self.stat_locolor = node.getAttribute("stat_locolor")
        self.stat_hicolor = node.getAttribute("stat_hicolor")

    def __str__(self):
        """
        Returns a string representation of the object.

        Returns:
            str: A string representation of the object.
        """
        # Initialize the temporary string with row and column and status name
        temp = "        _rowcol = %s, _stat_name = %s, \n" % (self.rowcol, self.stat_name)
        # Iterate through all attributes of the object
        for key in dir(self):
            # Skip attributes that start with "__", "_stat_name", and "_rowcol"
            if key.startswith('__'):
                continue
            if key == '_stat_name':
                continue
            if key == '_rowcol':
                continue
            # Get the value of the current attribute
            value = getattr(self, key)
            # Skip callable attributes
            if callable(value):
                continue
            # Add the current attribute and its value to the temporary string
            temp = f'{temp}            {key} = {str(value)}' + "\n"

        return temp


class Stat_sets(object):
    """
    A class that represents a set of statistics.
    """

    def __init__(self, node):
        """
        Initializes the Stat_sets object.

        Args:
        - node: The XML node to initialize from.
        """
        # Set the name attribute.
        self.name = node.getAttribute("name")

        # Set the rows attribute.
        self.rows = int(node.getAttribute("rows"))

        # Set the cols attribute.
        self.cols = int(node.getAttribute("cols"))

        # Set the xpad attribute.
        self.xpad = node.getAttribute("xpad")
        self.xpad = 0 if self.xpad == "" else int(self.xpad)

        # Set the ypad attribute.
        self.ypad = node.getAttribute("ypad")
        self.ypad = 0 if self.ypad == "" else int(self.ypad)

        # Initialize the stats dictionary.
        self.stats = {}

        # Loop through all the stat nodes.
        for stat_node in node.getElementsByTagName('stat'):
            stat = Stat(stat_node)
            self.stats[stat.rowcol] = stat # this is the key!


    def __str__(self):
        """
        Returns a string representation of the class instance.

        Returns:
        - temp (str): A string containing information about the class instance.
        """
        temp = f"Name = {self.name}" + "\n"
        temp = f"{temp}rows = {self.rows}" + " cols = {self.cols}"
        temp = f"{temp}    xpad = {self.xpad}" + f" ypad = {self.ypad}\n"

        # Loop through the keys in the dictionary of statistics.
        for stat in list(self.stats.keys()):
            temp = f"{temp}{self.stats[stat]}"

        return temp


class Database(object):
    def __init__(self, node):
        """
        Initializes a new instance of the DatabaseConnection class.
        :param node: The XML node containing the database connection information.
        """
        # Get the database connection information from the XML node.
        self.db_name   = node.getAttribute("db_name")   # Name of the database.
        self.db_desc   = node.getAttribute("db_desc")   # Description of the database.
        self.db_server = node.getAttribute("db_server").lower() # Server name where the database is hosted.
        self.db_ip     = node.getAttribute("db_ip")     # IP address of the server.
        if "db_port" in node.attributes:
            self.db_port = node.getAttribute("db_port")
        else:
            self.db_port = 5432  # Default PostgreSQL port number
        self.db_user   = node.getAttribute("db_user")   # Username for the database connection.
        self.db_pass   = node.getAttribute("db_pass")   # Password for the database connection.
        self.db_path   = node.getAttribute("db_path")   # Path to the database file.
        self.db_selected = string_to_bool(node.getAttribute("default"), default=False) # Whether this database is the default.

        # Log the connection information.
        log.debug("Database db_name:'%(name)s'  db_server:'%(server)s'  db_ip:'%(ip)s'  db_user:'%(user)s'  db_pass (not logged)  selected:'%(sel)s'" \
                % { 'name':self.db_name, 'server':self.db_server, 'ip':self.db_ip, 'user':self.db_user, 'sel':self.db_selected} )

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Initialize the string with the database name.
        temp = f'Database = {self.db_name}' + '\n'

        # Iterate over all attributes of the object.
        for key in dir(self):
            # Skip any attributes that start with '__'.
            if key.startswith('__'): continue

            # Get the value of the attribute.
            value = getattr(self, key)

            # Skip any attributes that are callable.
            if callable(value): continue

            # Add the attribute name and value to the string.
            temp = f'{temp}    {key} = {repr(value)}' + "\n"

        # Return the final string.
        return temp



class Aux_window(object):
    def __init__(self, node):
        """
        Initializes the object with attributes from the given XML node.
        """
        # Set each attribute of the object to the corresponding XML attribute value.
        for (name, value) in list(node.attributes.items()):
            setattr(self, name, value)

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Initialize the string with the name of the object.
        temp = f'Aux = {self.name}' + "\n"

        # Iterate over all attributes of the object.
        for key in dir(self):
            # Skip any attributes that start with '__'.
            if key.startswith('__'): continue

            # Get the value of the attribute.
            value = getattr(self, key)

            # Skip any attributes that are callable.
            if callable(value): continue

            # Add the attribute name and value to the string.
            temp = f'{temp}    {key} = {value}' + "\n"

        # Return the final string.
        return temp



class Supported_games(object):
    def __init__(self, node):
        """
        Initializes the object with attributes from the given XML node and creates a dictionary of Game_stat_set objects.
        """
        # Set each attribute of the object to the corresponding XML attribute value.
        for (name, value) in list(node.attributes.items()):
            setattr(self, name, value)

        # Initialize an empty dictionary to hold the Game_stat_set objects.
        self.game_stat_set = {}

        # Iterate over all game_stat_set nodes and create a Game_stat_set object for each one.
        for game_stat_set_node in node.getElementsByTagName('game_stat_set'):
            gss = Game_stat_set(game_stat_set_node)
            self.game_stat_set[gss.game_type] = gss

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Initialize the string with the name of the object.
        temp = f'Supported_games = {self.game_name}' + "\n"

        # Iterate over all attributes of the object.
        for key in dir(self):
            # Skip any attributes that start with '__', 'game_stat_set', or 'game_name'.
            if key.startswith('__'): continue
            if key == 'game_stat_set':  continue
            if key == 'game_name': continue

            # Get the value of the attribute.
            value = getattr(self, key)

            # Skip any attributes that are callable.
            if callable(value): continue

            # Add the attribute name and value to the string.
            temp = f'{temp}    {key} = {value}' + "\n"

        # Add the string representations of all Game_stat_set objects to the string.
        for gs in self.game_stat_set:
            temp = f"{temp}{str(self.game_stat_set[gs])}"

        # Return the final string.
        return temp



class Layout_set(object):
    def __init__(self, node):
        """
        Initializes the object with attributes from the given XML node and creates a dictionary of Layout objects.
        """
        # Set each attribute of the object to the corresponding XML attribute value.
        for (name, value) in list(node.attributes.items()):
            setattr(self, name, value)

        # Initialize an empty dictionary to hold the Layout objects.
        self.layout = {}

        # Iterate over all layout nodes and create a Layout object for each one.
        for layout_node in node.getElementsByTagName('layout'):
            lo = Layout(layout_node)
            self.layout[lo.max] = lo

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Initialize the string with the name of the object.
        temp = f'Layout set = {self.name}' + "\n"

        # Iterate over all attributes of the object.
        for key in dir(self):
            # Skip any attributes that start with '__', 'layout', or 'name'.
            if key.startswith('__'): continue
            if key == 'layout':  continue
            if key == 'name':  continue

            # Get the value of the attribute.
            value = getattr(self, key)

            # Skip any attributes that are callable.
            if callable(value): continue

            # Add the attribute name and value to the string.
            temp = f'{temp}    {key} = {value}' + "\n"

        # Add the string representations of all Layout objects to the string.
        for layout in self.layout:
            temp = f"{temp}{self.layout[layout]}"

        # Return the final string.
        return temp



class Game_stat_set(object):
    def __init__(self, node):
        """
        Initializes the object with attributes from the given XML node.
        """
        # Set the game_type and stat_set attributes of the object to the corresponding XML attribute values.
        self.game_type       = node.getAttribute("game_type")
        self.stat_set        = node.getAttribute("stat_set")

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Return a string showing the game_type and stat_set attributes.
        return "      Game Type: '%s' Stat Set: '%s'\n" % (self.game_type, self.stat_set)

        
class HHC(object):
    def __init__(self, node):
        """
        Initializes the object with attributes from the given XML node.
        """
        # Set the site, converter, and summaryImporter attributes of the object to the corresponding XML attribute values.
        self.site            = node.getAttribute("site")
        self.converter       = node.getAttribute("converter")
        self.summaryImporter = node.getAttribute("summaryImporter")

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        # Return a string showing the site, converter, and summaryImporter attributes.
        return "%s:\tconverter: '%s' summaryImporter: '%s'" % (self.site, self.converter, self.summaryImporter)


class Popup(object):
    def __init__(self, node):
        """
        Initializes a Popup object with the given XML node.

        Args:
        - node: xml.dom.minidom.Node - the XML node representing the Popup

        Attributes:
        - name: str - the name of the Popup
        - pu_class: str - the class of the Popup
        - pu_stats: list[str] - the names of the Popup's stats
        - pu_stats_submenu: list[(str, str)] - the names and submenus of the Popup's stats
        """
        self.name  = node.getAttribute("pu_name")
        self.pu_class = node.getAttribute("pu_class")
        self.pu_stats    = []
        self.pu_stats_submenu = []

        # Parse the Popup's stats and submenus
        for stat_node in node.getElementsByTagName('pu_stat'):
            self.pu_stats.append(stat_node.getAttribute("pu_stat_name"))
            if stat_node.hasAttribute("pu_stat_submenu"):
                self.pu_stats_submenu.append(
                    (
                        stat_node.getAttribute("pu_stat_name"),
                        stat_node.getAttribute("pu_stat_submenu"),
                    )
                )

            

    def __str__(self):
        """
        Returns a string representation of the Popup object.

        The string includes the Popup's name, class, and stats.

        Returns:
            str: A string representation of the Popup object.
        """
        temp = f"Popup = {self.name}  Class = {self.pu_class}" + "\n"
        for stat in self.pu_stats:
            temp = f"{temp} {stat}"
        return temp + "\n"


class Import(object):
    def __init__(self, node):
        """
        Initializes an Import object.

        Args:
            node (xml.dom.minidom.Element): The XML node containing the import settings.

        Attributes:
            node (xml.dom.minidom.Element): The XML node containing the import settings.
            interval (str): The interval at which hands are imported.
            sessionTimeout (bool): Whether the session timeout is enabled.
            ResultsDirectory (str): The directory where hand history files are stored.
            hhBulkPath (str): The path to the HHBulk executable.
            saveActions (bool): Whether actions are saved.
            cacheSessions (bool): Whether sessions are cached.
            publicDB (bool): Whether the public database is used.
            callFpdbHud (bool): Whether the FPDB HUD is called.
            fastStoreHudCache (bool): Whether the HUD cache is stored quickly.
            saveStarsHH (bool): Whether Stars hand histories are saved.
            importFilters (list of str): The filters used when importing hands.
            timezone (str): The timezone used when importing hands.
        """
        self.node = node
        self.interval = node.getAttribute("interval")
        self.sessionTimeout = string_to_bool(node.getAttribute("sessionTimeout"), default=30)
        self.ResultsDirectory = node.getAttribute("ResultsDirectory")
        self.hhBulkPath = node.getAttribute("hhBulkPath")
        self.saveActions = string_to_bool(node.getAttribute("saveActions"), default=False)
        self.cacheSessions = string_to_bool(node.getAttribute("cacheSessions"), default=False)
        self.publicDB = string_to_bool(node.getAttribute("publicDB"), default=False)
        self.callFpdbHud = string_to_bool(node.getAttribute("callFpdbHud"), default=False)
        self.fastStoreHudCache = string_to_bool(node.getAttribute("fastStoreHudCache"), default=False)
        self.saveStarsHH = string_to_bool(node.getAttribute("saveStarsHH"), default=False)
        if node.getAttribute("importFilters"):
            self.importFilters = node.getAttribute("importFilters").split(",")
        else:
            self.importFilters = []
        if node.getAttribute("timezone"):
            self.timezone = node.getAttribute("timezone")
        else:
            self.timezone = "America/New_York"

    def __str__(self):
        """
        Returns a string representation of the object.
        """
        return (
            "    interval = %s\n"
            "    callFpdbHud = %s\n"
            "    saveActions = %s\n"
            "    cacheSessions = %s\n"
            "    publicDB = %s\n"
            "    sessionTimeout = %s\n"
            "    fastStoreHudCache = %s\n"
            "    ResultsDirectory = %s"
            % (
                self.interval,
                self.callFpdbHud,
                self.saveActions,
                self.cacheSessions,
                self.publicDB,
                self.sessionTimeout,
                self.fastStoreHudCache,
                self.ResultsDirectory,
            )
        )

class HudUI(object):
    def __init__(self, node):
        """
        Initializes the HudUI object with information from the given node.

        Args:
        node (xml.etree.ElementTree.Element): The XML node containing the HudUI information.
        """
        self.node = node
        self.label = node.getAttribute('label')

        # Optional attributes
        if node.hasAttribute('card_ht'):
            self.card_ht = node.getAttribute('card_ht')
        if node.hasAttribute('card_wd'):
            self.card_wd = node.getAttribute('card_wd')
        if node.hasAttribute('deck_type'):
            self.deck_type = node.getAttribute('deck_type')
        if node.hasAttribute('card_back'):
            self.card_back = node.getAttribute('card_back')

        # Additional optional attributes
        if node.hasAttribute('stat_range'):
            self.stat_range = node.getAttribute('stat_range')
        if node.hasAttribute('stat_days'):
            self.hud_days = node.getAttribute('stat_days')
        if node.hasAttribute('aggregation_level_multiplier'):
            self.agg_bb_mult = node.getAttribute('aggregation_level_multiplier')
        if node.hasAttribute('seats_style'):
            self.seats_style = node.getAttribute('seats_style')
        if node.hasAttribute('seats_cust_nums_low'):
            self.seats_cust_nums_low = node.getAttribute('seats_cust_nums_low')
        if node.hasAttribute('seats_cust_nums_high'):
            self.seats_cust_nums_high = node.getAttribute('seats_cust_nums_high')

        # Additional optional attributes for hero stats
        if node.hasAttribute('hero_stat_range'):
            self.h_stat_range = node.getAttribute('hero_stat_range')
        if node.hasAttribute('hero_stat_days'):
            self.h_hud_days = node.getAttribute('hero_stat_days')
        if node.hasAttribute('hero_aggregation_level_multiplier'):
            self.h_agg_bb_mult = node.getAttribute('hero_aggregation_level_multiplier')
        if node.hasAttribute('hero_seats_style'):
            self.h_seats_style = node.getAttribute('hero_seats_style')
        if node.hasAttribute('hero_seats_cust_nums_low'):
            self.h_seats_cust_nums_low = node.getAttribute('hero_seats_cust_nums_low')
        if node.hasAttribute('hero_seats_cust_nums_high'):
            self.h_seats_cust_nums_high = node.getAttribute('hero_seats_cust_nums_high')



    def __str__(self):
        """
        Return a string representation of the object.
        """
        return "    label = %s\n" % self.label



class General(dict):
    def __str__(self):
        """
        Return a string representation of the object.
        """
        return "    label = %s\n" % self.label


    def add_elements(self, node):
        """Add elements to the configuration dictionary.

        Args:
            node: an XML node containing the configuration information.

        Returns:
            None
        """
        # day_start - number n where 0.0 <= n < 24.0 representing start of day for user.
        #             e.g. user could set to 4.0 for day to start at 4am local time.
        #
        # HH_bulk_path - path to the HH bulk file.


        for (name, value) in list(node.attributes.items()):
            log.debug(f"config.general: adding {name} = {value}")
            self[name] = value

        try:
            self["version"] = int(self["version"])
        except KeyError:
            self["version"] = 0
            self["ui_language"] = "system"
            self["config_difficulty"] = "expert"

            
    def get_defaults(self):
        """
        Returns a dictionary object with default configuration settings.

        Returns:
            dict: Dictionary object with default configuration settings.
        """
        self["version"] = 0  # The version of the configuration file.
        self["ui_language"] = "system"  # The language the user interface should use.
        self["config_difficulty"] = "expert"  # The difficulty level of the configuration settings.
        self["config_wrap_len"] = "-1"  # The maximum length of lines in the configuration file.


    def __str__(self):
        """
        Returns a string representation of the dictionary for printing.

        :return: string representation of the dictionary
        :rtype: str
        """
        s = ""
        for k in self:
            s = s + "    %s = %s\n" % (k, self[k])
        return s


class GUICashStats(list):
    """
    A class for representing cash statistics of a game.
    Inherits from the built-in list class.

    Attributes:
    -----------
    None

    Methods:
    --------
    __init__():
        Constructs a GUICashStats object which is an empty list.

    """
    """<gui_cash_stats>
           <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
           ...
       </gui_cash_stats>
    """
    def __init__(self):
        super(GUICashStats, self).__init__()




    def add_elements(self, node):
        """
        Adds child nodes to the current node.

        Args:
            node: The node to add child nodes to.
        """
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                # Set default values
                col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment = None, None, True, True, "%s", "str", 0.0

                # Override default values with values from child attributes if present
                if child.hasAttribute('col_name'):
                    col_name = child.getAttribute('col_name')
                if child.hasAttribute('col_title'):
                    col_title = child.getAttribute('col_title')
                if child.hasAttribute('disp_all'):
                    disp_all = string_to_bool(child.getAttribute('disp_all'))
                if child.hasAttribute('disp_posn'):
                    disp_posn = string_to_bool(child.getAttribute('disp_posn'))
                if child.hasAttribute('field_format'):
                    field_format = child.getAttribute('field_format')
                if child.hasAttribute('field_type'):
                    field_type = child.getAttribute('field_type')
                try:
                    if child.hasAttribute('xalignment'):
                        xalignment = float(child.getAttribute('xalignment'))
                except ValueError:
                    print(("bad number in xalignment was ignored"))
                    log.info(("bad number in xalignment was ignored"))

                # Append values to list
                self.append([col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment])


    def get_defaults(self):
        """
        A list of defaults to be called, should there be no entry in config.

        Returns:
        defaults: list
            A list of columns with their properties that are used as defaults.
        """
        # SQL column name, display title, display all, display positional, format, type, alignment
        defaults = [   ['game', 'Game', True, True, '%s', 'str', 0.0],       
            ['hand', 'Hand', False, False, '%s', 'str', 0.0],
            ['plposition', 'Posn', False, False, '%s', 'str', 1.0],
            ['pname', 'Name', False, False, '%s', 'str', 0.0],
            ['n', 'Hds', True, True, '%1.0f', 'str', 1.0],
            ['avgseats', 'Seats', False, False, '%3.1f', 'str', 1.0],
            ['vpip', 'VPIP', True, True, '%3.1f', 'str', 1.0],
            ['pfr', 'PFR', True, True, '%3.1f', 'str', 1.0],
            ['pf3', 'PF3', True, True, '%3.1f', 'str', 1.0],
            ['aggfac', 'AggFac', True, True, '%2.2f', 'str', 1.0],
            ['aggfrq', 'AggFreq', True, True, '%3.1f', 'str', 1.0],
            ['conbet', 'ContBet', True, True, '%3.1f', 'str', 1.0],
            ['rfi', 'RFI', True, True, '%3.1f', 'str', 1.0],
            ['steals', 'Steals', True, True, '%3.1f', 'str', 1.0],
            ['saw_f', 'Saw_F', True, True, '%3.1f', 'str', 1.0],
            ['sawsd', 'SawSD', True, True, '%3.1f', 'str', 1.0],
            ['wtsdwsf', 'WtSDwsF', True, True, '%3.1f', 'str', 1.0],
            ['wmsd', 'W$SD', True, True, '%3.1f', 'str', 1.0],
            ['flafq', 'FlAFq', True, True, '%3.1f', 'str', 1.0],
            ['tuafq', 'TuAFq', True, True, '%3.1f', 'str', 1.0],
            ['rvafq', 'RvAFq', True, True, '%3.1f', 'str', 1.0],
            ['pofafq', 'PoFAFq', False, False, '%3.1f', 'str', 1.0],
            ['net', 'Net($)', True, True, '%6.2f', 'cash', 1.0],
            ['bbper100', 'bb/100', True, True, '%4.2f', 'str', 1.0],
            ['rake', 'Rake($)', True, True, '%6.2f', 'cash', 1.0],
            ['bb100xr', 'bbxr/100', True, True, '%4.2f', 'str', 1.0],
            ['stddev', 'Standard Deviation', True, True, '%5.2f', 'str', 1.0]
            ]
        for col in defaults:
            self.append (col)

#    def __str__(self):
#        s = ""
#        for l in self:
#            s = s + "    %s = %s\n" % (k, self[k])
#        return(s)
class GUITourStats(list):
    """
    A class representing a list of GUI tour statistics.

    Attributes:
    Inherits all list attributes.

    Examples:
    gui_tour_stats = GUITourStats()
    """
    """<gui_tour_stats>
           <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
           ...
       </gui_tour_stats>
    """

    def __init__(self):
        super(GUITourStats, self).__init__()


    def add_elements(self, node):
        """
        Adds elements to the node.

        Args:
            node: The node to add elements to.

        Returns:
            None
        """
        # Loop through each child node of the given node
        for child in node.childNodes:
            # Check if the child node is an element node
            if child.nodeType == child.ELEMENT_NODE:
                # Define default values for each column
                col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment=None, None, True, True, "%s", "str", 0.0

                # Check if the child node has a 'col_name' attribute and assign its value to col_name
                if child.hasAttribute('col_name'):     col_name     = child.getAttribute('col_name')     # Column Name
                # Check if the child node has a 'col_title' attribute and assign its value to col_title
                if child.hasAttribute('col_title'):    col_title    = child.getAttribute('col_title')    # Column Title
                # Check if the child node has a 'disp_all' attribute, convert its value to a boolean and assign it to disp_all
                if child.hasAttribute('disp_all'):     disp_all     = string_to_bool(child.getAttribute('disp_all'))     # Display All
                # Check if the child node has a 'disp_posn' attribute, convert its value to a boolean and assign it to disp_posn
                if child.hasAttribute('disp_posn'):    disp_posn    = string_to_bool(child.getAttribute('disp_posn'))    # Display Position
                # Check if the child node has a 'field_format' attribute and assign its value to field_format
                if child.hasAttribute('field_format'): field_format = child.getAttribute('field_format') # Field Format
                # Check if the child node has a 'field_type' attribute and assign its value to field_type
                if child.hasAttribute('field_type'):   field_type   = child.getAttribute('field_type')   # Field Type
                try:
                    # Check if the child node has a 'xalignment' attribute, convert its value to a float and assign it to xalignment
                    if child.hasAttribute('xalignment'):   xalignment   = float(child.getAttribute('xalignment'))   # X Alignment
                except ValueError:
                    # If the value of 'xalignment' attribute cannot be converted to a float, log a warning message
                    print(("bad number in xalignment was ignored"))
                    log.info(("bad number in xalignment was ignored"))

                # Append a list of column values to the current object
                self.append( [col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment] )




    def get_defaults(self):
        """
        Returns a list of default settings if there are no entries in the config.

        Returns:
            list: A list of default settings, where each setting is also a list with the following elements:
                SQL column name, display title, display all, display positional, format, type, alignment
        """
        # Define the default settings as a list of lists
        defaults = [
            ['game', 'Game', True, True, '%s', 'str', 0.0],
            ['hand', 'Hand', False, False, '%s', 'str', 0.0],
        ]
        # Iterate over each default setting and append it to the instance of the class
        for col in defaults:
            self.append(col)




class RawHands(object):
    def __init__(self, node=None):
        """
        Initializes an instance of the RawHands class with the given XML node.

        Args:
            node (xml.dom.minidom.Element): An XML node containing the configuration settings for RawHands. Defaults to None.
        """
        if node is None:
            self.save = "error"
            self.compression = "none"
            #print ("missing config section raw_hands")
        else:
            # Get the "save" attribute from the XML node, and set self.save to that value
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                # If the "save" attribute is not valid, print a warning and set self.save to "error"
                print (("Invalid config value for %s, defaulting to %s") % (raw_hands.save, "\"error\""))
                self.save = "error"

            # Get the "compression" attribute from the XML node, and set self.compression to that value
            compression = node.getAttribute("compression")
            if compression in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                # If the "compression" attribute is not valid, print a warning and set self.compression to "none"
                print (("Invalid config value for %s, defaulting to %s") % (raw_hands.compression, "\"none\""))
                self.compression = "none"

    def __str__(self):
        """
        Returns a string representation of the RawHands instance.

        Returns:
            str: A string representation of the RawHands instance, in the format "save= <self.save>, compression= <self.compression>\n"
        """
        return "        save= %s, compression= %s\n" % (self.save, self.compression)


class RawTourneys(object):
    def __init__(self, node=None):
        """
        Initializes an instance of the RawTourneys class with the given XML node.

        Args:
            node (xml.dom.minidom.Element): An XML node containing the configuration settings for RawTourneys. Defaults to None.
        """
        if node is None:
            self.save = "error"
            self.compression = "none"
            #print ("missing config section raw_tourneys")
        else:
            # Get the "save" attribute from the XML node, and set self.save to that value
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                # If the "save" attribute is not valid, print a warning and set self.save to "error"
                print (("Invalid config value for %s, defaulting to %s") % (raw_tourneys.save, "\"error\""))
                self.save = "error"

            # Get the "compression" attribute from the XML node, and set self.compression to that value
            compression = node.getAttribute("compression")
            if compression in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                # If the "compression" attribute is not valid, print a warning and set self.compression to "none"
                print (("Invalid config value for %s, defaulting to %s") % (raw_tourneys.compression, "\"none\""))
                self.compression = "none"

    def __str__(self):
        """
        Returns a string representation of the RawTourneys instance.

        Returns:
            str: A string representation of the RawTourneys instance, in the format "save= <self.save>, compression= <self.compression>\n"
        """
        return "        save= %s, compression= %s\n" % (self.save, self.compression)


class Config(object):
    def __init__(self, file=None, dbname='', custom_log_dir='', lvl='INFO'):
        """
        Initializes an instance of the Config class with the given parameters.

        Args:
            file (str): A path to an XML file containing the fpdb/HUD configuration. Defaults to None.
            dbname (str): The name of the database to use. Defaults to an empty string.
            custom_log_dir (str): A custom directory for log files. Defaults to an empty string.
            lvl (str): The level of logging to use. Defaults to 'INFO'.
        """
        # Set various paths and properties of the Config instance
        self.install_method = INSTALL_METHOD
        self.fpdb_root_path = FPDB_ROOT_PATH
        self.appdata_path = APPDATA_PATH
        self.config_path = CONFIG_PATH
        self.pyfpdb_path = PYFPDB_PATH
        self.graphics_path = GRAPHICS_PATH
        self.os_family = OS_FAMILY
        self.posix = POSIX
        self.python_version = PYTHON_VERSION

        # Ensure that the CONFIG_PATH directory exists
        if not os.path.exists(CONFIG_PATH):
            os.makedirs(CONFIG_PATH)

        # Set the directory for log files based on the OS family and whether a custom directory was provided
        if custom_log_dir and os.path.exists(custom_log_dir):
            self.dir_log = str(custom_log_dir, "utf8")
        else:
            if OS_FAMILY == 'XP' or 'Win7':
                print('windows TRUE5')
                self.dir_log = os.path.join(CONFIG_PATH, 'log')
                self.dir_log = self.dir_log.replace("\\", "/")
            else:
                self.dir_log = os.path.join(CONFIG_PATH, 'log')
        self.log_file = os.path.join(self.dir_log, 'fpdb-log.txt')
        log = logging.getLogger("config")

#    "file" is a path to an xml file with the fpdb/HUD configuration
#    we check the existence of "file" and try to recover if it doesn't exist

#        self.default_config_path = self.get_default_config_path()
        self.example_copy = False
        if file is not None: # config file path passed in
            file = os.path.expanduser(file)
            if not os.path.exists(file):
                print(("Configuration file %s not found. Using defaults.") % (file))
                sys.stderr.write(("Configuration file %s not found. Using defaults.") % (file))
                file = None

        self.example_copy,example_file = True,None
        if file is None: (file,self.example_copy,example_file) = get_config("HUD_config.xml", True)

        self.file = file
        # Set up various dictionaries and properties of the Config instance            
        self.supported_sites = {}
        self.supported_games = {}
        self.supported_databases = {}        # databaseName --> Database instance
        self.aux_windows = {}
        self.layout_sets = {}
        self.stat_sets = {}
        self.hhcs = {}
        self.popup_windows = {}
        self.db_selected = None              # database the user would like to use
        self.general = General()
        self.emails = {}
        self.gui_cash_stats = GUICashStats()
        self.gui_tour_stats = GUITourStats()
        self.site_ids = {}                   # site ID list from the database


        added,n = 1,0  # use n to prevent infinite loop if add_missing_elements() fails somehow
        while added > 0 and n < 2:
            # Attempt to parse the configuration file
            n = n + 1
            log.info("Reading configuration file %s" % file)
            print (("\n"+("Reading configuration file %s")+"\n") % file)
            try:
                doc = xml.dom.minidom.parse(file)
                self.doc = doc
                self.file_error = None
            except:
                import traceback
                log.error((("Error parsing %s.") % (file)) + ("See error log file."))
                traceback.print_exc(file=sys.stderr)
                self.file_error = sys.exc_info()[1]
                # we could add a parameter to decide whether to return or read a line and exit?
                return
                #print "press enter to continue"
                #sys.stdin.readline()
                #sys.exit()

            if (not self.example_copy) and (example_file is not None):
                # reads example file and adds missing elements into current config
                added = self.add_missing_elements(doc, example_file)

        # Add or overwrite elements in the General and GUICashStats instances
        if doc.getElementsByTagName("general") == []:
            self.general.get_defaults()
        for gen_node in doc.getElementsByTagName("general"):
            self.general.add_elements(node=gen_node) # add/overwrite elements in self.general
            
        if int(self.general["version"]) == CONFIG_VERSION:
            self.wrongConfigVersion = False
        else:
            self.wrongConfigVersion = True
            
        if doc.getElementsByTagName("gui_cash_stats") == []:
            self.gui_cash_stats.get_defaults()
        for gcs_node in doc.getElementsByTagName("gui_cash_stats"):
            self.gui_cash_stats.add_elements(node=gcs_node) # add/overwrite elements in self.gui_cash_stats
            

        if doc.getElementsByTagName("gui_tour_stats") == []:
            self.gui_tour_stats.get_defaults()
        for gcs_node in doc.getElementsByTagName("gui_tour_stats"):
            self.gui_tour_stats.add_elements(node=gcs_node) # add/overwrite elements in self.gui_cash_stats
            

#        s_sites = doc.getElementsByTagName("supported_sites")
        for site_node in doc.getElementsByTagName("site"):
            site = Site(node = site_node)
            self.supported_sites[site.site_name] = site

#        s_games = doc.getElementsByTagName("supported_games")
        for supported_game_node in doc.getElementsByTagName("game"):
            supported_game = Supported_games(supported_game_node)
            self.supported_games[supported_game.game_name] = supported_game

        # parse databases defined by user in the <supported_databases> section
        # the user may select the actual database to use via commandline or by setting the selected="bool"
        # attribute of the tag. if no database is explicitely selected, we use the first one we come across
#        s_dbs = doc.getElementsByTagName("supported_databases")
        #TODO: do we want to take all <database> tags or all <database> tags contained in <supported_databases>
        #         ..this may break stuff for some users. so leave it unchanged for now untill there is a decission
        for db_node in doc.getElementsByTagName("database"):
            db = Database(node=db_node)
            if db.db_name in self.supported_databases:
                raise ValueError("Database names must be unique")
            if self.db_selected is None or db.db_selected:
                self.db_selected = db.db_name
                db_node.setAttribute("default", "True")
            self.supported_databases[db.db_name] = db
        #TODO: if the user may passes '' (empty string) as database name via command line, his choice is ignored
        #           ..when we parse the xml we allow for ''. there has to be a decission if to allow '' or not
        if dbname and dbname in self.supported_databases:
            self.db_selected = dbname
        #NOTE: fpdb can not handle the case when no database is defined in xml, so we throw an exception for now
        if self.db_selected is None:
            raise ValueError('There must be at least one database defined')

#     s_dbs = doc.getElementsByTagName("mucked_windows")
        for aw_node in doc.getElementsByTagName("aw"):
            aw = Aux_window(node = aw_node)
            self.aux_windows[aw.name] = aw

        for ls_node in doc.getElementsByTagName("ls"):
            ls = Layout_set(node = ls_node)
            self.layout_sets[ls.name] = ls
            
        for ss_node in doc.getElementsByTagName("ss"):
            ss = Stat_sets(node = ss_node)
            self.stat_sets[ss.name] = ss
            
#     s_dbs = doc.getElementsByTagName("mucked_windows")
        for hhc_node in doc.getElementsByTagName("hhc"):
            hhc = HHC(node = hhc_node)
            self.hhcs[hhc.site] = hhc

#        s_dbs = doc.getElementsByTagName("popup_windows")
        for pu_node in doc.getElementsByTagName("pu"):
            pu = Popup(node = pu_node)
            self.popup_windows[pu.name] = pu

        for imp_node in doc.getElementsByTagName("import"):
            imp = Import(node = imp_node)
            self.imp = imp

        for hui_node in doc.getElementsByTagName('hud_ui'):
            hui = HudUI(node = hui_node)
            self.ui = hui

        db = self.get_db_parameters()
        # Set the db path if it's defined in HUD_config.xml (sqlite only), otherwise place in config path.
        self.dir_database = db['db-path'] or os.path.join(CONFIG_PATH, u'database')
        if db['db-password'] == 'YOUR MYSQL PASSWORD':
            df_file = self.find_default_conf()
            if df_file is None: # this is bad
                pass
            else:
                df_parms = self.read_default_conf(df_file)
                self.set_db_parameters(db_name = 'fpdb', db_ip = df_parms['db-host'],
                                     db_user = df_parms['db-user'],
                                     db_port = df_parms['db-port'],
                                     db_pass = df_parms['db-password'])
                self.save(file=os.path.join(CONFIG_PATH, "HUD_config.xml"))
        
        if doc.getElementsByTagName("raw_hands") == []:
            self.raw_hands = RawHands()
        for raw_hands_node in doc.getElementsByTagName('raw_hands'):
            self.raw_hands = RawHands(raw_hands_node)
        
        if doc.getElementsByTagName("raw_tourneys") == []:
            self.raw_tourneys = RawTourneys()
        for raw_tourneys_node in doc.getElementsByTagName('raw_tourneys'):
            self.raw_tourneys = RawTourneys(raw_tourneys_node)
        
        #print ""
    #end def __init__

    def add_missing_elements(self, doc, example_file):
        """ Look through example config file and add any elements that are not in the config
            May need to add some 'enabled' attributes to turn things off - can't just delete a
            config section now because this will add it back in"""

        nodes_added = 0

        try:
            example_doc = xml.dom.minidom.parse(example_file) #parse the example configuration file
        except:
            log.error((("Error parsing example configuration file %s.") % (example_file)) + ("See error log file."))
            return nodes_added

        # loop through all FreePokerToolsConfig nodes in the document
        for cnode in doc.getElementsByTagName("FreePokerToolsConfig"):
            # loop through all FreePokerToolsConfig nodes in the example document
            for example_cnode in example_doc.childNodes:
                if example_cnode.localName == "FreePokerToolsConfig":
                    # loop through all child nodes of the FreePokerToolsConfig node in the example document
                    for e in example_cnode.childNodes:
                        # check if the child node is an element node and if there are no elements with the same name in the config file
                        if e.nodeType == e.ELEMENT_NODE and doc.getElementsByTagName(e.localName) == []:
                            # import the missing element into the config file
                            new = doc.importNode(e, True)  # True means do deep copy
                            t_node = self.doc.createTextNode("    ")
                            cnode.appendChild(t_node)
                            cnode.appendChild(new)
                            t_node = self.doc.createTextNode("\r\n\r\n")
                            cnode.appendChild(t_node)
                            print("... adding missing config section: " + e.localName)
                            nodes_added = nodes_added + 1

        if nodes_added > 0:
            print(("Added %d missing config sections" % nodes_added)+"\n")
            self.save()

        return nodes_added


    def find_default_conf(self):
        """Finds the default configuration file path.

        Returns:
            str: The path of the default configuration file, or None if it doesn't exist.
        """
        # Check if CONFIG_PATH is set
        if CONFIG_PATH:
            config_file = os.path.join(CONFIG_PATH, 'default.conf')
        else:
            # If CONFIG_PATH is not set, default configuration file does not exist
            config_file = None

        # Check if the default configuration file exists
        if config_file and os.path.exists(config_file):
            file = config_file
        else:
            file = None

        return file

    def get_doc(self):
        """Returns the document associated with the instance."""
        return self.doc

    def get_site_node(self, site):
        """Get the XML node for a given site."""
        # Loop through all the "site" nodes in the XML document.
        for site_node in self.doc.getElementsByTagName("site"):
            # If the "site_name" attribute of the current node matches the given site name,
            # return the node.
            if site_node.getAttribute("site_name") == site:
                return site_node


    def getEmailNode(self, siteName, fetchType):
        """
        Returns the email node for a given site name and fetch type.

        Args:
            siteName (str): The name of the site to search for.
            fetchType (str): The type of email to search for.

        Returns:
            The email node if found, else None.
        """
        siteNode = self.get_site_node(siteName)
        # Loop through each email node under the site node
        for emailNode in siteNode.getElementsByTagName("email"):
            if emailNode.getAttribute("fetchType") == fetchType:
                # Return the email node if its fetch type matches the input
                return emailNode
        # If no matching email node was found, return None
        return None


    def getStatSetNode(self, statsetName):
        """
        Returns the DOM game node for a given game.

        Args:
            statsetName (str): The name of the game.

        Returns:
            The DOM node for the game with the specified name.

        """
        # Loop through all the statset nodes in the document.
        for statsetNode in self.doc.getElementsByTagName("ss"):
            # Check if the name attribute of the current node matches the specified name.
            if statsetNode.getAttribute("name") == statsetName:
                # If it does, return the node.
                return statsetNode

    
    
    def getGameNode(self, gameName):
        """Returns the DOM game node for a given game name.

        Args:
            gameName (str): The name of the game to search for.

        Returns:
            The DOM node for the game with the given name, or None if it's not found.
        """
        # Loop through all game nodes in the document
        for gameNode in self.doc.getElementsByTagName("game"):
            # Uncomment this line to help with debugging
            #print "getGameNode gameNode:", gameNode

            # If this game node has the correct name attribute, return it
            if gameNode.getAttribute("game_name") == gameName:
                return gameNode

        # If we didn't find a matching game node, return None
        return None


    
    def get_aux_node(self, aux):
        """
        Returns the XML node for the given auxiliary data.

        Args:
            aux (str): The name of the auxiliary data.

        Returns:
            The XML node with the matching "name" attribute, or None if not found.
        """
        # Loop through all <aw> tags in the XML document
        for aux_node in self.doc.getElementsByTagName("aw"):
            # If the "name" attribute of the current node matches the given aux name, return it
            if aux_node.getAttribute("name") == aux:
                return aux_node
        # If we reach this point, the given aux name was not found in the XML document
        return None


    def get_layout_set_node(self, ls):
        """Return the layout set node with the given name.

        Args:
            ls (str): The name of the layout set.

        Returns:
            The layout set node with the given name, or None if not found.
        """
        # Iterate through all "ls" nodes in the document.
        for layout_set_node in self.doc.getElementsByTagName("ls"):
            # If the "name" attribute of the node matches the given name,
            # return the node.
            if layout_set_node.getAttribute("name") == ls:
                return layout_set_node
        # If no matching node was found, return None.
        return None


    def get_layout_node(self, ls, max):
        """
        This function searches the given xml layout for a node with the specified max attribute value.

        Args:
            ls (xml.dom.minidom.Document): the xml layout to search
            max (int): the max attribute value to search for

        Returns:
            xml.dom.minidom.Element: the layout node with the specified max attribute value, or None if not found
        """
        # iterate through each layout node in the xml document
        for layout_node in ls.getElementsByTagName("layout"):
            # check if the layout node has the specified max attribute value
            if layout_node.getAttribute("max") == str(max):
                return layout_node
        # if no layout node with the specified max attribute value is found, return None
        return None

                                
    def get_stat_set_node(self, ss):
        """
        Returns the first `ss` node in the XML document.

        Args:
            ss (str): The name of the `ss` node to find.

        Returns:
            xml.dom.minidom.Element: The first `ss` node in the XML document with
            the given name, or None if no such node exists.
        """
        # Iterate over all `ss` nodes in the document.
        for stat_set_node in self.doc.getElementsByTagName("ss"):
            # If the current `ss` node has the given name, return it.
            if stat_set_node.getAttribute("name") == ss:
                return stat_set_node

        # If no `ss` node with the given name was found, return None.
        return None


    def get_db_node(self, db_name):
        """
        Returns the XML node corresponding to the given database name, or None if not found.

        Args:
            db_name (str): The name of the database to search for.

        Returns:
            xml.dom.Node: The XML node corresponding to the given database name, or None if not found.
        """
        # Loop through each "database" node in the XML document
        for db_node in self.doc.getElementsByTagName("database"):
            # If the "db_name" attribute of this node matches the given database name
            if db_node.getAttribute("db_name") == db_name:
                # Return this node
                return db_node
        # If we get here, the database name was not found
        return None


#    def get_layout_node(self, site_node, layout):
#        for layout_node in site_node.getElementsByTagName("layout"):
#            if layout_node.getAttribute("max") is None:
#                return None
#            if int( layout_node.getAttribute("max") ) == int( layout ):
#                return layout_node

    def get_location_node(self, layout_node, seat):
        """
        Gets the location node for the given seat in the layout node

        Args:
            layout_node (xml.dom.minidom.Element): The layout node to search in
            seat (str): The seat to get the location node for. If "common", returns the common location node

        Returns:
            xml.dom.minidom.Element: The location node for the given seat, or None if not found
        """
        if seat == "common":
            # Look for the common location node
            for location_node in layout_node.getElementsByTagName("location"):
                if location_node.hasAttribute("common"):
                    return location_node
        else:
            # Look for the location node with the given seat attribute
            for location_node in layout_node.getElementsByTagName("location"):
                if int(location_node.getAttribute("seat")) == int(seat):
                    return location_node

        # If the location node is not found, return None
        return None


    def save(self, file=None):
        """
        Saves the XML document to a file.

        Parameters:
        - file: file path to save the document to. If None, the file path used to read the document is used.
        """
        if file is None:
            file = self.file

            # Backup the original file before overwriting it
            try:
                shutil.move(file, file + ".backup")
            except:
                pass

        # Write the XML document to the file
        with codecs.open(file, 'w', 'utf-8') as f:
            xml_string = self.doc.toxml()
            formatted_xml_string = self.wrap_long_lines(xml_string)
            f.write(formatted_xml_string)

    def wrap_long_lines(self, s):
        """
        Wraps long lines in a string to ensure they are no longer than 66 characters.

        Args:
            s (str): The input string to wrap.

        Returns:
            str: The wrapped string.
        """
        # Split the input string into separate lines.
        lines = [self.wrap_long_line(l) for l in s.splitlines()]

        # Join the wrapped lines back together into a single string.
        return '\n'.join(lines) + '\n'


    def wrap_long_line(self, l):
        """
        Takes a string and wraps it if it is longer than the configured wrap length.

        Args:
            l (str): The string to wrap.

        Returns:
            str: The wrapped string.
        """
        # Get the configured wrap length, or default to no wrap if it is not set.
        if 'config_wrap_len' in self.general:
            wrap_len = int(self.general['config_wrap_len'])
        else:
            wrap_len = -1    # < 0 means no wrap

        # If the configured wrap length is greater than or equal to 0 and the string is longer than the wrap length,
        # wrap the string.
        if wrap_len >= 0 and len(l) > wrap_len:
            # Find the length of the leading whitespace in the string, which will be used to indent the wrapped lines.
            m = re.compile('\s+\S+\s+')
            mo = m.match(l)
            if mo:
                indent_len = mo.end()
                indent = '\n' + ' ' * indent_len

                # Split the string into multiple parts, with each part being a substring that is wrapped to the
                # configured wrap length.
                m = re.compile('(\S+="[^"]+"\s+)')
                parts = [x for x in m.split(l[indent_len:]) if x]
                if len(parts) > 1:
                    l = l[0:indent_len] + indent.join(parts)
            return(l)
        else:
            return(l)


    def editEmail(self, siteName, fetchType, newEmail):
        """
        Edits the email for a given site and fetch type.

        Args:
            siteName (str): The name of the site.
            fetchType (str): The type of email fetch.
            newEmail (Email): The updated email information.

        Returns:
            None
        """
        # Get the email node for the site and fetch type
        emailNode = self.getEmailNode(siteName, fetchType)

        # Update the email attributes with the new information
        emailNode.setAttribute("host", newEmail.host)
        emailNode.setAttribute("username", newEmail.username)
        emailNode.setAttribute("password", newEmail.password)
        emailNode.setAttribute("folder", newEmail.folder)
        emailNode.setAttribute("useSsl", newEmail.useSsl)

    #end def editEmail
    
    def edit_fav_seat(self, site_name, enabled, seat2_dict, seat3_dict, seat4_dict, seat5_dict, seat6_dict, seat7_dict, seat8_dict, seat9_dict, seat10_dict):
        """
        Edits the favorite seat attribute of a given site node, based on the max attribute of each fav seat node.

        Args:
            site_name (str): Name of the site to edit.
            enabled (bool): Whether the site is enabled.
            seat2_dict (dict): Dictionary with the new favorite seats for max 2.
            seat3_dict (dict): Dictionary with the new favorite seats for max 3.
            seat4_dict (dict): Dictionary with the new favorite seats for max 4.
            seat5_dict (dict): Dictionary with the new favorite seats for max 5.
            seat6_dict (dict): Dictionary with the new favorite seats for max 6.
            seat7_dict (dict): Dictionary with the new favorite seats for max 7.
            seat8_dict (dict): Dictionary with the new favorite seats for max 8.
            seat9_dict (dict): Dictionary with the new favorite seats for max 9.
            seat10_dict (dict): Dictionary with the new favorite seats for max 10.
        """
        # Get the site node
        site_node = self.get_site_node(site_name)
        # Set the enabled attribute
        site_node.setAttribute("enabled", enabled)

        # Loop through all the fav seat nodes
        for fav_seat in site_node.getElementsByTagName("fav"):
            # Set the fav seat attribute based on the max attribute
            if fav_seat.getAttribute("max") == "2":
                fav_seat.setAttribute("fav_seat", seat2_dict)
            elif fav_seat.getAttribute("max") == "3":
                fav_seat.setAttribute("fav_seat", seat3_dict)
            elif fav_seat.getAttribute("max") == "4":
                fav_seat.setAttribute("fav_seat", seat4_dict)
            elif fav_seat.getAttribute("max") == "5":
                fav_seat.setAttribute("fav_seat", seat5_dict)
            elif fav_seat.getAttribute("max") == "6":
                fav_seat.setAttribute("fav_seat", seat6_dict)
            elif fav_seat.getAttribute("max") == "7":
                fav_seat.setAttribute("fav_seat", seat7_dict)
            elif fav_seat.getAttribute("max") == "8":
                fav_seat.setAttribute("fav_seat", seat8_dict)
            elif fav_seat.getAttribute("max") == "9":
                fav_seat.setAttribute("fav_seat", seat9_dict)
            elif fav_seat.getAttribute("max") == "10":
                fav_seat.setAttribute("fav_seat", seat10_dict)

    #end def
    
    def edit_hud(self, result, stat2, stat3, stat4, stat5, stat6, stat7, stat8, stat9, stat10, stat11, stat12, stat13):
        REPLACEMENTS = [
                        ("(0, 0)", "(1,1)"),
                        ("(0, 1)", "(1,2)"),
                        ("(0, 2)", "(1,3)"),
                        ("(0, 3)", "(1,4)"),
                        ("(1, 0)", "(2,1)"),
                        ("(1, 1)", "(2,2)"),
                        ("(1, 2)", "(2,3)"),
                        ("(1, 3)", "(2,4)"),
                        ("(2, 0)", "(3,1)"),
                        ("(2, 1)", "(3,2)"),
                        ("(2, 2)", "(3,3)"),
                        ("(2, 3)", "(3,4)"),
                        ("(3, 0)", "(4,1)"),
                        ("(3, 1)", "(4,2)"),
                        ("(3, 2)", "(4,3)"),
                        ("(3, 3)", "(4,4)"),
                        ]
            
        
        
            #print(transcript)
        for statsetNode in self.doc.getElementsByTagName("ss"):
            #print ("getStatSetNode statsetNode:",statsetNode)
            
            if statsetNode.getAttribute("name") == result:
                #print("true1")
                for fav_stat in statsetNode.getElementsByTagName("stat"):
                    print("type stat2", type(stat2))
                    print("stat2", (stat2))
                    print("fav",fav_stat.getAttribute("_rowcol"))
                    if stat2 == "(0, 0)":
                        stat2 = "(1,1)"
                    elif stat2 == "(0, 1)":
                        stat2 = "(1,2)"  
                    elif stat2 == "(0, 2)":
                        stat2 = "(1,3)"  
                    elif stat2 == "(0, 3)":
                        stat2 = "(1,4)"  
                    elif stat2 == "(1, 0)":
                        stat2 = "(2,1)"
                    elif stat2 == "(1, 1)":
                        stat2 = "(2,2)"  
                    elif stat2 == "(1, 2)":
                        stat2 = "(2,3)"  
                    elif stat2 == "(1, 3)":
                        stat2 = "(2,4)"
                    elif stat2 == "(2, 0)":
                        stat2 = "(3,1)"
                    elif stat2 == "(2, 1)":
                        stat2 = "(3,2)"  
                    elif stat2 == "(2, 2)":
                        stat2 = "(3,3)"  
                    elif stat2 == "(2, 3)":
                        stat2 = "(3,4)"
                    elif stat2 == "(32, 0)":
                        stat2 = "(4,1)"
                    elif stat2 == "(3, 1)":
                        stat2 = "(4,2)"  
                    elif stat2 == "(3, 2)":
                        stat2 = "(4,3)"  
                    elif stat2 == "(3, 3)":
                        stat2 = "(4,4)"
                    if fav_stat.getAttribute("_rowcol") == stat2:
                        fav_stat.setAttribute("_stat_name" ,stat3)
                        fav_stat.setAttribute("click" ,stat4)
                        fav_stat.setAttribute("hudcolor" ,stat5)
                        fav_stat.setAttribute("hudprefix" ,stat6)
                        fav_stat.setAttribute("hudsuffix" ,stat7)
                        fav_stat.setAttribute("popup" ,stat8)
                        fav_stat.setAttribute("stat_hicolor" ,stat9)
                        fav_stat.setAttribute("stat_hith" ,stat10)                            
                        fav_stat.setAttribute("stat_locolor" ,stat11)
                        fav_stat.setAttribute("stat_loth" ,stat12)
                        fav_stat.setAttribute("tip" ,stat13)
            
    #end def

    def edit_site(self, site_name, enabled, screen_name, history_path, summary_path):
        """
        Edits the site with the given site_name, setting its attributes to the provided values.

        Args:
            site_name (str): The name of the site to edit.
            enabled (bool): Whether the site should be enabled or not.
            screen_name (str): The screen name of the site.
            history_path (str): The path to the site's history file.
            summary_path (str): The path to the site's summary file, if it exists.
        """
        # Get the node corresponding to the site_name
        site_node = self.get_site_node(site_name)

        # Set the site's attributes to the provided values
        site_node.setAttribute("enabled", enabled)
        site_node.setAttribute("screen_name", screen_name)
        site_node.setAttribute("HH_path", history_path)

        # If a summary_path was provided, set the site's TS_path attribute to it
        if summary_path:
            site_node.setAttribute("TS_path", summary_path)

            
    def editStats(self, statsetName, statArray):
        """
        Replaces stat selection for the given gameName with the given statArray.
        """
        statsetNode = self.getStatSetNode(statsetName)
        statNodes = statsetNode.getElementsByTagName("stat")

        # Remove existing stats
        for node in statNodes:
            statsetNode.removeChild(node)

        # Set the rows and columns attributes
        statsetNode.setAttribute("rows", str(len(statArray)))
        statsetNode.setAttribute("cols", str(len(statArray[0])))

        # Add new stats
        for rowNumber in range(len(statArray)):
            for columnNumber in range(len(statArray[rowNumber])):
                newStat = self.doc.createElement("stat")

                # Set the _stat_name attribute
                newAttrStatName = self.doc.createAttribute("_stat_name")
                newStat.setAttributeNode(newAttrStatName)
                newStat.setAttribute("_stat_name", statArray[rowNumber][columnNumber])

                # Set the _rowcol attribute
                newAttrStatName = self.doc.createAttribute("_rowcol")
                newStat.setAttributeNode(newAttrStatName)
                newStat.setAttribute("_rowcol", ("("+str(rowNumber+1)+","+str(columnNumber+1)+")"))

                # Set the click attribute
                newAttrStatName = self.doc.createAttribute("click")
                newStat.setAttributeNode(newAttrStatName)
                newStat.setAttribute("click", "")

                # Set the popup attribute
                newAttrStatName = self.doc.createAttribute("popup")
                newStat.setAttributeNode(newAttrStatName)
                newStat.setAttribute("popup", "default")

                # Set the tip attribute
                newAttrStatName = self.doc.createAttribute("tip")
                newStat.setAttributeNode(newAttrStatName)
                newStat.setAttribute("tip", "")

                statsetNode.appendChild(newStat)

        # TODO: remove this line?
        statNodes = statsetNode.getElementsByTagName("stat")

    #end def editStats

    def editImportFilters(self, games):
        """
        Edit the import filters with the given games.

        Args:
            games (str): A comma-separated list of game names.

        Returns:
            None
        """
        # Update the import filters in the object
        self.imp.importFilters = games

        # Find the last import node in the XML document
        imp_node = self.doc.getElementsByTagName("import")[-1]

        # Update the importFilters attribute of the import node
        imp_node.setAttribute("importFilters", games)


    def save_layout_set(self, ls, max, locations, width=None, height=None):
        """
        Saves the layout set.

        Args:
            ls (LayoutSet): The layout set to be saved.
            max (int): The maximum number of windows.
            locations (dict): A dictionary with window IDs as keys and their positions as values.
            width (int, optional): The width of the layout set. Defaults to None.
            height (int, optional): The height of the layout set. Defaults to None.
        """
        #wid/height normally not specified when saving common from the mucked display

        # Print out some information for debugging purposes
        print("saving layout =", ls.name, " ", str(max), "Max ", str(locations), "size:", str(width), "x", str(height))

        # Get the layout set node and the layout node
        ls_node = self.get_layout_set_node(ls.name)
        layout_node = self.get_layout_node(ls_node, max)

        # Set the width and height attributes if they are specified
        if width: 
            layout_node.setAttribute("width", str(width))
        if height: 
            layout_node.setAttribute("height", str(height))

        # Iterate through the locations and set the x and y attributes of each location node in the layout node
        for (i, pos) in list(locations.items()):
            location_node = self.get_location_node(layout_node, i)
            location_node.setAttribute("x", str(locations[i][0]))
            location_node.setAttribute("y", str(locations[i][1]))

            # Refresh the live instance of the layout set with the new locations
            # This is needed because any future windows created after a save layout
            # MUST pickup the new layout
            # Fixme - this is horrid 
            if i == "common":
                self.layout_sets[ls.name].layout[max].common = (locations[i][0], locations[i][1])
            else:
                self.layout_sets[ls.name].layout[max].location[i] = (locations[i][0], locations[i][1])

        # More horridness below, fixme
        if height: 
            self.layout_sets[ls.name].layout[max].height = height
        if width: 
            self.layout_sets[ls.name].layout[max].width = width

        
                
    #NOTE: we got a nice Database class, so why map it again here?
    #            user input validation should be done when initializing the Database class. this allows to give appropriate feddback when something goes wrong
    #            try ..except is evil here. it swallows all kinds of errors. dont do this
    #            naming database types 2, 3, 4 on the fly is no good idea. i see this all over the code. better use some globally defined consts (see DATABASE_TYPE_*)
    #            i would like to drop this method entirely and replace it by get_selected_database() or better get_active_database(), returning one of our Database instances
    #            thus we can drop self.db_selected (holding database name) entirely and replace it with self._active_database = Database, avoiding to define the same
    #            thing multiple times
    def get_db_parameters(self):
        """
        Returns a dictionary containing the database parameters for the selected database.
        """
        db = {}
        name = self.db_selected

        # TODO: What's up with all the exception handling here?!
        # Set database name
        try:    
            db['db-databaseName'] = name
        except: 
            pass

        # Set database description
        try:    
            db['db-desc'] = self.supported_databases[name].db_desc
        except: 
            pass

        # Set database host
        try:    
            db['db-host'] = self.supported_databases[name].db_ip
        except: 
            pass
                
        # Set database port
        try:    
            db['db-port'] = self.supported_databases[name].db_port
        except: 
            pass

        # Set database user
        try:    
            db['db-user'] = self.supported_databases[name].db_user
        except: 
            pass

        # Set database password
        try:    
            db['db-password'] = self.supported_databases[name].db_pass
        except: 
            pass

        # Set database server
        try:    
            db['db-server'] = self.supported_databases[name].db_server
        except: 
            pass

        # Set database path
        try:    
            db['db-path'] = self.supported_databases[name].db_path
        except: 
            pass

        # Set database backend
        db['db-backend'] = self.get_backend(self.supported_databases[name].db_server)

        return db


    def set_db_parameters(self, db_name='fpdb', db_ip=None, db_user=None,
                        db_pass=None, db_desc=None, db_server=None,
                        default="False"):
        """
        Set the parameters of the database.

        Args:
            db_name (str): The name of the database.
            db_ip (str): The IP address of the database.
            db_user (str): The username to login to the database.
            db_pass (str): The password to login to the database.
            db_desc (str): The description of the database.
            db_server (str): The server of the database.
            default (str): Whether the database is the default one.

        Returns:
            None
        """
        # Get the node corresponding to the database
        db_node = self.get_db_node(db_name)

        # Convert the default value to a boolean
        default = default.lower()
        defaultb = string_to_bool(default, False)

        # Update the database node attributes if not None
        if db_node is not None:
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)

            # Set the default attribute to True if defaultb is True or the database is already selected
            if defaultb or self.db_selected == db_name:
                db_node.setAttribute("default", "True")

                # Remove the default attribute from other databases
                for dbn in self.doc.getElementsByTagName("database"):
                    if dbn.getAttribute('db_name') != db_name and dbn.hasAttribute("default"):
                        dbn.removeAttribute("default")
            # Remove the default attribute from the database node
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")

        # Update the supported database parameters if not None
        if db_name in self.supported_databases:
            if db_desc is not None:
                self.supported_databases[db_name].dp_desc = db_desc
            if db_ip is not None:
                self.supported_databases[db_name].dp_ip = db_ip
            if db_user is not None:
                self.supported_databases[db_name].dp_user = db_user
            if db_pass is not None:
                self.supported_databases[db_name].dp_pass = db_pass
            if db_server is not None:
                self.supported_databases[db_name].dp_server = db_server
            self.supported_databases[db_name].db_selected = defaultb

        # Set the selected database if defaultb is True
        if defaultb:
            self.db_selected = db_name
        return


    def add_db_parameters(self, db_name='fpdb', db_ip=None, db_user=None,
                        db_pass=None, db_desc=None, db_server=None,
                        default="False"):
        """
        Add database parameters to the XML configuration file.

        Args:
            db_name (str): Name of the database.
            db_ip (str): IP address of the database.
            db_user (str): Username for the database.
            db_pass (str): Password for the database.
            db_desc (str): Description of the database.
            db_server (str): Name of the server hosting the database.
            default (str): Whether or not this is the default database.

        Returns:
            None
        """
        # Convert default to boolean
        default = default.lower()
        defaultb = string_to_bool(default, False)

        # Check for duplicate database names
        if db_name in self.supported_databases:
            raise ValueError("Database names must be unique")

        # Get the database node and create a new one if it doesn't exist
        db_node = self.get_db_node(db_name)
        if db_node is None:
            for db_node in self.doc.getElementsByTagName("supported_databases"):
                # should only be one supported_databases element, use last one if there are several
                suppdb_node = db_node
            t_node = self.doc.createTextNode("    ")
            suppdb_node.appendChild(t_node)
            db_node = self.doc.createElement("database")
            suppdb_node.appendChild(db_node)
            t_node = self.doc.createTextNode("\r\n    ")
            suppdb_node.appendChild(t_node)
            db_node.setAttribute("db_name", db_name)
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)

            # Set as default database if necessary
            if defaultb:
                db_node.setAttribute("default", "True")
                for dbn in self.doc.getElementsByTagName("database"):
                    if dbn.getAttribute('db_name') != db_name and dbn.hasAttribute("default"):
                        dbn.removeAttribute("default")
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")
        else:
            # Update existing database node
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)

            # Set as default database if necessary
            if defaultb or self.db_selected == db_name:
                db_node.setAttribute("default", "True")
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")

        # Update supported databases dictionary

        if db_name in self.supported_databases:
            if db_desc   is not None: self.supported_databases[db_name].dp_desc   = db_desc
            if db_ip     is not None: self.supported_databases[db_name].dp_ip     = db_ip
            if db_user   is not None: self.supported_databases[db_name].dp_user   = db_user
            if db_pass   is not None: self.supported_databases[db_name].dp_pass   = db_pass
            if db_server is not None: self.supported_databases[db_name].dp_server = db_server
            self.supported_databases[db_name].db_selected = defaultb
        else:
            db = Database(node=db_node)
            self.supported_databases[db.db_name] = db

        if defaultb:
            self.db_selected = db_name
        return
    
    def get_backend(self, name):
        """Returns the number of the currently used backend.

        Args:
            name (str): The name of the database backend.

        Returns:
            int: The number of the currently used backend.

        Raises:
            ValueError: If the specified database backend is not supported.
        """
        if name == DATABASE_TYPE_MYSQL:
            ret = 2
        elif name == DATABASE_TYPE_POSTGRESQL:
            ret = 3
        elif name == DATABASE_TYPE_SQLITE:
            ret = 4
            # sqlcoder: this assignment fixes unicode problems for me with sqlite (windows, cp1252)
            #           feel free to remove or improve this if you understand the problems
            #           better than me (not hard!)
            Charset.not_needed1, Charset.not_needed2, Charset.not_needed3 = True, True, True
        else:
            raise ValueError('Unsupported database backend: %s' % self.supported_databases[name].db_server)

        return ret


    def getDefaultSite(self):
        """Return the name of the first enabled site or None if no sites are enabled."""
        # Iterate through each supported site and check if it's enabled
        for site_name, site in list(self.supported_sites.items()):
            if site.enabled:
                # Return the name of the first enabled site
                return site_name
        # Return None if no sites are enabled
        return None

    # Allow to change the menu appearance
    def get_hud_ui_parameters(self):
        """
        Returns a dictionary of HUD UI parameters.
        """
        hui = {}

        # Set default text if label is empty
        default_text = 'FPDB Menu - Right click\nLeft-Drag to Move'

        # Try to get label from UI, falling back to default text if it's empty
        try:
            hui['label'] = self.ui.label
            if self.ui.label == '':
                hui['label'] = default_text
        except:
            hui['label'] = default_text

        # Try to get card_ht from UI, falling back to default value if it's not an integer
        try:
            hui['card_ht'] = int(self.ui.card_ht)
        except:
            hui['card_ht'] = 42

        # Try to get card_wd from UI, falling back to default value if it's not an integer
        try:
            hui['card_wd'] = int(self.ui.card_wd)
        except:
            hui['card_wd'] = 30

        # Try to get deck_type from UI, falling back to default value if it's not a string
        try:
            hui['deck_type'] = str(self.ui.deck_type)
        except:
            hui['deck_type'] = 'colour'

        # Try to get card_back from UI, falling back to default value if it's not a string
        try:
            hui['card_back'] = str(self.ui.card_back)
        except:
            hui['card_back'] = 'back04'

        # Try to get stat_range from UI, falling back to default value if it's not a string
        try:
            hui['stat_range'] = self.ui.stat_range
        except:
            hui['stat_range'] = 'A' # default is show stats for All-time, also S(session) and T(ime)

        # Try to get hud_days from UI, falling back to default value if it's not an integer
        try:
            hui['hud_days'] = int(self.ui.hud_days)
        except:
            hui['hud_days'] = 90

        # Try to get agg_bb_mult from UI, falling back to default value if it's not an integer
        try:
            hui['agg_bb_mult'] = int(self.ui.agg_bb_mult)
        except:
            hui['agg_bb_mult'] = 1

        # Try to get seats_style from UI, falling back to default value if it's not a string
        try:
            hui['seats_style'] = self.ui.seats_style
        except:
            hui['seats_style'] = 'A' # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        # Try to get seats_cust_nums_low from UI, falling back to default value if it's not an integer
        try:
            hui['seats_cust_nums_low'] = int(self.ui.seats_cust_nums_low)
        except:
            hui['seats_cust_nums_low'] = 1

        # Try to get seats_cust_nums_high from UI, falling back to default value if it's not an integer
        try:
            hui['seats_cust_nums_high'] = int(self.ui.seats_cust_nums_high)
        except:
            hui['seats_cust_nums_high'] = 10

        # Hero specific

        try:    hui['h_stat_range']    = self.ui.h_stat_range
        except: hui['h_stat_range']    = 'S'

        try:    hui['h_hud_days']     = int(self.ui.h_hud_days)
        except: hui['h_hud_days']     = 30

        try:    hui['h_agg_bb_mult']    = int(self.ui.h_agg_bb_mult)
        except: hui['h_agg_bb_mult']    = 1

        try:    hui['h_seats_style']    = self.ui.h_seats_style
        except: hui['h_seats_style']    = 'A'  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:    hui['h_seats_cust_nums_low']    = int(self.ui.h_seats_cust_nums_low)
        except: hui['h_seats_cust_nums_low']    = 1
        try:    hui['h_seats_cust_nums_high']    = int(self.ui.h_seats_cust_nums_high)
        except: hui['h_seats_cust_nums_high']    = 10
        return hui


    def get_import_parameters(self):
        """
        Returns a dictionary of import parameters based on the current state of the object.
        """
        imp = {}

        # Get callFpdbHud parameter
        try:    
            imp['callFpdbHud'] = self.imp.callFpdbHud
        except:  
            imp['callFpdbHud'] = True

        # Get interval parameter
        try:    
            imp['interval'] = self.imp.interval
        except:  
            imp['interval'] = 10

        # Get ResultsDirectory parameter
        # NOTE: try: except: doesn't seem to be triggering
        #       using if instead
        if self.imp.ResultsDirectory != '':
            imp['ResultsDirectory'] = self.imp.ResultsDirectory
        else:
            imp['ResultsDirectory'] = "~/.fpdb/Results/"

        # Get hhBulkPath parameter
        try:    
            imp['hhBulkPath'] = self.imp.hhBulkPath
        except:  
            imp['hhBulkPath'] = ""

        # Get saveActions parameter
        try:    
            imp['saveActions'] = self.imp.saveActions
        except:  
            imp['saveActions'] = False

        # Get cacheSessions parameter
        try:    
            imp['cacheSessions'] = self.imp.cacheSessions
        except:  
            imp['cacheSessions'] = False

        # Get publicDB parameter
        try:    
            imp['publicDB'] = self.imp.publicDB
        except:  
            imp['publicDB'] = False

        # Get sessionTimeout parameter
        try:    
            imp['sessionTimeout'] = self.imp.sessionTimeout
        except:  
            imp['sessionTimeout'] = 30

        # Get saveStarsHH parameter
        try:    
            imp['saveStarsHH'] = self.imp.saveStarsHH
        except:  
            imp['saveStarsHH'] = False

        # Get fastStoreHudCache parameter
        try:    
            imp['fastStoreHudCache'] = self.imp.fastStoreHudCache
        except:  
            imp['fastStoreHudCache'] = False

        # Get importFilters parameter
        try:    
            imp['importFilters'] = self.imp.importFilters
        except:  
            imp['importFilters'] = []

        # Get timezone parameter
        try:    
            imp['timezone'] = self.imp.timezone
        except:  
            imp['timezone'] = "America/New_York"

        return imp

    
    def set_timezone(self, timezone):
        """
        Sets the timezone for the object.

        Args:
            timezone (str): The timezone to set.

        Returns:
            None
        """
        self.imp.timezone = timezone  # Update the timezone attribute of the object


    def get_default_paths(self, site=None):
        """
        Returns a dictionary of default paths for a given site.

        Args:
            site (str): The name of the site for which to retrieve default paths. 
                        Default is None.

        Returns:
            dict: A dictionary containing the default paths for a given site.
                If the path does not exist, an error message is returned instead.
        """
        # If site is None, use the default site
        if site is None: 
            site = self.getDefaultSite()
        paths = {}
        try:
            # Get the path for the given site
            path = os.path.expanduser(self.supported_sites[site].HH_path)
            # Check if the path exists as either a directory or file
            assert(os.path.isdir(path) or os.path.isfile(path))
            # Set the default path for HUD and bulk import to the path found earlier
            paths['hud-defaultPath'] = paths['bulkImport-defaultPath'] = path
            # If an hhBulkPath is set, set the bulk import default path to that instead
            if self.imp.hhBulkPath:
                paths['bulkImport-defaultPath'] = self.imp.hhBulkPath
            # If a TS_path is set for the site, set the hud-defaultTSPath to that
            if self.supported_sites[site].TS_path != '':
                tspath = os.path.expanduser(self.supported_sites[site].TS_path)
                paths['hud-defaultTSPath'] = tspath
        except AssertionError:
            # If the path does not exist, set the default path for HUD and bulk import to an error message
            paths['hud-defaultPath'] = paths['bulkImport-defaultPath'] = "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **"
        return paths


#    def get_frames(self, site = "PokerStars"):
#        if site not in self.supported_sites: return False
#        return self.supported_sites[site].use_frames == True

#    def get_default_colors(self, site = "PokerStars"):
#        colors = {}
#        if site not in self.supported_sites or self.supported_sites[site].hudopacity == "":
#            colors['hudopacity'] = 0.90
#        else:
#            colors['hudopacity'] = float(self.supported_sites[site].hudopacity)
#        if site not in self.supported_sites or self.supported_sites[site].hudbgcolor == "":
#            colors['hudbgcolor'] = "#FFFFFF"
#        else:
#            colors['hudbgcolor'] = self.supported_sites[site].hudbgcolor
#        if site not in self.supported_sites or self.supported_sites[site].hudfgcolor == "":
#            colors['hudfgcolor'] = "#000000"
#        else:
#            colors['hudfgcolor'] = self.supported_sites[site].hudfgcolor
#        return colors

#    def get_default_font(self, site='PokerStars'):
#        font = "Sans"
#        font_size = "8"
#        site = self.supported_sites.get(site, None)
#        if site is not None:
#            if site.font:
#                font = site.font
#            if site.font_size:
#                font_size = site.font_size
#        return font, font_size

    def get_layout_set_locations(self, set="mucked", max="9"):
        """
        Returns the locations of the cards in a given layout set.

        Args:
            set (str): The name of the layout set to use. Defaults to "mucked".
            max (str): The maximum number of cards in the layout set. Defaults to "9".

        Returns:
            tuple: A tuple containing the locations of the cards in the layout set.
        """
        try:
            locations = self.layout_sets[set].layout[max].location
        except:
            # If the layout set or maximum number of cards is not found, return default locations.
            locations = (
                (0, 0),
                (684, 61),
                (689, 239),
                (692, 346),
                (586, 393),
                (421, 440),
                (267, 440),
                (0, 361),
                (0, 280),
                (121, 280),
                (46, 30),
            )
        return locations

             
    def get_supported_sites(self, all=False):
        """
        Returns the list of supported sites.

        Args:
            all (bool): If True, returns the list of all supported sites, including disabled sites.

        Returns:
            list: A list containing the names of the supported sites.
        """
        if all:
            # If the 'all' parameter is True, return the keys of the 'supported_sites' dictionary.
            return list(self.supported_sites.keys())
        else:
            # Otherwise, return the names of the enabled sites.
            return [site_name for (site_name, site) in list(self.supported_sites.items()) if site.enabled]


    def get_site_parameters(self, site):
        """
        Returns a dictionary of the site parameters for the specified site.
        :param site: name of the site
        :return: dictionary of site parameters
        """
        # initialize an empty dictionary to store site parameters
        parms = {}
        # add site converter to the dictionary
        parms["converter"] = self.hhcs[site].converter
        # add site summary importer to the dictionary
        parms["summaryImporter"] = self.hhcs[site].summaryImporter
        # add site screen name to the dictionary
        parms["screen_name"] = self.supported_sites[site].screen_name
        # add site path to the dictionary
        parms["site_path"] = self.supported_sites[site].site_path
        # add site HH path to the dictionary
        parms["HH_path"] = self.supported_sites[site].HH_path
        # add site TS path to the dictionary
        parms["TS_path"] = self.supported_sites[site].TS_path
        # add site name to the dictionary
        parms["site_name"] = self.supported_sites[site].site_name
        # add site enabled status to the dictionary
        parms["enabled"] = self.supported_sites[site].enabled
        # add site aux enabled status to the dictionary
        parms["aux_enabled"] = self.supported_sites[site].aux_enabled
        # add site HUD menu X shift to the dictionary
        parms["hud_menu_xshift"] = self.supported_sites[site].hud_menu_xshift
        # add site HUD menu Y shift to the dictionary
        parms["hud_menu_yshift"] = self.supported_sites[site].hud_menu_yshift        
        # add site layout set to the dictionary
        parms["layout_set"] = self.supported_sites[site].layout_set
        # add site emails to the dictionary
        parms["emails"] = self.supported_sites[site].emails
        # add site favorite seat to the dictionary
        parms["fav_seat"] = self.supported_sites[site].fav_seat

        # return the dictionary of site parameters
        return parms


    def get_layout(self, site, game_type):
        """
        This method returns a Layout-set() instance for the given site and game type.

        Args:
            site (str): The name of the site.
            game_type (str): The type of the game.

        Returns:
            Layout-set() instance: The Layout-set() instance for the given site and game type.
            None: If there is no Layout-set() instance for the given site and game type.
        """

        # Find layouts used at site.
        site_layouts = self.get_site_parameters(site)["layout_set"]

        # Locate the one used for this game_type.
        if game_type in site_layouts:
            return self.layout_sets[site_layouts[game_type]]
        elif "all" in site_layouts:
            return self.layout_sets[site_layouts["all"]]
        else:
            return None


#    def set_site_parameters(self, site_name, converter = None, decoder = None,
#                            hudbgcolor = None, hudfgcolor = None,
#                            hudopacity = None, screen_name = None,
#                            site_path = None, table_finder = None,
#                            HH_path = None, enabled = None,
#                            font = None, font_size = None):
#        """Sets the specified site parameters for the specified site."""
#        site_node = self.get_site_node(site_name)
#        if db_node is not None:
#            if converter      is not None: site_node.setAttribute("converter", converter)
#            if decoder        is not None: site_node.setAttribute("decoder", decoder)
#            if hudbgcolor     is not None: site_node.setAttribute("hudbgcolor", hudbgcolor)
#            if hudfgcolor     is not None: site_node.setAttribute("hudfgcolor", hudfgcolor)
#            if hudopacity     is not None: site_node.setAttribute("hudopacity", hudopacity)
#            if screen_name    is not None: site_node.setAttribute("screen_name", screen_name)
#            if site_path      is not None: site_node.setAttribute("site_path", site_path)
#            if table_finder   is not None: site_node.setAttribute("table_finder", table_finder)
#            if HH_path        is not None: site_node.setAttribute("HH_path", HH_path)
#            if enabled        is not None: site_node.setAttribute("enabled", enabled)
#            if font           is not None: site_node.setAttribute("font", font)
#            if font_size      is not None: site_node.setAttribute("font_size", font_size)
#        return

    def set_general(self, lang=None):
        """
        Sets the 'ui_language' attribute of all 'general' nodes in the XML document.

        Args:
            lang (str): The language code to set the 'ui_language' attribute to. If not provided, the attribute is not set.
        """
        # Loop through all 'general' nodes in the document
        for general_node in self.doc.getElementsByTagName('general'):
            if lang:
                # Set the 'ui_language' attribute to the provided language code
                general_node.setAttribute("ui_language", lang)


    def set_site_ids(self, sites):
        """
        Sets the site IDs for the current object.

        Args:
            sites (dict): A dictionary of site IDs.

        Returns:
            None
        """
        # Convert the dictionary to a dictionary with string keys
        self.site_ids = dict(sites)


    def get_site_id(self, site):
        """
        Given a site, return the corresponding site ID from the `site_ids` dictionary.

        Args:
            site (str): The name of the site for which to retrieve the ID.

        Returns:
            int: The ID corresponding to the input `site`.

        Raises:
            KeyError: If the input `site` is not present in the `site_ids` dictionary.
        """
        return self.site_ids[site]  # Return the ID corresponding to the input `site`.

        
    def get_aux_windows(self):
        """
        Returns the list of mucked window formats in the configuration.

        Returns:
            list: A list of mucked window formats.
        """
        # Get the keys of the aux_windows dictionary and return them as a list.
        return list(self.aux_windows.keys())


    def get_aux_parameters(self, name):
        """
        Gets a dictionary of mucked window parameters from the named mw.

        Args:
            name (str): The name of the window to get parameters for.

        Returns:
            dict: A dictionary of parameters for the named window, or None if the window does not exist.
        """
        # Initialize an empty dictionary to hold the parameters.
        param = {}

        # Check if the named window exists in the aux_windows dictionary.
        if name in self.aux_windows:
            # Iterate over the properties of the named window.
            for key in dir(self.aux_windows[name]):
                # Skip any keys that start with '__', as they are special properties.
                if key.startswith('__'): continue

                # Get the value of the property.
                value = getattr(self.aux_windows[name], key)

                # Skip any values that are callable, as they are methods.
                if callable(value): continue

                # Add the key-value pair to the dictionary.
                param[key] = value

            # Return the dictionary of parameters.
            return param

        # Return None if the named window does not exist.
        return None


    def get_stat_sets(self):
        """Gets the list of stat block contents in the configuration.

        Returns:
            list: A list of all the stat block contents in the configuration.
        """
        return list(self.stat_sets.keys())

    

        
    def get_layout_set_parameters(self, name):
        """
        Gets a dict of parameters from the named layout set.

        Args:
            name (str): The name of the layout set.

        Returns:
            dict: A dictionary of parameters from the named layout set.
                If the named layout set does not exist, returns None.
        """

        # Create an empty dictionary to hold the layout set parameters.
        param = {}

        # Check if the named layout set exists.
        if name in self.layout_sets:

            # Loop through all the attributes of the layout set.
            for key in dir(self.layout_sets[name]):

                # Skip any attributes that start with '__'.
                if key.startswith('__'):
                    continue

                # Get the value of the attribute.
                value = getattr(self.layout_sets[name], key)

                # Skip any attributes that are callable.
                if callable(value):
                    continue

                # Add the attribute and its value to the parameter dictionary.
                param[key] = value

            # Return the parameter dictionary.
            return param

        # If the named layout set does not exist, return None.
        return None


        
    def get_layout_set_parameters(self, name):
        """Get a dict of parameters from the named layout set.

        Args:
            name (str): The name of the layout set.

        Returns:
            dict: A dictionary containing the parameters of the layout set.
        """
        # Create an empty dictionary to hold the parameters.
        param = {}

        # Check if the layout set exists.
        if name in self.layout_sets:
            # Get all attributes of the layout set.
            for key in dir(self.layout_sets[name]):
                # Skip any attributes that start with '__'.
                if key.startswith('__'):
                    continue

                # Get the value of the attribute.
                value = getattr(self.layout_sets[name], key)

                # Skip any callable attributes.
                if callable(value):
                    continue

                # Add the parameter to the dictionary.
                param[key] = value

            # Return the dictionary of parameters.
            return param

        # If the layout set does not exist, return None.
        return None


    def get_supported_games(self):
        """Returns the list of supported games.

        Returns:
            list: A list of supported game names.
        """
        supported_games = []
        # Iterate over the dictionary keys
        for game in list(self.supported_games.keys()):
            supported_games.append(self.supported_games[game].game_name)
        return supported_games


    def get_supported_games_parameters(self, name, game_type):
        """Gets a dict of parameters from the named gametype.

        Args:
        name (str): Name of the supported game.
        game_type (str): Type of the game.

        Returns:
        dict: A dictionary of parameters from the named gametype.
        """
        # Initialize an empty dictionary to store the parameters.
        param = {}

        # Check if the name is in the list of supported games.
        if name in self.supported_games:
            # Loop through the keys of the supported game.
            for key in dir(self.supported_games[name]):
                # Skip keys that start with '__' or are callable.
                if key.startswith('__') or callable(getattr(self.supported_games[name], key)):
                    continue
                # Add the key-value pair to the param dictionary.
                param[key] = getattr(self.supported_games[name], key)

            # Load the correct Stats_sets instance into the game_stat_set key.
            game_stat_set = getattr(self.supported_games[name], 'game_stat_set')
            if game_type in game_stat_set:
                # If game_type is in the game_stat_set, set the corresponding stat set.
                param['game_stat_set'] = self.stat_sets[game_stat_set[game_type].stat_set]
            elif "all" in game_stat_set:
                # If "all" is in the game_stat_set, set the corresponding stat set.
                param['game_stat_set'] = self.stat_sets[game_stat_set["all"].stat_set]
            else:
                # If neither game_type nor "all" is in the game_stat_set, return None.
                return None

            # Return the dictionary of parameters.
            return param

        # If the name is not in the list of supported games, return None.
        return None

        
    def execution_path(self, filename):
        """Join the fpdb path to the given filename.

        Args:
            filename (str): The name of the file to join to the fpdb path.

        Returns:
            str: The absolute path to the given filename, with the fpdb path as its base.
        """
        # Get the path to the current file
        current_file_path = inspect.getfile(sys._getframe(0))

        # Get the directory of the fpdb package
        fpdb_dir_path = os.path.dirname(current_file_path)

        # Combine the fpdb directory path with the given filename
        abs_path = os.path.join(fpdb_dir_path, filename)

        return abs_path

    def get_general_params(self):
        """Returns the general parameters."""
        return self.general


    def get_gui_cash_stat_params(self):
        """
        Returns the GUI cash statistics parameters.

        Args:
            self: The object instance.

        Returns:
            The GUI cash statistics parameters.
        """
        #print(type(self.gui_cash_stats))
        return self.gui_cash_stats

    
    def get_gui_tour_stat_params(self):
        """
        Returns the GUI tour statistics parameters.
        """
        # Uncomment the following line if you want to check the type of gui_tour_stats
        # print(type(self.gui_tour_stats))
        return self.gui_tour_stats


if __name__== "__main__":
    set_logfile("fpdb-log.txt")
    c = Config()
    
    print("\n----------- GENERAL -----------")
    print(c.general)

    print("\n----------- SUPPORTED SITES -----------")
    for s in list(c.supported_sites.keys()):
        print(c.supported_sites[s])

    print("\n----------- SUPPORTED GAMES -----------")
    for game in list(c.supported_games.keys()):
        print(c.supported_games[game])

    print("\n----------- SUPPORTED DATABASES -----------")
    for db in list(c.supported_databases.keys()):
        print(c.supported_databases[db])

    print("\n----------- AUX WINDOW FORMATS -----------")
    for w in list(c.aux_windows.keys()):
        print(c.aux_windows[w])
    
    print("\n----------- LAYOUT SETS FORMATS -----------")
    for w in list(c.layout_sets.keys()):
        print(c.layout_sets[w])
    
    print("\n----------- STAT SETS FORMATS -----------")
    for w in list(c.stat_sets.keys()):
        print(c.stat_sets[w])

    print("\n----------- HAND HISTORY CONVERTERS -----------")
    for w in list(c.hhcs.keys()):
        print(c.hhcs[w])

    print("\n----------- POPUP WINDOW FORMATS -----------")
    for w in list(c.popup_windows.keys()):
        print(c.popup_windows[w])
        
    print("\n-----------  DATABASE PARAMS -----------")
    print("db    = ", c.get_db_parameters())
    
    print("\n-----------  HUD PARAMS -----------")
    print("hud params =")
    for hud_param, value in list(c.get_hud_ui_parameters().items()):
        print(" %s = %s" % (hud_param, value))
        
    print("\n-----------  STARTUP PATH -----------")
    print("start up path = ", c.execution_path(""))
    
    print("\n-----------  GUI CASH STATS -----------")
    print("gui_cash_stats =", c.gui_cash_stats)

    print("\n----------- Heroes -----------")
    for s in list(c.supported_sites.keys()):
        print(c.supported_sites[s].screen_name)

    print("\n----------- ENVIRONMENT CONSTANTS -----------")
    print("Configuration.install_method {source,exe,app} =", INSTALL_METHOD)
    print("Configuration.fpdb_root_path =", FPDB_ROOT_PATH, type(FPDB_ROOT_PATH))
    print("Configuration.graphics_path =", GRAPHICS_PATH, type(GRAPHICS_PATH))
    print("Configuration.appdata_path =", APPDATA_PATH, type(APPDATA_PATH))
    print("Configuration.config_path =", CONFIG_PATH, type(CONFIG_PATH))
    print("Configuration.pyfpdb_path =", PYFPDB_PATH, type(PYFPDB_PATH))
    print("Configuration.os_family {Linux,Mac,XP,Win7} =", OS_FAMILY)
    print("Configuration.posix {True/False} =", POSIX)
    print("Configuration.python_version =", PYTHON_VERSION)
    print("\n\n----------- END OF CONFIG REPORT -----------")

    print("press enter to end")
    sys.stdin.readline()

