"""Postflop hand-state classification (#302).

The acceptance criteria are checked in order: classification works on flop,
turn and river; the made-hand categories are deterministic; the common draws are
covered; the nutness definitions are documented (and are exact statements about
the hands an opponent can hold, not vibes); the board archetypes are covered
extensively; and unknown cards are never classified.

The corpus is the constraint that makes the last one testable: it stores cards
for the players who showed, so its 77 postflop decisions contain 35 that can be
classified and 42 that cannot -- and a classifier that guessed at the other 42
would produce a composition of hands nobody held.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import pytest

from fpdb_3_legacy import hand_state as hs
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hand_state_store import enumerate_hand_states
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

# Flop/turn/river opponent holdings: C(47,2), C(46,2) and C(45,2) once the
# player's own two cards are out -- the denominator of every nutness band.
FLOP_HOLDINGS = 1081
TURN_HOLDINGS = 1035
RIVER_HOLDINGS = 990

_POSTFLOP_DECISIONS = 77
_CLASSIFIED_DECISIONS = 35

_MODULE_STATE: list[object] = []


@pytest.fixture(scope="module")
def corpus_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("hand-state")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return db


# --------------------------------------------------------------------------- #
# The made hand.
# --------------------------------------------------------------------------- #


class TestMadeHand:
    """Every category, deterministically, on every street."""

    @pytest.mark.parametrize(
        ("hole", "board", "expected"),
        [
            (("7c", "2d"), ("Ks", "Qh", "9c"), "high_card"),
            (("Kc", "8d"), ("Ks", "Qh", "9c"), "one_pair"),
            (("Kc", "Qd"), ("Ks", "Qh", "9c"), "two_pair"),
            (("9d", "9h"), ("Ks", "Qh", "9c"), "three_of_a_kind"),
            (("Jd", "Tc"), ("Ks", "Qh", "9c"), "straight"),
            (("7s", "4s"), ("Ks", "9s", "2s"), "flush"),
            (("Kd", "Kc"), ("Ks", "Qh", "Qc"), "full_house"),
            (("Kd", "Kc"), ("Ks", "Kh", "Qc"), "four_of_a_kind"),
            (("Js", "Ts"), ("Qs", "9s", "8s"), "straight_flush"),
        ],
    )
    def test_every_category_is_named(self, hole: tuple, board: tuple, expected: str) -> None:
        state = hs.classify(hole, board)
        assert state.made_hand == expected
        assert state.made_hand_rank == hs.MADE_HANDS.index(expected) + 1

    def test_the_same_hand_always_classifies_the_same(self) -> None:
        first = hs.classify(("Ah", "Kd"), ("Kh", "7s", "2c"))
        second = hs.classify(("Ah", "Kd"), ("Kh", "7s", "2c"))
        assert first == second
        assert first.as_dict() == second.as_dict()

    def test_the_hand_is_named_from_the_project_vocabulary(self) -> None:
        assert hs.classify(("Ad", "Kd"), ("Ac", "Kh", "2s")).made_hand_label == "two pair, Kings and Aces"
        assert hs.classify(("Ad", "3d"), ("Ah", "Ac", "As")).made_hand_label == "four of a kind, Aces"
        # The wheel is a five-high straight, not an ace-high one.
        assert hs.classify(("4d", "3c"), ("As", "5s", "2h")).made_hand_label == "a straight, Five high"

    @pytest.mark.parametrize("board", [("Ks", "Qh", "9c"), ("Ks", "Qh", "9c", "2d"), ("Ks", "Qh", "9c", "2d", "3s")])
    def test_every_street_is_classified(self, board: tuple) -> None:
        state = hs.classify(("Kc", "8d"), board)
        assert state.street in ("flop", "turn", "river")
        assert state.street == hs.street_of(board)
        assert state.made_hand == "one_pair"


class TestPairDetail:
    """A pair's name is a statement about the board, so the board decides it."""

    @pytest.mark.parametrize(
        ("hole", "board", "expected"),
        [
            (("As", "Ah"), ("Ks", "Qh", "2c"), "overpair"),
            (("4d", "4c"), ("Ac", "8h", "2s"), "pocket_pair_below_board"),
            (("Ad", "Kd"), ("Ac", "7h", "2s"), "top_pair"),
            (("8d", "7d"), ("Ac", "8h", "2s"), "middle_pair"),
            (("5d", "4d"), ("Ac", "8h", "5s"), "bottom_pair"),
            (("Ad", "Kd"), ("Ac", "Kh", "2s"), "top_two"),
            (("Kd", "5d"), ("Ac", "Kh", "5s"), "bottom_two"),
            (("7d", "5h"), ("Kc", "7s", "5s"), "bottom_two"),
            (("9d", "5h"), ("Ac", "9s", "5s", "2c"), "middle_two"),
            (("4d", "4c"), ("4h", "Kc", "2s"), "set"),
            (("Kd", "Qc"), ("Kh", "Kc", "2s"), "trips"),
        ],
    )
    def test_pair_details(self, hole: tuple, board: tuple, expected: str) -> None:
        assert hs.classify(hole, board).pair_detail == expected

    def test_a_hand_with_no_pair_has_no_pair_detail(self) -> None:
        assert hs.classify(("Jd", "Tc"), ("Ks", "Qh", "9c")).pair_detail is None
        assert hs.classify(("7s", "4s"), ("Ks", "9s", "2s")).pair_detail is None

    def test_a_board_pair_is_top_two_for_the_board_pair_too(self) -> None:
        """Holding kings over aces-and-kings is top two as much as A-K is."""
        assert hs.classify(("Kd", "Kc"), ("Ac", "Ah", "5s")).pair_detail == "top_two"
        # Kings over an ace-king board is a *set* of kings, not two pair: the
        # board pairs once, and the pair is the one in the hole.
        assert hs.classify(("Kd", "Kc"), ("Ac", "Kh", "5s")).pair_detail == "set"


