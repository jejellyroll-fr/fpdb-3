"""Unit tests for remembering which game a Winamax Fast-Fold pool deals.

The window states the game only to a process holding macOS Accessibility, which
packaged builds do not hold. What an imported hand proved has to survive, or the
Fast-Fold HUD pays a hand's delay on every pool, every session.
"""

from __future__ import annotations

from fpdb_3_legacy.winamax_pool_games import MAX_POOLS, WinamaxPoolGames, pool_name


class TestPoolName:
    def test_the_client_window_index_is_not_part_of_the_pool(self) -> None:
        assert pool_name("Colorado 4") == "Colorado"
        assert pool_name("Colorado") == "Colorado"
        assert pool_name("Casablanca 12") == "Casablanca"

    def test_a_number_inside_the_name_is_kept(self) -> None:
        assert pool_name("Colorado 2 Deluxe") == "Colorado 2 Deluxe"

    def test_a_name_that_merely_ends_in_a_digit_is_kept(self) -> None:
        """The client always puts a space before the window index."""
        assert pool_name("Pool4") == "Pool4"

    def test_nothing_is_not_a_pool(self) -> None:
        assert pool_name("") == ""
        assert pool_name(None) == ""


class TestRecall:
    def test_every_window_of_a_pool_shares_what_was_learned(self, tmp_path) -> None:
        store = WinamaxPoolGames(tmp_path / "pools.json")

        store.remember("Colorado", "omahahi")

        assert store.get("Colorado 4") == "omahahi"
        assert store.get("Colorado 1") == "omahahi"

    def test_an_unknown_pool_is_not_guessed(self, tmp_path) -> None:
        store = WinamaxPoolGames(tmp_path / "pools.json")

        assert store.get("Casablanca 6") is None

    def test_what_a_hand_proved_outlives_the_session(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        WinamaxPoolGames(path).remember("Colorado 4", "omahahi")

        assert WinamaxPoolGames(path).get("Colorado 2") == "omahahi"

    def test_a_pool_that_changes_game_is_re_learned(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        store = WinamaxPoolGames(path)

        store.remember("Colorado", "holdem")
        store.remember("Colorado", "omahahi")

        assert WinamaxPoolGames(path).get("Colorado") == "omahahi"

    def test_nothing_is_recorded_without_both_halves(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        store = WinamaxPoolGames(path)

        store.remember("Colorado", "")
        store.remember("", "omahahi")

        assert not path.exists()

    def test_the_file_cannot_grow_without_bound(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        store = WinamaxPoolGames(path)

        for i in range(MAX_POOLS + 10):
            store.remember(f"Pool{i}", "holdem")

        reloaded = WinamaxPoolGames(path)
        kept = [i for i in range(MAX_POOLS + 10) if reloaded.get(f"Pool{i}") is not None]
        assert len(kept) == MAX_POOLS
        # The most recent survive; the pools longest untouched are dropped.
        assert kept[0] == 10
        assert kept[-1] == MAX_POOLS + 9


class TestDegradedStorage:
    def test_a_corrupt_file_is_ignored_rather_than_fatal(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        path.write_text("{not json", encoding="utf-8")

        store = WinamaxPoolGames(path)

        assert store.get("Colorado") is None
        store.remember("Colorado", "holdem")
        assert store.get("Colorado") == "holdem"

    def test_a_file_holding_something_else_is_ignored(self, tmp_path) -> None:
        path = tmp_path / "pools.json"
        path.write_text('["Colorado"]', encoding="utf-8")

        assert WinamaxPoolGames(path).get("Colorado") is None

    def test_no_config_directory_still_works_in_memory(self) -> None:
        store = WinamaxPoolGames(None)

        store.remember("Colorado", "omahahi")

        assert store.get("Colorado 4") == "omahahi"

    def test_an_unwritable_path_does_not_raise(self, tmp_path) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("", encoding="utf-8")
        store = WinamaxPoolGames(blocker / "sub" / "pools.json")

        store.remember("Colorado", "omahahi")

        assert store.get("Colorado") == "omahahi"
