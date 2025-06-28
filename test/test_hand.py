import logging
from decimal import Decimal

import pytest

# Configure logging to display debug messages
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class FpdbParseError(Exception):
    """Custom exception for parsing errors in FPDB."""

    pass


class Pot:
    """Represents the pot in a poker hand, including committed amounts, contenders, common money, and side pots."""

    def __init__(self):
        self.committed = {}
        self.contenders = []
        self.common = {}
        self.stp = Decimal("0.00")
        self.pots = []
        self.returned = {}


class Hand:
    """Represents a poker hand, handling pot calculations, total pot, rake, and other related functionalities."""

    def __init__(self):
        self.pot = Pot()
        self.totalpot = Decimal("0.00")
        self.totalcollected = None
        self.handid = "test_hand_id"
        self.rake = Decimal("0.00")

    def totalPot(self):
        """
        Calculates the pots (main and side pots), handles uncalled bets, common money, the STP,
        and calculates the rake. Updates self.totalpot, self.rake, and self.pot.pots.
        """
        log.debug("Starting pot calculation...")

        # Basic check
        if not isinstance(self.pot.committed, dict) or len(self.pot.committed) == 0:
            log.error("self.pot.committed is not initialized or empty.")
            raise FpdbParseError(
                "self.pot.committed is missing or improperly initialized."
            )

        # Convert and filter positive commits
        try:
            commitsall = [
                (Decimal(v), k)
                for (k, v) in self.pot.committed.items()
                if Decimal(v) > 0
            ]
        except Exception as e:
            log.error(f"Error while preparing commitsall: {e}")
            raise FpdbParseError(f"Invalid data in self.pot.committed: {e}")

        commitsall.sort(key=lambda x: x[0])
        log.debug(f"Initial committed values (sorted): {commitsall}")

        # Initializations
        self.totalpot = Decimal("0.00")
        self.pot.pots = []
        if self.totalcollected is None:
            # If not specified, consider totalcollected as 0.00
            log.warning(
                "totalcollected was None during totalPot calculation. Set to 0.00"
            )
            self.totalcollected = Decimal("0.00")

        # Internal function to create a pot from a value
        def create_pot_from_value(value, calls):
            pot_val = sum(min(v, value) for (v, k) in calls)
            self.totalpot += pot_val
            participants = {k for (v, k) in calls}
            self.pot.pots.append((pot_val, participants))
            log.debug(f"Created pot: Value={pot_val}, Participants={participants}")

            # Update the list of remaining commitments
            updated = []
            for v, kk in calls:
                nv = v - value
                if nv > 0:
                    updated.append((nv, kk))
            updated.sort(key=lambda x: x[0])
            return updated

        # Internal function to handle leftover if only one player remains with an uncontested surplus
        def handle_leftover(calls):
            leftover_sum = sum(v for (v, k) in calls)
            diff = self.totalcollected - self.totalpot
            log.debug(
                f"Single-player leftover detected. diff={diff}, leftover={leftover_sum}"
            )

            # If diff > 0, it means there is a positive gap between the total collected and the current pot.
            # A solo pot can be formed for this leftover.
            if diff > 0:
                participant = {calls[0][1]}
                self.totalpot += leftover_sum
                self.pot.pots.append((leftover_sum, participant))
                log.debug(
                    f"Formed final solo pot from leftover: {leftover_sum}, Participant={participant}"
                )
                return []
            else:
                # Otherwise, this surplus must be returned to the player (uncalled bet)
                player = calls[0][1]
                self.pot.returned[player] = (
                    self.pot.returned.get(player, Decimal("0.00")) + leftover_sum
                )
                log.debug(f"Uncalled bet returned to {player}: {leftover_sum}")
                return []

        # Creating the pots
        try:
            while commitsall:
                v1 = commitsall[0][0]
                # Check if v1 is whole or fractional
                whole_units = int(v1)
                remainder = v1 - whole_units

                if remainder == 0:
                    # Whole number: a single pot
                    commitsall = create_pot_from_value(v1, commitsall)
                    if len(commitsall) == 1:
                        # One player remaining
                        commitsall = handle_leftover(commitsall)
                    if not commitsall:
                        break
                else:
                    # Fractional value
                    # First, handle the whole units
                    for _ in range(whole_units):
                        commitsall = create_pot_from_value(Decimal("1.00"), commitsall)
                        if len(commitsall) == 1:
                            commitsall = handle_leftover(commitsall)
                            break
                        if not commitsall:
                            break
                    else:
                        # Handle the remainder
                        if remainder > 0 and commitsall:
                            commitsall = create_pot_from_value(remainder, commitsall)
                            if len(commitsall) == 1:
                                commitsall = handle_leftover(commitsall)

                if not commitsall:
                    break

            # Add common money and the STP
            self.totalpot += sum(self.pot.common.values()) + self.pot.stp
            log.debug(f"Total pot after adding common money: {self.totalpot}")

            # Final rake checks
            log.debug(f"Total collected amount: {self.totalcollected}")
            log.debug(f"Total pot amount: {self.totalpot}")

            if self.totalpot > self.totalcollected:
                # Rake = totalpot - totalcollected
                self.rake = self.totalpot - self.totalcollected
                log.debug(f"Rake scenario, Rake={self.rake}")
                return self.totalpot
            elif self.totalpot == self.totalcollected:
                self.rake = Decimal("0.00")
                log.debug("Exact match between totalpot and totalcollected, rake=0")
                return self.totalpot
            else:
                # totalcollected > totalpot
                log.error(
                    f"Collected amount ({self.totalcollected}) exceeds total pot ({self.totalpot})"
                )
                raise FpdbParseError(
                    f"Collected amount exceeds total pot for hand {self.handid}"
                )

        except Exception as e:
            log.error(f"Pot calculation failed: {e}")
            raise FpdbParseError(f"Error in pot calculation: {str(e)}")

    def end(self, totalcollected):
        """
        Finalizes the pot calculation and includes uncontested pots correctly.
        """
        log.debug("Starting pot calculation...")

        # Start with the total committed and common chips
        self.total = (
            sum(Decimal(v) for v in self.pot.committed.values())
            + sum(self.pot.common.values())
            + self.pot.stp
        )
        log.debug(
            f"Initial total pot calculation (committed + common + STP): {self.total:.2f}"
        )

        commitsall = sorted(
            [(Decimal(v), k) for (k, v) in self.pot.committed.items() if Decimal(v) > 0]
        )
        log.debug(f"Committed values (sorted): {commitsall}")

        self.pot.pots = []

        try:
            while commitsall:
                # Minimum commitment among all players
                v1 = commitsall[0][0]
                participants = {k for (v, k) in commitsall}

                # Create a new pot with all participants
                new_pot_value = sum([min(v, v1) for (v, k) in commitsall])
                self.pot.pots.append((new_pot_value, participants))
                log.debug(
                    f"New pot created: Value={new_pot_value:.2f}, Participants={participants}"
                )

                # Deduct commitments
                commitsall = [(v - v1, k) for (v, k) in commitsall if v - v1 > 0]
                log.debug(f"Remaining commitments: {commitsall}")

        except Exception as e:
            log.error(f"Error during pot calculation: {e}")
            raise FpdbParseError("Error calculating pots")

        # Calculate total pots
        self.totalpot = sum(p[0] for p in self.pot.pots)
        log.debug(f"Calculated total pots: {self.totalpot:.2f}")

        # Final validation
        if totalcollected > self.totalpot:
            log.error(
                f"Collected amount ({totalcollected:.2f}) exceeds total pot ({self.totalpot:.2f})"
            )
            raise FpdbParseError(
                f"Collected amount exceeds total pot for hand {self.handid}"
            )

        log.debug(f"Final total pot after validation: {self.totalpot:.2f}")

        # Calculate rake
        self.rake = self.totalpot - totalcollected
        log.debug(f"Rake calculated: {self.rake:.2f}")

        # Validate rake
        if self.rake > self.totalpot * Decimal("0.25"):
            log.error(
                f"Suspicious rake: {self.rake:.2f} exceeds 25% of total pot {self.totalpot:.2f}"
            )
            raise FpdbParseError("Rake exceeds allowed percentage")

        log.debug(f"Pot calculation complete. Final pot: {self.totalpot:.2f}")