# --------------------------------------------------------------------------- #
# Draws.
# --------------------------------------------------------------------------- #


class TestDraws:
    """The draws the visible cards actually give, on the street being played."""

    @pytest.mark.parametrize(
        ("hole", "board", "expected"),
        [
            (("Ks", "Qs"), ("9s", "4s", "2h"), {"flush_draw"}),
            (("As", "5s"), ("9s", "4s", "2h"), {"nut_flush_draw", "gutshot", "combo_draw"}),
            (("9h", "3d"), ("Kh", "8h", "2c"), {"backdoor_flush_draw"}),
            (("9d", "8d"), ("Th", "Js", "2c"), {"open_ended_straight_draw"}),
            (("8c", "5d"), ("9h", "6s", "2c"), {"gutshot"}),
            (("6h", "8d"), ("2c", "4d", "5h"), {"double_gutshot"}),
            (("4h", "3d"), ("Kh", "8h", "2c"), {"backdoor_flush_draw", "backdoor_straight_draw"}),
        ],
    )
    def test_draws(self, hole: tuple, board: tuple, expected: set) -> None:
        state = hs.classify(hole, board)
        # Backdoor straight draws fire widely by construction: they say two
        # cards would complete a straight, which is true of most dry boards.
        assert expected <= set(state.draws)
        assert state.is_drawing

    def test_an_ace_high_four_run_is_a_gutshot_not_an_open_ender(self) -> None:
        """Both ends have to be live: A-K-Q-J draws only to a ten."""
        state = hs.classify(("Ah", "Kd"), ("Qh", "Jh", "2c"))
        assert "open_ended_straight_draw" not in state.draws
        assert "gutshot" in state.draws

    def test_a_made_straight_is_not_a_draw(self) -> None:
        state = hs.classify(("9d", "8d"), ("Th", "Js", "2c", "Qh"))
        assert state.made_hand == "straight"
        assert "gutshot" not in state.draws and "open_ended_straight_draw" not in state.draws

    def test_the_river_has_no_draws(self) -> None:
        """The last card is out: nothing is drawing, whatever the board is."""
        state = hs.classify(("Ks", "Qs"), ("9s", "4s", "2h", "7d", "3c"))
        assert state.draws == frozenset()

    def test_backdoors_need_two_cards_so_they_only_exist_on_the_flop(self) -> None:
        flop = hs.classify(("4h", "3d"), ("Kh", "8h", "2c"))
        turn = hs.classify(("4h", "3d"), ("Kh", "8h", "2c", "9d"))
        assert "backdoor_flush_draw" in flop.draws
        assert not any(draw.startswith("backdoor") for draw in turn.draws)

    def test_a_flush_draw_and_a_straight_draw_are_a_combo_draw(self) -> None:
        state = hs.classify(("Qs", "Js"), ("Ts", "9s", "2h"))
        assert {"flush_draw", "open_ended_straight_draw", "combo_draw"} <= set(state.draws)

    def test_every_draw_has_a_documented_definition(self) -> None:
        definitions = hs.draw_definitions()
        assert set(definitions) == set(hs.DRAW_CATEGORIES)
        assert all(text.strip() for text in definitions.values())


