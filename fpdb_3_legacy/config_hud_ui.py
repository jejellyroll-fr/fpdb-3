"""The HUD's user-interface preferences (<hud_ui>)."""

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

from fpdb_3_legacy.config_common import (
    ConfigBase,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class HudUI:
    def __init__(self, node) -> None:
        self.node = node
        self.label = node.getAttribute("label")
        if node.hasAttribute("fast_fold_seat_wait_ms"):
            self.fast_fold_seat_wait_ms = node.getAttribute("fast_fold_seat_wait_ms")
        if node.hasAttribute("fast_fold_window_seats"):
            self.fast_fold_window_seats = node.getAttribute("fast_fold_window_seats")
        if node.hasAttribute("card_ht"):
            self.card_ht = node.getAttribute("card_ht")
        if node.hasAttribute("card_wd"):
            self.card_wd = node.getAttribute("card_wd")
        if node.hasAttribute("deck_type"):
            self.deck_type = node.getAttribute("deck_type")
        if node.hasAttribute("card_back"):
            self.card_back = node.getAttribute("card_back")
        if node.hasAttribute("stat_range"):
            self.stat_range = node.getAttribute("stat_range")
        if node.hasAttribute("stat_days"):
            self.hud_days = node.getAttribute("stat_days")
        if node.hasAttribute("aggregation_level_multiplier"):
            self.agg_bb_mult = node.getAttribute("aggregation_level_multiplier")
        if node.hasAttribute("seats_style"):
            self.seats_style = node.getAttribute("seats_style")
        if node.hasAttribute("seats_cust_nums_low"):
            self.seats_cust_nums_low = node.getAttribute("seats_cust_nums_low")
        if node.hasAttribute("seats_cust_nums_high"):
            self.seats_cust_nums_high = node.getAttribute("seats_cust_nums_high")
        if node.hasAttribute("hero_stat_range"):
            self.h_stat_range = node.getAttribute("hero_stat_range")
        if node.hasAttribute("hero_stat_days"):
            self.h_hud_days = node.getAttribute("hero_stat_days")
        if node.hasAttribute("hero_aggregation_level_multiplier"):
            self.h_agg_bb_mult = node.getAttribute("hero_aggregation_level_multiplier")
        if node.hasAttribute("hero_seats_style"):
            self.h_seats_style = node.getAttribute("hero_seats_style")
        if node.hasAttribute("hero_seats_cust_nums_low"):
            self.h_seats_cust_nums_low = node.getAttribute("hero_seats_cust_nums_low")
        if node.hasAttribute("hero_seats_cust_nums_high"):
            self.h_seats_cust_nums_high = node.getAttribute("hero_seats_cust_nums_high")

        # Additional HUD positioning attributes
        if node.hasAttribute("xshift"):
            self.xshift = node.getAttribute("xshift")
        if node.hasAttribute("yshift"):
            self.yshift = node.getAttribute("yshift")

        # Aggregation settings
        if node.hasAttribute("aggregate_ring"):
            self.aggregate_ring = node.getAttribute("aggregate_ring")
        if node.hasAttribute("aggregate_tour"):
            self.aggregate_tour = node.getAttribute("aggregate_tour")
        if node.hasAttribute("hud_style"):
            self.hud_style = node.getAttribute("hud_style")
        if node.hasAttribute("hero_stat_aggregation"):
            self.hero_stat_aggregation = node.getAttribute("hero_stat_aggregation")
        if node.hasAttribute("h_hud_style"):
            self.h_hud_style = node.getAttribute("h_hud_style")

        # Player profiling settings
        if node.hasAttribute("player_profiling"):
            self.player_profiling = node.getAttribute("player_profiling")
        if node.hasAttribute("profile_in_name"):
            self.profile_in_name = node.getAttribute("profile_in_name")
        if node.hasAttribute("profile_min_hands"):
            self.profile_min_hands = node.getAttribute("profile_min_hands")

        # Appearance settings
        if node.hasAttribute("bgcolor"):
            self.bgcolor = node.getAttribute("bgcolor")
        if node.hasAttribute("fgcolor"):
            self.fgcolor = node.getAttribute("fgcolor")
        if node.hasAttribute("hudbgcolor"):
            self.hudbgcolor = node.getAttribute("hudbgcolor")
        if node.hasAttribute("hudfgcolor"):
            self.hudfgcolor = node.getAttribute("hudfgcolor")
        if node.hasAttribute("font"):
            self.font = node.getAttribute("font")
        if node.hasAttribute("font_size"):
            self.font_size = node.getAttribute("font_size")

        # HUD opacity
        if node.hasAttribute("opacity"):
            self.opacity = node.getAttribute("opacity")

        # Popup settings
        if node.hasAttribute("popup_style"):
            self.popup_style = node.getAttribute("popup_style")

        # Mucked cards settings
        if node.hasAttribute("mucked_cards"):
            self.mucked_cards = node.getAttribute("mucked_cards")
        if node.hasAttribute("mucked_cards_size"):
            self.mucked_cards_size = node.getAttribute("mucked_cards_size")
        if node.hasAttribute("mucked_cards_opacity"):
            self.mucked_cards_opacity = node.getAttribute("mucked_cards_opacity")

        # Aux windows settings
        if node.hasAttribute("aux_windows"):
            self.aux_windows = node.getAttribute("aux_windows")
        if node.hasAttribute("aux_windows_opacity"):
            self.aux_windows_opacity = node.getAttribute("aux_windows_opacity")

        # HUD menu settings
        if node.hasAttribute("hud_menu_opacity"):
            self.hud_menu_opacity = node.getAttribute("hud_menu_opacity")
        if node.hasAttribute("hud_menu_bgcolor"):
            self.hud_menu_bgcolor = node.getAttribute("hud_menu_bgcolor")
        if node.hasAttribute("hud_menu_fgcolor"):
            self.hud_menu_fgcolor = node.getAttribute("hud_menu_fgcolor")

        # Stat window settings
        if node.hasAttribute("stat_window_opacity"):
            self.stat_window_opacity = node.getAttribute("stat_window_opacity")
        if node.hasAttribute("stat_window_frame"):
            self.stat_window_frame = node.getAttribute("stat_window_frame")

        # Tooltip settings
        if node.hasAttribute("tooltip_delay"):
            self.tooltip_delay = node.getAttribute("tooltip_delay")
        if node.hasAttribute("tooltip_bgcolor"):
            self.tooltip_bgcolor = node.getAttribute("tooltip_bgcolor")
        if node.hasAttribute("tooltip_fgcolor"):
            self.tooltip_fgcolor = node.getAttribute("tooltip_fgcolor")

        # Advanced settings
        if node.hasAttribute("update_interval"):
            self.update_interval = node.getAttribute("update_interval")
        if node.hasAttribute("max_seats"):
            self.max_seats = node.getAttribute("max_seats")
        if node.hasAttribute("debug_level"):
            self.debug_level = node.getAttribute("debug_level")

        # Behaviour settings. set_hud_ui_parameters has always written these
        # seven onto the node, but nothing read them back, so each one reached
        # the file and then lost to the default on the next start.
        if node.hasAttribute("auto_close"):
            self.auto_close = node.getAttribute("auto_close")
        if node.hasAttribute("block_click"):
            self.block_click = node.getAttribute("block_click")
        if node.hasAttribute("on_click"):
            self.on_click = node.getAttribute("on_click")
        if node.hasAttribute("disable_hud"):
            self.disable_hud = node.getAttribute("disable_hud")
        if node.hasAttribute("debug_hud"):
            self.debug_hud = node.getAttribute("debug_hud")
        if node.hasAttribute("save_layout"):
            self.save_layout = node.getAttribute("save_layout")
        if node.hasAttribute("query_limit"):
            self.query_limit = node.getAttribute("query_limit")

    def __str__(self) -> str:
        return f"    label = {self.label}\n"


class ConfigHudUiMixin(ConfigBase):
    """Read and write the HUD's user-interface preferences."""

    # Allow to change the menu appearance
    def get_hud_ui_parameters(self):
        hui = {}

        default_text = "FPDB Menu - Right click\nLeft-Drag to Move"

        try:
            hui["label"] = self.ui.label
            if self.ui.label == "":  # Empty menu label is a big no-no
                hui["label"] = default_text
        except AttributeError as e:
            log.exception(f"Error getting label: {e}")
            hui["label"] = default_text

        try:
            hui["card_ht"] = int(self.ui.card_ht)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting card height: {e}")
            hui["card_ht"] = 42

        try:
            hui["card_wd"] = int(self.ui.card_wd)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting card width: {e}")
            hui["card_wd"] = 30

        try:
            hui["deck_type"] = str(self.ui.deck_type)
        except AttributeError as e:
            log.exception(f"Error getting deck type: {e}")
            hui["deck_type"] = "colour"

        try:
            hui["card_back"] = str(self.ui.card_back)
        except AttributeError as e:
            log.exception(f"Error getting card back: {e}")
            hui["card_back"] = "back04"

        try:
            hui["stat_range"] = self.ui.stat_range
        except AttributeError as e:
            log.exception(f"Error getting stat range: {e}")
            hui["stat_range"] = "A"  # default is show stats for All-time, also S(session) and T(ime)

        try:
            hui["hud_days"] = int(self.ui.hud_days)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting HUD days: {e}")
            hui["hud_days"] = 90

        try:
            hui["agg_bb_mult"] = int(self.ui.agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting aggregate BB multiplier: {e}")
            hui["agg_bb_mult"] = 1

        try:
            hui["seats_style"] = self.ui.seats_style
        except AttributeError as e:
            log.exception(f"Error getting seats style: {e}")
            hui["seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["seats_cust_nums_low"] = int(self.ui.seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting custom seat numbers low: {e}")
            hui["seats_cust_nums_low"] = 1

        try:
            hui["seats_cust_nums_high"] = int(self.ui.seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting custom seat numbers high: {e}")
            hui["seats_cust_nums_high"] = 10

        # Hero specific
        try:
            hui["h_stat_range"] = self.ui.h_stat_range
        except AttributeError as e:
            log.exception(f"Error getting hero stat range: {e}")
            hui["h_stat_range"] = "S"

        try:
            hui["h_hud_days"] = int(self.ui.h_hud_days)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero HUD days: {e}")
            hui["h_hud_days"] = 30

        try:
            hui["h_agg_bb_mult"] = int(self.ui.h_agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero aggregate BB multiplier: {e}")
            hui["h_agg_bb_mult"] = 1

        try:
            hui["h_seats_style"] = self.ui.h_seats_style
        except AttributeError as e:
            log.exception(f"Error getting hero seats style: {e}")
            hui["h_seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["h_seats_cust_nums_low"] = int(self.ui.h_seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero custom seat numbers low: {e}")
            hui["h_seats_cust_nums_low"] = 1

        try:
            hui["h_seats_cust_nums_high"] = int(self.ui.h_seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero custom seat numbers high: {e}")
            hui["h_seats_cust_nums_high"] = 10

        # Additional parameters that might be stored in hud_ui node
        try:
            hui["xshift"] = int(getattr(self.ui, "xshift", 0))
        except (AttributeError, ValueError):
            hui["xshift"] = 0

        try:
            hui["yshift"] = int(getattr(self.ui, "yshift", 0))
        except (AttributeError, ValueError):
            hui["yshift"] = 0

        try:
            hui["aggregate_ring"] = getattr(self.ui, "aggregate_ring", "True")
        except AttributeError:
            hui["aggregate_ring"] = "True"

        # How long a Fast-Fold table waits for the client log to finish naming
        # its players before it shows the ones it has. The log names a player
        # only once they have acted, so a six-handed table is named over several
        # seconds: showing at once means blocks appearing one at a time, waiting
        # means they appear together but later. Neither is right for everyone,
        # so it is a number rather than a decision. The default is what the HUD
        # has always done.
        try:
            hui["fast_fold_seat_wait_ms"] = max(0, int(getattr(self.ui, "fast_fold_seat_wait_ms", 500)))
        except (AttributeError, TypeError, ValueError):
            hui["fast_fold_seat_wait_ms"] = 500

        # Whether to read a Fast-Fold table's chairs off its window at all.
        # "auto" tries, and gives up per table once the client has shown it will
        # not answer usefully; "off" never tries. Each read is a synchronous
        # walk of another process's accessibility tree on the GUI thread, 94 to
        # 218ms on a client that answers, so a player whose client has never
        # published its felt is paying for it in stutter and nothing else.
        try:
            value = str(getattr(self.ui, "fast_fold_window_seats", "auto")).strip().lower()
        except (AttributeError, TypeError, ValueError):
            value = "auto"
        hui["fast_fold_window_seats"] = value if value in ("auto", "off") else "auto"

        try:
            hui["aggregate_tour"] = getattr(self.ui, "aggregate_tour", "True")
        except AttributeError:
            hui["aggregate_tour"] = "True"

        try:
            hui["hud_style"] = getattr(self.ui, "hud_style", "A")
        except AttributeError:
            hui["hud_style"] = "A"

        try:
            hui["hero_stat_aggregation"] = getattr(self.ui, "hero_stat_aggregation", "False")
        except AttributeError:
            hui["hero_stat_aggregation"] = "False"

        try:
            hui["h_hud_style"] = getattr(self.ui, "h_hud_style", "A")
        except AttributeError:
            hui["h_hud_style"] = "A"

        # Appearance parameters
        try:
            hui["bgcolor"] = getattr(self.ui, "bgcolor", "#000000")
        except AttributeError:
            hui["bgcolor"] = "#000000"

        try:
            hui["fgcolor"] = getattr(self.ui, "fgcolor", "#FFFFFF")
        except AttributeError:
            hui["fgcolor"] = "#FFFFFF"

        try:
            hui["hudbgcolor"] = getattr(self.ui, "hudbgcolor", "#000000")
        except AttributeError:
            hui["hudbgcolor"] = "#000000"

        try:
            hui["hudfgcolor"] = getattr(self.ui, "hudfgcolor", "#FFFFFF")
        except AttributeError:
            hui["hudfgcolor"] = "#FFFFFF"

        try:
            hui["font"] = getattr(self.ui, "font", "Sans")
        except AttributeError:
            hui["font"] = "Sans"

        try:
            hui["font_size"] = getattr(self.ui, "font_size", "8")
        except AttributeError:
            hui["font_size"] = "8"

        # Opacity settings
        try:
            hui["opacity"] = getattr(self.ui, "opacity", "1.0")
        except AttributeError:
            hui["opacity"] = "1.0"

        # Mucked cards settings
        try:
            hui["mucked_cards"] = getattr(self.ui, "mucked_cards", "True")
        except AttributeError:
            hui["mucked_cards"] = "True"

        try:
            hui["mucked_cards_size"] = getattr(self.ui, "mucked_cards_size", "100")
        except AttributeError:
            hui["mucked_cards_size"] = "100"

        try:
            hui["mucked_cards_opacity"] = getattr(self.ui, "mucked_cards_opacity", "1.0")
        except AttributeError:
            hui["mucked_cards_opacity"] = "1.0"

        # Aux windows settings
        try:
            hui["aux_windows"] = getattr(self.ui, "aux_windows", "True")
        except AttributeError:
            hui["aux_windows"] = "True"

        try:
            hui["aux_windows_opacity"] = getattr(self.ui, "aux_windows_opacity", "1.0")
        except AttributeError:
            hui["aux_windows_opacity"] = "1.0"

        # HUD menu settings
        try:
            hui["hud_menu_opacity"] = getattr(self.ui, "hud_menu_opacity", "1.0")
        except AttributeError:
            hui["hud_menu_opacity"] = "1.0"

        try:
            hui["hud_menu_bgcolor"] = getattr(self.ui, "hud_menu_bgcolor", "#000000")
        except AttributeError:
            hui["hud_menu_bgcolor"] = "#000000"

        try:
            hui["hud_menu_fgcolor"] = getattr(self.ui, "hud_menu_fgcolor", "#FFFFFF")
        except AttributeError:
            hui["hud_menu_fgcolor"] = "#FFFFFF"

        # Stat window settings
        try:
            hui["stat_window_opacity"] = getattr(self.ui, "stat_window_opacity", "1.0")
        except AttributeError:
            hui["stat_window_opacity"] = "1.0"

        try:
            hui["stat_window_frame"] = getattr(self.ui, "stat_window_frame", "True")
        except AttributeError:
            hui["stat_window_frame"] = "True"

        # Tooltip settings
        try:
            hui["tooltip_delay"] = getattr(self.ui, "tooltip_delay", "1000")
        except AttributeError:
            hui["tooltip_delay"] = "1000"

        try:
            hui["tooltip_bgcolor"] = getattr(self.ui, "tooltip_bgcolor", "#FFFFE0")
        except AttributeError:
            hui["tooltip_bgcolor"] = "#FFFFE0"

        try:
            hui["tooltip_fgcolor"] = getattr(self.ui, "tooltip_fgcolor", "#000000")
        except AttributeError:
            hui["tooltip_fgcolor"] = "#000000"

        # Advanced settings
        try:
            hui["update_interval"] = getattr(self.ui, "update_interval", "10")
        except AttributeError:
            hui["update_interval"] = "10"

        try:
            hui["max_seats"] = getattr(self.ui, "max_seats", "10")
        except AttributeError:
            hui["max_seats"] = "10"

        try:
            hui["debug_level"] = getattr(self.ui, "debug_level", "INFO")
        except AttributeError:
            hui["debug_level"] = "INFO"

        # Behavior parameters
        try:
            hui["update_interval"] = int(getattr(self.ui, "update_interval", 10))
        except (AttributeError, ValueError):
            hui["update_interval"] = 10

        try:
            hui["auto_close"] = getattr(self.ui, "auto_close", "True")
        except AttributeError:
            hui["auto_close"] = "True"

        try:
            hui["block_click"] = getattr(self.ui, "block_click", "False")
        except AttributeError:
            hui["block_click"] = "False"

        try:
            hui["on_click"] = getattr(self.ui, "on_click", "Nothing")
        except AttributeError:
            hui["on_click"] = "Nothing"

        try:
            hui["popup_style"] = getattr(self.ui, "popup_style", "default")
        except AttributeError:
            hui["popup_style"] = "default"

        try:
            hui["stat_range"] = getattr(self.ui, "stat_range", "True")
        except AttributeError:
            hui["stat_range"] = "True"

        # Advanced parameters
        try:
            hui["max_seats"] = int(getattr(self.ui, "max_seats", 10))
        except (AttributeError, ValueError):
            hui["max_seats"] = 10

        try:
            hui["disable_hud"] = getattr(self.ui, "disable_hud", "False")
        except AttributeError:
            hui["disable_hud"] = "False"

        try:
            hui["query_limit"] = int(getattr(self.ui, "query_limit", 1000))
        except (AttributeError, ValueError):
            hui["query_limit"] = 1000

        try:
            hui["debug_hud"] = getattr(self.ui, "debug_hud", "False")
        except AttributeError:
            hui["debug_hud"] = "False"

        try:
            hui["save_layout"] = getattr(self.ui, "save_layout", "True")
        except AttributeError:
            hui["save_layout"] = "True"

        try:
            hui["player_profiling"] = getattr(self.ui, "player_profiling", "True")
        except AttributeError:
            hui["player_profiling"] = "True"

        try:
            hui["profile_in_name"] = getattr(self.ui, "profile_in_name", "True")
        except AttributeError:
            hui["profile_in_name"] = "True"

        try:
            hui["profile_min_hands"] = int(getattr(self.ui, "profile_min_hands", 10))
        except (AttributeError, ValueError):
            hui["profile_min_hands"] = 10

        return hui

    def set_hud_ui_parameters(self, hud_params) -> None:
        """Set HUD UI parameters from a dictionary."""
        # Get the hud_ui node
        hud_ui_nodes = self.doc.getElementsByTagName("hud_ui")
        if not hud_ui_nodes:
            # Create hud_ui node if it doesn't exist
            for config_node in self.doc.getElementsByTagName("FreePokerToolsConfig"):
                hud_ui_node = self.doc.createElement("hud_ui")
                config_node.appendChild(hud_ui_node)
        else:
            hud_ui_node = hud_ui_nodes[0]

        # Update attributes
        if "label" in hud_params:
            hud_ui_node.setAttribute("label", str(hud_params["label"]))
        if "card_ht" in hud_params:
            hud_ui_node.setAttribute("card_ht", str(hud_params["card_ht"]))
        if "card_wd" in hud_params:
            hud_ui_node.setAttribute("card_wd", str(hud_params["card_wd"]))
        if "deck_type" in hud_params:
            hud_ui_node.setAttribute("deck_type", str(hud_params["deck_type"]))
        if "card_back" in hud_params:
            hud_ui_node.setAttribute("card_back", str(hud_params["card_back"]))
        if "stat_range" in hud_params:
            hud_ui_node.setAttribute("stat_range", str(hud_params["stat_range"]))
        if "hud_days" in hud_params:
            hud_ui_node.setAttribute("stat_days", str(hud_params["hud_days"]))
        if "agg_bb_mult" in hud_params:
            hud_ui_node.setAttribute("aggregation_level_multiplier", str(hud_params["agg_bb_mult"]))
        if "seats_style" in hud_params:
            hud_ui_node.setAttribute("seats_style", str(hud_params["seats_style"]))
        if "seats_cust_nums_low" in hud_params:
            hud_ui_node.setAttribute("seats_cust_nums_low", str(hud_params["seats_cust_nums_low"]))
        if "seats_cust_nums_high" in hud_params:
            hud_ui_node.setAttribute("seats_cust_nums_high", str(hud_params["seats_cust_nums_high"]))

        # Hero specific
        if "h_stat_range" in hud_params:
            hud_ui_node.setAttribute("hero_stat_range", str(hud_params["h_stat_range"]))
        if "h_hud_days" in hud_params:
            hud_ui_node.setAttribute("hero_stat_days", str(hud_params["h_hud_days"]))
        if "h_agg_bb_mult" in hud_params:
            hud_ui_node.setAttribute("hero_aggregation_level_multiplier", str(hud_params["h_agg_bb_mult"]))
        if "h_seats_style" in hud_params:
            hud_ui_node.setAttribute("hero_seats_style", str(hud_params["h_seats_style"]))
        if "h_seats_cust_nums_low" in hud_params:
            hud_ui_node.setAttribute("hero_seats_cust_nums_low", str(hud_params["h_seats_cust_nums_low"]))
        if "h_seats_cust_nums_high" in hud_params:
            hud_ui_node.setAttribute("hero_seats_cust_nums_high", str(hud_params["h_seats_cust_nums_high"]))

        # Additional appearance parameters
        if "bgcolor" in hud_params:
            hud_ui_node.setAttribute("bgcolor", str(hud_params["bgcolor"]))
        if "fgcolor" in hud_params:
            hud_ui_node.setAttribute("fgcolor", str(hud_params["fgcolor"]))
        if "hudbgcolor" in hud_params:
            hud_ui_node.setAttribute("hudbgcolor", str(hud_params["hudbgcolor"]))
        if "hudfgcolor" in hud_params:
            hud_ui_node.setAttribute("hudfgcolor", str(hud_params["hudfgcolor"]))
        if "font" in hud_params:
            hud_ui_node.setAttribute("font", str(hud_params["font"]))
        if "font_size" in hud_params:
            hud_ui_node.setAttribute("font_size", str(hud_params["font_size"]))
        if "opacity" in hud_params:
            hud_ui_node.setAttribute("opacity", str(hud_params["opacity"]))

        # Additional behavior parameters
        if "xshift" in hud_params:
            hud_ui_node.setAttribute("xshift", str(hud_params["xshift"]))
        if "yshift" in hud_params:
            hud_ui_node.setAttribute("yshift", str(hud_params["yshift"]))
        if "aggregate_ring" in hud_params:
            hud_ui_node.setAttribute("aggregate_ring", str(hud_params["aggregate_ring"]))
        if "aggregate_tour" in hud_params:
            hud_ui_node.setAttribute("aggregate_tour", str(hud_params["aggregate_tour"]))
        if "hud_style" in hud_params:
            hud_ui_node.setAttribute("hud_style", str(hud_params["hud_style"]))
        if "hero_stat_aggregation" in hud_params:
            hud_ui_node.setAttribute("hero_stat_aggregation", str(hud_params["hero_stat_aggregation"]))
        if "h_hud_style" in hud_params:
            hud_ui_node.setAttribute("h_hud_style", str(hud_params["h_hud_style"]))
        if "update_interval" in hud_params:
            hud_ui_node.setAttribute("update_interval", str(hud_params["update_interval"]))
        if "auto_close" in hud_params:
            hud_ui_node.setAttribute("auto_close", str(hud_params["auto_close"]))
        if "block_click" in hud_params:
            hud_ui_node.setAttribute("block_click", str(hud_params["block_click"]))
        if "on_click" in hud_params:
            hud_ui_node.setAttribute("on_click", str(hud_params["on_click"]))
        if "popup_style" in hud_params:
            hud_ui_node.setAttribute("popup_style", str(hud_params["popup_style"]))
        if "max_seats" in hud_params:
            hud_ui_node.setAttribute("max_seats", str(hud_params["max_seats"]))
        if "disable_hud" in hud_params:
            hud_ui_node.setAttribute("disable_hud", str(hud_params["disable_hud"]))
        if "query_limit" in hud_params:
            hud_ui_node.setAttribute("query_limit", str(hud_params["query_limit"]))
        if "debug_hud" in hud_params:
            hud_ui_node.setAttribute("debug_hud", str(hud_params["debug_hud"]))
        if "save_layout" in hud_params:
            hud_ui_node.setAttribute("save_layout", str(hud_params["save_layout"]))
        if "player_profiling" in hud_params:
            hud_ui_node.setAttribute("player_profiling", str(hud_params["player_profiling"]))
        if "profile_in_name" in hud_params:
            hud_ui_node.setAttribute("profile_in_name", str(hud_params["profile_in_name"]))
        if "profile_min_hands" in hud_params:
            hud_ui_node.setAttribute("profile_min_hands", str(hud_params["profile_min_hands"]))

        # Update the internal ui object
        if hasattr(self, "ui"):
            for key, value in hud_params.items():
                if key == "label":
                    self.ui.label = value
                elif key == "card_ht":
                    self.ui.card_ht = str(value)
                elif key == "card_wd":
                    self.ui.card_wd = str(value)
                elif key == "deck_type":
                    self.ui.deck_type = value
                elif key == "card_back":
                    self.ui.card_back = value
                elif key == "stat_range":
                    self.ui.stat_range = value
                elif key == "hud_days":
                    self.ui.hud_days = str(value)
                elif key == "agg_bb_mult":
                    self.ui.agg_bb_mult = str(value)
                elif key == "seats_style":
                    self.ui.seats_style = value
                elif key == "seats_cust_nums_low":
                    self.ui.seats_cust_nums_low = str(value)
                elif key == "seats_cust_nums_high":
                    self.ui.seats_cust_nums_high = str(value)
                elif key == "h_stat_range":
                    self.ui.h_stat_range = value
                elif key == "h_hud_days":
                    self.ui.h_hud_days = str(value)
                elif key == "h_agg_bb_mult":
                    self.ui.h_agg_bb_mult = str(value)
                elif key == "h_seats_style":
                    self.ui.h_seats_style = value
                elif key == "h_seats_cust_nums_low":
                    self.ui.h_seats_cust_nums_low = str(value)
                elif key == "h_seats_cust_nums_high":
                    self.ui.h_seats_cust_nums_high = str(value)
                elif key == "player_profiling":
                    self.ui.player_profiling = str(value)
                elif key == "profile_in_name":
                    self.ui.profile_in_name = str(value)
                elif key == "profile_min_hands":
                    self.ui.profile_min_hands = str(value)
