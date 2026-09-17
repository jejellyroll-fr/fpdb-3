"""Advanced positional and role-based popup packs (#299).

The acceptance criteria are checked in order: a complete default pack ships, the
hierarchy covers preflop, single-raised, 3-bet and river branches, IP/OOP and
position splits are visible, sample counts are shown, definitions are editable
without Python, and the classic popups keep working.

Two rules make the packs trustworthy rather than just present:

* **a pack can only name what exists** -- a stat the catalogue does not have, a
  popup class the HUD cannot resolve, or a submenu that points nowhere is a
  ``ValueError`` naming the field, so a pack that loads is a pack that renders;
* **installing is additive** -- an existing popup is never replaced, and
  re-installing a pack replaces its own popups rather than duplicating them.
"""

from __future__ import annotations

import json
import xml.dom.minidom as minidom
from pathlib import Path

import pytest

from fpdb_3_legacy import popup_packs as packs
from fpdb_3_legacy.Popup import resolve_popup_class

# The branches the issue names, as popup-name fragments the shipped library
# must reach from the root.
REQUIRED_BRANCHES = (
    "preflop",
    "preflop_rfi",
    "preflop_three_bet",
    "preflop_four_bet",
    "preflop_squeeze",
    "preflop_blind_defence",
    "srp_pfr_ip",
    "srp_pfr_oop",
    "srp_caller_flop",
    "srp_river",
    "threebet_pot_ip",
    "threebet_pot_oop",
    "threebet_pot_caller",
    "fourbet_pot_caller",
)


def _pack(**overrides) -> dict:
    """A minimal valid pack document, with fields overridden per test."""
    node = {"name": "pack_root", "entries": ["vpip", "pfr"]}
    data = {"name": "test_pack", "root": "pack_root", "nodes": [node]}
    data.update(overrides)
    return data


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "packs.json"
    path.write_text(json.dumps(payload))
    return path


# ---------------------------------------------------------------------------
# The shipped library.
# ---------------------------------------------------------------------------