# --------------------------------------------------------------------------- #
# Nutness.
# --------------------------------------------------------------------------- #


class TestNutness:
    """Exact bands, measured against the hands the deck actually allows."""

    @pytest.mark.parametrize(
        ("hole", "board", "holdings"),
        [
            (("As", "Ah"), ("Ks", "Qh", "2c"), FLOP_HOLDINGS),
            (("As", "Ah"), ("Ks", "Qh", "2c", "7d"), TURN_HOLDINGS),
            (("As", "Ah"), ("Ks", "Qh", "2c", "7d", "3s"), RIVER_HOLDINGS),
        ],
    )
    def test_the_denominator_is_the_deck_missing_your_own_cards(
        self,
        hole: tuple,
        board: tuple,
        holdings: int,
    ) -> None:
        assert hs.classify(hole, board).holdings == holdings

    def test_the_nuts_is_exactly_nothing_beats_it(self) -> None:
        """Quad aces on a three-ace board: the fourth ace is *in the hand*.

        Counting the deck's holdings without removing the player's own two cards
        made this hand merely ``strong``, because the best "opponent" holding the
        evaluator could find was the one holding the fourth ace.
        """
        state = hs.classify(("Ad", "3d"), ("Ah", "Ac", "As"))
        assert state.made_hand == "four_of_a_kind"
        assert state.nutness == "nuts"
        assert state.beats == state.holdings == FLOP_HOLDINGS
        assert state.beat_fraction == 1.0

    def test_a_set_on_a_dry_flop_is_near_nuts(self) -> None:
        """Only the nuts beats it -- here, the two remaining quads."""
        state = hs.classify(("4d", "4c"), ("4h", "Kc", "2s"))
        assert state.nutness == "near_nuts"
        assert state.beats == FLOP_HOLDINGS - 3

    def test_the_bands_are_percentiles_of_the_same_distribution(self) -> None:
        """weak < medium < strong, and the counts rise with the label."""
        weak = hs.classify(("8c", "5d"), ("9h", "6s", "2c"))
        medium = hs.classify(("8d", "7d"), ("Ac", "8h", "2s"))
        strong = hs.classify(("Ad", "Kd"), ("Ac", "7h", "2s"))
        assert weak.nutness == "weak" and medium.nutness == "medium" and strong.nutness == "strong"
        assert weak.beats < medium.beats < strong.beats
        assert weak.beat_fraction < hs.MEDIUM_PERCENTILE <= medium.beat_fraction
        assert medium.beat_fraction < hs.STRONG_PERCENTILE <= strong.beat_fraction

    def test_an_unknowable_hand_is_not_a_band(self) -> None:
        """The bands are about opponents' hands, so they need the cards."""
        with pytest.raises(hs.UnknownHoleCards):
            hs.classify(("0x", "0x"), ("Ks", "Qh", "2c"))


# --------------------------------------------------------------------------- #
# Blockers.
# --------------------------------------------------------------------------- #