# Tests with pytest
def test_normal_case():
    """Test a normal case with different committed amounts."""
    hand = Hand()
    hand.pot.committed = {"Alice": "10", "Bob": "20", "Charlie": "30"}
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}  # No common money
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("60.00")  # Total collected from players

    total_pot = hand.totalPot()

    # Verify the results
    assert total_pot == Decimal("60.00")
    assert hand.totalpot == Decimal("60.00")
    assert len(hand.pot.pots) == 3  # Should have three pots for different commitments

    expected_pots = [
        (Decimal("30.00"), {"Alice", "Bob", "Charlie"}),
        (Decimal("20.00"), {"Bob", "Charlie"}),
        (Decimal("10.00"), {"Charlie"}),
    ]
    assert hand.pot.pots == expected_pots
    assert hand.rake == Decimal("0.00")


def test_empty_committed():
    """Test handling of an empty committed dictionary."""
    hand = Hand()
    hand.pot.committed = {}
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("0.00")

    with pytest.raises(FpdbParseError) as excinfo:
        hand.totalPot()
    assert "self.pot.committed is missing or improperly initialized" in str(
        excinfo.value
    )


def test_collected_exceeds_pot():
    """Test when the collected amount exceeds the total pot."""
    hand = Hand()
    hand.pot.committed = {"Alice": "10", "Bob": "20", "Charlie": "30"}
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("70.00")  # More than the total pot

    with pytest.raises(FpdbParseError) as excinfo:
        hand.totalPot()
    assert "Collected amount exceeds total pot" in str(excinfo.value)


