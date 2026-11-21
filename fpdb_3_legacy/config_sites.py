"""Sites, e-mail accounts, hero aliases and profiles, data sources and supported games."""

# Handles fpdb/fpdb-hud configuration files.
#    Copyright 2008-2012,  Ray E. Barker
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
########################################################################
from __future__ import annotations

from fpdb_3_legacy import config_xml as cx
from fpdb_3_legacy.config_common import (
    ConfigBase,
    normalizePath,
    string_to_bool,
)
from fpdb_3_legacy.disabled_sites import is_site_disabled, is_site_import_only
from fpdb_3_legacy.hud_profiles import HudContext, HudProfileResolver
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class Email:
    def __init__(self, node) -> None:
        # pylint: disable=invalid-name  # the attribute names are the HUD_config.xml ones, read by name elsewhere
        self.node = node
        self.host = cx.attr(node, "host")
        self.username = cx.attr(node, "username")
        self.password = cx.attr(node, "password")
        self.useSsl = cx.attr(node, "useSsl")
        self.folder = cx.attr(node, "folder")
        self.fetchType = cx.attr(node, "fetchType")

    def __str__(self) -> str:
        return f"    email\n        fetchType = {self.fetchType}  host = {self.host}\n        username = {self.username} password = {self.password}\n        useSsl = {self.useSsl} folder = {self.folder}"


class Site:
    def __init__(self, node) -> None:
        # pylint: disable=invalid-name  # the attribute names are the HUD_config.xml ones, read by name elsewhere
        self.site_name = cx.attr(node, "site_name")
        self.screen_name = cx.attr(node, "screen_name")
        self.site_path = normalizePath(cx.attr(node, "site_path"))
        self.HH_path = normalizePath(cx.attr(node, "HH_path"))
        self.TS_path = normalizePath(cx.attr(node, "TS_path"))
        self.enabled = string_to_bool(cx.attr(node, "enabled"), default=True)
        # A room whose support is switched off stays off whatever the config
        # file says: an older HUD_config.xml (or the preferences editor) may
        # still carry enabled="True" for it. See fpdb_3_legacy.disabled_sites.
        if is_site_disabled(self.site_name):
            self.enabled = False
        self.aux_enabled = string_to_bool(cx.attr(node, "aux_enabled"), default=True)
        # An import-only room's files are imported after the session; no HUD
        # runs at its tables, whatever the config file says.
        if is_site_import_only(self.site_name):
            self.aux_enabled = False
        xshift = cx.attr(node, "hud_menu_xshift")
        self.hud_menu_xshift = 1 if xshift == "" else int(xshift)
        yshift = cx.attr(node, "hud_menu_yshift")
        self.hud_menu_yshift = 1 if yshift == "" else int(yshift)
        if cx.has_attr(node, "TS_path"):
            self.TS_path = normalizePath(cx.attr(node, "TS_path"))
        else:
            self.TS_path = ""

        # Support for the network attribute (configuration by skins)
        self.network = cx.attr(node, "network", "Unknown")

        # Hero aliases: a room can recognise several screen names as the hero
        # (nickname changes, multiple accounts). The primary ``screen_name`` is
        # always the first alias; additional ones come from <hero_alias> child
        # elements. Backward compatible: no <hero_alias> => [screen_name].
        self.hero_aliases = []
        _seen_aliases = set()
        for _alias in [self.screen_name] + [cx.attr(n, "name") for n in cx.find_all(node, "hero_alias")]:
            if _alias and _alias not in _seen_aliases:
                _seen_aliases.add(_alias)
                self.hero_aliases.append(_alias)

        self.fav_seat = {}
        for fav_node in cx.find_all(node, "fav"):
            max_seats = int(cx.attr(fav_node, "max"))
            fav = int(cx.attr(fav_node, "fav_seat"))
            self.fav_seat[max_seats] = fav

        self.layout_set = {}
        for site_layout_node in cx.find_all(node, "layout_set"):
            gt = cx.attr(site_layout_node, "game_type")
            ls = cx.attr(site_layout_node, "ls")
            self.layout_set[gt] = ls

        self.emails = {}
        for email_node in cx.find_all(node, "email"):
            email = Email(email_node)
            self.emails[email.fetchType] = email

    def __str__(self) -> str:
        temp = "Site = " + self.site_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "layout_set":
                continue
            if key == "fav_seat":
                continue
            if key == "emails":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + str(value) + "\n"

        for fetchtype in self.emails:
            temp = temp + str(self.emails[fetchtype]) + "\n"

        for game_type in self.layout_set:
            temp = temp + f"    game_type = {game_type}, layout_set = {self.layout_set[game_type]}\n"

        for max in self.fav_seat:
            temp = temp + f"    max = {max}, fav_seat = {self.fav_seat[max]}\n"

        return temp