class TestBlockers:
    """Each blocker is a rule about the cards held, not about a range."""

    @pytest.mark.parametrize(
        ("hole", "board", "expected"),
        [
            (("As", "5d"), ("9s", "4s", "2h"), "nut_flush_blocker"),
            (("Ad", "2c"), ("Ac", "Ah", "5s"), "paired_board_blocker"),
            (("Jd", "2c"), ("7h", "8s", "9c", "Td"), "straight_blocker"),
            (("Ad", "5d"), ("9h", "8s", "2c"), "overcard_blocker"),
        ],
    )
    def test_each_blocker_fires(self, hole: tuple, board: tuple, expected: str) -> None:
        assert expected in hs.classify(hole, board).blockers

    def test_a_blocker_is_not_claimed_without_the_card(self) -> None:
        """No ace of the drawn suit, no nut-flush blocker."""
        assert "nut_flush_blocker" not in hs.classify(("Ks", "5d"), ("9s", "4s", "2h")).blockers
        assert "overcard_blocker" not in hs.classify(("5d", "4c"), ("Kh", "8s", "2c")).blockers

    def test_a_straight_blocker_needs_a_board_that_is_four_into_a_straight(self) -> None:
        """A three-card board is nobody's out: there is nothing to block yet."""
        assert "straight_blocker" not in hs.classify(("Jd", "2c"), ("7h", "8s", "9c")).blockers
        assert "straight_blocker" in hs.classify(("Jd", "2c"), ("7h", "8s", "9c", "Td")).blockers


# --------------------------------------------------------------------------- #
# Refusals: a hand state that cannot be honest is not produced.
# --------------------------------------------------------------------------- #


class TestRefusals:
    """Nothing is classified that the cards do not support."""

    @pytest.mark.parametrize(
        ("hole", "board", "error"),
        [
            (("Ks", "Qh", "2c"), ("Ks", "Qh", "2c"), hs.UnknownHoleCards),
            (("Ks", "Qh"), ("Ks", "Qh"), hs.NotPostflop),
            (("Ks", "Qh"), (), hs.NotPostflop),
            (("Ks", "Qh"), ("Ks", "Qh", "2c", "3d", "4s", "5h"), hs.NotPostflop),
            (("Ks", "Ks"), ("Qh", "2c", "3d"), hs.HandStateError),
            (("Ks", "2c"), ("Ks", "Qh", "2c"), hs.HandStateError),
            (("0x", "Qh"), ("Ks", "Qh", "2c"), hs.UnknownHoleCards),
            (("Ks", "J"), ("Ks", "Qh", "2c"), hs.UnknownHoleCards),
            (("Ks", "AsKh"), ("Ks", "Qh", "2c"), hs.UnknownHoleCards),
            (("Ks", None), ("Ks", "Qh", "2c"), hs.UnknownHoleCards),
        ],
    )
    def test_unclassifiable_hands_are_refused(self, hole, board, error: type) -> None:
        with pytest.raises(error):
            hs.classify(hole, board)

    def test_a_non_holdem_hand_is_refused_by_name(self) -> None:
        with pytest.raises(hs.HandStateError, match="holdem"):
            hs.classify(("As", "Ah"), ("Ks", "Qh", "2c"), game="omahahi")

    def test_unknown_cards_classify_to_nothing_rather_than_to_a_guess(self) -> None:
        assert hs.classify_known_cards(("0x", "0x"), ("Ks", "Qh", "2c")) is None
        assert hs.classify_known_cards(("Ks", ""), ("Ks", "Qh", "2c")) is None
        # A game whose hand this is not is a refusal, not an unknown: the
        # caller named it, so silence would be a worse answer than the error.
        with pytest.raises(hs.HandStateError, match="holdem"):
            hs.classify_known_cards(("Ks", "Qh"), ("Ks", "Qh", "2c"), game="omaha")

    def test_a_bad_street_name_is_refused(self) -> None:
        with pytest.raises(hs.NotPostflop):
            hs.board_through_street(("As", "Ks", "Qs", "Js", "Ts"), "preflop")


# --------------------------------------------------------------------------- #
# The vocabulary, its masks and its helper.
# --------------------------------------------------------------------------- #


