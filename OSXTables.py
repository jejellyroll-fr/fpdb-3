#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OSX specific methods for Table class.
"""

import re
import subprocess
import ctypes
import json

from AppKit import NSView, NSWindowAbove, NSWorkspace
from Quartz.CoreGraphics import (CGWindowListCreateDescriptionFromArray, kCGWindowOwnerName, kCGWindowNumber,
                                 kCGWindowBounds, kCGWindowName, CGWindowListCopyWindowInfo, kCGNullWindowID,
                                 kCGWindowListExcludeDesktopElements, kCGWindowListOptionOnScreenOnly)

from AppKit import NSWorkspaceDidActivateApplicationNotification
from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtCore import Qt

from TableWindow import Table_Window
from Foundation import NSObject
from PyObjCTools import AppHelper
import objc

class TableActivationObserver(NSObject):
    def init(self):
        self = objc.super(TableActivationObserver, self).init()
        return self

    def applicationDidActivate_(self, notification):
        AppHelper.callAfter(self.check_active_app)

    def check_active_app(self):
        active_app = NSWorkspace.sharedWorkspace().activeApplication()
        if self.table.get_window_title() == active_app['NSApplicationName']:
            self.table.on_activate()
        else:
            self.table.on_deactivate()

class Table(Table_Window):
    def get_process_name(self):
        site_process_names = {
            'Winamax': 'Winamax',
            'PokerStars': 'PokerStars',
            # Ajoutez d'autres sites si nécessaire
        }
        return site_process_names.get(self.site, '').lower()

    def find_table_parameters(self):
        print(f"Searching for table: {self.search_string}")
        windows_info = self.get_window_titles_via_applescript()
        print(f"Found {len(windows_info)} windows")

        process_name = self.get_process_name()

        if hasattr(self, 'tournament') and self.tournament is not None:
            print(f"Searching for tournament: {self.tournament}, table: {getattr(self, 'table', 'N/A')}")
            for window in windows_info:
                if window['proc'].lower() == process_name:
                    print(f"Checking window: {window['name']}")
                    if f"Tournament {self.tournament} Table {self.table}" in window['name']:
                        print(f"Found matching tournament window: {window['name']}")
                        if isinstance(window['size'], dict):
                            if window['size']['width'] > 500 and window['size']['height'] > 400:
                                self.title = window['name']
                                self.number = self.get_window_number(
                                    title=self.title,
                                    size=window['size'],
                                    position=window['position'],
                                    pid=window['pid']
                                )
                                if self.number:
                                    print(f"Found tournament table. Number: {self.number}, Size: {window['size']}")
                                    return self.title
        else:
            for window in windows_info:
                if window['proc'].lower() == process_name:
                    print(f"Checking window: {window['name']}")
                    if self.check_bad_words(window['name']):
                        print(f"Skipping window due to bad words: {window['name']}")
                        continue
                    search_string = self.search_string.strip('/').strip()
                    if search_string.lower() in window['name'].lower():
                        print(f"Found matching window: {window['name']}")
                        if isinstance(window['size'], dict):
                            if window['size']['width'] > 500 and window['size']['height'] > 400:
                                self.title = window['name']
                                self.number = self.get_window_number(
                                    title=self.title,
                                    size=window['size'],
                                    position=window['position'],
                                    pid=window['pid']
                                )
                                if self.number:
                                    print(f"Found table. Number: {self.number}, Size: {window['size']}")
                                    return self.title

        print("No matching window found")
        return None

    def get_window_number(self, title, size, position, pid):
        print(f"Searching for window number for title: {title}")
        windows = CGWindowListCopyWindowInfo(kCGWindowListExcludeDesktopElements | kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

        process_name = self.get_process_name()

        for window in windows:
            owner_name = window.get(kCGWindowOwnerName, "")
            window_bounds = window.get(kCGWindowBounds, {})
            window_pid = window.get('kCGWindowOwnerPID', 0)
            print(f"Checking window: Owner='{owner_name}', PID={window_pid}, Bounds={window_bounds}")

            if owner_name.lower() == process_name and window_pid == pid:
                x = int(window_bounds.get('X', 0))
                y = int(window_bounds.get('Y', 0))
                width = int(window_bounds.get('Width', 0))
                height = int(window_bounds.get('Height', 0))

                if abs(x - position['x']) < 10 and abs(y - position['y']) < 10 and abs(width - size['width']) < 10 and abs(height - size['height']) < 10:
                    window_number = window.get(kCGWindowNumber)
                    print(f"Found matching window. Number: {window_number}")
                    return window_number

        print("No matching window number found")
        return None




    def get_window_titles_via_applescript(self):
        script = """
        tell application "System Events"
            set window_list to ""
            set process_list to processes where background only is false
            repeat with proc in process_list
                set proc_name to name of proc
                set proc_id to unix id of proc
                try
                    set window_names to name of every window of proc
                    set window_sizes to size of every window of proc
                    set window_positions to position of every window of proc
                    repeat with i from 1 to count of window_names
                        set win_name to item i of window_names
                        set win_size to item i of window_sizes
                        set win_position to item i of window_positions
                        -- Building the window info string
                        set win_info to proc_name & "||" & proc_id & "||" & win_name & "||" & (item 1 of win_size) & "," & (item 2 of win_size) & "||" & (item 1 of win_position) & "," & (item 2 of win_position)
                        if window_list is equal to "" then
                            set window_list to win_info
                        else
                            set window_list to window_list & ";;" & win_info
                        end if
                    end repeat
                end try
            end repeat
            return window_list
        end tell
        """
        
        print("Executing AppleScript...")
        
        try:
            proc = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = proc.communicate()
            
            print(f"Raw output: {output}")
            print(f"Raw error: {error}")
            
            if error:
                print(f"Error executing AppleScript: {error.decode('utf-8')}")
                return []
            
            # Decode the output
            raw_output = output.decode('utf-8').strip()
            print(f"Decoded output: {raw_output}")
            
            # Parsing the output
            window_info = []
            window_entries = raw_output.split(';;')
            
            for entry in window_entries:
                fields = entry.split('||')
                if len(fields) == 5:
                    proc_name, pid, win_name, size_str, position_str = fields
                    width, height = map(int, size_str.split(','))
                    x, y = map(int, position_str.split(','))
                    window_info.append({
                        "proc": proc_name,
                        "pid": int(pid),
                        "name": win_name,
                        "size": {"width": width, "height": height},
                        "position": {"x": x, "y": y}
                    })
                else:
                    print(f"Malformed entry: {entry}")
            
            print(f"Formatted window info: {json.dumps(window_info, indent=2)}")
            
            print(f"Nombre de fenêtres trouvées : {len(window_info)}")
            for window in window_info:
                print(f"Fenêtre trouvée : {window}")
            
            return window_info
        
        except Exception as e:
            print(f"Exception lors de l'exécution d'AppleScript : {e}")
            import traceback
            traceback.print_exc()
            return []




    def get_geometry(self):
        if self.number is None:
            return None
        
        WinListDict = CGWindowListCreateDescriptionFromArray((self.number,))
        for d in WinListDict:
            if d[kCGWindowNumber] == self.number:
                return {
                    'x': int(d[kCGWindowBounds]['X']),
                    'y': int(d[kCGWindowBounds]['Y']),
                    'width': int(d[kCGWindowBounds]['Width']),
                    'height': int(d[kCGWindowBounds]['Height'])
                }
        return None

    def get_window_title(self):
        if self.number is None:
            return None
        
        WinListDict = CGWindowListCreateDescriptionFromArray((self.number,))
        for d in WinListDict:
            if d[kCGWindowNumber] == self.number:
                return d[kCGWindowOwnerName]
        return None

    def topify(self, window):
        winid = window.effectiveWinId()
        cvp = ctypes.c_void_p(int(winid))
        view = NSView(c_void_p=cvp)
        if window.isVisible():
            view.window().orderWindow_relativeTo_(NSWindowAbove, self.number)
        window.windowHandle().setFlags(Qt.Window | Qt.FramelessWindowHint)

    def raise_hud_windows(self):
        if self.hud:
            for window in self.hud.windows:
                window.raise_()

    def setup_activation_monitoring(self):
        self.activation_observer = TableActivationObserver.alloc().init()
        self.activation_observer.table = self
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self.activation_observer,
            'applicationDidActivate:',
            NSWorkspaceDidActivateApplicationNotification,
            None
        )

    def on_activate(self):
        if self.hud:
            for window in self.hud.windows:
                window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                window.show()
        self.raise_hud_windows()

    def on_deactivate(self):
        if self.hud:
            for window in self.hud.windows:
                window.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                window.show()

    def check_bad_words(self, title):
        # Implement this method to check for unwanted words in the title
        # Return True if bad words are found, False otherwise
        return False