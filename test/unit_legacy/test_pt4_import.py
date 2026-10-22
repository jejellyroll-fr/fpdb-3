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


# --------------------------------------------------------------------------- #
# The common cash idioms of PT4's stock stats (#613). The SQL below is PT4's own
# column definitions, as its StatDefinitions.pt4 states them for "Cash Player".
# --------------------------------------------------------------------------- #

T = "cash_hand_player_statistics"
STOCK_COLUMNS = {
    "cnt_vpip": f"sum(if[{T}.flg_vpip, 1, 0])",
    "cnt_hands": f"sum(if[{T}.id_hand > 0, 1, 0])",
    "cnt_walks": "sum(if[lookup_actions_p.action = '', 1, 0])",
    "cnt_pfr": f"sum(if[{T}.cnt_p_raise > 0, 1, 0])",
    "cnt_pfr_opp": "sum(if[ lookup_actions_p.action LIKE '__%' OR (lookup_actions_p.action LIKE '_' AND ...), 1, 0])",
    "cnt_p_3bet": f"sum(if[{T}.flg_p_3bet, 1, 0])",
    "cnt_p_3bet_opp": f"sum(if[{T}.flg_p_3bet_opp, 1, 0])",
    "cnt_p_3bet_def_action_fold": f"sum(if[{T}.enum_p_3bet_action='F', 1, 0])",
    "cnt_p_3bet_def_opp": f"sum(if[{T}.flg_p_3bet_def_opp, 1, 0])",
    "cnt_f_cbet": f"sum(if[{T}.flg_f_cbet, 1, 0])",
    "cnt_f_cbet_opp": f"sum(if[{T}.flg_f_cbet_opp, 1, 0])",
    "cnt_f_cbet_def_action_fold": f"sum(if[{T}.enum_f_cbet_action='F', 1, 0])",
    "cnt_f_cbet_def_opp": f"sum(if[{T}.flg_f_cbet_def_opp, 1, 0])",
    "cnt_wtsd": f"sum(if[{T}.flg_showdown, 1, 0])",
    "cnt_wtsd_won": f"sum(if[{T}.flg_showdown AND {T}.flg_won_hand, 1, 0])",
    "cnt_f_saw": f"sum(if[{T}.flg_f_saw, 1, 0])",
    "cnt_f_bet": f"sum(if[{T}.flg_f_bet, 1, 0])",
    "cnt_f_raise": f"sum({T}.cnt_f_raise)",
    "cnt_f_call": f"sum({T}.cnt_f_call )",
    "cnt_f_fold": f"sum(if[{T}.flg_f_fold, 1, 0])",
    "cnt_steal_att": f"sum(if[{T}.flg_steal_att, 1, 0])",
    "cnt_steal_opp": f"sum(if[{T}.flg_steal_opp, 1, 0])",
    "cnt_steal_def_action_fold": f"sum(if[{T}.flg_blind_def_opp AND lookup_actions_p.action = 'F', 1, 0])",
    "cnt_steal_def_opp": f"sum(if[{T}.flg_blind_def_opp, 1, 0])",
}


def _stock(label, value_expr):
    referenced = {name: sql for name, sql in STOCK_COLUMNS.items() if name in value_expr}
    return pt4.DecodedStat(
        path=Path("StatDefinitions.pt4"),
        columns=referenced,
        value_expr=value_expr,
        label=label,
        category="Cash Player",
    )