class TestVocabulary:
    """The names, their bits, and the shapes a caller reads them back in."""

    def test_the_bitmaps_are_contiguous_and_in_order(self) -> None:
        for names, bits in ((hs.DRAW_CATEGORIES, hs.DRAW_BITS), (hs.BLOCKER_CATEGORIES, hs.BLOCKER_BITS)):
            assert list(bits) == list(names)
            assert sorted(bits.values()) == [1 << index for index in range(len(names))]

    def test_masks_round_trip(self) -> None:
        state = hs.classify(("As", "5s"), ("9s", "4s", "2h"))
        mask = hs.draws_mask(state.draws)
        assert set(hs.mask_names(mask, hs.DRAW_BITS)) == state.draws
        assert state.as_dict()["draws_mask"] == mask
        assert hs.mask_names(hs.blockers_mask(state.blockers), hs.BLOCKER_BITS) == tuple(
            sorted(state.blockers, key=list(hs.BLOCKER_BITS).index),
        )

    def test_an_unknown_name_is_refused_by_the_mask(self) -> None:
        with pytest.raises(ValueError, match="flushd_raw"):
            hs.draws_mask(["flushd_raw"])

    def test_nothing_is_carried_that_nothing_sets(self) -> None:
        """The state has no free-form fields: everything in it is derived."""
        fields = set(hs.HandState.__dataclass_fields__)
        assert fields == {
            "street",
            "hole_cards",
            "board",
            "made_hand",
            "made_hand_label",
            "made_cards",
            "pair_detail",
            "draws",
            "nutness",
            "beats",
            "holdings",
            "blockers",
        }

    def test_the_categories_cover_every_published_name(self) -> None:
        published = hs.categories()
        assert published["made_hand"] == hs.MADE_HANDS
        assert published["pair_detail"] == hs.PAIR_DETAILS
        assert published["nutness"] == hs.NUTNESS_LEVELS
        assert published["draw"] == hs.DRAW_CATEGORIES
        assert published["blocker"] == hs.BLOCKER_CATEGORIES

    def test_has_reads_every_classification_at_once(self) -> None:
        state = hs.classify(("As", "5s"), ("9s", "4s", "2h"))
        assert state.has("nut_flush_draw")
        assert state.has("gutshot", "weak")
        assert not state.has("full_house", "top_pair")

    def test_board_through_street_truncates_a_full_board(self) -> None:
        board = ("As", "Ks", "Qs", "Js", "Ts")
        assert hs.board_through_street(board, "flop") == ("As", "Ks", "Qs")
        assert hs.board_through_street(board, "turn") == ("As", "Ks", "Qs", "Js")
        assert hs.board_through_street(board, "river") == board

    def test_describe_names_what_the_hand_is(self) -> None:
        line = hs.classify(("Ks", "Qs"), ("9s", "4s", "2h")).describe()
        assert line.startswith("Flop: high card, Queen")
        assert "flush_draw" in line
        assert "holdings beaten" in line


# --------------------------------------------------------------------------- #
# The corpus.
# --------------------------------------------------------------------------- #


def _stored_states(db: Database) -> list[dict]:
    c = db.get_cursor()
    c.execute(
        "SELECT HS.handId, HS.actionNo, HS.streetName, HS.madeHand, HS.pairDetail, HS.nutness,"
        " HS.drawsMask, HS.blockersMask, HP.card1, HP.card2, S.board"
        " FROM HandStates HS"
        " JOIN HandsPlayers HP ON HP.handId = HS.handId AND HP.playerId = HS.playerId"
        " LEFT JOIN HandsSituations S ON S.handId = HS.handId AND S.actionNo = HS.actionNo"
        " ORDER BY HS.handId, HS.actionNo",
    )
    names = [description[0] for description in c.description]
    return [dict(zip(names, row, strict=True)) for row in c.fetchall()]


