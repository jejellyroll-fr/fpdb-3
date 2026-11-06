"""The configuration side of local-first sync (#680): which database each caller gets."""

from __future__ import annotations

from unittest.mock import MagicMock


def _config_with_node(attrs: dict):
    from fpdb_3_legacy.config_databases import ConfigDatabasesMixin
    from fpdb_3_legacy.config_databases import Database as DbNode

    node = MagicMock()
    node.getAttribute.side_effect = lambda name, default=None: attrs.get(name, default)
    db_node = DbNode.__new__(DbNode)
    DbNode.__init__(db_node, node)
    host = ConfigDatabasesMixin.__new__(ConfigDatabasesMixin)
    host.supported_databases = {"srv": db_node}
    host.db_selected = "srv"
    host.get_backend = lambda server: {"sqlite": 4, "postgresql": 3, "mysql": 2}[server]
    return host


def test_local_first_switch_returns_local_params_and_keeps_server_params() -> None:
    host = _config_with_node(
        {
            "db_name": "srv",
            "db_server": "postgresql",
            "db_ip": "lan-server",
            "db_port": "5432",
            "db_user": "fpdb",
            "db_pass": "secret",
            "db_path": "",
            "default": "true",
            "local_first": "1",
            "local_path": "C:/fpdb/local.sqlite3",
        }
    )
    params = host.get_db_parameters()
    assert params["db-local-first"] == "1"
    assert params["db-server"] == "sqlite"
    assert params["db-backend"] == 4
    assert params["db-databaseName"] == "C:/fpdb/local.sqlite3"

    server = host.get_server_db_parameters()
    assert server["db-server"] == "postgresql"
    assert server["db-host"] == "lan-server"
    assert server["db-password"] == "secret"


_FULL_NODE_ATTRS = {
    "db_name": "srv",
    "db_server": "postgresql",
    "db_ip": "lan-server",
    "db_port": "5432",
    "db_user": "fpdb",
    "db_pass": "secret",
    "db_path": "",
    "default": "true",
}


def test_server_params_with_unknown_selected_db_return_empty() -> None:
    host = _config_with_node(dict(_FULL_NODE_ATTRS))
    host.db_selected = "missing"
    assert not host.get_server_db_parameters()


def test_server_params_with_unsupported_backend_yield_none_backend() -> None:
    attrs = dict(_FULL_NODE_ATTRS, db_server="oracle")
    host = _config_with_node(attrs)

    def _boom(server):
        raise KeyError(server)  # get_backend raises KeyError for unknown servers

    host.get_backend = _boom
    params = host.get_server_db_parameters()
    assert params["db-server"] == "oracle"
    assert params["db-backend"] is None


def test_local_first_off_by_default() -> None:
    host = _config_with_node(
        {
            "db_name": "srv",
            "db_server": "postgresql",
            "db_ip": "lan-server",
            "db_port": "5432",
            "db_user": "fpdb",
            "db_pass": "secret",
            "default": "true",
        }
    )
    params = host.get_db_parameters()
    assert params["db-local-first"] == "0"
    assert params["db-server"] == "postgresql"


def test_hand_batch_interval_ms_is_parsed_from_xml(tmp_path) -> None:  # pylint: disable=unused-argument
    """The XML attribute must reach get_hud_ui_parameters, not just mocks (#680 P1)."""
    import defusedxml.minidom

    from fpdb_3_legacy.config_hud_ui import ConfigHudUiMixin, HudUI

    xml = (
        '<FreePokerToolsConfig><general version="87"/>'
        '<hud_ui label="m" hand_batch_interval_ms="350"/></FreePokerToolsConfig>'
    )
    doc = defusedxml.minidom.parseString(xml)
    host = ConfigHudUiMixin.__new__(ConfigHudUiMixin)
    host.ui = HudUI(node=doc.getElementsByTagName("hud_ui")[0])
    assert host.get_hud_ui_parameters()["hand_batch_interval_ms"] == 350
