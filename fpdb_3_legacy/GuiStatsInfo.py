#!/usr/bin/env python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

STATS_DATA = {
    "Preflop": [
        {
            "name": "Voluntarily Put In Pot",
            "abbr": "VPIP",
            "desc": "Percentage of times a player voluntarily put chips in the pot preflop (by calling or raising). Excludes posting blinds when folding.",
            "formula": "VPIP = (Voluntary Calls + Preflop Raises) / (Hands Played - Walks - All-in Blind - Folded Blind) * 100",
            "sql": "handsplayers.street0VPI = 1"
        },
        {
            "name": "Preflop Raise",
            "abbr": "PFR",
            "desc": "Percentage of times a player raised preflop when having the opportunity.",
            "formula": "PFR = Preflop Raises / (Hands Played - Walks) * 100",
            "sql": "handsplayers.street0Raises > 0"
        },
        {
            "name": "Three-Bet",
            "abbr": "PF3",
            "desc": "Percentage of times a player re-raised a raise preflop.",
            "formula": "Three-Bet = Preflop 3-Bets / Preflop 3-Bet Opportunities * 100",
            "sql": "handsplayers.street0Raises = 2 (where opportunity existed)"
        },
        {
            "name": "Four-Bet",
            "abbr": "PF4",
            "desc": "Percentage of times a player re-raised a 3-bet preflop.",
            "formula": "Four-Bet = Preflop 4-Bets / Preflop 4-Bet Opportunities * 100",
            "sql": "handsplayers.street0Raises = 3 (where opportunity existed)"
        },
        {
            "name": "Steal Attempt",
            "abbr": "Steals",
            "desc": "Percentage of times a player raised preflop from late position (CO, BTN, SB) when everyone folded before them.",
            "formula": "Steal Attempt = Steal Raises / Steal Opportunities * 100",
            "sql": "Raised first-in from Cutoff (CO), Button (BTN), or Small Blind (SB)"
        },
        {
            "name": "Raise First In",
            "abbr": "RFI",
            "desc": "Percentage of times a player raised preflop when they were first to enter the pot.",
            "formula": "RFI = Preflop Raises First In / Preflop Raise First In Opportunities * 100",
            "sql": "Raised first-in from any position"
        },
        {
            "name": "Called a Raise Preflop",
            "abbr": "CARpre",
            "desc": "Percentage of times a player called a preflop raise instead of folding or re-raising.",
            "formula": "CARpre = Preflop Calls of Raise / Preflop Call of Raise Opportunities * 100",
            "sql": "Called preflop raise"
        },
        {
            "name": "Fold SB to Steal",
            "abbr": "fSB",
            "desc": "Percentage of times a player folded in the Small Blind when facing a steal attempt from late position.",
            "formula": "fSB = SB Folds to Steal / SB Stolen Opportunities * 100",
            "sql": "handsplayers.sbnotdef = 1 / handsplayers.sbstolen = 1"
        },
        {
            "name": "Fold BB to Steal",
            "abbr": "fBB",
            "desc": "Percentage of times a player folded in the Big Blind when facing a steal attempt from late position.",
            "formula": "fBB = BB Folds to Steal / BB Stolen Opportunities * 100",
            "sql": "handsplayers.bbnotdef = 1 / handsplayers.bbstolen = 1"
        },
        {
            "name": "Fold Blind to Steal",
            "abbr": "fB",
            "desc": "Percentage of times a player folded their blind (SB or BB) when facing a steal attempt.",
            "formula": "fB = (SB Folds + BB Folds to Steal) / (SB + BB Stolen Opportunities) * 100",
            "sql": "(sbnotdef + bbnotdef) / (sbstolen + bbstolen) * 100"
        },
        {
            "name": "Fold to Three-Bet",
            "abbr": "F3B",
            "desc": "Percentage of times a player folded to a preflop 3-bet after opening.",
            "formula": "F3B = Fold to 3-Bet / 3-Bet Faced Opportunities * 100",
            "sql": "handsplayers.f3b_0 / handsplayers.f3b_opp_0 * 100"
        },
        {
            "name": "Fold to Four-Bet",
            "abbr": "F4B",
            "desc": "Percentage of times a player folded to a preflop 4-bet after 3-betting.",
            "formula": "F4B = Fold to 4-Bet / 4-Bet Faced Opportunities * 100",
            "sql": "handsplayers.f4b_0 / handsplayers.f4b_opp_0 * 100"
        },
        {
            "name": "Squeeze",
            "abbr": "SQZ",
            "desc": "Percentage of times a player raised preflop when there was a raise and one or more calls before them.",
            "formula": "SQZ = Squeezes / Squeeze Opportunities * 100",
            "sql": "handsplayers.sqz_0 / handsplayers.sqz_opp_0 * 100"
        },
        {
            "name": "Re-Steal / Defend Steal",
            "abbr": "RST",
            "desc": "Percentage of times a player re-raised from the blinds facing a steal attempt from late position.",
            "formula": "RST = Raise to Steal / Raise to Steal Opportunities * 100",
            "sql": "handsplayers.rts / handsplayers.rts_opp * 100"
        },
        {
            "name": "Successful Steal",
            "abbr": "SucSt",
            "desc": "Percentage of steal attempts that won the blinds without further contest.",
            "formula": "SucSt = Successful Steals / Steal Attempts * 100",
            "sql": "handsplayers.success_Steal / handsplayers.stealDone * 100"
        }
    ],
    "Postflop": [
        {
            "name": "Continuation Bet",
            "abbr": "ContBet",
            "desc": "Percentage of times the preflop aggressor bet on the flop.",
            "formula": "ContBet = Flop Bets as Preflop Aggressor / Flop C-Bet Opportunities * 100",
            "sql": "Bet on flop when preflop aggressor"
        },
        {
            "name": "Aggression Factor",
            "abbr": "AggFac",
            "desc": "Ratio of aggressive actions (Bets + Raises) to passive actions (Calls) postflop.",
            "formula": "AggFac = (Total Bets + Total Raises) / Total Calls",
            "sql": "(bets + raises) / calls (across flop, turn, and river)"
        },
        {
            "name": "Aggression Frequency",
            "abbr": "AggFreq",
            "desc": "Percentage of postflop actions that were aggressive (bets or raises).",
            "formula": "AggFreq = (Total Bets + Total Raises) / (Total Bets + Total Raises + Total Calls + Total Folds) * 100",
            "sql": "(bets + raises) / (bets + raises + calls + folds)"
        },
        {
            "name": "Flop Three-Bet",
            "abbr": "Flop3B",
            "desc": "Percentage of times a player made the third bet on the flop when given the opportunity.",
            "formula": "Flop3B = Flop 3-Bets / Flop 3-Bet Opportunities * 100",
            "sql": "handsplayers.street1_3BDone / handsplayers.street1_3BChance * 100"
        },
        {
            "name": "Turn Three-Bet",
            "abbr": "Turn3B",
            "desc": "Percentage of times a player made the third bet on the turn when given the opportunity.",
            "formula": "Turn3B = Turn 3-Bets / Turn 3-Bet Opportunities * 100",
            "sql": "handsplayers.street2_3BDone / handsplayers.street2_3BChance * 100"
        },
        {
            "name": "River Three-Bet",
            "abbr": "Rivr3B",
            "desc": "Percentage of times a player made the third bet on the river when given the opportunity.",
            "formula": "Rivr3B = River 3-Bets / River 3-Bet Opportunities * 100",
            "sql": "handsplayers.street3_3BDone / handsplayers.street3_3BChance * 100"
        },
        {
            "name": "Flop Four-Bet",
            "abbr": "Flop4B",
            "desc": "Percentage of times a player made the fourth bet on the flop when given the opportunity.",
            "formula": "Flop4B = Flop 4-Bets / Flop 4-Bet Opportunities * 100",
            "sql": "handsplayers.street1_4BDone / handsplayers.street1_4BChance * 100"
        },
        {
            "name": "Turn Four-Bet",
            "abbr": "Turn4B",
            "desc": "Percentage of times a player made the fourth bet on the turn when given the opportunity.",
            "formula": "Turn4B = Turn 4-Bets / Turn 4-Bet Opportunities * 100",
            "sql": "handsplayers.street2_4BDone / handsplayers.street2_4BChance * 100"
        },
        {
            "name": "River Four-Bet",
            "abbr": "Rivr4B",
            "desc": "Percentage of times a player made the fourth bet on the river when given the opportunity.",
            "formula": "Rivr4B = River 4-Bets / River 4-Bet Opportunities * 100",
            "sql": "handsplayers.street3_4BDone / handsplayers.street3_4BChance * 100"
        },
        {
            "name": "Flop Open Bet",
            "abbr": "FOpen",
            "desc": "Percentage of times a player made the first bet into an unopened flop when given the opportunity.",
            "formula": "FOpen = Flop Open Bets / Flop Open Opportunities * 100",
            "sql": "handsplayers.street1OpenDone / handsplayers.street1OpenChance * 100"
        },
        {
            "name": "Turn Open Bet",
            "abbr": "TOpen",
            "desc": "Percentage of times a player made the first bet into an unopened turn when given the opportunity.",
            "formula": "TOpen = Turn Open Bets / Turn Open Opportunities * 100",
            "sql": "handsplayers.street2OpenDone / handsplayers.street2OpenChance * 100"
        },
        {
            "name": "River Open Bet",
            "abbr": "ROpen",
            "desc": "Percentage of times a player made the first bet into an unopened river when given the opportunity.",
            "formula": "ROpen = River Open Bets / River Open Opportunities * 100",
            "sql": "handsplayers.street3OpenDone / handsplayers.street3OpenChance * 100"
        },
        {
            "name": "Flop Aggression Frequency",
            "abbr": "FlAFq",
            "desc": "Percentage of flop actions that were aggressive (bets or raises).",
            "formula": "FlAFq = (Flop Bets + Flop Raises) / (Flop Bets + Flop Raises + Flop Calls + Flop Folds) * 100",
            "sql": "AggFreq calculated on Flop only"
        },
        {
            "name": "Turn Aggression Frequency",
            "abbr": "TuAFq",
            "desc": "Percentage of turn actions that were aggressive (bets or raises).",
            "formula": "TuAFq = (Turn Bets + Turn Raises) / (Turn Bets + Turn Raises + Turn Calls + Turn Folds) * 100",
            "sql": "AggFreq calculated on Turn only"
        },
        {
            "name": "River Aggression Frequency",
            "abbr": "RvAFq",
            "desc": "Percentage of river actions that were aggressive (bets or raises).",
            "formula": "RvAFq = (River Bets + River Raises) / (River Bets + River Raises + River Calls + River Folds) * 100",
            "sql": "AggFreq calculated on River only"
        },
        {
            "name": "Postflop Aggression Frequency",
            "abbr": "PoFAFq",
            "desc": "Postflop aggression frequency across all streets (Flop, Turn, River).",
            "formula": "PoFAFq = (Postflop Bets + Postflop Raises) / (Postflop Bets + Postflop Raises + Postflop Calls + Postflop Folds) * 100",
            "sql": "Sum of raises and bets divided by total active actions postflop"
        },
        {
            "name": "Fold to Continuation Bet Flop",
            "abbr": "f_cb1",
            "desc": "Percentage of times a player folded to a continuation bet on the flop.",
            "formula": "f_cb1 = Fold to C-Bet Flop / Flop C-Bet Faced Opportunities * 100",
            "sql": "handsplayers.f_cb_1 / handsplayers.f_cb_opp_1 * 100"
        }
    ],
    "Showdown": [
        {
            "name": "Went to Showdown",
            "abbr": "WtSDwsF",
            "desc": "Percentage of times a player reached showdown after seeing the flop.",
            "formula": "WtSDwsF = Showdowns Reached / Seen Flop Hands * 100",
            "sql": "Saw showdown / Saw flop"
        },
        {
            "name": "Won Money when Seen Flop",
            "abbr": "W$wsF",
            "desc": "Percentage of times a player won the hand after seeing the flop.",
            "formula": "W$wsF = Pots Won after Flop / Seen Flop Hands * 100",
            "sql": "Won hand / Saw flop"
        },
        {
            "name": "Won at Showdown",
            "abbr": "W$SD",
            "desc": "Percentage of times a player won money when reaching a showdown.",
            "formula": "W$SD = Showdowns Won / Showdowns Reached * 100",
            "sql": "Won hand at showdown / Saw showdown"
        },
        {
            "name": "Saw Showdown",
            "abbr": "SawSD",
            "desc": "Percentage of hands where the player saw the showdown.",
            "formula": "SawSD = Showdowns Reached / Hands Played * 100",
            "sql": "Saw showdown / Hands played"
        },
        {
            "name": "Saw Flop",
            "abbr": "Saw_F",
            "desc": "Percentage of hands where the player saw the flop (street 1 seen).",
            "formula": "Saw_F = Seen Flop Hands / Hands Played * 100",
            "sql": "sum(street1Seen) / count(1) * 100"
        }
    ],
    "Winrate & Rake": [
        {
            "name": "Big Blinds per 100",
            "abbr": "bb/100",
            "desc": "Average number of big blinds won per 100 hands played.",
            "formula": "bb/100 = (Net Profit / Big Blind Value) / (Hands Played / 100)",
            "sql": "Net winnings in bb / (hands / 100)"
        },
        {
            "name": "Big Blinds per 100 excluding Rake",
            "abbr": "bbxr/100",
            "desc": "Average number of big blinds won per 100 hands before deducting rake.",
            "formula": "bbxr/100 = ((Net Profit + Rake Paid) / Big Blind Value) / (Hands Played / 100)",
            "sql": "(Net winnings + rake) in bb / (hands / 100)"
        },
        {
            "name": "Net Profit",
            "abbr": "Net($)",
            "desc": "Total net monetary winnings/profit earned across all sessions.",
            "formula": "Net = Money Won - Money Contributed",
            "sql": "Sum of net from handsplayers"
        },
        {
            "name": "Rake Paid",
            "abbr": "Rake($)",
            "desc": "Total rake contributed or attributed to the player across all hands.",
            "formula": "Rake($) = Sum of Rake paid in all hands",
            "sql": "Sum of rake from handsplayers"
        },
        {
            "name": "Profit per Hand",
            "abbr": "Profit/Hnd",
            "desc": "Average net profit per hand.",
            "formula": "Profit/Hnd = Net Profit / Hands Played",
            "sql": "Net winnings divided by hand count"
        },
        {
            "name": "Profit per Hand excluding Rake",
            "abbr": "ProfitHndXR",
            "desc": "Average profit per hand before deducting rake.",
            "formula": "ProfitHndXR = (Net Profit + Rake Paid) / Hands Played",
            "sql": "(Net winnings + rake) divided by hand count"
        },
        {
            "name": "Variance",
            "abbr": "Variance",
            "desc": "Variance of outcomes in the selected sample.",
            "formula": "Variance = Average squared deviation from the mean result",
            "sql": "Computed from aggregate result dispersion"
        },
        {
            "name": "Standard Deviation / Variance",
            "abbr": "Std. Dev.",
            "desc": "A statistical measure of the dispersion of session outcomes around the mean winrate, representing variance.",
            "formula": "Standard Deviation = Square Root of Variance(bb/100)",
            "sql": "Computed variance across session aggregates"
        }
    ],
    "Tournaments": [
        {
            "name": "Tournaments Played",
            "abbr": "#",
            "desc": "Total count of tournaments played by the player.",
            "formula": "Tournaments Played = Count of unique Tournaments",
            "sql": "count(distinct tourneyId) / count(1)"
        },
        {
            "name": "In The Money",
            "abbr": "ITM%",
            "desc": "Percentage of tournaments where the player finished in a paying rank.",
            "formula": "ITM% = (Tournaments with Cashout > 0 / Total Tournaments) * 100",
            "sql": "sum(case when won > 0 then 1 else 0 end) / count(1) * 100"
        },
        {
            "name": "Return on Investment",
            "abbr": "ROI%",
            "desc": "The percentage return on total tournament buy-ins and fees spent.",
            "formula": "ROI% = ((Total Winnings - Total Spent) / Total Spent) * 100",
            "sql": "(sum(won) - sum(spent)) / sum(spent) * 100"
        },
        {
            "name": "Total Spent",
            "abbr": "Spent",
            "desc": "Total money spent on tournament entry buy-ins and rake fees.",
            "formula": "Spent = Sum of (Buy-ins + Fees)",
            "sql": "sum(buyin + fee)"
        },
        {
            "name": "Total Won",
            "abbr": "Won",
            "desc": "Total gross payouts won from tournaments.",
            "formula": "Won = Sum of Gross Payouts",
            "sql": "sum(won)"
        },
        {
            "name": "Net Winnings",
            "abbr": "Net",
            "desc": "Total net tournament winnings after subtracting buy-ins and fees.",
            "formula": "Net = Total Won - Total Spent",
            "sql": "sum(won - spent)"
        },
        {
            "name": "Profit per Tournament",
            "abbr": "$/Tour",
            "desc": "Average profit won per tournament played.",
            "formula": "$/Tour = Total Net Winnings / Tournaments Played",
            "sql": "sum(won - spent) / count(1)"
        },
        {
            "name": "Knockout Bounties",
            "abbr": "KO",
            "desc": "Tournament knockout bounty cash collected.",
            "formula": "KO = Sum of Bounty wins",
            "sql": "sum(bounty)"
        },
        {
            "name": "Re-Entries",
            "abbr": "ReEntry",
            "desc": "Total count of tournament re-entries/second chance buy-ins.",
            "formula": "Re-Entries = Count of re-entered events",
            "sql": "sum(reentries)"
        }
    ]
}


