"""Unit tests for the PT4 .pt4stat importer/translator.

The translator and TOML round-trip are tested with hand-built DecodedStat
objects (deterministic, no external files). Decoding of the real binary files
is tested only when the sample directory is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy import pt4_import as pt4
from fpdb_3_legacy import stat_registry as sr

SAMPLE_DIR = Path("/Users/jde/Documents/github/fpdb-new/658225d6b920e_5-courbes-chips-ev-par-position")


def _decoded(value_expr, columns, label="ChipEV X", decimals=2):
    return pt4.DecodedStat(
        path=Path("mem.pt4stat"),
        columns=columns,
        value_expr=value_expr,
        decimals=decimals,
        label=label,
    )


class TestTranslateDimensioned:
    def test_sum_if_position_seats(self):
        sql = (
            "sum(if[tourney_hand_player_statistics.position=9 AND "
            "tourney_hand_player_statistics.cnt_players=3,\n"
            "tourney_hand_player_statistics.amt_expected_won,0])"
        )
        decoded = _decoded(
            "amt_expected_won_3h_sb",
            {"amt_expected_won_3h_sb": sql},
            label="ChipEV 3H_SB",
        )
        d = pt4.translate(decoded)
        assert d.supported
        assert d.descriptor["name"] == "chipev_3h_sb"
        assert d.descriptor["inputs"] == ["allInEV"]
        assert d.descriptor["dimension"] == {"seats": 3, "position": "S"}
        assert d.descriptor["value"] == "allInEV / 100"
        assert d.descriptor["series"] == "cumulative"
        assert d.descriptor["scope"] == ["tour"]

    def test_position_codes_mapped(self):
        for code, expected in ((0, 0), (8, "B"), (9, "S")):
            decoded = _decoded(
                "c",
                {"c": f"sum(if[t.position={code} AND t.cnt_players=2, t.amt_expected_won, 0])"},
            )
            assert pt4.translate(decoded).descriptor["dimension"]["position"] == expected


class TestTranslateContext:
    def test_division_by_cnt_tourneys(self):
        decoded = _decoded(
            "amt_expected_won / cnt_tourneys",
            {
                "amt_expected_won": "sum(tourney_hand_player_statistics.amt_expected_won)",
                "cnt_tourneys": "count(distinct tourney_summary.id_tourney)",
            },
            label="ChipsEV/tourney",
        )
        d = pt4.translate(decoded)
        assert d.supported
        assert d.descriptor["inputs"] == ["allInEV", "cnt_tourneys"]
        assert d.descriptor["context"] == ["cnt_tourneys"]
        assert d.descriptor["value"] == "allInEV / 100 / cnt_tourneys"
        assert "dimension" not in d.descriptor


class TestUnsupportedReported:
    def test_unmapped_column_skipped(self):
        # A PT4 column with no entry in the legacy mapping is reported.
        decoded = _decoded("c", {"c": "sum(t.amt_does_not_exist)"})
        d = pt4.translate(decoded)
        assert not d.supported
        assert any("amt_does_not_exist" in w for w in d.warnings)

    def test_mapped_money_column_translates(self):
        # amt_rake is in docs/pt4_legacy_mapping.json -> rake (scale 100).
        decoded = _decoded("c", {"c": "sum(t.amt_rake)"})
        d = pt4.translate(decoded)
        assert d.supported
        assert d.descriptor["inputs"] == ["rake"]
        assert d.descriptor["value"] == "rake / 100"

    def test_unmapped_position_skipped(self):
        decoded = _decoded("c", {"c": "sum(if[t.position=5 AND t.cnt_players=6, t.amt_expected_won, 0])"})
        d = pt4.translate(decoded)
        assert not d.supported
        assert any("position" in w for w in d.warnings)

    def test_no_value_expr_skipped(self):
        d = pt4.translate(_decoded("", {}))
        assert not d.supported


class TestPrintfFormatDetection:
    def test_printf_format_value_is_preceding_string(self):
        # PT4 ratio stats use a printf format ('/%.2f'), with the value in the
        # string just before it (not a format_number(...) call).
        strings = [
            "Cash Player",
            "cnt_a",
            "sum(if[cash_hand_player_statistics.flg_x, 1, 0])",
            "4Bet Preflop Success",
            "(cnt_a / cnt_b) * 100",
            "/%.2f",
            "/%.2f",
        ]
        # Drive the format/value detection directly.
        idx = pt4._find_format_index(strings)
        assert idx == 5
        assert strings[idx - 1] == "(cnt_a / cnt_b) * 100"

    def test_printf_regex_matches_common_directives(self):
        for fmt in ("%.2f", "/%.2f", "%d", "%5.1f%%", "/%d"):
            assert pt4._PRINTF_RE.match(fmt), fmt
        for nonfmt in ("(cnt_a / cnt_b) * 100", "amt_expected_won", "sum(x)"):
            assert not pt4._PRINTF_RE.match(nonfmt), nonfmt


class TestDecoderRobustness:
    def test_clean_latin_filter_rejects_cjk(self):
        # A mis-aligned read decodes marker bytes as CJK; it must be rejected so
        # the scanner re-syncs onto the real Latin strings.
        assert pt4._is_clean_latin("cnt_t_delayed_cbet")
        assert pt4._is_clean_latin("Fichas ganadas por torneo")  # Spanish
        assert not pt4._is_clean_latin("㱩Ā作")  # CJK / garbage


class TestAccurateUnsupportedReason:
    def test_ratio_with_unmapped_column_names_the_blocker(self):
        # flg_p_4bet now maps (street0_4BDone); the enum column does not, so the
        # report must name the genuinely-unmappable column, not the whole expr.
        decoded = _decoded(
            "(cnt_p_4bet_success / cnt_p_raise_3bet) * 100",
            {
                "cnt_p_4bet_success": "sum(if[cash_hand_player_statistics.flg_p_4bet, 1, 0])",
                "cnt_p_raise_3bet": "sum(if[cash_hand_player_statistics.enum_p_3bet_action = 'R', 1, 0])",
            },
            label="4Bet Preflop Success",
        )
        d = pt4.translate(decoded)
        assert not d.supported
        assert any("cnt_p_raise_3bet" in w for w in d.warnings)

    def test_real_compound_cash_stat_stays_unsupported(self):
        # The actual PT4 stat has a COMPOUND condition (flag AND char_length(...))
        # that reduces to no single FPDB column, so it must remain unsupported.
        decoded = _decoded(
            "(cnt_a / cnt_b) * 100",
            {
                "cnt_a": "sum(if[t.flg_p_4bet AND char_length(s.str_aggressors_p) = 3, 1, 0])",
                "cnt_b": "sum(if[t.flg_p_4bet AND char_length(s.str_aggressors_p) = 4, 1, 0])",
            },
        )
        d = pt4.translate(decoded)
        assert not d.supported


class TestGeneralArithmeticTranslation:
    def test_flag_ratio_translates_via_mapping(self):
        # W$SD%-like: (won_hand / showdown) * 100 over two mapped flag counts.
        decoded = _decoded(
            "(cnt_won / cnt_sd) * 100",
            {
                "cnt_won": "sum(if[t.flg_won_hand, 1, 0])",
                "cnt_sd": "sum(if[t.flg_showdown, 1, 0])",
            },
            label="W$SD",
        )
        d = pt4.translate(decoded)
        assert d.supported, d.warnings
        assert set(d.descriptor["inputs"]) == {"wonAtSD", "sawShowdown"}
        assert d.descriptor["value"] == "(wonAtSD / sawShowdown) * 100"
        assert d.descriptor["aggregate"] == "ratio"

    def test_flag_count_sum_if_resolves(self):
        fpdb_col, dim, scale = pt4._resolve_fact("sum(if[t.flg_p_4bet, 1, 0])")
        assert fpdb_col == "street0_4BDone"
        assert dim is None and scale == 1.0

    def test_ratio_with_one_unmapped_column_reports_it(self):
        decoded = _decoded(
            "(cnt_won / cnt_weird) * 100",
            {
                "cnt_won": "sum(if[t.flg_won_hand, 1, 0])",
                "cnt_weird": "sum(if[t.flg_made_up_flag, 1, 0])",
            },
        )
        d = pt4.translate(decoded)
        assert not d.supported
        assert any("flg_made_up_flag" in w for w in d.warnings)


class TestLegacyMappingFile:
    def test_mapping_loads_from_json(self):
        mapping = pt4.load_column_map()
        # Built-in fallback always present.
        assert mapping["amt_expected_won"] == ("allInEV", 100.0)
        # Loaded from docs/pt4_legacy_mapping.json.
        assert mapping["flg_showdown"] == ("sawShowdown", 1.0)
        assert mapping["amt_won"] == ("winnings", 100.0)

    def test_mapping_path_points_at_docs(self):
        assert pt4._legacy_mapping_path().name == "pt4_legacy_mapping.json"

    def test_documentation_keys_are_skipped(self):
        # "_note..." keys inside columns must not crash the loader or appear.
        mapping = pt4.load_column_map()
        assert not any(k.startswith("_") for k in mapping)

    def test_preflop_done_chance_pairs_present(self):
        mapping = pt4.load_column_map()
        assert mapping["flg_p_3bet"] == ("street0_3BDone", 1.0)
        assert mapping["flg_p_3bet_opp"] == ("street0_3BChance", 1.0)


class TestStandardRatioStat:
    def test_3bet_percent_translates(self):
        # A standard PT4 ratio over Done/Chance columns now imports as a ratio.
        decoded = _decoded(
            "(cnt_3b / cnt_3b_opp) * 100",
            {
                "cnt_3b": "sum(if[t.flg_p_3bet, 1, 0])",
                "cnt_3b_opp": "sum(if[t.flg_p_3bet_opp, 1, 0])",
            },
            label="3Bet PF",
        )
        d = pt4.translate(decoded)
        assert d.supported, d.warnings
        assert d.descriptor["value"] == "(street0_3BDone / street0_3BChance) * 100"
        assert set(d.descriptor["inputs"]) == {"street0_3BDone", "street0_3BChance"}
        assert set(d.descriptor["boolean_inputs"]) == {"street0_3BDone", "street0_3BChance"}


class TestRoundTripThroughRegistry:
    """Importer output must be loadable and computable by the foundation."""

    def test_emit_then_load(self, tmp_path):
        decoded = _decoded(
            "amt_expected_won_hu_bb",
            {"amt_expected_won_hu_bb": "sum(if[t.position=8 AND t.cnt_players=2, t.amt_expected_won, 0])"},
            label="ChipEV HU_BB",
        )
        toml_text = pt4.emit_toml(pt4.translate(decoded).descriptor)
        (tmp_path / "imported.toml").write_text(toml_text, encoding="utf-8")

        reg = sr.StatRegistry()
        loaded = reg.load_directory(tmp_path)
        assert loaded == 1
        d = reg.get("chipev_hu_bb")
        assert d is not None
        assert d.dimension == {"seats": 2, "position": "B"}
        # allInEV x100 of 5000 -> 50 chips.
        assert d.compute({"allInEV": 5000}) == 50.0


@pytest.mark.skipif(not SAMPLE_DIR.is_dir(), reason="PT4 sample directory not present")
class TestDecodeRealFiles:
    def test_all_six_translate(self):
        results = {}
        for path in sorted(SAMPLE_DIR.glob("*.pt4stat")):
            results[path.name] = pt4.translate(pt4.decode_pt4stat(path))
        assert len(results) == 6
        assert all(r.supported for r in results.values())
        names = {r.descriptor["name"] for r in results.values()}
        assert {"chipev_3h_bb", "chipev_3h_btn", "chipev_3h_sb", "chipev_hu_bb", "chipev_hu_sb"} <= names

    def test_import_directory_writes_six(self, tmp_path):
        report = pt4.import_directory(SAMPLE_DIR, tmp_path / "out.toml")
        assert len(report.imported) == 6
        assert not report.skipped
        # And the written file round-trips through the registry.
        reg = sr.StatRegistry()
        assert reg.load_directory(tmp_path) == 6


class TestImportFilesMerge:
    def _decoded_toml(self, tmp_path, name):
        # Build a descriptor file via the emitter so the merge reader can parse it.
        desc = pt4.translate(
            _decoded(
                "c",
                {"c": "sum(if[t.position=8 AND t.cnt_players=2, t.amt_expected_won, 0])"},
                label=name,
            ),
        ).descriptor
        return desc

    def test_merge_preserves_and_replaces_by_name(self, tmp_path):
        dest = tmp_path / "pt4_imported.toml"
        # Seed with one descriptor, then merge a second; both must survive.
        first = pt4.translate(
            _decoded("a", {"a": "sum(if[t.position=9 AND t.cnt_players=3, t.amt_expected_won, 0])"}, label="ChipEV A"),
        ).descriptor
        second = pt4.translate(
            _decoded("b", {"b": "sum(if[t.position=8 AND t.cnt_players=3, t.amt_expected_won, 0])"}, label="ChipEV B"),
        ).descriptor
        dest.write_text(pt4.emit_toml(first), encoding="utf-8")

        # Simulate a fresh translate by writing 'second' then merging via reload.
        reg = sr.StatRegistry()
        # Use import_files indirectly: write 'second' through emit + merge reader.
        merged = pt4._load_existing_descriptors(dest)
        assert "chipev_a" in merged
        merged[second["name"]] = second
        body = "\n".join(pt4.emit_toml(merged[n]) for n in sorted(merged))
        dest.write_text(body, encoding="utf-8")

        assert reg.load_directory(tmp_path) == 2
        assert "chipev_a" in reg and "chipev_b" in reg
