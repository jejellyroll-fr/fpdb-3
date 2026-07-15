"""Non-numeric HUD display entries extracted from the legacy stat catalogue."""

# ruff: noqa: UP031 - starthands preserves the legacy SQL interpolation text.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy import Card, Configuration, Database
from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_formatting import StatTuple

DisplayTuple = tuple[str, str, str, str, str, str]

GAME_ABBREVIATIONS = {
    "holdem.fl": "H", "studhilo.fl": "E", "omahahi.pl": "P", "27_3draw.fl": "T", "razz.fl": "R",
    "holdem.nl": "N", "omahahilo.fl": "O", "studhi.fl": "S", "27_1draw.nl": "K", "badugi.fl": "B",
    "fivedraw.fl": "F", "fivedraw.pl": "Fp", "fivedraw.nl": "Fn", "27_3draw.pl": "Tp", "27_3draw.nl": "Tn",
    "badugi.pl": "Bp", "badugi.hp": "Bh", "omahahilo.pl": "Op", "omahahilo.nl": "On", "holdem.pl": "Hp", "studhi.nl": "Sn",
}


def blank(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return an empty HUD grid cell."""
    return "", "", "", "", "", "<blank>"


def player_note(stat_dict: Mapping[int, Mapping[str, Any]], player: int | str) -> DisplayTuple:
    """Return the note icon; its color is resolved by the HUD display layer."""
    try:
        for data in stat_dict.values():
            if data.get("screen_name") == player:
                break
        return "📝", "📝", "📝", "📝", "📝", "Player note icon"
    except (AttributeError, KeyError, TypeError, ValueError):
        return "📝", "📝", "📝", "📝", "📝", "Player note icon"


def game_abbr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the abbreviation for the current hand's game and limit."""
    hand = get_hand_instance()
    try:
        if hand is None or "gametype" not in hand:
            return "NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation"
        game_type = hand.gametype
        value = GAME_ABBREVIATIONS.get(f"{game_type['category']}.{game_type['limitType']}", "Unknown")
        return value, value, f"game={value}", f"game_abbr={value}", f"({value})", "Game abbreviation"
    except (KeyError, TypeError, ValueError):
        return "NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation"


def n(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Format the number of observed hands, using compact notation for large samples."""
    try:
        hands = stat_dict[player]["n"]
        display = f"{int(hands)}"
        if hands >= 10000:
            thousands = hands / 1000
            remainder = hands % 1000
            decimal = round(float(remainder) / 100.0)
            if decimal == 10:
                thousands += 1
                decimal = 0
            display = f"{int(thousands)}.{decimal}k"
        return hands, display, f"n={int(hands)}", f"n={int(hands)}", f"({int(hands)})", "Number of hands seen"
    except (KeyError, TypeError, ValueError):
        return 0, "0", "n=0", "n=0", "(0)", "Number of hands seen"


def playername(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the player's full screen name."""
    try:
        name = str(stat_dict[player]["screen_name"])
        return name, name, name, name, name, "Player name"
    except (KeyError, TypeError, ValueError):
        return "", "", "", "", "", "Player name"


def playershort(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the screen name truncated to the historical six-character cell width."""
    try:
        full_name = str(stat_dict[player]["screen_name"])
    except (KeyError, TypeError, ValueError):
        return "", "", "", "", "", "Player Name 1-5"
    short_name = full_name[:5] + "." if len(full_name) > 6 else full_name
    return short_name, short_name, short_name, short_name, full_name, "Player Name 1-5"


def playerprofile(stat_dict: Mapping[int, Mapping[str, Any]] | None, player: int | None) -> DisplayTuple:
    """Return the dynamically classified player profile."""
    try:
        if stat_dict is None or player is None:
            raise TypeError("None parameter")
        from fpdb_3_legacy.PlayerProfiler import classify_player

        profile, icon, _color = classify_player(stat_dict, player)
        return profile, icon, f"p={profile}", f"playerprofile={profile}", profile, "Player Profile"
    except Exception:  # intentional broad catch: the profile is optional display data
        return "unknown", "❓", "p=unknown", "playerprofile=unknown", "unknown", "Player Profile"


def starthands(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Retrieves the starting hands and their positions for a specific player in a hand.

    Args:
        stat_dict (dict): A dictionary containing the statistics.
        player (int): The ID of the player.

    Returns:
        tuple: A tuple containing the following:
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the starting hands and their positions.
            - A string representing the title of the statistic.

    Raises:
        None.

    Notes:
        - This function retrieves the starting hands and their positions for a specific player in a hand.
        - The starting hands and their positions are displayed in a specific format.
        - The function uses a global variable `get_hand_instance()` to get the hand instance.
        - The function executes a SQL query to retrieve the starting hands and their positions from the database.
        - The function formats the retrieved data and returns it as a tuple.

    """
    hand_instance = get_hand_instance()
    if not hand_instance:
        return ("", "", "", "", "", "Hands seen at this table")

    # summary of known starting hands+position
    # data volumes could get crazy here,so info is limited to hands
    # in the current HH file only

    # this info is NOT read from the cache, so does not obey aggregation
    # parameters for other stats

    # display shows 5 categories
    # PFcall - limp or coldcall preflop
    # PFaggr - raise preflop
    # PFdefend - defended in BB
    # PFcar

    # hand is shown, followed by position indicator
    # (b=SB/BB. l=Button/cutoff m=previous 3 seats to that, e=remainder)

    # due to screen space required for this stat, it should only
    # be used in the popup section i.e.
    # <pu_stat pu_stat_name="starthands"> </pu_stat>
    handid = int(hand_instance.handid_selected)
    PFlimp = "Limped:"
    PFaggr = "Raised:"
    PFcar = "Called raise:"
    PFdefendBB = "Defend BB:"
    count_pfl = count_pfa = count_pfc = count_pfd = 5

    c = Configuration.Config()
    db_connection = Database.Database(c)
    sc = db_connection.get_cursor()

    query = (
        "SELECT distinct startCards, street0Aggr, street0CalledRaiseDone, "
        "case when HandsPlayers.position = 'B' then 'b' "
        "when HandsPlayers.position = 'S' then 'b' "
        "when HandsPlayers.position = '0' then 'l' "
        "when HandsPlayers.position = '1' then 'l' "
        "when HandsPlayers.position = '2' then 'm' "
        "when HandsPlayers.position = '3' then 'm' "
        "when HandsPlayers.position = '4' then 'm' "
        "when HandsPlayers.position = '5' then 'e' "
        "when HandsPlayers.position = '6' then 'e' "
        "when HandsPlayers.position = '7' then 'e' "
        "when HandsPlayers.position = '8' then 'e' "
        "when HandsPlayers.position = '9' then 'e' "
        "else 'X' end "
        "FROM Hands, HandsPlayers, Gametypes "
        "WHERE HandsPlayers.handId = Hands.id "
        " AND Gametypes.id = Hands.gametypeid "
        " AND Gametypes.type = "
        "   (SELECT Gametypes.type FROM Gametypes, Hands   "
        "  WHERE Hands.gametypeid = Gametypes.id and Hands.id = %d) "
        " AND Gametypes.Limittype =  "
        "   (SELECT Gametypes.limitType FROM Gametypes, Hands  "
        " WHERE Hands.gametypeid = Gametypes.id and Hands.id = %d) "
        "AND Gametypes.category = 'holdem' "
        "AND fileId = (SELECT fileId FROM Hands "
        " WHERE Hands.id = %d) "
        "AND HandsPlayers.playerId = %d "
        "AND street0VPI "
        "AND startCards > 0 AND startCards <> 170 "
        "ORDER BY startCards DESC "
        ";"
    ) % (int(handid), int(handid), int(handid), int(player))

    # print query
    sc.execute(query)
    for qstartcards, qstreet0Aggr, qstreet0CalledRaiseDone, qposition in sc.fetchall():
        humancards = Card.decodeStartHandValue("holdem", qstartcards)
        # print humancards, qstreet0Aggr, qstreet0CalledRaiseDone, qposition
        if qposition == "b" and qstreet0CalledRaiseDone:
            PFdefendBB = PFdefendBB + "/" + humancards
            count_pfd += 1
            if count_pfd / 8.0 == int(count_pfd / 8.0):
                PFdefendBB = PFdefendBB + "\n"
        elif qstreet0Aggr is True:
            PFaggr = PFaggr + "/" + humancards + "." + qposition
            count_pfa += 1
            if count_pfa / 8.0 == int(count_pfa / 8.0):
                PFaggr = PFaggr + "\n"
        elif qstreet0CalledRaiseDone:
            PFcar = PFcar + "/" + humancards + "." + qposition
            count_pfc += 1
            if count_pfc / 8.0 == int(count_pfc / 8.0):
                PFcar = PFcar + "\n"
        else:
            PFlimp = PFlimp + "/" + humancards + "." + qposition
            count_pfl += 1
            if count_pfl / 8.0 == int(count_pfl / 8.0):
                PFlimp = PFlimp + "\n"
    sc.close()

    returnstring = PFlimp + "\n" + PFaggr + "\n" + PFcar + "\n" + PFdefendBB  # + "\n" + str(handid)

    return (
        (returnstring),
        (returnstring),
        (returnstring),
        (returnstring),
        (returnstring),
        "Hands seen at this table\n",
    )