class TestCommonCashIdioms:
    @pytest.mark.parametrize(
        ("label", "value_expr", "fpdb_value"),
        [
            ("3Bet Preflop", "(cnt_p_3bet / cnt_p_3bet_opp) * 100", "(street0_3BDone / street0_3BChance) * 100"),
            (
                "Fold to PF 3Bet",
                "(cnt_p_3bet_def_action_fold / cnt_p_3bet_def_opp) * 100",
                "(street0_FoldTo3BDone / street0_FoldTo3BChance) * 100",
            ),
            ("CBet Flop", "(cnt_f_cbet / cnt_f_cbet_opp) * 100", "(street1CBDone / street1CBChance) * 100"),
            (
                "Fold to F CBet",
                "(cnt_f_cbet_def_action_fold / cnt_f_cbet_def_opp) * 100",
                "(foldToStreet1CBDone / foldToStreet1CBChance) * 100",
            ),
            ("WTSD", "(cnt_wtsd / cnt_f_saw) * 100", "(sawShowdown / street1Seen) * 100"),
            ("WSD", "(cnt_wtsd_won / cnt_wtsd) * 100", "(wonAtSD / sawShowdown) * 100"),
            ("Att To Steal", "(cnt_steal_att / cnt_steal_opp) * 100", "(stealDone / stealChance) * 100"),
            (
                "Fold to Steal",
                "(cnt_steal_def_action_fold / cnt_steal_def_opp) * 100",
                "((foldedSbToSteal + foldedBbToSteal) / (foldSbToStealChance + foldBbToStealChance)) * 100",
            ),
            ("Flop AF", "(cnt_f_bet + cnt_f_raise) / cnt_f_call", "(street1Bets + street1Raises) / street1Calls"),
        ],
    )
    def test_translates_as_pt4_defines_it(self, label, value_expr, fpdb_value):
        result = pt4.translate(_stock(label, value_expr))

        assert result.supported, result.warnings
        assert result.descriptor["value"] == fpdb_value
        assert result.notes == []
        assert result.descriptor["scope"] == ["ring", "tour"]

    @pytest.mark.parametrize(
        ("label", "value_expr", "fpdb_value", "note"),
        [
            ("VPIP", "(cnt_vpip / (cnt_hands - cnt_walks)) * 100", "(street0VPI / (street0VPIChance)) * 100", "walk"),
            ("PFR", "(cnt_pfr / cnt_pfr_opp) * 100", "(street0Aggr / street0AggrChance) * 100", "raise"),
        ],
    )
    def test_translates_under_fpdb_s_definition_and_says_so(self, label, value_expr, fpdb_value, note):
        result = pt4.translate(_stock(label, value_expr))

        assert result.supported, result.warnings
        assert result.descriptor["value"] == fpdb_value
        assert len(result.notes) == 1 and note in result.notes[0]
        assert "Differs from PT4:" in result.descriptor["description"]

    def test_afq_names_the_fold_counts_fpdb_lacks(self):
        result = pt4.translate(
            _stock(
                "Flop AFq", "((cnt_f_bet + cnt_f_raise) / (cnt_f_call + cnt_f_fold + cnt_f_bet + cnt_f_raise)) * 100"
            )
        )

        assert not result.supported
        assert any("flg_f_fold" in warning for warning in result.warnings)

    def test_a_count_column_is_a_boolean_input_and_an_action_count_is_not(self):
        result = pt4.translate(_stock("Flop AF", "(cnt_f_bet + cnt_f_raise) / cnt_f_call"))

        assert result.descriptor["boolean_inputs"] == ["street1Bets"]

    def test_both_blinds_steal_columns_are_inputs(self):
        result = pt4.translate(_stock("Fold to Steal", "(cnt_steal_def_action_fold / cnt_steal_def_opp) * 100"))

        assert set(result.descriptor["inputs"]) == {
            "foldedSbToSteal",
            "foldedBbToSteal",
            "foldSbToStealChance",
            "foldBbToStealChance",
        }

    def test_a_tournament_category_scopes_the_stat_to_tournaments(self):
        decoded = _stock("WTSD", "(cnt_wtsd / cnt_f_saw) * 100")
        decoded.category = "Tournament Player"

        assert pt4.translate(decoded).descriptor["scope"] == ["tour"]

    @pytest.mark.parametrize(
        ("condition", "normalised"),
        [
            ("cash_hand_player_statistics.enum_p_3bet_action='F'", "enum_p_3bet_action = 'F'"),
            ("t.flg_blind_def_opp AND lookup_actions_p.action  =  'F'", "flg_blind_def_opp AND action = 'F'"),
            ("t.cnt_p_raise>0", "cnt_p_raise > 0"),
        ],
    )
    def test_conditions_are_normalised_before_lookup(self, condition, normalised):
        assert pt4._normalise_condition(condition) == normalised

    def test_every_translated_idiom_loads_and_computes_in_the_registry(self, tmp_path):
        stats = [
            _stock("VPIP", "(cnt_vpip / (cnt_hands - cnt_walks)) * 100"),
            _stock("Fold to Steal", "(cnt_steal_def_action_fold / cnt_steal_def_opp) * 100"),
            _stock("Flop AF", "(cnt_f_bet + cnt_f_raise) / cnt_f_call"),
        ]
        body = "\n".join(pt4.emit_toml(pt4.translate(stat).descriptor) for stat in stats)
        (tmp_path / "stock.toml").write_text(body, encoding="utf-8")

        reg = sr.StatRegistry()
        assert reg.load_directory(tmp_path) == 3
        assert reg.get("vpip").compute({"street0VPI": 3, "street0VPIChance": 12}) == 25.0
        folded = {"foldedSbToSteal": 1, "foldedBbToSteal": 2, "foldSbToStealChance": 2, "foldBbToStealChance": 2}
        assert reg.get("fold_to_steal").compute(folded) == 75.0
        assert reg.get("flop_af").compute({"street1Bets": 2, "street1Raises": 1, "street1Calls": 2}) == 1.5


def _container(*strings: str) -> bytes:
    """A PT4 container: big-endian length-prefixed UTF-16 strings."""
    import struct

    return b"".join(struct.pack(">I", len(text)) + text.encode("utf-16-be") for text in strings)