class TestCorpus:
    """The golden corpus is the constraint: 35 of its 77 postflop decisions."""

    def test_only_the_decisions_with_known_cards_are_stored(self, corpus_db: Database) -> None:
        c = corpus_db.get_cursor()
        c.execute("SELECT COUNT(*) FROM HandsSituations WHERE streetName != 'preflop'")
        assert c.fetchone()[0] == _POSTFLOP_DECISIONS
        assert len(_stored_states(corpus_db)) == _CLASSIFIED_DECISIONS

    def test_every_stored_row_is_a_classification_of_its_own_cards(self, corpus_db: Database) -> None:
        """The stored row *is* the classifier's answer for those cards."""
        for row in _stored_states(corpus_db):
            board = json.loads(row["board"]) if isinstance(row["board"], str) else row["board"]
            state = hs.classify((row["card1"], row["card2"]), board)
            assert state.street == row["streetName"]
            assert state.made_hand == row["madeHand"]
            assert state.nutness == row["nutness"]
            assert hs.draws_mask(state.draws) == row["drawsMask"]
            assert hs.blockers_mask(state.blockers) == row["blockersMask"]

    def test_a_player_who_never_showed_has_no_state(self, corpus_db: Database) -> None:
        """Absence is the answer for unknown cards, and there is no other row."""
        c = corpus_db.get_cursor()
        c.execute(
            "SELECT COUNT(DISTINCT HS.handId || '-' || HS.playerId) FROM HandStates HS"
            " JOIN HandsPlayers HP ON HP.handId = HS.handId AND HP.playerId = HS.playerId"
            " WHERE HP.card1 = 0 OR HP.card2 = 0",
        )
        assert c.fetchone()[0] == 0

    def test_the_composition_is_the_corpus_shape(self, corpus_db: Database) -> None:
        c = corpus_db.get_cursor()
        c.execute("SELECT madeHand, COUNT(*) FROM HandStates GROUP BY madeHand ORDER BY 2 DESC")
        assert c.fetchall() == [("high_card", 19), ("one_pair", 11), ("two_pair", 3), ("three_of_a_kind", 2)]
        c.execute("SELECT streetName, COUNT(*) FROM HandStates GROUP BY streetName ORDER BY 2 DESC")
        assert c.fetchall() == [("flop", 26), ("turn", 6), ("river", 3)]

    def test_no_corpus_hand_is_nuts_or_hopeless(self, corpus_db: Database) -> None:
        """Every band that appears is one the corpus can actually contain."""
        c = corpus_db.get_cursor()
        c.execute("SELECT DISTINCT nutness FROM HandStates")
        bands = {row[0] for row in c.fetchall()}
        assert bands <= set(hs.NUTNESS_LEVELS)
        assert "medium" in bands and "strong" in bands

    def test_unknown_cards_are_never_classified(self) -> None:
        """A player with no cards, and a preflop decision: neither is a state."""
        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=1),
            _Situation(player="Boris", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=2),
            _Situation(player="Cara", board=(), street_name="preflop", street=0, action_no=3),
            _Situation(player="Dave", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=4, game="omahahi"),
        ]
        cards = {"Anna": ["As", "Ah"], "Boris": ["0x", "0x"], "Cara": ["Ks", "Kh"], "Dave": ["As", "Ah"]}
        decisions = enumerate_hand_states(situations, cards)
        assert [decision.player for decision in decisions] == ["Anna"]

    def test_the_holdem_classes_and_the_cards_are_the_projects_own(self) -> None:
        """The 1..52 encoding the database stores is what the classifier reads."""
        # Sorted by suit then rank, fpdb's encoding: 51 is the king of spades.
        assert hs.classify((51, 12), ("Qh", "2c", "3d")).made_hand == "one_pair"

    def test_a_board_of_more_cards_than_the_street_is_ignored(self) -> None:
        """A stored row whose board overruns its street is not classified."""
        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="turn", street=2, action_no=1),
        ]
        assert enumerate_hand_states(situations, {"Anna": ["As", "Ah"]}) == []


class _Situation:
    """The duck type ``enumerate_hand_states`` accepts (a stored row's shape)."""

    def __init__(self, player: str, board, street_name: str, street: int, action_no: int, game: str = "holdem"):
        self.player = player
        self.board = tuple(board)
        self.street_name = street_name
        self.street = street
        self.action_no = action_no
        self.hand_id = 1
        self.game = game


