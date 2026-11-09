"""ConfigurationManager must see and adopt HUD profile edits (#741).

The HUD preferences dialog writes <ss>/<pu>/<hud_profile_rules> sections.
Before the fix, _identify_changes never compared them, so reload_config()
returned "No changes detected" without reloading, the manager kept a stale
DOM, and the next save from that DOM wiped the profile edit off the disk.
"""

from __future__ import annotations

import os
import shutil

import pytest

from fpdb_3_legacy import Configuration as Conf
from fpdb_3_legacy.ConfigurationManager import ConfigurationManager
from fpdb_3_legacy.hud_profiles import HudProfileRule

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLE = os.path.join(ROOT, "HUD_config.xml.example")

pytestmark = pytest.mark.skipif(not os.path.exists(EXAMPLE), reason="example config missing")


@pytest.fixture
def manager(tmp_path):
    ConfigurationManager._instance = None
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    m = ConfigurationManager()
    m.initialize(str(cfg_path))
    yield m, cfg_path
    ConfigurationManager._instance = None


def _first_ss(doc):
    return doc.getElementsByTagName("ss")[0]


def test_a_stat_set_only_edit_is_detected_and_adopted(manager) -> None:
    m, cfg_path = manager
    before = _first_ss(m.get_config().doc).getAttribute("rows")
    edited = str(int(before) + 1)

    # The dialog edits its own Config and saves; the manager only sees the file.
    editor = Conf.Config(file=str(cfg_path))
    _first_ss(editor.doc).setAttribute("rows", edited)
    editor.save()

    success, message, _restart = m.reload_config()

    assert success
    assert "No changes detected" not in message
    assert _first_ss(m.get_config().doc).getAttribute("rows") == edited


def test_no_detected_change_still_follows_the_file(manager, monkeypatch) -> None:
    # Even when change detection is blind to the edit, the manager's live
    # config must not stay behind the file: a later save() from it would
    # otherwise write the stale DOM back over the edit.
    m, cfg_path = manager
    monkeypatch.setattr(m, "_identify_changes", lambda _old, _new: [])

    editor = Conf.Config(file=str(cfg_path))
    _first_ss(editor.doc).setAttribute("rows", "9")
    editor.save()

    success, message, _restart = m.reload_config()

    assert success
    assert message == "No changes detected"
    assert _first_ss(m.get_config().doc).getAttribute("rows") == "9"


def test_a_later_host_save_does_not_wipe_the_profile_edit(manager) -> None:
    m, cfg_path = manager

    editor = Conf.Config(file=str(cfg_path))
    _first_ss(editor.doc).setAttribute("rows", "7")
    editor.save()
    m.reload_config()

    # What fpdb.reload_config() hands back to the host process.
    host = m.get_config()
    assert _first_ss(host.doc).getAttribute("rows") == "7"

    # The host saves again (site preferences, import filters, ...) without
    # touching the stat sets; the profile edit must survive on disk.
    host.save()
    reread = Conf.Config(file=str(cfg_path))
    assert _first_ss(reread.doc).getAttribute("rows") == "7"


def test_identify_changes_covers_popups_and_profile_rules(manager) -> None:
    m, cfg_path = manager
    old = Conf.Config(file=str(cfg_path))
    new = Conf.Config(file=str(cfg_path))

    pu_nodes = new.doc.getElementsByTagName("pu")
    if pu_nodes:
        pu_nodes[0].setAttribute("pu_class", "changed_class")
    new.hud_profile_rules = [HudProfileRule.from_mapping({"profile": "SomeProfile", "site": "Winamax"}, 0)]

    paths = [c.path for c in m._identify_changes(old, new)]

    assert "hud_profile_rules" in paths
    if pu_nodes:
        assert any(p.startswith("popup_windows.") for p in paths)


def test_check_pending_changes_sees_stat_set_edits(manager) -> None:
    m, cfg_path = manager
    editor = Conf.Config(file=str(cfg_path))
    _first_ss(editor.doc).setAttribute("rows", "8")

    changes = m.detect_changes_from_saved_state(editor)

    assert any(c.path.startswith("stat_sets.") for c in changes)