class TestStatDefinitions:
    def test_reads_the_player_stats_with_the_columns_they_reference(self, tmp_path):
        path = tmp_path / "StatDefinitions.pt4"
        path.write_bytes(
            _container(
                "Cash Player",
                "cnt_p_3bet",
                STOCK_COLUMNS["cnt_p_3bet"],
                "Sum",
                "Number of times the player 3bet.",
                "Cash Player",
                "cnt_p_3bet_opp",
                STOCK_COLUMNS["cnt_p_3bet_opp"],
                "Sum",
                "Number of 3bet chances.",
                "Cash Player",
                "3Bet Preflop",
                "Preflop 3Bet %",
                "3Bet PF",
                "(cnt_p_3bet / cnt_p_3bet_opp) * 100",
                "/%.1f",
                "/%.1f",
                "Percentage of the time the player 3bet preflop.\n\nFormula: ...",
                "Preflop",
                "Cash Hand",
                "amt_bb",
                "cash_limit.amt_bb",
                "Count Unique",
                "Amount of the big blind.",
            )
        )

        (stat,) = pt4.read_stat_definitions(path)

        assert stat.label == "3Bet Preflop"
        assert stat.category == "Cash Player"
        assert stat.value_expr == "(cnt_p_3bet / cnt_p_3bet_opp) * 100"
        assert stat.columns == {
            "cnt_p_3bet": STOCK_COLUMNS["cnt_p_3bet"],
            "cnt_p_3bet_opp": STOCK_COLUMNS["cnt_p_3bet_opp"],
        }
        assert stat.decimals == 1
        assert stat.description == "Percentage of the time the player 3bet preflop."
        assert pt4.translate(stat).supported

    @pytest.mark.parametrize(
        ("display", "decimals"), [("/%.2f", 2), ("format_number(x / y, 1, false, false)", 1), ("tourney_no", 2)]
    )
    def test_decimals_come_from_the_display_expression(self, display, decimals):
        assert pt4._decimals(display) == decimals


class TestCoverageReport:
    def test_counts_names_and_blockers(self):
        results = [
            (_stock("3Bet Preflop", "(cnt_p_3bet / cnt_p_3bet_opp) * 100"), None),
            (_stock("VPIP", "(cnt_vpip / (cnt_hands - cnt_walks)) * 100"), None),
            (_stock("Flop AFq", "(cnt_f_bet + cnt_f_raise) / (cnt_f_call + cnt_f_fold)"), None),
        ]
        report = pt4.CoverageReport([(stat, pt4.translate(stat)) for stat, _ in results])

        text = report.markdown("StatDefinitions.pt4")

        assert "| Cash Player | 2 | 1 | 1 | 1 |" in text
        assert "| 3Bet Preflop | `(street0_3BDone / street0_3BChance) * 100` | translated |" in text
        assert "| VPIP | `(street0VPI / (street0VPIChance)) * 100` | translated: PT4's VPIP" in text
        assert "| PFR | | not in this PT4 version |" in text
        assert report.blockers() == [("unmapped column: `flg_f_fold`", 1)]

    def test_the_command_line_writes_the_report(self, tmp_path):
        path = tmp_path / "StatDefinitions.pt4"
        path.write_bytes(
            _container(
                "Cash Player",
                "cnt_wtsd",
                STOCK_COLUMNS["cnt_wtsd"],
                "Sum",
                "Went to showdown.",
                "Cash Player",
                "cnt_f_saw",
                STOCK_COLUMNS["cnt_f_saw"],
                "Sum",
                "Saw the flop.",
                "Cash Player",
                "WTSD",
                "Went to Showdown %",
                "WTSD %",
                "(cnt_wtsd / cnt_f_saw) * 100",
                "/%.2f",
                "/%.2f",
                "Percentage of the time the player went to showdown.",
                "Showdown",
            )
        )

        assert pt4.main([str(path), str(tmp_path / "coverage.md"), "--coverage"]) == 0
        assert "| WTSD | `(sawShowdown / street1Seen) * 100` | translated |" in (tmp_path / "coverage.md").read_text()


STOCK_FILE = Path("/Applications/PokerTracker 4.app/Contents/Resources/Data/Stats/StatDefinitions.pt4")


@pytest.mark.skipif(not STOCK_FILE.exists(), reason="PokerTracker 4 is not installed here")
class TestInstalledPT4:
    def test_the_common_cash_stats_translate_but_afq(self):
        stats = {s.label: s for s in pt4.read_stat_definitions(STOCK_FILE) if s.category == "Cash Player"}
        outcome = {title: pt4.translate(stats[title]).supported for title in pt4.COMMON_CASH_STATS}

        assert outcome == {title: title not in ("Flop AFq", "Total AFq") for title in pt4.COMMON_CASH_STATS}


def test_an_import_report_says_which_stats_differ_from_pt4(tmp_path):
    report = pt4.ImportReport(imported=["vpip"], differs={"vpip": ["PT4's VPIP opportunity is every hand but a walk."]})

    assert "Imported under FPDB's definition, which differs from PT4's (1):" in report.summary()
    assert "  - vpip: PT4's VPIP opportunity is every hand but a walk." in report.summary()