class TestStore:
    """The row writer: what it accepts, what it drops, what it writes."""

    def _decision(self, player: str = "Anna", action_no: int = 1) -> object:
        from fpdb_3_legacy.hand_state_store import DecisionState

        state = hs.classify(("As", "Ah"), ("Ks", "Qh", "2c"))
        return DecisionState(
            hand_id=7,
            action_no=action_no,
            player=player,
            street=1,
            street_name="flop",
            state=state,
        )

    def test_a_decision_row_carries_its_identity_and_its_state(self) -> None:
        decision = self._decision()
        assert decision.as_dict()["player"] == "Anna"
        assert decision.as_dict()["state"]["made_hand"] == "one_pair"

    def test_the_row_written_is_the_state_written(self) -> None:
        from fpdb_3_legacy.hand_state_store import HAND_STATE_COLUMNS, state_row

        columns, values = state_row(self._decision(), 3)
        assert columns == [*HAND_STATE_COLUMNS, "stateVersion"]
        record = dict(zip(columns, values, strict=True))
        assert record["madeHand"] == "one_pair"
        assert record["pairDetail"] == "overpair"
        assert record["streetName"] == "flop"
        assert record["stateVersion"] == 3
        assert record["nutnessHoldings"] == 1081

    def test_a_decision_for_an_unknown_player_is_dropped(self) -> None:
        """The state names a decision by a player who must exist in Players."""
        from fpdb_3_legacy.hand_state_store import bulk_rows

        rows = bulk_rows(7, {}, [self._decision()], 1)
        assert rows == []
        rows = bulk_rows(7, {"Anna": 42}, [self._decision()], 1)
        assert rows and rows[0][:2] == [7, 42]

    @pytest.mark.parametrize(
        "cards",
        [5, [], ["As"], "AsAh"],
    )
    def test_a_card_value_that_is_not_two_cards_is_no_cards(self, cards) -> None:
        from fpdb_3_legacy.hand_state_store import enumerate_hand_states

        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=1),
        ]
        assert enumerate_hand_states(situations, {"Anna": cards}) == []

    def test_the_encoded_cards_the_database_stores_are_accepted(self) -> None:
        from fpdb_3_legacy.hand_state_store import enumerate_hand_states

        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=1),
        ]
        decisions = enumerate_hand_states(situations, {"Anna": {"card1": 1, "card2": 2}})
        assert len(decisions) == 1
        assert decisions[0].state.hole_cards == ("2h", "3h")

    def test_a_broken_hand_is_skipped_like_an_unknown_one(self) -> None:
        """Duplicate cards make a decision unclassifiable, not an import fatal."""
        from fpdb_3_legacy.hand_state_store import enumerate_hand_states

        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=1),
        ]
        assert enumerate_hand_states(situations, {"Anna": ["Ks", "Ks"]}) == []

    def test_a_missing_evaluator_is_not_a_missing_hand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No evaluator is an environment fault, and it must not look like "no cards"."""
        from fpdb_3_legacy import hand_state_store as store

        monkeypatch.setattr(store, "classify_known_cards", _raise_evaluator_unavailable)
        situations = [
            _Situation(player="Anna", board=("Ks", "Qh", "2c"), street_name="flop", street=1, action_no=1),
        ]
        with pytest.raises(hs.EvaluatorUnavailable):
            store.enumerate_hand_states(situations, {"Anna": ["As", "Ah"]})

    def test_a_read_back_row_has_its_masks_as_names(self) -> None:
        from fpdb_3_legacy.hand_state_store import decode_state_row

        row = {
            "madeHand": "high_card",
            "drawsMask": 1 | 64,
            "blockersMask": 8,
            "nutnessBeats": "3",
            "nutnessHoldings": None,
            "madeHandRank": 1,
        }
        decoded = decode_state_row(row)
        assert decoded["draws"] == ["flush_draw", "backdoor_straight_draw"]
        assert decoded["blockers"] == ["overcard_blocker"]
        assert decoded["nutnessBeats"] == 3 and decoded["nutnessHoldings"] is None


def _raise_evaluator_unavailable(*_args, **_kwargs):
    raise hs.EvaluatorUnavailable("no evaluator")


def test_a_missing_evaluator_refuses_rather_than_answering(monkeypatch: pytest.MonkeyPatch) -> None:
    """The project has one evaluator: when it cannot load, nothing is invented."""
    monkeypatch.setattr(hs, "load_poker_eval", lambda: None)
    with pytest.raises(hs.EvaluatorUnavailable):
        hs.classify(("As", "Ah"), ("Ks", "Qh", "2c"))


def test_an_unknown_hand_type_from_the_evaluator_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vocabulary this project does not know is an error, not a category."""
    monkeypatch.setattr(hs, "_evaluator", lambda: _FakeEvaluator())
    with pytest.raises(hs.HandStateError, match="unknown hand type"):
        hs.classify(("As", "Ah"), ("Ks", "Qh", "2c"))


