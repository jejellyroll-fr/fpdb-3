"""Unit test verifying that legacy hand import does not create duplicate HUDs when FastFold HUD is active."""

from unittest.mock import MagicMock

from fpdb_3_legacy import HUD_main


def test_create_new_hud_skips_when_fast_fold_hud_active():
    """Verify that _create_new_hud returns early if a FastFold HUD is active for temp_key."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    mock_fast_fold_hud = MagicMock()
    mock_fast_fold_hud.is_fast_fold = True
    hud_main.hud_dict = {"Bucarest 5 #330784": mock_fast_fold_hud}

    # Attempt to create legacy HUD for "Bucarest 5" without resolved_window
    res = hud_main._create_new_hud(
        new_hand_id="677",
        temp_key="Bucarest 5",
        table_info=("Bucarest 5", 6, "holdem", "ring", None, None, None),
        site_id=1,
        num_seats=6,
        hud_site_name="Winamax",
        resolved_window=None,
    )

    # Must return None early without adding "Bucarest 5" to hud_dict
    assert res is None
    assert "Bucarest 5" not in hud_main.hud_dict
