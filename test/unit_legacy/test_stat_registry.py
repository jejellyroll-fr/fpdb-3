"""Unit tests for fpdb_3_legacy.stat_registry.

These cover the three pieces of the plug-and-play stat foundation:
the sandboxed expression evaluator, descriptor validation, and the registry
that loads descriptor files (including the bundled ChipEV-by-position stats).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fpdb_3_legacy import stat_registry as sr


class TestSafeExpression:
    def test_basic_arithmetic(self):
        expr = sr.SafeExpression("100 * a / b", frozenset({"a", "b"}))
        assert expr.evaluate({"a": 3, "b": 4}) == 75.0

    def test_referenced_names_subset(self):
        expr = sr.SafeExpression("a + 1", frozenset({"a", "b"}))
        assert expr.referenced_names == frozenset({"a"})

    def test_division_by_zero_returns_none(self):
        expr = sr.SafeExpression("a / b", frozenset({"a", "b"}))
        assert expr.evaluate({"a": 5, "b": 0}) is None

    def test_missing_variable_treated_as_zero(self):
        expr = sr.SafeExpression("a + b", frozenset({"a", "b"}))
        assert expr.evaluate({"a": 5}) == 5

    def test_none_variable_treated_as_zero(self):
        expr = sr.SafeExpression("a + b", frozenset({"a", "b"}))
        assert expr.evaluate({"a": 5, "b": None}) == 5

    def test_whitelisted_function(self):
        expr = sr.SafeExpression("coalesce(a, b, 0)", frozenset({"a", "b"}))
        assert expr.evaluate({"a": 0, "b": 7}) == 7

    def test_unknown_name_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.SafeExpression("allInEV / cnt", frozenset({"allInEV"}))

    def test_attribute_access_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.SafeExpression("a.__class__", frozenset({"a"}))

    def test_arbitrary_call_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.SafeExpression("__import__('os')", frozenset())

    def test_boolean_literal_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.SafeExpression("a + True", frozenset({"a"}))


class TestBuildDescriptor:
    def _valid(self, **over):
        data = {
            "name": "vpip",
            "label": "VPIP",
            "inputs": ["street0VPI", "street0VPIChance"],
            "value": "100 * street0VPI / street0VPIChance",
            "scope": ["ring", "tour"],
            "format": "%3.1f",
        }
        data.update(over)
        return data

    def test_valid_descriptor(self):
        d = sr.build_descriptor(self._valid())
        assert d.name == "vpip"
        assert d.applies_to("ring")
        assert d.compute({"street0VPI": 30, "street0VPIChance": 100}) == 30.0
        assert d.format(30.0) == "30.0"

    def test_zero_denominator_formats_placeholder(self):
        d = sr.build_descriptor(self._valid())
        assert d.compute({"street0VPI": 0, "street0VPIChance": 0}) is None
        assert d.format(None) == "-"

    def test_bad_name_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.build_descriptor(self._valid(name="3invalid name"))

    def test_value_referencing_missing_column_rejected(self):
        # The whole point of Tier-2/Tier-3 boundary: an expression that needs a
        # column not declared as an input is refused at load time.
        with pytest.raises(sr.StatDescriptorError):
            sr.build_descriptor(self._valid(value="amt_expected_won / 100"))

    def test_invalid_scope_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.build_descriptor(self._valid(scope=["nonsense"]))

    def test_invalid_dimension_key_rejected(self):
        with pytest.raises(sr.StatDescriptorError):
            sr.build_descriptor(self._valid(dimension={"street": 1}))

    def test_dimension_accepted(self):
        d = sr.build_descriptor(
            self._valid(inputs=["allInEV"], value="allInEV / 100.0", dimension={"seats": 3, "position": "S"}),
        )
        assert d.dimension == {"seats": 3, "position": "S"}


class TestRegistryLoadsBundledChipEV:
    @pytest.fixture()
    def registry(self):
        reg = sr.StatRegistry()
        reg.load_directory(sr.default_stats_dir())
        return reg

    def test_chipev_descriptors_loaded(self, registry):
        for name in ("chipev_3h_btn", "chipev_3h_sb", "chipev_3h_bb", "chipev_hu_sb", "chipev_hu_bb", "chipev_tourney"):
            assert name in registry, f"{name} missing from registry"

    def test_five_curves_are_cumulative_series(self, registry):
        series = {d.name for d in registry.series_for_scope("tour")}
        assert series == {"chipev_3h_btn", "chipev_3h_sb", "chipev_3h_bb", "chipev_hu_sb", "chipev_hu_bb"}

    def test_chipev_scope_is_tour_only(self, registry):
        d = registry.get("chipev_3h_sb")
        assert d.applies_to("tour")
        assert not d.applies_to("ring")

    def test_chipev_value_scales_by_100(self, registry):
        d = registry.get("chipev_3h_sb")
        # allInEV stored x100 -> 2500 means 25 chips of EV.
        assert d.compute({"allInEV": 2500}) == 25.0

    def test_dimension_maps_pt4_positions(self, registry):
        assert registry.get("chipev_3h_sb").dimension == {"seats": 3, "position": "S"}
        assert registry.get("chipev_3h_bb").dimension == {"seats": 3, "position": "B"}
        assert registry.get("chipev_3h_btn").dimension == {"seats": 3, "position": 0}
        assert registry.get("chipev_hu_sb").dimension == {"seats": 2, "position": "S"}


class TestRegistrySkipsBadFiles:
    def test_malformed_file_is_skipped(self, tmp_path):
        (tmp_path / "good.json").write_text(
            '{"stat": {"name": "good", "label": "G", "inputs": ["n"], "value": "n", "scope": ["ring"]}}',
            encoding="utf-8",
        )
        (tmp_path / "bad.json").write_text('{"stat": {"name": "bad", "value": "oops"}}', encoding="utf-8")
        reg = sr.StatRegistry()
        loaded = reg.load_directory(tmp_path)
        assert loaded == 1
        assert "good" in reg
        assert "bad" not in reg