class HeroProfile:
    """A logical hero identity spanning one or more rooms.

    Links a set of ``(site_name, alias)`` pairs so stats/reports can aggregate a
    player's identity across rooms (e.g. ``koko`` on Stars + ``koko76`` on
    Winamax). Parsed from::

        <hero_profile name="Me" default="True">
            <link site_name="PokerStars" alias="koko"/>
            <link site_name="Winamax"    alias="koko76"/>
        </hero_profile>
    """

    def __init__(self, node) -> None:
        self.name = cx.attr(node, "name")
        self.default = string_to_bool(cx.attr(node, "default"), default=False)
        self.links: list[tuple[str, str]] = []
        seen = set()
        for link in cx.find_all(node, "link"):
            site = cx.attr(link, "site_name")
            alias = cx.attr(link, "alias")
            if site and alias and (site, alias) not in seen:
                seen.add((site, alias))
                self.links.append((site, alias))

    def aliases_by_site(self):
        """Return ``{site_name: [alias, ...]}`` for this profile."""
        out: dict[str, list[str]] = {}
        for site, alias in self.links:
            out.setdefault(site, []).append(alias)
        return out

    def sites(self):
        """Return the ordered, deduplicated list of sites in this profile."""
        out: list[str] = []
        for site, _alias in self.links:
            if site not in out:
                out.append(site)
        return out

    def __str__(self) -> str:
        links = ", ".join(f"{s}:{a}" for s, a in self.links)
        return f"HeroProfile {self.name} (default={self.default}) [{links}]"


#: Sources fpdb stores hands under without being a poker room: no parser, no
#: ``<site>`` entry, no HUD. Each is its own ``Sites`` row (``phh_import.PHH_SITE_NAME``).
DATA_SOURCES: tuple[str, ...] = ("PHH",)


class DataSource:
    """The hero identity of a data source (#423): which of its players are the hero.

    A data source is not a room, so it has no ``<site>`` and no ``screen_name``; its
    hero is a list of names, resolved exactly like a room's hero aliases. Parsed from::

        <data_sources>
            <data_source name="PHH">
                <hero_alias name="koko"/>
                <hero_alias name="koko76"/>
            </data_source>
        </data_sources>
    """

    def __init__(self, node) -> None:
        self.name = cx.attr(node, "name")
        self.hero_aliases: list[str] = []
        for alias_node in cx.find_all(node, "hero_alias"):
            alias = cx.attr(alias_node, "name")
            if alias and alias not in self.hero_aliases:
                self.hero_aliases.append(alias)

    def __str__(self) -> str:
        return f"DataSource {self.name} [{', '.join(self.hero_aliases)}]"


class Supported_games:
    def __init__(self, node) -> None:
        self.game_name = ""
        for name, value in cx.attributes(node).items():
            setattr(self, name, value)

        self.game_stat_set = {}
        for game_stat_set_node in cx.find_all(node, "game_stat_set"):
            gss = Game_stat_set(game_stat_set_node)
            self.game_stat_set[gss.game_type] = gss

    def __str__(self) -> str:
        temp = "Supported_games = " + self.game_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "game_stat_set":
                continue
            if key == "game_name":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + value + "\n"

        for gs in self.game_stat_set:
            temp = temp + f"{self.game_stat_set[gs]!s}"
        return temp


