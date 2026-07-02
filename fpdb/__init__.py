"""FPDB-3 - Free Poker Database

Clean Architecture implementation with hexagonal architecture pattern.

Layers:
- domain: Pure business logic entities and value objects
- application: Use cases, commands, queries (CQRS)
- infrastructure: Database, parsers, external services
- presentation: GUI, Web, CLI interfaces
"""

__version__ = "3.0.0"
__author__ = "FPDB Team"
__license__ = "AGPL-3.0"
