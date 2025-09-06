"""Hand Data Reporter for analyzing hand parsing quality."""

import contextlib
import json
from datetime import datetime
from typing import Any


class HandDataReporter:
    """Reporter for capturing and analyzing data extracted from hands."""

    def __init__(self, report_level: str = "detailed") -> None:
        self.report_level = report_level
        self.files_stats = {}
        self.session_stats = {
            "total_files": 0,
            "total_hands": 0,
            "successful_hands": 0,
            "failed_hands": 0,
            "start_time": datetime.now(),
            "parser_errors": {},
            "game_types": {
                "cash_games": {
                    "holdem": {"nl": 0, "pl": 0, "fl": 0},
                    "stud": {"7_card": 0, "5_card": 0, "hi_lo": 0},
                    "draw": {"5_card": 0, "2_7": 0, "badugi": 0},
                },
                "tournaments": {
                    "holdem": {"nl": 0, "pl": 0, "fl": 0},
                    "stud": {"7_card": 0, "5_card": 0, "hi_lo": 0},
                    "draw": {"5_card": 0, "2_7": 0, "badugi": 0},
                },
            },
        }

    def start_file(self, filepath: str) -> None:
        """Initialize tracking for a file."""
        self.files_stats[filepath] = {
            "hands_processed": 0,
            "hands_successful": 0,
            "hands_failed": 0,
            "errors": [],
            "hands_data": [],
            "start_time": datetime.now(),
        }
        self.session_stats["total_files"] += 1

    def report_hand_success(self, filepath: str, hand_obj: Any) -> None:
        """Capture all data extracted from a successful hand."""
        if filepath not in self.files_stats:
            self.start_file(filepath)

        file_stats = self.files_stats[filepath]
        file_stats["hands_processed"] += 1
        file_stats["hands_successful"] += 1
        self.session_stats["successful_hands"] += 1
        self.session_stats["total_hands"] += 1

        # Classify game type
        try:
            game_category = self._classify_game_type(hand_obj)
            self._update_game_type_stats(game_category)
        except Exception:
            game_category = {"format": "cash_games", "family": "unknown", "subtype": "unknown"}

        # Extract data according to detail level
        if self.report_level in ["detailed", "full"]:
            hand_data = self._extract_hand_data(hand_obj)
            hand_data["game_classification"] = game_category
            file_stats["hands_data"].append(hand_data)
        elif self.report_level == "hierarchy":
            # Light level: just classification and basic info
            hand_data = {
                "hand_id": getattr(hand_obj, "handid", None),
                "table_name": getattr(hand_obj, "tablename", None),
                "start_time": str(getattr(hand_obj, "startTime", None)),
                "game_classification": game_category,
                "player_count": len(getattr(hand_obj, "players", [])),
                "total_pot": str(getattr(hand_obj, "totalpot", 0)),
            }
            file_stats["hands_data"].append(hand_data)

    def report_hand_failure(
        self, filepath: str, error: Exception, hand_text_snippet: str = "", hand_obj: Any = None
    ) -> None:
        """Record parsing failures."""
        import traceback

        if filepath not in self.files_stats:
            self.start_file(filepath)

        file_stats = self.files_stats[filepath]
        file_stats["hands_processed"] += 1
        file_stats["hands_failed"] += 1
        self.session_stats["failed_hands"] += 1
        self.session_stats["total_hands"] += 1

        error_type = type(error).__name__
        if error_type not in self.session_stats["parser_errors"]:
            self.session_stats["parser_errors"][error_type] = 0
        self.session_stats["parser_errors"][error_type] += 1

        # Capture complete stack trace (from enriched error or default)
        full_traceback = (
            getattr(error, "full_traceback", None) or traceback.format_exc()
            if hasattr(error, "__traceback__") and error.__traceback__
            else "No traceback available"
        )

        error_info = {
            "error_type": error_type,
            "error_message": str(error),
            "full_traceback": full_traceback,
            "hand_snippet": hand_text_snippet[:500] if hand_text_snippet else "No text available",  # Plus de contexte
            "timestamp": datetime.now().isoformat(),
            "is_partial": "[PARTIAL]" in str(error),
            "severity": self._categorize_error_severity(error),
            "hand_object_analysis": self._analyze_failed_hand_object(hand_obj),
        }
        file_stats["errors"].append(error_info)

    def _categorize_error_severity(self, error: Exception) -> str:
        """Categorize error severity for better diagnosis."""
        error_msg = str(error).lower()

        if "[partial]" in error_msg:
            return "info"  # Partial hands - info only
        if "no small blind posted" in error_msg or "no big blind posted" in error_msg:
            return "warning"  # Blind problems - warning
        if "keyerror" in error_msg or "attributeerror" in error_msg:
            return "error"  # Parsing errors - error
        if "malformed" in error_msg or "invalid" in error_msg:
            return "critical"  # Invalid format - critical
        return "unknown"  # Other errors

    def _analyze_failed_hand_object(self, hand_obj: Any) -> dict[str, Any]:
        """Specifically analyze a failed Hand object for debugging."""
        if not hand_obj:
            return {"status": "no_hand_object", "reason": "Hand object was not created (early parsing failure)"}

        analysis = {
            "status": "hand_object_available",
            "basic_info": {},
            "parsed_elements": {},
            "missing_elements": [],
            "parsing_stage": "unknown",
        }

        # Basic information always present
        basic_attrs = {
            "handid": getattr(hand_obj, "handid", None),
            "siteHandNo": getattr(hand_obj, "siteHandNo", None),
            "tablename": getattr(hand_obj, "tablename", None),
            "startTime": str(getattr(hand_obj, "startTime", None)),
            "gametype": getattr(hand_obj, "gametype", None),
            "maxseats": getattr(hand_obj, "maxseats", None),
        }

        for attr, value in basic_attrs.items():
            if value is not None:
                analysis["basic_info"][attr] = str(value)[:100]  # Limit size

        # Progressive parsing elements
        parsing_elements = {
            "players": "Player list",
            "actions": "Actions per street",
            "holecards": "Player cards",
            "board": "Board cards",
            "collected": "Collections",
            "bets": "Bet structure",
            "posted": "Posted blinds/antes",
        }

        for attr, description in parsing_elements.items():
            value = getattr(hand_obj, attr, None)
            if value is not None:
                if isinstance(value, (list, dict)):
                    analysis["parsed_elements"][attr] = {
                        "description": description,
                        "type": str(type(value).__name__),
                        "size": len(value),
                        "sample": str(value)[:200] if len(str(value)) <= 200 else str(value)[:200] + "...",
                    }
                else:
                    analysis["parsed_elements"][attr] = {
                        "description": description,
                        "type": str(type(value).__name__),
                        "value": str(value)[:100],
                    }
            else:
                analysis["missing_elements"].append(f"{attr} ({description})")

        # Determine the parsing stage reached
        if hasattr(hand_obj, "players") and hand_obj.players:
            if hasattr(hand_obj, "actions") and hand_obj.actions:
                if hasattr(hand_obj, "holecards") and hand_obj.holecards:
                    analysis["parsing_stage"] = "holecards_parsed"
                else:
                    analysis["parsing_stage"] = "actions_parsed"
            else:
                analysis["parsing_stage"] = "players_parsed"
        else:
            analysis["parsing_stage"] = "basic_info_only"

        return analysis

    def _analyze_object_structure(self, obj: Any, max_depth: int = 2) -> dict[str, Any]:
        """Analyze the complete structure of an object for debugging."""
        analysis = {}

        if max_depth <= 0:
            return {"type": str(type(obj)), "value": str(obj)[:100]}

        # Object attributes
        if hasattr(obj, "__dict__"):
            analysis["attributes"] = {}
            for attr_name in dir(obj):
                if not attr_name.startswith("_") and not callable(getattr(obj, attr_name)):
                    try:
                        attr_value = getattr(obj, attr_name)
                        if attr_value is not None:
                            attr_info = {
                                "type": str(type(attr_value)),
                                "value": str(attr_value)[:200]
                                if not isinstance(attr_value, (dict, list))
                                else len(attr_value),
                            }

                            # For important attributes, capture detailed structure
                            if attr_name in ["actions", "holecards", "board", "posted", "collected", "bets"]:
                                if isinstance(attr_value, dict):
                                    attr_info["dict_structure"] = {}
                                    for key, value in attr_value.items():
                                        if isinstance(value, list):
                                            attr_info["dict_structure"][str(key)] = {
                                                "type": "list",
                                                "length": len(value),
                                                "content": str(value)[:300]
                                                if len(str(value)) <= 300
                                                else str(value)[:300] + "...",
                                            }
                                        else:
                                            attr_info["dict_structure"][str(key)] = {
                                                "type": str(type(value)),
                                                "value": str(value)[:100],
                                            }
                                elif isinstance(attr_value, list):
                                    attr_info["list_content"] = []
                                    for i, item in enumerate(attr_value[:5]):  # First 5 elements
                                        attr_info["list_content"].append(
                                            {
                                                "index": i,
                                                "type": str(type(item)),
                                                "value": str(item)[:100],
                                            }
                                        )

                            analysis["attributes"][attr_name] = attr_info
                    except:
                        analysis["attributes"][attr_name] = {"error": "Could not access"}

        return analysis

    def _classify_game_type(self, hand_obj: Any) -> dict[str, str]:
        """Classify game type for hierarchical organization."""
        gametype = getattr(hand_obj, "gametype", {})
        category = gametype.get("category", "unknown").lower()
        limit_type = gametype.get("limitType", "unknown").lower()

        # Determine game family
        if "hold" in category or "omaha" in category:
            game_family = "holdem"
        elif "stud" in category:
            game_family = "stud"
        elif "draw" in category or "badugi" in category:
            game_family = "draw"
        else:
            game_family = "unknown"

        # Determine subtype
        if game_family == "holdem":
            if limit_type == "nl":
                game_subtype = "nl"
            elif limit_type == "pl":
                game_subtype = "pl"
            else:
                game_subtype = "fl"
        elif game_family == "stud":
            if "7" in category:
                game_subtype = "7_card"
            elif "5" in category:
                game_subtype = "5_card"
            elif "hilo" in category or "hi/lo" in category:
                game_subtype = "hi_lo"
            else:
                game_subtype = "7_card"  # Default for studhi
        elif game_family == "draw":
            if "2-7" in category or "27" in category:
                game_subtype = "2_7"
            elif "badugi" in category:
                game_subtype = "badugi"
            else:
                game_subtype = "5_card"
        else:
            game_subtype = "unknown"

        # Determine if cash or tournament
        is_tournament = getattr(hand_obj, "tourNo", None) is not None
        game_format = "tournaments" if is_tournament else "cash_games"

        return {
            "format": game_format,
            "family": game_family,
            "subtype": game_subtype,
            "category": category,
            "limit_type": limit_type,
        }

    def _update_game_type_stats(self, classification: dict[str, str]) -> None:
        """Update statistics by game type."""
        game_format = classification["format"]
        game_family = classification["family"]
        game_subtype = classification["subtype"]

        if (
            game_format in self.session_stats["game_types"]
            and game_family in self.session_stats["game_types"][game_format]
            and game_subtype in self.session_stats["game_types"][game_format][game_family]
        ):
            self.session_stats["game_types"][game_format][game_family][game_subtype] += 1

    def _extract_hand_data(self, hand_obj: Any) -> dict[str, Any]:
        """Extract important data from a Hand object."""
        # Complete analysis of object structure for debugging
        hand_structure = self._analyze_object_structure(hand_obj) if self.report_level == "full" else {}

        hand_data = {
            "hand_id": getattr(hand_obj, "handid", None),
            "site_hand_no": getattr(hand_obj, "siteHandNo", None) or getattr(hand_obj, "handid", None),
            "database_hand_id": getattr(hand_obj, "dbid_hands", None),
            "table_name": getattr(hand_obj, "tablename", None),
            "start_time": str(getattr(hand_obj, "startTime", None)),
            "game_type": getattr(hand_obj, "gametype", {}),
            "max_seats": getattr(hand_obj, "maxseats", None),
            "button_pos": getattr(hand_obj, "buttonpos", None),
            "total_pot": str(getattr(hand_obj, "totalpot", 0)),
            "rake": str(getattr(hand_obj, "rake", 0)),
            "player_count": len(getattr(hand_obj, "players", [])),
            "currency": getattr(hand_obj, "gametype", {}).get("currency", "USD"),
            "limit_type": getattr(hand_obj, "gametype", {}).get("limitType", "unknown"),
            "category": getattr(hand_obj, "gametype", {}).get("category", "unknown"),
            "object_structure": hand_structure,  # Pour debugging
            # Enriched information for advanced analyses
            "ante": str(getattr(hand_obj, "gametype", {}).get("ante", 0)),
            "small_blind": str(getattr(hand_obj, "gametype", {}).get("sb", 0)),
            "big_blind": str(getattr(hand_obj, "gametype", {}).get("bb", 0)),
            "site_name": getattr(hand_obj, "sitename", None),
            "total_collected": str(getattr(hand_obj, "totalcollected", 0)),
            # New enriched information from debug logs
            "final_stacks": {},
            "bets_by_street": {},
            "pot_details": {},
            "tournament_info": {},
            "winners": {},
        }

        # Player data - ALL players
        if hasattr(hand_obj, "players") and hand_obj.players:
            hand_data["players"] = {}
            hand_data["all_players_list"] = []
            for player in hand_obj.players:
                if len(player) >= 3:
                    seat_no = player[0]
                    player_name = player[1]
                    stack = player[2]

                    # Determine special position (SB, BB, Dealer)
                    position = getattr(hand_obj, "positions", {}).get(player_name, "unknown")
                    special_pos = ""
                    if hasattr(hand_obj, "buttonpos") and hand_obj.buttonpos == seat_no:
                        special_pos = " (Dealer)"
                    elif hasattr(hand_obj, "posted") and hand_obj.posted:
                        for post in hand_obj.posted:
                            if len(post) >= 2 and post[0] == player_name:
                                if "small" in str(post[1]).lower():
                                    special_pos = " (SB)"
                                elif "big" in str(post[1]).lower():
                                    special_pos = " (BB)"

                    # Player cards (hole cards)
                    hole_cards = ""
                    if hasattr(hand_obj, "holecards") and hand_obj.holecards:
                        # Hold'em structure: {'PREFLOP': {'Hero': [[], ['2s', '4c']], ...}}
                        if "PREFLOP" in hand_obj.holecards:
                            preflop_cards = hand_obj.holecards["PREFLOP"]
                            if isinstance(preflop_cards, dict) and player_name in preflop_cards:
                                player_cards = preflop_cards[player_name]
                                if isinstance(player_cards, list) and len(player_cards) >= 2:
                                    # Cards are in the 2nd element: [[], ['2s', '4c']]
                                    cards_list = player_cards[1] if len(player_cards[1]) > 0 else player_cards[0]
                                    if cards_list:
                                        hole_cards = " ".join(cards_list)

                        # Stud structure: {'THIRD': {'Hero': [['2s', '4c', '7h'], []], ...}}
                        else:
                            all_cards = []
                            stud_streets = ["THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
                            for street in stud_streets:
                                if street in hand_obj.holecards:
                                    street_cards = hand_obj.holecards[street]
                                    if isinstance(street_cards, dict) and player_name in street_cards:
                                        player_cards = street_cards[player_name]
                                        if isinstance(player_cards, list) and len(player_cards) >= 1:
                                            # Visible cards are in the first element
                                            visible_cards = player_cards[0] if player_cards[0] else []
                                            all_cards.extend(visible_cards)

                            if all_cards:
                                hole_cards = " ".join(all_cards)

                    player_info = {
                        "seat": seat_no,
                        "starting_stack": str(stack),
                        "final_stack": str(getattr(hand_obj, "stacks", {}).get(player_name, 0)),
                        "position": position,
                        "special_position": special_pos,
                        "hole_cards": hole_cards,
                    }

                    hand_data["players"][player_name] = player_info
                    hand_data["all_players_list"].append(f"Seat {seat_no}: {player_name}{special_pos} (${stack})")

        # Actions per street (summary AND details)
        if hasattr(hand_obj, "actions"):
            hand_data["actions_summary"] = {}
            hand_data["detailed_actions"] = {}
            for street, actions in hand_obj.actions.items():
                if actions:
                    hand_data["actions_summary"][street] = len(actions)
                    hand_data["detailed_actions"][street] = []
                    for action in actions:
                        if len(action) >= 2:
                            player = action[0]
                            action_type = action[1]

                            # Better amount conversion using real data
                            amount = "0"
                            total_bet = "0"

                            if len(action) > 2 and action[2] is not None:
                                # Handle Decimal, float, int
                                try:
                                    if hasattr(action[2], "__float__"):  # Decimal or float
                                        amount = str(float(action[2]))
                                    else:
                                        amount = str(action[2])
                                except (ValueError, TypeError):
                                    amount = str(action[2])

                            if len(action) > 3 and action[3] is not None and action[3] is not False:
                                try:
                                    if hasattr(action[3], "__float__"):  # Decimal or float
                                        total_bet = str(float(action[3]))
                                    else:
                                        total_bet = str(action[3])
                                except (ValueError, TypeError):
                                    total_bet = str(action[3])

                            action_detail = {
                                "player": player,
                                "action": action_type,  # Now we have the real types!
                                "amount": amount,
                                "total_bet": total_bet,
                            }
                            hand_data["detailed_actions"][street].append(action_detail)

        # Board cards
        if hasattr(hand_obj, "board") and hand_obj.board:
            hand_data["board_cards"] = {}
            for street, cards in hand_obj.board.items():
                if cards and cards != []:
                    hand_data["board_cards"][street] = cards if isinstance(cards, list) else [cards]

        # Collections (player winnings)
        hand_data["collections"] = []
        if hasattr(hand_obj, "collected") and hand_obj.collected:
            for collection in hand_obj.collected:
                if isinstance(collection, list) and len(collection) >= 2:
                    hand_data["collections"].append(
                        {
                            "player": collection[0],
                            "amount": str(collection[1]),
                        }
                    )
                    # Populate winners dictionary
                    hand_data["winners"][collection[0]] = str(collection[1])

        # Final player stacks from debug logs
        if hasattr(hand_obj, "stacks") and hand_obj.stacks:
            for player, stack in hand_obj.stacks.items():
                hand_data["final_stacks"][player] = str(stack)

        # Detailed bet structure per street
        if hasattr(hand_obj, "bets") and hand_obj.bets:
            for street, player_bets in hand_obj.bets.items():
                if player_bets:  # If there are bets on this street
                    hand_data["bets_by_street"][street] = {}
                    for player, bets_list in player_bets.items():
                        if bets_list:  # If this player bet on this street
                            hand_data["bets_by_street"][street][player] = [str(bet) for bet in bets_list]

        # Pot information
        if hasattr(hand_obj, "pot") and hand_obj.pot:
            try:
                pot_obj = hand_obj.pot
                hand_data["pot_details"] = {
                    "total": str(getattr(pot_obj, "total", 0)),
                    "main_pot": str(getattr(pot_obj, "main", 0)),
                    "side_pots": str(getattr(pot_obj, "side", [])),
                }
            except Exception:
                hand_data["pot_details"] = {"error": "Could not parse pot structure"}
        else:
            # Fallback to total pot from hand object
            total_pot = hand_data.get("total_pot", "0")
            if total_pot != "0":
                hand_data["pot_details"] = {
                    "total": total_pot,
                    "main_pot": total_pot,
                    "side_pots": "[]",
                }

        # Tournament information if applicable
        if hasattr(hand_obj, "tourNo") and hand_obj.tourNo:
            hand_data["tournament_info"] = {
                "tourney_no": str(hand_obj.tourNo),
                "tourney_id": str(getattr(hand_obj, "tourneyId", "")),
                "buyin": str(getattr(hand_obj, "buyin", 0)),
                "fee": str(getattr(hand_obj, "fee", 0)),
                "buyin_currency": getattr(hand_obj, "buyinCurrency", ""),
                "level": str(getattr(hand_obj, "level", "")),
                "is_rebuy": getattr(hand_obj, "isRebuy", False),
                "is_addon": getattr(hand_obj, "isAddOn", False),
                "is_ko": getattr(hand_obj, "isKO", False),
                "is_lottery": getattr(hand_obj, "isLottery", False),
                "tourney_multiplier": getattr(hand_obj, "tourneyMultiplier", 1),
                "speed": getattr(hand_obj, "speed", ""),
            }

        # Database status
        hand_data["database_ready"] = hasattr(hand_obj, "hands") and bool(getattr(hand_obj, "hands", None))

        if self.report_level == "full":
            # Complete data for "full" level
            if hasattr(hand_obj, "handsplayers") and hand_obj.handsplayers:
                hand_data["players_statistics"] = {}
                for player, stats in hand_obj.handsplayers.items():
                    # Select the most important stats
                    key_stats = {}
                    important_fields = [
                        "position",
                        "seatNo",
                        "startCash",
                        "winnings",
                        "street0VPI",
                        "street0Aggr",
                        "wonWhenSeenStreet1",
                        "sawShowdown",
                        "street1Seen",
                        "street2Seen",
                    ]
                    for field in important_fields:
                        if field in stats and stats[field] is not None:
                            key_stats[field] = stats[field]
                    hand_data["players_statistics"][player] = key_stats

            # Detailed actions already processed in main section

        return hand_data

    def finish_file(self, filepath: str) -> None:
        """Finalize file stats."""
        if filepath in self.files_stats:
            self.files_stats[filepath]["end_time"] = datetime.now()
            duration = self.files_stats[filepath]["end_time"] - self.files_stats[filepath]["start_time"]
            self.files_stats[filepath]["processing_time_seconds"] = duration.total_seconds()

    def generate_report(self) -> None:
        """Generate report according to configured level."""
        total_hands = self.session_stats["successful_hands"] + self.session_stats["failed_hands"]
        success_rate = (self.session_stats["successful_hands"] / total_hands * 100) if total_hands > 0 else 0

        print("\n" + "=" * 80)
        print("📊 DETAILED IMPORT REPORT")
        print("=" * 80)
        print(f"📁 Total files: {self.session_stats['total_files']}")
        print(f"🃏 Total hands: {total_hands}")
        print(f"✅ Success: {self.session_stats['successful_hands']} ({success_rate:.1f}%)")
        print(f"❌ Failures: {self.session_stats['failed_hands']}")

        # Hierarchical display by game type
        self._display_game_type_hierarchy()

        if self.session_stats["parser_errors"]:
            print("\n🔥 PARSING ERRORS:")
            total_errors = sum(self.session_stats["parser_errors"].values())
            for error_type, count in self.session_stats["parser_errors"].items():
                percentage = (count / total_errors * 100) if total_errors > 0 else 0
                print(f"   • {error_type}: {count} errors ({percentage:.1f}%)")

            # Display some common error descriptions
            if self.report_level == "full":
                print("\n   📝 COMMON ERROR DESCRIPTIONS:")
                error_descriptions = {
                    "FpdbHandDuplicateError": "Hands already imported in database",
                    "FpdbHandPartial": "Incomplete hands or incorrect format",
                    "FpdbParseError": "Hand data parsing errors",
                    "Exception": "Various errors (see details per file)",
                    "ValueError": "Invalid values in data",
                    "KeyError": "Missing fields in data",
                }
                for error_type, count in self.session_stats["parser_errors"].items():
                    desc = error_descriptions.get(error_type, "Undocumented error")
                    print(f"      • {error_type}: {desc}")

        # Display most problematic files
        if self.report_level == "full":
            problematic_files = [
                (filepath, stats) for filepath, stats in self.files_stats.items() if stats["hands_failed"] > 0
            ]
            if problematic_files:
                # Sort by decreasing failure count
                problematic_files.sort(key=lambda x: x[1]["hands_failed"], reverse=True)
                top_problematic = problematic_files[:5]  # Top 5 problematic files

                print(f"\n⚠️  MOST PROBLEMATIC FILES (Top {len(top_problematic)}):")
                for i, (filepath, stats) in enumerate(top_problematic, 1):
                    filename = filepath.split("/")[-1]  # Just the filename
                    failure_rate = (
                        (stats["hands_failed"] / stats["hands_processed"] * 100) if stats["hands_processed"] > 0 else 0
                    )
                    print(f"   {i}. {filename}")
                    print(f"      📊 {stats['hands_failed']}/{stats['hands_processed']} failures ({failure_rate:.1f}%)")

        # Details per file
        print(f"\n📋 DETAILS PER FILE ({len(self.files_stats)} files):")
        for filepath, stats in self.files_stats.items():
            file_success_rate = (
                (stats["hands_successful"] / stats["hands_processed"] * 100) if stats["hands_processed"] > 0 else 0
            )
            print(f"\n📄 {filepath}")
            print(f"   🃏 Hands processed: {stats['hands_processed']}")
            print(f"   ✅ Success: {stats['hands_successful']} ({file_success_rate:.1f}%)")
            print(f"   ❌ Failures: {stats['hands_failed']}")

            if "processing_time_seconds" in stats:
                print(f"   ⏱️  Time: {stats['processing_time_seconds']:.2f}s")

            # Display error details for this file
            if stats["errors"] and self.report_level in ["detailed", "full"]:
                print("   🔥 DETAILED ERRORS:")
                error_counts = {}
                for error in stats["errors"]:
                    error_type = error.get("error_type", "Exception")
                    if error_type not in error_counts:
                        error_counts[error_type] = 0
                    error_counts[error_type] += 1

                for error_type, count in error_counts.items():
                    print(f"      • {error_type}: {count}")

                # Display detailed errors
                if self.report_level in ["full", "debug"]:
                    level_label = "ULTRA-DETAILED DEBUG" if self.report_level == "debug" else "COMPLETE ERROR MESSAGES"
                    print(f"      🔍 {level_label}:")
                    for i, error in enumerate(stats["errors"], 1):
                        error_msg = error.get("error_message", "Message inconnu")
                        error_type = error.get("error_type", "Exception")
                        hand_snippet = error.get("hand_snippet", "")

                        print(f"         ─── Error #{i} ───")
                        print(f"         Type: {error_type}")
                        print(f"         Message: {error_msg}")

                        # Display complete stack trace
                        full_traceback = error.get("full_traceback", "")
                        if full_traceback and full_traceback != "No traceback available":
                            print("         🔥 COMPLETE STACK TRACE:")
                            # Indent each line of traceback
                            for line in full_traceback.strip().split("\n"):
                                print(f"           {line}")
                            print()

                        if hand_snippet and hand_snippet != "No text available":
                            # In debug mode, show more context
                            context_length = (
                                "first 1000 characters" if self.report_level == "debug" else "first 500 characters"
                            )
                            print(f"         📄 HAND CONTEXT ({context_length}):")
                            displayed_snippet = (
                                hand_snippet[:1000] if self.report_level == "debug" else hand_snippet[:500]
                            )
                            # Display line by line for better readability in debug mode
                            if self.report_level == "debug":
                                for line_num, line in enumerate(displayed_snippet.split("\n"), 1):
                                    if line.strip():
                                        print(f"           {line_num:2d}: {line}")
                                    if line_num > 50:  # Limiter à 50 lignes max
                                        print("           ... (content truncated)")
                                        break
                            else:
                                print(f"           {displayed_snippet}")
                        print()
                elif self.report_level == "detailed":
                    # In detailed mode, show just the first 5 errors with complete messages
                    shown_errors = stats["errors"][:5]
                    for i, error in enumerate(shown_errors, 1):
                        error_msg = error.get("error_message", "Message inconnu")
                        error_type = error.get("error_type", "Exception")
                        print(f"         [{i}] {error_type}: {error_msg}")

                    if len(stats["errors"]) > 5:
                        print(f"         ... and {len(stats['errors']) - 5} other errors")

            if self.report_level == "hierarchy" and stats["hands_data"]:
                total_hands = len(stats["hands_data"])
                # Adaptive logic: show all hands if <= 10, otherwise sample
                if total_hands <= 10:
                    display_hands = stats["hands_data"]
                else:
                    display_hands = stats["hands_data"][:5] + stats["hands_data"][-2:]  # 5 first + 2 last
                    f"\n   🃏 PROCESSED HANDS (sample {len(display_hands)}/{total_hands}):"

                for i, hand in enumerate(display_hands, 1):
                    game_class = hand.get("game_classification", {})
                    self._get_game_type_icon(game_class) if game_class else "🎮"
                    i if total_hands <= 10 else (i if i <= 5 else total_hands - (len(display_hands) - i))
                    if total_hands > 10 and i == 5:
                        pass
            elif self.report_level in ["detailed", "full"] and stats["hands_data"]:
                if self.report_level == "full":
                    hands_to_show = stats["hands_data"]  # All hands in full mode
                else:
                    hands_to_show = stats["hands_data"][:2]  # First 2 hands in detailed mode

                for i, hand in enumerate(hands_to_show, 1):
                    if self.report_level == "full":
                        # Enriched information
                        if hand.get("ante", "0") != "0" or hand.get("ante", "0") != "0":
                            pass

                        # Only show blinds for non-Stud games
                        game_category = hand.get("category", "").lower()
                        if "stud" not in game_category:
                            if hand.get("small_blind", "0") != "0":
                                pass
                            if hand.get("big_blind", "0") != "0":
                                pass

                        if hand.get("total_collected", "0") != "0":
                            pass

                        # Table information
                        if hand.get("button_pos") is not None:
                            pass

                        if hand.get("all_players_list"):
                            for player_info in hand["all_players_list"]:
                                if isinstance(player_info, dict):
                                    player_info.get("name", "Unknown")
                                    player_info.get("final_stack", "0")
                                else:
                                    # player_info is a string (player name)
                                    pass

                        # Display player cards
                        if hand.get("players"):
                            players_with_cards = [p for p, info in hand["players"].items() if info.get("hole_cards")]
                            if players_with_cards:
                                for player in players_with_cards:
                                    cards = hand["players"][player]["hole_cards"]
                                    # Remplacer les cartes "0x" par "[cachées]"
                                    if "0x" in cards:
                                        cards = cards.replace("0x", "X").replace("X X X X", "[hidden]")

                        # Display board
                        if hand.get("board_cards"):
                            board_str = ", ".join(
                                [
                                    f"{street}: {' '.join(cards)}"
                                    for street, cards in hand["board_cards"].items()
                                    if cards
                                ]
                            )
                            if board_str:
                                pass

                        # Display detailed actions per street
                        if hand.get("detailed_actions"):
                            for actions in hand["detailed_actions"].values():
                                if actions:
                                    for action in actions:
                                        player = action.get("player", "Unknown")
                                        action.get("action", "unknown")
                                        amount = action.get("amount", "0")
                                        if amount and amount != "0":
                                            pass
                                        else:
                                            pass

                        # Display collections (who won how much)
                        if hand.get("winners"):
                            for player in hand["winners"]:
                                pass

                        # New enriched information
                        if hand.get("final_stacks"):
                            for player in hand["final_stacks"]:
                                pass

                        if hand.get("bets_by_street"):
                            for player_bets in hand["bets_by_street"].values():
                                for player, bets in player_bets.items():
                                    " → ".join(f"${bet}" for bet in bets)

                        if hand.get("pot_details"):
                            pot_total = hand["pot_details"].get("total", "0")
                            # If pot details total is None or 0, use the main total_pot
                            if pot_total in ["None", "0", "none", None]:
                                pot_total = hand.get("total_pot", "0")

                            if pot_total not in ["0", "0.0", None]:
                                if hand["pot_details"].get("main_pot", "0") not in ["0", "None", None]:
                                    pass
                                if hand["pot_details"].get("side_pots") and hand["pot_details"]["side_pots"] != "[]":
                                    pass

                        if hand.get("tournament_info") and hand["tournament_info"].get("tourney_no"):
                            info = hand["tournament_info"]
                            buyin_val = info.get("buyin", "0")
                            fee_val = info.get("fee", "0")
                            if buyin_val not in ("0", "None", None, ""):
                                # Convert from centimes to euros for display
                                float(buyin_val) / 100
                            if fee_val not in ("0", "None", None, ""):
                                # Convert from centimes to euros for display
                                float(fee_val) / 100
                            if info.get("level"):
                                pass
                            features = []
                            if info.get("is_rebuy"):
                                features.append("Rebuy")
                            if info.get("is_addon"):
                                features.append("Add-on")
                            if info.get("is_ko"):
                                features.append("Knockout")
                            if features:
                                pass

                            # Display lottery information only for lottery SNGs
                            if info.get("is_lottery"):
                                multiplier = info.get("tourney_multiplier", 1)
                                if multiplier and str(multiplier) not in ("1", "None", None, ""):
                                    pass
                                speed = info.get("speed", "").strip()
                                if speed:
                                    pass

                        # Information about detected bugs
                        if hand.get("site_hand_no") == hand.get("hand_id") or not hand.get("site_hand_no"):
                            pass
                        if not hand.get("database_hand_id"):
                            pass
                        if hand.get("rake", "0") == "0":
                            pass

                        # Card verification
                        players_with_cards = [
                            p for p, info in hand.get("players", {}).items() if info.get("hole_cards")
                        ]
                        if not players_with_cards:
                            pass

                        # Only show board card warning for non-Stud games
                        game_category = hand.get("category", "").lower()
                        if "stud" not in game_category and not hand.get("board_cards"):
                            pass

                        # Hand object structure for debugging (debug mode only)
                        # This section is disabled as it's too technical for end user
                        # To reactivate, uncomment the following lines
                        # if hand.get('object_structure') and hand['object_structure'].get('attributes'):
                        #     print(f"         🔍 Structure de l'objet Hand (échantillon):")
                        #     attrs = hand['object_structure']['attributes']
                        #     important_attrs = ['siteHandNo', 'handid', 'tablename', 'actions', 'holecards', 'board', 'posted', 'collected']
                        #     for attr in important_attrs:
                        #         if attr in attrs:
                        #             print(f"            - {attr}: {attrs[attr]['type']} = {attrs[attr]['value']}")
                        #
                        #             # Afficher la structure détaillée des dictionnaires
                        #             if 'dict_structure' in attrs[attr]:
                        #                 print(f"              Structure détaillée:")
                        #                 for key, structure in attrs[attr]['dict_structure'].items():
                        #                     if structure['type'] == 'list':
                        #                         print(f"                {key}: {structure['type']}[{structure['length']}] = {structure['content']}")
                        #                     else:
                        #                         print(f"                {key}: {structure['type']} = {structure['value']}")
                        #
                        #             # Afficher le contenu des listes
                        #             if 'list_content' in attrs[attr]:
                        #                 print(f"              Contenu de la liste:")
                        #                 for item in attrs[attr]['list_content']:
                        #                     print(f"                [{item['index']}]: {item['type']} = {item['value']}")
                        #
                        #     print(f"            - Total attributs disponibles: {len(attrs)}")
                        #     print(f"            - Tous les attributs: {', '.join(sorted(attrs.keys())[:20])}...")

            if stats["errors"]:
                # Separate errors by severity
                partial_errors = [e for e in stats["errors"] if e.get("is_partial", False)]
                real_errors = [e for e in stats["errors"] if not e.get("is_partial", False)]

                if partial_errors and self.report_level in ["detailed", "full"]:
                    for i, error in enumerate(partial_errors[:2], 1):
                        # Extract more useful info for partial hands
                        snippet = error.get("hand_snippet", "")
                        if "Hand #" in snippet:
                            with contextlib.suppress(IndexError, AttributeError):
                                snippet.split("Hand #")[1].split()[0]

                        # Display partial hand content (more context)
                        if snippet and len(snippet) > 50:
                            # Split snippet into lines for better display
                            lines = snippet.replace("\\n", "\n").split("\n")[:8]  # First 8 lines
                            for line in lines:
                                if line.strip():
                                    pass
                            if len(snippet) > 500:
                                pass

                        # In debug mode, show even more info
                        if hasattr(self, "_debug_mode") and self._debug_mode:
                            # Hand object analysis if available
                            hand_analysis = error.get("hand_object_analysis")
                            if hand_analysis:
                                if hand_analysis.get("status") == "hand_object_available":
                                    # Basic captured information
                                    basic_info = hand_analysis.get("basic_info", {})
                                    if basic_info:
                                        for key in basic_info:
                                            pass

                                    # Successfully parsed elements
                                    parsed = hand_analysis.get("parsed_elements", {})
                                    if parsed:
                                        for key, info in parsed.items():
                                            if info.get("type") in ["dict", "list"]:
                                                pass
                                            else:
                                                pass

                                    # Missing elements
                                    missing = hand_analysis.get("missing_elements", [])
                                    if missing:
                                        for _element in missing[:5]:  # Limit to 5 to avoid too much output
                                            pass
                                        if len(missing) > 5:
                                            pass
                                elif hand_analysis.get("status") == "no_hand_object":
                                    hand_analysis.get("reason", "Unknown")

                if real_errors:
                    error_counts = {}
                    for error in real_errors:
                        severity = error.get("severity", "unknown")
                        error_type = error["error_type"]
                        key = f"{severity}:{error_type}"
                        error_counts[key] = error_counts.get(key, 0) + 1

                    for key in error_counts:
                        severity, error_type = key.split(":", 1)
                        {"critical": "🔥", "error": "❌", "warning": "⚠️", "unknown": "❓"}.get(severity, "❓")

                    if self.report_level in ["detailed", "full"]:
                        for error in real_errors[:2]:  # Première 2 erreurs
                            severity = error.get("severity", "unknown")
                            {"critical": "🔥", "error": "❌", "warning": "⚠️", "unknown": "❓"}.get(severity, "❓")

        # Debug: end of report confirmation

    def _display_game_type_hierarchy(self) -> None:
        """Display game type hierarchy."""
        game_types = self.session_stats["game_types"]

        print("\n🎮 DISTRIBUTION BY GAME TYPE:")

        # Cash Games
        cash_total = sum(sum(variants.values()) for variants in game_types["cash_games"].values())
        if cash_total > 0:
            print(f"\n💰 CASH GAMES (Total: {cash_total})")

            # Hold'em
            holdem_cash = game_types["cash_games"]["holdem"]
            holdem_total = sum(holdem_cash.values())
            if holdem_total > 0:
                print(f"   🃏 Hold'em: {holdem_total}")
                if holdem_cash["nl"] > 0:
                    print(f"      • No Limit: {holdem_cash['nl']}")
                if holdem_cash["pl"] > 0:
                    print(f"      • Pot Limit: {holdem_cash['pl']}")
                if holdem_cash["fl"] > 0:
                    print(f"      • Fixed Limit: {holdem_cash['fl']}")

            # Stud
            stud_cash = game_types["cash_games"]["stud"]
            stud_total = sum(stud_cash.values())
            if stud_total > 0:
                print(f"   🎯 Stud: {stud_total}")
                if stud_cash["7_card"] > 0:
                    print(f"      • 7-Card Stud: {stud_cash['7_card']}")
                if stud_cash["5_card"] > 0:
                    print(f"      • 5-Card Stud: {stud_cash['5_card']}")
                if stud_cash["hi_lo"] > 0:
                    print(f"      • Hi-Lo: {stud_cash['hi_lo']}")

            # Draw
            draw_cash = game_types["cash_games"]["draw"]
            draw_total = sum(draw_cash.values())
            if draw_total > 0:
                print(f"   🎨 Draw: {draw_total}")
                if draw_cash["5_card"] > 0:
                    print(f"      • 5-Card Draw: {draw_cash['5_card']}")
                if draw_cash["2_7"] > 0:
                    print(f"      • 2-7 Triple Draw: {draw_cash['2_7']}")
                if draw_cash["badugi"] > 0:
                    print(f"      • Badugi: {draw_cash['badugi']}")

        # Tournaments
        tourney_total = sum(sum(variants.values()) for variants in game_types["tournaments"].values())
        if tourney_total > 0:
            print(f"\n🏆 TOURNOIS (Total: {tourney_total})")

            # Hold'em
            holdem_tourney = game_types["tournaments"]["holdem"]
            holdem_total = sum(holdem_tourney.values())
            if holdem_total > 0:
                print(f"   🃏 Hold'em: {holdem_total}")
                if holdem_tourney["nl"] > 0:
                    print(f"      • No Limit: {holdem_tourney['nl']}")
                if holdem_tourney["pl"] > 0:
                    print(f"      • Pot Limit: {holdem_tourney['pl']}")
                if holdem_tourney["fl"] > 0:
                    print(f"      • Fixed Limit: {holdem_tourney['fl']}")

            # Stud
            stud_tourney = game_types["tournaments"]["stud"]
            stud_total = sum(stud_tourney.values())
            if stud_total > 0:
                print(f"   🎯 Stud: {stud_total}")
                if stud_tourney["7_card"] > 0:
                    print(f"      • 7-Card Stud: {stud_tourney['7_card']}")
                if stud_tourney["5_card"] > 0:
                    print(f"      • 5-Card Stud: {stud_tourney['5_card']}")
                if stud_tourney["hi_lo"] > 0:
                    print(f"      • Hi-Lo: {stud_tourney['hi_lo']}")

            # Draw
            draw_tourney = game_types["tournaments"]["draw"]
            draw_total = sum(draw_tourney.values())
            if draw_total > 0:
                print(f"   🎨 Draw: {draw_total}")
                if draw_tourney["5_card"] > 0:
                    print(f"      • 5-Card Draw: {draw_tourney['5_card']}")
                if draw_tourney["2_7"] > 0:
                    print(f"      • 2-7 Triple Draw: {draw_tourney['2_7']}")
                if draw_tourney["badugi"] > 0:
                    print(f"      • Badugi: {draw_tourney['badugi']}")

    def _get_game_type_icon(self, classification: dict[str, str]) -> str:
        """Return appropriate icon for game type."""
        base_icon = "🏆" if classification["format"] == "tournaments" else "💰"

        if classification["family"] == "holdem":
            return f"{base_icon}🃏"
        if classification["family"] == "stud":
            return f"{base_icon}🎯"
        if classification["family"] == "draw":
            return f"{base_icon}🎲"
        return base_icon

    def export_json(self, output_file: str) -> None:
        """Export data to JSON."""
        self.session_stats["end_time"] = datetime.now()
        self.session_stats["total_duration_seconds"] = (
            self.session_stats["end_time"] - self.session_stats["start_time"]
        ).total_seconds()

        export_data = {
            "metadata": {
                "export_timestamp": datetime.now().isoformat(),
                "report_level": self.report_level,
                "fpdb_parser": "BovadaToFpdb",
                "total_statistics_per_player": 191,
            },
            "session_stats": self.session_stats,
            "files_stats": self.files_stats,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, default=str, ensure_ascii=False)
