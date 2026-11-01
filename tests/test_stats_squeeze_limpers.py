#!/usr/bin/env python3
"""Tests for the squeeze-defense and limpers-faced HUD stats."""

from __future__ import annotations

import fpdb_3_legacy.Stats as Stats


def test_fold_to_squeeze_percentage():
    sd = {7: {"sqzdef_opp": "4", "sqzdef_fold": "3"}}
    res = Stats.fold_to_squeeze(sd, 7)
    assert abs(res[0] - 0.75) < 1e-9
    assert res[1] == "75.0"
    assert res[2] == "FvSq=75.0%"
    assert res[4] == "(3/4)"
    assert res[5] == "% fold to squeeze"


def test_fold_to_squeeze_no_opportunity():
    assert Stats.fold_to_squeeze({1: {"sqzdef_opp": "0", "sqzdef_fold": "0"}}, 1)[1] in ("-", "NA")
    assert Stats.fold_to_squeeze({1: {}}, 1)[1] in ("-", "NA")


def test_face_limpers_average():
    sd = {2: {"n": "50", "face_limpers": "40"}}
    res = Stats.face_limpers(sd, 2)
    assert abs(res[0] - 0.8) < 1e-9
    assert res[1] == "0.8"
    assert res[2] == "FLmp=0.8"
    assert res[4] == "(40/50)"
    assert res[5] == "avg limpers faced preflop"


def test_face_limpers_no_hands_returns_no_data():
    assert Stats.face_limpers({1: {"n": "0", "face_limpers": "0"}}, 1)[1] in ("-", "NA")
    assert Stats.face_limpers({1: {}}, 1)[1] in ("-", "NA")


def test_both_registered_in_statlist():
    assert "fold_to_squeeze" in Stats.STATLIST
    assert "face_limpers" in Stats.STATLIST
