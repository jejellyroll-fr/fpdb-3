"""Regression tests for raw archive table DDL."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_raw import raw_schema_queries


def test_raw_archive_queries_are_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = raw_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_raw_hand_and_tourney_tables_remain_structurally_parallel() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        queries = raw_schema_queries(backend)
        hand = queries["createRawHands"]
        tourney = queries["createRawTourneys"]
        assert hand.replace("RawHands", "RawTourneys").replace("handId", "tourneyId").replace("rawHand", "rawTourney") == tourney
