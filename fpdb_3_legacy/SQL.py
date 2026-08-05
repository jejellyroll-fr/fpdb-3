#!/usr/bin/env python
from __future__ import annotations

"""Returns a dict of SQL statements used in fpdb."""

import sys

from fpdb_3_legacy.sql_indexes import index_queries
from fpdb_3_legacy.sql_metadata import metadata_queries
from fpdb_3_legacy.sql_queries_aof import aof_queries
from fpdb_3_legacy.sql_queries_cache_maintenance import cache_maintenance_queries
from fpdb_3_legacy.sql_queries_cache_rebuild import cache_rebuild_queries
from fpdb_3_legacy.sql_queries_cards_cache_write import cards_cache_write_queries
from fpdb_3_legacy.sql_queries_cash_profit import cash_profit_queries
from fpdb_3_legacy.sql_queries_core import core_lookup_queries
from fpdb_3_legacy.sql_queries_database_admin import database_admin_queries
from fpdb_3_legacy.sql_queries_filters import filter_queries
from fpdb_3_legacy.sql_queries_game_types import game_type_queries
from fpdb_3_legacy.sql_queries_hand_artifacts import hand_artifact_queries
from fpdb_3_legacy.sql_queries_hand_detail import hand_detail_queries
from fpdb_3_legacy.sql_queries_hand_player_persistence import hand_player_persistence_queries
from fpdb_3_legacy.sql_queries_hand_root_persistence import hand_root_persistence_queries
from fpdb_3_legacy.sql_queries_history import history_window_queries
from fpdb_3_legacy.sql_queries_hud_aggregated_stats import hud_aggregated_stats_queries
from fpdb_3_legacy.sql_queries_hud_cache_write import hud_cache_write_queries
from fpdb_3_legacy.sql_queries_hud_current_stats import hud_current_stats_queries
from fpdb_3_legacy.sql_queries_hud_session_stats import hud_session_stats_queries
from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries
from fpdb_3_legacy.sql_queries_opponents import opponent_report_queries
from fpdb_3_legacy.sql_queries_player_auto_notes import player_auto_note_queries
from fpdb_3_legacy.sql_queries_player_detailed import player_detailed_report_queries
from fpdb_3_legacy.sql_queries_player_position import player_position_stats_queries
from fpdb_3_legacy.sql_queries_player_stats import player_stats_queries
from fpdb_3_legacy.sql_queries_positions_cache_write import positions_cache_write_queries
from fpdb_3_legacy.sql_queries_replayer import replayer_queries
from fpdb_3_legacy.sql_queries_session_cache_write import session_cache_write_queries
from fpdb_3_legacy.sql_queries_session_stats import session_stats_queries
from fpdb_3_legacy.sql_queries_tournament_graph import tournament_graph_queries
from fpdb_3_legacy.sql_queries_tournament_persistence import tournament_persistence_queries
from fpdb_3_legacy.sql_queries_tournament_player import tournament_player_detailed_queries
from fpdb_3_legacy.sql_queries_utility import utility_queries
from fpdb_3_legacy.sql_query_placeholders import finalize_query_placeholders
from fpdb_3_legacy.sql_schema_aof import aof_schema_queries
from fpdb_3_legacy.sql_schema_cards_cache import cards_cache_schema_queries
from fpdb_3_legacy.sql_schema_core import core_schema_queries
from fpdb_3_legacy.sql_schema_game import game_schema_queries
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries
from fpdb_3_legacy.sql_schema_hand_player import hand_player_schema_queries
from fpdb_3_legacy.sql_schema_hand_root import root_hand_schema_queries
from fpdb_3_legacy.sql_schema_hud_cache import hud_cache_schema_queries
from fpdb_3_legacy.sql_schema_import import import_schema_queries
from fpdb_3_legacy.sql_schema_lookup import lookup_schema_queries
from fpdb_3_legacy.sql_schema_player import player_schema_queries
from fpdb_3_legacy.sql_schema_position_cache import position_cache_schema_queries
from fpdb_3_legacy.sql_schema_raw import raw_schema_queries
from fpdb_3_legacy.sql_schema_session_cache import session_cache_schema_queries
from fpdb_3_legacy.sql_schema_time import time_schema_queries
from fpdb_3_legacy.sql_schema_tournament import tournament_schema_queries
from fpdb_3_legacy.sql_schema_tournament_cache import tournament_cache_schema_queries

