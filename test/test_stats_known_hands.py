"""Value tests for modern stats over a small, known hand sample."""

from fpdb_3_legacy.Stats import do_stat

# Six known flop-seen hands for Hero:
# - Hero wins money in hands 1, 3, and 6;
# - Hero reaches showdown in hands 1, 2, 4, and 6;
# - Hero faces four turn cbets and folds twice;
# - Hero faces two river cbets and folds once.
KNOWN_HAND_SAMPLE = {
    1: {
        "n": 20,
        "saw_f": 6,
        "saw_1": 6,
        "w_w_s_1": 3,
        "sd": 4,
        "f_cb_2": 2,
        "f_cb_opp_2": 4,
        "f_cb_3": 1,
        "f_cb_opp_3": 2,
        "tb_btn": 3,
        "tb_opp_btn": 10,
        "fb_co": 1,
        "fb_opp_co": 5,
        "sqz_bb": 2,
        "sqz_opp_bb": 8,
        "tb_0": 3,
        "fb_0": 1,
        "sqz_0": 2,
    },
}


def test_wwsf_value_on_known_hands() -> None:
    result = do_stat(KNOWN_HAND_SAMPLE, 1, "wwsf")

    assert result[0] == 0.5
    assert result[1] == "50.0"
    assert result[4] == "(3/6)"


def test_wtsd_value_on_known_hands() -> None:
    result = do_stat(KNOWN_HAND_SAMPLE, 1, "wtsd")

    assert result[0] == 4 / 6
    assert result[1] == "66.7"
    assert result[4] == "(4/6)"


def test_fold_to_cbet_by_street_values_on_known_hands() -> None:
    turn = do_stat(KNOWN_HAND_SAMPLE, 1, "fold_to_cbet_turn")
    river = do_stat(KNOWN_HAND_SAMPLE, 1, "fold_to_cbet_river")

    assert (turn[0], turn[1], turn[4]) == (0.5, "50.0", "(2/4)")
    assert (river[0], river[1], river[4]) == (0.5, "50.0", "(1/2)")


def test_modern_names_preserve_no_data_semantics() -> None:
    no_data = {1: {}}

    assert do_stat(no_data, 1, "wwsf")[1] == "-"
    assert do_stat(no_data, 1, "fold_to_cbet_flop")[1] == "-"
    assert do_stat(no_data, 1, "fold_to_cbet_turn")[1] == "-"
    assert do_stat(no_data, 1, "fold_to_cbet_river")[1] == "-"


def test_preflop_aggression_by_position_on_known_hands() -> None:
    three_bet = do_stat(KNOWN_HAND_SAMPLE, 1, "three_bet_btn")
    four_bet = do_stat(KNOWN_HAND_SAMPLE, 1, "four_bet_co")
    squeeze = do_stat(KNOWN_HAND_SAMPLE, 1, "squeeze_bb")

    assert (three_bet[0], three_bet[1], three_bet[4]) == (0.3, "30.0", "(3/10)")
    assert (four_bet[0], four_bet[1], four_bet[4]) == (0.2, "20.0", "(1/5)")
    assert (squeeze[0], squeeze[1], squeeze[4]) == (0.25, "25.0", "(2/8)")


def test_all_preflop_position_stats_are_registered_and_handle_no_data() -> None:
    for action in ("three_bet", "four_bet", "squeeze"):
        for position in ("bb", "sb", "btn", "co", "mp", "ep"):
            assert do_stat({1: {}}, 1, f"{action}_{position}")[1] == "-"


def test_observed_preflop_ranges_use_all_dealt_hands() -> None:
    three_bet = do_stat(KNOWN_HAND_SAMPLE, 1, "three_bet_range")
    four_bet = do_stat(KNOWN_HAND_SAMPLE, 1, "four_bet_range")
    squeeze = do_stat(KNOWN_HAND_SAMPLE, 1, "squeeze_range")

    assert (three_bet[0], three_bet[1], three_bet[4]) == (0.15, "15.0", "(3/20)")
    assert (four_bet[0], four_bet[1], four_bet[4]) == (0.05, "5.0", "(1/20)")
    assert (squeeze[0], squeeze[1], squeeze[4]) == (0.1, "10.0", "(2/20)")


def test_observed_ranges_distinguish_zero_from_no_sample() -> None:
    sample_without_actions = {1: {"n": 12}}

    assert do_stat(sample_without_actions, 1, "three_bet_range")[1] == "0.0"
    assert do_stat({1: {}}, 1, "three_bet_range")[1] == "-"
