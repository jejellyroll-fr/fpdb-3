#!/usr/bin/env python3
"""Coverage tests for Stats.py exception handlers and calculation branches.

Targets previously-uncovered lines in ``fpdb_3_legacy/Stats.py``:

- Block B: ``except (KeyError, ValueError, TypeError)`` handlers, reached by
  passing a player key that is absent from ``stat_dict``.
- Block C: success-path calculation branches, reached by supplying valid
  non-zero data so the division is actually performed.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Stats
from fpdb_3_legacy.Stats import (
    WMsF,
    a_freq2,
    a_freq3,
    a_freq4,
    a_freq_123,
    agg_fact,
    agg_fact_pct,
    car0,
    check_raise_frequency,
    cr4,
    dbr3,
    f_dbr1,
    f_dbr2,
    f_dbr3,
    fbr,
    game_abbr,
    open_limp,
    player_note,
    squeeze,
    triple_barrel,
)


class TestCalcBranches:
    """Block C — exercise the success-path calculation branches."""

    def test_dbr3_calc_branch(self) -> None:
        """(saw_3 - cb_opp_3) != 0 performs the donk-bet-and-raise division."""
        result = dbr3({"p": {"aggr_3": 5, "cb_3": 2, "saw_3": 10, "cb_opp_3": 4}}, "p")
        assert result[1] == "50.0"  # (5-2)/(10-4) = 0.5
        assert result[4] == "(3/6)"

    def test_f_dbr1_calc_branch(self) -> None:
        """(was_raised_1 - f_cb_opp_1) != 0 performs the fold-to-DBR division."""
        result = f_dbr1({"p": {"f_freq_1": 5, "f_cb_1": 1, "was_raised_1": 10, "f_cb_opp_1": 2}}, "p")
        assert result[1] == "50.0"  # (5-1)/(10-2) = 0.5
        assert result[4] == "(4/8)"

    def test_f_dbr2_calc_branch(self) -> None:
        """(was_raised_2 - f_cb_opp_2) != 0 performs the turn fold-to-DBR division."""
        result = f_dbr2({"p": {"f_freq_2": 5, "f_cb_2": 1, "was_raised_2": 10, "f_cb_opp_2": 2}}, "p")
        assert result[1] == "50.0"
        assert result[4] == "(4/8)"

    def test_f_dbr3_calc_branch(self) -> None:
        """(was_raised_3 - f_cb_opp_3) != 0 performs the river fold-to-DBR division."""
        result = f_dbr3({"p": {"f_freq_3": 5, "f_cb_3": 1, "was_raised_3": 10, "f_cb_opp_3": 2}}, "p")
        assert result[1] == "50.0"
        assert result[4] == "(4/8)"

    def test_squeeze_calc_branch(self) -> None:
        """sqz_opp_0 != 0 performs the squeeze division."""
        result = squeeze({"p": {"sqz_0": 3, "sqz_opp_0": 10}}, "p")
        assert result[1] == "30.0"
        assert result[2] == "SQZ=30.0%"
        assert result[4] == "(3/10)"

    def test_car0_calc_branch(self) -> None:
        """car_opp_0 != 0 performs the called-a-raise-preflop division."""
        result = car0({"p": {"car_0": 4, "car_opp_0": 10}}, "p")
        assert result[1] == "40.0"
        assert result[4] == "(4/10)"

    def test_cr4_calc_branch(self) -> None:
        """ccr_opp_4 != 0 performs the 7th-street check-raise division."""
        result = cr4({"p": {"cr_4": 3, "ccr_opp_4": 10}}, "p")
        assert result[1] == "30.0"
        assert result[4] == "(3/10)"

    def test_check_raise_frequency_calc_branch(self) -> None:
        """total_opp != 0 performs the check-raise-frequency division."""
        result = check_raise_frequency(
            {"p": {"cr_1": 2, "cr_2": 1, "cr_3": 1, "ccr_opp_1": 5, "ccr_opp_2": 3, "ccr_opp_3": 2}},
            "p",
        )
        assert result[1] == "40.0"  # 4/10
        assert result[4] == "(4/10)"

    def test_WMsF_no_flop_branch(self) -> None:
        """saw_f == 0 takes the no-data branch."""
        result = WMsF({"p": {"saw_f": 0, "saw_1": 0, "w_w_s_1": 0}}, "p")
        assert result[1] == "-"
        assert result[2] == "WMsF=-"

    def test_triple_barrel_else_branch(self) -> None:
        """A negative cb_opp keeps opportunities != 0 but skips the cb-rate path.

        This is the only way to reach the ``triple_barrel_count = 0`` else branch:
        ``min()`` is non-zero yet not all three cb_opp values are > 0.
        """
        result = triple_barrel(
            {"p": {"cb_opp_1": -1, "cb_1": 0, "cb_opp_2": 5, "cb_2": 0, "cb_opp_3": 5, "cb_3": 0}},
            "p",
        )
        assert result[0] == 0.0  # triple_barrel_count = 0 / opportunities

    def test_player_note_match_branch(self) -> None:
        """A matching screen_name sets player_id and returns the note icon."""
        result = player_note({1: {"screen_name": "hero"}}, "hero")
        assert result == ("📝", "📝", "📝", "📝", "📝", "Player note icon")

    def test_player_note_exception_branch(self) -> None:
        """A non-dict entry makes data.get() raise, hitting the except branch."""
        result = player_note({1: "not-a-dict"}, "hero")
        assert result == ("📝", "📝", "📝", "📝", "📝", "Player note icon")


class TestExceptionHandlers:
    """Block B — reach the ``except (KeyError, ValueError, TypeError)`` handlers."""

    def test_fbr_exception(self) -> None:
        result = fbr({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "fbr=NA"

    def test_f_dbr1_exception(self) -> None:
        result = f_dbr1({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "f_dbr1=NA"

    def test_a_freq2_exception(self) -> None:
        result = a_freq2({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "a2=NA"

    def test_a_freq3_exception(self) -> None:
        result = a_freq3({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "a3=NA"

    def test_a_freq4_exception(self) -> None:
        result = a_freq4({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "a4=NA"

    def test_a_freq_123_exception(self) -> None:
        result = a_freq_123({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "afq=NA"

    def test_agg_fact_exception(self) -> None:
        result = agg_fact({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "afa=NA"

    def test_agg_fact_pct_exception(self) -> None:
        result = agg_fact_pct({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "afap=NA"

    def test_open_limp_exception(self) -> None:
        result = open_limp({}, "missing")
        assert result[1] == "-"
        assert result[2] == "open_limp=-"

    def test_check_raise_frequency_exception(self) -> None:
        result = check_raise_frequency({}, "missing")
        assert result[1] == "NA"
        assert result[2] == "CRF=NA"

    def test_game_abbr_exception(self, monkeypatch) -> None:
        """A hand instance whose gametype lacks 'category' triggers the handler."""

        class FakeHand:
            def __contains__(self, key) -> bool:
                return True  # so `"gametype" not in hand_instance` is False

            gametype = {}  # missing "category" -> KeyError when indexed

        monkeypatch.setattr(Stats, "_get_hand_instance", lambda: FakeHand())
        result = game_abbr({}, "p")
        assert result[2] == "game=NA"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