#    Copyright 2008-2011, Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

#    NOTES:  The sql statements use the placeholder %s for bind variables
#            which is then replaced by ? for sqlite. Comments can be included
#            within sql statements using C style /* ... */ comments, BUT
#            THE COMMENTS MUST NOT INCLUDE %s OR ?.

########################################################################

#    Standard Library modules


#    pyGTK modules

#    FreePokerTools modules


class Sql:
    def __init__(self, game="holdem", db_server="mysql") -> None:
        self.query = {}
        self.query.update(metadata_queries(db_server))
        self.query.update(aof_schema_queries(db_server))
        self.query.update(cards_cache_schema_queries(db_server))
        self.query.update(core_schema_queries(db_server))
        self.query.update(game_schema_queries(db_server))
        self.query.update(hand_schema_queries(db_server))
        self.query.update(hand_player_schema_queries(db_server))
        self.query.update(root_hand_schema_queries(db_server))
        self.query.update(hud_cache_schema_queries(db_server))
        self.query.update(import_schema_queries(db_server))
        self.query.update(lookup_schema_queries(db_server))
        self.query.update(player_schema_queries(db_server))
        self.query.update(position_cache_schema_queries(db_server))
        self.query.update(raw_schema_queries(db_server))
        self.query.update(session_cache_schema_queries(db_server))
        self.query.update(tournament_schema_queries(db_server))
        self.query.update(tournament_cache_schema_queries(db_server))
        self.query.update(time_schema_queries(db_server))
        self.query.update(index_queries(db_server))
        self.query.update(aof_queries())
        self.query.update(core_lookup_queries())
        self.query.update(database_admin_queries(db_server))
        self.query.update(cash_profit_queries())
        self.query.update(cache_maintenance_queries())
        self.query.update(cache_rebuild_queries(db_server))
        self.query.update(cards_cache_write_queries())
        self.query.update(filter_queries(db_server))
        self.query.update(game_type_queries(db_server))
        self.query.update(hand_artifact_queries())
        self.query.update(hand_detail_queries())
        self.query.update(hand_player_persistence_queries())
        self.query.update(hand_root_persistence_queries())
        self.query.update(history_window_queries(db_server))
        self.query.update(hud_aggregated_stats_queries())
        self.query.update(hud_current_stats_queries())
        self.query.update(hud_session_stats_queries(db_server))
        self.query.update(hud_cache_write_queries())
        self.query.update(import_auxiliary_queries())
        self.query.update(opponent_report_queries(db_server))
        self.query.update(player_detailed_report_queries(db_server))
        self.query.update(player_position_stats_queries(db_server))
        self.query.update(player_auto_note_queries())
        self.query.update(player_stats_queries(db_server))
        self.query.update(positions_cache_write_queries())
        self.query.update(replayer_queries())
        self.query.update(session_cache_write_queries())
        self.query.update(session_stats_queries(db_server))
        self.query.update(tournament_player_detailed_queries(db_server))
        self.query.update(tournament_graph_queries())
        self.query.update(tournament_persistence_queries(db_server))
        self.query.update(utility_queries())
        self.query = finalize_query_placeholders(self.query, db_server)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB SQL utility")
    parser.add_argument("--list-queries", action="store_true", help="List all available SQL queries")
    parser.add_argument("--show-query", metavar="QUERY_NAME", help="Show a specific SQL query")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    try:
        s = Sql()
    except Exception as e:  # intentional broad catch: CLI top-level Sql() init boundary
        print(f"Error initializing SQL: {e}")
        return 1

    if args.list_queries:
        print("=== Available SQL Queries ===")
        print(f"Total queries: {len(s.query)}")
        for i, query_name in enumerate(sorted(s.query.keys()), 1):
            print(f"  {i:3}. {query_name}")

    if args.show_query:
        query_name = args.show_query
        if query_name in s.query:
            print(f"\n=== Query: {query_name} ===")
            print(s.query[query_name])
        else:
            print(f"Query '{query_name}' not found")
            print("Use --list-queries to see available queries")
            return 1

    if args.interactive:
        print("Running original interactive test...")
        s = Sql()
        for _key in s.query:
            pass
        print("Interactive test complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
