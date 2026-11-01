"""The configured databases and the database a session uses."""

# Handles fpdb/fpdb-hud configuration files.
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
from __future__ import annotations

from typing import Any

from fpdb_3_legacy.config_common import (
    ConfigBase,
    string_to_bool,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class Database:
    def __init__(self, node) -> None:
        self.db_name = node.getAttribute("db_name")
        self.db_desc = node.getAttribute("db_desc")
        self.db_server = node.getAttribute("db_server").lower()
        self.db_ip = node.getAttribute("db_ip")
        self.db_port = node.getAttribute("db_port")
        self.db_user = node.getAttribute("db_user")
        self.db_pass = node.getAttribute("db_pass")
        self.db_path = node.getAttribute("db_path")
        self.db_selected = string_to_bool(node.getAttribute("default"), default=False)
        log.debug(
            f"Database db_name:'{self.db_name}'  db_server:'{self.db_server}'  db_ip:'{self.db_ip}'  db_port:'{self.db_port}' db_user:'{self.db_user}'  db_pass (not logged)  selected:'{self.db_selected}'",
        )

    def __str__(self) -> str:
        temp = "Database = " + self.db_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + repr(value) + "\n"
        return temp


class ConfigDatabasesMixin(ConfigBase):
    """Read and edit the configured databases."""

    def get_db_node(self, db_name):
        for db_node in self.doc.getElementsByTagName("database"):
            if db_node.getAttribute("db_name") == db_name:
                return db_node
        return None

    #    def get_layout_node(self, site_node, layout):
    #        for layout_node in site_node.getElementsByTagName("layout"):
    #            if layout_node.getAttribute("max") is None:
    #                return None
    #            if int( layout_node.getAttribute("max") ) == int( layout ):
    #                return layout_node

    # NOTE: we got a nice Database class, so why map it again here?
    #            user input validation should be done when initializing the Database class. this allows to give appropriate feddback when something goes wrong
    #            try ..except is evil here. it swallows all kinds of errors. dont do this
    #            naming database types 2, 3, 4 on the fly is no good idea. i see this all over the code. better use some globally defined consts (see DATABASE_TYPE_*)
    #            i would like to drop this method entirely and replace it by get_selected_database() or better get_active_database(), returning one of our Database instances
    #            thus we can drop self.db_selected (holding database name) entirely and replace it with self._active_database = Database, avoiding to define the same
    #            thing multiple times
    def get_db_parameters(self):
        db: dict[str, Any] = {}
        name = self.db_selected

        if name not in self.supported_databases:
            log.error(f"Database {name} not found in supported databases.")
            return db

        # Parameters are retrieved with default values
        db["db-databaseName"] = name

        # use getattr
        db["db-desc"] = getattr(self.supported_databases[name], "db_desc", None)
        db["db-host"] = getattr(self.supported_databases[name], "db_ip", None)
        db["db-port"] = getattr(self.supported_databases[name], "db_port", None)
        db["db-user"] = getattr(self.supported_databases[name], "db_user", None)
        db["db-password"] = getattr(self.supported_databases[name], "db_pass", None)
        db["db-server"] = getattr(self.supported_databases[name], "db_server", None)
        db["db-path"] = getattr(self.supported_databases[name], "db_path", None)

        # add backend
        try:
            db["db-backend"] = self.get_backend(self.supported_databases[name].db_server)
        except (AttributeError, KeyError) as e:
            log.exception(f"Error retrieving backend for {name}: {e!s}")
            db["db-backend"] = None

        return db

    @staticmethod
    def _write_db_attributes(db_node, **values: str | None) -> None:
        """Put on the node every attribute that was actually given.

        None means "leave whatever is there alone", which is not the same as
        the empty string: an empty db_pass is a password that was cleared.
        """
        for name, value in values.items():
            if value is not None:
                db_node.setAttribute(name, value)

    def _write_db_cache(self, db_name: str, *, selected: bool, **values: str | None) -> None:
        """Mirror onto the loaded Database what was just written to the file."""
        database = self.supported_databases[db_name]
        for name, value in values.items():
            if value is not None:
                setattr(database, name, value)
        database.db_selected = selected

    def _mark_db_default(self, db_node, db_name: str, *, wanted: bool) -> None:
        """Carry the default flag on the node, and off every other database.

        The attribute names the one database fpdb opens, so at most one node
        may hold it. A file naming two leaves the choice to whichever comes
        last in the document, which is not a choice anyone made.
        """
        if wanted:
            db_node.setAttribute("default", "True")
            for dbn in self.doc.getElementsByTagName("database"):
                if dbn.getAttribute("db_name") != db_name and dbn.hasAttribute("default"):
                    dbn.removeAttribute("default")
        elif db_node.hasAttribute("default"):
            db_node.removeAttribute("default")

    def set_db_parameters(
        self,
        db_name="fpdb",
        db_ip=None,
        db_port=None,
        db_user=None,
        db_pass=None,
        db_desc=None,
        db_server=None,
        default="False",
    ) -> None:
        db_node = self.get_db_node(db_name)
        defaultb = string_to_bool(default.lower(), False)
        if db_node is not None:
            self._write_db_attributes(
                db_node,
                db_desc=db_desc,
                db_ip=db_ip,
                db_port=db_port,
                db_user=db_user,
                db_pass=db_pass,
                db_server=db_server,
            )
            self._mark_db_default(db_node, db_name, wanted=defaultb or self.db_selected == db_name)
        if db_name in self.supported_databases:
            self._write_db_cache(
                db_name,
                selected=defaultb,
                db_desc=db_desc,
                db_ip=db_ip,
                db_port=db_port,
                db_user=db_user,
                db_pass=db_pass,
                db_server=db_server,
            )
        if defaultb:
            self.db_selected = db_name

    def add_db_parameters(
        self,
        db_name="fpdb",
        db_ip=None,
        db_port=None,
        db_user=None,
        db_pass=None,
        db_desc=None,
        db_server=None,
        default="False",
    ) -> None:
        defaultb = string_to_bool(default.lower(), False)
        if db_name in self.supported_databases:
            msg = "Database names must be unique"
            raise ValueError(msg)

        db_node = self.get_db_node(db_name)
        if db_node is None:
            db_node = self._append_db_node(db_name)
            wanted = defaultb
        else:
            # The node is in the file but never reached supported_databases,
            # which happens when a <supported_databases> section and a
            # top-level <database> both exist: only the section is loaded.
            # Such a node may already be the selection, which keeps the flag.
            wanted = defaultb or self.db_selected == db_name

        self._write_db_attributes(
            db_node,
            db_desc=db_desc,
            db_ip=db_ip,
            db_port=db_port,
            db_user=db_user,
            db_pass=db_pass,
            db_server=db_server,
        )
        self._mark_db_default(db_node, db_name, wanted=wanted)

        # The name is known not to be in supported_databases: the guard above
        # raises when it is, and nothing since has touched the dictionary.
        db = Database(node=db_node)
        self.supported_databases[db.db_name] = db

        if defaultb:
            self.db_selected = db_name

    def _append_db_node(self, db_name: str):
        """Add an empty <database> where this file already keeps its databases.

        Most files hold them in a <supported_databases> section, but the format
        also allows them at the top level, and reading a file falls back to
        those when the section yields nothing. Giving such a file a section to
        put the new database in would hide the ones it already has, since the
        section wins the moment it holds anything -- so the new node joins the
        others where they are.
        """
        parent = None
        for candidate in self.doc.getElementsByTagName("supported_databases"):
            # should only be one supported_databases element, use last one if there are several
            parent = candidate
        if parent is None:
            parent = self.doc.documentElement
        parent.appendChild(self.doc.createTextNode("    "))
        db_node = self.doc.createElement("database")
        parent.appendChild(db_node)
        parent.appendChild(self.doc.createTextNode("\r\n    "))
        db_node.setAttribute("db_name", db_name)
        return db_node

    def del_db_parameters(self, db_name="fpdb") -> None:
        """Remove a database from the config (both the XML node and the cache).

        If the removed database was the selected one, another configured
        database (if any) becomes the selection.
        """
        db_node = self.get_db_node(db_name)
        if db_node is not None and db_node.parentNode is not None:
            db_node.parentNode.removeChild(db_node)
        self.supported_databases.pop(db_name, None)
        if self.db_selected == db_name:
            self.db_selected = next(iter(self.supported_databases), None)

    def get_backend(self, name):
        """Returns the number of the currently used backend."""
        # Map received character strings to expected constants
        name_mapping = {
            "sqlite": "DATABASE_TYPE_SQLITE",
            "mysql": "DATABASE_TYPE_MYSQL",
            "postgresql": "DATABASE_TYPE_POSTGRESQL",
        }

        # Convert the name to uppercase using mapping
        if name in name_mapping:
            name = name_mapping[name]
        else:
            msg = f"Unsupported database backend: {name}"
            raise ValueError(msg)

        # Use of expected constants
        backends = {
            "DATABASE_TYPE_MYSQL": 2,
            "DATABASE_TYPE_POSTGRESQL": 3,
            "DATABASE_TYPE_SQLITE": 4,
        }

        return backends[name]
