"""A PT4 HUD as an .fpdbhud package, listing what does not translate (#614).

The package is the translated stat-set plus an ``<untranslated>`` list; it has
to re-import like any other package and be readable by the HUD presentation
reader. Configurations here are throwaway copies of the shipped example.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import defusedxml.minidom
import pytest

from fpdb_3_legacy import pt4hud
from fpdb_3_legacy.hud_package import install_missing_hud_package
from fpdb_3_legacy.hud_presentation import describe_package

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "test" / "fixtures" / "generationpoker_3h.pt4hud"
EXAMPLE = ROOT / "HUD_config.xml.example"


@pytest.fixture
def package(tmp_path):
    xml, summary = pt4hud.to_package(str(FIXTURE))
    path = tmp_path / "layout.fpdbhud"
    path.write_text(xml, encoding="utf-8")
    return path, summary


@pytest.fixture
def config_copy(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(EXAMPLE))
    path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, path)
    return configuration, path


def test_the_package_holds_the_translated_stat_set(package) -> None:
    path, summary = package
    root = defusedxml.minidom.parse(str(path)).documentElement

    assert root.tagName == "fpdb_hud_package"
    assert root.getAttribute("version") == "1.0"
    (stat_set,) = root.getElementsByTagName("ss")
    assert stat_set.getAttribute("name") == summary["name"]
    assert len(stat_set.getElementsByTagName("stat")) == summary["stats"] == 30
    assert len(stat_set.getElementsByTagName("block")) == summary["blocks"] > 1
    assert {s.getAttribute("popup") for s in stat_set.getElementsByTagName("stat")} == {"default"}


def test_every_untranslated_pt4_stat_is_listed_in_the_package(package) -> None:
    path, summary = package
    root = defusedxml.minidom.parse(str(path)).documentElement

    (listing,) = root.getElementsByTagName("untranslated")
    listed = listing.getElementsByTagName("pt4_stat")
    assert listing.getAttribute("count") == str(len(listed)) == "2"
    assert len(summary["untranslated"]) == 2
    for node in listed:
        assert node.getAttribute("section") == "Villain Info 3H"
        assert node.getAttribute("pt4_name").startswith("sum(if[tourney_hand_player_statistics")
        assert not node.hasAttribute("formula")  # a formula stat's name is its formula, said once


def test_only_stats_are_reported_as_untranslated_not_labels_or_lines() -> None:
    layout = pt4hud.parse(str(FIXTURE))

    missing = pt4hud.untranslated(layout)

    stat_cells = [c for c in layout.cells if c.kind == "stat"]
    assert len(missing) == sum(1 for c in stat_cells if not c.fpdb_stat)
    assert len(missing) < len(layout.unsupported)  # unsupported also counts text labels and lines


def test_what_the_package_leaves_out_is_named(package) -> None:
    _path, summary = package

    assert summary["left_out"] == ["Push Nash", "Call Nash", "DEF Explain"]


def test_the_package_re_imports_into_a_configuration(package, config_copy) -> None:
    path, summary = package
    configuration, config_path = config_copy
    config = configuration.Config(file=str(config_path))
    assert summary["name"] not in config.stat_sets

    root = defusedxml.minidom.parse(str(path)).documentElement
    assert install_missing_hud_package(config.doc, root)
    config.save()

    reloaded = configuration.Config(file=str(config_path))
    assert summary["name"] in reloaded.stat_sets
    assert not reloaded.wrongConfigVersion


def test_the_hud_presentation_reader_reads_the_package(package) -> None:
    path, summary = package

    described = describe_package(path)

    assert len(described.panels) == summary["blocks"]


def test_the_import_reports_the_untranslated_stats_too(config_copy) -> None:
    configuration, config_path = config_copy
    config = configuration.Config(file=str(config_path))

    summary = pt4hud.import_to_config(str(FIXTURE), config)

    assert summary["untranslated"] == pt4hud.untranslated(pt4hud.parse(str(FIXTURE)))


def test_the_command_line_writes_a_package(tmp_path, capsys) -> None:
    out = tmp_path / "cli.fpdbhud"

    assert pt4hud.main([str(FIXTURE), "--package", str(out)]) == 0

    assert defusedxml.minidom.parse(str(out)).documentElement.tagName == "fpdb_hud_package"
    printed = capsys.readouterr().out
    assert "30 stats" in printed
    assert printed.count("untranslated [Villain Info 3H]") == 2
