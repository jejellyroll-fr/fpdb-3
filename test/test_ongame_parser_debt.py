from pathlib import Path

import pytest

from fpdb_3_legacy.OnGameToFpdb import OnGame

ROOT = Path(__file__).resolve().parents[1]
ONGAME = ROOT / "regression-test-files" / "cash" / "OnGame" / "Flop"


@pytest.mark.parametrize(
    ("filename", "currency"),
    [
        ("NLHE-6max-play-0.25-0.50-201204.txt", "play"),
        ("PLO8-USD-0.50-0.50-201111.txt", "USD"),
        ("PLO-6max-EUR-1-1-2011002.Sample.txt", "EUR"),
    ],
)
def test_determine_game_type_distinguishes_real_and_play_money(
    filename: str,
    currency: str,
) -> None:
    hand_history = (ONGAME / filename).read_text(encoding="utf-8")

    game_type = OnGame.determineGameType(OnGame.__new__(OnGame), hand_history)

    assert game_type["currency"] == currency
