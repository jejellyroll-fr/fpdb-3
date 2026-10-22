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
    assert listing.getAttribute("count") == str(len(listed)) == str(len(summary["untranslated"])) == "19"
    built_in = [n for n in listed if not n.getAttribute("pt4_name").startswith("sum(")]
    formulas = [n for n in listed if n.getAttribute("pt4_name").startswith("sum(")]
    # Seventeen built-in PT4 stats fpdb has no equivalent for, each with its panel and column label...
    assert len(built_in) == 17
    assert {n.getAttribute("section") for n in built_in} == {"SB 3h", "BB 3h", "BU 3h"}
    assert ("BU 3h", "T FvPROBE", "Fold to T Probe Bet") in {
        (n.getAttribute("section"), n.getAttribute("label"), n.getAttribute("pt4_name")) for n in built_in
    }
    # ... and the two custom formulas, whose name is their formula, said once.
    assert len(formulas) == 2
    assert all(n.getAttribute("section") == "Villain Info 3H" and not n.hasAttribute("formula") for n in formulas)


def test_a_built_in_stat_without_an_fpdb_equivalent_is_reported_not_blanked_silently(monkeypatch) -> None:
    """PT4 stats missing from PT4_TO_FPDB used to become anonymous blank cells, absent from every report."""
    monkeypatch.delitem(pt4hud.PT4_TO_FPDB, "PFR")
    layout = pt4hud.parse(str(FIXTURE))

    missing = [s for s in pt4hud.untranslated(layout) if s["pt4_name"] == "PFR"]

    assert missing
    assert all(s["section"] for s in missing)
    _xml, summary = pt4hud.to_package(str(FIXTURE))
    assert summary["stats"] == 30 - len(missing)  # the rest still translates


def test_an_untranslated_stat_keeps_its_slot_in_the_hud(monkeypatch) -> None:
    """The stat-set draws a blank cell where the untranslated stat was, so the grid does not shift."""
    with_pfr, _ = pt4hud.to_package(str(FIXTURE))
    monkeypatch.delitem(pt4hud.PT4_TO_FPDB, "PFR")
    without_pfr, _ = pt4hud.to_package(str(FIXTURE))

    def slots(xml: str) -> list[str]:
        (stat_set,) = defusedxml.minidom.parseString(xml).getElementsByTagName("ss")
        return sorted(
            f"{block.getAttribute('id')}{node.getAttribute('_rowcol')}"
            for block in stat_set.getElementsByTagName("block")
            for node in block.childNodes
            if node.nodeType == node.ELEMENT_NODE
        )

    assert slots(with_pfr) == slots(without_pfr)


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


def test_the_untranslated_list_reads_back_from_the_package(package) -> None:
    path, summary = package
    root = defusedxml.minidom.parse(str(path)).documentElement

    assert pt4hud.package_untranslated(root) == summary["untranslated"]


def test_a_package_not_converted_from_pt4_lists_nothing() -> None:
    root = defusedxml.minidom.parseString('<fpdb_hud_package version="1.0"><ss name="mine"/></fpdb_hud_package>')

    assert pt4hud.package_untranslated(root.documentElement) == []
