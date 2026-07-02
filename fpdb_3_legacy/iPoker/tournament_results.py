from __future__ import annotations

import decimal
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_parser")


class IPokerTournamentResultsMixin:
    """Tournament result parsing helpers for iPoker hand histories."""

    def _initialize_tournament_data(self, hand: Any) -> None:
        """Initialize tournament data structures."""
        hand.winnings = {}
        hand.ranks = {}
        hand.playersIn = []
        hand.isProgressive = False
        log.debug("Initialized tournament data structures method: iPoker:readTourneyResults, is_progressive: False")

    def _parse_tournament_data(self, hand_text: str) -> dict:  # noqa: C901, PLR0912, PLR0915
        """Parse tournament data from hand text."""
        tournament_data = {
            "buyin_amount": Decimal(0),
            "fee_amount": Decimal(0),
            "totbuyin_amount": Decimal(0),
            "currency_symbol": "EUR",
            "tourno": None,
            "rank": None,
            "tournament_name": None,
        }

        # Use whole_file instead of hand_text for XML parsing
        xml_source = getattr(self, "whole_file", hand_text)

        # Parse tournament info from XML - extended patterns
        tourney_patterns = {
            # Basic tournament data
            "tournamentcode": r"<tournamentcode>([^<]*)</tournamentcode>",
            "tournamentname": r"<tournamentname>([^<]*)</tournamentname>",
            "place": r"<place>([^<]*)</place>",
            "buyin": r"<buyin>([^<]*)</buyin>",
            "birake": r"<birake>([^<]*)</birake>",
            "totalbuyin": r"<totalbuyin>([^<]*)</totalbuyin>",
            "win": r"<win>([^<]*)</win>",
            "currency": r"<currency>([^<]*)</currency>",
            # Extended data for tournament results
            "rewarddrawn": r"<rewarddrawn>([^<]*)</rewarddrawn>",
            "statuspoints": r"<statuspoints>([^<]*)</statuspoints>",
            "awardpoints": r"<awardpoints>([^<]*)</awardpoints>",
            "ipoints": r"<ipoints>([^<]*)</ipoints>",
            "gamecount": r"<gamecount>([^<]*)</gamecount>",
            "duration": r"<duration>([^<]*)</duration>",
            "tablesize": r"<tablesize>([^<]*)</tablesize>",
            "mode": r"<mode>([^<]*)</mode>",
            "bets": r"<bets>([^<]*)</bets>",
            "wins": r"<wins>([^<]*)</wins>",
            "chipsin": r"<chipsin>([^<]*)</chipsin>",
            "chipsout": r"<chipsout>([^<]*)</chipsout>",
        }

        tourney_info = {}
        for key, pattern in tourney_patterns.items():
            match = re.search(pattern, xml_source)
            if match:
                tourney_info[key] = match.group(1)
                log.debug("Found tournament %s: %s", key, match.group(1))

        # Extract tournament data
        tournament_data["tourno"] = tourney_info.get("tournamentcode")
        tournament_data["tournament_name"] = tourney_info.get("tournamentname")
        tournament_data["rank"] = tourney_info.get("place")
        tournament_data["currency_symbol"] = tourney_info.get("currency", "EUR")

        # Extended tournament data
        tournament_data["gamecount"] = tourney_info.get("gamecount", "0")
        tournament_data["duration"] = tourney_info.get("duration", "")
        tournament_data["tablesize"] = tourney_info.get("tablesize", "")
        tournament_data["mode"] = tourney_info.get("mode", "")
        tournament_data["statuspoints"] = tourney_info.get("statuspoints", "0")
        tournament_data["awardpoints"] = tourney_info.get("awardpoints", "0")
        tournament_data["ipoints"] = tourney_info.get("ipoints", "0")
        tournament_data["bets"] = tourney_info.get("bets", "0")
        tournament_data["wins"] = tourney_info.get("wins", "0")
        tournament_data["chipsin"] = tourney_info.get("chipsin", "0")
        tournament_data["chipsout"] = tourney_info.get("chipsout", "0")

        # Parse buyin amounts
        try:
            buyin_str = tourney_info.get("buyin", "0")
            if buyin_str and buyin_str != "0":
                buyin_clean = self._clean_currency_amount(buyin_str)
                tournament_data["buyin_amount"] = Decimal(buyin_clean)

            birake_str = tourney_info.get("birake", "0")
            if birake_str and birake_str != "0":
                birake_clean = self._clean_currency_amount(birake_str)
                tournament_data["fee_amount"] = Decimal(birake_clean)

            totalbuyin_str = tourney_info.get("totalbuyin", "0")
            if totalbuyin_str and totalbuyin_str != "0":
                totalbuyin_clean = self._clean_currency_amount(totalbuyin_str)
                tournament_data["totbuyin_amount"] = Decimal(totalbuyin_clean)

            # Parse hero winnings
            win_str = tourney_info.get("win", "0")
            if win_str and win_str != "0":
                win_clean = self._clean_currency_amount(win_str)
                tournament_data["hero_winnings"] = Decimal(win_clean)
            else:
                tournament_data["hero_winnings"] = Decimal(0)

            # Parse reward drawn (Twister prize pool)
            rewarddrawn_str = tourney_info.get("rewarddrawn", "0")
            if rewarddrawn_str and rewarddrawn_str != "0":
                reward_clean = self._clean_currency_amount(rewarddrawn_str)
                tournament_data["rewarddrawn"] = Decimal(reward_clean)
            else:
                tournament_data["rewarddrawn"] = Decimal(0)

            # Calculate Twister multiplier (rewarddrawn / buyin)
            if tournament_data["rewarddrawn"] > 0 and tournament_data["buyin_amount"] > 0:
                tournament_data["multiplier"] = tournament_data["rewarddrawn"] / tournament_data["buyin_amount"]
                log.debug(
                    "Calculated Twister multiplier: %s (rewarddrawn: %s / buyin: %s)",
                    tournament_data["multiplier"],
                    tournament_data["rewarddrawn"],
                    tournament_data["buyin_amount"],
                )
            elif tournament_data["rewarddrawn"] > 0 and tournament_data["totbuyin_amount"] > 0:
                # Fallback to totalbuyin if buyin_amount is 0
                tournament_data["multiplier"] = tournament_data["rewarddrawn"] / tournament_data["totbuyin_amount"]
                log.debug(
                    "Calculated Twister multiplier using totalbuyin: %s (rewarddrawn: %s / totalbuyin: %s)",
                    tournament_data["multiplier"],
                    tournament_data["rewarddrawn"],
                    tournament_data["totbuyin_amount"],
                )
            else:
                tournament_data["multiplier"] = Decimal(0)
                log.debug(
                    "Cannot calculate multiplier: rewarddrawn=%s, buyin_amount=%s, totbuyin_amount=%s",
                    tournament_data["rewarddrawn"],
                    tournament_data["buyin_amount"],
                    tournament_data["totbuyin_amount"],
                )

        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            log.warning("Error parsing tournament buyin amounts: %s", e)

        self._validate_tournament_data(tournament_data)
        return tournament_data

    def _extract_tournament_data_from_match(self, mg: dict, tournament_data: dict) -> None:
        """Extract tournament data from regex match."""
        if mg.get("TOURNO"):
            tournament_data["tourno"] = mg["TOURNO"]
            log.debug("Parsed tournament number: %s", tournament_data["tourno"])

        if mg.get("NAME"):
            tournament_data["tournament_name"] = mg["NAME"]
            log.debug("Parsed tournament name: %s", tournament_data["tournament_name"])

        if mg.get("PLACE"):
            tournament_data["rank"] = mg["PLACE"]
            log.debug("Parsed tournament place: %s", tournament_data["rank"])

        self._process_buyin_amount(mg, tournament_data)
        self._process_fee_amounts(mg, tournament_data)
        self._process_total_buyin(mg, tournament_data)

    def _process_buyin_amount(self, mg: dict, tournament_data: dict) -> None:
        """Process buy-in amount from match groups."""
        if mg.get("BIAMT"):
            amt_str = mg["BIAMT"].strip()
            log.debug("Raw BIAMT value: %s", amt_str)
            amt_str = amt_str.replace(",", ".")
            amt_str = self.clearMoneyString(amt_str)

            try:
                if amt_str:
                    tournament_data["buyin_amount"] = Decimal(amt_str)
                    log.debug("Converted BIAMT to Decimal: %s", tournament_data["buyin_amount"])
                else:
                    log.warning("Empty or invalid BIAMT value: %s", mg["BIAMT"])
            except InvalidOperation:
                log.exception("Failed to convert BIAMT to Decimal: %s", amt_str)
                tournament_data["buyin_amount"] = Decimal(0)

    def _process_fee_amounts(self, mg: dict, tournament_data: dict) -> None:
        """Process fee amounts (BIRAKE and BIRAKE2) from match groups."""
        if mg.get("BIRAKE"):
            rake_str = mg["BIRAKE"].strip().replace(",", ".")
            rake_str = self.clearMoneyString(rake_str)
            try:
                if rake_str:
                    tournament_data["fee_amount"] = Decimal(rake_str)
                    log.debug("Converted BIRAKE to Decimal: %s", tournament_data["fee_amount"])
            except InvalidOperation:
                log.exception("Failed to convert BIRAKE to Decimal: %s", rake_str)

        if mg.get("BIRAKE2"):
            rake2_str = mg["BIRAKE2"].strip().replace(",", ".")
            rake2_str = self.clearMoneyString(rake2_str)
            try:
                if rake2_str:
                    tournament_data["fee_amount"] += Decimal(rake2_str)
                    log.debug("Added BIRAKE2 to fee_amount. New fee_amount: %s", tournament_data["fee_amount"])
            except InvalidOperation:
                log.exception("Failed to convert BIRAKE2 to Decimal: %s", rake2_str)

    def _process_total_buyin(self, mg: dict, tournament_data: dict) -> None:
        """Process total buy-in amount from match groups."""
        if mg.get("TOTBUYIN"):
            totbuy_str = mg["TOTBUYIN"].strip().replace(",", ".")
            totbuy_str = self.clearMoneyString(totbuy_str.replace("€", ""))
            try:
                if totbuy_str:
                    tournament_data["totbuyin_amount"] = Decimal(totbuy_str)
                    log.debug("Converted TOTBUYIN to Decimal: %s", tournament_data["totbuyin_amount"])
            except InvalidOperation:
                log.exception("Failed to convert TOTBUYIN to Decimal: %s", totbuy_str)

    def _validate_tournament_data(self, tournament_data: dict) -> None:
        """Validate and adjust tournament data."""
        if (
            tournament_data["totbuyin_amount"] > 0
            and tournament_data["buyin_amount"] == 0
            and tournament_data["fee_amount"] == 0
        ):
            tournament_data["buyin_amount"] = tournament_data["totbuyin_amount"]
            tournament_data["fee_amount"] = Decimal(0)
            log.debug("Using TOTBUYIN as buy-in amount since BIAMT and fees were missing.")

    def _set_tournament_attributes(self, tournament_data: dict, hand: Any) -> None:
        """Set tournament attributes from parsed data."""
        hand.tourNo = tournament_data["tourno"]
        hand.buyin = int(tournament_data["buyin_amount"] * 100)
        hand.fee = int(tournament_data["fee_amount"] * 100)
        hand.buyinCurrency = tournament_data["currency_symbol"]
        hand.currency = tournament_data["currency_symbol"]
        hand.isTournament = True
        hand.tourneyName = tournament_data["tournament_name"] if tournament_data["tournament_name"] else hand.tablename
        hand.isSng = True
        hand.isRebuy = False
        hand.isAddOn = False
        hand.isKO = False

        # Extended tournament attributes
        hand.gamecount = tournament_data.get("gamecount", "0")
        hand.duration = tournament_data.get("duration", "")
        hand.tablesize = tournament_data.get("tablesize", "")
        hand.mode = tournament_data.get("mode", "")

        # iPoker points
        hand.statuspoints = tournament_data.get("statuspoints", "0")
        hand.awardpoints = tournament_data.get("awardpoints", "0")
        hand.ipoints = tournament_data.get("ipoints", "0")

        # Player performance
        hand.bets = tournament_data.get("bets", "0")
        hand.wins = tournament_data.get("wins", "0")
        hand.chipsin = tournament_data.get("chipsin", "0")
        hand.chipsout = tournament_data.get("chipsout", "0")

        # Hero winnings (in cents)
        hand.hero_winnings = int(tournament_data.get("hero_winnings", Decimal(0)) * 100)

        # Reward drawn (Twister prize pool) in cents
        hand.rewarddrawn = int(tournament_data.get("rewarddrawn", Decimal(0)) * 100)

        # Twister multiplier (rewarddrawn / buyin)
        hand.multiplier = float(tournament_data.get("multiplier", Decimal(0)))

        # Lottery tournament detection and attributes
        hand.isLottery = tournament_data.get("multiplier", Decimal(0)) > 1
        hand.tourneyMultiplier = int(tournament_data.get("multiplier", Decimal(1)))

        if not hasattr(hand, "endTime"):
            hand.endTime = hand.startTime

        log.debug("Set tournament attributes: tourNo=%s, buyin=%s, fee=%s", hand.tourNo, hand.buyin, hand.fee)
        log.debug(
            "Set tournament attributes continued: hero_winnings=%s, rewarddrawn=%s, multiplier=%s",
            hand.hero_winnings,
            hand.rewarddrawn,
            hand.multiplier,
        )

    def _process_tournament_players(self, hand: Any, tournament_data: dict) -> None:
        """Process tournament players and their results."""
        # Initialize player data
        for player in hand.players:
            player_name = player[1]
            hand.playersIn.append(player_name)
            hand.ranks[player_name] = 0
            hand.winnings[player_name] = 0

        # Set rank for specific player if available
        if tournament_data["rank"] and tournament_data["rank"] != "N/A":
            try:
                rank_value = int(tournament_data["rank"])
                if hasattr(self, "hero") and self.hero and self.hero in hand.ranks:
                    hand.ranks[self.hero] = rank_value
                    log.debug("Set rank for hero %s: %s", self.hero, rank_value)
            except (ValueError, TypeError):
                log.warning("Invalid rank value: %s", tournament_data["rank"])

        # Set hero winnings from tournament data
        if hasattr(self, "hero") and self.hero and self.hero in hand.winnings:
            hero_winnings_cents = int(tournament_data.get("hero_winnings", Decimal(0)) * 100)
            hand.winnings[self.hero] = hero_winnings_cents
            log.debug("Set winnings for hero %s: %s cents", self.hero, hero_winnings_cents)
        else:
            log.error("Hero %s not found in hand.winnings: %s", getattr(self, "hero", "None"), hand.winnings)

        # For Twister tournaments, calculate other players' winnings based on Twister rules
        if tournament_data.get("multiplier", Decimal(0)) > 1:
            # In Twister, only the winner gets the prize pool, others get 0
            if hasattr(self, "hero") and self.hero and self.hero in hand.ranks and hand.ranks[self.hero] == 1:
                # Hero is the winner, already set above
                pass
            elif hasattr(self, "hero") and self.hero and self.hero in hand.winnings:
                hand.winnings[self.hero] = 0
                log.debug("Set winnings for hero %s to 0 (non-winner in Twister)", self.hero)

        # Set hand statistics
        hand.entries = len(hand.playersIn)
        hand.prizepool = sum(hand.winnings.values())

        # Tournament summary will be handled by iPokerSummary parser automatically
        # when summary_in_file = True and summaryImporter="iPokerSummary" in config
        log.debug("Tournament summary will be processed by iPokerSummary parser")
