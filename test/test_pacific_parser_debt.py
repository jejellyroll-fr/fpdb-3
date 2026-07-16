from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker


def test_supported_pacific_games_do_not_require_stud_bring_in() -> None:
    supported_games = PacificPoker.__new__(PacificPoker).readSupportedGames()

    assert supported_games
    assert {base for _, base, _ in supported_games} == {"hold"}
    assert {game_type for game_type, _, _ in supported_games} == {"ring", "tour"}