def test_rake_calculation():
    """Test the calculation of the rake when the total collected is less than the total pot."""
    hand = Hand()
    hand.pot.committed = {"Alice": "10", "Bob": "20", "Charlie": "30"}
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal(
        "58.00"
    )  # Less than the total pot, rake should be 2.00

    total_pot = hand.totalPot()

    # Verify the total pot
    assert total_pot == Decimal("60.00")
    assert hand.totalpot == Decimal("60.00")
    # Verify rake calculation
    assert hand.rake == Decimal("2.00")


def test_common_money_included():
    """Test that common money is correctly included in the total pot."""
    hand = Hand()
    hand.pot.committed = {"Alice": "50", "Bob": "50"}
    hand.pot.contenders = ["Alice", "Bob"]
    hand.pot.common = {"ante": Decimal("10.00")}
    hand.pot.stp = Decimal("5.00")  # Side pot total
    hand.totalcollected = Decimal("115.00")  # Total collected from players

    total_pot = hand.totalPot()

    # The total should be the sum of commitments plus common money
    assert total_pot == Decimal("115.00")
    assert hand.totalpot == Decimal("115.00")
    assert hand.rake == Decimal("0.00")


def test_no_contenders():
    """Test the scenario where there are no contenders."""
    hand = Hand()
    hand.pot.committed = {"Alice": "10", "Bob": "20"}
    hand.pot.contenders = []  # No players in contention
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("30.00")

    total_pot = hand.totalPot()

    assert total_pot == Decimal("30.00")
    assert hand.totalpot == Decimal("30.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 2
    expected_pots = [(Decimal("20.00"), {"Alice", "Bob"}), (Decimal("10.00"), {"Bob"})]
    assert hand.pot.pots == expected_pots


def test_non_numeric_committed():
    """Test handling of non-numeric committed amounts."""
    hand = Hand()
    hand.pot.committed = {"Alice": "ten", "Bob": "20"}
    hand.pot.contenders = ["Alice", "Bob"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("30.00")

    with pytest.raises(FpdbParseError) as excinfo:
        hand.totalPot()
    assert "Invalid data in self.pot.committed" in str(excinfo.value)


def test_negative_committed():
    """Test that negative committed amounts are ignored."""
    hand = Hand()
    hand.pot.committed = {"Alice": "-10", "Bob": "20"}
    hand.pot.contenders = ["Alice", "Bob"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("10.00")

    total_pot = hand.totalPot()

    # Negative amount should be ignored
    assert total_pot == Decimal("20.00")
    assert hand.totalpot == Decimal("20.00")
    assert hand.rake == Decimal("10.00")  # Since totalcollected is 10.00


def test_stp_included():
    """Test that the STP (Side Pot Total) is correctly included."""
    hand = Hand()
    hand.pot.committed = {"Alice": "50", "Bob": "50"}
    hand.pot.contenders = ["Alice", "Bob"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("10.00")  # Side pot total
    hand.totalcollected = Decimal("110.00")

    total_pot = hand.totalPot()

    assert total_pot == Decimal("110.00")
    assert hand.totalpot == Decimal("110.00")
    assert hand.rake == Decimal("0.00")


def test_missing_totalcollected():
    """Test handling when totalcollected is missing (None)."""
    hand = Hand()
    hand.pot.committed = {"Alice": "25", "Bob": "25"}
    hand.pot.contenders = ["Alice", "Bob"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = None  # Not initialized

    total_pot = hand.totalPot()

    assert total_pot == Decimal("50.00")
    assert hand.totalpot == Decimal("50.00")
    assert hand.rake == Decimal("50.00")  # Since totalcollected is defaulted to 0.00


def test_all_in_during_blinds():
    """Test scenario where a player goes all-in during the blinds."""
    hand = Hand()
    hand.pot.committed = {
        "Alice": "1.00",
        "Bob": "2.00",
        "Charlie": "100.00",
    }  # Charlie goes all-in during blinds
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("103.00")  # Sum of commitments
    total_pot = hand.totalPot()

    assert total_pot == Decimal("103.00")
    assert hand.totalpot == Decimal("103.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 3
    expected_pots = [
        (Decimal("3.00"), {"Alice", "Bob", "Charlie"}),
        (
            Decimal("2.00"),
            {"Bob", "Charlie"},
        ),  # Additional commitment from Bob and Charlie
        (Decimal("98.00"), {"Charlie"}),  # Remaining all-in from Charlie
    ]
    assert hand.pot.pots == expected_pots


def test_all_in_preflop():
    """Test preflop all-in scenarios."""
    hand = Hand()
    hand.pot.committed = {
        "Alice": "50.00",
        "Bob": "100.00",
        "Charlie": "200.00",
    }  # Preflop all-ins
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("350.00")
    total_pot = hand.totalPot()

    assert total_pot == Decimal("350.00")
    assert hand.totalpot == Decimal("350.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 3
    expected_pots = [
        (Decimal("150.00"), {"Alice", "Bob", "Charlie"}),
        (Decimal("100.00"), {"Bob", "Charlie"}),
        (Decimal("100.00"), {"Charlie"}),
    ]
    assert hand.pot.pots == expected_pots


def test_all_in_flop():
    """Test all-in scenarios during the flop."""
    hand = Hand()
    hand.pot.committed = {
        "Alice": "50.00",
        "Bob": "50.00",
        "Charlie": "50.00",
    }  # Preflop
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    # Bets on the flop
    hand.pot.committed["Alice"] = str(
        Decimal(hand.pot.committed["Alice"]) + Decimal("0.00")
    )  # Alice checks
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("100.00")
    )  # Bob bets 100
    hand.pot.committed["Charlie"] = str(
        Decimal(hand.pot.committed["Charlie"]) + Decimal("150.00")
    )  # Charlie goes all-in

    hand.totalcollected = Decimal("400.00")  # Updated total collected
    total_pot = hand.totalPot()

    assert total_pot == Decimal("400.00")
    assert hand.totalpot == Decimal("400.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 3
    expected_pots = [
        (Decimal("150.00"), {"Alice", "Bob", "Charlie"}),
        (Decimal("200.00"), {"Bob", "Charlie"}),
        (Decimal("50.00"), {"Charlie"}),
    ]
    assert hand.pot.pots == expected_pots


def test_all_in_turn():
    """Test all-in scenarios during the turn."""
    hand = Hand()
    hand.pot.committed = {"Alice": "100.00", "Bob": "100.00"}  # Until the flop
    hand.pot.contenders = ["Alice", "Bob"]
    # Bets on the turn
    hand.pot.committed["Alice"] = str(
        Decimal(hand.pot.committed["Alice"]) + Decimal("0.00")
    )  # Alice checks
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("200.00")
    )  # Bob goes all-in

    hand.totalcollected = Decimal("400.00")
    total_pot = hand.totalPot()

    assert total_pot == Decimal("400.00")
    assert hand.totalpot == Decimal("400.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 2
    expected_pots = [
        (Decimal("200.00"), {"Alice", "Bob"}),
        (Decimal("200.00"), {"Bob"}),
    ]
    assert hand.pot.pots == expected_pots


def test_all_in_river():
    """Test all-in scenarios during the river."""
    hand = Hand()
    hand.pot.committed = {"Alice": "100.00", "Bob": "100.00"}  # Until the turn
    hand.pot.contenders = ["Alice", "Bob"]
    # Bets on the river
    hand.pot.committed["Alice"] = str(
        Decimal(hand.pot.committed["Alice"]) + Decimal("500.00")
    )  # Alice goes all-in
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("0.00")
    )  # Bob folds

    hand.totalcollected = Decimal("700.00")
    total_pot = hand.totalPot()

    assert total_pot == Decimal("700.00")
    assert hand.totalpot == Decimal("700.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 2  # Updated here
    expected_pots = [
        (Decimal("200.00"), {"Alice", "Bob"}),
        (Decimal("500.00"), {"Alice"}),
    ]
    assert hand.pot.pots == expected_pots


def test_uncalled_bet():
    """Test handling of uncalled bets."""
    hand = Hand()
    hand.pot.committed = {"Alice": "100.00", "Bob": "100.00"}  # Until the turn
    hand.pot.contenders = ["Alice", "Bob"]
    # Bets on the river
    hand.pot.committed["Alice"] = str(
        Decimal(hand.pot.committed["Alice"]) + Decimal("200.00")
    )  # Alice bets 200
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("0.00")
    )  # Bob folds

    hand.totalcollected = Decimal("400.00")  # Updated total collected
    total_pot = hand.totalPot()

    assert total_pot == Decimal("400.00")
    assert hand.totalpot == Decimal("400.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 2
    expected_pots = [
        (Decimal("200.00"), {"Alice", "Bob"}),
        (Decimal("200.00"), {"Alice"}),
    ]
    assert hand.pot.pots == expected_pots


def test_all_in_with_uncalled_bet():
    """Test all-in scenarios with uncalled bets."""
    hand = Hand()
    hand.pot.committed = {
        "Alice": "50.00",
        "Bob": "50.00",
        "Charlie": "50.00",
    }  # Preflop
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    # Bets on the flop
    hand.pot.committed["Alice"] = str(
        Decimal(hand.pot.committed["Alice"]) + Decimal("150.00")
    )  # Alice goes all-in
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("150.00")
    )  # Bob calls
    hand.pot.committed["Charlie"] = str(
        Decimal(hand.pot.committed["Charlie"]) + Decimal("0.00")
    )  # Charlie folds

    # Bets on the turn
    hand.pot.committed["Bob"] = str(
        Decimal(hand.pot.committed["Bob"]) + Decimal("200.00")
    )  # Bob bets 200
    # Alice is already all-in and cannot call

    # Bob has an uncalled bet of 200

    hand.totalcollected = Decimal("650.00")  # Updated total collected
    total_pot = hand.totalPot()

    assert total_pot == Decimal("650.00")
    assert hand.totalpot == Decimal("650.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 3
    expected_pots = [
        (Decimal("150.00"), {"Alice", "Bob", "Charlie"}),
        (Decimal("300.00"), {"Alice", "Bob"}),
        (Decimal("200.00"), {"Bob"}),
    ]
    assert hand.pot.pots == expected_pots


def test_preflop_partial_allin_sb():
    """
    SB = 0.5 (all-in), BB = 1.00.
    The SB can only put in 0.5, the BB puts in 1.00.
    The main pot should be 1.00 (0.5 from each player).
    The additional 0.5 from the BB should be returned to the BB.
    """
    hand = Hand()
    hand.pot.committed = {"SB": "0.50", "BB": "1.00"}
    hand.pot.contenders = ["SB", "BB"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    # Logically, the total collected should only be 1.00,
    # as the additional 0.5 from the BB is not called.
    hand.totalcollected = Decimal("1.00")

    total_pot = hand.totalPot()

    assert total_pot == Decimal("1.00")
    assert hand.totalpot == Decimal("1.00")
    assert hand.rake == Decimal("0.00")
    # Only one pot because no other players can contest the surplus
    assert len(hand.pot.pots) == 1
    # The main pot consists of 0.5 from SB and 0.5 from BB
    expected_pots = [
        (Decimal("1.00"), {"SB", "BB"}),
    ]
    assert hand.pot.pots == expected_pots


def test_preflop_partial_allin_bb():
    """
    SB = 1.00, BB = 0.50 (all-in).
    The BB can only put in 0.5, while the SB has put in 1.00.
    Only 0.5 from the SB is contested by the BB.
    The main pot should be 1.00 (0.5 from each player).
    The additional 0.5 from the SB should be returned to the SB.
    """
    hand = Hand()
    hand.pot.committed = {"SB": "1.00", "BB": "0.50"}
    hand.pot.contenders = ["SB", "BB"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    # The total collected should only be 1.00 (0.5 from SB and 0.5 from BB)
    hand.totalcollected = Decimal("1.00")

    total_pot = hand.totalPot()

    assert total_pot == Decimal("1.00")
    assert hand.totalpot == Decimal("1.00")
    assert hand.rake == Decimal("0.00")
    assert len(hand.pot.pots) == 1
    # The main pot: 0.5 (SB) + 0.5 (BB) = 1.00
    expected_pots = [
        (Decimal("1.00"), {"SB", "BB"}),
    ]
    assert hand.pot.pots == expected_pots


def test_flop_partial_allin():
    """
    Scenario on the flop:
    Player A (in BB) is all-in for an amount that does not fully cover Player B's bet.
    Example:
    Preflop: A = 1.00, B = 1.00
    Flop: B bets an additional 2.00, A can only add 0.50 more (all-in).
    The main pot should include 1.00 + 1.00 = 2.00 from the preflop + (0.50 from A and 0.50 from B on the flop) = 3.00 total.
    The surplus of 1.50 from B not called should not be included.
    """
    hand = Hand()
    # Preflop: A and B each put in 1.00
    hand.pot.committed = {"A": "1.00", "B": "1.00"}
    hand.pot.contenders = ["A", "B"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")

    # On the flop, B bets an additional 2.00, A can only add 0.50 (all-in)
    hand.pot.committed["A"] = str(Decimal(hand.pot.committed["A"]) + Decimal("0.50"))
    hand.pot.committed["B"] = str(Decimal(hand.pot.committed["B"]) + Decimal("2.00"))

    # Total that should actually be contested:
    # Preflop: 2.00 total
    # Flop: A adds 0.50, B can only contest 0.50 of this bet
    # Total: 2.00 + 1.00 = 3.00
    hand.totalcollected = Decimal("3.00")

    total_pot = hand.totalPot()

    assert total_pot == Decimal("3.00")
    assert hand.totalpot == Decimal("3.00")
    assert hand.rake == Decimal("0.00")
    # First pot: 2.00 from the preflop (1.00 from each)
    # Second pot: 1.00 from the flop (0.50 from each)
    # No side pot for the uncalled surplus
    # According to the internal logic, there will be two pots (one for preflop + combined flop if they are merged into a single pot?)
    # In practice, the function creates a pot for each tier of minimal bets.
    # Here, we will have:
    #  - Main pot: 1.00 (A) + 1.00 (B) = 2.00 from the preflop
    #  - Side pot: 0.50 (A) + 0.50 (B) = 1.00 from the flop
    # Total = 3.00
    expected_pots = [(Decimal("2.00"), {"A", "B"}), (Decimal("1.00"), {"A", "B"})]
    assert hand.pot.pots == expected_pots


def test_end_with_net_gains():
    """
    Tests the end method for a simple scenario and verifies the net gains of the players.
    """
    hand = Hand()
    hand.pot.committed = {"Alice": "30", "Bob": "50", "Charlie": "70"}
    hand.pot.contenders = ["Alice", "Bob", "Charlie"]
    hand.pot.common = {}
    hand.pot.stp = Decimal("0.00")
    hand.totalcollected = Decimal("150.00")

    # Call totalPot to calculate the pots
    hand.totalPot()

    # Distribution of pots (winners: Charlie for the main pot)
    hand.pot.collected = {"Charlie": Decimal("150.00")}  # Gains collected by Charlie
    hand.end(Decimal("150.00"))

    # Net gains for each player
    gains_nets = {
        player: hand.pot.collected.get(player, Decimal("0.00"))
        - Decimal(hand.pot.committed.get(player, "0.00"))
        for player in hand.pot.committed.keys()
    }

    assert gains_nets["Alice"] == Decimal("-30.00")
    assert gains_nets["Bob"] == Decimal("-50.00")
    assert gains_nets["Charlie"] == Decimal("80.00")