class GuiStatsInfo(QSplitter):
    def __init__(self, config, parent) -> None:
        super().__init__(parent)
        self.config = config
        self.parent = parent
        
        # Color fallbacks
        self.accent_color = "#b64fd8"
        self.fg_color = "#ffffff"
        
        # Left sidebar layout
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_layout.setSpacing(8)
        
        # Search filter field
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search statistics...")
        self.search_box.textChanged.connect(self.filter_stats)
        self.sidebar_layout.addWidget(self.search_box)
        
        # Sidebar list widget
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("statsListWidget")
        self.list_widget.currentItemChanged.connect(self.display_stat_detail)
        self.sidebar_layout.addWidget(self.list_widget)
        
        self.addWidget(self.sidebar_widget)
        
        # Right detail area
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("filterSidebar")
        self.scroll_area.setWidgetResizable(True)
        
        self.statsInfoFrame = QFrame()
        self.statsInfoFrame.setObjectName("statsInfoFrame")
        self.detail_layout = QVBoxLayout(self.statsInfoFrame)
        self.detail_layout.setContentsMargins(20, 20, 20, 20)
        self.detail_layout.setSpacing(15)
        
        # Rich Text Browser for documentation rendering
        self.text_browser = QTextBrowser()
        self.text_browser.setObjectName("statDetailsBrowser")
        self.text_browser.setOpenExternalLinks(True)
        self.detail_layout.addWidget(self.text_browser)
        
        self.scroll_area.setWidget(self.statsInfoFrame)
        self.addWidget(self.scroll_area)
        
        # Splitter sizing
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 3)
        self.setSizes([300, 900])
        
        # Initial population of stats list
        self.populate_list()
        
        # Select first item by default if any
        self.select_first_valid_item()

    def populate_list(self, filter_text: str = "") -> None:
        self.list_widget.clear()
        
        for category, stats in STATS_DATA.items():
            category_added = False
            for stat in stats:
                name = stat["name"]
                abbr = stat["abbr"]
                
                # Check filter matching
                if filter_text:
                    match = (filter_text.lower() in name.lower()) or (filter_text.lower() in abbr.lower())
                    if not match:
                        continue
                
                # Add category header if not added yet
                if not category_added and not filter_text:
                    header = QListWidgetItem()
                    header.setFlags(Qt.ItemFlag.NoItemFlags)
                    header.setData(Qt.ItemDataRole.UserRole, None)
                    self.list_widget.addItem(header)
                    
                    label = QLabel(category.upper())
                    label.setStyleSheet(
                        f"color: {self.accent_color}; "
                        f"font-weight: bold; "
                        f"font-size: 12px; "
                        f"background-color: transparent; "
                        f"padding: 12px 4px 4px 4px;"
                    )
                    self.list_widget.setItemWidget(header, label)
                    header.setSizeHint(label.sizeHint())
                    category_added = True
                
                # Indent child items under category headers
                display_text = f"  {name} ({abbr})" if not filter_text else f"{name} ({abbr})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, stat)
                self.list_widget.addItem(item)

    def select_first_valid_item(self) -> None:
        if self.list_widget.count() > 0:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole) is not None:
                    self.list_widget.setCurrentRow(i)
                    break

    def filter_stats(self, text: str) -> None:
        self.populate_list(text)
        self.select_first_valid_item()

    def display_stat_detail(self, current: QListWidgetItem, previous: QListWidgetItem = None) -> None:
        if current is None:
            self.text_browser.clear()
            return
            
        stat = current.data(Qt.ItemDataRole.UserRole)
        if stat is None:
            # Category header selected, ignore
            return
            
        name = stat["name"]
        abbr = stat["abbr"]
        desc = stat["desc"]
        formula = stat["formula"]
        sql_ref = stat["sql"]
        
        # Rich premium-aligned HTML documentation
        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; margin: 10px;">
            <h1 style="color: #60a5fa; font-size: 24px; font-weight: bold; margin-bottom: 5px; border-bottom: 2px solid #2d3748; padding-bottom: 10px;">
                {name} <span style="color: #94a3b8; font-size: 16px; font-weight: normal;">({abbr})</span>
            </h1>
            
            <div style="margin: 20px 0;">
                <h3 style="color: #38bdf8; font-size: 14px; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">Description</h3>
                <p style="color: #e2e8f0; font-size: 14px; margin-top: 0;">{desc}</p>
            </div>
            
            <div style="margin: 20px 0; background-color: #1e293b; border-left: 4px solid #10b981; border-radius: 4px; padding: 15px;">
                <h3 style="color: #10b981; font-size: 14px; font-weight: bold; text-transform: uppercase; margin-top: 0; margin-bottom: 8px; letter-spacing: 0.5px;">Formula</h3>
                <code style="color: #a7f3d0; font-family: 'Courier New', Courier, monospace; font-size: 13px; font-weight: bold; word-break: break-all;">
                    {formula}
                </code>
            </div>
            
            <div style="margin: 20px 0; background-color: #0f172a; border-radius: 6px; padding: 15px; border: 1px solid #1e293b;">
                <h3 style="color: #f59e0b; font-size: 13px; font-weight: bold; text-transform: uppercase; margin-top: 0; margin-bottom: 8px; letter-spacing: 0.5px;">SQL Database Field / Logic</h3>
                <code style="color: #fde047; font-family: 'Courier New', Courier, monospace; font-size: 12px; word-break: break-all;">
                    {sql_ref}
                </code>
            </div>
        </div>
        """
        self.text_browser.setHtml(html)

    def refresh_theme(self, colors: dict[str, str], theme_colors: dict[str, str]) -> None:
        """Called by ThemeManager when application theme changes."""
        bg_color = theme_colors.get("background", "#222b32")
        fg_color = theme_colors.get("foreground", "#ffffff")
        self.accent_color = colors.get("accent", "#b64fd8")
        self.fg_color = fg_color
        
        # Apply clean dark blue background to details browser
        self.statsInfoFrame.setStyleSheet(f"background-color: {bg_color};")
        self.text_browser.setStyleSheet(
            f"background-color: {bg_color}; border: 0; color: {fg_color};"
        )
        
        # Apply sidebar and search colors
        self.sidebar_widget.setStyleSheet(f"background-color: {colors.get('sidebar', '#1a1e24')};")
        self.search_box.setStyleSheet(
            f"background-color: {colors.get('input', '#20262b')}; "
            f"color: {colors.get('text', '#ffffff')}; "
            f"border: 1px solid {colors.get('border', '#46505a')};"
        )
        self.list_widget.setStyleSheet(
            f"background-color: {colors.get('input', '#20262b')}; "
            f"color: {colors.get('text', '#ffffff')}; "
            f"border: 1px solid {colors.get('border', '#46505a')};"
        )
        
        # Repopulate list to apply the new category header colors
        current_text = self.search_box.text()
        self.populate_list(current_text)
