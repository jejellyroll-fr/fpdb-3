"""Player persistence and resolution for the fpdb database.

Split out of Database.py: these methods own the Players table queries, hero
aliases, hero profile resolution, player ID lookups and player insertion.
"""

from __future__ import annotations

import re
import sys
import traceback
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.database_lambda_dict import LambdaDict
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")
re_char = re.compile("[^a-zA-Z]")


def _site_key(site_name: str) -> str:
    """A site name compared loosely: "PokerStars.FR" and "pokerstars fr" are one key."""
    return site_name.lower().replace(" ", "").replace(".", "").replace("-", "")


class DatabasePlayersMixin:
    """Reads and writes player queries, hero profiles, and aliases.

    Mixed into Database.
    """

    # Provided by Database.
    sql: Any
    backend: Any
    config: Any
    connection: Any
    pcache: Any
    MYSQL_INNODB: int

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def get_site_id(self, site: str) -> Any: ...

        def get_last_insert_id(self, cursor: Any) -> Any: ...

        def insertOrUpdate(self, type: str, cursor: Any, key: Any, select: Any, insert: Any) -> Any: ...

    def get_player_id(self, config, siteName, playerName):
        c = self.connection.cursor()
        c.execute(self.sql.query["get_player_id"], (playerName, siteName))
        row = c.fetchone()
        if row:
            return row[0]

        ph = self.sql.query.get("placeholder", "%s")
        q1 = "SELECT id FROM Players WHERE name = %s".replace("%s", ph)
        c.execute(q1, (playerName,))
        rows = c.fetchall()
        if len(rows) == 1:
            log.info(
                f"Database.get_player_id: Fallback found unique player ID {rows[0][0]} for '{playerName}' (searched across all sites)"
            )
            return rows[0][0]
        elif len(rows) > 1:
            q2 = """
                SELECT p.id
                FROM Players p
                JOIN Sites s ON p.siteId = s.id
                WHERE p.name = %s
                AND (s.name LIKE %s OR %s LIKE s.name || %s)
            """.replace("%s", ph)
            c.execute(q2, (playerName, siteName + "%", siteName, "%"))
            match_rows = c.fetchall()
            if match_rows:
                log.info(
                    f"Database.get_player_id: Fallback matched site prefix player ID {match_rows[0][0]} for '{playerName}' on site '{siteName}' variant"
                )
                return match_rows[0][0]
            log.info(
                f"Database.get_player_id: Fallback returned first player ID {rows[0][0]} of multiple matches for '{playerName}'"
            )
            return rows[0][0]
        return None

    def get_player_site_id(self, playerId):
        c = self.connection.cursor()
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT siteId FROM Players WHERE id = %s".replace("%s", ph)
        c.execute(q, (playerId,))
        row = c.fetchone()
        if row:
            return row[0]
        return None

    def get_player_name_by_id(self, playerId):
        c = self.get_cursor()
        ph = self.sql.query.get("placeholder", "%s")
        q = "SELECT name FROM Players WHERE id = %s".replace("%s", ph)
        c.execute(q, (playerId,))
        row = c.fetchone()
        if row:
            return row[0]
        return None

    def get_player_names(self, config, site_id=None, like_player_name="%"):
        """Fetch player names from players. Use site_id and like_player_name if provided."""
        if site_id is None:
            site_id = -1
        c = self.get_cursor()
        c.execute(
            self.sql.query["get_player_names"],
            (like_player_name, site_id, site_id),
        )
        return c.fetchall()

    def _hero_aliases(self, site_name):
        """Resolve the configured hero aliases for a site, defensively."""
        cfg = self.config
        getter = getattr(cfg, "get_hero_aliases", None)
        if callable(getter):
            return list(getter(site_name) or [])
        site = getattr(cfg, "supported_sites", {}).get(site_name)
        if site is None:
            return []
        screen_name = getattr(site, "screen_name", "")
        return [screen_name] if screen_name else []

    def _resolve_alias_ids(self, site_name, aliases):
        """Resolve exact (siteId, name) matches for a list of aliases."""
        site_res = self.get_site_id(site_name)
        if not site_res:
            return set()
        site_id = site_res[0][0]
        aliases = [a for a in aliases if a]
        if not aliases:
            return set()
        ph = self.sql.query["placeholder"]
        marks = ",".join(["%s"] * len(aliases))
        q = f"SELECT id FROM Players WHERE siteId=%s AND name IN ({marks})".replace("%s", ph)
        c = self.get_cursor()
        c.execute(q, tuple([site_id, *aliases]))
        return {int(r[0]) for r in c.fetchall()}

    def get_hero_player_ids_for_profile(self, profile):
        """Return hero playerIds for a multiroom HeroProfile."""
        ids = set()
        for site_ids in self.get_hero_player_ids_by_site(profile).values():
            ids.update(site_ids)
        return sorted(ids)

    def get_hero_player_ids_by_site(self, profile):
        """Return ``{site_name: [playerId, ...]}`` for a multiroom HeroProfile.

        Each site lists the players its links resolve to; a site none of them resolve
        on is left out.
        """
        if isinstance(profile, str):
            getter = getattr(self.config, "get_hero_profiles", None)
            profile = getter().get(profile) if callable(getter) else None
        if profile is None:
            return {}
        by_site = {}
        for site_name, aliases in profile.aliases_by_site().items():
            site_ids = self._resolve_alias_ids(site_name, aliases)
            # A link imported under a site skin only ("PokerStars" linked, hands under
            # "PokerStars.FR"), as get_player_id resolves a hero selection.
            for alias in aliases:
                if not self._resolve_alias_ids(site_name, [alias]):
                    site_ids.update(self._resolve_alias_skin_ids(site_name, alias))
            if site_ids:
                by_site[site_name] = sorted(site_ids)
        return by_site

    def _resolve_alias_skin_ids(self, site_name, alias):
        """The players named *alias* on a skin of *site_name*, or the room a skin belongs to.

        Matched by site-name prefix, as ``get_player_id`` does -- but never on an
        unrelated room: a name alone stands for no one there.
        """
        if not alias or not site_name:
            return set()
        c = self.get_cursor()
        c.execute(self.sql.query["get_players_and_sites_by_name"], (alias,))
        wanted = _site_key(site_name)
        return {
            int(player_id)
            for player_id, stored_site in c.fetchall()
            if (key := _site_key(stored_site)) != wanted and (key.startswith(wanted) or wanted.startswith(key))
        }

    def get_player_identity(self, player_id):
        """``(site name, player name)`` of a player, or ``None``: who the analytics filters name."""
        c = self.get_cursor()
        c.execute(self.sql.query["get_player_identity"], (player_id,))
        row = c.fetchone()
        return (row[0], row[1]) if row else None

    def _is_data_source(self, site_name) -> bool:
        """Whether *site_name* is a data source (PHH) rather than a configured room."""
        is_source = getattr(self.config, "is_data_source", None)
        return bool(callable(is_source) and is_source(site_name))

    def get_hero_player_ids(self, site_name=None, profile=None):
        """Return every hero playerId for a site (multi-alias aware).

        A data source (PHH) answers with its configured hero aliases only (#423): its
        hero-flagged players are each file's own ``_hero``, not one hero, so they are no
        fallback there.
        """
        if profile is not None:
            return self.get_hero_player_ids_for_profile(profile)

        site_res = self.get_site_id(site_name)
        if not site_res:
            return []
        site_id = site_res[0][0]

        ids = self._resolve_alias_ids(site_name, self._hero_aliases(site_name))

        if not ids and not self._is_data_source(site_name):
            ph = self.sql.query["placeholder"]
            q = "SELECT id FROM Players WHERE siteId=%s AND hero=%s".replace("%s", ph)
            c = self.get_cursor()
            c.execute(q, (site_id, True))
            ids.update(int(r[0]) for r in c.fetchall())

        return sorted(ids)

    def get_selected_player_ids(self, site_name, name):
        """The players a report reads for *name* selected on *site_name*.

        The same players the report filters read (#434). On a configured room the alias
        selected stands for every hero alias configured there -- an old nickname, a
        second account -- or, when none of them is imported yet, the room's
        hero-flagged players. On a data source (PHH) one of its configured hero aliases
        stands for all of them (#423), and any other of its players for that player
        alone. When that resolves to no one, the name selected, resolved variant-aware:
        ``get_player_id`` maps a "PokerStars" selection to the hero's "PokerStars.FR"
        account, so data imported under a site skin still shows.
        """
        if self._stands_for_hero_aliases(site_name, name) and (ids := self.get_hero_player_ids(site_name)):
            return ids
        result = self.get_player_id(self.config, site_name, name)
        return [int(result)] if result is not None else []

    def _stands_for_hero_aliases(self, site_name, name) -> bool:
        """Whether *name* on *site_name* stands for every hero alias configured there.

        Mirrors ``Filters._resolves_by_alias``: a configured room always, a data source
        only for one of its configured hero aliases.
        """
        getter = getattr(self.config, "get_supported_sites", None)
        if callable(getter) and site_name in getter():
            return True
        return self._is_data_source(site_name) and name in self._hero_aliases(site_name)

    def getHeroIds(self, pids, sitename):
        try:
            hero_ids = []
            for site in self.config.get_supported_sites():
                aliases = set(self._hero_aliases(site))
                for n, v in list(pids.items()):
                    if sitename == site and n in aliases:
                        hero_ids.append(v)
        except Exception:
            err = traceback.extract_tb(sys.exc_info()[2])[-1]
            log.exception("Error acquiring hero ids")
            log.exception(f"traceback: {err}")
            hero_ids = []
        return hero_ids

    def getSqlPlayerIDs(self, pnames, siteid, hero):
        result = {}
        if self.pcache is None:
            self.pcache = LambdaDict(
                lambda key: self.insertPlayer(key[0], key[1], key[2]),
            )

        for player in pnames:
            result[player] = self.pcache[(player, siteid, player == hero)]

        return result

    def insertPlayer(self, name, site_id, hero):
        insert_player = "INSERT INTO Players (name, siteId, hero, chars) VALUES (%s, %s, %s, %s)"
        insert_player = insert_player.replace("%s", self.sql.query["placeholder"])
        _name = name[:32] if name else " "
        if not _name:
            _name = " "
        if re_char.match(_name[0]):
            char = "123"
        elif len(_name) == 1 or re_char.match(_name[1]):
            char = _name[0] + "1"
        else:
            char = _name[:2]

        key = (_name, site_id, hero, char.upper())

        c = self.get_cursor()
        if self.backend == self.MYSQL_INNODB:
            upsert_player = insert_player + " ON DUPLICATE KEY UPDATE hero=hero OR VALUES(hero), id=LAST_INSERT_ID(id)"
            c.execute(upsert_player, key)
            return self.get_last_insert_id(c)

        q = "SELECT id, name, hero FROM Players WHERE name=%s and siteid=%s"
        q = q.replace("%s", self.sql.query["placeholder"])
        return self.insertOrUpdate("players", c, key, q, insert_player)