class TestShippedLibrary:
    def test_the_default_packs_load(self) -> None:
        registry = packs.load_default_registry()
        assert registry.names() == ["analytics", "fourbet_pot", "preflop", "srp", "threebet_pot"]
        assert len(registry.all_nodes()) >= 25

    def test_every_popup_class_resolves_in_the_hud(self) -> None:
        # The list is data so loading a pack need not import Qt; this keeps it
        # honest in both directions.
        for name in packs.POPUP_CLASSES:
            assert resolve_popup_class(name) is not None, f"{name} is not resolvable"
        for name in ("default", "Submenu", "Multicol", "ModernSubmenu", "ModernSubmenuLight", "CategorizedPopup"):
            assert name in packs.POPUP_CLASSES

    def test_the_root_reaches_every_branch(self) -> None:
        registry = packs.load_default_registry()
        root = registry.get("analytics")
        reached = set()
        frontier = [root.root]
        by_name = {node.name: node for node in registry.all_nodes()}
        while frontier:
            current = frontier.pop()
            if current in reached:
                continue
            reached.add(current)
            frontier.extend(by_name[current].submenus() if current in by_name else [])
        missing = [branch for branch in REQUIRED_BRANCHES if branch not in reached]
        assert missing == []

    def test_the_library_uses_real_stats_only(self) -> None:
        registry = packs.load_default_registry()
        known = packs.known_stats()
        for node in registry.all_nodes():
            for stat in node.stats():
                assert stat in known, f"{node.name} names unknown stat {stat}"

    def test_frequency_popups_require_their_sample(self) -> None:
        # Every node that declares require_sample loaded, which means every
        # rate in it can show a denominator; only the name/sample-free rows
        # (playername, n) are allowed to lack one.
        registry = packs.load_default_registry()
        warnings = registry.validate()
        assert all("playername" in warning for warning in warnings)

    def test_splits_are_visible_where_the_issue_asks(self) -> None:
        registry = packs.load_default_registry()
        by_name = {node.name: node for node in registry.all_nodes()}
        three_bet_labels = [entry.display_text for entry in by_name["preflop_three_bet"].entries]
        assert "3-bet BTN" in three_bet_labels  # a position split
        assert "3-bet BB" in three_bet_labels
        srp_labels = [entry.display_text for entry in by_name["srp"].entries]
        assert "PFR in position" in srp_labels and "PFR out of position" in srp_labels
        threebet_labels = [entry.display_text for entry in by_name["threebet_pot"].entries]
        assert "Aggressor's streets" in threebet_labels and "Caller's streets" in threebet_labels

    def test_the_packs_are_editable_data(self) -> None:
        # A pack is a JSON file: no Python, no SQL, no widget tree.
        for path in sorted(packs.default_packs_dir().glob("*.json")):
            document = json.loads(path.read_text())
            assert document["schema_version"] == packs.POPUP_PACK_SCHEMA_VERSION
            assert document["packs"]

    def test_an_extra_directory_adds_to_the_library(self, tmp_path: Path) -> None:
        node = {"name": "mine_root", "entries": ["vpip"]}
        _write(tmp_path, {"name": "mine", "root": "mine_root", "nodes": [node]})
        registry = packs.load_default_registry([tmp_path])
        assert "mine" in registry.names()
        assert "preflop" in registry.names()
        assert registry.sources["mine"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------


class TestValidation:
    def test_a_pack_parses_into_nodes_and_a_root(self) -> None:
        pack = packs.parse_pack(_pack())
        assert pack.name == "test_pack" and pack.root == "pack_root"
        assert pack.node("pack_root").stats() == ("vpip", "pfr")

    def test_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown field"):
            packs.parse_pack(_pack(colour="red"))

    def test_an_unknown_stat_is_refused_with_the_name(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {"packs": [_pack(nodes=[{"name": "r", "entries": ["vpip", "not_a_stat"]}], root="r")]})
        with pytest.raises(ValueError, match="unknown stat 'not_a_stat'"):
            packs.load_packs(path)

    def test_an_unknown_popup_class_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown class 'FancyPopup'"):
            packs.parse_pack(_pack(nodes=[{"name": "r", "class": "FancyPopup", "entries": ["vpip"]}], root="r"))

    def test_a_dangling_submenu_is_refused(self) -> None:
        nodes = [{"name": "r", "entries": [{"stat": "More", "submenu": "nowhere"}]}]
        with pytest.raises(ValueError, match="submenu 'nowhere'"):
            packs.parse_pack(_pack(nodes=nodes, root="r"))

    def test_a_submenu_may_point_at_a_configured_popup(self) -> None:
        nodes = [{"name": "r", "entries": [{"stat": "Classic", "submenu": "hold_pre"}]}]
        pack = packs.parse_pack(_pack(nodes=nodes, root="r"), known_popups=["hold_pre"])
        assert pack.node("r").submenus() == ("hold_pre",)

    def test_a_cycle_is_refused(self) -> None:
        nodes = [
            {"name": "a", "entries": [{"stat": "b", "submenu": "b"}]},
            {"name": "b", "entries": [{"stat": "a", "submenu": "a"}]},
        ]
        with pytest.raises(ValueError, match="Submenu cycle"):
            packs.parse_pack(_pack(nodes=nodes, root="a"))

    def test_a_duplicate_popup_is_refused(self) -> None:
        nodes = [{"name": "a", "entries": ["vpip"]}, {"name": "a", "entries": ["pfr"]}]
        with pytest.raises(ValueError, match="Duplicate popup 'a'"):
            packs.parse_pack(_pack(nodes=nodes, root="a"))

    def test_a_missing_root_is_refused(self) -> None:
        with pytest.raises(ValueError, match="root 'nope' is not one of its popups"):
            packs.parse_pack(_pack(root="nope"))

    def test_an_entry_needs_a_stat(self) -> None:
        with pytest.raises(ValueError, match="needs a stat name"):
            packs.parse_pack(_pack(nodes=[{"name": "r", "entries": [{"label": "x"}]}], root="r"))

    def test_an_unknown_param_is_refused(self) -> None:
        nodes = [{"name": "r", "entries": ["vpip"], "params": {"colour": "red"}}]
        with pytest.raises(ValueError, match="unknown param"):
            packs.parse_pack(_pack(nodes=nodes, root="r"))

    def test_a_known_param_is_kept(self) -> None:
        node = packs.parse_pack(_pack(nodes=[{"name": "r", "entries": ["vpip"], "params": {"width": "520"}}], root="r")).node("r")
        assert node.params == {"width": "520"}

    def test_a_popup_needs_entries(self) -> None:
        with pytest.raises(ValueError, match="needs at least one entry"):
            packs.parse_pack(_pack(nodes=[{"name": "r", "entries": []}], root="r"))

    def test_a_future_schema_is_refused(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {"schema_version": packs.POPUP_PACK_SCHEMA_VERSION + 1, "packs": []})
        with pytest.raises(ValueError, match="newer than"):
            packs.load_packs(path)

    def test_a_node_requiring_a_sample_refuses_a_stat_without_one(self) -> None:
        # ``playername`` is a name, not a rate: it has no sample column at all.
        nodes = [{"name": "r", "entries": ["vpip", "playername"], "require_sample": True}]
        with pytest.raises(ValueError, match="requires a sample"):
            packs.parse_pack(_pack(nodes=nodes, root="r"))

    def test_a_node_requiring_a_sample_refuses_a_descriptor_without_one(self) -> None:
        nodes = [{"name": "r", "entries": ["vpip", "chipev_tourney"], "require_sample": True}]
        with pytest.raises(ValueError, match="needs a 'sample' expression"):
            packs.parse_pack(_pack(nodes=nodes, root="r"))

    def test_a_node_requiring_a_sample_accepts_one_that_has_it(self) -> None:
        nodes = [{"name": "r", "entries": ["vpip", "cb1"], "require_sample": True}]
        assert packs.parse_pack(_pack(nodes=nodes, root="r")).node("r").require_sample is True

    def test_a_pack_round_trips_through_save_and_load(self, tmp_path: Path) -> None:
        original = packs.parse_pack(_pack())
        path = packs.PackRegistry().save(original, tmp_path / "saved.json")
        loaded = packs.load_packs(path)
        assert len(loaded) == 1
        # ``source`` records the file it came from, so it is the one field that
        # legitimately changes across the trip.
        assert loaded[0].nodes["pack_root"].as_dict() == original.nodes["pack_root"].as_dict()
        assert (loaded[0].name, loaded[0].root) == (original.name, original.root)
        assert loaded[0].source == str(path)

    def test_saving_refuses_what_loading_would(self, tmp_path: Path) -> None:
        bad = packs.parse_pack(_pack(nodes=[{"name": "r", "entries": ["vpip"]}], root="r"))
        broken = packs.PopupPack(name="bad", nodes={"r": packs.PopupNode(name="r", entries=(packs.PopupEntry("nope"),))}, root="r")
        with pytest.raises(ValueError, match="unknown stat 'nope'"):
            packs.PackRegistry().save(broken, tmp_path / "bad.json")
        # The valid one still writes, so the refusal was about the file, not the API.
        assert packs.PackRegistry().save(bad, tmp_path / "ok.json").exists()


# ---------------------------------------------------------------------------
# Compiling a pack into the configuration's popup type.
# ---------------------------------------------------------------------------


class TestCompilation:
    def test_a_node_compiles_to_the_config_popup_the_hud_reads(self) -> None:
        node = packs.parse_pack(
            _pack(
                nodes=[
                    {
                        "name": "compiled",
                        "class": "ModernSubmenu",
                        "title": "{player}",
                        "entries": [
                            {"stat": "vpip", "label": "VPIP", "category": "Preflop", "color": "#00E59B"},
                            {"stat": "More", "submenu": "other"},
                        ],
                        "params": {"theme": "classic"},
                    },
                    {"name": "other", "entries": ["pfr"]},
                ],
                root="compiled",
            ),
        ).node("compiled")
        popup = node.to_config_popup()
        assert popup.name == "compiled"
        assert popup.pu_class == "ModernSubmenu"
        assert popup.pu_stats == ["vpip", "More"]
        assert popup.pu_stats_label == ["VPIP", ""]
        assert popup.pu_stats_category == ["Preflop", ""]
        assert popup.pu_stats_color == ["#00E59B", ""]
        assert popup.pu_stats_submenu == [("vpip", ""), ("More", "other")]
        assert popup.pu_class_params == {"theme": "classic", "title": "{player}"}

    def test_the_compiled_popup_is_the_configuration_type(self) -> None:
        from fpdb_3_legacy.Configuration import Popup as ConfigPopup

        popup = packs.parse_pack(_pack()).node("pack_root").to_config_popup()
        assert isinstance(popup, ConfigPopup)

    def test_the_exported_xml_parses_back_into_the_same_popup(self) -> None:
        node = packs.parse_pack(_pack()).node("pack_root")
        reparsed = minidom.parseString(node.to_xml()).documentElement
        from fpdb_3_legacy.Configuration import Popup as ConfigPopup

        assert ConfigPopup(reparsed).pu_stats == ["vpip", "pfr"]

    def test_a_submenu_entry_keeps_its_row_text(self) -> None:
        node = packs.parse_pack(
            _pack(nodes=[{"name": "r", "entries": [{"stat": "RFI by position", "submenu": "s"}]}, {"name": "s", "entries": ["vpip"]}], root="r"),
        ).node("r")
        popup = node.to_config_popup()
        # The row text lives in ``pu_stat_name``, exactly as in HUD_config.xml.
        assert popup.pu_stats == ["RFI by position"]
        assert popup.pu_stats_submenu == [("RFI by position", "s")]
        assert node.entries[0].display_text == "RFI by position"


# ---------------------------------------------------------------------------
# Installing into a configuration.
# ---------------------------------------------------------------------------


class FakeConfig:
    """The two attributes ``install_packs`` touches."""

    def __init__(self, popups: dict | None = None) -> None:
        self.popup_windows = dict(popups or {})


class FakePopup:
    def __init__(self, name: str) -> None:
        self.name = name
        self.pu_stats: list[str] = ["vpip"]
        self.pu_stats_category: list[str] = [""]
        self.pu_stats_label: list[str] = [""]
        self.pu_stats_color: list[str] = [""]
        self.pu_stats_submenu: list[tuple[str, str]] = [("vpip", "")]


class TestInstall:
    def test_installing_is_additive(self) -> None:
        config = FakeConfig({"classic": FakePopup("classic")})
        report = packs.install_packs(config, [packs.parse_pack(_pack())])
        assert report.installed == ["pack_root"]
        assert config.popup_windows["classic"].pu_stats == ["vpip"]
        assert config.popup_windows["pack_root"].pu_stats == ["vpip", "pfr"]

    def test_an_existing_popup_is_never_replaced(self) -> None:
        config = FakeConfig({"pack_root": FakePopup("pack_root")})
        report = packs.install_packs(config, [packs.parse_pack(_pack())])
        assert report.skipped == ["pack_root"]
        assert config.popup_windows["pack_root"].pu_stats == ["vpip"]

    def test_overwrite_is_opt_in(self) -> None:
        config = FakeConfig({"pack_root": FakePopup("pack_root")})
        report = packs.install_packs(config, [packs.parse_pack(_pack())], overwrite=True)
        assert report.replaced == ["pack_root"]
        assert config.popup_windows["pack_root"].pu_stats == ["vpip", "pfr"]

    def test_reinstalling_a_pack_replaces_its_own_popups(self) -> None:
        config = FakeConfig()
        packs.install_packs(config, [packs.parse_pack(_pack())])
        report = packs.install_packs(config, [packs.parse_pack(_pack())])
        assert report.installed == []
        assert report.replaced == ["pack_root"]
        assert config.pack_popups["pack_root"] == "test_pack"

    def test_a_cross_pack_submenu_resolves_at_install(self) -> None:
        # A link to another pack's popup can only be checked against the names
        # that pack declares, which is what load_directory passes.
        root = packs.parse_pack(
            _pack(nodes=[{"name": "pack_root", "entries": [{"stat": "Other", "submenu": "other_root"}]}]),
            known_popups=["other_root"],
        )
        other = packs.parse_pack({"name": "other_pack", "root": "other_root", "nodes": [{"name": "other_root", "entries": ["pfr"]}]})
        config = FakeConfig()
        report = packs.install_packs(config, [root, other])
        assert report.installed == ["pack_root", "other_root"]
        assert config.popup_windows["pack_root"].pu_stats_submenu == [("Other", "other_root")]

    def test_linking_a_pack_into_an_existing_popup_is_one_row(self) -> None:
        config = FakeConfig({"holdring_modern": FakePopup("holdring_modern")})
        pack = packs.parse_pack(_pack())
        packs.install_packs(config, [pack])
        packs.link_pack(config, "holdring_modern", pack, label="Analytics")
        popup = config.popup_windows["holdring_modern"]
        assert popup.pu_stats_submenu[-1] == ("Analytics", "pack_root")
        # Idempotent: linking twice does not add the row twice.
        packs.link_pack(config, "holdring_modern", pack, label="Analytics")
        assert len(popup.pu_stats) == 2

    def test_linking_refuses_a_popup_that_does_not_exist(self) -> None:
        pack = packs.parse_pack(_pack())
        config = FakeConfig()
        packs.install_packs(config, [pack])
        with pytest.raises(ValueError, match="no such popup"):
            packs.link_pack(config, "nowhere", pack)

    def test_linking_refuses_an_uninstalled_pack(self) -> None:
        config = FakeConfig({"holdring_modern": FakePopup("holdring_modern")})
        with pytest.raises(ValueError, match="not installed"):
            packs.link_pack(config, "holdring_modern", packs.parse_pack(_pack()))


# ---------------------------------------------------------------------------
# The configuration integration: shipped packs plus classic popups.
# ---------------------------------------------------------------------------


class TestConfigurationIntegration:
    @pytest.fixture(scope="class")
    def config(self):
        from fpdb_3_legacy.Configuration import Config

        return Config(file="HUD_config.xml")

    def test_the_packs_arrive_with_the_configuration(self, config) -> None:
        assert "preflop" in config.popup_windows
        assert "analytics" in config.popup_windows
        assert config.pack_popups["preflop"] == "preflop"

    def test_the_classic_popups_are_untouched(self, config) -> None:
        # Every popup HUD_config.xml defines keeps its own definition: no pack
        # owns it, and its rows are exactly what the file says.
        for name in ("default", "hold_pre", "hold_flop", "holdring_modern", "aof_profile"):
            assert name in config.popup_windows
            assert config.pack_popups.get(name, "") == ""
            assert config.popup_windows[name].pu_stats
        assert config.popup_windows["default"].pu_class == "Multicol"
        assert len(config.popup_windows) == len(config.pack_popups) + 45 == 73

    def test_installing_again_is_idempotent(self, config) -> None:
        before = sorted(config.popup_windows)
        config.install_popup_packs()
        assert sorted(config.popup_windows) == before

    def test_a_pack_popup_is_reachable_from_the_root(self, config) -> None:
        root = config.popup_windows["analytics"]
        targets = [submenu for _label, submenu in root.pu_stats_submenu]
        assert "preflop" in targets and "srp" in targets


# ---------------------------------------------------------------------------
# Sample sizes.
# ---------------------------------------------------------------------------


class TestSamples:
    def test_a_descriptor_can_declare_its_sample(self) -> None:
        from fpdb_3_legacy import stat_registry

        descriptor = stat_registry.get_registry().get("vpip")
        assert descriptor is not None
        raw = {"street0VPI": 150, "street0VPIChance": 1200}
        assert descriptor.format_sample(descriptor.compute_sample(raw)) == "(1200)"

    def test_the_hud_tuple_carries_the_sample_not_the_expression(self) -> None:
        from fpdb_3_legacy.stat_adapters import HudAdapter
        from fpdb_3_legacy.stat_registry import get_registry

        descriptor = get_registry().get("vpip")
        stats = {"street0VPI": 150, "street0VPIChance": 1200, "n": 1200}
        result = HudAdapter().stat_tuple(descriptor, stats)
        assert result[4] == "(1200)"
        assert descriptor.value not in result[4]
        assert result[1] == "12.5"

    def test_a_descriptor_without_a_sample_reports_none(self) -> None:
        from fpdb_3_legacy.stat_registry import get_registry

        descriptor = get_registry().get("chipev_tourney")
        assert descriptor.format_sample() == ""
        assert packs.sample_for("chipev_tourney") == ""

    def test_a_descriptor_sample_must_use_declared_inputs(self) -> None:
        from fpdb_3_legacy.stat_registry import StatDescriptorError, build_descriptor

        with pytest.raises(StatDescriptorError, match="unknown name 'c'"):
            build_descriptor(
                {
                    "name": "bad",
                    "inputs": ["a", "b"],
                    "value": "100 * a / b",
                    "sample": "c",
                },
            )

    def test_a_native_stat_reports_the_sample_column_it_has(self) -> None:
        assert packs.sample_for("vpip")  # the catalogue's "(done/chances)"
        assert packs.has_sample("cb1")
        assert not packs.has_sample("playername")

    def test_the_pack_formatting_shows_samples(self) -> None:
        pack = packs.get_registry().get("preflop")
        rendered = packs.format_pack(pack, with_samples=True)
        assert "[(-/-)]" in rendered  # a native frequency's sample column
        assert "[(3, 4)]" not in rendered
        plain = packs.format_pack(pack, with_samples=False)
        assert "[-" not in plain


# ---------------------------------------------------------------------------
# The modern popup renders the hierarchy.
# ---------------------------------------------------------------------------


def _renderer(pop, theme_name: str = "hud_dark"):
    """A ``CategorizedPopup`` with just enough state to render, without Qt."""
    from fpdb_3_legacy.ModernPopup import CategorizedPopup
    from fpdb_3_legacy.PopupThemes import get_theme

    renderer = CategorizedPopup.__new__(CategorizedPopup)
    renderer.pop = pop
    renderer.theme = get_theme(theme_name)
    renderer.stat_dict = {7: {"seat": 3, "screen_name": "Anna"}}
    renderer.hand_instance = None
    renderer.submenu_count = 0
    return renderer


class TestModernPopupRendering:
    def _popup(self):
        from fpdb_3_legacy.Configuration import Popup as ConfigPopup

        node = packs.parse_pack(
            _pack(
                nodes=[
                    {"name": "r", "entries": [{"stat": "vpip"}, {"stat": "Read more", "submenu": "s"}]},
                    {"name": "s", "entries": ["pfr"]},
                ],
                root="r",
            ),
        ).node("r")
        return ConfigPopup(minidom.parseString(node.to_xml()).documentElement)

    def test_a_navigation_row_shows_a_chevron_and_its_row_text(self) -> None:
        rows = _renderer(self._popup())._stat_rows(7)
        navigation = [row for row in rows if row[5] == "s"]
        assert len(navigation) == 1
        assert navigation[0][1] == "Read more"
        assert navigation[0][2] == "›"
        assert navigation[0][3] == ""  # a link has no sample column

    def test_a_navigation_row_is_an_anchor_in_the_html(self) -> None:
        renderer = _renderer(self._popup())
        html = renderer._rich_html(renderer._stat_rows(7))
        assert 'href="submenu:s"' in html
        assert "Read more" in html

    def test_five_element_rows_still_render(self) -> None:
        # The existing popup tests build 5-tuples; the submenu element is optional.
        html = _renderer(self._popup())._rich_html([("Preflop", "VPIP", "25.8", "(63/244)", "")])
        assert "VPIP" in html and "(63/244)" in html

    def test_opening_a_submenu_uses_the_configured_popup(self, monkeypatch) -> None:
        from fpdb_3_legacy import ModernPopup

        opened: list[tuple] = []
        monkeypatch.setattr(ModernPopup, "popup_factory", lambda *args: opened.append(args))
        popup = ModernPopup.ModernSubmenu.__new__(ModernPopup.ModernSubmenu)
        popup.seat = 3
        popup.stat_dict = {7: {"seat": 3}}
        popup.win = object()
        popup.hand_instance = None
        popup.submenu_count = 0
        target = object()
        popup.config = type("C", (), {"popup_windows": {"s": target}})()
        popup.open_submenu("s")
        assert len(opened) == 1
        assert opened[0][3] is target  # the configured popup, not a new one

    def test_opening_twice_at_one_level_is_ignored(self, monkeypatch) -> None:
        from fpdb_3_legacy import ModernPopup

        opened: list[tuple] = []
        monkeypatch.setattr(ModernPopup, "popup_factory", lambda *args: opened.append(args))
        popup = ModernPopup.ModernSubmenu.__new__(ModernPopup.ModernSubmenu)
        popup.seat = 3
        popup.stat_dict = {}
        popup.win = object()
        popup.hand_instance = None
        popup.submenu_count = 1
        popup.config = type("C", (), {"popup_windows": {"s": object()}})()
        popup.open_submenu("s")
        assert opened == []

    def test_opening_a_missing_submenu_logs_instead_of_raising(self) -> None:
        from fpdb_3_legacy import ModernPopup

        popup = ModernPopup.ModernSubmenu.__new__(ModernPopup.ModernSubmenu)
        popup.seat = 3
        popup.stat_dict = {}
        popup.win = object()
        popup.hand_instance = None
        popup.submenu_count = 0
        popup.config = type("C", (), {"popup_windows": {}})()
        popup.open_submenu("nowhere")  # must not raise