class Game_stat_set:
    def __init__(self, node) -> None:
        self.game_type = cx.attr(node, "game_type")
        self.stat_set = cx.attr(node, "stat_set")

    def __str__(self) -> str:
        return f"      Game Type: '{self.game_type}' Stat Set: '{self.stat_set}'\n"


class ConfigSitesMixin(ConfigBase):
    """Read and edit the sites, heroes and supported games."""

    def get_site_node(self, site):
        for site_node in cx.find_all(self.doc, "site"):
            if cx.attr(site_node, "site_name") == site:
                return site_node
        return None

    def getEmailNode(self, siteName, fetchType):
        site_node = self.get_site_node(siteName)
        for email_node in cx.find_all(site_node, "email"):
            if cx.attr(email_node, "fetchType") == fetchType:
                return email_node
                break
        return None

    # end def getEmailNode

    def getGameNode(self, gameName):
        """Returns DOM game node for a given game."""
        for game_node in cx.find_all(self.doc, "game"):
            if cx.attr(game_node, "game_name") == gameName:
                return game_node
        return None

    # end def getGameNode

    def editEmail(self, siteName, fetchType, newEmail) -> None:
        emailNode = self.getEmailNode(siteName, fetchType)
        cx.set_attr(emailNode, "host", newEmail.host)
        cx.set_attr(emailNode, "username", newEmail.username)
        cx.set_attr(emailNode, "password", newEmail.password)
        cx.set_attr(emailNode, "folder", newEmail.folder)
        cx.set_attr(emailNode, "useSsl", newEmail.useSsl)

    # end def editEmail

    def edit_site(self, site_name, enabled, screen_name, history_path, summary_path) -> None:
        site_node = self.get_site_node(site_name)
        cx.set_attr(site_node, "enabled", enabled)
        cx.set_attr(site_node, "screen_name", screen_name)
        cx.set_attr(site_node, "HH_path", history_path)
        if summary_path:
            cx.set_attr(site_node, "TS_path", summary_path)

    def get_hero_aliases(self, site_name):
        """Return all hero screen names recognised for a site.

        The primary ``screen_name`` is always first, followed by any extra
        ``<hero_alias>`` entries (deduplicated). Returns ``[]`` for an unknown
        site. Backward compatible: a site without aliases yields
        ``[screen_name]``. A data source (``PHH``) answers with its own
        ``<data_source>`` aliases, so its hero resolves the way a room's does (#423).
        """
        site = self.supported_sites.get(site_name)
        if site is None and site_name:
            for k, v in self.supported_sites.items():
                if k.lower() == site_name.lower():
                    site = v
                    break
        if site is None:
            return self.get_data_source_hero_aliases(site_name)
        return list(getattr(site, "hero_aliases", []) or ([site.screen_name] if site.screen_name else []))

    def get_data_source_names(self) -> list[str]:
        """The data sources a hero can be configured for: the built-in ones, then any other configured."""
        names = list(DATA_SOURCES)
        names.extend(name for name in self.data_sources if name not in names)
        return names

    def is_data_source(self, name) -> bool:
        """True if *name* is a data source rather than a configured room."""
        return bool(name) and name not in self.supported_sites and name in self.get_data_source_names()

    def get_data_source_hero_aliases(self, name) -> list[str]:
        """The hero aliases configured for a data source; ``[]`` when none are."""
        if not name:
            return []
        source = self.data_sources.get(name)
        if source is None:
            source = next((v for k, v in self.data_sources.items() if k.lower() == name.lower()), None)
        return list(source.hero_aliases) if source is not None else []

    def _get_data_sources_node(self, create=False):
        """Return the ``<data_sources>`` DOM node, optionally creating it."""
        nodes = cx.find_all(self.doc, "data_sources")
        if nodes:
            return nodes[0]
        if not create:
            return None
        node = cx.create_element(self.doc, "data_sources")
        cx.append(self.doc, cx.root(self.doc), node)
        return node

    def set_data_source_hero_aliases(self, name, aliases) -> None:
        """Persist a data source's hero aliases into the config DOM (#423).

        Replaces the ``<data_source>`` of that name; no aliases removes it, so a
        configuration that never named a hero for a source carries no entry for it.
        Keeps the in-memory ``data_sources`` in sync. Like :meth:`set_hero_aliases`,
        the caller saves.
        """
        ordered: list[str] = []
        for alias in aliases:
            if alias and alias not in ordered:
                ordered.append(alias)

        sources_node = self._get_data_sources_node(create=bool(ordered))
        if sources_node is not None:
            for old in list(cx.find_all(sources_node, "data_source")):
                if cx.attr(old, "name") == name:
                    cx.remove(self.doc, old)
        if not ordered:
            self.data_sources.pop(name, None)
            return

        source_node = cx.create_element(self.doc, "data_source")
        cx.set_attr(source_node, "name", name)
        for alias in ordered:
            alias_node = cx.create_element(self.doc, "hero_alias")
            cx.set_attr(alias_node, "name", alias)
            cx.append(self.doc, source_node, alias_node)
        cx.append(self.doc, sources_node, source_node)
        self.data_sources[name] = DataSource(node=source_node)

    def set_hero_aliases(self, site_name, aliases) -> None:
        """Persist the hero aliases for a site into the config DOM.

        The first alias becomes the primary ``screen_name``; the remaining ones
        are written as ``<hero_alias name=.../>`` children (replacing existing
        ones). Keeps the in-memory ``Site`` object in sync.
        """
        # Deduplicate while preserving order.
        ordered = []
        seen = set()
        for alias in aliases:
            if alias and alias not in seen:
                seen.add(alias)
                ordered.append(alias)

        site_node = self.get_site_node(site_name)
        primary = ordered[0] if ordered else ""
        cx.set_attr(site_node, "screen_name", primary)

        # Remove existing <hero_alias> children before re-adding.
        for old in list(cx.find_all(site_node, "hero_alias")):
            cx.remove(self.doc, old)

        for alias in ordered[1:]:
            alias_node = cx.create_element(self.doc, "hero_alias")
            cx.set_attr(alias_node, "name", alias)
            cx.append(self.doc, site_node, alias_node)

        if site_name in self.supported_sites:
            self.supported_sites[site_name].screen_name = primary
            self.supported_sites[site_name].hero_aliases = ordered

    def is_hero_name(self, site_name, name) -> bool:
        """True if ``name`` is one of the hero aliases configured for a site."""
        if not name:
            return False
        aliases = [a.lower() for a in self.get_hero_aliases(site_name)]
        return name.lower() in aliases

    def get_hero_profiles(self):
        """Return ``{name: HeroProfile}`` for all configured multiroom profiles."""
        return self.hero_profiles

    def get_default_hero_profile(self):
        """Return the default hero profile, or the first one, or ``None``."""
        for hp in self.hero_profiles.values():
            if hp.default:
                return hp
        return next(iter(self.hero_profiles.values()), None)

    def _get_hero_profiles_node(self, create=False):
        """Return the ``<hero_profiles>`` DOM node, optionally creating it."""
        nodes = cx.find_all(self.doc, "hero_profiles")
        if nodes:
            return nodes[0]
        if not create:
            return None
        root = cx.find_all(self.doc, "FreePokerToolsConfig")[0]
        node = cx.create_element(self.doc, "hero_profiles")
        cx.append(self.doc, root, node)
        return node

    def save_hero_profile(self, name, links, default=False) -> None:
        """Create or replace a multiroom hero profile in the config DOM.

        ``links`` is an iterable of ``(site_name, alias)`` pairs. Keeps the
        in-memory ``hero_profiles`` dict in sync.
        """
        # Deduplicate links, preserving order.
        ordered_links = []
        seen = set()
        for site, alias in links:
            if site and alias and (site, alias) not in seen:
                seen.add((site, alias))
                ordered_links.append((site, alias))

        profiles_node = self._get_hero_profiles_node(create=True)

        # Remove an existing profile with the same name before re-adding.
        for old in list(cx.find_all(profiles_node, "hero_profile")):
            if cx.attr(old, "name") == name:
                cx.remove(self.doc, old)

        hp_node = cx.create_element(self.doc, "hero_profile")
        cx.set_attr(hp_node, "name", name)
        cx.set_attr(hp_node, "default", str(bool(default)))
        for site, alias in ordered_links:
            link_node = cx.create_element(self.doc, "link")
            cx.set_attr(link_node, "site_name", site)
            cx.set_attr(link_node, "alias", alias)
            cx.append(self.doc, hp_node, link_node)
        cx.append(self.doc, profiles_node, hp_node)

        self.hero_profiles[name] = HeroProfile(node=hp_node)

    def delete_hero_profile(self, name) -> None:
        """Remove a multiroom hero profile from the config DOM and memory."""
        profiles_node = self._get_hero_profiles_node(create=False)
        if profiles_node is not None:
            for old in list(cx.find_all(profiles_node, "hero_profile")):
                if cx.attr(old, "name") == name:
                    cx.remove(self.doc, old)
        self.hero_profiles.pop(name, None)

    def getDefaultSite(self):
        """Returns first enabled site or None."""
        for site_name, site in list(self.supported_sites.items()):
            if site.enabled:
                return site_name
        return None

    def get_supported_sites(self, all=False):
        """Returns the list of supported sites."""
        if all:
            return list(self.supported_sites.keys())
        return [site_name for (site_name, site) in list(self.supported_sites.items()) if site.enabled]

    def get_site_parameters(self, site):
        """Returns a dict of the site parameters for the specified site."""
        parms = {}
        # A site can be enabled under <supported_sites> without a matching <hhc>
        # converter entry (e.g. "BetOnline" vs "BetOnline Poker"). Don't raise
        # KeyError here: callers that iterate every enabled site (auto-import,
        # HUD_main.read_stdin) would otherwise abort on the first such site and
        # the HUD would never create a table window.
        hhc = self.hhcs.get(site)
        if hhc is None:
            log.warning("No <hhc> converter configured for site '%s'; import/HUD disabled for it", site)
        parms["converter"] = hhc.converter if hhc is not None else None
        parms["summaryImporter"] = hhc.summaryImporter if hhc is not None else None
        parms["screen_name"] = self.supported_sites[site].screen_name
        parms["site_path"] = self.supported_sites[site].site_path
        parms["HH_path"] = self.supported_sites[site].HH_path
        parms["TS_path"] = self.supported_sites[site].TS_path
        parms["site_name"] = self.supported_sites[site].site_name
        parms["enabled"] = self.supported_sites[site].enabled
        parms["aux_enabled"] = self.supported_sites[site].aux_enabled
        parms["hud_menu_xshift"] = self.supported_sites[site].hud_menu_xshift
        parms["hud_menu_yshift"] = self.supported_sites[site].hud_menu_yshift
        parms["layout_set"] = self.supported_sites[site].layout_set
        parms["emails"] = self.supported_sites[site].emails
        parms["fav_seat"] = self.supported_sites[site].fav_seat

        return parms

    def set_site_ids(self, sites) -> None:
        self.site_ids = dict(sites)

    def get_site_id(self, site):
        if not self.site_ids or site not in self.site_ids:
            # Fallback for standalone/testing environments
            fallbacks = {
                "Full Tilt Poker": 1,
                "PokerStars": 2,
                "Everleaf": 3,
                "Boss": 4,
                "OnGame": 5,
                "UltimateBet": 6,
                "Betfair": 7,
                "Absolute": 8,
                "PartyPoker": 9,
                "PacificPoker": 10,
                "Partouche": 11,
                "Merge": 12,
                "PKR": 13,
                "iPoker": 14,
                "BetOnline": 19,
                "Microgaming": 20,
                "Bovada": 21,
                "Enet": 22,
                "SealsWithClubs": 23,
                "WinningPoker": 24,
                "PokerMaster": 25,
                "Run It Once Poker": 26,
                "GGPoker": 27,  # Note: Database.py has GG=27, GGPokerToFpdb has site_id=27. GGPoker=110 in legacy config but matches 27 in db. Let's make sure both/either are supported or match GGPokerToFpdb.
                "KingsClub": 28,
                "PokerBros": 29,
                "Unibet": 30,
                "PokerStars.COM": 32,
                "PokerStars.FR": 33,
                "PokerStars.IT": 34,
                "PokerStars.ES": 35,
                "PokerStars.PT": 36,
                "PokerStars.EU": 37,
                "Party Poker": 38,
                "PMU Poker": 56,
                "FDJ Poker": 57,
                "Poker770": 58,
                "NetBet Poker": 59,
                "Barrière Poker": 60,
                "Red Star Poker": 61,
                "Titan Poker": 62,
                "Bet365 Poker": 63,
                "William Hill Poker": 64,
                "Paddy Power Poker": 65,
                "Betfair Poker": 66,
                "Coral Poker": 67,
                "Genting Poker": 68,
                "Mansion Poker": 69,
                "Winner Poker": 70,
                "Ladbrokes Poker": 71,
                "Sky Poker": 72,
                "Sisal Poker": 73,
                "Lottomatica Poker": 74,
                "Eurobet Poker": 75,
                "Snai Poker": 76,
                "Goldbet Poker": 77,
                "Casino Barcelona Poker": 78,
                "Sportium Poker": 79,
                "Marca Apuestas Poker": 80,
                "Everest Poker": 81,
                "Bet-at-home Poker": 82,
                "Mybet Poker": 83,
                "Betsson Poker": 84,
                "Betsafe Poker": 85,
                "NordicBet Poker": 86,
                "Unibet Poker": 87,
                "Maria Casino Poker": 88,
                "LeoVegas Poker": 89,
                "Mr Green Poker": 90,
                "Redbet Poker": 91,
                "Betclic Poker": 131,
                "Bet365.fr Poker": 132,
                "Betclic": 142,
                "BetRivers": 144,
                "PokerStars.UK": 145,
            }
            return fallbacks.get(site, 2)
        return self.site_ids[site]

    def get_supported_games(self):
        """Get the list of supported games."""
        sg = []
        for game in list(self.supported_games.keys()):
            sg.append(self.supported_games[game].game_name)
        return sg

    def get_supported_games_parameters(self, name, game_type, context: HudContext | None = None):
        """Gets a dict of parameters from the named gametype."""
        param = {}
        if name in self.supported_games:
            for key in dir(self.supported_games[name]):
                if key.startswith("__"):
                    continue
                if key == ("game_stat_set"):
                    continue
                value = getattr(self.supported_games[name], key)
                if callable(value):
                    continue
                param[key] = value

            # some gymnastics now to load the correct Stats_sets instance
            # into the game_stat_set key

            game_stat_set = self.supported_games[name].game_stat_set

            if game_type in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set[game_type].stat_set]
            elif "all" in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set["all"].stat_set]
            else:
                return None

            if context is not None:
                fallback = getattr(param["game_stat_set"], "name", None)
                profile = HudProfileResolver(self.hud_profile_rules).resolve(context, fallback)
                if profile in self.stat_sets:
                    param["game_stat_set"] = self.stat_sets[profile]

            return param

        return None