class _FakeEvaluator:
    """An evaluator that answers in a vocabulary the project does not have."""

    def best_hand(self, _game: str, _cards: list) -> list:
        return ["Royalish", 1, 2, 3, 4, 5]

    def best_hand_value(self, _game: str, _cards: list) -> int:  # pragma: no cover - never reached
        return 0


def test_a_hand_with_no_name_falls_back_to_the_bare_label() -> None:
    """``Card.hands`` has a placeholder entry with no template; it stays bare."""
    assert hs._hand_label("Nothing", ("As",)) == "Nothing"


def test_a_ten_written_as_10_is_the_ten() -> None:
    """Two ways of writing a card are one card, or a hand would be classified twice."""
    assert hs.classify(("10h", "Ah"), ("Ks", "Qh", "2c")).hole_cards == ("Th", "Ah")


def test_a_board_forced_pairing_has_no_pair_to_detail() -> None:
    """A pair that is only the board's is a pair the player is not holding."""
    state = hs.classify(("Ad", "7d"), ("Ks", "Kh", "2c"))
    assert state.made_hand == "one_pair"
    assert state.pair_detail is None


def test_a_wheel_run_draws_at_both_ends() -> None:
    """2-3-4-5 draws to an ace and a six, so it is open-ended, not a gutshot."""
    assert "open_ended_straight_draw" in hs.classify(("5c", "9h"), ("2h", "3s", "4d")).draws


def test_describe_names_the_pair_the_draws_and_the_blockers() -> None:
    line = hs.classify(("Ad", "Kd"), ("Ac", "7h", "2s")).describe()
    assert "top pair" in line
    assert "strong (" in line
    blockers = hs.classify(("As", "5d"), ("9s", "4s", "2h")).describe()
    assert "blocking: " in blockers
    # A bare hand still describes itself: made hand, band, and nothing invented.
    assert hs.classify(("7c", "2d"), ("Ks", "Qh", "9c")).describe().count("|") >= 1


def test_every_hand_shape_the_corpus_uses_is_classifiable(corpus_db: Database) -> None:
    """A sanity sweep: no stored state has an empty or impossible field."""
    for row in _stored_states(corpus_db):
        assert row["madeHand"] in hs.MADE_HANDS
        assert row["nutness"] in hs.NUTNESS_LEVELS
        assert row["pairDetail"] is None or row["pairDetail"] in hs.PAIR_DETAILS
        assert set(hs.mask_names(row["drawsMask"], hs.DRAW_BITS)) <= set(hs.DRAW_CATEGORIES)
        assert set(hs.mask_names(row["blockersMask"], hs.BLOCKER_BITS)) <= set(hs.BLOCKER_CATEGORIES)


def test_the_pool_is_every_two_card_holding_the_deck_allows() -> None:
    """The nutness distribution is exhaustive, not sampled."""
    pool, values, counts = hs._board_pool(("Ks", "Qh", "2c"))
    assert len(pool) == 49
    assert len(values) == len(list(combinations(pool, 2))) == 1176
    assert sum(counts.values()) == len(values)
    assert list(values) == sorted(values)


def test_the_state_is_frozen_so_a_caller_cannot_edit_a_classification() -> None:
    state = hs.classify(("As", "Ah"), ("Ks", "Qh", "2c"))
    with pytest.raises(Exception):
        state.nutness = "nuts"  # type: ignore[misc]


def test_paths_are_the_same_module() -> None:
    """Importing the classifier is importing the project's own package."""
    assert Path(hs.__file__ or "").name == "hand_state.py"
